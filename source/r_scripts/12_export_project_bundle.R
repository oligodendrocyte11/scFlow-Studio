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
if (length(args) < 1) stop("Usage: Rscript 12_export_project_bundle.R <params.json>")

params <- read_params(args[1])
output_dir <- as.character(params$output_dir %||% ".")
ensure_dir(output_dir)

report_progress <- function(pct, message) {
  cat(sprintf("##PROGRESS:%d:%s\n", as.integer(pct), message))
}

safe_read_json <- function(path) {
  if (!file.exists(path)) return(NULL)
  tryCatch(
    jsonlite::fromJSON(path, simplifyVector = FALSE, simplifyDataFrame = FALSE, simplifyMatrix = FALSE),
    error = function(e) NULL
  )
}

safe_read_csv <- function(path) {
  if (!file.exists(path)) return(NULL)
  tryCatch(read.csv(path, stringsAsFactors = FALSE, check.names = FALSE), error = function(e) NULL)
}

safe_read_rds <- function(path) {
  if (!file.exists(path)) return(NULL)
  tryCatch(readRDS(path), error = function(e) NULL)
}

collect_files <- function(dir_path, pattern) {
  if (!dir.exists(dir_path)) return(character(0))
  sort(list.files(dir_path, pattern = pattern, full.names = TRUE))
}

discover_subcluster_results <- function(project_dir, project_info) {
  out <- list()
  entries <- project_info$subcluster_results %||% list()
  if (length(entries) > 0) {
    for (item in entries) {
      if (!is.list(item)) next
      result_id <- as.character(item$result_id %||% "")
      cache_dir_rel <- as.character(item$cache_dir_rel %||% "")
      if (!nzchar(result_id) || !nzchar(cache_dir_rel)) next
      cache_dir <- file.path(project_dir, gsub("/", .Platform$file.sep, cache_dir_rel))
      out[[result_id]] <- list(
        meta = item,
        cache_dir = cache_dir,
        subclustered = file.path(cache_dir, "subclustered.rds"),
        sub_annotated = file.path(cache_dir, "sub_annotated.rds"),
        summary = file.path(cache_dir, "summary.json"),
        tables = collect_files(cache_dir, "\\.csv$"),
        figures = c(
          collect_files(cache_dir, "\\.png$"),
          collect_files(cache_dir, "\\.pdf$"),
          collect_files(cache_dir, "\\.svg$")
        )
      )
    }
  }
  if (length(out) == 0) {
    legacy_dir <- file.path(project_dir, "cache", "subcluster")
    if (file.exists(file.path(legacy_dir, "subclustered.rds")) || file.exists(file.path(legacy_dir, "sub_annotated.rds"))) {
      out[["legacy_subcluster_001"]] <- list(
        meta = list(result_id = "legacy_subcluster_001", display_name = "legacy_subcluster_001", cache_dir_rel = "cache/subcluster"),
        cache_dir = legacy_dir,
        subclustered = file.path(legacy_dir, "subclustered.rds"),
        sub_annotated = file.path(legacy_dir, "sub_annotated.rds"),
        summary = file.path(legacy_dir, "summary.json"),
        tables = collect_files(legacy_dir, "\\.csv$"),
        figures = c(
          collect_files(legacy_dir, "\\.png$"),
          collect_files(legacy_dir, "\\.pdf$"),
          collect_files(legacy_dir, "\\.svg$")
        )
      )
    }
  }
  out
}

tryCatch({
  project_dir <- as.character(params$project_dir %||% "")
  output_rds <- as.character(params$output_rds %||% "")
  if (project_dir == "" || !dir.exists(project_dir)) {
    stop("Project directory does not exist, so the project bundle cannot be exported.")
  }
  if (output_rds == "") {
    stop("No output .rds path was provided.")
  }

  report_progress(5, "Reading project configuration...")
  config_path <- file.path(project_dir, "project_config.json")
  samples_path <- file.path(project_dir, "samples.json")
  cache_dir <- file.path(project_dir, "cache")
  results_dir <- file.path(project_dir, "results")
  logs_dir <- file.path(project_dir, "logs")

  project_info <- safe_read_json(config_path)
  samples_info <- safe_read_json(samples_path)

  report_progress(20, "Collecting main analysis objects...")
  object_paths <- list(
    clustered = file.path(cache_dir, "clustering", "clustered.rds"),
    annotated = file.path(cache_dir, "annotation", "annotated.rds"),
    subclustered = file.path(cache_dir, "subcluster", "subclustered.rds"),
    sub_annotated = file.path(cache_dir, "subcluster", "sub_annotated.rds")
  )
  objects <- list()
  object_meta <- list()
  for (nm in names(object_paths)) {
    obj_path <- object_paths[[nm]]
    obj <- safe_read_rds(obj_path)
    if (!is.null(obj)) {
      objects[[nm]] <- obj
      object_meta[[nm]] <- list(
        path = obj_path,
        file_size_mb = round(file.info(obj_path)$size / (1024^2), 2)
      )
    }
  }

  report_progress(35, "Collecting multi-subcluster results...")
  subcluster_results <- discover_subcluster_results(project_dir, project_info)
  subcluster_objects <- list()
  subcluster_result_meta <- list()
  subcluster_tables <- list()
  subcluster_summaries <- list()
  subcluster_figures <- list()
  for (result_id in names(subcluster_results)) {
    info <- subcluster_results[[result_id]]
    subcluster_objects[[result_id]] <- list(
      subclustered = safe_read_rds(info$subclustered),
      sub_annotated = safe_read_rds(info$sub_annotated)
    )
    subcluster_result_meta[[result_id]] <- list(
      meta = info$meta,
      cache_dir = info$cache_dir,
      subclustered_path = info$subclustered,
      sub_annotated_path = info$sub_annotated
    )
    subcluster_tables[[result_id]] <- list()
    for (path in info$tables %||% character(0)) {
      tbl <- safe_read_csv(path)
      if (!is.null(tbl)) {
        subcluster_tables[[result_id]][[basename(path)]] <- tbl
      }
    }
    subcluster_summaries[[result_id]] <- safe_read_json(info$summary)
    subcluster_figures[[result_id]] <- info$figures %||% character(0)
  }

  report_progress(50, "Collecting step summaries...")
  summary_paths <- list(
    qc = file.path(cache_dir, "qc", "summary.json"),
    doublet = file.path(cache_dir, "doublet", "summary.json"),
    batch = file.path(cache_dir, "batch", "summary.json"),
    clustering = file.path(cache_dir, "clustering", "summary.json"),
    annotation = file.path(cache_dir, "annotation", "summary.json"),
    subcluster = file.path(cache_dir, "subcluster", "summary.json"),
    deg = file.path(cache_dir, "deg", "summary.json")
  )
  summaries <- list()
  for (nm in names(summary_paths)) {
    info <- safe_read_json(summary_paths[[nm]])
    if (!is.null(info)) {
      summaries[[nm]] <- info
    }
  }

  report_progress(65, "Collecting key tables...")
  csv_groups <- list(
    annotation = collect_files(file.path(cache_dir, "annotation"), "\\.csv$"),
    subcluster = collect_files(file.path(cache_dir, "subcluster"), "\\.csv$"),
    deg = collect_files(file.path(cache_dir, "deg"), "\\.csv$")
  )
  tables <- list()
  table_meta <- list()
  for (group_name in names(csv_groups)) {
    paths <- csv_groups[[group_name]]
    if (length(paths) == 0) next
    tables[[group_name]] <- list()
    table_meta[[group_name]] <- list()
    for (path in paths) {
      key <- basename(path)
      tbl <- safe_read_csv(path)
      if (!is.null(tbl)) {
        tables[[group_name]][[key]] <- tbl
        table_meta[[group_name]][[key]] <- list(
          path = path,
          nrow = nrow(tbl),
          ncol = ncol(tbl)
        )
      }
    }
  }

  report_progress(80, "Collecting figure paths...")
  png_paths <- c(
    collect_files(file.path(cache_dir, "qc"), "\\.png$"),
    collect_files(file.path(cache_dir, "doublet"), "\\.png$"),
    collect_files(file.path(cache_dir, "clustering"), "\\.png$"),
    collect_files(file.path(cache_dir, "annotation"), "\\.png$"),
    collect_files(file.path(cache_dir, "subcluster"), "\\.png$"),
    unlist(lapply(subcluster_figures, function(x) x[grepl("\\.png$", x)]), use.names = FALSE),
    collect_files(file.path(cache_dir, "deg"), "\\.png$"),
    collect_files(file.path(cache_dir, "gsea"), "\\.png$"),
    collect_files(file.path(cache_dir, "gene_analysis"), "\\.png$"),
    collect_files(file.path(cache_dir, "module_score"), "\\.png$")
  )
  pdf_paths <- c(
    collect_files(file.path(results_dir, "exports"), "\\.pdf$"),
    collect_files(file.path(cache_dir, "qc"), "\\.pdf$"),
    collect_files(file.path(cache_dir, "doublet"), "\\.pdf$"),
    collect_files(file.path(cache_dir, "clustering"), "\\.pdf$"),
    collect_files(file.path(cache_dir, "annotation"), "\\.pdf$"),
    collect_files(file.path(cache_dir, "subcluster"), "\\.pdf$"),
    unlist(lapply(subcluster_figures, function(x) x[grepl("\\.pdf$", x)]), use.names = FALSE),
    collect_files(file.path(cache_dir, "deg"), "\\.pdf$"),
    collect_files(file.path(cache_dir, "gsea"), "\\.pdf$"),
    collect_files(file.path(cache_dir, "gene_analysis"), "\\.pdf$"),
    collect_files(file.path(cache_dir, "module_score"), "\\.pdf$")
  )
  svg_paths <- c(
    collect_files(file.path(cache_dir, "qc"), "\\.svg$"),
    collect_files(file.path(cache_dir, "doublet"), "\\.svg$"),
    collect_files(file.path(cache_dir, "clustering"), "\\.svg$"),
    collect_files(file.path(cache_dir, "annotation"), "\\.svg$"),
    collect_files(file.path(cache_dir, "subcluster"), "\\.svg$"),
    unlist(lapply(subcluster_figures, function(x) x[grepl("\\.svg$", x)]), use.names = FALSE),
    collect_files(file.path(cache_dir, "deg"), "\\.svg$"),
    collect_files(file.path(cache_dir, "gsea"), "\\.svg$"),
    collect_files(file.path(cache_dir, "gene_analysis"), "\\.svg$"),
    collect_files(file.path(cache_dir, "module_score"), "\\.svg$")
  )

  bundle <- list(
    bundle_type = "scflow_project_bundle",
    exported_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
    project_info = project_info,
    samples = samples_info,
    step_status = project_info$step_status %||% list(),
    objects = objects,
    object_meta = object_meta,
    subcluster_results = subcluster_objects,
    subcluster_result_meta = subcluster_result_meta,
    summaries = summaries,
    subcluster_summaries = subcluster_summaries,
    tables = tables,
    subcluster_tables = subcluster_tables,
    table_meta = table_meta,
    figures = list(
      png = png_paths,
      pdf = pdf_paths,
      svg = svg_paths
    ),
    paths = list(
      project_dir = project_dir,
      cache_dir = cache_dir,
      results_dir = results_dir,
      logs_dir = logs_dir
    )
  )

  report_progress(92, "Writing project bundle .rds...")
  saveRDS(bundle, output_rds)

  n_tables <- 0L
  if (length(table_meta) > 0) {
    n_tables <- sum(vapply(table_meta, length, integer(1)))
  }
  write_summary(list(
    status = "success",
    action = "export_project_bundle",
    method = "project_bundle_rds",
    output_rds = output_rds,
    n_objects = length(objects),
    n_subcluster_results = length(subcluster_results),
    n_tables = n_tables,
    n_summaries = length(summaries),
    figures = list(),
    tables = list()
  ), output_dir)
  report_progress(100, "Project bundle export finished")
}, error = function(e) {
  write_error_summary(
    "Project bundle export",
    conditionMessage(e),
    "Please confirm that the project directory is intact, key objects are present, and the output path is writable.",
    output_dir
  )
  quit(status = 1)
})
