# Quick Start

1. Launch **scFlow Studio Agent V0.1.0**.
2. Click **New Project** and choose a project directory outside the installation folder.
3. On **01 Data Import**, add 10X folders, expression matrices, H5AD files, archives, or compatible RDS objects.
4. Confirm the sample names, biological groups, species, and paths.
5. Click **Check All Data**, then create the project.
6. Run each numbered step from top to bottom. Review the **Parameters**, **Log**, **Images**, and **Tables** areas before clicking **Confirm and Continue**.
7. Use **15 Export Report** to collect figures, tables, H5AD files, or Seurat objects.

## GSE250245 example

For the bundled demonstration folders, import the samples in this order:

| Sample | Group |
| --- | --- |
| Sham | Sham |
| MMCAO | MCAO |
| SMCAO | MCAO |

Keep the default random seed and sample order when comparing repeated runs. The complete illustrated procedure is in [`docs/scFlow-Studio-Agent-V0.1.0-User-Manual.docx`](docs/scFlow-Studio-Agent-V0.1.0-User-Manual.docx).

## First QC run

The first step that genuinely invokes R may take longer while the bundled R runtime is prepared in a temporary runtime directory. Follow the progress bar and Log rather than closing the application.
