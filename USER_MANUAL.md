# User Manual

## Overview

scFlow Studio is organized as a project-based desktop workflow. Each page corresponds to one analysis stage and writes intermediate outputs to the project cache.

## Pages

1. **Project and Data**: create/open projects and register samples.
2. **Single-Sample QC**: calculate QC metrics, filter cells/genes, and export QC plots.
3. **Doublet Removal**: run or skip doublet removal.
4. **Batch Correction**: preview and apply batch correction where needed.
5. **Merge and Clustering**: merge samples, normalize data, select variable features, run PCA/UMAP/t-SNE, and cluster cells.
6. **Main Annotation**: annotate main clusters with manual markers, SingleR, SCINA, CellAssign, or marker overlap.
7. **Subcluster Analysis**: create and manage subcluster results, annotate subtypes, and generate subtype plots.
8. **Differential Analysis**: run condition- or cell-type-aware DEG comparisons.
9. **GSEA**: perform pathway-level enrichment analysis from DEG results.
10. **Single-Gene Analysis**: visualize and compare expression of selected genes.
11. **Gene-Set Scoring**: score user-defined gene sets and compare module scores.
12. **Export**: export figures, tables, h5ad, RDS, and project bundles.

## Notes

- Keep project paths in user-writable directories.
- Very large datasets may require more memory and disk space.
- Review the log tab if an R package or input-format error occurs.
