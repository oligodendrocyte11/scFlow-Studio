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
if (length(args) < 1) stop("Usage: Rscript 03_doublet_passthrough.R <params.json>")

params <- read_params(args[1])
output_dir <- params$output_dir %||% params$cache_dir %||% "."
ensure_dir(output_dir)

samples <- safe_samples(params$samples)
if (length(samples) == 0) {
  stop("No samples were provided for doublet passthrough.")
}

sample_stats <- list()

tryCatch({
  for (i in seq_along(samples)) {
    s <- samples[[i]]
    sname <- as.character(s$name %||% paste0("sample_", i))
    qc_rds <- as.character(s$qc_rds %||% "")
    if (!file.exists(qc_rds)) {
      stop(sprintf("QC passthrough input is missing for sample %s: %s", sname, qc_rds))
    }
    report_progress(as.integer((i - 1) / length(samples) * 100), paste0("Preparing passthrough singlet object: ", sname))
    obj <- readRDS(qc_rds)
    before_cells <- if (inherits(obj, "Seurat")) ncol(obj) else NA
    out_rds <- file.path(output_dir, paste0(sname, "_singlet.rds"))
    saveRDS(obj, out_rds)
    sample_stats[[i]] <- list(
      name = sname,
      before = before_cells,
      after = before_cells,
      doublets = 0,
      doublet_rate = "0.0%",
      skipped = TRUE
    )
  }

  write_summary(list(
    status = "success",
    action = "skip_doublet",
    skipped = TRUE,
    message = "Doublet removal was skipped. Downstream analyses will use data without doublet filtering.",
    sample_stats = sample_stats,
    figures = list(),
    tables = list()
  ), output_dir)
  report_progress(100, "Doublet skip completed")
}, error = function(e) {
  write_error_summary("Doublet Skip", conditionMessage(e), "Please check the QC output objects before skipping doublet removal.", output_dir)
  cat(sprintf("Error: %s\n", conditionMessage(e)))
  quit(status = 1)
})
