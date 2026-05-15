# scFlow Studio for macOS

scFlow Studio is a desktop single-cell RNA-seq analysis application with a Python/PySide6 interface and a Seurat-based R backend. This English edition preserves the same workflow as the Chinese macOS version while presenting user-facing, logs, help content, and report labels in English.

## Quick Start

```bash
cd scFlow-Studio
./build_macos.sh
```

The packaged application is written to `dist_macos/scFlow Studio.app`.

## Workflow

1. Project and Data
2. Single-Sample QC
3. Doublet Removal
4. Batch Correction
5. Merge and Clustering
6. Main Annotation
7. Subcluster Analysis
8. Differential Expression
9. GSEA Enrichment
10. Single-Gene Analysis
11. Gene Set Scoring
12. Export Report

## Runtime Notes

The macOS build is designed to use bundled resources when available, including R scripts, static resources, celldex reference cache, and bundled R/Python runtimes. Developer ID signing and notarization are still required for frictionless distribution on other Macs.
