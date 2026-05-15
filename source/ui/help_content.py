from __future__ import annotations

from html import escape
from typing import Iterable

REFERENCE_URLS = {
    "seurat_pbmc": "https://satijalab.org/seurat/articles/pbmc3k_tutorial",
    "seurat_find_markers": "https://satijalab.org/seurat/reference/findmarkers",
    "doubletfinder": "https://github.com/chris-mcginnis-ucsf/DoubletFinder",
    "singler": "https://www.bioconductor.org/packages/release/bioc/html/SingleR.html",
    "tenx_cell_qc": "https://www.10xgenomics.com/analysis-guides/common-considerations-for-quality-control-filters-for-single-cell-rna-seq-data",
    "tenx_best_practices": "https://www.10xgenomics.com/resources/analysis-guides/best-practices-analysis-10x-single-cell-rna-sequencing-data",
    "scbp_qc": "https://www.sc-best-practices.org/preprocessing_visualization/quality_control.html",
    "anndata": "https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html",
}

STEP_TITLES = {
    "project": "1. Project and Data",
    "qc": "2. Single-Sample QC",
    "doublet": "3. Doublet Removal",
    "batch": "4. Batch Correction",
    "merge_cluster": "5. Merge and Clustering",
    "annotation": "6. Main Annotation",
    "subcluster": "7. Subcluster Analysis",
    "deg": "8. Differential Expression",
    "gsea": "9. GSEA Enrichment",
    "gene_analysis": "10. Single-Gene Analysis",
    "module_score": "11. Gene Set Scoring",
    "export": "12. Export Report",
}

STEP_SUMMARIES = {
    "project": "Create a project, register samples, validate input data, and choose the project-wide plotting theme.",
    "qc": "Filter low-quality cells using UMI counts, detected genes, mitochondrial percentage, and per-sample settings.",
    "doublet": "Run DoubletFinder per sample or pass data through unchanged when doublet removal is intentionally skipped.",
    "batch": "Preview and optionally correct sample or batch effects before final clustering.",
    "merge_cluster": "Merge selected samples and run normalization, HVG selection, PCA, neighbor graph construction, clustering, UMAP, and tSNE.",
    "annotation": "Find cluster markers and annotate main clusters using manual markers, SCINA, CellAssign, marker overlap, or SingleR.",
    "subcluster": "Subset selected cell types and run independent subcluster analyses, marker detection, annotation, and plotting.",
    "deg": "Run differential expression on the main object or any saved subcluster result, including cross-group and cross-cell-type comparisons.",
    "gsea": "Use DEG result tables and a local GMT file to perform fgsea-based pathway enrichment and pathway visualization.",
    "gene_analysis": "Visualize one gene across cell types and groups, with optional pairwise statistical comparison.",
    "module_score": "Score a custom gene set or GMT pathway and visualize the score across embeddings, groups, and cell types.",
    "export": "Export images, tables, h5ad files, project bundles, and complete Seurat objects for sharing and downstream analysis.",
}


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return escape(str(value))


def _bullets(items: Iterable[str]) -> str:
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def _section(title: str, items: Iterable[str]) -> str:
    return f"<div class='help-card'><h4>{escape(title)}</h4>{_bullets(items)}</div>"


def _references(items: Iterable[tuple[str, str]]) -> str:
    links = "".join(f"<li><a href='{escape(url)}'>{escape(label)}</a></li>" for label, url in items)
    return f"<div class='help-card'><h4>References</h4><ol>{links}</ol></div>"


def _wrap(title: str, subtitle: str, sections: Iterable[str], refs: Iterable[tuple[str, str]]) -> str:
    return f"""
    <html>
    <head>
      <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 13px; line-height: 1.65; color: #243447; }}
        h3 {{ margin: 0 0 8px 0; font-size: 20px; color: #0F4C81; }}
        h4 {{ margin: 0 0 6px 0; font-size: 15px; color: #1B5E20; }}
        p {{ margin: 0 0 10px 0; }}
        ul, ol {{ margin-top: 4px; padding-left: 20px; }}
        li {{ margin-bottom: 5px; }}
        code {{ background: #F3F6FA; padding: 1px 5px; border-radius: 4px; }}
        .help-card {{ border: 1px solid #D8E1EA; border-radius: 8px; padding: 10px 12px; margin: 9px 0; background: #FBFDFF; }}
        .subtitle {{ color: #546E7A; }}
        a {{ color: #1565C0; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
      </style>
    </head>
    <body>
      <h3>{escape(title)}</h3>
      <p class='subtitle'>{escape(subtitle)}</p>
      {''.join(sections)}
      {_references(refs) if refs else ''}
    </body>
    </html>
    """


def _context_items(ctx: dict) -> list[str]:
    items: list[str] = []
    for key, value in (ctx or {}).items():
        label = str(key).replace("_", " ").title()
        items.append(f"<b>{escape(label)}:</b> {_fmt(value)}")
    return items or ["No page-specific parameters are currently available."]


def build_step_help(step_id: str, ctx: dict | None = None) -> str:
    title = STEP_TITLES.get(step_id, "scFlow Studio Help")
    subtitle = STEP_SUMMARIES.get(step_id, "This page provides workflow guidance and parameter context.")
    sections = [
        _section("Current Settings", _context_items(ctx or {})),
        _section("Recommended Workflow", [
            "Review the parameters before running the step.",
            "Run the current step and check the log tab for warnings or errors.",
            "Inspect the preview panel and result table before moving to the next step.",
        ]),
        _section("Troubleshooting", [
            "If a step fails, verify input files, selected object source, and the configured Rscript path.",
            "For large datasets, allow enough memory and avoid moving the project cache while a task is running.",
            "If a reference or package is unavailable, confirm that the bundled runtime and local cache are present.",
        ]),
    ]
    refs = [
        ("Seurat PBMC tutorial", REFERENCE_URLS["seurat_pbmc"]),
        ("Seurat FindMarkers", REFERENCE_URLS["seurat_find_markers"]),
        ("SingleR", REFERENCE_URLS["singler"]),
    ]
    if step_id == "qc":
        refs.extend([
            ("10x Genomics QC considerations", REFERENCE_URLS["tenx_cell_qc"]),
            ("Single-cell best practices: QC", REFERENCE_URLS["scbp_qc"]),
        ])
    if step_id == "doublet":
        refs.append(("DoubletFinder", REFERENCE_URLS["doubletfinder"]))
    if step_id == "export":
        refs.append(("AnnData h5ad format", REFERENCE_URLS["anndata"]))
    return _wrap(title, subtitle, sections, refs)
