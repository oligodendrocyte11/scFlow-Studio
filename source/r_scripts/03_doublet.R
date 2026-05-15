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

cat(sprintf('Seurat version: %s\n', as.character(packageVersion('Seurat'))))

old_assay_ver <- getOption('Seurat.object.assay.version')
options(Seurat.object.assay.version = 'v3')
on.exit({ options(Seurat.object.assay.version = old_assay_ver) }, add = TRUE)
cat('[global] assay.version = v3\n')

flatten_df_columns <- function(df) {
  for (cn in colnames(df)) {
    col <- df[[cn]]
    if (is.data.frame(col)) {
      df[[cn]] <- as.vector(col[[1]])
    } else if (is.list(col)) {
      df[[cn]] <- unlist(col)
    } else if (is.factor(col)) {
      df[[cn]] <- as.character(col)
    }
  }
  df
}

manual_find_pK <- function(sweep.stats) {
  cat('  [fallback] calculating BCmetric manually...\n')
  sweep.stats$pK <- as.numeric(as.character(sweep.stats$pK))
  bc_col <- NULL
  for (cand in c('BCmetric', 'BCmvn', 'BCreal')) {
    if (cand %in% colnames(sweep.stats)) {
      bc_col <- cand
      break
    }
  }
  if (is.null(bc_col)) {
    numeric_cols <- setdiff(names(which(sapply(sweep.stats, is.numeric))), c('pN', 'pK'))
    if (length(numeric_cols) > 0) {
      bc_col <- numeric_cols[length(numeric_cols)]
    }
  }
  if (is.null(bc_col)) {
    stop('No numeric BCmetric-like column was found in sweep.stats.')
  }
  sweep.stats[[bc_col]] <- as.numeric(as.character(sweep.stats[[bc_col]]))
  unique_pK <- sort(unique(sweep.stats$pK))
  bc_mean <- sapply(unique_pK, function(pk) mean(sweep.stats[[bc_col]][sweep.stats$pK == pk], na.rm = TRUE))
  bc_var <- sapply(unique_pK, function(pk) var(sweep.stats[[bc_col]][sweep.stats$pK == pk], na.rm = TRUE))
  bc_var[is.na(bc_var) | bc_var == 0] <- 1e-10
  data.frame(pK = unique_pK, BCmetric = bc_mean / bc_var, stringsAsFactors = FALSE)
}

rebuild_as_v3 <- function(obj_old) {
  cat('  [rebuild] rebuilding a clean v3 object from counts...\n')
  counts_mat <- tryCatch(
    GetAssayData(obj_old, layer = 'counts'),
    error = function(e) obj_old[['RNA']]$counts
  )
  meta_old <- obj_old@meta.data
  obj_new <- CreateSeuratObject(
    counts = counts_mat,
    project = obj_old@project.name,
    meta.data = meta_old
  )
  cat(sprintf('  [rebuild] done: %d cells, %d genes, RNA class = %s\n',
              ncol(obj_new), nrow(obj_new), class(obj_new[['RNA']])[1]))
  obj_new
}

sample_param_num <- function(sample, key, default_value) {
  value <- sample$doublet_params[[key]] %||% default_value
  as.numeric(value)
}

sample_param_chr <- function(sample, key, default_value) {
  value <- sample$doublet_params[[key]] %||% default_value
  as.character(value)
}

sample_param_lgl <- function(sample, key, default_value) {
  value <- sample$doublet_params[[key]] %||% default_value
  as.logical(value)
}

parse_pcs_value <- function(pcs_raw) {
  if (is.null(pcs_raw)) {
    return(1:30)
  }
  if (is.character(pcs_raw)) {
    pcs_range <- eval(parse(text = pcs_raw))
  } else if (is.list(pcs_raw)) {
    pcs_range <- as.integer(unlist(pcs_raw))
  } else {
    pcs_range <- as.integer(pcs_raw)
  }
  as.integer(pcs_range)
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop('Usage: Rscript 03_doublet.R <params.json>')
}

params <- read_params(args[1])
output_dir <- params$output_dir %||% '.'
ensure_dir(output_dir)

samples <- safe_samples(params$samples)
n_samples <- length(samples)

if (!requireNamespace('DoubletFinder', quietly = TRUE)) {
  cat('Warning: DoubletFinder is not installed; skipping doublet removal.\n')
  for (sample in samples) {
    out_rds <- file.path(output_dir, paste0(sample$name, '_singlet.rds'))
    if (!is.null(sample$qc_rds) && file.exists(sample$qc_rds)) {
      file.copy(sample$qc_rds, out_rds, overwrite = TRUE)
    }
  }
  write_summary(list(
    status = 'success',
    message = 'DoubletFinder not installed, doublet removal skipped.',
    sample_stats = list(),
    figures = list()
  ), output_dir)
  quit(status = 0)
}

library(DoubletFinder)
cat(sprintf('DoubletFinder version: %s\n', as.character(packageVersion('DoubletFinder'))))

set.seed(as.integer(params$seed %||% 1234))

default_expected_rate <- as.numeric(params$expected_doublet_rate %||% 0.06)
default_pN <- as.numeric(params$pN %||% 0.25)
default_resolution <- as.numeric(params$resolution %||% 0.5)
default_auto_pk <- as.logical(params$auto_pk %||% TRUE)
default_pcs_raw <- params$pcs %||% '1:30'
default_pcs_range <- parse_pcs_value(default_pcs_raw)

cat(sprintf('\nDefault parameters: rate=%.3f, PCs=%s, pN=%.2f, resolution=%.2f\n',
            default_expected_rate,
            paste(range(default_pcs_range), collapse = ':'),
            default_pN,
            default_resolution))

sample_stats <- list()
all_figures <- c()

tryCatch({
  for (i in seq_along(samples)) {
    sample_item <- samples[[i]]
    sample_name <- as.character(sample_item$name)
    qc_rds <- sample_item$qc_rds

    sample_expected_rate <- sample_param_num(sample_item, 'expected_doublet_rate', default_expected_rate)
    sample_pN <- sample_param_num(sample_item, 'pN', default_pN)
    sample_resolution <- sample_param_num(sample_item, 'resolution', default_resolution)
    sample_auto_pk <- sample_param_lgl(sample_item, 'auto_pk', default_auto_pk)
    sample_pcs_raw <- sample_param_chr(sample_item, 'pcs', default_pcs_raw)
    sample_pcs_range <- parse_pcs_value(sample_pcs_raw)

    report_progress(as.integer((i - 1) / n_samples * 100), paste0('Doublet removal: ', sample_name))
    cat(sprintf('\n=== Sample %d/%d: %s ===\n', i, n_samples, sample_name))
    cat(sprintf('  Sample-specific doublet params: rate=%.3f, PCs=%s, pN=%.2f, resolution=%.2f, auto_pk=%s\n',
                sample_expected_rate,
                paste(range(sample_pcs_range), collapse = ':'),
                sample_pN,
                sample_resolution,
                sample_auto_pk))

    if (is.null(qc_rds) || !file.exists(qc_rds)) {
      cat(sprintf('  Skip: QC file not found: %s\n', qc_rds %||% '(NULL)'))
      next
    }

    obj_old <- readRDS(qc_rds)
    cells_before <- ncol(obj_old)
    cat(sprintf('  Loaded: %d cells, RNA class = %s\n', cells_before, class(obj_old[['RNA']])[1]))

    obj <- rebuild_as_v3(obj_old)
    rm(obj_old)
    gc(verbose = FALSE)

    cat('  [1/6] preprocessing...\n')
    obj <- NormalizeData(obj, verbose = FALSE)
    obj <- FindVariableFeatures(obj, selection.method = 'vst', nfeatures = 2000, verbose = FALSE)
    obj <- ScaleData(obj, vars.to.regress = c('nCount_RNA', 'percent.mt'), verbose = FALSE)
    obj <- RunPCA(obj, features = VariableFeatures(obj), verbose = FALSE)
    obj <- RunUMAP(obj, dims = sample_pcs_range, umap.method = "uwot", metric = "cosine", verbose = FALSE)
    obj <- FindNeighbors(obj, dims = sample_pcs_range, verbose = FALSE)
    obj <- safe_find_clusters(obj, resolution = sample_resolution, random_seed = as.integer(params$seed %||% 1234), verbose = FALSE)

    cat('  [2/6] paramSweep...\n')
    sweep.res <- paramSweep(obj, PCs = sample_pcs_range, sct = FALSE)

    cat('  [3/6] summarizeSweep...\n')
    sweep.stats <- summarizeSweep(sweep.res, GT = FALSE)
    sweep.stats <- flatten_df_columns(sweep.stats)

    cat('  [4/6] selecting best pK...\n')
    bcmvn <- tryCatch({
      result <- find.pK(sweep.stats)
      result <- flatten_df_columns(result)
      if (!'BCmetric' %in% colnames(result)) {
        manual_find_pK(sweep.stats)
      } else {
        result
      }
    }, error = function(e) {
      cat(sprintf('  find.pK failed (%s), using fallback.\n', conditionMessage(e)))
      manual_find_pK(sweep.stats)
    })

    pk_vec <- as.numeric(as.character(bcmvn[['pK']]))
    bcmetric_vec <- as.numeric(as.character(bcmvn[['BCmetric']]))
    if (all(is.na(bcmetric_vec))) {
      stop(paste0('BCmetric is all NA for sample: ', sample_name))
    }

    if (sample_auto_pk) {
      best_idx <- which.max(bcmetric_vec)
      best_pk <- pk_vec[best_idx]
    } else {
      best_pk <- 0.09
      best_idx <- which.min(abs(pk_vec - best_pk))
    }
    cat(sprintf('  Best pK=%.4f (BCmetric=%.2f)\n', best_pk, bcmetric_vec[best_idx]))

    plot_df <- data.frame(pK = pk_vec, BCmetric = bcmetric_vec)
    p_pk <- ggplot(plot_df, aes(x = pK, y = BCmetric)) +
      geom_line(linewidth = 0.8) +
      geom_point(size = 2) +
      geom_vline(xintercept = best_pk, linetype = 'dashed', color = 'red') +
      labs(title = paste0(sample_name, ' - pK=', round(best_pk, 4))) +
      sc_theme
    fig <- save_plot(p_pk, paste0(sample_name, '_pk_sweep'), output_dir)
    all_figures <- c(all_figures, basename(fig))

    cat('  [5/6] DoubletFinder...\n')
    homotypic.prop <- modelHomotypic(obj$seurat_clusters)
    nExp_poi <- round(sample_expected_rate * ncol(obj))
    nExp_poi.adj <- round(nExp_poi * (1 - homotypic.prop))
    cat(sprintf('  Expected doublets: raw=%d, adjusted=%d\n', nExp_poi, nExp_poi.adj))

    obj <- doubletFinder(
      obj,
      PCs = sample_pcs_range,
      pN = sample_pN,
      pK = best_pk,
      nExp = nExp_poi.adj,
      reuse.pANN = NULL,
      sct = FALSE
    )

    df_col <- grep('DF.classifications', colnames(obj@meta.data), value = TRUE)
    if (length(df_col) == 0) {
      stop('DoubletFinder did not generate a classification column.')
    }
    df_col <- df_col[length(df_col)]

    cls_table <- table(obj@meta.data[[df_col]])
    cat(sprintf('  Classification summary: %s\n',
                paste(names(cls_table), cls_table, sep = '=', collapse = ', ')))

    cat('  [6/6] filtering doublets...\n')
    p_umap <- DimPlot(obj, group.by = df_col,
                      cols = c('Singlet' = '#4CAF50', 'Doublet' = '#F44336')) +
      labs(title = paste0(sample_name, ' - Singlet vs Doublet')) +
      sc_theme
    fig <- save_plot(p_umap, paste0(sample_name, '_doublet_umap'), output_dir)
    all_figures <- c(all_figures, basename(fig))

    singlet_cells <- rownames(obj@meta.data)[obj@meta.data[[df_col]] == 'Singlet']
    obj <- subset(obj, cells = singlet_cells)
    cells_after <- ncol(obj)
    n_doublet <- cells_before - cells_after

    cat(sprintf('  Final: %d -> %d (removed %d, %.1f%%)\n',
                cells_before, cells_after, n_doublet,
                n_doublet / max(cells_before, 1) * 100))

    sample_stats[[i]] <- list(
      name = sample_name,
      before = cells_before,
      after = cells_after,
      doublets = n_doublet,
      doublet_rate = sprintf('%.1f%%', n_doublet / max(cells_before, 1) * 100),
      best_pk = best_pk
    )

    rds_path <- file.path(output_dir, paste0(sample_name, '_singlet.rds'))
    saveRDS(obj, rds_path)
    cat(sprintf('  Saved: %s\n', rds_path))

    report_progress(as.integer(i / n_samples * 100), paste0('Completed: ', sample_name))
  }

  write_summary(list(
    status = 'success',
    sample_stats = sample_stats,
    figures = as.list(all_figures),
    tables = list()
  ), output_dir)
  cat('\n=== Doublet removal completed successfully ===\n')
}, error = function(e) {
  err_msg <- conditionMessage(e)
  cat(sprintf('\nError: %s\n', err_msg))
  suggestion <- 'Please verify DoubletFinder installation, QC input files, and per-sample parameters.'
  if (grepl('xtfrm|sort|order', err_msg)) {
    suggestion <- paste0(
      'Seurat v5 object compatibility issue was detected.\n',
      'Suggested fix: remotes::install_github("chris-mcginnis-ucsf/DoubletFinder")'
    )
  }
  write_error_summary('Doublet removal', err_msg, suggestion, output_dir)
  quit(status = 1)
})