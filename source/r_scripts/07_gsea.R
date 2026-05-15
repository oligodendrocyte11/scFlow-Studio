# Force project logs and R warnings to English when the system supports it.
.scflow_set_english_locale <- function() {
  Sys.setenv(LANGUAGE = "en", LANG = "en_US.UTF-8")
  for (loc in c("en_US.UTF-8", "C.UTF-8", "C")) {
    ok <- tryCatch({
      res <- suppressWarnings(Sys.setlocale("LC_MESSAGES", loc))
      !is.na(res) && nzchar(res)
    }, error = function(e) FALSE)
    if (isTRUE(ok)) break
  }
}
.scflow_set_english_locale()

suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
  library(dplyr)
  library(fgsea)
})

initial_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", initial_args, value = TRUE)
if (length(file_arg) > 0) {
  script_path <- sub("^--file=", "", file_arg[1])
  script_path <- gsub("~+~", " ", script_path, fixed = TRUE)
  SCRIPT_DIR <- dirname(normalizePath(script_path))
} else {
  SCRIPT_DIR <- getwd()
}
source(file.path(SCRIPT_DIR, "utils", "io_utils.R"))
source(file.path(SCRIPT_DIR, "utils", "plot_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: Rscript 07_gsea.R <params.json>")
}

params <- read_params(args[1])
output_dir <- params$output_dir %||% params$cache_dir %||% "."
ensure_dir(output_dir)
set.seed(as.integer(params$seed %||% 1234))

action <- as.character(params$action %||% "run_gsea")

safe_name <- function(x) {
  x <- gsub("[\\\\/:*?\"<>|]+", "_", x)
  x <- gsub("\\s+", "_", x)
  x <- gsub("_+", "_", x)
  x
}

wrap_label <- function(x, width = 42, max_lines = NULL) {
  x <- as.character(x)
  vapply(x, function(item) {
    text <- gsub("_", " ", item)
    lines <- strwrap(text, width = width)
    if (length(lines) == 0) {
      lines <- ""
    }
    if (!is.null(max_lines) && length(lines) > max_lines) {
      max_lines <- max(1, as.integer(max_lines))
      if (max_lines == 1) {
        trimmed <- strwrap(paste(lines, collapse = " "), width = width)[1]
        lines <- paste0(sub("\\.*$", "", substr(trimmed, 1, max(1, width - 3))), "...")
      } else {
        remaining <- paste(lines[max_lines:length(lines)], collapse = " ")
        trimmed <- strwrap(remaining, width = width)[1]
        if (nchar(remaining) > nchar(trimmed)) {
          trimmed <- paste0(sub("\\.*$", "", substr(trimmed, 1, max(1, width - 3))), "...")
        }
        lines <- c(lines[seq_len(max_lines - 1)], trimmed)
      }
    }
    paste(lines, collapse = "\n")
  }, character(1), USE.NAMES = FALSE)
}

read_deg_table <- function(path) {
  if (!file.exists(path)) {
    stop(sprintf("Cannot find the DEG results file: %s", path))
  }
  deg <- read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  if (!"gene" %in% colnames(deg)) {
    stop("The DEG result is missing the gene column; GSEA cannot continue.")
  }
  fc_col <- if ("avg_log2FC" %in% colnames(deg)) "avg_log2FC" else if ("avg_logFC" %in% colnames(deg)) "avg_logFC" else ""
  if (fc_col == "") {
    stop("The DEG result is missing avg_log2FC or avg_logFC; the ranked GSEA gene list cannot be constructed.")
  }
  if (!"p_val_adj" %in% colnames(deg)) {
    stop("The DEG result is missing p_val_adj; the ranked GSEA gene list cannot be constructed.")
  }
  list(table = deg, fc_col = fc_col)
}

build_ranked_gene_list <- function(deg, fc_col) {
  deg <- deg %>%
    filter(!is.na(gene), gene != "", !is.na(.data[[fc_col]]), !is.na(p_val_adj)) %>%
    mutate(rank_score = .data[[fc_col]] * (-log10(p_val_adj + 1e-300)))

  if (nrow(deg) == 0) {
    stop("The DEG result is empty; the ranked GSEA gene list cannot be constructed.")
  }

  deg <- deg %>%
    arrange(desc(abs(rank_score))) %>%
    group_by(gene) %>%
    slice_head(n = 1) %>%
    ungroup() %>%
    filter(is.finite(rank_score))

  stats <- deg$rank_score
  names(stats) <- deg$gene
  stats <- sort(stats, decreasing = TRUE)

  if (length(stats) < 10) {
    stop("Too few genes are available for stable GSEA ranking.")
  }
  stats
}

read_gmt_safe <- function(gmt_file) {
  if (!file.exists(gmt_file)) {
    stop(sprintf("GMT file does not exist: %s", gmt_file))
  }
  pathways <- tryCatch(
    fgsea::gmtPathways(gmt_file),
    error = function(e) {
      stop(sprintf("Failed to load the GMT file. Please check the file format: %s", conditionMessage(e)))
    }
  )
  if (length(pathways) == 0) {
    stop("No pathways were loaded from the GMT file.")
  }
  pathways
}

select_top_directional <- function(gsea_res, direction = c("positive", "negative"), top_n = 10) {
  direction <- match.arg(direction)
  if (direction == "positive") {
    df <- gsea_res %>% filter(NES > 0)
  } else {
    df <- gsea_res %>% filter(NES < 0)
  }

  if (nrow(df) == 0) {
    return(df)
  }

  df %>%
    arrange(padj, pval, desc(abs(NES))) %>%
    slice_head(n = top_n) %>%
    arrange(desc(abs(NES)))
}

build_directional_bubble_plot <- function(gsea_res, top_n, comparison_name, direction = c("positive", "negative")) {
  direction <- match.arg(direction)
  plot_df <- select_top_directional(gsea_res, direction = direction, top_n = top_n)
  if (nrow(plot_df) == 0) {
    return(NULL)
  }

  accent_col <- if (direction == "positive") {
    sc_colors[1]
  } else {
    if (length(sc_colors) >= 2) sc_colors[2] else "#4E79A7"
  }
  neutral_col <- if (length(sc_colors) >= 3) sc_colors[3] else "#B0B0B0"

  plot_df <- plot_df %>%
    mutate(
      sig_score = -log10(padj + 1e-300),
      pathway_wrap = wrap_label(pathway, width = 34, max_lines = 2),
      pathway_wrap = factor(pathway_wrap, levels = rev(pathway_wrap))
    )

  ggplot(plot_df, aes(x = NES, y = pathway_wrap)) +
    geom_point(aes(size = sig_score, colour = NES), alpha = 0.92) +
    scale_size_continuous(name = "-log10(padj)", range = c(3.2, 10.5)) +
    scale_colour_gradient(low = grDevices::adjustcolor(neutral_col, alpha.f = 0.8), high = accent_col, name = "NES") +
    labs(
      title = comparison_name,
      subtitle = NULL,
      x = "NES",
      y = NULL
    ) +
    sc_theme +
    theme(
      plot.title = element_text(face = "bold"),
      axis.text.y = element_text(size = 10, lineheight = 0.95),
      plot.margin = margin(12, 16, 12, 12)
    )
}

format_stat <- function(x) {
  if (is.null(x) || length(x) == 0 || is.na(x)) {
    return("NA")
  }
  formatC(x, format = "e", digits = 2)
}

build_enrichment_plot <- function(pathways, stats, pathway_name, comparison_name, pathway_stats = NULL) {
  subtitle_text <- comparison_name
  nes_value <- NA_real_
  padj_value <- NA_real_
  if (!is.null(pathway_stats) && nrow(pathway_stats) > 0) {
    nes_value <- pathway_stats$NES[[1]]
    padj_value <- pathway_stats$padj[[1]]
    subtitle_text <- sprintf(
      "%s    |    NES = %s    |    p.adjust = %s",
      comparison_name,
      format(round(nes_value, 3), nsmall = 3),
      format_stat(padj_value)
    )
  }

  plot_enrichment_data <- getFromNamespace("plotEnrichmentData", "fgsea")
  enrichment_df <- plot_enrichment_data(pathways[[pathway_name]], stats)
  curve_df <- enrichment_df$curve
  ticks_df <- enrichment_df$ticks
  pos_es <- enrichment_df$posES
  neg_es <- enrichment_df$negES
  spread_es <- max(abs(c(pos_es, neg_es, 0)))
  if (!is.finite(spread_es) || spread_es <= 0) {
    spread_es <- 1
  }

  tick_span <- spread_es * 0.08
  tick_offset <- spread_es * 0.08
  if (is.finite(nes_value) && nes_value < -1) {
    tick_bottom <- tick_offset
    tick_top <- tick_offset + tick_span
  } else {
    tick_top <- -tick_offset
    tick_bottom <- -(tick_offset + tick_span)
  }

  p <- ggplot(curve_df, aes(x = rank, y = ES)) +
    geom_hline(yintercept = 0, linewidth = 0.5, colour = "black") +
    geom_line(linewidth = 1.15, colour = sc_colors[1], lineend = "round") +
    geom_segment(
      data = ticks_df,
      aes(x = rank, xend = rank, y = tick_bottom, yend = tick_top),
      inherit.aes = FALSE,
      linewidth = 0.35,
      colour = "#D32F2F"
    ) +
    labs(
      title = wrap_label(pathway_name, width = 55),
      subtitle = subtitle_text,
      x = "Rank in ordered gene list",
      y = "Running enrichment score"
    ) +
    sc_theme +
    theme(
      plot.title = element_text(face = "bold", size = 14),
      plot.subtitle = element_text(size = 11, colour = "#4E5D6C"),
      plot.margin = margin(14, 16, 12, 12)
    )

  if (is.finite(nes_value) && nes_value > 1 && is.finite(pos_es)) {
    p <- p + geom_hline(yintercept = pos_es, linewidth = 0.6, colour = "#C62828", linetype = "dashed")
  } else if (is.finite(nes_value) && nes_value < -1 && is.finite(neg_es)) {
    p <- p + geom_hline(yintercept = neg_es, linewidth = 0.6, colour = "#C62828", linetype = "dashed")
  }

  p
}

write_gsea_summary <- function(summary_list) {
  write_summary(summary_list, output_dir)
}

tryCatch({
  if (action == "run_gsea") {
    deg_csv <- as.character(params$deg_csv %||% "")
    comparison_name <- as.character(params$comparison_name %||% "GSEA")
    gmt_file <- as.character(params$gmt_file %||% "")
    top_n <- as.integer(params$top_n %||% 10)
    min_size <- as.integer(params$min_size %||% 10)
    max_size <- as.integer(params$max_size %||% 500)

    report_progress(5, "Loading DEG results...")
    deg_info <- read_deg_table(deg_csv)
    deg <- deg_info$table
    fc_col <- deg_info$fc_col

    report_progress(15, "Building ranked gene list...")
    stats <- build_ranked_gene_list(deg, fc_col)

    report_progress(25, "Loading GMT file...")
    pathways <- read_gmt_safe(gmt_file)

    report_progress(45, "Running fgsea...")
    fgsea_res <- fgsea::fgsea(
      pathways = pathways,
      stats = stats,
      minSize = min_size,
      maxSize = max_size,
      eps = 0
    )

    if (nrow(fgsea_res) == 0) {
      stop("GSEA returned no pathways. Please check whether GMT gene names match the DEG gene names.")
    }

    fgsea_df <- as.data.frame(fgsea_res) %>%
      arrange(padj, pval, desc(abs(NES)))
    fgsea_df$leadingEdge <- vapply(
      fgsea_df$leadingEdge,
      function(x) paste(as.character(x), collapse = ";"),
      character(1)
    )

    results_name <- paste0("GSEA_results_", safe_name(comparison_name), ".csv")
    top_name <- paste0("GSEA_top", top_n, "_", safe_name(comparison_name), ".csv")
    context_name <- paste0("GSEA_context_", safe_name(comparison_name), ".rds")
    results_csv <- file.path(output_dir, results_name)
    top_csv <- file.path(output_dir, top_name)
    context_rds <- file.path(output_dir, context_name)

    report_progress(65, "Saving GSEA tables...")
    write.csv(fgsea_df, results_csv, row.names = FALSE)
    write.csv(head(fgsea_df, top_n), top_csv, row.names = FALSE)
    saveRDS(list(
      comparison_name = comparison_name,
      pathways = pathways,
      stats = stats,
      gmt_file = gmt_file,
      fc_col = fc_col,
      gsea_table = fgsea_df
    ), context_rds)

    figures_out <- list()

    report_progress(74, "Plotting positive GSEA bubble plot...")
    positive_plot <- build_directional_bubble_plot(
      fgsea_df,
      top_n = top_n,
      comparison_name = comparison_name,
      direction = "positive"
    )
    if (!is.null(positive_plot)) {
      positive_file <- save_plot(
        positive_plot,
        paste0("gsea_bubble_positive_", safe_name(comparison_name)),
        output_dir,
        width = 10,
        height = 7
      )
      figures_out <- append(figures_out, basename(positive_file))
    }

    report_progress(82, "Plotting negative GSEA bubble plot...")
    negative_plot <- build_directional_bubble_plot(
      fgsea_df,
      top_n = top_n,
      comparison_name = comparison_name,
      direction = "negative"
    )
    if (!is.null(negative_plot)) {
      negative_file <- save_plot(
        negative_plot,
        paste0("gsea_bubble_negative_", safe_name(comparison_name)),
        output_dir,
        width = 10,
        height = 7
      )
      figures_out <- append(figures_out, basename(negative_file))
    }

    top_pathway <- ""
    if (nrow(fgsea_df) > 0) {
      top_pathway <- as.character(fgsea_df$pathway[[1]])
    }
    if (identical(top_pathway, "") || is.na(top_pathway)) {
      top_pathway <- names(pathways)[1]
    }

    report_progress(90, "Plotting default single-pathway enrichment...")
    pathway_stats <- fgsea_df %>% filter(.data$pathway == top_pathway) %>% slice_head(n = 1)
    top_plot <- build_enrichment_plot(pathways, stats, top_pathway, comparison_name, pathway_stats = pathway_stats)
    top_plot_file <- save_plot(
      top_plot,
      paste0("gsea_pathway_top_", safe_name(comparison_name)),
      output_dir,
      width = 9,
      height = 6
    )
    figures_out <- append(figures_out, basename(top_plot_file))

    write_gsea_summary(list(
      status = "success",
      action = "run_gsea",
      comparison_name = comparison_name,
      results_csv = basename(results_csv),
      top_csv = basename(top_csv),
      context_rds = basename(context_rds),
      top_pathway = top_pathway,
      n_pathways = nrow(fgsea_df),
      pathways = as.list(as.character(fgsea_df$pathway)),
      figures = figures_out,
      tables = list(
        basename(results_csv),
        basename(top_csv)
      )
    ))
    report_progress(100, "GSEA finished")
  }

  if (action == "plot_pathway") {
    context_rds <- as.character(params$context_rds %||% "")
    pathway_name <- as.character(params$pathway_name %||% "")
    comparison_name <- as.character(params$comparison_name %||% "GSEA")

    if (!file.exists(context_rds)) {
      stop("Cannot find the GSEA context file. Please run GSEA first.")
    }
    ctx <- readRDS(context_rds)
    pathways <- ctx$pathways
    stats <- ctx$stats
    gsea_table <- ctx$gsea_table %||% data.frame()
    if (!pathway_name %in% names(pathways)) {
      stop(sprintf("The selected pathway is not present in the current GSEA results: %s", pathway_name))
    }

    report_progress(40, "Plotting single-pathway result...")
    pathway_stats <- gsea_table %>% filter(.data$pathway == pathway_name) %>% slice_head(n = 1)
    p <- build_enrichment_plot(pathways, stats, pathway_name, comparison_name, pathway_stats = pathway_stats)
    fig <- save_plot(
      p,
      paste0("gsea_pathway_", safe_name(pathway_name)),
      output_dir,
      width = 9,
      height = 6
    )

    write_gsea_summary(list(
      status = "success",
      action = "plot_pathway",
      comparison_name = comparison_name,
      pathway_name = pathway_name,
      figures = list(basename(fig)),
      tables = list()
    ))
    report_progress(100, "Single-pathway plot finished")
  }
}, error = function(e) {
  write_error_summary(
    "GSEA",
    conditionMessage(e),
    "Please check the DEG results, GMT file format, and gene-name consistency.",
    output_dir
  )
  cat(sprintf("Error: %s\n", conditionMessage(e)))
  quit(status = 1)
})
