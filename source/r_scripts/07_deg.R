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

# ===========================================
# 07_deg.R - Differential expression analysis
# Supports single comparison, cross-cell-type comparison,
# and multiple pairwise comparisons in one run.
# ===========================================
suppressPackageStartupMessages({
  library(Seurat)
  library(ggplot2)
  library(dplyr)
  library(jsonlite)
})

if (requireNamespace("MAST", quietly = TRUE)) {
  suppressPackageStartupMessages(library(MAST))
}

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

if (requireNamespace("ggrepel", quietly = TRUE)) {
  library(ggrepel)
  has_ggrepel <- TRUE
} else {
  has_ggrepel <- FALSE
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Usage: Rscript 07_deg.R <params.json>")

params <- read_params(args[1])
output_dir <- params$output_dir %||% "."
ensure_dir(output_dir)
set.seed(as.integer(params$seed %||% 1234))

old_ver <- getOption("Seurat.object.assay.version")
options(Seurat.object.assay.version = "v3")
on.exit({ options(Seurat.object.assay.version = old_ver) }, add = TRUE)

input_rds <- as.character(params$input_rds %||% "")
celltype_col <- as.character(params$celltype_col %||% "cell.type")
group_1 <- as.character(params$group_1 %||% "")
ct_1 <- as.character(params$ct_1 %||% "")
group_2 <- as.character(params$group_2 %||% "")
ct_2 <- as.character(params$ct_2 %||% "")
test_use <- as.character(params$test_use %||% "MAST")
min_pct <- as.numeric(params$min_pct %||% 0.1)
logfc_threshold <- as.numeric(params$logfc_threshold %||% 0.6)
padj_cutoff <- as.numeric(params$padj_cutoff %||% 0.05)
comparison_name <- as.character(params$comparison_name %||% "DEG")
comparison_mode <- as.character(params$comparison_mode %||% "same_celltype")
object_source_label <- as.character(params$object_source_label %||% "")
object_source_key <- as.character(params$object_source_key %||% "main")
comparisons_param <- params$comparisons %||% list()
result_id <- as.character(params$result_id %||% "")
result_name <- as.character(params$result_name %||% "")

all_figures <- c()
all_tables <- c()
comparison_summaries <- list()

sanitize_filename_stub <- function(x) {
  x <- as.character(x %||% "")
  x <- trimws(x)
  if (!nzchar(x)) return("comparison")
  x <- iconv(x, from = "", to = "ASCII//TRANSLIT", sub = "_")
  x <- gsub("[^A-Za-z0-9._-]+", "_", x)
  x <- gsub("_+", "_", x)
  x <- gsub("^_|_$", "", x)
  if (!nzchar(x)) x <- "comparison"
  tolower(x)
}

normalize_choice <- function(x) {
  if (is.null(x) || length(x) == 0) return("")
  x <- trimws(as.character(x[[1]] %||% ""))
  if (!nzchar(x) || x %in% c("", "(All)", "All", "ALL", "all", "*")) return("")
  x
}

build_side_label <- function(group_name, celltype_name) {
  parts <- c(normalize_choice(group_name), normalize_choice(celltype_name))
  parts <- parts[nzchar(parts)]
  if (length(parts) == 0) return("all")
  paste(parts, collapse = "_")
}

build_comparison_name <- function(comp, idx) {
  explicit_name <- trimws(as.character(comp$comparison_name %||% ""))
  if (nzchar(explicit_name)) return(explicit_name)
  base_name <- paste0(
    build_side_label(comp$group_1, comp$ct_1),
    "_vs_",
    build_side_label(comp$group_2, comp$ct_2)
  )
  base_name <- sanitize_filename_stub(base_name)
  if (!nzchar(base_name)) base_name <- sprintf("comparison_%02d", idx)
  paste0(object_source_key, "__", base_name)
}

materialize_comparisons <- function() {
  out <- list()
  out[[1]] <- list(
    group_1 = normalize_choice(group_1),
    ct_1 = normalize_choice(ct_1),
    group_2 = normalize_choice(group_2),
    ct_2 = normalize_choice(ct_2),
    comparison_name = comparison_name
  )
  if (identical(comparison_mode, "same_celltype")) {
    out <- lapply(out, function(comp) {
      if (!nzchar(comp$ct_1) && nzchar(comp$ct_2)) comp$ct_1 <- comp$ct_2
      if (!nzchar(comp$ct_2) && nzchar(comp$ct_1)) comp$ct_2 <- comp$ct_1
      comp
    })
  }
  out
}

filter_cells <- function(obj, grp, ct, ct_col) {
  mask <- rep(TRUE, ncol(obj))
  if (nzchar(grp) && "group" %in% colnames(obj@meta.data)) {
    mask <- mask & as.character(obj$group) == grp
  }
  if (nzchar(ct) && ct_col %in% colnames(obj@meta.data)) {
    mask <- mask & as.character(obj@meta.data[[ct_col]]) == ct
  }
  colnames(obj)[mask]
}

run_single_comparison <- function(obj, comp, idx) {
  comp_name <- build_comparison_name(comp, idx)
  comp_stub <- sanitize_filename_stub(comp_name)

  report_progress(min(20 + idx * 5, 65), sprintf("Running comparison %d/%d...", idx, length(comparisons)))
  cat(sprintf("\n=== DEG comparison %d/%d: %s ===\n", idx, length(comparisons), comp_name))
  cat(sprintf("  Set1: group='%s' %s='%s'\n", comp$group_1, celltype_col, comp$ct_1))
  cat(sprintf("  Set2: group='%s' %s='%s'\n", comp$group_2, celltype_col, comp$ct_2))

  cells_1 <- filter_cells(obj, comp$group_1, comp$ct_1, celltype_col)
  cells_2 <- filter_cells(obj, comp$group_2, comp$ct_2, celltype_col)
  if (length(cells_1) < 3) stop(sprintf("Comparison '%s': Set1 has fewer than 3 cells.", comp_name))
  if (length(cells_2) < 3) stop(sprintf("Comparison '%s': Set2 has fewer than 3 cells.", comp_name))

  overlap <- intersect(cells_1, cells_2)
  if (length(overlap) > 0) {
    cells_2 <- setdiff(cells_2, overlap)
  }
  if (length(cells_2) < 3) stop(sprintf("Comparison '%s': Set2 has fewer than 3 non-overlapping cells.", comp_name))

  obj_sub <- subset(obj, cells = union(cells_1, cells_2))
  obj_sub$deg_group <- NA_character_
  names(obj_sub$deg_group) <- colnames(obj_sub)
  obj_sub$deg_group[colnames(obj_sub) %in% cells_1] <- "Set1"
  obj_sub$deg_group[colnames(obj_sub) %in% cells_2] <- "Set2"
  Idents(obj_sub) <- "deg_group"

  deg <- FindMarkers(
    obj_sub,
    ident.1 = "Set1",
    ident.2 = "Set2",
    test.use = test_use,
    min.pct = min_pct,
    logfc.threshold = 0,
    only.pos = FALSE
  )
  deg$gene <- rownames(deg)
  fc_col <- if ("avg_log2FC" %in% colnames(deg)) "avg_log2FC" else "avg_logFC"

  deg$status <- "Not sig"
  deg$status[deg$p_val_adj < padj_cutoff & deg[[fc_col]] > 0 & abs(deg[[fc_col]]) < logfc_threshold] <- "UP_p"
  deg$status[deg$p_val_adj < padj_cutoff & deg[[fc_col]] < 0 & abs(deg[[fc_col]]) < logfc_threshold] <- "DOWN_p"
  deg$status[deg$p_val_adj < padj_cutoff & deg[[fc_col]] >= logfc_threshold] <- "UP_p_logFC"
  deg$status[deg$p_val_adj < padj_cutoff & deg[[fc_col]] <= -logfc_threshold] <- "DOWN_p_logFC"

  n_up <- sum(deg$status == "UP_p_logFC", na.rm = TRUE)
  n_down <- sum(deg$status == "DOWN_p_logFC", na.rm = TRUE)

  full_csv <- file.path(output_dir, paste0("deg_results_full_", comp_stub, ".csv"))
  write.csv(deg, full_csv, row.names = FALSE)
  simple_full_csv <- file.path(output_dir, paste0("de_", comp_stub, ".csv"))
  write.csv(deg, simple_full_csv, row.names = FALSE)
  sig_csv <- file.path(output_dir, paste0("deg_results_significant_", comp_stub, ".csv"))
  deg_sig <- deg %>% filter(p_val_adj < padj_cutoff & abs(.data[[fc_col]]) >= logfc_threshold)
  write.csv(deg_sig, sig_csv, row.names = FALSE)
  stats_csv <- file.path(output_dir, paste0("deg_summary_statistics_", comp_stub, ".csv"))
  write.csv(data.frame(
    comparison_name = comp_name,
    comparison_mode = comparison_mode,
    object_source_label = object_source_label,
    test_method = test_use,
    min_pct = min_pct,
    logfc_threshold = logfc_threshold,
    padj_cutoff = padj_cutoff,
    cells_set1 = length(cells_1),
    cells_set2 = length(cells_2),
    genes_tested = nrow(deg),
    up_significant = n_up,
    down_significant = n_down,
    stringsAsFactors = FALSE
  ), stats_csv, row.names = FALSE)

  deg$neg_log10_padj <- -log10(deg$p_val_adj + 1e-300)
  deg$status <- factor(deg$status, levels = c("UP_p_logFC", "UP_p", "DOWN_p_logFC", "DOWN_p", "Not sig"))
  label_genes <- deg %>%
    filter(p_val_adj < padj_cutoff) %>%
    arrange(p_val_adj) %>%
    mutate(dir = ifelse(.data[[fc_col]] >= 0, "up", "down")) %>%
    group_by(dir) %>%
    slice_head(n = 15) %>%
    ungroup()
  label_genes$neg_log10_padj <- -log10(label_genes$p_val_adj + 1e-300)

  up_col <- sc_colors[1]
  down_col <- if (length(sc_colors) >= 2) sc_colors[2] else "#4E79A7"
  neutral_col <- if (length(sc_colors) >= 3) sc_colors[3] else "#9AA5B1"
  status_cols <- c(
    "UP_p_logFC" = up_col,
    "UP_p" = grDevices::adjustcolor(up_col, alpha.f = 0.65),
    "DOWN_p_logFC" = down_col,
    "DOWN_p" = grDevices::adjustcolor(down_col, alpha.f = 0.65),
    "Not sig" = grDevices::adjustcolor(neutral_col, alpha.f = 0.35)
  )

  x_thr <- -log10(padj_cutoff)
  x_max <- max(deg$neg_log10_padj[is.finite(deg$neg_log10_padj)], na.rm = TRUE)
  y_max <- max(deg[[fc_col]], na.rm = TRUE)
  y_min <- min(deg[[fc_col]], na.rm = TRUE)
  p_v <- ggplot(deg, aes(x = neg_log10_padj, y = .data[[fc_col]], colour = status)) +
    annotate("rect", xmin = -Inf, xmax = Inf,
             ymin = -logfc_threshold, ymax = logfc_threshold,
             fill = grDevices::adjustcolor(neutral_col, alpha.f = 1), alpha = 0.35) +
    geom_point(data = deg %>% filter(status == "Not sig"), size = 0.9, alpha = 0.35) +
    geom_point(data = deg %>% filter(status %in% c("UP_p", "DOWN_p")), size = 1.2, alpha = 0.65) +
    geom_point(data = deg %>% filter(status %in% c("UP_p_logFC", "DOWN_p_logFC")), size = 1.6, alpha = 0.9) +
    scale_colour_manual(values = status_cols, name = NULL) +
    geom_vline(xintercept = x_thr, linetype = "dashed", colour = "grey40") +
    geom_hline(yintercept = c(-logfc_threshold, logfc_threshold), linetype = "dashed", colour = "grey40")
  if (has_ggrepel && nrow(label_genes) > 0) {
    p_v <- p_v + ggrepel::geom_text_repel(data = label_genes, aes(label = gene), size = 3, max.overlaps = 50, show.legend = FALSE)
  }
  p_v <- p_v +
    annotate("text", x = x_max, y = y_max, hjust = 1, vjust = 1, size = 4, colour = up_col, label = paste0("UP: ", n_up)) +
    annotate("text", x = x_max, y = y_min, hjust = 1, vjust = 0, size = 4, colour = down_col, label = paste0("DOWN: ", n_down)) +
    theme_classic() +
    labs(x = "-log10(adj.p)", y = fc_col, title = comp_name) +
    sc_theme
  volcano_fig <- save_plot(p_v, paste0("deg_volcano_plot_", comp_stub), output_dir, width = 10, height = 8)

  list(
    comparison_name = comp_name,
    comparison_mode = comparison_mode,
    file_stub = comp_stub,
    group_1 = comp$group_1,
    ct_1 = comp$ct_1,
    group_2 = comp$group_2,
    ct_2 = comp$ct_2,
    n_up = n_up,
    n_down = n_down,
    n_genes_tested = nrow(deg),
    n_cells_set1 = length(cells_1),
    n_cells_set2 = length(cells_2),
    figures = list(basename(volcano_fig)),
    tables = list(basename(full_csv), basename(simple_full_csv), basename(sig_csv), basename(stats_csv))
  )
}

tryCatch({
  if (!file.exists(input_rds)) stop(paste("Input object does not exist:", input_rds))

  report_progress(5, "Loading object...")
  obj <- readRDS(input_rds)
  tryCatch({
    if (inherits(obj[["RNA"]], "Assay5")) obj[["RNA"]] <- JoinLayers(obj[["RNA"]])
  }, error = function(e) {})
  cat(sprintf("Object: %d cells, %d genes\n", ncol(obj), nrow(obj)))

  comparisons <- materialize_comparisons()
  if (length(comparisons) == 0) stop("No valid comparisons were provided.")
  cat(sprintf("Comparison mode: %s\n", comparison_mode))
  cat(sprintf("Number of comparisons: %d\n", length(comparisons)))

  for (idx in seq_along(comparisons)) {
    res <- run_single_comparison(obj, comparisons[[idx]], idx)
    comparison_summaries[[length(comparison_summaries) + 1]] <- res
    all_figures <- unique(c(all_figures, unlist(res$figures)))
    all_tables <- unique(c(all_tables, unlist(res$tables)))
  }

  report_progress(95, "Writing summary...")
  first_res <- comparison_summaries[[1]]
  total_up <- sum(vapply(comparison_summaries, function(x) as.numeric(x$n_up %||% 0), numeric(1)))
  total_down <- sum(vapply(comparison_summaries, function(x) as.numeric(x$n_down %||% 0), numeric(1)))
  total_genes <- sum(vapply(comparison_summaries, function(x) as.numeric(x$n_genes_tested %||% 0), numeric(1)))

  write_summary(list(
    status = "success",
    result_id = result_id,
    result_name = result_name,
    comparison_name = first_res$comparison_name,
    comparison_mode = comparison_mode,
    object_source_label = object_source_label,
    n_total_deg = total_up + total_down,
    n_up = first_res$n_up,
    n_down = first_res$n_down,
    n_genes_tested = first_res$n_genes_tested,
    n_cells_set1 = first_res$n_cells_set1,
    n_cells_set2 = first_res$n_cells_set2,
    n_comparisons = length(comparison_summaries),
    comparisons = comparison_summaries,
    figures = as.list(all_figures),
    tables = as.list(all_tables)
  ), output_dir)

  report_progress(100, "DEG finished")
  cat(sprintf("\n=== DEG finished: %d comparison(s), total UP=%d, total DOWN=%d ===\n", length(comparison_summaries), total_up, total_down))
}, error = function(e) {
  err_msg <- conditionMessage(e)
  cat(sprintf("\nError: %s\n", err_msg))
  suggestion <- "Please check the selected groups / cell types and verify that each comparison has enough cells."
  if (grepl("MAST", err_msg, ignore.case = TRUE)) {
    suggestion <- "MAST is not installed. Install with: BiocManager::install('MAST')"
  }
  write_error_summary("DEG", err_msg, suggestion, output_dir)
  quit(status = 1)
})
