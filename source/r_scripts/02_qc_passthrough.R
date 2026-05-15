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
  library(Matrix)
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
if (length(args) < 1) stop("Usage: Rscript 02_qc_passthrough.R <params.json>")

params <- read_params(args[1])
output_dir <- params$output_dir %||% params$cache_dir %||% "."
ensure_dir(output_dir)

old_ver <- getOption("Seurat.object.assay.version")
options(Seurat.object.assay.version = "v3")
on.exit({ options(Seurat.object.assay.version = old_ver) }, add = TRUE)

samples <- safe_samples(params$samples)
if (length(samples) == 0) {
  stop("No samples were provided for QC passthrough.")
}

find_matching_file <- function(path, patterns) {
  entries <- list.files(path, full.names = TRUE)
  base_names <- basename(entries)
  for (pat in patterns) {
    idx <- grep(pat, base_names, ignore.case = TRUE, perl = TRUE)
    if (length(idx) > 0) {
      return(entries[idx[1]])
    }
  }
  NULL
}

score_feature_column <- function(values) {
  values <- trimws(as.character(values %||% character(0)))
  values <- values[nzchar(values) & !is.na(values)]
  if (!length(values)) {
    return(-Inf)
  }

  symbol_like <- grepl("^[A-Za-z][A-Za-z0-9._-]*$", values)
  ensembl_like <- grepl("^ENS[A-Z0-9]*G[0-9]+(?:\\.[0-9]+)?$", values, ignore.case = TRUE)
  mito_like <- grepl("^(MT-|Mt-|mt-)", values)
  duplicated_penalty <- sum(duplicated(values))

  sum(symbol_like) * 2 + sum(mito_like) * 4 - sum(ensembl_like) * 3 - duplicated_penalty
}

feature_column_for_file <- function(feature_path) {
  preview <- tryCatch({
    if (grepl("\\.gz$", feature_path, ignore.case = TRUE)) {
      read.delim(gzfile(feature_path), header = FALSE, nrows = 5, stringsAsFactors = FALSE, comment.char = "")
    } else {
      read.delim(feature_path, header = FALSE, nrows = 5, stringsAsFactors = FALSE, comment.char = "")
    }
  }, error = function(e) NULL)
  if (is.null(preview) || ncol(preview) < 2) {
    return(1L)
  }
  col1 <- trimws(as.character(preview[[1]]))
  col2 <- trimws(as.character(preview[[2]]))
  valid2 <- nzchar(col2) & !is.na(col2)
  same_cols <- valid2 & (col1 == col2)
  score1 <- score_feature_column(col1)
  score2 <- score_feature_column(col2)
  if (is.finite(score2) && score2 > score1) {
    return(2L)
  }
  if (sum(valid2 & !same_cols) >= 1 && score2 >= score1) {
    return(2L)
  }
  1L
}

detect_mt_pattern <- function(feature_names, preferred_pattern, species = "") {
  feature_names <- as.character(feature_names %||% character(0))
  if (!length(feature_names)) {
    return(as.character(preferred_pattern))
  }

  species <- tolower(trimws(as.character(species %||% "")))
  species_candidates <- switch(
    species,
    human = c("^MT-", "^[mM][tT]-", "^Mt-", "^mt-"),
    mouse = c("^[mM][tT]-", "^Mt-", "^mt-", "^MT-"),
    rat = c("^[mM][tT]-", "^Mt-", "^mt-", "^MT-"),
    c("^[mM][tT]-", "^MT-", "^Mt-", "^mt-")
  )

  candidate_patterns <- unique(c(
    as.character(preferred_pattern %||% ""),
    species_candidates
  ))
  candidate_patterns <- candidate_patterns[nzchar(candidate_patterns)]

  hit_counts <- vapply(candidate_patterns, function(pattern) {
    length(grep(pattern, feature_names, value = TRUE))
  }, numeric(1))

  preferred_hits <- unname(hit_counts[match(as.character(preferred_pattern), candidate_patterns)])
  if (!is.na(preferred_hits) && preferred_hits > 0) {
    return(as.character(preferred_pattern))
  }

  best_idx <- which.max(hit_counts)
  if (length(best_idx) && hit_counts[best_idx] > 0) {
    auto_pattern <- candidate_patterns[best_idx]
    if (!identical(auto_pattern, as.character(preferred_pattern))) {
      cat(sprintf("  Auto-detected MT regex: %s (species=%s, requested %s had %d matches)\n",
                  auto_pattern,
                  ifelse(nzchar(species), species, "unknown"),
                  as.character(preferred_pattern),
                  ifelse(is.na(preferred_hits), 0, preferred_hits)))
    }
    return(auto_pattern)
  }

  as.character(preferred_pattern)
}

read_10x_flexible <- function(data_path) {
  matrix_path <- find_matching_file(data_path, c("(^|.*_)matrix\\.mtx(\\.gz)?$"))
  barcode_path <- find_matching_file(data_path, c("(^|.*_)barcodes\\.tsv(\\.gz)?$"))
  feature_path <- find_matching_file(data_path, c("(^|.*_)features\\.tsv(\\.gz)?$", "(^|.*_)genes\\.tsv(\\.gz)?$"))
  if (is.null(matrix_path) || is.null(barcode_path) || is.null(feature_path)) {
    stop("10X folder is missing matrix / barcode / feature files.")
  }
  raw_data <- ReadMtx(
    mtx = matrix_path,
    cells = barcode_path,
    features = feature_path,
    feature.column = feature_column_for_file(feature_path)
  )
  if (is.list(raw_data) && !inherits(raw_data, "dgCMatrix")) {
    if ("Gene Expression" %in% names(raw_data)) {
      raw_data <- raw_data[["Gene Expression"]]
    } else {
      raw_data <- raw_data[[1]]
    }
  }
  raw_data
}

read_expression_matrix_flexible <- function(data_path) {
  finalize_expression_df <- function(expr_df) {
    if (ncol(expr_df) == 0) stop("Expression matrix has no numeric columns after parsing.")
    original_df <- expr_df
    numeric_mask <- vapply(expr_df, function(col) {
      suppressWarnings(parsed <- as.numeric(as.character(col)))
      all(!is.na(parsed))
    }, logical(1))
    if (!any(numeric_mask)) stop("No numeric expression columns were detected in the matrix file.")
    if (!all(numeric_mask)) expr_df <- expr_df[, numeric_mask, drop = FALSE]
    numeric_df <- data.frame(lapply(expr_df, function(col) as.numeric(as.character(col))),
                             check.names = FALSE, stringsAsFactors = FALSE)
    rownames(numeric_df) <- rownames(original_df)
    as(as.matrix(numeric_df), "CsparseMatrix")
  }

  maybe_transpose_cell_by_gene <- function(expr_df) {
    rn <- rownames(expr_df)
    cn <- colnames(expr_df)
    if (is.null(rn) || is.null(cn)) {
      return(finalize_expression_df(expr_df))
    }

    barcode_like_rows <- mean(grepl("-\\d+$", rn)) > 0.5
    mito_like_cols <- mean(grepl("^(MT-|Mt-|mt-)", cn)) > 0
    gene_like_cols <- mean(grepl("^[A-Za-z][A-Za-z0-9._-]*$", cn)) > 0.5

    if (barcode_like_rows && (mito_like_cols || gene_like_cols)) {
      mat <- finalize_expression_df(expr_df)
      return(t(mat))
    }

    finalize_expression_df(expr_df)
  }

  con <- if (grepl("\\.gz$", data_path, ignore.case = TRUE)) gzfile(data_path, open = "rt") else file(data_path, open = "rt")
  first_line <- readLines(con, n = 1, warn = FALSE)
  close(con)

  if (grepl("\t", first_line, fixed = TRUE)) {
    expr_df <- read.delim(data_path, sep = "\t", header = TRUE, row.names = 1,
                          check.names = FALSE, stringsAsFactors = FALSE)
    if (ncol(expr_df) >= 1 && !is.numeric(expr_df[[1]])) {
      alt_names <- make.unique(as.character(expr_df[[1]]))
      if (sum(nzchar(alt_names)) > 0) rownames(expr_df) <- alt_names
      expr_df <- expr_df[, -1, drop = FALSE]
    }
    return(maybe_transpose_cell_by_gene(expr_df))
  }

  if (grepl(",", first_line, fixed = TRUE)) {
    expr_df <- read.csv(data_path, header = TRUE, row.names = 1,
                        check.names = FALSE, stringsAsFactors = FALSE)
    if (ncol(expr_df) >= 1 && !is.numeric(expr_df[[1]])) {
      alt_names <- make.unique(as.character(expr_df[[1]]))
      if (sum(nzchar(alt_names)) > 0) rownames(expr_df) <- alt_names
      expr_df <- expr_df[, -1, drop = FALSE]
    }
    return(maybe_transpose_cell_by_gene(expr_df))
  }

  expr_df <- read.table(data_path, header = TRUE, sep = "", quote = "\"",
                        check.names = FALSE, stringsAsFactors = FALSE, comment.char = "")
  if ("barcode" %in% colnames(expr_df)) {
    barcode_ids <- make.unique(as.character(expr_df$barcode))
    drop_cols <- intersect(c("barcode", "final_cluster_labels", "library"), colnames(expr_df))
    gene_df <- expr_df[, setdiff(colnames(expr_df), drop_cols), drop = FALSE]
    gene_matrix <- t(data.matrix(gene_df))
    colnames(gene_matrix) <- barcode_ids
    return(as(gene_matrix, "CsparseMatrix"))
  }
  if (ncol(expr_df) >= 2) {
    rownames(expr_df) <- make.unique(as.character(expr_df[[1]]))
    expr_df <- expr_df[, -1, drop = FALSE]
  }
  finalize_expression_df(expr_df)
}

read_sample_object <- function(sample_item) {
  data_type <- as.character(sample_item$data_type %||% "10X Matrix Folder")
  data_path <- as.character(sample_item$data_path %||% "")
  sample_name <- as.character(sample_item$name %||% "sample")
  mt_pattern <- as.character(sample_item$qc_params$mt_pattern %||% "^[mM][tT]-")
  species <- as.character(sample_item$species %||% "")

  if (data_type == "Seurat RDS") {
    obj <- readRDS(data_path)
    if (!inherits(obj, "Seurat")) {
      stop(sprintf("Sample %s is not a valid Seurat object.", sample_name))
    }
    if (!"percent.mt" %in% colnames(obj@meta.data)) {
      effective_mt_pattern <- detect_mt_pattern(rownames(obj), mt_pattern, species)
      obj[["percent.mt"]] <- PercentageFeatureSet(obj, pattern = effective_mt_pattern)
    }
    obj$sample <- sample_name
    obj$group <- sample_item$group %||% sample_name
    return(obj)
  }

  counts <- if (startsWith(data_type, "Expression Matrix")) {
    read_expression_matrix_flexible(data_path)
  } else {
    read_10x_flexible(data_path)
  }
  rownames(counts) <- gsub("_", "-", rownames(counts))
  obj <- CreateSeuratObject(counts = counts, project = sample_name, min.cells = 0, min.features = 0)
  obj$sample <- sample_name
  obj$group <- sample_item$group %||% sample_name
  effective_mt_pattern <- detect_mt_pattern(rownames(obj), mt_pattern, species)
  obj[["percent.mt"]] <- PercentageFeatureSet(obj, pattern = effective_mt_pattern)
  obj
}

sample_stats <- list()

tryCatch({
  for (i in seq_along(samples)) {
    s <- samples[[i]]
    sname <- as.character(s$name %||% paste0("sample_", i))
    report_progress(as.integer((i - 1) / length(samples) * 100), paste0("Preparing passthrough QC object: ", sname))
    obj <- read_sample_object(s)
    before_cells <- ncol(obj)
    out_rds <- file.path(output_dir, paste0(sname, "_qc.rds"))
    saveRDS(obj, out_rds)
    sample_stats[[i]] <- list(
      name = sname,
      cells_before = before_cells,
      cells_after = before_cells,
      cells_removed = 0,
      pct_removed = "0.0%",
      skipped = TRUE
    )
  }

  write_summary(list(
    status = "success",
    action = "skip_qc",
    skipped = TRUE,
    message = "QC was skipped. Downstream analyses will use unfiltered data.",
    sample_stats = sample_stats,
    figures = list(),
    tables = list()
  ), output_dir)
  report_progress(100, "QC skip completed")
}, error = function(e) {
  write_error_summary("QC Skip", conditionMessage(e), "Please check the original input files and sample settings before skipping QC.", output_dir)
  cat(sprintf("Error: %s\n", conditionMessage(e)))
  quit(status = 1)
})
