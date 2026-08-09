# Known Limitations

- The current release focuses on single-cell RNA-seq analysis. It is not a general-purpose primary workflow for scATAC-seq, spatial transcriptomics, bulk RNA-seq, or TCR/BCR analysis.
- Large H5AD objects and large sparse matrices may require substantial import time, memory, and temporary disk space.
- The Windows installer is not digitally signed; Windows SmartScreen may display an Unknown publisher warning.
- The first QC run can start slowly while the bundled R runtime is prepared for first use.
- Some optional online references and AI-provider features require network access and provider credentials.
- AI-provider credentials should be kept session-only when possible and must never be committed to a project or repository.
- Exact numerical reproducibility requires the same application build, bundled runtime, input files, sample order, parameters, random seed, and relevant reduction choice.
- After rerunning major clustering with a different reduction, reopen Subcluster Analysis and verify its reduction setting before running downstream analyses.
- The Windows application occupies approximately 4.72 GB before project data and caches are added.
- A matching macOS DMG is distributed separately and may have different signing or launch requirements.
