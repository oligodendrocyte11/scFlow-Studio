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
if (length(args) < 1) stop("Usage: Rscript 04_batch.R <params.json>")

params <- read_params(args[1])
output_dir <- params$output_dir %||% params$cache_dir %||% "."
ensure_dir(output_dir)
set.seed(as.integer(params$seed %||% 1234))

samples <- safe_samples(params$samples)
add_prefix <- as.logical(params$add_prefix %||% TRUE)
batch_enabled_requested <- as.logical(params$batch_enabled %||% FALSE)
batch_key <- as.character(params$batch_key %||% "sample")
batch_method <- as.character(params$batch_method %||% "RPCA (Recommended)")
hvg_number <- as.integer(params$hvg_number %||% 3000)
npcs <- max(as.integer(params$npcs %||% 30), 30)
dims_str <- as.character(params$dims %||% "1:30")
dims_range <- eval(parse(text = dims_str))

all_figures <- c()

load_sample_objects <- function(sample_records) {
  objects <- list()
  for (sample_info in sample_records) {
    if (is.null(sample_info$rds_path) || !file.exists(sample_info$rds_path)) {
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

make_preview_embedding <- function(obj, hvg_number, npcs, dims_range) {
  obj <- NormalizeData(obj, verbose = FALSE)
  obj <- FindVariableFeatures(obj, selection.method = "vst", nfeatures = hvg_number, verbose = FALSE)
  obj <- ScaleData(obj, verbose = FALSE)
  obj <- RunPCA(obj, npcs = npcs, verbose = FALSE)
  obj <- RunUMAP(obj, dims = dims_range, umap.method = "uwot", metric = "cosine", verbose = FALSE)
  obj
}

integrate_batch_objects <- function(loaded_objects, batch_objects, batch_key, batch_method, hvg_number, npcs, dims_range, add_prefix = TRUE) {
  if (grepl("Harmony", batch_method, ignore.case = TRUE)) {
    merged_obj <- merge_named_objects(loaded_objects, add_prefix = add_prefix)
    merged_obj <- NormalizeData(merged_obj, verbose = FALSE)
    merged_obj <- FindVariableFeatures(merged_obj, selection.method = "vst", nfeatures = hvg_number, verbose = FALSE)
    merged_obj <- ScaleData(merged_obj, verbose = FALSE)
    merged_obj <- RunPCA(merged_obj, npcs = npcs, verbose = FALSE)
    merged_obj <- RunHarmony(
      object = merged_obj,
      group.by.vars = batch_key,
      reduction.use = "pca",
      dims.use = dims_range,
      verbose = FALSE
    )
    merged_obj <- RunUMAP(merged_obj, reduction = "harmony", dims = dims_range, umap.method = "uwot", metric = "cosine", verbose = FALSE)
    return(merged_obj)
  }

  object.list <- lapply(batch_objects, function(obj) {
    obj <- NormalizeData(obj, verbose = FALSE)
    obj <- FindVariableFeatures(obj, selection.method = "vst", nfeatures = hvg_number, verbose = FALSE)
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
  integrated <- ScaleData(integrated, verbose = FALSE)
  integrated <- RunPCA(integrated, npcs = npcs, verbose = FALSE)
  integrated <- RunUMAP(integrated, dims = dims_range, umap.method = "uwot", metric = "cosine", verbose = FALSE)
  integrated
}

write_batch_config <- function(path, config) {
  jsonlite::write_json(config, path, auto_unbox = TRUE, pretty = TRUE)
}

tryCatch({
  loaded_objects <- load_sample_objects(samples)
  if (length(loaded_objects) == 0) {
    stop("No singlet objects were found. Please finish doublet removal first.")
  }

  batch_objects <- build_batch_objects(loaded_objects, batch_key = batch_key, add_prefix = add_prefix)
  batch_units <- names(batch_objects)
  effective_batch_enabled <- batch_enabled_requested && length(batch_objects) > 1

  if (!batch_enabled_requested) {
    batch_status <- "skipped"
    batch_message <- "batch_enabled = false; skipping batch correction."
    cat("batch_enabled = false\n")
    cat("Skipping batch correction; no IntegrateData, Harmony, or correction method will be applied.\n")
  } else if (length(batch_objects) <= 1) {
    batch_status <- "pass_through"
    batch_message <- "Only one batch unit was found; completed in pass-through mode."
    cat("Batch unit count <= 1; skipping batch correction and completing in pass-through mode.\n")
  } else {
    batch_status <- "enabled"
    batch_message <- sprintf("Batch correction enabled: %s / %s", batch_key, batch_method)
    cat(sprintf("batch_enabled = true; starting batch correction: %s / %s\n", batch_key, batch_method))
  }

  report_progress(10, "Generating pre-correction preview...")
  merged_raw <- merge_named_objects(loaded_objects, add_prefix = add_prefix)
  raw_preview <- make_preview_embedding(merged_raw, hvg_number = hvg_number, npcs = npcs, dims_range = dims_range)

  batch_plot_tables <- c()
  write_embedding_table <- function(obj, reduction_name, basename_no_ext, phase) {
    if (!reduction_name %in% Reductions(obj)) return(NULL)
    coords <- Embeddings(obj, reduction_name)
    df <- data.frame(
      cell_id = rownames(coords),
      phase = phase,
      dim_1 = coords[, 1],
      dim_2 = coords[, 2],
      sample = as.character(obj$sample),
      group = if ("group" %in% colnames(obj@meta.data)) as.character(obj$group) else "All",
      stringsAsFactors = FALSE
    )
    csv <- file.path(output_dir, paste0(basename_no_ext, ".csv"))
    write.csv(df, csv, row.names = FALSE)
    batch_plot_tables <<- unique(c(batch_plot_tables, basename(csv)))
    csv
  }

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
  write_embedding_table(raw_preview, "umap", "batch_before_umap_coordinates", "before")

  if (identical(batch_status, "enabled")) {
    report_progress(50, "Running Seurat batch integration...")
    integrated_preview <- integrate_batch_objects(
      loaded_objects = loaded_objects,
      batch_objects = batch_objects,
      batch_key = batch_key,
      batch_method = batch_method,
      hvg_number = hvg_number,
      npcs = npcs,
      dims_range = dims_range,
      add_prefix = add_prefix
    )
    p_after_group <- if (group_available) {
      DimPlot(integrated_preview, reduction = "umap", group.by = "group", cols = sc_colors) +
        labs(title = sprintf("After Batch Correction (group / %s)", batch_method)) + sc_theme
    } else NULL
    p_after_sample <- if (sample_available) {
      DimPlot(integrated_preview, reduction = "umap", group.by = "sample", cols = sc_colors) +
        labs(title = sprintf("After Batch Correction (sample / %s)", batch_method)) + sc_theme
    } else NULL
    write_embedding_table(integrated_preview, "umap", "batch_after_umap_coordinates", "after")
  } else {
    report_progress(50, "Batch correction is disabled; completed in pass-through mode...")
    p_after_group <- if (!is.null(p_before_group)) p_before_group + labs(title = "Skipped Batch Correction (group / pass-through)") else NULL
    p_after_sample <- if (!is.null(p_before_sample)) p_before_sample + labs(title = "Skipped Batch Correction (sample / pass-through)") else NULL
  }

  if (!is.null(p_before_group) && !is.null(p_after_group)) {
    p_compare_group <- p_before_group + p_after_group + plot_layout(ncol = 2)
    fig_group_compare <- save_plot(p_compare_group, "batch_group_compare", output_dir, width = 14, height = 6)
    all_figures <- c(all_figures, basename(fig_group_compare))
  }

  if (!is.null(p_before_sample) && !is.null(p_after_sample)) {
    p_compare_sample <- p_before_sample + p_after_sample + plot_layout(ncol = 2)
    fig_compare_sample <- save_plot(p_compare_sample, "batch_sample_compare", output_dir, width = 14, height = 6)
    all_figures <- c(all_figures, basename(fig_compare_sample))
  }

  config <- list(
    batch_enabled = effective_batch_enabled,
    batch_requested = batch_enabled_requested,
    batch_status = batch_status,
    correction_performed = identical(batch_status, "enabled"),
    batch_key = batch_key,
    batch_method = batch_method,
    batch_message = batch_message
  )
  write_batch_config(file.path(output_dir, "batch_config.json"), config)

  write_summary(list(
    status = "success",
    action = "batch_preview",
    batch_enabled = effective_batch_enabled,
    batch_requested = batch_enabled_requested,
    batch_status = batch_status,
    correction_performed = identical(batch_status, "enabled"),
    batch_message = batch_message,
    batch_key = batch_key,
    batch_method = batch_method,
    n_samples = length(loaded_objects),
    n_batches = length(batch_objects),
    n_cells = ncol(merged_raw),
    batch_units = as.list(batch_units),
    figures = as.list(all_figures),
    tables = as.list(batch_plot_tables)
  ), output_dir)

  report_progress(100, "Batch correction step finished")
  cat(sprintf("Step finished: %s\n", batch_message))
}, error = function(e) {
  write_error_summary(
    "Batch Correction",
    conditionMessage(e),
 "Please confirm that doublet removal has completed and that the selected batch column is available.",
    output_dir
  )
  cat(sprintf("Error: %s\n", conditionMessage(e)))
  quit(status = 1)
})
