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
  library(harmony)
  library(ggplot2)
  library(patchwork)
  library(jsonlite)
})

initial_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", initial_args, value = TRUE)
if (length(file_arg) > 0) {
  SCRIPT_DIR <- dirname(normalizePath(sub("^--file=", "", file_arg[1])))
} else {
  SCRIPT_DIR <- getwd()
}
source(file.path(SCRIPT_DIR, "utils", "io_utils.R"))
source(file.path(SCRIPT_DIR, "utils", "plot_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Usage: Rscript 05_cluster.R <params.json>")

params <- read_params(args[1])
output_dir <- params$output_dir %||% "."
ensure_dir(output_dir)
set.seed(as.integer(params$seed %||% 1234))

samples <- safe_samples(params$samples)
add_prefix <- as.logical(params$add_prefix %||% TRUE)
hvg_method <- as.character(params$hvg_method %||% "vst")
hvg_number <- as.integer(params$hvg_number %||% 3000)
regress_str <- as.character(params$regress_vars %||% "nCount_RNA,percent.mt")
regress_vars <- trimws(strsplit(regress_str, ",")[[1]])
npcs <- as.integer(params$npcs %||% 50)
dims_str <- as.character(params$dims %||% "1:30")
dims_range <- eval(parse(text = dims_str))
resolution <- as.numeric(params$resolution %||% 1.2)
primary_red <- tolower(as.character(params$primary_reduction %||% "umap"))
run_umap <- as.logical(params$run_umap %||% (primary_red == "umap"))
run_tsne <- as.logical(params$run_tsne %||% (primary_red == "tsne"))

batch_enabled <- as.logical(params$batch_enabled %||% FALSE)
batch_key <- as.character(params$batch_key %||% "sample")
batch_method <- as.character(params$batch_method %||% "RPCA (Recommended)")
batch_status_from_page <- as.character(params$batch_status %||% "")

merge_dir <- params$merge_cache_dir %||% output_dir
ensure_dir(merge_dir)

old_ver <- getOption("Seurat.object.assay.version")
options(Seurat.object.assay.version = "v3")
on.exit({ options(Seurat.object.assay.version = old_ver) }, add = TRUE)

all_figures <- c()
all_tables <- c()

load_sample_objects <- function(sample_records) {
  objects <- list()
  for (sample_info in sample_records) {
    if (is.null(sample_info$rds_path) || !file.exists(sample_info$rds_path)) {
      cat(sprintf("  Warning: Cannot find %s; skipping\n", sample_info$rds_path %||% "(NULL)"))
      next
    }
    obj <- readRDS(sample_info$rds_path)
    obj$sample <- sample_info$name
    obj$group <- sample_info$group %||% sample_info$name
    objects[[length(objects) + 1]] <- list(
      name = sample_info$name,
      group = sample_info$group %||% sample_info$name,
      obj = obj
    )
  }
  objects
}

merge_named_objects <- function(named_objects, add_prefix = TRUE) {
  objs <- lapply(named_objects, function(x) x$obj)
  sample_names <- vapply(named_objects, function(x) x$name, character(1))
  if (length(objs) == 1) {
    return(objs[[1]])
  }
  if (add_prefix) {
    merge(objs[[1]], y = objs[-1], add.cell.ids = sample_names, project = "scFlowStudio")
  } else {
    merge(objs[[1]], y = objs[-1], project = "scFlowStudio")
  }
}

build_batch_objects <- function(loaded_objects, batch_key = "sample", add_prefix = TRUE) {
  unit_map <- list()
  for (entry in loaded_objects) {
    batch_unit <- if (identical(batch_key, "group")) entry$group else entry$name
    if (is.null(unit_map[[batch_unit]])) {
      unit_map[[batch_unit]] <- list()
    }
    unit_map[[batch_unit]][[length(unit_map[[batch_unit]]) + 1]] <- entry
  }

  result <- list()
  for (unit_name in names(unit_map)) {
    result[[unit_name]] <- merge_named_objects(unit_map[[unit_name]], add_prefix = add_prefix)
  }
  result
}

make_raw_preview <- function(obj, hvg_method, hvg_number, npcs, dims_range) {
  obj <- NormalizeData(obj, normalization.method = "LogNormalize", scale.factor = 10000, verbose = FALSE)
  obj <- FindVariableFeatures(obj, selection.method = hvg_method, nfeatures = hvg_number, verbose = FALSE)
  obj <- ScaleData(obj, verbose = FALSE)
  obj <- RunPCA(obj, features = VariableFeatures(obj), npcs = npcs, verbose = FALSE)
  obj <- RunUMAP(obj, dims = dims_range, umap.method = "uwot", metric = "cosine", verbose = FALSE)
  obj
}

integrate_batch_objects <- function(loaded_objects, batch_objects, batch_key, batch_method, hvg_method, hvg_number, npcs, dims_range, add_prefix = TRUE) {
  if (grepl("Harmony", batch_method, ignore.case = TRUE)) {
    merged_obj <- merge_named_objects(loaded_objects, add_prefix = add_prefix)
    merged_obj <- NormalizeData(merged_obj, normalization.method = "LogNormalize", scale.factor = 10000, verbose = FALSE)
    merged_obj <- FindVariableFeatures(merged_obj, selection.method = hvg_method, nfeatures = hvg_number, verbose = FALSE)
    merged_obj <- ScaleData(merged_obj, verbose = FALSE)
    merged_obj <- RunPCA(merged_obj, npcs = npcs, verbose = FALSE)
    merged_obj <- RunHarmony(
      object = merged_obj,
      group.by.vars = batch_key,
      reduction.use = "pca",
      dims.use = dims_range,
      verbose = FALSE
    )
    return(merged_obj)
  }

  object.list <- lapply(batch_objects, function(obj) {
    obj <- NormalizeData(obj, normalization.method = "LogNormalize", scale.factor = 10000, verbose = FALSE)
    obj <- FindVariableFeatures(obj, selection.method = hvg_method, nfeatures = hvg_number, verbose = FALSE)
    obj
  })

  features <- SelectIntegrationFeatures(object.list = object.list, nfeatures = hvg_number)
  reduction_name <- if (grepl("CCA", batch_method, ignore.case = TRUE)) "cca" else "rpca"

  if (identical(reduction_name, "rpca")) {
    object.list <- lapply(object.list, function(obj) {
      obj <- ScaleData(obj, verbose = FALSE)
      obj <- RunPCA(obj, npcs = npcs, verbose = FALSE)
      obj
    })
  }

  anchors <- FindIntegrationAnchors(
    object.list = object.list,
    anchor.features = features,
    reduction = reduction_name,
    dims = dims_range
  )
  integrated <- IntegrateData(anchorset = anchors, dims = dims_range)
  DefaultAssay(integrated) <- "integrated"
  integrated
}

save_cluster_embeddings <- function(obj, output_dir, run_umap, run_tsne, primary_red, reduction_source = "pca") {
  figure_names <- c()
  if (run_umap) {
    report_progress(70, "Run UMAP...")
    obj <- RunUMAP(obj, reduction = reduction_source, dims = dims_range, seed.use = as.integer(params$seed %||% 1234), umap.method = "uwot", metric = "cosine", verbose = FALSE)

    umap_coords <- Embeddings(obj, "umap")
    umap_coord_df <- data.frame(cell_id = rownames(umap_coords), umap_1 = umap_coords[, 1], umap_2 = umap_coords[, 2], seurat_cluster = as.character(obj$seurat_clusters), group = as.character(obj$group), sample = as.character(obj$sample), stringsAsFactors = FALSE)
    write.csv(umap_coord_df, file.path(output_dir, "umap_coordinates.csv"), row.names = FALSE)
    p1 <- DimPlot(obj, reduction = "umap", group.by = "seurat_clusters", cols = sc_colors, label = TRUE, label.size = 4) +
      labs(title = "UMAP - Clusters") + sc_theme
    fig <- save_plot(p1, "clustering_global", output_dir, width = 9, height = 7)
    figure_names <- c(figure_names, basename(fig))

    p2 <- DimPlot(obj, reduction = "umap", group.by = "group", cols = sc_colors) +
      labs(title = "UMAP - Groups") + sc_theme
    fig <- save_plot(p2, "umap_groups", output_dir, width = 9, height = 7)
    figure_names <- c(figure_names, basename(fig))

    n_groups <- length(unique(obj$group))
    if (n_groups > 1 && n_groups <= 6) {
      p3 <- DimPlot(obj, reduction = "umap", group.by = "seurat_clusters", split.by = "group", cols = sc_colors, label = TRUE) +
        labs(title = "UMAP - Split by Group") + sc_theme
      fig <- save_plot(p3, "clustering_split_by_group", output_dir, width = 6 * n_groups, height = 6)
      figure_names <- c(figure_names, basename(fig))
    }
  }

  if (run_tsne) {
    report_progress(85, "Run tSNE...")
    obj <- RunTSNE(obj, reduction = reduction_source, dims = dims_range, seed.use = as.integer(params$seed %||% 1234), verbose = FALSE)
    tsne_coords <- Embeddings(obj, "tsne")
    tsne_coord_df <- data.frame(cell_id = rownames(tsne_coords), tsne_1 = tsne_coords[, 1], tsne_2 = tsne_coords[, 2], seurat_cluster = as.character(obj$seurat_clusters), group = as.character(obj$group), sample = as.character(obj$sample), stringsAsFactors = FALSE)
    write.csv(tsne_coord_df, file.path(output_dir, "tsne_coordinates.csv"), row.names = FALSE)
    p_tsne <- DimPlot(obj, reduction = "tsne", group.by = "seurat_clusters", cols = sc_colors, label = TRUE) +
      labs(title = "tSNE - Clusters") + sc_theme
    fig <- save_plot(p_tsne, "tsne_clusters", output_dir, width = 9, height = 7)
    figure_names <- c(figure_names, basename(fig))
  }

  list(obj = obj, figures = figure_names)
}

tryCatch({
  loaded_objects <- load_sample_objects(samples)
  if (length(loaded_objects) == 0) {
    stop("No valid singlet object is available for merge and clustering.")
  }

  report_progress(5, "Loading sample objects...")
  for (entry in loaded_objects) {
    cat(sprintf("  Loading: %s\n", entry$name))
  }

  report_progress(15, "Merging objects...")
  merged_raw <- merge_named_objects(loaded_objects, add_prefix = add_prefix)
  saveRDS(merged_raw, file.path(merge_dir, "merged.rds"))
  cat(sprintf("Merge completed: %d cells, %d genes\n", ncol(merged_raw), nrow(merged_raw)))

  # Run an HVG preview on the raw merged object so both single-sample and multi-sample workflows keep the variable-features plot.
  report_progress(25, "Normalization...")
  raw_for_hvg <- NormalizeData(merged_raw, normalization.method = "LogNormalize", scale.factor = 10000, verbose = FALSE)

  report_progress(30, "Find variable features...")
  raw_for_hvg <- FindVariableFeatures(raw_for_hvg, selection.method = hvg_method, nfeatures = hvg_number, verbose = FALSE)
  p_hvg <- VariableFeaturePlot(raw_for_hvg)
  top10 <- head(VariableFeatures(raw_for_hvg), 10)
  p_hvg <- LabelPoints(plot = p_hvg, points = top10, repel = TRUE)
  hvg_df <- data.frame(
    gene = VariableFeatures(raw_for_hvg),
    rank = seq_along(VariableFeatures(raw_for_hvg)),
    is_top10 = VariableFeatures(raw_for_hvg) %in% top10,
    stringsAsFactors = FALSE
  )
  write.csv(hvg_df, file.path(output_dir, "variable_features.csv"), row.names = FALSE)
  all_tables <- unique(c(all_tables, "variable_features.csv"))
  fig <- save_plot(p_hvg, "variable_features", output_dir, width = 10, height = 6)
  all_figures <- c(all_figures, basename(fig))

batch_objects <- build_batch_objects(loaded_objects, batch_key = batch_key, add_prefix = add_prefix)
effective_batch_enabled <- batch_enabled && length(batch_objects) > 1
reduction_source <- "pca"
effective_batch_status <- if (effective_batch_enabled) {
    "enabled"
  } else if (nzchar(batch_status_from_page)) {
    batch_status_from_page
  } else {
    "skipped"
  }

  if (effective_batch_enabled) {
    report_progress(40, "Batch correction preview...")
    raw_preview <- make_raw_preview(merged_raw, hvg_method = hvg_method, hvg_number = hvg_number, npcs = max(npcs, 30), dims_range = dims_range)
    group_available <- "group" %in% colnames(raw_preview@meta.data) && length(unique(as.character(raw_preview$group))) > 1
    sample_available <- "sample" %in% colnames(raw_preview@meta.data) && length(unique(as.character(raw_preview$sample))) > 1

    p_before_group <- if (group_available) {
      DimPlot(raw_preview, reduction = "umap", group.by = "group", cols = sc_colors) +
        labs(title = "Before Batch Correction (group)") + sc_theme
    } else NULL
    p_before_sample <- if (sample_available) {
      DimPlot(raw_preview, reduction = "umap", group.by = "sample", cols = sc_colors) +
        labs(title = "Before Batch Correction (sample)") + sc_theme
    } else NULL

    report_progress(50, "Running batch integration...")
    clustered_obj <- integrate_batch_objects(
      loaded_objects = loaded_objects,
      batch_objects = batch_objects,
      batch_key = batch_key,
      batch_method = batch_method,
      hvg_method = hvg_method,
      hvg_number = hvg_number,
      npcs = npcs,
      dims_range = dims_range,
      add_prefix = add_prefix
    )
    if (grepl("Harmony", batch_method, ignore.case = TRUE)) {
      after_preview <- clustered_obj
      after_preview <- RunUMAP(after_preview, reduction = "harmony", dims = dims_range, umap.method = "uwot", metric = "cosine", verbose = FALSE)
      reduction_source <- "harmony"
    } else {
      after_preview <- ScaleData(clustered_obj, verbose = FALSE)
      after_preview <- RunPCA(after_preview, npcs = npcs, verbose = FALSE)
      after_preview <- RunUMAP(after_preview, dims = dims_range, umap.method = "uwot", metric = "cosine", verbose = FALSE)
      reduction_source <- "pca"
    }

    if (!is.null(p_before_group)) {
      p_after_group <- DimPlot(after_preview, reduction = "umap", group.by = "group", cols = sc_colors) +
        labs(title = sprintf("After Batch Correction (group / %s)", batch_method)) + sc_theme
      p_compare_group <- p_before_group + p_after_group + plot_layout(ncol = 2)
      fig <- save_plot(p_compare_group, "batch_group_compare", output_dir, width = 14, height = 6)
      all_figures <- c(all_figures, basename(fig))
    }

    if (!is.null(p_before_sample)) {
      p_after_sample <- DimPlot(after_preview, reduction = "umap", group.by = "sample", cols = sc_colors) +
        labs(title = sprintf("After Batch Correction (sample / %s)", batch_method)) + sc_theme
      p_compare_sample <- p_before_sample + p_after_sample + plot_layout(ncol = 2)
      fig <- save_plot(p_compare_sample, "batch_sample_compare", output_dir, width = 14, height = 6)
      all_figures <- c(all_figures, basename(fig))
    }

    report_progress(55, "Scaling integrated assay...")
    valid_regress <- regress_vars[regress_vars %in% colnames(clustered_obj@meta.data)]
    if (grepl("Harmony", batch_method, ignore.case = TRUE)) {
      if (length(valid_regress) > 0) {
        clustered_obj <- ScaleData(clustered_obj, vars.to.regress = valid_regress, verbose = FALSE)
      } else {
        clustered_obj <- ScaleData(clustered_obj, verbose = FALSE)
      }
      clustered_obj <- RunPCA(clustered_obj, npcs = npcs, verbose = FALSE)
      clustered_obj <- RunHarmony(
        object = clustered_obj,
        group.by.vars = batch_key,
        reduction.use = "pca",
        dims.use = dims_range,
        verbose = FALSE
      )
    } else if (length(valid_regress) > 0) {
      clustered_obj <- ScaleData(clustered_obj, vars.to.regress = valid_regress, verbose = FALSE)
    } else {
      clustered_obj <- ScaleData(clustered_obj, verbose = FALSE)
    }
  } else {
    cat("Batch correction is disabled or unnecessary; continuing with uncorrected data for clustering.\n")
    clustered_obj <- raw_for_hvg
    report_progress(40, "Scaling data...")
    valid_regress <- regress_vars[regress_vars %in% colnames(clustered_obj@meta.data)]
    if (length(valid_regress) > 0) {
      clustered_obj <- ScaleData(clustered_obj, vars.to.regress = valid_regress, verbose = FALSE)
    } else {
      clustered_obj <- ScaleData(clustered_obj, verbose = FALSE)
    }
  }

  report_progress(50, "Run PCA...")
  if (!effective_batch_enabled || !grepl("Harmony", batch_method, ignore.case = TRUE)) {
    clustered_obj <- RunPCA(clustered_obj, npcs = npcs, verbose = FALSE)
  }
  p_elbow <- ElbowPlot(clustered_obj, ndims = npcs) + labs(title = "Elbow Plot") + sc_theme
  stdev <- tryCatch(clustered_obj[[reduction_source]]@stdev, error = function(e) numeric(0))
  if (length(stdev) > 0) {
    elbow_df <- data.frame(pc = seq_along(stdev), stdev = as.numeric(stdev), variance = as.numeric(stdev)^2, stringsAsFactors = FALSE)
    write.csv(elbow_df, file.path(output_dir, "elbow_plot_data.csv"), row.names = FALSE)
    all_tables <- unique(c(all_tables, "elbow_plot_data.csv"))
  }
  fig <- save_plot(p_elbow, "elbow_plot", output_dir, width = 8, height = 5)
  all_figures <- c(all_figures, basename(fig))

  report_progress(60, "Clustering...")
  clustered_obj <- FindNeighbors(clustered_obj, reduction = reduction_source, dims = dims_range, verbose = FALSE)
  clustered_obj <- safe_find_clusters(clustered_obj, resolution = resolution, random_seed = as.integer(params$seed %||% 1234), verbose = FALSE)
  cat(sprintf("Clustering completed: %d clusters\n", length(unique(Idents(clustered_obj)))))

  embedding_result <- save_cluster_embeddings(clustered_obj, output_dir, run_umap, run_tsne, primary_red, reduction_source = reduction_source)
  clustered_obj <- embedding_result$obj
  all_figures <- c(all_figures, embedding_result$figures)

  report_progress(95, "Saving...")
  saveRDS(clustered_obj, file.path(output_dir, "clustered.rds"))
  writeLines(rownames(clustered_obj), file.path(output_dir, "gene_list.txt"))
  writeLines(primary_red, file.path(output_dir, "primary_reduction.txt"))

  cluster_table <- table(Idents(clustered_obj))
  cluster_ids <- names(cluster_table)
  cluster_stats <- lapply(seq_along(cluster_table), function(i) {
    list(
      cluster = cluster_ids[i],
      count = as.integer(cluster_table[i]),
      percent = sprintf("%.1f%%", cluster_table[i] / ncol(clustered_obj) * 100)
    )
  })

  write_summary(list(
    status = "success",
    total_cells = ncol(clustered_obj),
    total_genes = nrow(clustered_obj),
    n_clusters = length(cluster_ids),
    cluster_ids = as.list(cluster_ids),
    primary_reduction = primary_red,
    batch_enabled = effective_batch_enabled,
    batch_status = effective_batch_status,
    batch_key = batch_key,
    batch_method = batch_method,
    cluster_stats = cluster_stats,
    figures = as.list(all_figures),
    tables = as.list(unique(c(all_tables, "umap_coordinates.csv", "tsne_coordinates.csv"))),
    output_rds = "clustered.rds"
  ), output_dir)

  report_progress(100, "Finished")
  cat("\n=== Merge and Clustering Finished ===\n")
}, error = function(e) {
  write_error_summary(
    "Merge and Clustering",
    conditionMessage(e),
    "Please confirm that post-doublet RDS files exist and check the batch column, PCA dimensions, and resolution parameters.",
    output_dir
  )
  cat(sprintf("Error: %s\n", conditionMessage(e)))
  quit(status = 1)
})
