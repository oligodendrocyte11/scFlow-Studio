# Demo Data Preparation

This repository does not include large raw datasets. Prepare one of the supported public input formats before testing the workflow.

## GSE250245 example

The Windows user manual demonstrates three samples:

| Sample | Group |
| --- | --- |
| Sham | Sham |
| MMCAO | MCAO |
| SMCAO | MCAO |

Keep this sample order when reproducing the illustrated workflow.

## 10X Matrix folder

A standard 10X folder contains:

- `matrix.mtx.gz`
- `barcodes.tsv.gz`
- `features.tsv.gz` or `genes.tsv.gz`

## Expression matrix

CSV, TSV, and TXT matrices can be imported through **Import Matrix File**. Confirm the detected orientation, sample names, groups, and species before continuing.

## H5AD / AnnData

Single-sample and multi-sample H5AD objects are supported. During confirmation, replace numeric groups such as `0` and `1` with the true experimental group names when necessary.

## Marker and gene-set files

Marker tables should identify cell types and marker genes. GMT files use the standard tab-separated structure:

```text
GeneSetName<TAB>Description<TAB>GeneA<TAB>GeneB<TAB>GeneC
```

Record the accession, species, sample count, cell count, source URL, and preprocessing parameters for every public dataset used in a report or manuscript.
