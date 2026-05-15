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
  library(jsonlite)
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

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Usage: Rscript 13_export_full_seurat.R <params.json>")

params <- read_params(args[1])
output_dir <- as.character(params$output_dir %||% ".")
ensure_dir(output_dir)

report_progress <- function(pct, message) {
  cat(sprintf("##PROGRESS:%d:%s\n", as.integer(pct), message))
}

safe_read_rds <- function(path) {
  if (!file.exists(path)) {
    return(NULL)
  }
  tryCatch(readRDS(path), error = function(e) NULL)
}

safe_read_json <- function(path) {
  if (!file.exists(path)) {
    return(NULL)
  }
  tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(e) NULL)
}

discover_subcluster_results <- function(project_dir) {
  config <- safe_read_json(file.path(project_dir, "project_config.json"))
  results <- config$subcluster_results %||% list()
  out <- list()

  if (length(results) > 0) {
    for (item in results) {
      if (!is.list(item)) {
        next
      }
      result_id <- as.character(item$result_id %||% "")
      cache_dir_rel <- as.character(item$cache_dir_rel %||% "")
      if (!nzchar(result_id) || !nzchar(cache_dir_rel)) {
        next
      }
      cache_dir <- file.path(project_dir, gsub("/", .Platform$file.sep, cache_dir_rel))
      out[[length(out) + 1]] <- list(
        result_id = result_id,
        display_name = as.character(item$display_name %||% result_id),
        target_celltypes = as.character(unlist(item$target_celltypes %||% character(0))),
        created_at = as.character(item$created_at %||% ""),
        primary_reduction = as.character(item$primary_reduction %||% ""),
        cache_dir = cache_dir,
        cache_dir_rel = cache_dir_rel
      )
    }
  }

  if (length(out) == 0) {
    legacy_dir <- file.path(project_dir, "cache", "subcluster")
    if (
      file.exists(file.path(legacy_dir, "subclustered.rds")) ||
      file.exists(file.path(legacy_dir, "sub_annotated.rds"))
    ) {
      out[[1]] <- list(
        result_id = "legacy_subcluster_001",
        display_name = "legacy_subcluster_001",
        target_celltypes = character(0),
        created_at = "",
        primary_reduction = "",
        cache_dir = legacy_dir,
        cache_dir_rel = "cache/subcluster"
      )
    }
  }
  out
}

attach_subcluster_results <- function(main_obj, subcluster_entries) {
  main_meta <- main_obj@meta.data
  registry <- list()
  merged_columns <- character(0)
  attached_count <- 0L

  for (entry in subcluster_entries) {
    result_id <- as.character(entry$result_id %||% "")
    if (!nzchar(result_id)) {
      next
    }
    cache_dir <- as.character(entry$cache_dir %||% "")
    annotated_path <- file.path(cache_dir, "sub_annotated.rds")
    clustered_path <- file.path(cache_dir, "subclustered.rds")
    sub_obj <- safe_read_rds(annotated_path)
    if (is.null(sub_obj)) {
      sub_obj <- safe_read_rds(clustered_path)
    }
    if (is.null(sub_obj) || !inherits(sub_obj, "Seurat")) {
      next
    }

    common_cells <- intersect(colnames(main_obj), colnames(sub_obj))
    if (length(common_cells) == 0) {
      next
    }

    subtype_col <- paste0("subtype__", result_id)
    subcluster_col <- paste0("subcluster__", result_id)
    target_col <- paste0("target_celltype__", result_id)
    result_col <- paste0("subcluster_result__", result_id)

    if (!subtype_col %in% colnames(main_meta)) main_meta[[subtype_col]] <- NA
    if (!subcluster_col %in% colnames(main_meta)) main_meta[[subcluster_col]] <- NA
    if (!target_col %in% colnames(main_meta)) main_meta[[target_col]] <- NA
    if (!result_col %in% colnames(main_meta)) main_meta[[result_col]] <- NA

    if ("subtype" %in% colnames(sub_obj@meta.data)) {
      main_meta[common_cells, subtype_col] <- as.character(sub_obj@meta.data[common_cells, "subtype"])
      merged_columns <- c(merged_columns, subtype_col)
    }
    if ("seurat_clusters" %in% colnames(sub_obj@meta.data)) {
      main_meta[common_cells, subcluster_col] <- as.character(sub_obj@meta.data[common_cells, "seurat_clusters"])
      merged_columns <- c(merged_columns, subcluster_col)
    }
    target_value <- paste(as.character(entry$target_celltypes %||% character(0)), collapse = "+")
    if (!nzchar(target_value)) {
      target_value <- as.character(entry$display_name %||% result_id)
    }
    main_meta[common_cells, target_col] <- target_value
    main_meta[common_cells, result_col] <- as.character(entry$display_name %||% result_id)
    merged_columns <- c(merged_columns, target_col, result_col)

    registry[[result_id]] <- list(
      meta = entry,
      object = sub_obj,
      cells = common_cells,
      metadata_columns = list(
        subtype = subtype_col,
        subcluster = subcluster_col,
        target_celltype = target_col,
        result_label = result_col
      )
    )
    if (is.null(main_obj@misc$subclusters)) {
      main_obj@misc$subclusters <- list()
    }
    main_obj@misc$subclusters[[result_id]] <- list(
      cells = common_cells,
      params = entry,
      result = sub_obj,
      annotation = if ("subtype" %in% colnames(sub_obj@meta.data)) {
        as.character(sub_obj@meta.data[common_cells, "subtype"])
      } else {
        NULL
      }
    )
    attached_count <- attached_count + 1L
  }

  main_obj@meta.data <- main_meta
  main_obj@misc$scflow_subcluster_results <- registry
  main_obj@misc$scflow_subcluster_registry <- lapply(registry, function(item) item$meta)
  list(
    object = main_obj,
    merged = attached_count > 0,
    merged_columns = unique(merged_columns),
    result_count = attached_count,
    message = if (attached_count > 0) {
      paste0("Attached ", attached_count, " subcluster result(s) into object@misc and metadata.")
    } else {
      "No subcluster results were attached."
    }
  )
}

tryCatch({
  project_dir <- as.character(params$project_dir %||% "")
  output_rds <- as.character(params$output_rds %||% "")
  if (!dir.exists(project_dir)) {
    stop("Project directory does not exist.")
  }
  if (!nzchar(output_rds)) {
    stop("Output .rds path is missing.")
  }

  cache_dir <- file.path(project_dir, "cache")
  main_candidates <- c(
    file.path(cache_dir, "annotation", "annotated.rds"),
    file.path(cache_dir, "clustering", "clustered.rds")
  )
  source_path <- ""
  main_obj <- NULL
  for (candidate in main_candidates) {
    obj <- safe_read_rds(candidate)
    if (!is.null(obj) && inherits(obj, "Seurat")) {
      main_obj <- obj
      source_path <- candidate
      break
    }
  }
  if (is.null(main_obj)) {
    stop("No main Seurat object was found for export.")
  }

  report_progress(20, "Loading main Seurat object...")
  report_progress(45, "Collecting multiple subcluster results...")
  subcluster_entries <- discover_subcluster_results(project_dir)
  merged <- attach_subcluster_results(main_obj, subcluster_entries)
  export_obj <- merged$object

  report_progress(70, "Checking reductions and annotations...")
  reductions <- tolower(Reductions(export_obj))
  reduction_flags <- c("pca", "umap", "tsne")
  reductions_present <- reduction_flags[reduction_flags %in% reductions]

  report_progress(90, "Saving full Seurat object...")
  saveRDS(export_obj, output_rds)

  write_summary(list(
    status = "success",
    action = "export_full_seurat",
    method = "full_seurat_rds",
    output_rds = output_rds,
    source_object = basename(source_path),
    source_path = source_path,
    subtype_merged = merged$merged,
    merged_columns = as.list(merged$merged_columns),
    merge_message = merged$message,
    n_subcluster_results = merged$result_count,
    n_cells = ncol(export_obj),
    n_features = nrow(export_obj),
    has_group = "group" %in% colnames(export_obj@meta.data),
    has_celltype = "cell.type" %in% colnames(export_obj@meta.data),
    has_subtype = "subtype" %in% colnames(export_obj@meta.data),
    has_seurat_clusters = "seurat_clusters" %in% colnames(export_obj@meta.data),
    reductions = as.list(reductions_present),
    figures = list(),
    tables = list()
  ), output_dir)
  report_progress(100, "Full annotated Seurat object exported")
}, error = function(e) {
  write_error_summary(
    "Full Seurat export",
    conditionMessage(e),
    "Please confirm that the project already contains clustered or annotated Seurat objects and that the output path is writable.",
    output_dir
  )
  cat(sprintf("Error: %s\n", conditionMessage(e)))
  quit(status = 1)
})
