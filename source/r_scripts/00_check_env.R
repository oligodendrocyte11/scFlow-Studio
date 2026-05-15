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
# 00_check_env.R — R 
# ═══════════════════════════════════════════
args <- commandArgs(trailingOnly = TRUE)

# 
if (length(args) >= 1) {
  params <- jsonlite::fromJSON(args[1])
  output_dir <- params$output_dir
} else {
  output_dir <- tempdir()
}

required_packages <- c(
  "Seurat", "jsonlite", "ggplot2", "patchwork",
  "dplyr", "tidyr", "Matrix"
)

optional_packages <- c(
  "DoubletFinder", "CellChat", "monocle3",
  "ComplexHeatmap", "MAST", "pheatmap",
  "SeuratDisk", "zellkonverter"
)

check_pkg <- function(pkg) {
  installed <- requireNamespace(pkg, quietly = TRUE)
  version <- if (installed) as.character(packageVersion(pkg)) else NA
  list(package = pkg, installed = installed, version = version)
}

results_required <- lapply(required_packages, check_pkg)
results_optional <- lapply(optional_packages, check_pkg)

r_version <- paste0(R.version$major, ".", R.version$minor)

summary <- list(
  status = "success",
  r_version = r_version,
  required = results_required,
  optional = results_optional,
  all_required_ok = all(sapply(results_required, function(x) x$installed))
)

# Results
jsonlite::write_json(summary, file.path(output_dir, "summary.json"),
                      auto_unbox = TRUE, pretty = TRUE)

cat("R environment check completed\n")
if (!summary$all_required_ok) {
  missing <- sapply(results_required, function(x) {
    if (!x$installed) x$package else NULL
  })
  missing <- Filter(Negate(is.null), missing)
  cat("Missing required packages:", paste(missing, collapse = ", "), "\n")
} else {
  cat("All required packages are installed\n")
}
