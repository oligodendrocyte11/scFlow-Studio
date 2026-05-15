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
  library(Seurat)
  library(ggplot2)
  library(jsonlite)
  library(dplyr)
  library(patchwork)
  library(Matrix)
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
if (length(args) < 1) stop("Usage: Rscript 10_module_score.R <params.json>")

params <- read_params(args[1])
output_dir <- params$output_dir %||% params$cache_dir %||% "."
ensure_dir(output_dir)
set.seed(as.integer(params$seed %||% 1234))

input_rds <- as.character(params$input_rds %||% "")
label_col <- as.character(params$label_col %||% "cell.type")
input_mode <- as.character(params$input_mode %||% "custom")
gmt_file <- as.character(params$gmt_file %||% "")
selected_pathway <- trimws(as.character(params$selected_pathway %||% ""))
gene_set_file <- as.character(params$gene_set_file %||% "")
preferred_reduction <- as.character(params$preferred_reduction %||% "")
comparison_mode <- as.character(params$comparison_mode %||% "basic")
group_1 <- as.character(params$group_1 %||% "")
group_2 <- as.character(params$group_2 %||% "")
selected_label <- trimws(as.character(params$selected_label %||% ""))
selected_label_2 <- trimws(as.character(params$selected_label_2 %||% ""))
stat_method <- as.character(params$stat_method %||% "wilcox")
object_source_label <- as.character(params$object_source_label %||% "")
result_prefix <- trimws(as.character(params$result_prefix %||% ""))

if (!is.null(params$color_scheme) && exists("set_color_scheme")) {
  try(set_color_scheme(as.character(params$color_scheme)), silent = TRUE)
}

all_figures <- c()
all_tables <- c()

write_plot_data_csv <- function(df, basename_no_ext) {
  csv_path <- file.path(output_dir, paste0(with_prefix(basename_no_ext), ".csv"))
  write.csv(df, csv_path, row.names = FALSE)
  all_tables <<- c(all_tables, basename(csv_path))
  basename(csv_path)
}

set_group_order <- function(obj, params) {
  go <- params$group_order
  if (!is.null(go) && length(go) > 0) {
    go <- as.character(unlist(go))
    if ("group" %in% colnames(obj@meta.data)) {
      obj$group <- factor(obj$group, levels = go)
    }
  }
  obj
}

read_custom_gene_set <- function(path) {
  if (!file.exists(path)) {
    stop("Custom gene-set file was not found.")
  }
  ext <- tolower(tools::file_ext(path))
  genes <- character(0)
  if (ext == "txt") {
    genes <- readLines(path, warn = FALSE, encoding = "UTF-8")
  } else if (ext == "csv") {
    df <- read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
    if (ncol(df) == 0) {
      genes <- character(0)
    } else if ("gene" %in% tolower(colnames(df))) {
      genes <- df[[which(tolower(colnames(df)) == "gene")[1]]]
    } else {
      genes <- df[[1]]
    }
  } else {
    stop("Only txt or csv custom gene-set files are supported.")
  }
  genes <- unique(trimws(as.character(genes)))
  genes[nzchar(genes)]
}

read_gmt_gene_set <- function(path, pathway_name) {
  if (!file.exists(path)) {
    stop("GMT file was not found.")
  }
  if (!nzchar(pathway_name)) {
    stop("No pathway was selected from the GMT file.")
  }
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  for (line in lines) {
    parts <- strsplit(line, "\t", fixed = FALSE)[[1]]
    if (length(parts) >= 3 && identical(trimws(parts[1]), pathway_name)) {
      genes <- unique(trimws(parts[-c(1, 2)]))
      return(genes[nzchar(genes)])
    }
  }
  stop(sprintf("Pathway %s was not found in the GMT file.", pathway_name))
}

pairwise_matrix_to_table <- function(mat, stat_name) {
  if (is.null(mat)) return(data.frame())
  rows <- rownames(mat)
  cols <- colnames(mat)
  out <- list()
  idx <- 1
  for (r in seq_along(rows)) {
    for (c in seq_along(cols)) {
      value <- mat[r, c]
      if (!is.na(value)) {
        out[[idx]] <- data.frame(group1 = rows[r], group2 = cols[c], metric = stat_name, value = as.numeric(value), stringsAsFactors = FALSE)
        idx <- idx + 1
      }
    }
  }
  if (length(out) == 0) return(data.frame())
  do.call(rbind, out)
}

make_palette <- function(n) {
  cols <- get_color_scheme(n = max(n, 3))
  cols[seq_len(n)]
}

with_prefix <- function(name) {
  if (!nzchar(result_prefix)) {
    return(name)
  }
  paste0(result_prefix, "_", name)
}

build_group_feature_plot <- function(feature_df, value_col, value_label, title) {
  plot_df <- feature_df[!is.na(feature_df$group) & nzchar(as.character(feature_df$group)), , drop = FALSE]
  if (nrow(plot_df) == 0) {
    return(NULL)
  }
  plot_df$group <- factor(as.character(plot_df$group), levels = unique(as.character(plot_df$group)))
  ggplot(plot_df, aes(x = dim_1, y = dim_2, colour = .data[[value_col]])) +
    geom_point(size = 0.18, alpha = 0.92) +
    facet_wrap(~ group, nrow = 1) +
    scale_colour_gradient(low = "#E8F1F8", high = sc_colors[1], name = value_label) +
    labs(title = title, x = "umap_1", y = "umap_2") +
    coord_equal() +
    sc_theme +
    theme(panel.grid = element_blank())
}

choose_reduction <- function(obj, preferred_reduction = "") {
  available <- tolower(Reductions(obj))
  preferred <- tolower(trimws(as.character(preferred_reduction %||% "")))

  if (nzchar(preferred) && preferred %in% available) {
    return(list(name = preferred, fallback = FALSE, message = ""))
  }
  if ("umap" %in% available) {
    return(list(
      name = "umap",
      fallback = nzchar(preferred) && preferred != "umap",
      message = if (nzchar(preferred) && preferred != "umap") {
        sprintf("Preferred reduction '%s' was not found. Falling back to UMAP.", preferred)
      } else {
        ""
      }
    ))
  }
  if ("tsne" %in% available) {
    return(list(
      name = "tsne",
      fallback = nzchar(preferred) && preferred != "tsne",
      message = if (nzchar(preferred) && preferred != "tsne") {
        sprintf("Preferred reduction '%s' was not found. Falling back to tSNE.", preferred)
      } else {
        ""
      }
    ))
  }

  list(
    name = "",
    fallback = FALSE,
    message = "No UMAP or tSNE reduction is available in the current object."
  )
}

build_score_dotplot <- function(meta_df, value_col = "module_score") {
  dot_df <- meta_df %>%
    group_by(label) %>%
    summarise(
      pct_positive = mean(.data[[value_col]] > 0, na.rm = TRUE) * 100,
      avg_score = mean(.data[[value_col]], na.rm = TRUE),
      .groups = "drop"
    )
  dot_df$label <- factor(dot_df$label, levels = levels(meta_df$label))
  ggplot(dot_df, aes(x = 1, y = label)) +
    geom_point(aes(size = pct_positive, colour = avg_score), alpha = 0.92) +
    scale_size_continuous(name = "Positive Cells (%)", range = c(2, 10)) +
    scale_colour_gradient(low = "#D6E7F5", high = sc_colors[1], name = "Average Score") +
    scale_x_continuous(breaks = 1, labels = "Gene Set") +
    labs(title = "Module Score DotPlot", x = NULL, y = NULL) +
    sc_theme +
    theme(axis.text.x = element_text(size = 11))
}

resolve_score_method <- function(stat_method) {
  method <- tolower(trimws(as.character(stat_method %||% "wilcox")))
  if (identical(method, "mast")) {
    return(list(
      requested = stat_method,
      used = "wilcox",
      message = "Method 'MAST' is not available for gene-set score comparison and has been replaced with wilcox."
    ))
  }
  if (identical(method, "bimod")) {
    return(list(
      requested = stat_method,
      used = "wilcox",
      message = sprintf("Method '%s' is not suitable for gene-set scores stored in metadata. Falling back to wilcox.", stat_method)
    ))
  }
  if (!method %in% c("wilcox", "t")) {
    return(list(
      requested = stat_method,
      used = "wilcox",
      message = sprintf("Method '%s' is unsupported for module score comparison. Falling back to wilcox.", stat_method)
    ))
  }
  list(requested = stat_method, used = method, message = "")
}

build_comparison_name <- function(mode, group_1, group_2, selected_label = "", selected_label_2 = "") {
  if (identical(mode, "within_label") && nzchar(selected_label)) {
    return(sprintf("%s_in_%s_vs_%s", selected_label, group_1, group_2))
  }
  if (identical(mode, "cross_label")) {
    return(sprintf("%s_%s_vs_%s_%s", group_1, selected_label, group_2, selected_label_2))
  }
  if (identical(mode, "overall_group")) {
    return(sprintf("AllCells_%s_vs_%s", group_1, group_2))
  }
  ""
}

run_module_score_comparison <- function(obj, label_col, comparison_mode, group_1, group_2, selected_label, selected_label_2, stat_method, output_dir, selected_pathway, input_mode) {
  if (!"group" %in% colnames(obj@meta.data)) {
    stop("Current object does not contain a 'group' column, so group comparison is unavailable.")
  }

  method_info <- resolve_score_method(stat_method)
  compare_df <- FetchData(obj, vars = c("group", label_col, "module_score"))
  colnames(compare_df) <- c("group", "label", "module_score")
  compare_df <- compare_df[!is.na(compare_df$group) & !is.na(compare_df$label), , drop = FALSE]
  compare_df$group <- as.character(compare_df$group)
  compare_df$label <- as.character(compare_df$label)
  compare_df <- compare_df[compare_df$group %in% c(group_1, group_2), , drop = FALSE]
  if (identical(comparison_mode, "within_label")) {
    compare_df <- compare_df[compare_df$label == selected_label, , drop = FALSE]
  }
  if (identical(comparison_mode, "cross_label")) {
    compare_df <- compare_df[
      (compare_df$group == group_1 & compare_df$label == selected_label) |
      (compare_df$group == group_2 & compare_df$label == selected_label_2),
      , drop = FALSE
    ]
  }
  if (nrow(compare_df) < 4) {
    stop("Too few cells remained after applying the selected comparison filters.")
  }

  compare_df$group <- factor(compare_df$group, levels = c(group_1, group_2))
  compare_df <- compare_df[!is.na(compare_df$group), , drop = FALSE]
  n_group_1 <- sum(compare_df$group == group_1)
  n_group_2 <- sum(compare_df$group == group_2)
  if (n_group_1 < 2 || n_group_2 < 2) {
    stop("Each comparison group must contain at least two cells.")
  }

  test_res <- if (identical(method_info$used, "t")) {
    t.test(module_score ~ group, data = compare_df)
  } else {
    wilcox.test(module_score ~ group, data = compare_df, exact = FALSE)
  }
  comparison_name <- build_comparison_name(comparison_mode, group_1, group_2, selected_label, selected_label_2)

  p_cmp <- ggplot(compare_df, aes(x = group, y = module_score, fill = group)) +
    geom_violin(scale = "width", alpha = 0.82, colour = "grey20") +
    geom_boxplot(width = 0.18, outlier.shape = NA, fill = "white", colour = "grey20") +
    labs(
      title = if (identical(comparison_mode, "within_label")) {
        paste0("Module Score in ", selected_label, ": ", group_1, " vs ", group_2)
      } else {
        paste0("Module Score: ", group_1, " vs ", group_2)
      },
      x = NULL,
      y = "Module Score"
    ) +
    scale_fill_manual(values = setNames(c(sc_colors[1], sc_colors[min(2, length(sc_colors))]), c(group_1, group_2))) +
    sc_theme +
    theme(legend.position = "none")
  fig <- save_plot(p_cmp, with_prefix("gene_set_group_comparison_plot"), output_dir, width = 6.5, height = 5.5)

  stats_df <- data.frame(
    comparison_name = comparison_name,
    method = method_info$used,
    requested_method = method_info$requested,
    group_1 = group_1,
    group_2 = group_2,
    label_col = label_col,
    selected_label = if (comparison_mode %in% c("within_label", "cross_label")) selected_label else "",
    selected_label_2 = if (identical(comparison_mode, "cross_label")) selected_label_2 else "",
    gene_set_name = if (identical(input_mode, "gmt") && nzchar(selected_pathway)) selected_pathway else "Custom Gene Set",
    statistic = as.numeric(test_res$statistic),
    p_value = as.numeric(test_res$p.value),
    adjusted_p_value = as.numeric(p.adjust(test_res$p.value, method = "BH")),
    cells_group_1 = n_group_1,
    cells_group_2 = n_group_2,
    method_message = method_info$message,
    stringsAsFactors = FALSE
  )
  stats_csv <- file.path(output_dir, paste0(with_prefix("gene_set_group_comparison_stats"), ".csv"))
  write.csv(stats_df, stats_csv, row.names = FALSE)

  list(
    figure = basename(fig),
    table = basename(stats_csv),
    comparison_name = comparison_name,
    method_used = method_info$used,
    method_message = method_info$message
  )
}

tryCatch({
  if (!file.exists(input_rds)) stop("Input object does not exist.")

  report_progress(5, "Loading object...")
  obj <- readRDS(input_rds)
  obj <- set_group_order(obj, params)
  if (inherits(obj[["RNA"]], "Assay5")) {
    tryCatch({ obj[["RNA"]] <- JoinLayers(obj[["RNA"]]) }, error = function(e) {})
  }
  DefaultAssay(obj) <- "RNA"
  if (!label_col %in% colnames(obj@meta.data)) stop(sprintf("Grouping column %s was not found in the current object.", label_col))

  report_progress(15, "Reading gene set...")
  raw_genes <- if (identical(input_mode, "gmt")) {
    read_gmt_gene_set(gmt_file, selected_pathway)
  } else {
    read_custom_gene_set(gene_set_file)
  }
  if (length(raw_genes) == 0) stop("No valid genes were read from the selected gene set.")

  valid_genes <- intersect(raw_genes, rownames(obj))
  ignored_genes <- setdiff(raw_genes, valid_genes)
  if (length(valid_genes) < 3) {
    stop(sprintf("Only %d valid genes were found; this is too few for stable module scoring.", length(valid_genes)))
  }

  report_progress(30, "Calculating module score...")
  total_gene_n <- nrow(obj)
  ctrl_use <- if (total_gene_n < 500 || length(valid_genes) < 20) 1 else min(25, max(5, floor(length(valid_genes) / 2)))
  nbin_use <- max(4, min(24, floor(total_gene_n / 50)))
  obj <- AddModuleScore(
    obj,
    features = list(valid_genes),
    pool = rownames(obj),
    ctrl = ctrl_use,
    nbin = nbin_use,
    name = "ModuleScore"
  )
  score_col <- grep("^ModuleScore", colnames(obj@meta.data), value = TRUE)[1]
  obj$module_score <- obj@meta.data[[score_col]]

  meta_df <- FetchData(obj, vars = c(label_col, "module_score"))
  colnames(meta_df) <- c("label", "module_score")
  meta_df$label <- factor(as.character(meta_df$label), levels = unique(as.character(meta_df$label)))
  if ("group" %in% colnames(obj@meta.data)) {
    meta_df$group <- as.character(FetchData(obj, vars = "group")[rownames(meta_df), 1])
  } else {
    meta_df$group <- "All"
  }
  meta_df$cell_id <- rownames(meta_df)
  write_plot_data_csv(meta_df[, c("cell_id", "label", "group", "module_score")], "gene_set_score_matrix")
  label_cols <- make_palette(length(levels(meta_df$label)))
  names(label_cols) <- levels(meta_df$label)

  report_progress(50, "Generating feature plot...")
  reduction_info <- choose_reduction(obj, preferred_reduction)
  red <- reduction_info$name
  if (nzchar(red)) {
    plot_suffix <- if (identical(input_mode, "gmt") && nzchar(selected_pathway)) selected_pathway else "Custom Gene Set"
    p_feat <- FeaturePlot(obj, features = "module_score", reduction = red) +
      scale_colour_gradient(low = "#E8F1F8", high = sc_colors[1]) +
      labs(title = paste0(plot_suffix, " Module Score on ", toupper(red))) +
      sc_theme
    coords <- Embeddings(obj, red)
    feature_df <- data.frame(
      cell_id = rownames(coords),
      reduction = red,
      dim_1 = coords[, 1],
      dim_2 = coords[, 2],
      group = if ("group" %in% colnames(obj@meta.data)) as.character(obj$group) else "All",
      label = as.character(obj@meta.data[[label_col]]),
      pathway = plot_suffix,
      module_score = obj$module_score[rownames(coords)],
      stringsAsFactors = FALSE
    )
    write_plot_data_csv(feature_df, "gene_set_featureplot_data")
    fig <- save_plot(p_feat, with_prefix("gene_set_featureplot"), output_dir, width = 8, height = 6)
    all_figures <- c(all_figures, basename(fig))
    if ("group" %in% colnames(obj@meta.data) && length(unique(na.omit(as.character(obj$group)))) > 1) {
      n_groups <- length(unique(na.omit(as.character(obj$group))))
      p_feat_group <- build_group_feature_plot(
        feature_df,
        value_col = "module_score",
        value_label = "Module Score",
        title = paste0(plot_suffix, " Module Score by Group on ", toupper(red))
      )
      if (!is.null(p_feat_group)) {
        fig <- save_plot(p_feat_group, with_prefix("gene_set_featureplot_by_group"), output_dir, width = max(10, 4.5 * n_groups), height = 6)
        all_figures <- c(all_figures, basename(fig))
      }
    }
    if (nzchar(reduction_info$message)) {
      cat(sprintf("Reduction fallback: %s\n", reduction_info$message))
    }
  } else {
    cat("Module score feature plot skipped because neither UMAP nor tSNE is available in the current object.\n")
  }

  report_progress(65, "Generating violin plot...")
  p_vln <- ggplot(meta_df, aes(x = label, y = module_score, fill = label)) +
    geom_violin(scale = "width", alpha = 0.82, colour = "grey20") +
    scale_fill_manual(values = label_cols) +
    labs(title = "Module Score Distribution Across Cell Types", x = NULL, y = "Module Score") +
    sc_theme +
    theme(axis.text.x = element_text(angle = 40, hjust = 1), legend.position = "none")
  violin_df <- meta_df %>% group_by(label, group) %>% summarise(mean_score = mean(module_score), median_score = median(module_score), pct_positive = mean(module_score > 0) * 100, .groups = "drop")
  write_plot_data_csv(violin_df, "gene_set_violin_plot_data")
  fig <- save_plot(p_vln, with_prefix("gene_set_violin_plot"), output_dir, width = max(8, length(levels(meta_df$label)) * 0.55), height = 6)
  all_figures <- c(all_figures, basename(fig))

  p_vln_all <- ggplot(meta_df, aes(x = label, y = module_score, fill = group)) +
    geom_violin(position = position_dodge(width = 0.85), scale = "width", alpha = 0.82, colour = "grey20") +
    labs(title = "Module Score Across All Cell Types", x = NULL, y = "Module Score") +
    sc_theme +
    theme(axis.text.x = element_text(angle = 40, hjust = 1))
  fig <- save_plot(p_vln_all, with_prefix("violin_all_celltypes"), output_dir, width = max(8, length(levels(meta_df$label)) * 0.65), height = 6)
  all_figures <- c(all_figures, basename(fig))

  report_progress(78, "Generating dot plot...")
  p_dot <- build_score_dotplot(meta_df)
  dot_df <- meta_df %>% group_by(label) %>% summarise(pct_positive = mean(module_score > 0) * 100, avg_score = mean(module_score), .groups = "drop")
  write_plot_data_csv(dot_df, "gene_set_dotplot_data")
  fig <- save_plot(p_dot, with_prefix("gene_set_dotplot"), output_dir, width = 6.5, height = max(4.5, length(levels(meta_df$label)) * 0.4 + 1.8))
  all_figures <- c(all_figures, basename(fig))

  if (length(unique(meta_df$group)) > 1) {
    grouped_dot_df <- meta_df %>% group_by(group, label) %>% summarise(pct_positive = mean(module_score > 0) * 100, avg_score = mean(module_score), .groups = "drop")
    write_plot_data_csv(grouped_dot_df, "gene_set_grouped_dotplot_data")
    p_group_dot <- ggplot(grouped_dot_df, aes(x = label, y = group)) +
      geom_point(aes(size = pct_positive, colour = avg_score), alpha = 0.92) +
      scale_size_continuous(name = "Positive Cells (%)", range = c(2, 10)) +
      scale_colour_gradient(low = "#D6E7F5", high = sc_colors[1], name = "Average Score") +
      labs(title = "Module Score DotPlot by Group", x = NULL, y = NULL) +
      sc_theme + theme(axis.text.x = element_text(angle = 35, hjust = 1))
    fig <- save_plot(p_group_dot, with_prefix("gene_set_dotplot_grouped"), output_dir, width = max(8, length(levels(meta_df$label)) * 0.55), height = 5)
    all_figures <- c(all_figures, basename(fig))
  }

  report_progress(86, "Calculating pairwise statistics...")
  pw_ct <- pairwise.wilcox.test(meta_df$module_score, meta_df$label, p.adjust.method = "BH")
  ct_table <- pairwise_matrix_to_table(pw_ct$p.value, "celltype_padj")
  ct_table$source_mode <- input_mode
  ct_table$selected_pathway <- selected_pathway
  ct_csv <- file.path(output_dir, paste0(with_prefix("gene_set_pairwise_celltype_stats"), ".csv"))
  write.csv(ct_table, ct_csv, row.names = FALSE)
  all_tables <- c(all_tables, basename(ct_csv))

  if ("group" %in% colnames(obj@meta.data) && length(unique(na.omit(obj$group))) > 1) {
    group_df <- FetchData(obj, vars = c("group", label_col, "module_score"))
    colnames(group_df) <- c("group", "label", "module_score")
    group_df <- group_df[!is.na(group_df$group) & !is.na(group_df$label), , drop = FALSE]
    if (nrow(group_df) > 0) {
      group_df$group <- factor(as.character(group_df$group), levels = unique(as.character(group_df$group)))
      group_df$label <- factor(as.character(group_df$label), levels = levels(meta_df$label))
      pw_group <- pairwise.wilcox.test(group_df$module_score, interaction(group_df$label, group_df$group, sep = " | "), p.adjust.method = "BH")
      group_table <- pairwise_matrix_to_table(pw_group$p.value, "group_padj")
      group_table$source_mode <- input_mode
      group_table$selected_pathway <- selected_pathway
      group_csv <- file.path(output_dir, paste0(with_prefix("gene_set_pairwise_group_stats"), ".csv"))
      write.csv(group_table, group_csv, row.names = FALSE)
      all_tables <- c(all_tables, basename(group_csv))
    }
  }

  comparison_name <- ""
  method_used <- ""
  method_message <- ""
  if (!identical(comparison_mode, "basic")) {
    report_progress(92, "Running selected module score comparison...")
    cmp <- run_module_score_comparison(obj, label_col, comparison_mode, group_1, group_2, selected_label, selected_label_2, stat_method, output_dir, selected_pathway, input_mode)
    all_figures <- c(all_figures, cmp$figure)
    all_tables <- c(all_tables, cmp$table)
    comparison_name <- cmp$comparison_name
    method_used <- cmp$method_used
    method_message <- cmp$method_message
    if (nzchar(method_message)) {
      cat(sprintf("Comparison method note: %s\n", method_message))
    }
  }

  gene_table <- data.frame(
    gene = raw_genes,
    status = ifelse(raw_genes %in% valid_genes, "used", "ignored"),
    stringsAsFactors = FALSE
  )
  gene_csv <- file.path(output_dir, paste0(with_prefix("gene_set_gene_status"), ".csv"))
  write.csv(gene_table, gene_csv, row.names = FALSE)
  all_tables <- c(all_tables, basename(gene_csv))

  score_csv <- file.path(output_dir, paste0(with_prefix("gene_set_per_cell_scores"), ".csv"))
  score_df <- obj@meta.data
  score_df$cell_id <- rownames(score_df)
  keep_cols <- intersect(c("cell_id", label_col, "group", "module_score"), colnames(score_df))
  write.csv(score_df[, keep_cols, drop = FALSE], score_csv, row.names = FALSE)
  all_tables <- c(all_tables, basename(score_csv))

  write_summary(list(
    status = "success",
    action = "module_score",
    input_mode = input_mode,
    selected_pathway = selected_pathway,
    reduction_used = red,
    reduction_fallback = reduction_info$fallback,
    reduction_message = reduction_info$message,
    comparison_mode = comparison_mode,
    comparison_name = comparison_name,
    object_source_label = object_source_label,
    result_prefix = result_prefix,
    method_used = method_used,
    method_message = method_message,
    valid_gene_count = length(valid_genes),
    ignored_gene_count = length(ignored_genes),
    figures = as.list(unique(all_figures)),
    tables = as.list(unique(all_tables))
  ), output_dir)
  report_progress(100, "Module scoring finished")
}, error = function(e) {
  write_error_summary("Module scoring", conditionMessage(e), "Please check the input file format, selected pathway, valid gene count, and comparison settings.", output_dir)
  cat(sprintf("Error: %s\n", conditionMessage(e)))
  quit(status = 1)
})
