# English Version Check Report

Updated: 2026-04-28

## Scope

This report covers the targeted cleanup performed only inside `Mac_EnglishVersion`. The Chinese `Mac_copy` project was not modified.

## Fix Summary

- Restored and preserved English runtime logging through `RBridge` and page logs.
- Added an English-locale prelude to project R scripts so R warnings and project messages prefer English before package loading.
- Added a Python-side fallback translator in `core/r_bridge.py` for common Chinese R warning fragments when system locale fallback is unavailable.
- Replaced deprecated sparse matrix coercions from `as(..., "dgCMatrix")` to `as(..., "CsparseMatrix")` in QC and export-related scripts.
- Explicitly set `RunUMAP(..., umap.method = "uwot", metric = "cosine")` in all project R scripts to suppress Seurat's default-method warning.
- Fixed the GSEA `wrap_label()` implementation so vector input works inside `dplyr::mutate()` and `strwrap()` always receives its `x` argument.
- Fixed the GSEA single-pathway plot subtitle variable.
- Fixed Batch Correction UI blank checkbox text and cleaned batch result labels.
- Fixed Main Annotation / SingleR UI blank labels and incomplete button/help text.
- Fixed DEG comparison mode option `D.` so it now has a complete English label.
- Fixed blank comparison-mode items in Single-Gene Analysis and Gene-Set Scoring.
- Cleaned additional visible placeholder fragments in subcluster, project, and shared page messages.

## Files Updated

### Python

- `core/r_bridge.py`
- `ui/pages/base_page.py`
- `ui/pages/p01_project.py`
- `ui/pages/p04_batch.py`
- `ui/pages/p05_annotation.py`
- `ui/pages/p06_deg.py`
- `ui/pages/p07_subcluster.py`
- `ui/pages/p09_gene_analysis.py`
- `ui/pages/p10_module_score.py`

### R

- All project R scripts under `r_scripts/` received the English-locale prelude.
- `r_scripts/02_qc.R`
- `r_scripts/02_qc_passthrough.R`
- `r_scripts/03_doublet.R`
- `r_scripts/04_batch.R`
- `r_scripts/05_cluster.R`
- `r_scripts/07_gsea.R`
- `r_scripts/08_subcluster.R`
- `r_scripts/11_export_h5ad.R`

## Specific Issue Coverage

### QC Matrix Deprecated Warning

Deprecated sparse conversion calls were replaced with `CsparseMatrix` coercion. This avoids the Matrix warning about `as(<dgTMatrix>, "dgCMatrix")` while preserving sparse matrix input for Seurat object creation.

### RunUMAP Default Method Warning

All project `RunUMAP()` calls now explicitly use `umap.method = "uwot"` and `metric = "cosine"`. This keeps the current R-native UMAP behavior while suppressing Seurat's default-method change warning.

### Batch Correction UI and Warnings

The batch correction checkbox now displays `Enable batch correction`. Batch preview/result labels were cleaned, and R warnings are forced toward English through the R locale prelude plus RBridge fallback translation.

### SingleR / Main Annotation UI and Logs

The SingleR row now displays explicit labels: `Annotation method` and `Reference database`. Buttons and annotation hints were normalized to English, and SingleR reference warnings/errors remain in English.

### DEG Comparison Mode

The blank `D.` comparison mode is now `D. Custom group/cell-type comparison`. DEG helper text and table headers were cleaned.

### GSEA wrap_label Bug

`wrap_label()` now accepts vectors, safely wraps each pathway label, and returns a character vector suitable for `mutate()`. The single-pathway plot subtitle variable was also corrected.

## Validation Performed

- Python AST check: passed.
- Python import smoke check for modified modules: passed.
- R parse check for project R scripts: passed (`21` files).
- GSEA `wrap_label()` vector smoke test: passed.
- Project-owned Chinese-character scan: no Chinese characters found in scanned source/resource files.
- Bad placeholder scan: no remaining empty checkbox/radio/dropdown patterns for the targeted issues.

## Chinese Residual Scan

Scan command scope:

- `*.py`, `*.R`, `*.json`, `*.txt`, `*.md`, `*.qss`, `*.ui`, `*.csv`, `*.tsv`, `*.yml`, `*.yaml`
- Excluded generated or third-party directories: `.venv/`, `vendor/`, `dist_macos/`, `build_macos/`, `celldex_cache/`, `__pycache__/`, `.fix_backups/`

Result: no project-owned Chinese residuals were detected in the scanned scope.

## Notes

- Third-party R/Python packages may still emit non-English text if the host system forces a non-English locale, but the project now sets an English locale before package loading and translates common Chinese R warning prefixes at the RBridge level.
- The fixes intentionally do not change analysis algorithms, cache schema, output file naming, or workflow order.
