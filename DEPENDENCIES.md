# Dependencies

The macOS academic trial app bundles the runtime environment required for reviewer testing, including Python, R, R packages, R scripts, resources, and local reference-cache files available at build time.

## Python dependencies

See `source/requirements.txt`.

Major Python dependencies include:

- PySide6
- psutil
- cryptography
- numpy
- pandas
- scipy
- h5py
- openpyxl

## R dependencies

Major R dependencies include:

- Seurat
- SeuratObject
- Matrix
- jsonlite
- ggplot2
- patchwork
- dplyr
- tidyr
- harmony
- DoubletFinder
- SingleR
- celldex
- SCINA
- cellassign
- fgsea
- MAST
- SeuratDisk
- zellkonverter

## Runtime notes

The trial `.app` is intended to run without requiring users to install Python or R manually.

The source snapshot does not include the full bundled runtime because of file size. Rebuilding the standalone app requires restoring the prepared runtime folders described in `source/vendor/README.md`, if applicable.

## Reference data

SingleR/celldex references are expected to be available from the bundled cache when included in the trial app. If a reference is missing from the local cache, some annotation workflows may require network access to retrieve the reference from its original provider.
