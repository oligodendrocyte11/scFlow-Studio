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
if (length(args) < 1) stop("Usage: Rscript 08_subcluster.R <params.json>")

params <- read_params(args[1])
output_dir <- params$output_dir %||% params$cache_dir %||% "."
ensure_dir(output_dir)
seed <- as.integer(params$seed %||% 1234)
set.seed(seed)

if (!is.null(params$color_scheme) && exists("set_color_scheme")) {
  try(set_color_scheme(as.character(params$color_scheme)), silent = TRUE)
}

action <- as.character(params$action %||% "subset_and_cluster")
input_rds <- params$input_rds

old_ver <- getOption("Seurat.object.assay.version")
options(Seurat.object.assay.version = "v3")
on.exit({ options(Seurat.object.assay.version = old_ver) }, add = TRUE)

all_figures <- c()
all_tables <- c()

attach_subcluster_runtime_meta <- function(obj, params, action_name = "", annotation_info = NULL) {
  result_id <- as.character(params$result_id %||% "")
  result_name <- as.character(params$result_name %||% result_id)
  target_celltypes <- as.character(unlist(params$target_celltype %||% character(0)))
  if (is.null(obj@misc$subcluster_runtime)) {
    obj@misc$subcluster_runtime <- list()
  }
  obj@misc$subcluster_runtime$result_id <- result_id
  obj@misc$subcluster_runtime$result_name <- result_name
  obj@misc$subcluster_runtime$target_celltypes <- target_celltypes
  obj@misc$subcluster_runtime$params <- params
  obj@misc$subcluster_runtime$last_action <- action_name
  if (!is.null(annotation_info)) {
    obj@misc$subcluster_runtime$annotation <- annotation_info
  }
  obj
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

get_rna_data <- function(obj) {
  tryCatch(
    GetAssayData(obj, assay = "RNA", layer = "data"),
    error = function(e) GetAssayData(obj, assay = "RNA", slot = "data")
  )
}

get_rna_counts <- function(obj) {
  tryCatch(
    GetAssayData(obj, assay = "RNA", layer = "counts"),
    error = function(e) GetAssayData(obj, assay = "RNA", slot = "counts")
  )
}

get_fc_col <- function(marker_df) {
  if ("avg_log2FC" %in% colnames(marker_df)) {
    return("avg_log2FC")
  }
  if ("avg_logFC" %in% colnames(marker_df)) {
    return("avg_logFC")
  }
  stop("marker result is missing avg_log2FC / avg_logFC column.")
}

sanitize_label_vec <- function(x, fallback = "Unknown") {
  x <- as.character(x)
  x[is.na(x)] <- ""
  x <- trimws(x)
  x[x == ""] <- fallback
  x
}

build_composition_df <- function(group_vec, label_vec, group_order = NULL, label_col = "subtype") {
  meta_df <- data.frame(
    group = as.character(group_vec),
    label = sanitize_label_vec(label_vec, fallback = "Unknown"),
    stringsAsFactors = FALSE
  )
  meta_df$group[is.na(meta_df$group)] <- ""
  meta_df$group <- trimws(meta_df$group)
  meta_df <- meta_df[nzchar(meta_df$group), , drop = FALSE]
  if (nrow(meta_df) == 0) {
    stop("No valid group information was found for subcluster composition plot.")
  }

  observed_groups <- unique(meta_df$group)
  if (!is.null(group_order) && length(group_order) > 0) {
    group_order <- as.character(unlist(group_order))
    group_levels <- c(intersect(group_order, observed_groups), setdiff(observed_groups, group_order))
  } else {
    group_levels <- observed_groups
  }
  group_levels <- unique(group_levels)
  label_levels <- sort(unique(meta_df$label))

  base_df <- expand.grid(
    group = group_levels,
    label = label_levels,
    stringsAsFactors = FALSE
  )
  count_df <- meta_df %>%
    count(group, label, name = "count")

  prop_df <- dplyr::left_join(base_df, count_df, by = c("group", "label"))
  prop_df$count[is.na(prop_df$count)] <- 0
  prop_df <- prop_df %>%
    group_by(group) %>%
    mutate(
      group_total = sum(count),
      proportion = ifelse(group_total > 0, count / group_total, 0),
      percent = proportion * 100
    ) %>%
    ungroup()

  check_df <- prop_df %>%
    group_by(group) %>%
    summarise(percent_sum = sum(percent), .groups = "drop")
  bad_df <- check_df %>%
    filter(group %in% observed_groups & abs(percent_sum - 100) > 0.001)
  if (nrow(bad_df) > 0) {
    stop(
      paste0(
        "Subcluster composition percent validation failed: ",
        paste(sprintf("%s=%.6f", bad_df$group, bad_df$percent_sum), collapse = "; ")
      )
    )
  }

  names(prop_df)[names(prop_df) == "label"] <- label_col
  prop_df$group <- factor(prop_df$group, levels = group_levels)
  prop_df[[label_col]] <- factor(prop_df[[label_col]], levels = label_levels)
  prop_df
}

save_plot_variant <- function(plot_obj, name, output_dir, width, height, dpi = 300, limitsize = TRUE) {
  fig <- save_plot(
    plot_obj,
    name,
    output_dir,
    width = width,
    height = height,
    dpi = dpi,
    limitsize = limitsize
  )
  basename(fig)
}

clamp_value <- function(x, lower, upper) {
  max(lower, min(upper, x))
}


order_cluster_ids <- function(cluster_ids) {
  cluster_ids <- as.character(cluster_ids)
  numeric_ids <- suppressWarnings(as.numeric(cluster_ids))
  if (all(!is.na(numeric_ids))) {
    return(cluster_ids[order(numeric_ids)])
  }
  sort(cluster_ids)
}

build_marker_bubble_plot_variant <- function(
  obj,
  markers_csv,
  label_col,
  plot_basename,
  plot_title,
  output_dir,
  top_n = 4,
  width_cap = Inf,
  height_cap = Inf,
  limitsize = TRUE
) {
  if (!file.exists(markers_csv) || !label_col %in% colnames(obj@meta.data)) {
    return(NULL)
  }

  marker_df <- read.csv(markers_csv, stringsAsFactors = FALSE, check.names = FALSE)
  if (nrow(marker_df) == 0 || !all(c("cluster", "gene") %in% colnames(marker_df))) {
    return(NULL)
  }

  fc_col <- get_fc_col(marker_df)
  meta_df <- data.frame(
    cluster = as.character(obj$seurat_clusters),
    label = as.character(obj@meta.data[[label_col]]),
    stringsAsFactors = FALSE
  )
  meta_df <- meta_df[!is.na(meta_df$label) & nzchar(meta_df$label), , drop = FALSE]
  if (nrow(meta_df) == 0) {
    return(NULL)
  }

  cluster_label <- unique(meta_df[, c("cluster", "label")])
  cluster_order <- order_cluster_ids(cluster_label$cluster)
  cluster_label$order_key <- match(cluster_label$cluster, cluster_order)
  cluster_label <- cluster_label[order(cluster_label$order_key, cluster_label$label), c("cluster", "label")]
  label_order <- unique(cluster_label$label)
  if (length(label_order) == 0) {
    return(NULL)
  }

  label_palette <- grDevices::colorRampPalette(sc_colors)(max(length(label_order), 3))[seq_along(label_order)]
  names(label_palette) <- label_order

  marker_df$cluster <- as.character(marker_df$cluster)
  marker_df$gene <- as.character(marker_df$gene)
  marker_df <- marker_df[marker_df$gene %in% rownames(obj) & nzchar(marker_df$gene), , drop = FALSE]
  if (nrow(marker_df) == 0) {
    return(NULL)
  }

  marker_df <- merge(marker_df, cluster_label, by = "cluster")
  if (nrow(marker_df) == 0) {
    return(NULL)
  }

  marker_df <- marker_df %>%
    group_by(label, gene) %>%
    summarise(fc_value = max(.data[[fc_col]], na.rm = TRUE), .groups = "drop")

  marker_df$label <- factor(marker_df$label, levels = label_order)
  marker_df <- marker_df %>% arrange(label, desc(fc_value), gene)

  gene_records <- list()
  used_genes <- character(0)
  gene_to_label <- character(0)
  for (label_name in label_order) {
    sub_df <- marker_df %>% filter(label == label_name) %>% arrange(desc(fc_value), gene)
    if (nrow(sub_df) == 0) {
      next
    }
    picked <- character(0)
    for (gene_name in sub_df$gene) {
      if (!gene_name %in% used_genes) {
        picked <- c(picked, gene_name)
        used_genes <- c(used_genes, gene_name)
      }
      if (length(picked) >= top_n) {
        break
      }
    }
    if (length(picked) > 0) {
      gene_records[[label_name]] <- picked
      gene_to_label[picked] <- label_name
    }
  }

  gene_order <- unname(unlist(gene_records, use.names = FALSE))
  if (length(gene_order) == 0) {
    return(NULL)
  }

  # Keep the current hand-tuned layout as the baseline, then lightly
  # compensate for different numbers of labels/genes so main and sub plots
  # stay visually closer to each other.
  n_labels <- length(label_order)
  n_genes <- length(gene_order)
  label_scale <- max(0.65, min(1.05, n_labels / 8))
  gene_scale <- max(0.60, min(1.20, n_genes / 30))
  label_panel_width <- 1.78 * (0.94 + 0.06 * label_scale)
  strip_panel_width <- 0.30 * (0.78 + 0.22 * label_scale)
  main_panel_width <- 13.52 * (0.98 + 0.02 * gene_scale)
  strip_tile_width <- 0.20 * (0.78 + 0.22 * label_scale)
  plot_height <- max(4.8, n_labels * 0.42 + 1.8)

  obj$.plot_label_tmp <- factor(as.character(obj@meta.data[[label_col]]), levels = label_order)
  dot_df <- DotPlot(obj, features = gene_order, group.by = ".plot_label_tmp")$data
  dot_df <- dot_df[dot_df$features.plot %in% gene_order, , drop = FALSE]
  if (nrow(dot_df) == 0) {
    return(NULL)
  }

  x_index <- seq_along(gene_order)
  names(x_index) <- gene_order

  dot_df$features.plot <- as.character(dot_df$features.plot)
  dot_df$gene_index <- unname(x_index[dot_df$features.plot])
  dot_df$id <- factor(as.character(dot_df$id), levels = rev(label_order))

  label_display_df <- data.frame(
    label = factor(rev(label_order), levels = rev(label_order)),
    x = 1,
    stringsAsFactors = FALSE
  )

  gene_label_df <- data.frame(
    gene = gene_order,
    label = factor(unname(gene_to_label[gene_order]), levels = label_order),
    gene_index = seq_along(gene_order),
    y = 1,
    stringsAsFactors = FALSE
  )

  gene_blocks <- data.frame(
    gene = gene_order,
    label = factor(unname(gene_to_label[gene_order]), levels = label_order),
    stringsAsFactors = FALSE
  )
  gene_blocks$index <- seq_len(nrow(gene_blocks))
  block_ranges <- gene_blocks %>%
    group_by(label) %>%
    summarise(start = min(index), end = max(index), .groups = "drop")
  vline_pos <- block_ranges$end[-nrow(block_ranges)] + 0.5

  p_labels <- ggplot(label_display_df, aes(x = x, y = label, label = label, colour = label)) +
    geom_text(hjust = 1, fontface = "bold", size = 3.5, show.legend = FALSE) +
    scale_colour_manual(values = label_palette, guide = "none") +
    scale_y_discrete(drop = FALSE) +
    coord_cartesian(xlim = c(-1, 1.02), clip = "off") +
    theme_void() +
    theme(plot.margin = margin(8, 0, 6, 1))

  p_strip <- ggplot(label_display_df, aes(x = 1, y = label, fill = label)) +
    geom_tile(width = strip_tile_width, height = 0.86, show.legend = FALSE) +
    scale_fill_manual(values = label_palette, guide = "none") +
    scale_y_discrete(drop = FALSE) +
    coord_cartesian(xlim = c(0.95, 1.12), clip = "off") +
    theme_void() +
    theme(plot.margin = margin(8, 0, 8, 0))

  p_main <- ggplot(dot_df, aes(x = gene_index, y = id)) +
    geom_point(aes(size = pct.exp, colour = avg.exp.scaled), alpha = 0.92) +
    scale_size_continuous(name = "pct.exp", range = c(1.5, 8.5)) +
    scale_colour_gradient2(
      name = "avg.exp.scaled",
      low = "#D6E7F5",
      mid = "#F7F7F7",
      high = sc_colors[1],
      midpoint = 0
    ) +
    scale_x_continuous(
      breaks = x_index,
      labels = rep("", length(x_index)),
      expand = c(0.02, 0.02)
    ) +
    geom_vline(xintercept = vline_pos, colour = "#D9D9D9", linewidth = 0.35) +
    labs(title = plot_title, x = NULL, y = NULL) +
    sc_theme +
    theme(
      plot.title = element_text(face = "bold", size = 14, hjust = 0),
      axis.text.x = element_blank(),
      axis.ticks.x = element_blank(),
      axis.text.y = element_blank(),
      axis.ticks.y = element_blank(),
      panel.grid.major.x = element_blank(),
      panel.grid.minor = element_blank(),
      legend.position = "right",
      legend.box.margin = margin(0, 0, 0, 0),
      legend.margin = margin(0, 0, 0, 0),
      legend.key.height = unit(14, "pt"),
      plot.margin = margin(18, 2, -2, 0)
    )

  p_genes <- ggplot(gene_label_df, aes(x = gene_index, y = y, label = gene, colour = label)) +
    geom_text(angle = 45, hjust = 1, vjust = 1, size = 3.1, show.legend = FALSE) +
    scale_colour_manual(values = label_palette, guide = "none") +
    scale_x_continuous(
      limits = c(0.5, length(gene_order) + 0.5),
      expand = c(0, 0)
    ) +
    coord_cartesian(clip = "off") +
    theme_void() +
    theme(plot.margin = margin(5, 2, 35, 0))

  right_block <- p_main / p_genes + plot_layout(heights = c(18, 0))
  combined <- p_labels + p_strip + right_block + plot_layout(widths = c(label_panel_width, strip_panel_width, main_panel_width))
  plot_width <- max(13.8, length(gene_order) * 0.52 + 4.3)
  plot_width <- clamp_value(plot_width, 10, width_cap)
  plot_height <- clamp_value(plot_height, 4.8, height_cap)
  fig <- save_plot_variant(
    combined,
    plot_basename,
    output_dir,
    width = plot_width,
    height = plot_height,
    limitsize = limitsize
  )
  basename(fig)
}

build_marker_bubble_plot_dual <- function(obj, markers_csv, label_col, output_dir) {
  result <- list(compact_fig = NULL, full_fig = NULL, message = "")

  result$compact_fig <- tryCatch(
    build_marker_bubble_plot_variant(
      obj = obj,
      markers_csv = markers_csv,
      label_col = label_col,
      plot_basename = "subcluster_marker_bubble_plot_compact",
      plot_title = "Subcluster Marker Bubble Plot (Compact)",
      output_dir = output_dir,
      top_n = 4,
      width_cap = 18,
      height_cap = 11,
      limitsize = TRUE
    ),
    error = function(e) {
      result$message <<- paste0("Compact subtype marker bubble plot failed: ", conditionMessage(e))
      NULL
    }
  )

  result$full_fig <- tryCatch(
    build_marker_bubble_plot_variant(
      obj = obj,
      markers_csv = markers_csv,
      label_col = label_col,
      plot_basename = "subcluster_marker_bubble_plot_full",
      plot_title = "Subcluster Marker Bubble Plot (Full)",
      output_dir = output_dir,
      top_n = Inf,
      width_cap = Inf,
      height_cap = Inf,
      limitsize = FALSE
    ),
    error = function(e) {
      msg <- paste0("Full subtype marker bubble plot failed but compact output was kept: ", conditionMessage(e))
      if (nzchar(result$message)) {
        result$message <<- paste(result$message, msg, sep = "\n")
      } else {
        result$message <<- msg
      }
      NULL
    }
  )

  result
}

normalize_custom_markers <- function(marker_obj) {
  if (is.null(marker_obj) || !is.list(marker_obj) || length(marker_obj) == 0) {
    return(list())
  }
  out <- list()
  for (nm in names(marker_obj)) {
    genes <- marker_obj[[nm]]
    if (is.null(genes)) {
      next
    }
    if (is.list(genes)) {
      genes <- unlist(genes, use.names = FALSE)
    }
    genes <- unique(trimws(as.character(genes)))
    genes <- genes[nzchar(genes)]
    if (length(genes) > 0) {
      out[[nm]] <- genes
    }
  }
  out
}

prepare_marker_signatures <- function(marker_obj, feature_names, min_markers_per_type = 1L) {
  marker_obj <- normalize_custom_markers(marker_obj)
  if (length(marker_obj) == 0) {
    return(list())
  }
  feature_names <- unique(as.character(feature_names))
  out <- list()
  for (label_name in names(marker_obj)) {
    genes <- unique(marker_obj[[label_name]])
    genes <- genes[genes %in% feature_names]
    if (length(genes) >= min_markers_per_type) {
      out[[label_name]] <- genes
    }
  }
  out
}

build_marker_matrix <- function(marker_obj, feature_names, min_markers_per_type = 1L) {
  marker_obj <- prepare_marker_signatures(marker_obj, feature_names, min_markers_per_type = min_markers_per_type)
  if (length(marker_obj) == 0) {
    return(NULL)
  }
  all_genes <- unique(unlist(marker_obj, use.names = FALSE))
  marker_mat <- matrix(
    0,
    nrow = length(all_genes),
    ncol = length(marker_obj),
    dimnames = list(all_genes, names(marker_obj))
  )
  for (label_name in names(marker_obj)) {
    marker_mat[marker_obj[[label_name]], label_name] <- 1
  }
  marker_mat
}

build_cluster_mapping_from_labels <- function(cluster_ids, labels, unknown_values = c("unknown", "unassigned", "NA", "")) {
  cluster_ids <- as.character(cluster_ids)
  labels <- as.character(labels)
  if (length(cluster_ids) != length(labels)) {
    stop("Prediction labels do not match the number of cells.")
  }
  label_norm <- labels
  label_norm[is.na(label_norm)] <- "Unknown"
  label_norm[trimws(label_norm) == ""] <- "Unknown"
  low_vals <- tolower(trimws(label_norm))
  label_norm[low_vals %in% tolower(unknown_values)] <- "Unknown"

  split_labels <- split(label_norm, cluster_ids)
  mapping <- lapply(split_labels, function(label_vec) {
    keep <- label_vec[!is.na(label_vec) & nzchar(trimws(label_vec))]
    if (length(keep) == 0) {
      return("Unknown")
    }
    names(sort(table(keep), decreasing = TRUE))[1]
  })
  mapping[order(names(mapping))]
}

run_scina_mapping <- function(obj, marker_obj, output_dir) {
  if (!requireNamespace("SCINA", quietly = TRUE)) {
    stop(
      "SCINA package is not available in the local R runtime. ",
      "Please install SCINA in the bundled/local R environment before using this method."
    )
  }
  signatures <- prepare_marker_signatures(marker_obj, rownames(obj), min_markers_per_type = 1L)
  if (length(signatures) < 2) {
    stop("SCINA requires at least two subtypes with markers found in the current object.")
  }

  expr_data <- get_rna_data(obj)
  sig_genes <- intersect(unique(unlist(signatures, use.names = FALSE)), rownames(expr_data))
  expr_mat <- as.matrix(expr_data[sig_genes, , drop = FALSE])
  if (nrow(expr_mat) < 2) {
    stop("Too few marker genes were found in the current object for SCINA.")
  }

  scina_res <- SCINA::SCINA(
    exp = expr_mat,
    signatures = signatures,
    max_iter = 100,
    convergence_n = 10,
    convergence_rate = 0.99,
    sensitivity_cutoff = 0.9,
    rm_overlap = FALSE,
    allow_unknown = TRUE,
    log_file = tempfile(pattern = "scina_sub_", fileext = ".log")
  )
  cell_labels <- as.character(scina_res$cell_labels)
  if (length(cell_labels) != ncol(obj)) {
    stop("SCINA returned an unexpected number of predicted labels.")
  }
  names(cell_labels) <- colnames(obj)
  mapping <- build_cluster_mapping_from_labels(as.character(obj$seurat_clusters), cell_labels)

  pred_df <- data.frame(
    cell = colnames(obj),
    cluster = as.character(obj$seurat_clusters),
    predicted_label = sanitize_label_vec(cell_labels, fallback = "Unknown"),
    stringsAsFactors = FALSE
  )
  write.csv(pred_df, file.path(output_dir, "sub_scina_cell_predictions.csv"), row.names = FALSE)
  write.csv(
    data.frame(cluster = names(mapping), label = unlist(mapping), stringsAsFactors = FALSE),
    file.path(output_dir, "sub_scina_mapping.csv"),
    row.names = FALSE
  )
  list(mapping = mapping, cell_labels = cell_labels)
}

run_cellassign_mapping <- function(obj, marker_obj, output_dir) {
  cellassign_env <- NULL
  configure_cellassign_python <- function() {
    current_py <- Sys.getenv("RETICULATE_PYTHON", unset = "")
    Sys.setenv(
      RETICULATE_MINICONDA_ENABLED = "FALSE",
      CONDA_NO_PLUGINS = "true",
      TF_CPP_MIN_LOG_LEVEL = "2",
      CUDA_VISIBLE_DEVICES = "-1"
    )
    resource_root <- normalizePath(R.home("home"), winslash = "/", mustWork = FALSE)
    candidate_paths <- c(
      file.path(resource_root, "..", "..", "..", "..", "..", "..", "Resources", "vendor", "cellassign_runtime", "bin", "python"),
      file.path(resource_root, "..", "..", "..", "..", "cellassign_runtime", "bin", "python"),
      file.path(resource_root, "..", "..", "..", "..", "..", "..", "Resources", "vendor", "cellassign_py", "bin", "python"),
      file.path(resource_root, "..", "..", "..", "..", "cellassign_py", "bin", "python"),
      file.path(resource_root, "..", "..", "..", "..", "..", "..", "Resources", "vendor", "cellassign_py310", "bin", "python"),
      file.path(resource_root, "..", "..", "..", "..", "cellassign_py310", "bin", "python"),
      file.path(getwd(), "vendor", "cellassign_runtime", "bin", "python"),
      file.path(getwd(), "vendor", "cellassign_py", "bin", "python"),
      file.path(getwd(), "vendor", "cellassign_py310", "bin", "python"),
      file.path(R.home("home"), "..", "cellassign_py310", "python.exe"),
      file.path(R.home("home"), "..", "..", "cellassign_py310", "python.exe"),
      file.path(getwd(), "vendor", "cellassign_py310", "python.exe"),
      file.path(R.home("home"), "..", "cellassign_py", "Scripts", "python.exe"),
      file.path(R.home("home"), "..", "..", "cellassign_py", "Scripts", "python.exe"),
      file.path(getwd(), "vendor", "cellassign_py", "Scripts", "python.exe"),
      Sys.which("python")
    )
    candidate_paths <- unique(normalizePath(candidate_paths[nzchar(candidate_paths)], winslash = "/", mustWork = FALSE))
    for (cand in candidate_paths) {
      if (nzchar(cand) && file.exists(cand)) {
        Sys.setenv(RETICULATE_PYTHON = cand)
        return(cand)
      }
    }
    if (nzchar(current_py)) {
      return(current_py)
    }
    ""
  }

  get_cellassign_source_dir <- function() {
    resource_root <- normalizePath(R.home("home"), winslash = "/", mustWork = FALSE)
    candidate_dirs <- c(
      file.path(resource_root, "..", "..", "..", "..", "..", "..", "Resources", "vendor", "cellassign_Rsrc"),
      file.path(resource_root, "..", "..", "..", "..", "cellassign_Rsrc"),
      file.path(getwd(), "vendor", "cellassign_Rsrc"),
      file.path(getwd(), "cellassign_Rsrc")
    )
    candidate_dirs <- unique(normalizePath(candidate_dirs, winslash = "/", mustWork = FALSE))
    for (cand in candidate_dirs) {
      if (dir.exists(cand) && file.exists(file.path(cand, "R", "cellassign.R"))) {
        return(cand)
      }
    }
    ""
  }

  load_cellassign_source_runtime <- function() {
    src_dir <- get_cellassign_source_dir()
    if (!nzchar(src_dir)) {
      stop(
        "CellAssign source runtime is not available in this app bundle. ",
        "Please rebuild the app with vendor/cellassign_Rsrc included."
      )
    }
    env <- new.env(parent = globalenv())
    source(file.path(src_dir, "R", "utils.R"), local = env)
    source(file.path(src_dir, "R", "cellassign.R"), local = env)
    source(file.path(src_dir, "R", "inference-tensorflow.R"), local = env)
    env$inference_tensorflow <- inference_tensorflow_compat
    env
  }

  shape_compat <- function(...) {
    dims <- list(...)
    vals <- lapply(dims, function(d) {
      if (is.null(d) || (length(d) == 1 && isTRUE(is.na(d)))) {
        return(NULL)
      }
      as.integer(d)
    })
    if (any(vapply(vals, is.null, logical(1)))) {
      return(lapply(vals, function(x) if (is.null(x)) NULL else as.integer(x)))
    }
    as.integer(unlist(vals, use.names = FALSE))
  }

  shape_tensor_compat <- function(...) {
    as.array(as.integer(unlist(list(...), use.names = FALSE)))
  }

  inference_tensorflow_compat <- function(Y, rho, s, X, G, C, N, P, B,
                                          shrinkage, verbose, n_batches,
                                          rel_tol_adam, rel_tol_em,
                                          max_iter_adam, max_iter_em,
                                          learning_rate, min_delta,
                                          dirichlet_concentration,
                                          random_seed, threads) {
    tf <- tensorflow::tf$compat$v1
    tf$disable_v2_behavior()
    tfp <- reticulate::import("tensorflow_probability")
    tfd <- tfp$distributions
    tf$reset_default_graph()

    entry_stop_gradients <- function(target, mask) {
      mask_h <- tf$logical_not(mask)
      mask <- tf$cast(mask, dtype = target$dtype)
      mask_h <- tf$cast(mask_h, dtype = target$dtype)
      tf$add(tf$stop_gradient(tf$multiply(mask_h, target)), tf$multiply(mask, target))
    }
    get_mle_cell_type <- function(gamma) {
      which_max <- apply(gamma, 1, which.max)
      colnames(gamma)[which_max]
    }

    Y_ <- tf$placeholder(tf$float64, shape = shape_compat(NULL, G), name = "Y_")
    X_ <- tf$placeholder(tf$float64, shape = shape_compat(NULL, P), name = "X_")
    s_ <- tf$placeholder(tf$float64, shape = shape_compat(NULL), name = "s_")
    rho_ <- tf$placeholder(tf$float64, shape = shape_compat(G, C), name = "rho_")
    sample_idx <- tf$placeholder(tf$int32, shape = shape_compat(NULL), name = "sample_idx")

    B <- as.integer(B)
    basis_means_fixed <- seq(from = min(Y), to = max(Y), length.out = B)
    basis_means <- tf$constant(basis_means_fixed, dtype = tf$float64)
    b_init <- 2 * (basis_means_fixed[2] - basis_means_fixed[1])^2
    LOWER_BOUND <- 1e-10

    if (shrinkage) {
      delta_log_mean <- tf$Variable(0, dtype = tf$float64)
      delta_log_variance <- tf$Variable(1, dtype = tf$float64)
    }

    delta_log <- tf$Variable(
      tf$random_uniform(shape_tensor_compat(G, C), minval = -2, maxval = 2,
                        seed = random_seed, dtype = tf$float64),
      dtype = tf$float64,
      constraint = function(x) {
        tf$clip_by_value(
          x,
          tf$constant(log(min_delta), dtype = tf$float64),
          tf$constant(Inf, dtype = tf$float64)
        )
      }
    )

    beta_0_init <- scale(colMeans(Y))
    beta_init <- cbind(beta_0_init, matrix(0, nrow = G, ncol = P - 1))
    beta <- tf$Variable(tf$constant(beta_init, dtype = tf$float64), dtype = tf$float64)
    theta_logit <- tf$Variable(
      tf$random_normal(shape_tensor_compat(C), mean = 0, stddev = 1,
                       seed = random_seed, dtype = tf$float64),
      dtype = tf$float64
    )

    a <- tf$exp(tf$Variable(tf$zeros(shape = B, dtype = tf$float64)))
    b <- tf$exp(tf$constant(rep(-log(b_init), B), dtype = tf$float64))
    delta_log <- entry_stop_gradients(delta_log, tf$cast(rho_, tf$bool))
    delta <- tf$exp(delta_log)
    theta_log <- tf$nn$log_softmax(theta_logit)
    base_mean <- tf$transpose(tf$einsum("np,gp->gn", X_, beta) + tf$log(s_))

    base_mean_list <- vector("list", C)
    for (c in seq_len(C)) {
      base_mean_list[[c]] <- base_mean
    }

    mu_ngc <- tf$add(
      tf$stack(base_mean_list, 2L),
      tf$multiply(delta, rho_),
      name = "adding_base_mean_to_delta_rho"
    )
    mu_cng <- tf$transpose(mu_ngc, shape_compat(2L, 0L, 1L))
    mu_cngb <- tf$tile(tf$expand_dims(mu_cng, axis = 3L), c(1L, 1L, 1L, B))
    phi_cng <- tf$reduce_sum(a * tf$exp(-b * tf$square(mu_cngb - basis_means)), 3L) + LOWER_BOUND
    phi <- tf$transpose(phi_cng, shape_compat(1L, 2L, 0L))
    mu_ngc <- tf$transpose(mu_cng, shape_compat(1L, 2L, 0L))
    mu_ngc <- tf$exp(mu_ngc)
    p <- mu_ngc / (mu_ngc + phi)
    nb_pdf <- tfd$NegativeBinomial(probs = p, total_count = phi)

    Y_tensor_list <- vector("list", C)
    for (c in seq_len(C)) {
      Y_tensor_list[[c]] <- Y_
    }
    Y__ <- tf$stack(Y_tensor_list, axis = 2L)

    y_log_prob_raw <- nb_pdf$log_prob(Y__)
    y_log_prob <- tf$transpose(y_log_prob_raw, shape_compat(0L, 2L, 1L))
    y_log_prob_sum <- tf$reduce_sum(y_log_prob, 2L) + theta_log
    p_y_on_c_unorm <- tf$transpose(y_log_prob_sum, shape_compat(1L, 0L))
    gamma_fixed <- tf$placeholder(dtype = tf$float64, shape = shape_compat(NULL, C))
    Q <- -tf$einsum("nc,cn->", gamma_fixed, p_y_on_c_unorm)
    p_y_on_c_norm <- tf$reshape(tf$reduce_logsumexp(p_y_on_c_unorm, 0L), shape_compat(1L, -1L))
    gamma <- tf$transpose(tf$exp(p_y_on_c_unorm - p_y_on_c_norm))

    if (shrinkage) {
      delta_log_prior <- tfd$Normal(loc = delta_log_mean * rho_, scale = delta_log_variance)
      delta_log_prob <- -tf$reduce_sum(delta_log_prior$log_prob(delta_log))
    }

    THETA_LOWER_BOUND <- 1e-20
    theta_log_prior <- tfd$Dirichlet(
      concentration = tf$constant(dirichlet_concentration, dtype = tf$float64)
    )
    theta_log_prob <- -theta_log_prior$log_prob(tf$exp(theta_log) + THETA_LOWER_BOUND)
    Q <- Q + theta_log_prob
    if (shrinkage) {
      Q <- Q + delta_log_prob
    }

    optimizer <- tf$train$AdamOptimizer(learning_rate = learning_rate)
    train <- optimizer$minimize(Q)
    L_y <- tf$reduce_sum(tf$reduce_logsumexp(p_y_on_c_unorm, 0L))
    L_y <- L_y - theta_log_prob
    if (shrinkage) {
      L_y <- L_y - delta_log_prob
    }

    splits <- split(sample(seq_len(N), size = N, replace = FALSE), seq_len(n_batches))
    session_conf <- tf$ConfigProto(
      intra_op_parallelism_threads = threads,
      inter_op_parallelism_threads = threads
    )
    sess <- tf$Session(config = session_conf)
    init <- tf$global_variables_initializer()
    sess$run(init)

    fd_full <- reticulate::dict(Y_ = Y, X_ = X, s_ = s, rho_ = rho)
    log_liks <- ll_old <- sess$run(L_y, feed_dict = fd_full)

    for (i in seq_len(max_iter_em)) {
      ll <- 0
      for (b in seq_len(n_batches)) {
        fd <- reticulate::dict(
          Y_ = Y[splits[[b]], , drop = FALSE],
          X_ = X[splits[[b]], , drop = FALSE],
          s_ = s[splits[[b]]],
          rho_ = rho
        )
        g <- sess$run(gamma, feed_dict = fd)
        gfd <- reticulate::dict(
          Y_ = Y[splits[[b]], , drop = FALSE],
          X_ = X[splits[[b]], , drop = FALSE],
          s_ = s[splits[[b]]],
          rho_ = rho,
          gamma_fixed = g
        )
        Q_old <- sess$run(Q, feed_dict = gfd)
        Q_diff <- rel_tol_adam + 1
        mi <- 0
        while (mi < max_iter_adam && Q_diff > rel_tol_adam) {
          mi <- mi + 1
          sess$run(train, feed_dict = gfd)
          if (mi %% 20 == 0) {
            if (verbose) {
              message(paste(mi, sess$run(Q, feed_dict = gfd)))
            }
            Q_new <- sess$run(Q, feed_dict = gfd)
            Q_diff <- -(Q_new - Q_old) / abs(Q_old)
            Q_old <- Q_new
          }
        }
        l_new <- sess$run(L_y, feed_dict = gfd)
        ll <- ll + l_new
      }

      ll_diff <- (ll - ll_old) / abs(ll_old)
      if (verbose) {
        message(sprintf("%i\tL old: %f; L new: %f; Difference (%%): %f",
                        mi, ll_old, ll, ll_diff))
      }
      ll_old <- ll
      log_liks <- c(log_liks, ll)
      if (ll_diff < rel_tol_em) {
        break
      }
    }

    variable_list <- list(delta, beta, phi, gamma, mu_ngc, a, tf$exp(theta_log))
    variable_names <- c("delta", "beta", "phi", "gamma", "mu", "a", "theta")
    if (shrinkage) {
      variable_list <- c(variable_list, list(delta_log_mean, delta_log_variance))
      variable_names <- c(variable_names, "ld_mean", "ld_var")
    }
    mle_params <- sess$run(variable_list, feed_dict = fd_full)
    names(mle_params) <- variable_names
    sess$close()

    mle_params$delta[rho == 0] <- 0
    if (is.null(colnames(rho))) {
      colnames(rho) <- paste0("cell_type_", seq_len(ncol(rho)))
    }
    colnames(mle_params$gamma) <- colnames(rho)
    rownames(mle_params$delta) <- rownames(rho)
    colnames(mle_params$delta) <- colnames(rho)
    rownames(mle_params$beta) <- rownames(rho)
    names(mle_params$theta) <- colnames(rho)

    cell_type <- get_mle_cell_type(mle_params$gamma)
    list(cell_type = cell_type, mle_params = mle_params, lls = log_liks)
  }

  configured_python <- configure_cellassign_python()
  if (nzchar(configured_python) && requireNamespace("reticulate", quietly = TRUE)) {
    try(reticulate::use_python(configured_python, required = TRUE), silent = TRUE)
  }
  use_packaged_cellassign <- requireNamespace("cellassign", quietly = TRUE)
  if (!use_packaged_cellassign) {
    cellassign_env <- load_cellassign_source_runtime()
  }
  marker_mat <- build_marker_matrix(marker_obj, rownames(obj), min_markers_per_type = 1L)
  if (is.null(marker_mat) || ncol(marker_mat) < 2) {
    stop("CellAssign requires at least two subtypes with markers found in the current object.")
  }

  if (use_packaged_cellassign) {
    assignInNamespace("inference_tensorflow", inference_tensorflow_compat, ns = "cellassign")
  } else {
    cellassign_env$inference_tensorflow <- inference_tensorflow_compat
  }

  full_counts <- get_rna_counts(obj)
  common_genes <- intersect(rownames(marker_mat), rownames(full_counts))
  if (length(common_genes) < 2) {
    stop("Too few marker genes were found in the raw counts matrix for CellAssign.")
  }
  marker_mat <- marker_mat[common_genes, , drop = FALSE]
  counts_mat <- full_counts[common_genes, , drop = FALSE]
  size_factors <- Matrix::colSums(full_counts)
  cellassign_expr <- t(as.matrix(counts_mat))

  fit <- if (use_packaged_cellassign) {
    cellassign::cellassign(
      exprs_obj = cellassign_expr,
      marker_gene_info = marker_mat,
      s = size_factors,
      learning_rate = 1e-2,
      shrinkage = TRUE,
      verbose = FALSE
    )
  } else {
    cellassign_env$cellassign(
      exprs_obj = cellassign_expr,
      marker_gene_info = marker_mat,
      s = size_factors,
      learning_rate = 1e-2,
      shrinkage = TRUE,
      verbose = FALSE
    )
  }
  cell_labels <- NULL
  if (!is.null(fit$cell_type)) {
    cell_labels <- as.character(fit$cell_type)
  } else if ("cell_type" %in% colnames(as.data.frame(SummarizedExperiment::colData(fit)))) {
    cell_labels <- as.character(SummarizedExperiment::colData(fit)$cell_type)
  } else if (use_packaged_cellassign && "celltypes" %in% getNamespaceExports("cellassign")) {
    cell_labels <- as.character(cellassign::celltypes(fit))
  } else if (!use_packaged_cellassign && exists("celltypes", envir = cellassign_env, inherits = FALSE)) {
    cell_labels <- as.character(cellassign_env$celltypes(fit))
  }
  if (length(cell_labels) != ncol(obj)) {
    stop("CellAssign returned an unexpected number of predicted labels.")
  }
  names(cell_labels) <- colnames(obj)
  mapping <- build_cluster_mapping_from_labels(as.character(obj$seurat_clusters), cell_labels)

  pred_df <- data.frame(
    cell = colnames(obj),
    cluster = as.character(obj$seurat_clusters),
    predicted_label = sanitize_label_vec(cell_labels, fallback = "Unknown"),
    stringsAsFactors = FALSE
  )
  write.csv(pred_df, file.path(output_dir, "sub_cellassign_cell_predictions.csv"), row.names = FALSE)
  write.csv(
    data.frame(cluster = names(mapping), label = unlist(mapping), stringsAsFactors = FALSE),
    file.path(output_dir, "sub_cellassign_mapping.csv"),
    row.names = FALSE
  )
  list(mapping = mapping, cell_labels = cell_labels, python = configured_python)
}

build_manual_marker_dotplot_variant <- function(
  obj,
  marker_dict,
  label_col,
  plot_basename,
  plot_title,
  output_dir,
  max_genes_per_panel = Inf,
  width_cap = Inf,
  height_cap = Inf,
  limitsize = TRUE
) {
  marker_dict <- normalize_custom_markers(marker_dict)
  if (length(marker_dict) == 0 || !label_col %in% colnames(obj@meta.data)) {
    return(list(fig = NULL, message = "Manual subtype marker dotplot was skipped because no manual marker panel is available."))
  }

  gene_order <- character(0)
  gene_to_panel <- character(0)
  for (panel_name in names(marker_dict)) {
    genes <- marker_dict[[panel_name]]
    genes <- genes[genes %in% rownames(obj)]
    if (is.finite(max_genes_per_panel)) {
      genes <- head(genes, max_genes_per_panel)
    }
    for (gene_name in genes) {
      if (!gene_name %in% gene_order) {
        gene_order <- c(gene_order, gene_name)
        gene_to_panel[gene_name] <- panel_name
      }
    }
  }

  if (length(gene_order) < 2) {
    return(list(fig = NULL, message = "Manual subtype marker dotplot was skipped because fewer than two manual markers were found in the current object."))
  }

  obj$.manual_label_tmp <- factor(as.character(obj@meta.data[[label_col]]))
  dot_df <- DotPlot(obj, features = gene_order, group.by = ".manual_label_tmp")$data
  dot_df <- dot_df[dot_df$features.plot %in% gene_order, , drop = FALSE]
  if (nrow(dot_df) == 0) {
    return(list(fig = NULL, message = "Manual subtype marker dotplot was skipped because no expression values were available for the manual marker panel."))
  }

  dot_df$features.plot <- factor(as.character(dot_df$features.plot), levels = gene_order)
  dot_df$marker_panel <- factor(unname(gene_to_panel[as.character(dot_df$features.plot)]), levels = unique(names(marker_dict)))
  dot_df$id <- factor(as.character(dot_df$id), levels = rev(unique(as.character(dot_df$id))))

  p <- ggplot(dot_df, aes(x = features.plot, y = id)) +
    geom_point(aes(size = pct.exp, colour = avg.exp.scaled), alpha = 0.92) +
    facet_grid(. ~ marker_panel, scales = "free_x", space = "free_x") +
    scale_size_continuous(name = "pct.exp", range = c(1.8, 8.8)) +
    scale_colour_gradient2(
      name = "avg.exp.scaled",
      low = "#D6E7F5",
      mid = "#F7F7F7",
      high = sc_colors[1],
      midpoint = 0
    ) +
    labs(title = plot_title, x = NULL, y = NULL) +
    sc_theme +
    theme(
      strip.text.x = element_text(face = "bold", size = 10),
      axis.text.x = element_text(angle = 45, hjust = 1, vjust = 1),
      panel.grid.major.x = element_blank(),
      panel.grid.minor = element_blank(),
      legend.position = "right"
    )

  plot_width <- max(10, length(gene_order) * 0.42 + length(unique(names(marker_dict))) * 0.8 + 2.5)
  plot_height <- max(5.5, length(unique(dot_df$id)) * 0.32 + 2.5)
  plot_width <- clamp_value(plot_width, 9, width_cap)
  plot_height <- clamp_value(plot_height, 5.5, height_cap)
  fig <- save_plot_variant(
    p,
    plot_basename,
    output_dir,
    width = plot_width,
    height = plot_height,
    limitsize = limitsize
  )
  list(fig = basename(fig), message = "")
}

build_manual_marker_dotplot_dual <- function(obj, marker_dict, label_col, output_dir) {
  result <- list(compact_fig = NULL, full_fig = NULL, message = "")

  compact_res <- tryCatch(
    build_manual_marker_dotplot_variant(
      obj = obj,
      marker_dict = marker_dict,
      label_col = label_col,
      plot_basename = "sub_manual_marker_dotplot_compact",
      plot_title = "Manual Subtype Marker DotPlot (Compact)",
      output_dir = output_dir,
      max_genes_per_panel = 6,
      width_cap = 18,
      height_cap = 11,
      limitsize = TRUE
    ),
    error = function(e) {
      list(fig = NULL, message = paste0("Compact manual subtype marker dotplot failed: ", conditionMessage(e)))
    }
  )
  result$compact_fig <- compact_res$fig
  result$message <- compact_res$message %||% ""

  full_res <- tryCatch(
    build_manual_marker_dotplot_variant(
      obj = obj,
      marker_dict = marker_dict,
      label_col = label_col,
      plot_basename = "sub_manual_marker_dotplot_full",
      plot_title = "Manual Subtype Marker DotPlot (Full)",
      output_dir = output_dir,
      max_genes_per_panel = Inf,
      width_cap = Inf,
      height_cap = Inf,
      limitsize = FALSE
    ),
    error = function(e) {
      list(fig = NULL, message = paste0("Full manual subtype marker dotplot failed but compact output was kept: ", conditionMessage(e)))
    }
  )
  result$full_fig <- full_res$fig
  if (nzchar(full_res$message %||% "")) {
    result$message <- paste(c(result$message, full_res$message), collapse = "\n")
    result$message <- trimws(result$message)
  }

  result
}

tryCatch({
  if (!file.exists(input_rds)) {
    stop(paste("Input object was not found for subcluster analysis:", input_rds))
  }

  obj <- readRDS(input_rds)
  tryCatch({
    if (inherits(obj[["RNA"]], "Assay5")) {
      obj[["RNA"]] <- JoinLayers(obj[["RNA"]])
    }
  }, error = function(e) {})
  obj <- set_group_order(obj, params)
  cat(sprintf("Object: %d cells, %d genes\n", ncol(obj), nrow(obj)))

  if (action == "subset_and_cluster") {
    target_ct <- as.character(unlist(params$target_celltype))
    result_id <- as.character(params$result_id %||% "")
    result_name <- as.character(params$result_name %||% result_id)
    if (length(target_ct) == 0) {
      stop("Please select at least one target main cell type.")
    }
    if (!"cell.type" %in% colnames(obj@meta.data)) {
      stop("cell.type column is missing. Please annotate main clusters first.")
    }

    report_progress(5, "Creating subcluster subset...")
    Idents(obj) <- "cell.type"
    sub_obj <- subset(obj, idents = target_ct)
    if (ncol(sub_obj) < 50) {
      stop(sprintf("Subset contains too few cells (%d) for stable subcluster analysis.", ncol(sub_obj)))
    }

    if ("RNA" %in% Assays(sub_obj)) {
      DefaultAssay(sub_obj) <- "RNA"
      tryCatch({
        if (inherits(sub_obj[["RNA"]], "Assay5")) {
          sub_obj[["RNA"]] <- JoinLayers(sub_obj[["RNA"]])
        }
      }, error = function(e) {})
    }

    hvg_n <- as.integer(params$hvg_number %||% 2000)
    npcs <- as.integer(params$npcs %||% 30)
    dims_s <- as.character(params$dims %||% "1:10")
    dims_r <- eval(parse(text = dims_s))
    res <- as.numeric(params$resolution %||% 0.3)
    primary_red <- tolower(as.character(params$reduction %||% "umap"))
    run_umap <- primary_red == "umap"
    run_tsne <- primary_red == "tsne"

    report_progress(15, "NormalizeData...")
    sub_obj <- NormalizeData(sub_obj, verbose = FALSE)
    report_progress(25, "FindVariableFeatures...")
    sub_obj <- FindVariableFeatures(sub_obj, nfeatures = hvg_n, verbose = FALSE)
    p_var <- VariableFeaturePlot(sub_obj)
    top10 <- head(VariableFeatures(sub_obj), 10)
    p_var <- LabelPoints(plot = p_var, points = top10, repel = TRUE)
    var_basename <- if (nzchar(result_id)) paste0(result_id, "_variable_features") else "subcluster_variable_features"
    fig <- save_plot(p_var, var_basename, output_dir, width = 10, height = 6)
    all_figures <- c(all_figures, basename(fig))
    report_progress(35, "ScaleData...")
    sub_obj <- ScaleData(sub_obj, verbose = FALSE)
    report_progress(45, "RunPCA...")
    sub_obj <- RunPCA(sub_obj, npcs = npcs, verbose = FALSE)
    p_elbow <- ElbowPlot(sub_obj, ndims = npcs) + labs(title = "Subcluster Elbow Plot") + sc_theme
    elbow_basename <- if (nzchar(result_id)) paste0(result_id, "_elbow_plot") else "subcluster_elbow_plot"
    fig <- save_plot(p_elbow, elbow_basename, output_dir, width = 8, height = 5)
    all_figures <- c(all_figures, basename(fig))

    if (run_umap) {
      report_progress(55, "RunUMAP...")
      sub_obj <- RunUMAP(sub_obj, dims = dims_r, umap.method = "uwot", metric = "cosine", verbose = FALSE)
    }
    if (run_tsne) {
      report_progress(65, "RunTSNE...")
      sub_obj <- RunTSNE(sub_obj, dims = dims_r, verbose = FALSE)
    }

    report_progress(75, "FindNeighbors...")
    sub_obj <- FindNeighbors(sub_obj, dims = dims_r, verbose = FALSE)
    report_progress(85, "FindClusters...")
    sub_obj <- safe_find_clusters(sub_obj, resolution = res, random_seed = as.integer(seed), verbose = FALSE)

    if (run_umap && "umap" %in% Reductions(sub_obj)) {
      p1 <- DimPlot(sub_obj, reduction = "umap", group.by = "seurat_clusters", cols = sc_colors, label = TRUE) +
        labs(title = paste0(paste(target_ct, collapse = "+"), " - UMAP")) + sc_theme
      fig <- save_plot(p1, "subcluster_umap", output_dir, width = 9, height = 7)
      all_figures <- c(all_figures, basename(fig))
      if ("group" %in% colnames(sub_obj@meta.data) && length(unique(as.character(sub_obj$group))) > 1) {
        p1_split <- DimPlot(sub_obj, reduction = "umap", group.by = "seurat_clusters", split.by = "group", cols = sc_colors, label = TRUE, label.size = 3.5) +
          labs(title = paste0(paste(target_ct, collapse = "+"), " - UMAP Split by Group")) + sc_theme
        split_basename <- if (nzchar(result_id)) paste0(result_id, "_umap_split") else "subcluster_umap_split"
        fig <- save_plot(p1_split, split_basename, output_dir, width = max(10, 4.5 * length(unique(as.character(sub_obj$group)))), height = 6.5)
        all_figures <- c(all_figures, basename(fig))
      }
    }

    if (run_tsne && "tsne" %in% Reductions(sub_obj)) {
      p2 <- DimPlot(sub_obj, reduction = "tsne", group.by = "seurat_clusters", cols = sc_colors, label = TRUE) +
        labs(title = paste0(paste(target_ct, collapse = "+"), " - t-SNE")) + sc_theme
      fig <- save_plot(p2, "subcluster_tsne", output_dir, width = 9, height = 7)
      all_figures <- c(all_figures, basename(fig))
      if ("group" %in% colnames(sub_obj@meta.data) && length(unique(as.character(sub_obj$group))) > 1) {
        p2_split <- DimPlot(sub_obj, reduction = "tsne", group.by = "seurat_clusters", split.by = "group", cols = sc_colors, label = TRUE, label.size = 3.5) +
          labs(title = paste0(paste(target_ct, collapse = "+"), " - t-SNE Split by Group")) + sc_theme
        split_basename <- if (nzchar(result_id)) paste0(result_id, "_tsne_split") else "subcluster_tsne_split"
        fig <- save_plot(p2_split, split_basename, output_dir, width = max(10, 4.5 * length(unique(as.character(sub_obj$group)))), height = 6.5)
        all_figures <- c(all_figures, basename(fig))
      }
    }

    report_progress(95, "Saving subcluster object...")
    sub_obj <- attach_subcluster_runtime_meta(sub_obj, params, action_name = "subset_and_cluster")
    saveRDS(sub_obj, file.path(output_dir, "subclustered.rds"))
    cluster_ids <- sort(unique(as.character(Idents(sub_obj))))
    writeLines(rownames(sub_obj), file.path(output_dir, "gene_list.txt"))

    write_summary(list(
      status = "success",
      action = "subset_and_cluster",
      result_id = result_id,
      result_name = result_name,
      target_celltypes = as.list(target_ct),
      target_celltype = paste(target_ct, collapse = "+"),
      n_cells = ncol(sub_obj),
      n_clusters = length(cluster_ids),
      cluster_ids = as.list(cluster_ids),
      primary_reduction = primary_red,
      figures = as.list(all_figures),
      tables = as.list(all_tables)
    ), output_dir)

    report_progress(100, "Subcluster clustering finished")
  }

  if (action == "find_markers") {
    report_progress(10, "FindAllMarkers...")
    Idents(obj) <- "seurat_clusters"
    heatmap_message <- ""
    markers <- FindAllMarkers(
      obj,
      min.pct = as.numeric(params$min_pct %||% 0.25),
      logfc.threshold = as.numeric(params$logfc_threshold %||% 0.25),
      only.pos = TRUE,
      verbose = FALSE
    )

    report_progress(70, "Saving subcluster marker results...")
    if (as.logical(params$filter_genes %||% TRUE)) {
      markers <- markers %>% filter(!grepl("^LOC|^RGD|^ENSRNOG|^AABR|^Gm[0-9]", gene))
    }

    write.csv(markers, file.path(output_dir, "sub_all_markers.csv"), row.names = FALSE)
    all_tables <- c(all_tables, "sub_all_markers.csv")

    fc_col <- get_fc_col(markers)
    top_m <- markers %>% group_by(cluster) %>% slice_max(order_by = .data[[fc_col]], n = 10) %>% ungroup()
    write.csv(top_m, file.path(output_dir, "sub_top_markers.csv"), row.names = FALSE)
    all_tables <- c(all_tables, "sub_top_markers.csv")

    top5 <- markers %>% group_by(cluster) %>% slice_max(order_by = .data[[fc_col]], n = 5) %>% ungroup()
    heatmap_genes <- unique(top5$gene)
    heatmap_genes <- heatmap_genes[heatmap_genes %in% rownames(obj)]
    if (length(heatmap_genes) >= 3 && length(unique(top5$cluster)) >= 2) {
      report_progress(82, "Generating subcluster marker heatmap...")
      heatmap_plot <- tryCatch({
        DoHeatmap(obj, features = heatmap_genes, group.colors = sc_colors, size = 3) +
          theme(axis.text.y = element_text(size = 6))
      }, error = function(e) NULL)
      if (!is.null(heatmap_plot)) {
        fig <- save_plot(heatmap_plot, "subcluster_marker_heatmap", output_dir, width = 14, height = 10)
        all_figures <- c(all_figures, basename(fig))
      } else {
        heatmap_message <- "Too few marker genes are available for a stable subcluster heatmap. Heatmap was skipped."
      }
    } else {
      heatmap_message <- "Too few marker genes are available for a stable subcluster heatmap. Heatmap was skipped."
    }

    cluster_ids <- sort(unique(as.character(Idents(obj))))
    writeLines(rownames(obj), file.path(output_dir, "gene_list.txt"))

    write_summary(list(
      status = "success",
      action = "find_markers",
      n_markers = nrow(markers),
      cluster_ids = as.list(cluster_ids),
      markers_csv = "sub_top_markers.csv",
      heatmap_message = heatmap_message,
      figures = as.list(all_figures),
      tables = as.list(all_tables)
    ), output_dir)

    report_progress(100, "Subcluster markers finished")
  }

  if (action == "apply_annotation") {
    mapping <- params$cluster_mapping
    if (is.null(mapping) || length(mapping) == 0) {
      stop("Cluster-to-subtype mapping is missing.")
    }

    report_progress(20, "Applying subtype mapping...")
    Idents(obj) <- "seurat_clusters"
    subtype_map <- unlist(mapping)
    names(subtype_map) <- names(mapping)
    subtype_vec <- subtype_map[as.character(Idents(obj))]
    subtype_vec[is.na(subtype_vec)] <- "Unknown"
    names(subtype_vec) <- colnames(obj)
    obj@meta.data$subtype <- sanitize_label_vec(subtype_vec, fallback = "Unknown")
    obj <- attach_subcluster_runtime_meta(
      obj,
      params,
      action_name = "apply_annotation",
      annotation_info = list(method = "manual", mapping = as.list(subtype_map))
    )
    mapping_df <- data.frame(
      cluster = names(subtype_map),
      subtype = sanitize_label_vec(unname(subtype_map), fallback = "Unknown"),
      stringsAsFactors = FALSE
    )
    write.csv(mapping_df, file.path(output_dir, "sub_cluster_mapping.csv"), row.names = FALSE)

    report_progress(60, "Saving subtype annotation object...")
    saveRDS(obj, file.path(output_dir, "sub_annotated.rds"))
    writeLines(sort(unique(obj$subtype)), file.path(output_dir, "subtypes.txt"))
    write.csv(obj@meta.data, file.path(output_dir, "sub_metadata.csv"), row.names = TRUE)

    write_summary(list(
      status = "success",
      action = "apply_annotation",
      result_id = as.character(params$result_id %||% ""),
      result_name = as.character(params$result_name %||% ""),
      subtypes = as.list(sort(unique(obj$subtype))),
      output_rds = "sub_annotated.rds",
      tables = list("sub_cluster_mapping.csv"),
      figures = list(),
      target_celltypes = as.list(as.character(unlist(params$target_celltype %||% c())))
    ), output_dir)

    report_progress(100, "Subcluster annotation finished")
  }

  if (action == "scina_annotate") {
    report_progress(12, "Preparing SCINA signatures...")
    scina_res <- run_scina_mapping(obj, params$custom_markers, output_dir)
    report_progress(78, "Saving SCINA mapping...")
    all_tables <- c(all_tables, "sub_scina_mapping.csv", "sub_scina_cell_predictions.csv")
    write_summary(list(
      status = "success",
      action = "scina_annotate",
      method = "SCINA",
      scina_mapping = as.list(scina_res$mapping),
      cluster_ids = as.list(names(scina_res$mapping)),
      figures = list(),
      tables = as.list(all_tables)
    ), output_dir)
    report_progress(100, "SCINA subtype annotation finished")
  }

  if (action == "cellassign_annotate") {
    report_progress(12, "Preparing CellAssign marker matrix...")
    cellassign_res <- run_cellassign_mapping(obj, params$custom_markers, output_dir)
    report_progress(78, "Saving CellAssign mapping...")
    all_tables <- c(all_tables, "sub_cellassign_mapping.csv", "sub_cellassign_cell_predictions.csv")
    write_summary(list(
      status = "success",
      action = "cellassign_annotate",
      method = "CellAssign",
      python_runtime = cellassign_res$python,
      cellassign_mapping = as.list(cellassign_res$mapping),
      cluster_ids = as.list(names(cellassign_res$mapping)),
      figures = list(),
      tables = as.list(all_tables)
    ), output_dir)
    report_progress(100, "CellAssign subtype annotation finished")
  }

  if (action == "generate_plots") {
    if (!"group" %in% colnames(obj@meta.data)) {
      obj$group <- "All"
    }
    obj <- set_group_order(obj, params)
    col_name <- if ("subtype" %in% colnames(obj@meta.data)) "subtype" else "seurat_clusters"
    Idents(obj) <- col_name

    red <- tolower(as.character(params$reduction %||% "umap"))
    if (!red %in% Reductions(obj)) {
      stop(sprintf("Requested reduction '%s' was not found. Please rerun subcluster analysis with the same reduction used in the main analysis.", red))
    }

    red_label <- if (identical(red, "tsne")) "t-SNE" else toupper(red)
    report_progress(20, paste0(red_label, " plot..."))
    p1 <- DimPlot(obj, reduction = red, group.by = col_name, cols = sc_colors, label = TRUE, label.size = 5.25, repel = TRUE) +
      labs(title = paste0("Subtype (", red_label, ")")) + sc_theme
    fig <- save_plot(p1, paste0("subtype_", red), output_dir, width = 10, height = 8)
    all_figures <- c(all_figures, basename(fig))

    n_groups <- length(unique(obj$group))
    manual_marker_message <- ""
    if (n_groups > 1) {
      report_progress(35, "Calculating subcluster composition...")
      group_order <- if (is.factor(obj$group)) levels(obj$group) else unique(as.character(obj$group))
      prop_df <- build_composition_df(
        group_vec = obj$group,
        label_vec = obj@meta.data[[col_name]],
        group_order = group_order,
        label_col = "subtype"
      )
      group_levels <- levels(prop_df$group)
      x_positions <- seq_along(group_levels)
      if (length(x_positions) >= 2) {
        x_positions[1] <- x_positions[1] + 0.08
      }
      names(x_positions) <- group_levels
      prop_df$x_pos <- unname(x_positions[as.character(prop_df$group)])
      n_groups <- length(group_levels)
      plot_width <- max(4.5, 4.5 + (n_groups - 2) * 0.85)
      p_bar <- ggplot(prop_df, aes(x = x_pos, y = proportion, fill = subtype)) +
        geom_col(width = 0.6) +
        scale_fill_manual(values = sc_colors) +
        scale_y_continuous(labels = scales::percent_format(accuracy = 1)) +
        scale_x_continuous(
          breaks = unname(x_positions),
          labels = group_levels,
          expand = expansion(add = c(0.38, 0.38))
        ) +
        theme_classic() +
        ylab("Proportion") + xlab("") +
        theme(plot.margin = margin(5.5, 14, 5.5, 14)) +
        ggtitle("Subcluster Composition") + sc_theme
      fig <- save_plot(p_bar, "subtype_composition_bar", output_dir, width = plot_width, height = 6)
      all_figures <- c(all_figures, basename(fig))
      comp_csv <- file.path(output_dir, "composition_sub_percent.csv")
      write.csv(prop_df, comp_csv, row.names = FALSE)
      all_tables <- c(all_tables, basename(comp_csv))
    }

    if (n_groups > 1 && n_groups <= 6) {
      report_progress(50, "Split plot...")
      p2 <- DimPlot(obj, reduction = red, group.by = col_name, split.by = "group", cols = sc_colors, label = TRUE, label.size = 3.5) +
        labs(title = paste0("Subtypes by Group (", red_label, ")")) + sc_theme
      fig <- save_plot(p2, paste0("subtype_", red, "_by_group"), output_dir, width = 6 * n_groups, height = 6)
      all_figures <- c(all_figures, basename(fig))
    }

    bubble_plot <- build_marker_bubble_plot_dual(
      obj = obj,
      markers_csv = file.path(output_dir, "sub_top_markers.csv"),
      label_col = col_name,
      output_dir = output_dir
    )
    for (fig_name in c(bubble_plot$compact_fig, bubble_plot$full_fig)) {
      if (!is.null(fig_name) && nzchar(fig_name)) {
        all_figures <- c(all_figures, fig_name)
      }
    }

    manual_plot <- build_manual_marker_dotplot_dual(
      obj = obj,
      marker_dict = params$custom_markers,
      label_col = col_name,
      output_dir = output_dir
    )
    for (fig_name in c(manual_plot$compact_fig, manual_plot$full_fig)) {
      if (!is.null(fig_name) && nzchar(fig_name)) {
        all_figures <- c(all_figures, fig_name)
      }
    }
    manual_marker_message <- paste(
      c(
        bubble_plot$message %||% "",
        manual_plot$message %||% ""
      ),
      collapse = "\n"
    )
    manual_marker_message <- trimws(manual_marker_message)

    write_summary(list(
      status = "success",
      action = "generate_plots",
      result_id = as.character(params$result_id %||% ""),
      result_name = as.character(params$result_name %||% ""),
      manual_marker_plot_message = manual_marker_message,
      figures = as.list(all_figures),
      tables = as.list(all_tables)
    ), output_dir)

    report_progress(100, "Subcluster plots finished")
  }

  if (action == "get_genes") {
    writeLines(rownames(obj), file.path(output_dir, "gene_list.txt"))
    write_summary(list(status = "success", action = "get_genes", n_genes = nrow(obj), figures = list(), tables = list()), output_dir)
  }
}, error = function(e) {
  err_msg <- conditionMessage(e)
  suggestion <- "Please check the input object, target cell type, and parameter settings."
  if (grepl("SCINA", err_msg, ignore.case = TRUE)) {
    suggestion <- paste0(
      "Please verify that the local R runtime contains the SCINA package and that each subtype has markers present in the current object.\n",
      "SCINA runs fully offline in this app and does not use an online reference atlas."
    )
  } else if (grepl("CellAssign|cellassign", err_msg, ignore.case = TRUE)) {
    suggestion <- paste0(
      "Please verify that the local R runtime contains the cellassign package stack and that raw counts plus marker genes are available.\n",
      "CellAssign runs fully offline in this app and does not use an online reference atlas."
    )
  }
  write_error_summary("Subcluster Analysis", err_msg, suggestion, output_dir)
  cat(sprintf("Error: %s\n", err_msg))
  quit(status = 1)
})
