# Known Limitations

- scFlow Studio currently focuses on single-cell RNA-seq analysis.
- scATAC-seq, spatial transcriptomics, bulk RNA-seq, TCR/BCR analysis, and multi-omics integration are not currently supported as primary workflows.
- h5ad export is supported, but h5ad import is not currently implemented.
- H5Seurat import is not currently implemented or requires further confirmation.
- Trajectory and pseudotime analysis are not currently implemented.
- Interactive HTML report generation is not currently implemented.
- The current benchmark summary is based on one approximately 35k-cell dataset and should be expanded to additional datasets and larger cell counts.
- Larger datasets may require more memory and longer runtime.
- The macOS app is ad-hoc signed and not Apple-notarized; users may need to use right-click **Open** or remove the quarantine attribute.
- SingleR/celldex annotation may require network access if a selected reference is missing from the bundled local cache.
