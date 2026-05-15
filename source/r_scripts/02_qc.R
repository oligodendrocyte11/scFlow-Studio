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
  library(patchwork)
  library(jsonlite)
  library(Matrix)
})

initial_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep('^--file=', initial_args, value = TRUE)
if (length(file_arg) > 0) {
  script_path <- sub('^--file=', '', file_arg[1])
  script_path <- gsub('~+~', ' ', script_path, fixed = TRUE)
  SCRIPT_DIR <- dirname(normalizePath(script_path))
} else {
  SCRIPT_DIR <- getwd()
}
source(file.path(SCRIPT_DIR, 'utils', 'io_utils.R'))
source(file.path(SCRIPT_DIR, 'utils', 'plot_utils.R'))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop('Usage: Rscript 02_qc.R <params.json>')

params <- read_params(args[1])
output_dir <- params$output_dir %||% '.'
ensure_dir(output_dir)

if (!is.null(params$color_scheme) && exists('set_color_scheme')) {
  try(set_color_scheme(as.character(params$color_scheme)), silent = TRUE)
}

set.seed(as.integer(params$seed %||% 1234))

min_ncount   <- as.numeric(params$min_ncount %||% 500)
max_ncount   <- as.numeric(params$max_ncount %||% 50000)
min_nfeature <- as.numeric(params$min_nfeature %||% 250)
max_nfeature <- as.numeric(params$max_nfeature %||% 5000)
max_mt       <- as.numeric(params$max_mt_percent %||% 5)
mt_pattern   <- as.character(params$mt_pattern %||% '^[mM][tT]-')
remove_mt    <- as.logical(params$remove_mt_genes %||% TRUE)
min_gene_umi <- as.numeric(params$min_gene_umi %||% 3)
regress_vars <- as.character(unlist(params$regress_vars %||% c('nCount_RNA', 'percent.mt')))

sample_param_num <- function(sample, key, default_value) {
  value <- sample$qc_params[[key]] %||% default_value
  as.numeric(value)
}

sample_param_chr <- function(sample, key, default_value) {
  value <- sample$qc_params[[key]] %||% default_value
  as.character(value)
}

sample_param_lgl <- function(sample, key, default_value) {
  value <- sample$qc_params[[key]] %||% default_value
  as.logical(value)
}

cat('QC parameters:\n')
cat(sprintf('  nCount:   [%d, %d]\n', min_ncount, max_ncount))
cat(sprintf('  nFeature: [%d, %d]\n', min_nfeature, max_nfeature))
cat(sprintf('  max MT:   %.1f%%\n', max_mt))
cat(sprintf('  MT regex: %s\n', mt_pattern))
cat(sprintf('  remove MT genes: %s\n', remove_mt))
cat(sprintf('  minimum gene UMI: %d\n', min_gene_umi))
cat(sprintf('  regress vars: %s\n', paste(regress_vars, collapse = ', ')))

samples <- safe_samples(params$samples)
n_samples <- length(samples)
if (n_samples == 0) stop('No samples found in params$samples')
cat(sprintf('Sample count: %d\n', n_samples))

qc_horizontal_records <- list()

for (i in seq_along(samples)) {
  s <- samples[[i]]
  if (is.null(s$name) || is.null(s$data_path)) {
    stop(sprintf('Sample #%d is missing required fields: name or data_path', i))
  }
}

force_v3 <- function() {
  old <- getOption('Seurat.object.assay.version')
  options(Seurat.object.assay.version = 'v3')
  old
}
restore_v3 <- function(old) {
  if (is.null(old)) {
    options(Seurat.object.assay.version = NULL)
  } else {
    options(Seurat.object.assay.version = old)
  }
}
old_ver <- force_v3()
on.exit(restore_v3(old_ver), add = TRUE)

get_counts_data <- function(obj) {
  tryCatch(
    GetAssayData(obj, assay = 'RNA', layer = 'counts'),
    error = function(e) GetAssayData(obj, assay = 'RNA', slot = 'counts')
  )
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
    if (grepl('\\.gz$', feature_path, ignore.case = TRUE)) {
      read.delim(gzfile(feature_path), header = FALSE, nrows = 5,
                 stringsAsFactors = FALSE, comment.char = '')
    } else {
      read.delim(feature_path, header = FALSE, nrows = 5,
                 stringsAsFactors = FALSE, comment.char = '')
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

detect_mt_pattern <- function(feature_names, preferred_pattern, species = '') {
  feature_names <- as.character(feature_names %||% character(0))
  if (!length(feature_names)) {
    return(as.character(preferred_pattern))
  }

  species <- tolower(trimws(as.character(species %||% '')))
  species_candidates <- switch(
    species,
    human = c('^MT-', '^[mM][tT]-', '^Mt-', '^mt-'),
    mouse = c('^[mM][tT]-', '^Mt-', '^mt-', '^MT-'),
    rat = c('^[mM][tT]-', '^Mt-', '^mt-', '^MT-'),
    c('^[mM][tT]-', '^MT-', '^Mt-', '^mt-')
  )

  candidate_patterns <- unique(c(
    as.character(preferred_pattern %||% ''),
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
      cat(sprintf('  Auto-detected MT regex: %s (species=%s, requested %s had %d matches)\n',
                  auto_pattern,
                  ifelse(nzchar(species), species, 'unknown'),
                  as.character(preferred_pattern),
                  ifelse(is.na(preferred_hits), 0, preferred_hits)))
    }
    return(auto_pattern)
  }

  as.character(preferred_pattern)
}

read_gz_or_plain_lines <- function(path, expected_n = NULL) {
  con <- if (grepl('\\.gz$', path, ignore.case = TRUE)) gzfile(path, open = 'rt') else file(path, open = 'rt')
  on.exit(close(con), add = TRUE)
  lines <- readLines(con, warn = FALSE)
  lines <- trimws(lines)
  lines <- lines[nzchar(lines)]
  if (!is.null(expected_n) && length(lines) != expected_n) {
    stop(sprintf('Expected %d lines in %s but found %d.', expected_n, basename(path), length(lines)))
  }
  lines
}

read_feature_names_flexible <- function(feature_path, expected_n, preferred_col = 2L) {
  con <- if (grepl('\\.gz$', feature_path, ignore.case = TRUE)) gzfile(feature_path, open = 'rt') else file(feature_path, open = 'rt')
  on.exit(close(con), add = TRUE)

  feature_names <- character(expected_n)
  idx <- 0L
  repeat {
    line <- readLines(con, n = 1, warn = FALSE)
    if (!length(line)) break
    idx <- idx + 1L
    parts <- strsplit(line, '\t', fixed = TRUE)[[1]]
    first_col <- if (length(parts) >= 1) trimws(parts[1]) else ''
    selected_col <- if (length(parts) >= preferred_col) trimws(parts[preferred_col]) else ''
    feature_name <- if (nzchar(selected_col)) selected_col else first_col
    if (!nzchar(feature_name)) {
      feature_name <- sprintf('feature_%d', idx)
    }
    if (idx > expected_n) {
      stop(sprintf('Feature file %s contains more than %d rows.', basename(feature_path), expected_n))
    }
    feature_names[idx] <- feature_name
  }

  if (idx != expected_n) {
    stop(sprintf('Matrix has %d rows but found %d features in %s.', expected_n, idx, basename(feature_path)))
  }

  if (anyDuplicated(feature_names)) {
    cat(sprintf('  Detected duplicated feature names in column %d; applying make.unique()...\n', preferred_col))
    feature_names <- make.unique(feature_names)
  }
  feature_names
}

read_10x_flexible <- function(data_path) {
  matrix_path <- find_matching_file(data_path, c('(^|.*_)matrix\\.mtx(\\.gz)?$'))
  barcode_path <- find_matching_file(data_path, c('(^|.*_)barcodes\\.tsv(\\.gz)?$'))
  feature_path <- find_matching_file(data_path, c('(^|.*_)features\\.tsv(\\.gz)?$', '(^|.*_)genes\\.tsv(\\.gz)?$'))

  if (is.null(matrix_path)) stop('Missing matrix.mtx(.gz) in 10X folder')
  if (is.null(barcode_path)) stop('Missing barcodes.tsv(.gz) in 10X folder')
  if (is.null(feature_path)) stop('Missing features.tsv(.gz) or genes.tsv(.gz) in 10X folder')

  cat(sprintf('  10X files: %s | %s | %s\n', basename(matrix_path), basename(barcode_path), basename(feature_path)))
  selected_feature_col <- feature_column_for_file(feature_path)
  cat(sprintf('  Feature column guess: %d\n', selected_feature_col))
  mtx_con <- if (grepl('\\.gz$', matrix_path, ignore.case = TRUE)) gzfile(matrix_path, open = 'rt') else file(matrix_path, open = 'rt')
  on.exit(close(mtx_con), add = TRUE)
  raw_data <- Matrix::readMM(mtx_con)
  raw_data <- as(raw_data, 'CsparseMatrix')

  barcode_names <- read_gz_or_plain_lines(barcode_path, expected_n = ncol(raw_data))
  feature_names <- tryCatch(
    read_feature_names_flexible(feature_path, expected_n = nrow(raw_data), preferred_col = selected_feature_col),
    error = function(e) {
      err_msg <- conditionMessage(e)
      should_retry_first_col <-
        selected_feature_col != 1L &&
        grepl('Matrix has .* rows but found .* features|duplicate|Duplicate|Feature file', err_msg, ignore.case = TRUE)
      if (!should_retry_first_col) {
        stop(e)
      }
      cat(sprintf('  Feature parsing failed with column %d: %s\n', selected_feature_col, err_msg))
      cat('  Retry feature parsing with column 1 for non-standard 10X features file...\n')
      read_feature_names_flexible(feature_path, expected_n = nrow(raw_data), preferred_col = 1L)
    }
  )

  colnames(raw_data) <- make.unique(barcode_names)
  rownames(raw_data) <- feature_names
  raw_data
}

read_expression_matrix_flexible <- function(data_path) {
  read_delimited_expression <- function(path, sep) {
    if (identical(sep, ",")) {
      read.csv(
        path,
        header = TRUE,
        check.names = FALSE,
        stringsAsFactors = FALSE
      )
    } else {
      read.delim(
        path,
        sep = sep,
        header = TRUE,
        check.names = FALSE,
        stringsAsFactors = FALSE
      )
    }
  }

  normalize_expression_df <- function(expr_df) {
    if (ncol(expr_df) < 2) {
      stop("Expression matrix must contain at least one gene column and one cell column.")
    }

    gene_names <- make.unique(as.character(expr_df[[1]]))
    gene_names[is.na(gene_names) | !nzchar(gene_names)] <- sprintf("gene_%d", seq_along(gene_names))[is.na(gene_names) | !nzchar(gene_names)]
    expr_df <- expr_df[, -1, drop = FALSE]

    if (ncol(expr_df) >= 1 && !is.numeric(expr_df[[1]])) {
      alt_names <- make.unique(as.character(expr_df[[1]]))
      valid_alt <- nzchar(alt_names) & !is.na(alt_names)
      if (any(valid_alt)) {
        gene_names[valid_alt] <- alt_names[valid_alt]
      }
      expr_df <- expr_df[, -1, drop = FALSE]
    }

    rownames(expr_df) <- gene_names
    expr_df
  }

  finalize_expression_df <- function(expr_df) {
    if (ncol(expr_df) == 0) {
      stop("Expression matrix has no numeric columns after parsing.")
    }

    original_df <- expr_df
    numeric_mask <- vapply(expr_df, function(col) {
      suppressWarnings(parsed <- as.numeric(as.character(col)))
      all(!is.na(parsed))
    }, logical(1))

    if (!any(numeric_mask)) {
      stop("No numeric expression columns were detected in the matrix file.")
    }

    if (!all(numeric_mask)) {
      expr_df <- expr_df[, numeric_mask, drop = FALSE]
    }

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

  con <- if (grepl('\\.gz$', data_path, ignore.case = TRUE)) gzfile(data_path, open = 'rt') else file(data_path, open = 'rt')
  first_line <- readLines(con, n = 1, warn = FALSE)
  close(con)
  first_line <- trimws(first_line)

  if (grepl('\t', first_line, fixed = TRUE)) {
    expr_df <- read_delimited_expression(data_path, "\t")
    expr_df <- normalize_expression_df(expr_df)
    return(maybe_transpose_cell_by_gene(expr_df))
  }

  if (grepl(',', first_line, fixed = TRUE)) {
    expr_df <- read_delimited_expression(data_path, ",")
    expr_df <- normalize_expression_df(expr_df)
    return(maybe_transpose_cell_by_gene(expr_df))
  }

  expr_df <- read.table(data_path, header = TRUE, sep = '', quote = '"',
                        check.names = FALSE, stringsAsFactors = FALSE, comment.char = '')

  if ('barcode' %in% colnames(expr_df)) {
    barcode_ids <- make.unique(as.character(expr_df$barcode))
    drop_cols <- intersect(c('barcode', 'final_cluster_labels', 'library'), colnames(expr_df))
    gene_df <- expr_df[, setdiff(colnames(expr_df), drop_cols), drop = FALSE]
    gene_matrix <- t(data.matrix(gene_df))
    colnames(gene_matrix) <- barcode_ids
    return(as(gene_matrix, 'CsparseMatrix'))
  }

  if (ncol(expr_df) >= 2) {
    rownames(expr_df) <- make.unique(as.character(expr_df[[1]]))
    expr_df <- expr_df[, -1, drop = FALSE]
  }
  finalize_expression_df(expr_df)
}

read_sparse_bundle_sample <- function(data_path, library_identity, sample_name) {
  library_identity <- trimws(as.character(library_identity %||% ''))
  if (!nzchar(library_identity)) {
    stop(sprintf('Sample %s is missing library_identity for sparse bundle import', sample_name))
  }

  matrix_path <- find_matching_file(data_path, c('rawcounts.*sparse\\.mtx\\.gz$', '\\.mtx\\.gz$'))
  barcode_path <- find_matching_file(data_path, c('allcells.*cellbarcodes.*\\.txt\\.gz$', 'cellbarcodes.*\\.txt\\.gz$'))
  feature_path <- find_matching_file(data_path, c('allcells.*geneids.*\\.txt\\.gz$', 'geneids.*\\.txt\\.gz$'))

  if (is.null(matrix_path)) stop('Sparse bundle is missing RawCounts sparse matrix')
  if (is.null(barcode_path)) stop('Sparse bundle is missing cell barcodes file')
  if (is.null(feature_path)) stop('Sparse bundle is missing gene IDs file')

  cat(sprintf('  Sparse bundle files: %s | %s | %s\n',
              basename(matrix_path), basename(barcode_path), basename(feature_path)))

  barcodes <- readLines(gzfile(barcode_path), warn = FALSE)
  keep_idx <- startsWith(barcodes, paste0(library_identity, '_'))
  if (!any(keep_idx)) {
    stop(sprintf('No barcodes found for library %s', library_identity))
  }
  selected_barcodes <- barcodes[keep_idx]
  selected_cols <- which(keep_idx)
  col_map <- integer(length(barcodes))
  col_map[selected_cols] <- seq_along(selected_cols)
  cat(sprintf('  Sparse bundle subset: %s -> %d cells\n', library_identity, length(selected_barcodes)))

  feature_df <- read.delim(gzfile(feature_path), header = TRUE, stringsAsFactors = FALSE, check.names = FALSE)
  if (ncol(feature_df) >= 2) {
    feature_ids <- as.character(feature_df[[1]])
    feature_names <- as.character(feature_df[[2]])
  } else {
    feature_ids <- as.character(feature_df[[1]])
    feature_names <- feature_ids
  }
  feature_names[is.na(feature_names) | !nzchar(feature_names)] <- feature_ids[is.na(feature_names) | !nzchar(feature_names)]
  feature_names <- make.unique(feature_names)

  chunk_size <- 500000L
  i_chunks <- list()
  j_chunks <- list()
  x_chunks <- list()
  current_i <- integer(chunk_size)
  current_j <- integer(chunk_size)
  current_x <- numeric(chunk_size)
  fill <- 0L

  flush_chunk <- function() {
    if (fill <= 0L) return()
    i_chunks[[length(i_chunks) + 1L]] <<- current_i[seq_len(fill)]
    j_chunks[[length(j_chunks) + 1L]] <<- current_j[seq_len(fill)]
    x_chunks[[length(x_chunks) + 1L]] <<- current_x[seq_len(fill)]
    fill <<- 0L
  }

  con <- gzfile(matrix_path, open = 'rt')
  on.exit(close(con), add = TRUE)
  header_read <- FALSE
  n_genes <- length(feature_names)
  line_count <- 0L
  repeat {
    lines <- readLines(con, n = 50000L, warn = FALSE)
    if (!length(lines)) break
    for (line in lines) {
      text <- trimws(line)
 if (!nzchar() || startsWith(, '%')) next
      if (!header_read) {
        parts <- strsplit(text, '\\s+')[[1]]
        if (length(parts) >= 2) {
          suppressWarnings({
            n_genes <- as.integer(parts[1])
          })
        }
        header_read <- TRUE
        next
      }
      parts <- strsplit(text, '\\s+')[[1]]
      if (length(parts) < 3) next
      col_idx <- suppressWarnings(as.integer(parts[2]))
      if (is.na(col_idx) || col_idx < 1L || col_idx > length(col_map)) next
      new_col <- col_map[col_idx]
      if (new_col <= 0L) next
      fill <- fill + 1L
      current_i[fill] <- as.integer(parts[1])
      current_j[fill] <- new_col
      current_x[fill] <- as.numeric(parts[3])
      if (fill >= chunk_size) flush_chunk()
    }
    line_count <- line_count + length(lines)
    if (line_count %% 500000L == 0L) {
      cat(sprintf('  Sparse bundle parsing: ~%d matrix lines scanned\n', line_count))
    }
  }
  flush_chunk()

  if (!length(i_chunks)) {
    stop(sprintf('Sparse bundle subset %s produced an empty matrix', library_identity))
  }

  i_idx <- do.call(c, i_chunks)
  j_idx <- do.call(c, j_chunks)
  x_val <- do.call(c, x_chunks)

  sparseMatrix(
    i = i_idx,
    j = j_idx,
    x = x_val,
    dims = c(n_genes, length(selected_barcodes)),
    dimnames = list(feature_names, selected_barcodes)
  )
}

subset_by_barcode_suffix <- function(raw_data, split_suffix, sample_name) {
  split_suffix <- trimws(as.character(split_suffix %||% ''))
  if (!nzchar(split_suffix)) return(raw_data)

  barcode_names <- colnames(raw_data)
  if (is.null(barcode_names) || length(barcode_names) == 0) {
    stop(sprintf('Sample %s is missing barcode column names; cannot split by suffix', sample_name))
  }

  suffix_value <- gsub('^[-_]', '', split_suffix)
  keep_idx <- grepl(paste0('[_-]', suffix_value, '$'), barcode_names)
  if (!any(keep_idx)) {
    stop(sprintf('Sample %s has no barcodes matching suffix %s', sample_name, suffix_value))
  }
  raw_data[, keep_idx, drop = FALSE]
}

wrap_sample_label <- function(label, target_width = 18, max_lines = 3) {
  label <- as.character(label %||% '')
  if (!nzchar(label)) return(label)
  parts <- unlist(strsplit(label, '_', fixed = TRUE), use.names = FALSE)
  if (length(parts) <= 1) {
    parts <- unlist(strsplit(label, '-', fixed = TRUE), use.names = FALSE)
  }
  if (length(parts) <= 1) return(label)

  lines <- character(0)
  current <- ''
  for (part in parts) {
    candidate <- if (!nzchar(current)) part else paste(current, part, sep = '_')
    if (nchar(candidate) <= target_width) {
      current <- candidate
    } else {
      if (nzchar(current)) lines <- c(lines, current)
      current <- part
    }
  }
  if (nzchar(current)) lines <- c(lines, current)

  if (length(lines) > max_lines) {
    tail_text <- paste(lines[max_lines:length(lines)], collapse = '_')
 lines <- c(lines[seq_len(max_lines - 1)], tail_)
  }
  paste(lines, collapse = '\n')
}

prefilter_large_sparse_matrix <- function(raw_data, min_gene_umi, sample_name) {
  original_genes <- nrow(raw_data)
  if (original_genes == 0) {
    return(raw_data)
  }

  gene_totals <- Matrix::rowSums(raw_data)
  keep_nonzero <- gene_totals > 0
  if (sum(keep_nonzero) < original_genes) {
    cat(sprintf('  Prefilter zero-count features: %d -> %d\n', original_genes, sum(keep_nonzero)))
    raw_data <- raw_data[keep_nonzero, , drop = FALSE]
    gene_totals <- gene_totals[keep_nonzero]
  }

  if (nrow(raw_data) > 500000) {
    keep_sparse <- gene_totals >= min_gene_umi
    kept_n <- sum(keep_sparse)
    if (kept_n > 0 && kept_n < nrow(raw_data)) {
      cat(sprintf(
        '  Ultra-large matrix detected for %s; prefilter features by total UMI >= %d: %d -> %d\n',
        sample_name, min_gene_umi, nrow(raw_data), kept_n
      ))
      raw_data <- raw_data[keep_sparse, , drop = FALSE]
    }
  }

  raw_data
}

sample_stats <- list()
all_figures <- c()

tryCatch({
  for (i in seq_along(samples)) {
    s <- samples[[i]]
    sname <- as.character(s$name)
    data_path <- as.character(s$data_path)
    data_type <- as.character(s$data_type %||% '10X Matrix Folder')
    library_identity <- as.character(s$library_identity %||% '')
    split_suffix <- as.character(s$split_suffix %||% '')
    sample_min_ncount <- sample_param_num(s, 'min_ncount', min_ncount)
    sample_max_ncount <- sample_param_num(s, 'max_ncount', max_ncount)
    sample_min_nfeature <- sample_param_num(s, 'min_nfeature', min_nfeature)
    sample_max_nfeature <- sample_param_num(s, 'max_nfeature', max_nfeature)
    sample_max_mt <- sample_param_num(s, 'max_mt_percent', max_mt)
    sample_mt_pattern <- sample_param_chr(s, 'mt_pattern', mt_pattern)
    sample_species <- as.character(s$species %||% '')
    sample_remove_mt <- sample_param_lgl(s, 'remove_mt_genes', remove_mt)

    report_progress(as.integer((i - 1) / n_samples * 100), paste0('Processing: ', sname))
    cat(sprintf('\n=== Sample: %s ===\n', sname))
    cat(sprintf('  Sample-specific QC params: nCount [%d, %d], nFeature [%d, %d], max MT %.1f%%, mt_pattern=%s, remove_mt=%s\n',
                sample_min_ncount, sample_max_ncount,
                sample_min_nfeature, sample_max_nfeature,
                sample_max_mt, sample_mt_pattern, sample_remove_mt))

    if (data_type == 'Seurat RDS') {
      if (!file.exists(data_path)) stop(sprintf('Sample %s file does not exist: %s', sname, data_path))
    } else if (data_type == 'Sparse Bundle Folder') {
      if (!dir.exists(data_path)) stop(sprintf('Sample %s folder does not exist: %s', sname, data_path))
    } else if (startsWith(data_type, 'Expression Matrix')) {
      if (!file.exists(data_path)) stop(sprintf('Sample %s file does not exist: %s', sname, data_path))
    } else {
      if (!dir.exists(data_path)) stop(sprintf('Sample %s folder does not exist: %s', sname, data_path))
    }

    cat(sprintf('  Reading data (%s)...\n', data_type))
    if (data_type == 'Seurat RDS') {
      obj_raw <- readRDS(data_path)
      if (!inherits(obj_raw, 'Seurat')) stop(sprintf('Sample %s .rds is not a Seurat object', sname))
      if (!'RNA' %in% Assays(obj_raw)) stop(sprintf('Sample %s Seurat object is missing RNA assay', sname))
      raw_data <- get_counts_data(obj_raw)
      if (is.list(raw_data) && !inherits(raw_data, 'dgCMatrix')) raw_data <- raw_data[[1]]
    } else if (data_type == 'Sparse Bundle Folder') {
      raw_data <- read_sparse_bundle_sample(data_path, library_identity, sname)
    } else if (startsWith(data_type, 'Expression Matrix')) {
      raw_data <- read_expression_matrix_flexible(data_path)
    } else {
      raw_data <- read_10x_flexible(data_path)
    }

            raw_data <- subset_by_barcode_suffix(raw_data, split_suffix, sname)
            raw_data <- prefilter_large_sparse_matrix(raw_data, min_gene_umi, sname)
            rownames(raw_data) <- gsub('_', '-', rownames(raw_data))
            cat('  Gene names normalized (_ -> -)\n')

    obj <- CreateSeuratObject(counts = raw_data, project = sname, min.cells = 3, min.features = 50)
    if (inherits(obj[['RNA']], 'Assay5')) {
      obj[['RNA']] <- as(object = obj[['RNA']], Class = 'Assay')
      cat('  [v5->v3] RNA Assay converted to v3 format\n')
    }
    obj$sample <- sname
    obj$group <- s$group %||% sname
    qc_label <- wrap_sample_label(sname, target_width = 18, max_lines = 3)
    obj$qc_identity <- qc_label
    Idents(obj) <- 'qc_identity'
    cat(sprintf('  Raw: %d cells, %d genes\n', ncol(obj), nrow(obj)))

    effective_mt_pattern <- detect_mt_pattern(rownames(obj), sample_mt_pattern, sample_species)
    mt_genes_found <- grep(effective_mt_pattern, rownames(obj), value = TRUE)
    cat(sprintf('  Mitochondrial genes (%s): %d\n', effective_mt_pattern, length(mt_genes_found)))
    obj[['percent.mt']] <- PercentageFeatureSet(obj, pattern = effective_mt_pattern)
    cells_before <- ncol(obj)

    qc_horizontal_records[[length(qc_horizontal_records) + 1]] <- data.frame(
      sample = rep(sname, ncol(obj)),
      nCount_RNA = obj$nCount_RNA,
      nFeature_RNA = obj$nFeature_RNA,
      percent.mt = obj$percent.mt,
      stringsAsFactors = FALSE
    )

    cat('  Generating QC plots...\n')
    p_vln_list <- VlnPlot(
      obj,
      features = c('nFeature_RNA', 'nCount_RNA', 'percent.mt'),
      ncol = 3,
      cols = sc_colors[1],
      combine = FALSE
    )
    p_vln_list <- lapply(p_vln_list, function(p) {
      p + sc_theme +
        theme(axis.text.x = element_text(size = 9, lineheight = 0.9))
    })
    p_vln <- patchwork::wrap_plots(p_vln_list, ncol = 3, guides = 'collect') &
      theme(
        legend.position = 'right',
        legend.title = element_text(size = 10, face = 'bold'),
        legend.text = element_text(size = 9, lineheight = 0.9),
        legend.key.size = unit(10, 'pt')
      )
    fig <- save_plot(p_vln, paste0(sname, '_qc_violin'), output_dir, width = 13.5, height = 5)
    all_figures <- c(all_figures, basename(fig))

    p1 <- FeatureScatter(obj, feature1 = 'nCount_RNA', feature2 = 'nFeature_RNA', cols = sc_colors[1]) +
      sc_theme +
      geom_hline(yintercept = c(sample_min_nfeature, sample_max_nfeature), linetype = 'dashed', color = 'red', linewidth = 0.5)

    p2 <- FeatureScatter(obj, feature1 = 'nCount_RNA', feature2 = 'percent.mt', cols = sc_colors[1]) +
      sc_theme +
      geom_hline(yintercept = sample_max_mt, linetype = 'dashed', color = 'red', linewidth = 0.5)

    p_scatter <- patchwork::wrap_plots(list(p1, p2), ncol = 2, guides = 'collect') &
      theme(
        legend.position = 'right',
        legend.title = element_text(size = 10, face = 'bold'),
        legend.text = element_text(size = 9, lineheight = 0.9),
        legend.key.size = unit(10, 'pt')
      )
    fig <- save_plot(p_scatter, paste0(sname, '_qc_scatter'), output_dir, width = 13.5, height = 5)
    all_figures <- c(all_figures, basename(fig))

    cat(sprintf('  Filtering: nFeature [%d,%d], nCount [%d,%d], MT < %.1f%%\n',
                sample_min_nfeature, sample_max_nfeature, sample_min_ncount, sample_max_ncount, sample_max_mt))
    obj <- subset(
      obj,
      subset = nFeature_RNA > sample_min_nfeature &
        nFeature_RNA < sample_max_nfeature &
        nCount_RNA > sample_min_ncount &
        nCount_RNA < sample_max_ncount &
        percent.mt < sample_max_mt
    )
    cat(sprintf('  Cells after filtering: %d\n', ncol(obj)))

    counts_qc <- get_counts_data(obj)
    gene_totals <- Matrix::rowSums(counts_qc)
    keep_genes <- names(gene_totals[gene_totals >= min_gene_umi])
    cat(sprintf('  Gene filtering (total UMI >= %d): %d -> %d\n',
                min_gene_umi, nrow(obj), length(keep_genes)))

    if (sample_remove_mt) {
      mito_genes <- grep(effective_mt_pattern, keep_genes, value = TRUE)
      keep_genes <- setdiff(keep_genes, mito_genes)
      cat(sprintf('  Removed %d mitochondrial genes\n', length(mito_genes)))
    }

    obj <- subset(obj, features = keep_genes)

    cells_after <- ncol(obj)
    cells_removed <- cells_before - cells_after
    pct_removed <- sprintf('%.1f%%', cells_removed / max(cells_before, 1) * 100)
    cat(sprintf('  Final: %d cells, %d genes (removed %d, %s)\n',
                ncol(obj), nrow(obj), cells_removed, pct_removed))

    sample_stats[[i]] <- list(
      name = sname,
      cells_before = cells_before,
      cells_after = cells_after,
      genes_after = nrow(obj),
      pct_removed = pct_removed,
      figures = list(
        paste0(sname, '_qc_violin.png'),
        paste0(sname, '_qc_scatter.png')
      )
    )

    rds_path <- file.path(output_dir, paste0(sname, '_qc.rds'))
    saveRDS(obj, rds_path)
    cat(sprintf('  Saved: %s\n', rds_path))

    report_progress(as.integer(i / n_samples * 100), paste0('Completed: ', sname))
  }

  if (length(qc_horizontal_records) > 0) {
    qc_df <- do.call(rbind, qc_horizontal_records)
    long_df <- rbind(
      data.frame(sample = qc_df$sample, metric = 'nCount_RNA', value = qc_df$nCount_RNA, stringsAsFactors = FALSE),
      data.frame(sample = qc_df$sample, metric = 'nFeature_RNA', value = qc_df$nFeature_RNA, stringsAsFactors = FALSE),
      data.frame(sample = qc_df$sample, metric = 'percent.mt', value = qc_df$percent.mt, stringsAsFactors = FALSE)
    )
    sample_levels <- unique(qc_df$sample)
    long_df$sample <- factor(long_df$sample, levels = rev(sample_levels))
    long_df$metric <- factor(long_df$metric, levels = c('nCount_RNA', 'nFeature_RNA', 'percent.mt'))

    p_vln_horizontal <- ggplot(long_df, aes(x = sample, y = value, fill = sample)) +
      geom_violin(scale = 'width', trim = TRUE, linewidth = 0.25, show.legend = FALSE) +
      coord_flip() +
      facet_wrap(~ metric, scales = 'free_x', ncol = 1) +
      labs(x = NULL, y = NULL, title = 'QC Horizontal Violin Plot') +
      sc_theme +
      theme(
        strip.text = element_text(face = 'bold'),
        panel.spacing = unit(0.6, 'lines')
      )
    fig <- save_plot(
      p_vln_horizontal,
      'qc_violin_horizontal',
      output_dir,
      width = max(10, 4 + length(sample_levels) * 0.35),
      height = 8
    )
    all_figures <- c(all_figures, basename(fig))
  }

  write_summary(list(
    status = 'success',
    n_samples = n_samples,
    sample_stats = sample_stats,
    figures = as.list(all_figures),
    tables = list()
  ), output_dir)

  cat('\n=== QC completed successfully ===\n')
}, error = function(e) {
  err_msg <- conditionMessage(e)
  cat(sprintf('\nError: %s\n', err_msg))
  suggestion <- 'Please verify input files, sample paths, and QC parameters before rerunning.'
  if (grepl('cannot open|missing', err_msg, ignore.case = TRUE)) {
    suggestion <- 'Please confirm the sample folder contains valid 10X files or a readable expression matrix.'
  }
  write_error_summary('QC', err_msg, suggestion, output_dir)
  quit(status = 1)
})
