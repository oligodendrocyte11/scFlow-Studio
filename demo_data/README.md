# Demo Data Preparation

This package does not include large demo datasets. To test the workflow, prepare one of the following input types.

## 10X Matrix Folder

A standard 10X folder should contain:

- `matrix.mtx.gz`
- `barcodes.tsv.gz`
- `features.tsv.gz` or `genes.tsv.gz`

Add each sample folder from the **Project and Data** page.

## Expression Matrix

A matrix file can be prepared as CSV/TSV/TXT where rows represent genes and columns represent cells or samples, depending on the import mode supported by the project page. If a sidecar metadata file is available, place it in the same directory and use matching sample/barcode identifiers.

## Marker CSV

A marker table should contain cell-type names and marker genes. Recommended columns include:

- `celltype`
- `gene`

## GMT Gene Sets

A GMT file should follow the standard format:

```text
GeneSetName<TAB>Description<TAB>GeneA<TAB>GeneB<TAB>GeneC
```

## Suggested Public Data

For manuscript validation, select at least one public scRNA-seq dataset with known cell types and experimental groups. Record the accession, species, sample count, cell count, and preprocessing parameters in the manuscript.
