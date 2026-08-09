# Dependencies

The Windows V0.1.0 installer bundles the runtime environment required for normal use. Users do not need to install R or Python separately.

## Bundled Windows runtime

- R 4.5.2
- Seurat 5.4.0
- SeuratObject 5.3.0
- Matrix 1.7-4
- DoubletFinder 2.0.6
- SingleR 2.12.0
- CellChat 1.6.1
- monocle3 1.4.26
- PySide6 application interface and the packaged Python runtime

Additional R and Python packages are included for H5AD import/export, annotation, differential expression, enrichment, scoring, plotting, report export, and optional AI-provider integration.

## Runtime isolation

The application is designed to use its bundled R and package library. Leave **Settings > Rscript Path** on **Auto**. Pointing the application to a system R installation can change package resolution and reproducibility.

During the first real R analysis, the packaged R runtime may be prepared in a temporary runtime directory before execution. This is expected behavior.

## Source builds

The source snapshot does not duplicate every large runtime component. Building a complete standalone release requires the matching platform-specific R/Python runtimes, package libraries, reference data, and packaging configuration.

## Third-party terms

Bundled third-party components retain their original licenses. Package-level license metadata and license files are included with the respective runtime components where supplied upstream. See `THIRD_PARTY_LICENSES.md`.
