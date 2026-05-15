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
  library(Matrix)
})

if (.Platform$OS.type == "windows") {
  tryCatch(Sys.setlocale("LC_ALL", "English_United States.1252"), error = function(e) {})
}

initial_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", initial_args, value = TRUE)
if (length(file_arg) > 0) {
  SCRIPT_DIR <- dirname(normalizePath(sub("^--file=", "", file_arg[1])))
} else {
  SCRIPT_DIR <- getwd()
}
source(file.path(SCRIPT_DIR, "utils", "io_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
params <- read_params(args[1])
output_dir <- params$output_dir
input_rds <- params$input_rds
sub_rds <- params$sub_rds %||% ""
merge_sub <- as.logical(params$merge_subcluster %||% FALSE)

ensure_dir(output_dir)

old_ver <- getOption("Seurat.object.assay.version")
options(Seurat.object.assay.version = "v3")
on.exit({ options(Seurat.object.assay.version = old_ver) }, add = TRUE)

cat(sprintf("Exporting intermediate files\n  Input: %s\n", input_rds))
if (merge_sub && nchar(sub_rds) > 0) {
  cat(sprintf("  Subcluster object: %s\n", sub_rds))
}

extract_export_matrix <- function(seu_obj) {
  assay_names <- names(seu_obj@assays)
  if (!"RNA" %in% assay_names) {
 stop("The object does not contain an RNA assay; unable to export the matrix.")
  }

  try_get <- function(assay_name, layer_name = NULL, slot_name = NULL) {
    if (!is.null(layer_name)) {
      tryCatch(GetAssayData(seu_obj, assay = assay_name, layer = layer_name), error = function(e) NULL)
    } else {
      tryCatch(GetAssayData(seu_obj, assay = assay_name, slot = slot_name), error = function(e) NULL)
    }
  }

  mat <- try_get("RNA", layer_name = "counts")
  source_layer <- "RNA/counts(layer)"
  if (is.null(mat)) {
    mat <- try_get("RNA", slot_name = "counts")
    source_layer <- "RNA/counts(slot)"
  }
  if (is.null(mat)) {
    mat <- try_get("RNA", layer_name = "data")
    source_layer <- "RNA/data(layer)"
  }
  if (is.null(mat)) {
    mat <- try_get("RNA", slot_name = "data")
    source_layer <- "RNA/data(slot)"
  }

  if (is.null(mat)) {
 stop("Unable to retrieve the RNA assay counts/data matrix. Please check the object.")
  }
  if (!inherits(mat, "CsparseMatrix")) {
    mat <- as(mat, "CsparseMatrix")
  }
  if (is.null(mat) || any(dim(mat) == 0)) {
 stop("The export matrix is empty. Please check the selected Seurat assay/layer.")
  }
  if (is.null(colnames(mat)) || is.null(rownames(mat))) {
 stop("The export matrix is missing feature or barcode names; unable to write h5ad.")
  }
  if (length(colnames(mat)) != ncol(mat) || length(rownames(mat)) != nrow(mat)) {
 stop("The export matrix must be a matrix-like object.")
  }

  list(mat = mat, source_layer = source_layer)
}

tryCatch({
  if (!file.exists(input_rds)) {
    stop(paste("Input file does not exist:", input_rds))
  }

  obj <- readRDS(input_rds)
  cat(sprintf("Object: %d cells, %d genes\n", ncol(obj), nrow(obj)))

  sub_info <- list()
  if (merge_sub && nchar(sub_rds) > 0 && file.exists(sub_rds)) {
    cat("Merging subcluster metadata...\n")
    sub_obj <- readRDS(sub_rds)

    if ("subtype" %in% colnames(sub_obj@meta.data)) {
      sub_meta <- sub_obj@meta.data[, "subtype", drop = FALSE]
      colnames(sub_meta) <- "subtype"
      common_cells <- intersect(rownames(sub_meta), rownames(obj@meta.data))
      if (length(common_cells) > 0) {
        obj@meta.data$subtype <- NA_character_
        obj@meta.data[common_cells, "subtype"] <- sub_meta[common_cells, "subtype"]
 cat(sprintf(" Merged subcluster annotation for %d cells\n", length(common_cells)))
        sub_info$n_subcells <- length(common_cells)
        sub_info$subtypes <- unique(sub_meta[common_cells, "subtype"])
      }
    }

    if ("umap" %in% Reductions(sub_obj)) {
      sub_umap <- Embeddings(sub_obj, "umap")
      sub_umap_path <- file.path(output_dir, "embedding_sub_umap.csv")
      write.csv(sub_umap, sub_umap_path, row.names = TRUE)
      cat(sprintf("  Saving subcluster UMAP: %d cells\n", nrow(sub_umap)))
    }

    rm(sub_obj)
    gc(verbose = FALSE)
  }

  export_res <- extract_export_matrix(obj)
  counts_mat <- export_res$mat
  source_layer <- export_res$source_layer
  barcodes <- colnames(counts_mat)
  features <- rownames(counts_mat)
  meta <- obj@meta.data[barcodes, , drop = FALSE]

  cat(sprintf("Export matrix source: %s\n", source_layer))
  cat(sprintf("Export matrix dimensions: %d genes x %d cells\n", nrow(counts_mat), ncol(counts_mat)))

  cat("Saving counts...\n")
  writeMM(counts_mat, file.path(output_dir, "counts.mtx"))
  writeLines(barcodes, file.path(output_dir, "barcodes.tsv"))
  writeLines(features, file.path(output_dir, "features.tsv"))

  cat("Saving metadata...\n")
  for (cn in colnames(meta)) {
    if (is.list(meta[[cn]])) {
      meta[[cn]] <- as.character(meta[[cn]])
    }
  }
  write.csv(meta, file.path(output_dir, "metadata.csv"), row.names = TRUE)

  emb_saved <- c()
  for (rd in Reductions(obj)) {
    tryCatch({
      emb <- Embeddings(obj, rd)
      emb <- emb[barcodes, , drop = FALSE]
      write.csv(emb, file.path(output_dir, paste0("embedding_", rd, ".csv")), row.names = TRUE)
      emb_saved <- c(emb_saved, rd)
      cat(sprintf("  embedding: %s (%d x %d)\n", rd, nrow(emb), ncol(emb)))
    }, error = function(e) {})
  }

  obs_columns <- colnames(meta)
  has_celltype <- "cell.type" %in% obs_columns
  has_subtype <- "subtype" %in% obs_columns

  write_summary(list(
    status = "success",
    method = "intermediate_files",
    assay_used = "RNA",
    matrix_source = source_layer,
    n_cells = ncol(counts_mat),
    n_genes = nrow(counts_mat),
    embeddings = as.list(emb_saved),
    obs_columns = as.list(obs_columns),
    has_celltype = has_celltype,
    has_subtype = has_subtype,
    sub_info = sub_info,
    figures = list(),
    tables = list()
  ), output_dir)

  cat("=== Intermediate export completed ===\n")
}, error = function(e) {
 write_error_summary("Export", conditionMessage(e), "Please check the input object.", output_dir)
  quit(status = 1)
})
