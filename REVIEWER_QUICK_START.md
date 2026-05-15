# Reviewer Quick Start

## 1. Download and open the trial app

Download `scFlow_Studio_Mac_AcademicTrial_2026-10-01.zip` from GitHub Releases, unzip it, and open `scFlow Studio.app`.

If macOS blocks the app because it is not notarized, right-click the app and choose **Open**. For local reviewer testing, quarantine can also be removed with:

```bash
xattr -dr com.apple.quarantine "scFlow Studio.app"
```

## 2. Prepare test data

Recommended manuscript demo dataset:

- Dataset: GSE250245
- Biological context: right-hemisphere ischemic lesion single-cell RNA-seq dataset
- Example samples: GSM7976207, GSM7976209, GSM7976211
- Approximate benchmark size: 35,377 cells, depending on QC and preprocessing settings

If the demo data are not included in this repository, download the original data from GEO and organize the 10X folders before importing.

## 3. Create a project

Open scFlow Studio, create a new project in a writable directory, and add the prepared samples from the Project and Data page.

## 4. Run the core workflow

Recommended smoke-test workflow:

1. Check data
2. Run single-sample QC
3. Run or skip doublet removal
4. Run batch correction preview if multiple samples are present
5. Run merge and clustering
6. Run main annotation
7. Run differential expression
8. Run GSEA
9. Export figures and tables

## 5. Expected outputs

The project cache should contain PNG/PDF/SVG figures, CSV/TSV/TXT result tables, summary JSON files, and exported RDS/h5ad files depending on the selected modules.

## 6. Expected runtime

On a 16 GB macOS machine, the approximately 35k-cell benchmark workflow is expected to complete in less than 30 minutes with peak memory below 10 GB. Please verify and update these values before publication if hardware or input data change.
