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
  SCRIPT_DIR <- dirname(normalizePath(sub("^--file=", "", file_arg[1])))
} else {
  SCRIPT_DIR <- getwd()
}
source(file.path(SCRIPT_DIR, "utils", "io_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Usage: Rscript 01_detect_seurat_rds.R <params.json>")

params <- read_params(args[1])
output_dir <- as.character(params$output_dir %||% ".")
ensure_dir(output_dir)

get_counts_data <- function(obj) {
  tryCatch(
    GetAssayData(obj, assay = "RNA", layer = "counts"),
    error = function(e) {
      GetAssayData(obj, assay = "RNA", slot = "counts")
    }
  )
}

tryCatch({
  input_rds <- as.character(params$input_rds %||% "")
  if (input_rds == "" || !file.exists(input_rds)) {
 stop(".rds file does not exist.")
  }

  report_progress <- function(pct, message) {
    cat(sprintf("##PROGRESS:%d:%s\n", as.integer(pct), message))
  }

  report_progress(10, "Loading Seurat RDS...")
  obj <- readRDS(input_rds)
  if (!inherits(obj, "Seurat")) {
 stop(".rds Seurat Object, Sample Seurat Object.")
  }
  if (!"RNA" %in% Assays(obj)) {
 stop("The Seurat object is missing the RNA assay; unable to continue.")
  }

  report_progress(40, "Checking counts matrix...")
  counts <- get_counts_data(obj)
  n_cells <- ncol(counts)
  n_genes <- nrow(counts)
  if (is.null(n_cells) || is.null(n_genes) || n_cells <= 0 || n_genes <= 0) {
 stop(" Seurat Object counts matrix, Unable to Sample.")
  }

  sample_name <- as.character(params$sample_name %||% "")
  if (sample_name == "") {
    sample_name <- tools::file_path_sans_ext(basename(input_rds))
  }

  report_progress(80, "Preparing sample metadata...")
  write_summary(list(
    status = "success",
    action = "detect_seurat_rds",
    source_type = "seurat_rds",
    sample_count = 1,
    cell_count = n_cells,
    gene_count = n_genes,
    samples = list(list(
      sample_name = sample_name,
      group = sample_name,
      cell_count = n_cells,
      gene_count = n_genes,
      data_type = "Seurat RDS"
    )),
    figures = list(),
    tables = list()
  ), output_dir)
  report_progress(100, "Seurat RDS detection completed")
}, error = function(e) {
 write_error_summary("Seurat RDS ", conditionMessage(e), "Please confirmfileSample Seurat Object, Object RNA assay counts matrix.", output_dir)
  quit(status = 1)
})
