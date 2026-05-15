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
if (length(args) < 1) stop("Usage: Rscript 09_gene_analysis.R <params.json>")

params <- read_params(args[1])
output_dir <- params$output_dir %||% params$cache_dir %||% "."
ensure_dir(output_dir)
set.seed(as.integer(params$seed %||% 1234))

input_rds <- as.character(params$input_rds %||% "")
label_col <- as.character(params$label_col %||% "cell.type")
gene_name <- trimws(as.character(params$gene %||% ""))
multi_genes_raw <- as.character(params$multi_genes %||% "")
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

pairwise_matrix_to_table <- function(mat, stat_name) {
  if (is.null(mat)) {
    return(data.frame())
  }
  rows <- rownames(mat)
  cols <- colnames(mat)
  out <- list()
  idx <- 1
  for (r in seq_along(rows)) {
    for (c in seq_along(cols)) {
      value <- mat[r, c]
      if (!is.na(value)) {
        out[[idx]] <- data.frame(
          group1 = rows[r],
          group2 = cols[c],
          metric = stat_name,
          value = as.numeric(value),
          stringsAsFactors = FALSE
        )
        idx <- idx + 1
      }
    }
  }
  if (length(out) == 0) {
    return(data.frame())
  }
  do.call(rbind, out)
}

split_multi_genes <- function(text) {
  if (!nzchar(text)) {
    return(character(0))
  }
  genes <- unlist(strsplit(text, "[,;\n\r\t ]+"))
  genes <- unique(trimws(as.character(genes)))
  genes[nzchar(genes)]
}

with_prefix <- function(name) {
  if (!nzchar(result_prefix)) {
    return(name)
  }
  paste0(result_prefix, "_", name)
}

make_palette <- function(n) {
  cols <- get_color_scheme(n = max(n, 3))
  cols[seq_len(n)]
}

resolve_gene_method <- function(stat_method) {
  method <- tolower(trimws(as.character(stat_method %||% "wilcox")))
  if (identical(method, "mast")) {
    return(list(
      requested = stat_method,
      used = "wilcox",
      message = "Method 'MAST' is not available in single-gene analysis and has been replaced with wilcox."
    ))
  }
  if (!method %in% c("wilcox", "t", "bimod")) {
    return(list(
      requested = stat_method,
      used = "wilcox",
      message = sprintf("Method '%s' is unsupported in single-gene analysis. Falling back to wilcox.", stat_method)
    ))
  }
  list(requested = stat_method, used = method, message = "")
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

build_expression_dotplot <- function(meta_df, x_col = "label", y_col = NULL, value_col = "expr", title = "Single-Gene Expression DotPlot") {
  summary_df <- meta_df %>%
    group_by(across(all_of(c(if (!is.null(y_col)) y_col else character(0), x_col)))) %>%
    summarise(
      pct_exp = mean(.data[[value_col]] > 0, na.rm = TRUE) * 100,
      avg_exp = mean(.data[[value_col]], na.rm = TRUE),
      .groups = "drop"
    )

  if (is.null(y_col)) {
    summary_df$plot_row <- "All Labels"
  } else {
    summary_df$plot_row <- summary_df[[y_col]]
  }
  summary_df$plot_col <- summary_df[[x_col]]
  summary_df$plot_row <- factor(as.character(summary_df$plot_row), levels = unique(as.character(summary_df$plot_row)))
  summary_df$plot_col <- factor(as.character(summary_df$plot_col), levels = unique(as.character(summary_df$plot_col)))

  ggplot(summary_df, aes(x = plot_col, y = plot_row)) +
    geom_point(aes(size = pct_exp, colour = avg_exp), alpha = 0.92) +
    scale_size_continuous(name = "Pct. Expressing Cells", range = c(2.2, 11)) +
    scale_colour_gradient(low = "#D6E7F5", high = sc_colors[1], name = "Average Expression") +
    labs(title = title, x = NULL, y = NULL) +
    sc_theme +
    theme(axis.text.x = element_text(angle = 35, hjust = 1))
}

run_gene_comparison <- function(obj, gene_name, label_col, comparison_mode, group_1, group_2, selected_label, selected_label_2, stat_method, output_dir) {
  if (!"group" %in% colnames(obj@meta.data)) {
    stop("Current object does not contain a 'group' column, so group comparison is unavailable.")
  }
  method_info <- resolve_gene_method(stat_method)

  compare_df <- FetchData(obj, vars = c("group", label_col, gene_name))
  colnames(compare_df) <- c("group", "label", "expr")
  compare_df <- compare_df[!is.na(compare_df$group) & !is.na(compare_df$label), , drop = FALSE]
  compare_df$group <- as.character(compare_df$group)
  compare_df$label <- as.character(compare_df$label)

  keep_cells <- rownames(compare_df)[compare_df$group %in% c(group_1, group_2)]
  if (identical(comparison_mode, "within_label")) {
    keep_cells <- intersect(keep_cells, rownames(compare_df)[compare_df$label == selected_label])
  }
  if (identical(comparison_mode, "cross_label")) {
    keep_cells <- rownames(compare_df)[
      (compare_df$group == group_1 & compare_df$label == selected_label) |
      (compare_df$group == group_2 & compare_df$label == selected_label_2)
    ]
  }
  if (length(keep_cells) < 2) {
    stop("Too few cells remained after applying the selected comparison filters.")
  }

  plot_df <- compare_df[keep_cells, , drop = FALSE]
  plot_df$group <- factor(plot_df$group, levels = c(group_1, group_2))
  plot_df <- plot_df[!is.na(plot_df$group), , drop = FALSE]
  n_group_1 <- sum(plot_df$group == group_1)
  n_group_2 <- sum(plot_df$group == group_2)
  if (n_group_1 < 2 || n_group_2 < 2) {
    stop("Each comparison group must contain at least two cells.")
  }

  comp_obj <- subset(obj, cells = keep_cells)
  if (identical(comparison_mode, "within_label")) {
    comp_obj <- subset(comp_obj, cells = colnames(comp_obj)[comp_obj@meta.data[[label_col]] == selected_label])
  }
  if (identical(comparison_mode, "cross_label")) {
    comp_obj <- subset(comp_obj, cells = colnames(comp_obj)[
      (as.character(comp_obj$group) == group_1 & as.character(comp_obj@meta.data[[label_col]]) == selected_label) |
      (as.character(comp_obj$group) == group_2 & as.character(comp_obj@meta.data[[label_col]]) == selected_label_2)
    ])
  }
  comp_obj$comparison_group <- factor(as.character(comp_obj$group), levels = c(group_1, group_2))
  Idents(comp_obj) <- "comparison_group"

  fm <- FindMarkers(
    comp_obj,
    ident.1 = group_1,
    ident.2 = group_2,
    features = gene_name,
    test.use = method_info$used,
    min.pct = 0,
    logfc.threshold = -Inf,
    verbose = FALSE
  )
  fm <- as.data.frame(fm)
  if (nrow(fm) == 0) {
    stop("No comparison statistics were returned for the selected gene.")
  }
  if (is.null(rownames(fm)) || length(rownames(fm)) == 0) {
    rownames(fm) <- gene_name
  }
  stat_row <- fm[1, , drop = FALSE]
  statistic_value <- if ("statistic" %in% colnames(stat_row)) stat_row$statistic[1] else NA_real_
  effect_value <- if ("avg_log2FC" %in% colnames(stat_row)) stat_row$avg_log2FC[1] else if ("avg_diff" %in% colnames(stat_row)) stat_row$avg_diff[1] else NA_real_
  comparison_name <- build_comparison_name(comparison_mode, group_1, group_2, selected_label, selected_label_2)

  if (identical(comparison_mode, "within_label")) {
    plot_df$plot_label <- selected_label
  } else {
    plot_df$plot_label <- "All Cells"
  }
  p_cmp <- build_expression_dotplot(
    plot_df,
    x_col = "group",
    y_col = "plot_label",
    value_col = "expr",
    title = if (identical(comparison_mode, "within_label")) {
      paste0(gene_name, " Expression Summary in ", selected_label)
    } else if (identical(comparison_mode, "cross_label")) {
      paste0(gene_name, ": ", group_1, " + ", selected_label, " vs ", group_2, " + ", selected_label_2)
    } else {
      paste0(gene_name, " Expression Summary Across Groups")
    }
  )
  fig <- save_plot(p_cmp, with_prefix("single_gene_group_comparison_plot"), output_dir, width = 6.8, height = 4.8)

  p_cmp_violin <- ggplot(plot_df, aes(x = group, y = expr, fill = group)) +
    geom_violin(scale = "width", alpha = 0.82, colour = "grey20") +
    geom_boxplot(width = 0.18, outlier.shape = NA, fill = "white", colour = "grey20") +
    scale_fill_manual(values = setNames(c(sc_colors[1], sc_colors[min(2, length(sc_colors))]), c(group_1, group_2))) +
    labs(
      title = if (identical(comparison_mode, "within_label")) {
        paste0(gene_name, " Expression in ", selected_label, ": ", group_1, " vs ", group_2)
      } else if (identical(comparison_mode, "cross_label")) {
        paste0(gene_name, ": ", group_1, " + ", selected_label, " vs ", group_2, " + ", selected_label_2)
      } else {
        paste0(gene_name, " Expression: ", group_1, " vs ", group_2)
      },
      x = NULL,
      y = "Expression"
    ) +
    sc_theme +
    theme(legend.position = "none")
  fig_violin <- save_plot(p_cmp_violin, with_prefix("single_gene_group_comparison_violin_plot"), output_dir, width = 6.5, height = 5.5)

  stats_df <- data.frame(
    comparison_name = comparison_name,
    method = method_info$used,
    requested_method = method_info$requested,
    group_1 = group_1,
    group_2 = group_2,
    label_col = label_col,
    selected_label = if (comparison_mode %in% c("within_label", "cross_label")) selected_label else "",
    selected_label_2 = if (identical(comparison_mode, "cross_label")) selected_label_2 else "",
    gene = gene_name,
    statistic = as.numeric(statistic_value),
    effect_size = as.numeric(effect_value),
    p_value = as.numeric(stat_row$p_val[1]),
    adjusted_p_value = as.numeric(stat_row$p_val_adj[1]),
    cells_group_1 = n_group_1,
    cells_group_2 = n_group_2,
    stringsAsFactors = FALSE
  )
  stats_csv <- file.path(output_dir, paste0(with_prefix("single_gene_group_comparison_stats"), ".csv"))
  write.csv(stats_df, stats_csv, row.names = FALSE)

  raw_csv <- file.path(output_dir, paste0(with_prefix("single_gene_group_comparison_values"), ".csv"))
  raw_df <- data.frame(cell_id = rownames(plot_df), group = as.character(plot_df$group), label = as.character(plot_df$label), expression = as.numeric(plot_df$expr), stringsAsFactors = FALSE)
  write.csv(raw_df, raw_csv, row.names = FALSE)

  list(
    figures = c(basename(fig), basename(fig_violin)),
    figure = basename(fig_violin),
    table = basename(stats_csv),
    raw_table = basename(raw_csv),
    comparison_name = comparison_name,
    method_used = method_info$used,
    method_message = method_info$message
  )
}

tryCatch({
  if (!file.exists(input_rds)) {
    stop(paste("Input object does not exist:", input_rds))
  }
  if (!nzchar(gene_name)) {
    stop("No target gene was provided.")
  }

  report_progress(5, "Loading object...")
  obj <- readRDS(input_rds)
  obj <- set_group_order(obj, params)
  if (inherits(obj[["RNA"]], "Assay5")) {
    tryCatch({
      obj[["RNA"]] <- JoinLayers(obj[["RNA"]])
    }, error = function(e) {})
  }
  DefaultAssay(obj) <- "RNA"

  if (!gene_name %in% rownames(obj)) {
    stop(sprintf("Gene %s was not found in the current object.", gene_name))
  }
  if (!label_col %in% colnames(obj@meta.data)) {
    stop(sprintf("Grouping column %s was not found in the current object.", label_col))
  }

  multi_genes <- split_multi_genes(multi_genes_raw)
  valid_multi_genes <- intersect(multi_genes, rownames(obj))
  ignored_multi_genes <- setdiff(multi_genes, valid_multi_genes)

  meta_df <- FetchData(obj, vars = c(label_col, gene_name))
  colnames(meta_df) <- c("label", "expr")
  meta_df$label <- as.character(meta_df$label)
  meta_df <- meta_df[!is.na(meta_df$label) & nzchar(meta_df$label), , drop = FALSE]
  meta_df$label <- factor(meta_df$label, levels = unique(meta_df$label))
  if (nrow(meta_df) == 0) {
    stop("No valid cell labels are available for plotting.")
  }

  label_cols <- make_palette(length(levels(meta_df$label)))
  names(label_cols) <- levels(meta_df$label)
  if ("group" %in% colnames(obj@meta.data)) {
    meta_df$group <- as.character(FetchData(obj, vars = "group")[rownames(meta_df), 1])
  } else {
    meta_df$group <- "All"
  }
  meta_df$cell_id <- rownames(meta_df)
  write_plot_data_csv(meta_df[, c("cell_id", "label", "group", "expr")], "single_gene_expression_values")

  report_progress(22, "Generating single-gene violin plot...")
  p_violin <- ggplot(meta_df, aes(x = label, y = expr, fill = label)) +
    geom_violin(scale = "width", alpha = 0.82, colour = "grey20") +
    scale_fill_manual(values = label_cols) +
    labs(title = paste0(gene_name, " Expression Across Labels"), x = NULL, y = "Expression") +
    sc_theme +
    theme(axis.text.x = element_text(angle = 40, hjust = 1), legend.position = "none")
  violin_summary_df <- meta_df %>% group_by(label, group) %>% summarise(mean_expression = mean(expr), median_expression = median(expr), pct_exp = mean(expr > 0) * 100, .groups = "drop")
  write_plot_data_csv(violin_summary_df, "single_gene_violin_plot_data")
  fig <- save_plot(p_violin, with_prefix("single_gene_violin_plot"), output_dir, width = max(8, length(levels(meta_df$label)) * 0.55), height = 6)
  all_figures <- c(all_figures, basename(fig))

  p_violin_all <- ggplot(meta_df, aes(x = label, y = expr, fill = group)) +
    geom_violin(position = position_dodge(width = 0.85), scale = "width", alpha = 0.8, colour = "grey20") +
    labs(title = paste0(gene_name, " Expression Across All Cell Types"), x = NULL, y = "Expression") +
    sc_theme +
    theme(axis.text.x = element_text(angle = 40, hjust = 1))
  fig <- save_plot(p_violin_all, with_prefix("violin_all_celltypes"), output_dir, width = max(8, length(levels(meta_df$label)) * 0.65), height = 6)
  all_figures <- c(all_figures, basename(fig))

  report_progress(38, "Generating single-gene expression dot plot...")
  p_dot <- build_expression_dotplot(
    meta_df,
    x_col = "label",
    y_col = NULL,
    value_col = "expr",
    title = paste0(gene_name, " Expression Summary Across Labels")
  )
  dotplot_df <- meta_df %>% group_by(label) %>% summarise(pct_exp = mean(expr > 0) * 100, avg_exp = mean(expr), .groups = "drop")
  write_plot_data_csv(dotplot_df, "single_gene_dotplot_data")
  fig <- save_plot(p_dot, with_prefix("single_gene_expression_dotplot"), output_dir, width = max(7, length(levels(meta_df$label)) * 0.48), height = 4.8)
  all_figures <- c(all_figures, basename(fig))

  if (length(unique(meta_df$group)) > 1) {
    grouped_dot_df <- meta_df %>% group_by(group, label) %>% summarise(pct_exp = mean(expr > 0) * 100, avg_exp = mean(expr), .groups = "drop")
    write_plot_data_csv(grouped_dot_df, "single_gene_grouped_dotplot_data")
    p_group_dot <- ggplot(grouped_dot_df, aes(x = label, y = group)) +
      geom_point(aes(size = pct_exp, colour = avg_exp), alpha = 0.92) +
      scale_size_continuous(name = "Pct. Expressing Cells", range = c(2, 10)) +
      scale_colour_gradient(low = "#D6E7F5", high = sc_colors[1], name = "Average Expression") +
      labs(title = paste0(gene_name, " DotPlot by Group"), x = NULL, y = NULL) +
      sc_theme + theme(axis.text.x = element_text(angle = 35, hjust = 1))
    fig <- save_plot(p_group_dot, with_prefix("single_gene_dotplot_grouped"), output_dir, width = max(8, length(levels(meta_df$label)) * 0.55), height = 5)
    all_figures <- c(all_figures, basename(fig))
  }

  report_progress(52, "Generating feature plot...")
  reduction_info <- choose_reduction(obj, preferred_reduction)
  red <- reduction_info$name
  if (nzchar(red)) {
    p_feat <- FeaturePlot(obj, features = gene_name, reduction = red) +
      scale_colour_gradient(low = "#E8F1F8", high = sc_colors[1]) +
      labs(title = paste0(gene_name, " Expression on ", toupper(red))) +
      sc_theme
    coords <- Embeddings(obj, red)
    feature_df <- data.frame(
      cell_id = rownames(coords),
      reduction = red,
      dim_1 = coords[, 1],
      dim_2 = coords[, 2],
      group = if ("group" %in% colnames(obj@meta.data)) as.character(obj$group) else "All",
      label = as.character(obj@meta.data[[label_col]]),
      gene = gene_name,
      expression = FetchData(obj, vars = gene_name)[rownames(coords), 1],
      stringsAsFactors = FALSE
    )
    write_plot_data_csv(feature_df, "single_gene_featureplot_data")
    fig <- save_plot(p_feat, with_prefix("single_gene_featureplot"), output_dir, width = 8, height = 6)
    all_figures <- c(all_figures, basename(fig))
    if ("group" %in% colnames(obj@meta.data) && length(unique(na.omit(as.character(obj$group)))) > 1) {
      n_groups <- length(unique(na.omit(as.character(obj$group))))
      p_feat_group <- build_group_feature_plot(
        feature_df,
        value_col = "expression",
        value_label = gene_name,
        title = paste0(gene_name, " Expression by Group on ", toupper(red))
      )
      if (!is.null(p_feat_group)) {
        fig <- save_plot(p_feat_group, with_prefix("single_gene_featureplot_by_group"), output_dir, width = max(10, 4.5 * n_groups), height = 6)
        all_figures <- c(all_figures, basename(fig))
      }
    }
    if (nzchar(reduction_info$message)) {
      cat(sprintf("Reduction fallback: %s\n", reduction_info$message))
    }
  } else {
    cat("Feature plot skipped because neither UMAP nor tSNE is available in the current object.\n")
  }

  report_progress(66, "Calculating cell type pairwise statistics...")
  pw_ct <- pairwise.wilcox.test(meta_df$expr, meta_df$label, p.adjust.method = "BH")
  ct_table <- pairwise_matrix_to_table(pw_ct$p.value, "celltype_padj")
  ct_table$gene <- gene_name
  ct_csv <- file.path(output_dir, paste0(with_prefix("single_gene_pairwise_celltype_stats"), ".csv"))
  write.csv(ct_table, ct_csv, row.names = FALSE)
  all_tables <- c(all_tables, basename(ct_csv))

  if ("group" %in% colnames(obj@meta.data) && length(unique(na.omit(obj$group))) > 1) {
    report_progress(78, "Calculating group pairwise statistics...")
    group_df <- FetchData(obj, vars = c("group", label_col, gene_name))
    colnames(group_df) <- c("group", "label", "expr")
    group_df <- group_df[!is.na(group_df$group) & !is.na(group_df$label), , drop = FALSE]
    if (nrow(group_df) > 0) {
      group_df$group <- factor(as.character(group_df$group), levels = unique(as.character(group_df$group)))
      group_df$label <- factor(as.character(group_df$label), levels = levels(meta_df$label))
      pw_group <- pairwise.wilcox.test(group_df$expr, interaction(group_df$label, group_df$group, sep = " | "), p.adjust.method = "BH")
      group_table <- pairwise_matrix_to_table(pw_group$p.value, "group_padj")
      group_table$gene <- gene_name
      group_csv <- file.path(output_dir, paste0(with_prefix("single_gene_pairwise_group_stats"), ".csv"))
      write.csv(group_table, group_csv, row.names = FALSE)
      all_tables <- c(all_tables, basename(group_csv))
    }
  }

  comparison_name <- ""
  method_used <- ""
  method_message <- ""
  if (!identical(comparison_mode, "basic")) {
    report_progress(88, "Running selected group comparison...")
    cmp <- run_gene_comparison(obj, gene_name, label_col, comparison_mode, group_1, group_2, selected_label, selected_label_2, stat_method, output_dir)
    all_figures <- c(all_figures, cmp$figures %||% cmp$figure)
    all_tables <- c(all_tables, cmp$table, cmp$raw_table)
    comparison_name <- cmp$comparison_name
    method_used <- cmp$method_used
    method_message <- cmp$method_message
    if (nzchar(method_message)) {
      cat(sprintf("Comparison method note: %s\n", method_message))
    }
  }

  if (length(valid_multi_genes) >= 2) {
    report_progress(92, "Generating multi-gene dot plot...")
    p_multi_dot <- DotPlot(obj, features = valid_multi_genes, group.by = label_col)
    multi_dot_data <- p_multi_dot$data
    write_plot_data_csv(multi_dot_data, "single_gene_multi_dotplot_data")
    p_multi_dot <- p_multi_dot +
      scale_colour_gradient(low = "#D6E7F5", high = sc_colors[1]) +
      labs(title = "Multi-Gene DotPlot", x = NULL, y = NULL) +
      sc_theme +
      theme(axis.text.x = element_text(angle = 35, hjust = 1))
    fig <- save_plot(p_multi_dot, with_prefix("single_gene_multi_dotplot"), output_dir, width = max(8, length(valid_multi_genes) * 0.38 + 3), height = 5.5)
    all_figures <- c(all_figures, basename(fig))

    expr_mat <- FetchData(obj, vars = valid_multi_genes)
    expr_mat$cell_id <- rownames(expr_mat)
    write_plot_data_csv(expr_mat[, c("cell_id", valid_multi_genes), drop = FALSE], "multi_gene_expression_matrix")
  }

  expr_matrix_csv <- file.path(output_dir, paste0(with_prefix("single_gene_expression_matrix"), ".csv"))
  write.csv(meta_df[, c("cell_id", "label", "group", "expr")], expr_matrix_csv, row.names = FALSE)
  all_tables <- c(all_tables, basename(expr_matrix_csv))
  expr_csv <- file.path(output_dir, paste0(with_prefix("single_gene_expression_summary"), ".csv"))
  summary_df <- meta_df %>% group_by(label, group) %>% summarise(mean_expr = mean(expr), median_expr = median(expr), pct_exp = mean(expr > 0) * 100, .groups = "drop")
  summary_df$gene <- gene_name
  summary_df$multi_gene_count <- length(valid_multi_genes)
  summary_df$ignored_multi_gene_count <- length(ignored_multi_genes)
  write.csv(summary_df, expr_csv, row.names = FALSE)
  all_tables <- c(all_tables, basename(expr_csv))

  write_summary(list(
    status = "success",
    action = "gene_analysis",
    gene = gene_name,
    label_col = label_col,
    reduction_used = red,
    reduction_fallback = reduction_info$fallback,
    reduction_message = reduction_info$message,
    comparison_mode = comparison_mode,
    comparison_name = comparison_name,
    object_source_label = object_source_label,
    result_prefix = result_prefix,
    method_used = method_used,
    method_message = method_message,
    valid_multi_genes = as.list(valid_multi_genes),
    ignored_multi_genes = as.list(ignored_multi_genes),
    figures = as.list(unique(all_figures)),
    tables = as.list(unique(all_tables))
  ), output_dir)
  report_progress(100, "Gene analysis finished")
}, error = function(e) {
  write_error_summary("Gene analysis", conditionMessage(e), "Please check the gene name, object level, grouping column, and comparison settings.", output_dir)
  cat(sprintf("Error: %s\n", conditionMessage(e)))
  quit(status = 1)
})
