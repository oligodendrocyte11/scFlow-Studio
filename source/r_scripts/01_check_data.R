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

# ═══════════════════════════════════════════
# 01_check_data.R — 10X 
# ═══════════════════════════════════════════
suppressPackageStartupMessages({
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

# ── LoadingParameters ──
args <- commandArgs(trailingOnly = TRUE)
params <- read_params(args[1])
output_dir <- params$output_dir
ensure_dir(output_dir)

paths <- params$paths  # list of data_path strings

results <- list()

for (i in seq_along(paths)) {
  p <- paths[[i]]
  status <- "valid"
  message <- "OK"
  cells <- 0
  genes <- 0

  if (!dir.exists(p)) {
    status <- "missing"
    message <- paste("Path does not exist:", p)
  } else {
    # file
    mtx_files <- c("matrix.mtx", "matrix.mtx.gz")
    feat_files <- c("features.tsv", "features.tsv.gz", "genes.tsv", "genes.tsv.gz")
    bc_files <- c("barcodes.tsv", "barcodes.tsv.gz")

    has_mtx  <- any(file.exists(file.path(p, mtx_files)))
    has_feat <- any(file.exists(file.path(p, feat_files)))
    has_bc   <- any(file.exists(file.path(p, bc_files)))

    if (!has_mtx)  { status <- "missing"; message <- "Missing matrix.mtx(.gz)" }
    if (!has_feat) { status <- "missing"; message <- "Missing features.tsv(.gz)" }
    if (!has_bc)   { status <- "missing"; message <- "Missing barcodes.tsv(.gz)" }

 # 
    if (status == "valid") {
      bc_file <- NULL
      for (f in bc_files) {
        fp <- file.path(p, f)
        if (file.exists(fp)) { bc_file <- fp; break }
      }
      if (!is.null(bc_file)) {
        if (grepl("\\.gz$", bc_file)) {
          cells <- length(readLines(gzfile(bc_file)))
        } else {
          cells <- length(readLines(bc_file))
        }
      }

      feat_file <- NULL
      for (f in feat_files) {
        fp <- file.path(p, f)
        if (file.exists(fp)) { feat_file <- fp; break }
      }
      if (!is.null(feat_file)) {
        if (grepl("\\.gz$", feat_file)) {
          genes <- length(readLines(gzfile(feat_file)))
        } else {
          genes <- length(readLines(feat_file))
        }
      }
    }
  }

  results[[i]] <- list(
    path = p,
    status = status,
    message = message,
    cells = cells,
    genes = genes
  )
}

write_summary(list(
  status = "success",
  results = results,
  figures = list(),
  tables = list()
), output_dir)

cat("Data validation completed\n")
