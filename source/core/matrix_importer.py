import csv
import gzip
import io
import itertools
import os
import re
import shlex
import subprocess
import tarfile
import shutil
import tempfile
from collections import OrderedDict
from typing import Iterable

csv.field_size_limit(1024 * 1024 * 256)
SUBPROCESS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SUPPORTED_MATRIX_EXTENSIONS = (".txt", ".tsv", ".csv", ".txt.gz", ".tsv.gz", ".csv.gz")
SUPPORTED_IMPORT_EXTENSIONS = SUPPORTED_MATRIX_EXTENSIONS + (".tar", ".tar.gz", ".tgz", ".rar", ".rds")


def _open_text(path: str):
    if path.lower().endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace', newline='')
    return open(path, 'r', encoding='utf-8', errors='replace', newline='')


def _open_tar_member_text(archive: tarfile.TarFile, member: tarfile.TarInfo):
    extracted = archive.extractfile(member)
    if extracted is None:
        raise FileNotFoundError(f'Unable to read tar member: {member.name}')
    if member.name.lower().endswith('.gz'):
        return gzip.open(extracted, 'rt', encoding='utf-8', errors='replace', newline='')
    return io.TextIOWrapper(extracted, encoding='utf-8', errors='replace', newline='')


def _open_tar_member_binary(archive: tarfile.TarFile, member: tarfile.TarInfo):
    extracted = archive.extractfile(member)
    if extracted is None:
        raise FileNotFoundError(f'Unable to read tar member: {member.name}')
    return extracted


def _detect_delimiter(path: str) -> str:
    with _open_text(path) as handle:
        header = handle.readline()
    if '\t' not in header and ',' not in header:
        return ' '
    return ',' if header.count(',') > header.count('\t') else '\t'


def _find_folder_file(path: str, patterns: tuple[str, ...]) -> str:
    if not path or not os.path.isdir(path):
        return ""
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if not os.path.isfile(full) or _is_ignored_auxiliary_name(name):
            continue
        for pattern in patterns:
            if re.search(pattern, name, flags=re.IGNORECASE):
                return full
    return ""


def _detect_member_delimiter(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    with _open_tar_member_text(archive, member) as handle:
        header = handle.readline()
    if '\t' not in header and ',' not in header:
        return ' '
    return ',' if header.count(',') > header.count('\t') else '\t'


def _strip(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _is_ignored_auxiliary_name(name: str) -> bool:
    base = os.path.basename(name)
    return base.startswith("._") or base == ".DS_Store"


def infer_group(sample_name: str) -> str:
    upper = re.split(r'[^A-Za-z0-9]+', sample_name.upper())
    keywords = [
        'AD', 'WT', 'UNTREATED', 'SHAM', 'CONTROL', 'CTRL',
        'TREATED', 'KO', 'TG', 'CASE', 'NORMAL', 'MODEL', 'MCAO'
    ]
    for key in keywords:
        if key in upper:
            return key
    return sample_name.split('_')[0] if '_' in sample_name else sample_name


def sanitize_sample_name(name: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', name.strip())
    return safe.strip('._') or 'sample'


def _parse_sparse_bundle_metadata(path: str) -> dict:
    matrix_path = _find_folder_file(path, (r"rawcounts.*sparse\.mtx\.gz$", r"\.mtx\.gz$"))
    genes_path = _find_folder_file(path, (r"allcells.*geneids.*\.txt\.gz$", r"geneids.*\.txt\.gz$"))
    barcodes_path = _find_folder_file(path, (r"allcells.*cellbarcodes.*\.txt\.gz$", r"cellbarcodes.*\.txt\.gz$"))
    metadata_path = _find_folder_file(path, (r"metadata.*table.*\.txt\.gz$", r"metadata.*\.txt\.gz$"))

    if not (matrix_path and genes_path and barcodes_path and metadata_path):
        raise ValueError("No complete sparse matrix bundle was detected in this folder (matrix + GeneIDs + cellBarcodes + metadata).")

    sample_rows: OrderedDict[str, dict] = OrderedDict()
    with _open_text(metadata_path) as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        if reader.fieldnames is None:
            raise ValueError('The metadata file is missing a header row.')
        if 'Library_Identity' not in reader.fieldnames:
            raise ValueError('The metadata file is missing the Library_Identity column.')
        if 'CellBarcode_Identity' not in reader.fieldnames:
            raise ValueError('The metadata file is missing the CellBarcode_Identity column.')

        disease_col = 'Disease_Identity' if 'Disease_Identity' in reader.fieldnames else ''
        subject_col = 'Subject_Identity' if 'Subject_Identity' in reader.fieldnames else ''

        for row in reader:
            library = _strip(row.get('Library_Identity', ''))
            barcode = _strip(row.get('CellBarcode_Identity', ''))
            if not library or not barcode:
                continue
            info = sample_rows.setdefault(
                library,
                {
                    'sample_name': library,
                    'group': '',
                    'cell_count': 0,
                    'gene_count': 0,
                    'library_identity': library,
                },
            )
            info['cell_count'] += 1
            if disease_col and not info['group']:
                info['group'] = _strip(row.get(disease_col, ''))
            if not info['group'] and subject_col:
                info['group'] = _strip(row.get(subject_col, ''))

    if not sample_rows:
        raise ValueError('No usable library/cell information was detected in the metadata file.')

    gene_count = 0
    with _open_text(genes_path) as handle:
        next(handle, None)
        for line in handle:
            if line.strip():
                gene_count += 1

    for item in sample_rows.values():
        item['gene_count'] = gene_count
        if not item['group']:
            item['group'] = infer_group(item['sample_name'])

    return {
        'matrix_path': matrix_path,
        'genes_path': genes_path,
        'barcodes_path': barcodes_path,
        'metadata_path': metadata_path,
        'samples': list(sample_rows.values()),
        'gene_count': gene_count,
    }


def detect_sparse_bundle_folder(path: str) -> dict:
    parsed = _parse_sparse_bundle_metadata(path)
    total_cells = sum(sample['cell_count'] for sample in parsed['samples'])
    return {
        'source_type': 'sparse_bundle_folder',
        'cell_count': total_cells,
        'sample_count': len(parsed['samples']),
        'samples': parsed['samples'],
        'gene_count': parsed['gene_count'],
    }


def _split_preview_fields(line: str, delimiter: str | None = None) -> list[str]:
    text = str(line).strip()
    if not text:
        return []
    if delimiter is None:
        if '\t' in text:
            delimiter = '\t'
        elif ',' in text:
            delimiter = ','
        else:
            delimiter = ' '
    if delimiter == ' ':
        return [_strip(token) for token in shlex.split(text)]
    return [_strip(token) for token in next(csv.reader([text], delimiter=delimiter))]


def _profile_matrix_preview(first_line: str, second_line: str) -> dict:
    delimiter = '\t' if '\t' in first_line else ',' if ',' in first_line else ' '
    header_fields = _split_preview_fields(first_line, delimiter)
    row_fields = _split_preview_fields(second_line, delimiter) if second_line else []
    orientation = "gene_by_cell"
    metadata_columns = 1

    if header_fields:
        first_header = header_fields[0].lower()
        if first_header == "barcode":
            orientation = "cell_by_gene"
            metadata_columns = 3
        elif len(row_fields) == len(header_fields) + 1 and first_header in {"barcode", "cell", "cell_id"}:
            orientation = "cell_by_gene"
            metadata_columns = 3
        elif (
            orientation == "gene_by_cell"
            and len(header_fields) >= 3
            and header_fields[1].strip().lower() in {"gene", "genes", "symbol", "gene_name", "genename"}
        ):
            metadata_columns = 2

    return {
        "delimiter": delimiter,
        "header_fields": header_fields,
        "row_fields": row_fields,
        "orientation": orientation,
        "metadata_columns": metadata_columns,
    }


def _detect_suffix_groups_from_cells(cell_ids: list[str]) -> list[dict]:
    counts: OrderedDict[str, int] = OrderedDict()
    for cell_id in cell_ids:
        match = re.search(r"[_-](\d+)$", cell_id)
        if not match:
            return []
        suffix = match.group(1)
        counts[suffix] = counts.get(suffix, 0) + 1
    if len(counts) <= 1:
        return []
    return [
        {"suffix": suffix, "cell_count": cell_count}
        for suffix, cell_count in counts.items()
    ]


def _detect_named_suffix_groups_from_cells(cell_ids: list[str]) -> list[dict]:
    counts: OrderedDict[str, int] = OrderedDict()
    for cell_id in cell_ids:
        if "_" not in cell_id:
            return []
        suffix = _strip(cell_id.rsplit("_", 1)[-1]).lower()
        if not suffix:
            return []
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{1,20}", suffix):
            return []
        counts[suffix] = counts.get(suffix, 0) + 1
    if len(counts) <= 1 or len(counts) > 12:
        return []
    if any(cell_count < 5 for cell_count in counts.values()):
        return []
    return [
        {"suffix": suffix, "cell_count": cell_count}
        for suffix, cell_count in counts.items()
    ]


def _find_sidecar_metadata_file(matrix_path: str) -> str:
    folder = os.path.dirname(matrix_path)
    if not folder or not os.path.isdir(folder):
        return ""

    candidates = [
        r"(^|.*_)?meta(data)?\.csv\.gz$",
        r"(^|.*_)?meta(data)?\.tsv\.gz$",
        r"(^|.*_)?meta(data)?\.csv$",
        r"(^|.*_)?meta(data)?\.tsv$",
        r"(^|.*_)?cell[_-]?meta(data)?\.csv\.gz$",
        r"(^|.*_)?cell[_-]?meta(data)?\.tsv\.gz$",
        r"(^|.*_)?cell[_-]?meta(data)?\.csv$",
        r"(^|.*_)?cell[_-]?meta(data)?\.tsv$",
        r".*metaData\.csv\.gz$",
        r".*metadata\.csv\.gz$",
        r"SC-MetaData\.csv$",
    ]
    return _find_folder_file(folder, tuple(candidates))


def _normalize_cell_lookup_key(value: str) -> str:
    text = _strip(str(value or ""))
    if not text:
        return ""
    return re.sub(r"[-\s]+", "_", text).lower()


def _extract_tar_member_lines(archive: tarfile.TarFile, member_name: str) -> list[str]:
    member = archive.getmember(member_name)
    with _open_tar_member_text(archive, member) as handle:
        return [_strip(line) for line in handle if _strip(line)]


def _load_tar_metadata_groups(archive: tarfile.TarFile, metadata_member_name: str, cells: list[str]) -> list[dict]:
    member = archive.getmember(metadata_member_name)
    delimiter = _detect_member_delimiter(archive, member)
    with _open_tar_member_text(archive, member) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = reader.fieldnames or []
        normalized = {str(name).strip().lower(): name for name in fieldnames}

        first_field = fieldnames[0] if fieldnames else None
        unnamed_first = first_field if first_field is not None and str(first_field).strip().lower() in {"", "x", "index"} else None
        cell_id_col = (
            normalized.get("cell_id")
            or normalized.get("cellid")
            or normalized.get("cells")
            or normalized.get("cell")
            or normalized.get("barcode")
            or normalized.get("barcodes")
            or unnamed_first
        )
        sample_col = (
            normalized.get("sample")
            or normalized.get("sample_id")
            or normalized.get("sampleid")
            or normalized.get("orig.ident")
            or normalized.get("orig_ident")
            or normalized.get("library")
            or normalized.get("library_id")
            or normalized.get("donor")
            or normalized.get("patient")
            or normalized.get("subject")
        )
        group_col = (
            normalized.get("subtype")
            or normalized.get("condition")
            or normalized.get("conditions")
            or normalized.get("group")
            or normalized.get("status")
            or normalized.get("treatment")
            or normalized.get("celltype_major")
        )

        if cell_id_col is None or sample_col is None:
            return []

        meta_map: OrderedDict[str, dict] = OrderedDict()
        for row in reader:
            cell_id = _strip(str(row.get(cell_id_col, "")))
            sample_name = _strip(str(row.get(sample_col, "")))
            group_value = _strip(str(row.get(group_col, ""))) if group_col else ""
            if not cell_id or not sample_name:
                continue
            meta_map[_normalize_cell_lookup_key(cell_id)] = {
                "sample_name": sanitize_sample_name(sample_name),
                "group": group_value or infer_group(sample_name),
            }

    if not meta_map:
        return []

    sample_map = OrderedDict()
    matched = 0
    for index, cell in enumerate(cells):
        cell_key = _normalize_cell_lookup_key(cell)
        meta = meta_map.get(cell_key)
        if meta is None:
            continue
        matched += 1
        sample_name = meta["sample_name"]
        if sample_name not in sample_map:
            sample_map[sample_name] = {
                "sample_name": sample_name,
                "group": meta["group"] or infer_group(sample_name),
                "cell_count": 0,
                "column_indexes": [],
                "cell_ids": [],
                "metadata_member": metadata_member_name,
            }
        sample_map[sample_name]["cell_count"] += 1
        sample_map[sample_name]["column_indexes"].append(index)
        sample_map[sample_name]["cell_ids"].append(cell)

    if matched == 0 or len(sample_map) <= 1:
        return []

    return list(sample_map.values())


def _load_sidecar_sample_groups(matrix_path: str, cells: list[str]) -> list[dict]:
    metadata_path = _find_sidecar_metadata_file(matrix_path)
    if not metadata_path:
        return []

    delimiter = _detect_delimiter(metadata_path)
    with _open_text(metadata_path) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = reader.fieldnames or []
        normalized = {str(name).strip().lower(): name for name in fieldnames}

        cell_id_col = (
            normalized.get("cell_id")
            or normalized.get("cellid")
            or normalized.get("cells")
            or normalized.get("cell")
            or normalized.get("barcode")
        )
        sample_col = (
            normalized.get("sample")
            or normalized.get("sample_id")
            or normalized.get("sampleid")
            or normalized.get("orig.ident")
            or normalized.get("orig_ident")
            or normalized.get("library")
            or normalized.get("library_id")
            or normalized.get("libraryidentity")
            or normalized.get("donor")
            or normalized.get("subject")
            or normalized.get("subject_id")
        )
        group_col = (
            normalized.get("condition")
            or normalized.get("conditions")
            or normalized.get("group")
            or normalized.get("status")
            or normalized.get("treatment")
        )

        if not cell_id_col:
            return []

        meta_map: OrderedDict[str, dict] = OrderedDict()
        unique_groups: OrderedDict[str, None] = OrderedDict()
        for row in reader:
            cell_id = _strip(str(row.get(cell_id_col, "")))
            sample_name = _strip(str(row.get(sample_col, ""))) if sample_col else ""
            group_value = _strip(str(row.get(group_col, ""))) if group_col else ""
            if not cell_id:
                continue

            if not sample_name and group_value:
                sample_name = group_value
            if not sample_name:
                continue

            if group_value:
                unique_groups[group_value] = None

            meta_map[_normalize_cell_lookup_key(cell_id)] = {
                "sample_name": sanitize_sample_name(sample_name),
                "group": group_value or infer_group(sample_name),
            }

    if not meta_map:
        return []

    sample_map = OrderedDict()
    matched = 0
    for index, cell in enumerate(cells):
        cell_key = _normalize_cell_lookup_key(cell)
        prefix = _normalize_cell_lookup_key(cell.split("_", 1)[0] if "_" in cell else cell)
        meta = meta_map.get(cell_key) or meta_map.get(prefix)
        if meta is None:
            continue
        matched += 1
        sample_name = meta["sample_name"]
        if sample_name not in sample_map:
            sample_map[sample_name] = {
                "sample_name": sample_name,
                "group": meta["group"] or infer_group(sample_name),
                "cell_count": 0,
                "column_indexes": [],
                "cell_ids": [],
                "metadata_path": metadata_path,
            }
        sample_map[sample_name]["cell_count"] += 1
        sample_map[sample_name]["column_indexes"].append(index)
        sample_map[sample_name]["cell_ids"].append(cell)

    if matched == 0 or len(sample_map) <= 1:
        return []

    unmatched_indexes = [
        idx for idx, cell in enumerate(cells)
        if (
            _normalize_cell_lookup_key(cell) not in meta_map
            and _normalize_cell_lookup_key(cell.split("_", 1)[0] if "_" in cell else cell) not in meta_map
        )
    ]
    if unmatched_indexes:
        fallback_name = sanitize_sample_name(_infer_matrix_sample_name(matrix_path) + "_unmapped")
        sample_map[fallback_name] = {
            "sample_name": fallback_name,
            "group": infer_group(fallback_name),
            "cell_count": len(unmatched_indexes),
            "column_indexes": unmatched_indexes,
            "cell_ids": [cells[idx] for idx in unmatched_indexes],
            "metadata_path": metadata_path,
        }

    return list(sample_map.values())


def _count_member_cells(archive: tarfile.TarFile, member: tarfile.TarInfo) -> int:
    with _open_tar_member_text(archive, member) as handle:
        first_line = handle.readline()
        second_line = handle.readline()
    profile = _profile_matrix_preview(first_line, second_line)
    if profile["orientation"] == "cell_by_gene":
        return max(_count_member_lines(archive, member) - 1, 0)
    header = profile["header_fields"]
    if not header or len(header) < 2:
        return 0
    return max(len(header) - 1, 0)


def _count_member_lines(archive: tarfile.TarFile, member: tarfile.TarInfo) -> int:
    count = 0
    with _open_tar_member_text(archive, member) as handle:
        for line in handle:
            if str(line).strip():
                count += 1
    return count


def _read_mtx_dimensions(archive: tarfile.TarFile, member: tarfile.TarInfo) -> tuple[int, int]:
    with _open_tar_member_text(archive, member) as handle:
        for line in handle:
            text = str(line).strip()
            if not text or text.startswith('%'):
                continue
            parts = text.split()
            if len(parts) >= 3:
                try:
                    n_genes = int(parts[0])
                    n_cells = int(parts[1])
                    return n_genes, n_cells
                except ValueError:
                    continue
    return 0, 0


def _strip_known_suffixes(name: str) -> str:
    lower = name.lower()
    suffixes = [
        "barcodes.tsv.gz", "barcodes.tsv",
        "features.tsv.gz", "features.tsv",
        "genes.tsv.gz", "genes.tsv",
        "matrix.mtx.gz", "matrix.mtx",
        "_barcodes.tsv.gz", "_barcodes.tsv",
        "_features.tsv.gz", "_features.tsv",
        "_genes.tsv.gz", "_genes.tsv",
        "_matrix.mtx.gz", "_matrix.mtx",
        "-barcodes.tsv.gz", "-barcodes.tsv",
        "-features.tsv.gz", "-features.tsv",
        "-genes.tsv.gz", "-genes.tsv",
        "-matrix.mtx.gz", "-matrix.mtx",
    ]
    for suffix in suffixes:
        if lower.endswith(suffix):
            return name[:-len(suffix)]
    return name


def _find_first_exact_or_suffix(path: str, exact_names: tuple[str, ...], suffix_names: tuple[str, ...]) -> str:
    entries = [
        name for name in os.listdir(path)
        if os.path.isfile(os.path.join(path, name)) and not _is_ignored_auxiliary_name(name)
    ]
    lower_map = {name.lower(): name for name in entries}
    for candidate in exact_names:
        matched = lower_map.get(candidate.lower())
        if matched:
            return os.path.join(path, matched)

    lower_entries = [name.lower() for name in entries]
    for suffix in suffix_names:
        suffix = suffix.lower()
        for idx, lower_name in enumerate(lower_entries):
            if lower_name.endswith(suffix):
                return os.path.join(path, entries[idx])
    return ""


def detect_10x_barcode_suffix_groups(path: str) -> list[dict]:
    """Detect multiplexed 10X libraries mixed in one folder via barcode suffixes (-1/-2/...)."""
    if not path or not os.path.isdir(path):
        return []

    barcode_path = _find_first_exact_or_suffix(
        path,
        ("barcodes.tsv.gz", "barcodes.tsv"),
        ("_barcodes.tsv.gz", "_barcodes.tsv"),
    )
    if not barcode_path:
        return []

    counts: OrderedDict[str, int] = OrderedDict()
    with _open_text(barcode_path) as handle:
        for line in handle:
            barcode = line.strip()
            if not barcode:
                continue
            match = re.search(r"-(\d+)$", barcode)
            if not match:
                return []
            suffix = match.group(1)
            counts[suffix] = counts.get(suffix, 0) + 1

    if len(counts) <= 1:
        return []

    def _sort_key(item):
        suffix = item[0]
        return (0, int(suffix)) if suffix.isdigit() else (1, suffix)

    return [
        {"suffix": suffix, "cell_count": cell_count}
        for suffix, cell_count in sorted(counts.items(), key=_sort_key)
    ]


def _infer_bundle_sample_name(member_name: str) -> str:
    normalized = member_name.replace("\\", "/").strip("/")
    if not normalized:
        return ""

    parts = normalized.split("/")
    base = parts[-1]
    lower = base.lower()
    if lower in {
        "barcodes.tsv.gz", "barcodes.tsv",
        "features.tsv.gz", "features.tsv",
        "genes.tsv.gz", "genes.tsv",
        "matrix.mtx.gz", "matrix.mtx",
    } and len(parts) >= 2:
        return sanitize_sample_name(parts[-2])

    return sanitize_sample_name(_strip_known_suffixes(base))


def _infer_matrix_sample_name(path: str) -> str:
    base = os.path.basename(path)
    lower = base.lower()
    for suffix in (".csv.gz", ".tsv.gz", ".txt.gz", ".csv", ".tsv", ".txt"):
        if lower.endswith(suffix):
            base = base[:-len(suffix)]
            break

    base = re.sub(
        r'[-_ ]?(raw|norm|normalized|counts|expression|matrix|rna|rnacounts)+$',
        '',
        base,
        flags=re.IGNORECASE,
    )
    base = re.sub(r'[_-]+$', '', base)
    return sanitize_sample_name(base or "sample")


def _infer_archive_base_name(path: str) -> str:
    base = os.path.basename(path)
    lower = base.lower()
    for suffix in (".tar.gz", ".tgz", ".tar", ".rar"):
        if lower.endswith(suffix):
            base = base[:-len(suffix)]
            break
    base = re.sub(r'[_-]?matrix$', '', base, flags=re.IGNORECASE)
    return sanitize_sample_name(base or "sample")


def _infer_sample_group(sample_name: str) -> str:
    if "_" in sample_name:
        tail = sanitize_sample_name(sample_name.rsplit("_", 1)[-1])
        if tail and any(ch.isalpha() for ch in tail) and tail.lower() not in {"matrix", "counts", "raw", "norm", "normalized", "expression"}:
            return tail
    return infer_group(sample_name)


def _run_system_tar_extract(archive_path: str, output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    archive_literal = archive_path.replace("'", "''")
    output_literal = output_dir.replace("'", "''")
    ps_script = (
        f"$archive='{archive_literal}'; "
        f"$out='{output_literal}'; "
        "if (!(Test-Path -LiteralPath $out)) { New-Item -ItemType Directory -Path $out | Out-Null }; "
        "tar -xf $archive -C $out"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=SUBPROCESS_NO_WINDOW,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or "unknown tar extraction error"
        raise RuntimeError(f"Unable to extract archive: {detail}")


def _make_archive_temp_dir(prefix: str) -> str:
    base_dir = os.path.join(tempfile.gettempdir(), "scflow_archive_runtime")
    os.makedirs(base_dir, exist_ok=True)
    name = prefix.rstrip("_")
    candidate = os.path.join(base_dir, f"{name}_{next(tempfile._get_candidate_names())}")
    os.makedirs(candidate, exist_ok=True)
    return candidate


def _detect_tar_10x_samples(archive: tarfile.TarFile, members: list[tarfile.TarInfo]) -> list[dict]:
    grouped = OrderedDict()
    for member in members:
        if _is_ignored_auxiliary_name(member.name):
            continue
        base = os.path.basename(member.name)
        lower = base.lower()
        kind = None
        canonical_name = None
        if lower.endswith(("barcodes.tsv.gz", "barcodes.tsv")):
            kind = "barcodes"
            canonical_name = "barcodes.tsv.gz" if lower.endswith(".gz") else "barcodes.tsv"
        elif lower.endswith(("features.tsv.gz", "features.tsv")):
            kind = "features"
            canonical_name = "features.tsv.gz" if lower.endswith(".gz") else "features.tsv"
        elif lower.endswith(("genes.tsv.gz", "genes.tsv")):
            kind = "features"
            canonical_name = "genes.tsv.gz" if lower.endswith(".gz") else "genes.tsv"
        elif lower.endswith(("matrix.mtx.gz", "matrix.mtx")):
            kind = "matrix"
            canonical_name = "matrix.mtx.gz" if lower.endswith(".gz") else "matrix.mtx"

        if kind is None:
            continue

        sample_name = _infer_bundle_sample_name(member.name)
        if not sample_name:
            continue
        grouped.setdefault(sample_name, {})
        grouped[sample_name][kind] = {
            "member_name": member.name,
            "canonical_name": canonical_name,
        }

    detected = []
    for sample_name, bundle in grouped.items():
        if "matrix" not in bundle or "barcodes" not in bundle or "features" not in bundle:
            continue
        matrix_member = archive.getmember(bundle["matrix"]["member_name"])
        n_genes, n_cells = _read_mtx_dimensions(archive, matrix_member)
        if n_genes <= 0 or n_cells <= 0:
            barcodes_member = archive.getmember(bundle["barcodes"]["member_name"])
            features_member = archive.getmember(bundle["features"]["member_name"])
            n_cells = _count_member_lines(archive, barcodes_member)
            n_genes = _count_member_lines(archive, features_member)
        detected.append({
            "sample_name": sample_name,
            "group": infer_group(sample_name),
            "cell_count": n_cells,
            "gene_count": n_genes,
            "archive_members": {
                "matrix": bundle["matrix"]["member_name"],
                "barcodes": bundle["barcodes"]["member_name"],
                "features": bundle["features"]["member_name"],
            },
            "archive_target_names": {
                "matrix": bundle["matrix"]["canonical_name"],
                "barcodes": bundle["barcodes"]["canonical_name"],
                "features": bundle["features"]["canonical_name"],
            },
            "data_type": "10X Matrix Folder",
        })
    return detected


def _detect_tar_sparse_bundle_with_metadata(archive: tarfile.TarFile, members: list[tarfile.TarInfo]) -> list[dict]:
    matrix_member = None
    barcodes_member = None
    features_member = None
    metadata_member = None

    for member in members:
        base = os.path.basename(member.name).lower()
        if _is_ignored_auxiliary_name(base):
            continue
        if matrix_member is None and base.endswith(("count_matrix_sparse.mtx", "matrix.mtx", "matrix.mtx.gz")):
            matrix_member = member.name
        elif barcodes_member is None and base.endswith(("count_matrix_barcodes.tsv", "barcodes.tsv", "barcodes.tsv.gz")):
            barcodes_member = member.name
        elif features_member is None and base.endswith(("count_matrix_genes.tsv", "count_matrix_features.tsv", "genes.tsv", "features.tsv", "genes.tsv.gz", "features.tsv.gz")):
            features_member = member.name
        elif metadata_member is None and base.endswith(("metadata.csv", "metadata.tsv", "metadata.csv.gz", "metadata.tsv.gz")):
            metadata_member = member.name

    if not (matrix_member and barcodes_member and features_member and metadata_member):
        return []

    cells = _extract_tar_member_lines(archive, barcodes_member)
    metadata_groups = _load_tar_metadata_groups(archive, metadata_member, cells)
    if not metadata_groups:
        return []

    matrix_tarinfo = archive.getmember(matrix_member)
    n_genes, n_cells = _read_mtx_dimensions(archive, matrix_tarinfo)
    if n_genes <= 0:
        n_genes = len(_extract_tar_member_lines(archive, features_member))
    if n_cells <= 0:
        n_cells = len(cells)

    samples = []
    for sample in metadata_groups:
        samples.append({
            "sample_name": sample["sample_name"],
            "group": sample["group"],
            "cell_count": sample["cell_count"],
            "gene_count": n_genes,
            "column_indexes": sample.get("column_indexes", []),
            "cell_ids": sample.get("cell_ids", []),
            "archive_bundle_members": {
                "matrix": matrix_member,
                "barcodes": barcodes_member,
                "features": features_member,
                "metadata": metadata_member,
            },
            "data_type": "10X Matrix Folder",
        })
    return samples


def _open_nested_tar_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> tarfile.TarFile:
    extracted = archive.extractfile(member)
    if extracted is None:
        raise FileNotFoundError(f'Unable to read tar member: {member.name}')
    payload = extracted.read()
    return tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz')


def _detect_nested_tar_10x_samples(archive: tarfile.TarFile, members: list[tarfile.TarInfo]) -> list[dict]:
    detected = []
    nested_members = [
        m for m in members
        if m.name.lower().endswith(('.tar.gz', '.tgz')) and not _is_ignored_auxiliary_name(m.name)
    ]
    for nested_member in nested_members:
        try:
            with _open_nested_tar_member(archive, nested_member) as inner_archive:
                inner_files = [m for m in inner_archive.getmembers() if m.isfile()]
                inner_detected = _detect_tar_10x_samples(inner_archive, inner_files)
                for sample in inner_detected:
                    sample['nested_archive_member'] = nested_member.name
                    detected.append(sample)
        except (tarfile.TarError, OSError):
            continue
    return detected


def detect_matrix_samples(path: str) -> dict:
    with _open_text(path) as handle:
        first_line = handle.readline()
        second_line = handle.readline()
    profile = _profile_matrix_preview(first_line, second_line)
    header = profile["header_fields"]
    if len(header) < 2:
        raise ValueError('The file header has fewer than two columns and cannot be recognized as a gene-by-cell expression matrix.')

    if profile["orientation"] == "cell_by_gene":
        barcode_ids = []
        with _open_text(path) as handle:
            next(handle, None)
            for line in handle:
                fields = _split_preview_fields(line, profile["delimiter"])
                if fields:
                    barcode_ids.append(fields[0])
        cell_count = len(barcode_ids)
        gene_count = max(len(header) - profile["metadata_columns"], 0)
        sample_name = _infer_matrix_sample_name(path)
        suffix_groups = _detect_suffix_groups_from_cells(barcode_ids)
        if not suffix_groups:
            suffix_groups = _detect_named_suffix_groups_from_cells(barcode_ids)
        if suffix_groups:
            samples = []
            for item in suffix_groups:
                suffix = item["suffix"]
                samples.append({
                    'sample_name': f'{sample_name}_{suffix}',
                    'group': _infer_sample_group(f'{sample_name}_{suffix}'),
                    'cell_count': item["cell_count"],
                    'gene_count': gene_count,
                    'split_suffix': suffix,
                    'column_indexes': [],
                    'cell_ids': [],
                })
            return {
                'source_type': 'shared_matrix_suffix_groups',
                'delimiter': profile["delimiter"],
                'cell_count': cell_count,
                'sample_count': len(samples),
                'samples': samples,
            }
        return {
            'source_type': 'single_matrix',
            'delimiter': profile["delimiter"],
            'cell_count': cell_count,
            'sample_count': 1,
            'samples': [{
                'sample_name': sample_name,
                'group': infer_group(sample_name),
                'cell_count': cell_count,
                'gene_count': gene_count,
                'column_indexes': [],
                'cell_ids': [],
            }],
        }

    cell_start = max(int(profile["metadata_columns"]), 1)
    cells = [_strip(cell) for cell in header[cell_start:]]
    if not cells:
        raise ValueError('No cell columns were detected.')

    metadata_groups = _load_sidecar_sample_groups(path, cells)
    if metadata_groups:
        return {
            'source_type': 'single_matrix_metadata_groups',
            'delimiter': profile["delimiter"],
            'cell_count': len(cells),
            'sample_count': len(metadata_groups),
            'samples': metadata_groups,
        }

    grouped_keys = []
    for cell in cells:
        sample_key = cell.rsplit('_', 1)[0] if '_' in cell else cell
        grouped_keys.append(sample_key)

    unique_keys = list(OrderedDict.fromkeys(grouped_keys).keys())
    single_sample_mode = (
        len(unique_keys) == len(cells)
        or len(unique_keys) / max(len(cells), 1) > 0.8
    )

    sample_map = OrderedDict()
    if single_sample_mode:
        sample_name = _infer_matrix_sample_name(path)
        suffix_groups = _detect_suffix_groups_from_cells(cells)
        if not suffix_groups:
            suffix_groups = _detect_named_suffix_groups_from_cells(cells)
        if suffix_groups:
            samples = []
            for item in suffix_groups:
                suffix = item["suffix"]
                indexes = [
                    idx for idx, cell in enumerate(cells)
                    if re.search(rf"[_-]{re.escape(suffix)}$", cell)
                ]
                samples.append({
                    'sample_name': f'{sample_name}_{suffix}',
                    'group': _infer_sample_group(f'{sample_name}_{suffix}'),
                    'cell_count': len(indexes),
                    'column_indexes': indexes,
                    'cell_ids': [cells[idx] for idx in indexes],
                    'split_suffix': suffix,
                })
            return {
                'source_type': 'single_matrix_suffix_groups',
                'delimiter': profile["delimiter"],
                'cell_count': len(cells),
                'sample_count': len(samples),
                'samples': samples,
            }
        sample_map[sample_name] = {
            'sample_name': sample_name,
            'group': infer_group(sample_name),
            'cell_count': len(cells),
            'column_indexes': list(range(len(cells))),
            'cell_ids': cells,
        }
    else:
        for index, cell in enumerate(cells):
            sample_key = grouped_keys[index]
            if sample_key not in sample_map:
                sample_map[sample_key] = {
                    'sample_name': sample_key,
                    'group': infer_group(sample_key),
                    'cell_count': 0,
                    'column_indexes': [],
                    'cell_ids': [],
                }
            sample_map[sample_key]['cell_count'] += 1
            sample_map[sample_key]['column_indexes'].append(index)
            sample_map[sample_key]['cell_ids'].append(cell)

    return {
        'source_type': 'single_matrix',
        'delimiter': profile["delimiter"],
        'cell_count': len(cells),
        'sample_count': len(sample_map),
        'samples': list(sample_map.values()),
    }


def detect_tar_samples(path: str) -> dict:
    if not tarfile.is_tarfile(path):
        raise ValueError('This is not a valid tar file.')

    sample_map = OrderedDict()
    with tarfile.open(path, 'r:*') as archive:
        members = [m for m in archive.getmembers() if m.isfile() and not _is_ignored_auxiliary_name(m.name)]
        sparse_bundle_samples = _detect_tar_sparse_bundle_with_metadata(archive, members)
        if sparse_bundle_samples:
            total_cells = sum(sample.get('cell_count', 0) for sample in sparse_bundle_samples)
            return {
                'source_type': 'tar_sparse_bundle_metadata',
                'cell_count': total_cells,
                'sample_count': len(sparse_bundle_samples),
                'samples': sparse_bundle_samples,
            }
        tenx_samples = _detect_tar_10x_samples(archive, members)
        if tenx_samples:
            archive_name = _infer_archive_base_name(path)
            if len(tenx_samples) == 1 and tenx_samples[0].get('sample_name') == 'sample':
                tenx_samples[0]['sample_name'] = archive_name
                tenx_samples[0]['group'] = infer_group(archive_name)
            total_cells = sum(sample.get('cell_count', 0) for sample in tenx_samples)
            return {
                'source_type': 'tar_10x_archive',
                'cell_count': total_cells,
                'sample_count': len(tenx_samples),
                'samples': tenx_samples,
            }
        nested_tenx_samples = _detect_nested_tar_10x_samples(archive, members)
        if nested_tenx_samples:
            for sample in nested_tenx_samples:
                nested_name = sample.get('nested_archive_member', '')
                if sample.get('sample_name') == 'sample' and nested_name:
                    inferred = _infer_archive_base_name(nested_name)
                    sample['sample_name'] = inferred
                    sample['group'] = infer_group(inferred)
            total_cells = sum(sample.get('cell_count', 0) for sample in nested_tenx_samples)
            return {
                'source_type': 'nested_tar_10x_archive',
                'cell_count': total_cells,
                'sample_count': len(nested_tenx_samples),
                'samples': nested_tenx_samples,
            }
        raw_candidates = [
            m for m in members
            if m.name.lower().endswith(('.csv.gz', '.tsv.gz', '.txt.gz', '.csv', '.tsv', '.txt'))
            and 'raw_count' in os.path.basename(m.name).lower()
        ]
        if not raw_candidates:
            raw_candidates = [
                m for m in members
                if m.name.lower().endswith(('.csv.gz', '.tsv.gz', '.txt.gz', '.csv', '.tsv', '.txt'))
                and 'norm_count' not in os.path.basename(m.name).lower()
            ]
        if not raw_candidates:
            raise ValueError('No importable raw count matrix file was detected inside the tar archive.')

        total_cells = 0
        for member in sorted(raw_candidates, key=lambda item: item.name):
            member_name = member.name
            base = os.path.basename(member_name)
            sample_name = _infer_matrix_sample_name(base)
            with _open_tar_member_text(archive, member) as handle:
                first_line = handle.readline()
                second_line = handle.readline()
            profile = _profile_matrix_preview(first_line, second_line)
            if profile["orientation"] == "cell_by_gene":
                cell_count = max(_count_member_lines(archive, member) - 1, 0)
                gene_count = max(len(profile["header_fields"]) - profile["metadata_columns"], 0)
            else:
                cell_count = _count_member_cells(archive, member)
                gene_count = 0
            total_cells += cell_count
            sample_map[sample_name] = {
                'sample_name': sample_name,
                'group': infer_group(sample_name),
                'cell_count': cell_count,
                'gene_count': gene_count,
                'archive_member': member_name,
                'data_type': 'Expression Matrix File',
            }

    return {
        'source_type': 'tar_archive',
        'cell_count': total_cells,
        'sample_count': len(sample_map),
        'samples': list(sample_map.values()),
    }


def detect_rar_samples(path: str, progress_callback=None) -> dict:
    temp_dir = _make_archive_temp_dir('scflow_rar_detect_')
    try:
        if progress_callback is not None:
            progress_callback("Reading RAR archive structure...")
        _run_system_tar_extract(path, temp_dir)

        inner_tar_paths = []
        matrix_files = []
        for root, _, files in os.walk(temp_dir):
            for name in files:
                if _is_ignored_auxiliary_name(name):
                    continue
                lower = name.lower()
                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, temp_dir).replace("\\", "/")
                if lower.endswith(('.tar', '.tar.gz', '.tgz')):
                    inner_tar_paths.append((rel_path, full_path))
                elif lower.endswith(SUPPORTED_MATRIX_EXTENSIONS):
                    matrix_files.append((rel_path, full_path))

        detected_samples = []
        if inner_tar_paths:
            total_archives = len(inner_tar_paths)
            for idx, (rel_path, full_path) in enumerate(sorted(inner_tar_paths, key=lambda item: item[0]), start=1):
                if progress_callback is not None:
                    progress_callback(f"Parsing nested sample archive {idx}/{total_archives}: {os.path.basename(rel_path)}")
                try:
                    detected = detect_tar_samples(full_path)
                except Exception:
                    continue
                for sample in detected.get('samples', []):
                    clone = dict(sample)
                    clone['rar_inner_archive'] = rel_path
                    if clone.get('sample_name') == 'sample':
                        inferred = _infer_archive_base_name(rel_path)
                        clone['sample_name'] = inferred
                        clone['group'] = infer_group(inferred)
                    detected_samples.append(clone)

            if detected_samples:
                if progress_callback is not None:
                    progress_callback(f"Detected {len(detected_samples)} samples. Preparing import results...")
                total_cells = sum(sample.get('cell_count', 0) for sample in detected_samples)
                return {
                    'source_type': 'rar_nested_archive',
                    'cell_count': total_cells,
                    'sample_count': len(detected_samples),
                    'samples': detected_samples,
                }

        if len(matrix_files) == 1:
            _, matrix_path = matrix_files[0]
            return detect_matrix_samples(matrix_path)

        raise ValueError('No importable matrix file or 10X archive was detected inside the rar archive.')
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def ensure_unique_names(samples: Iterable[dict]) -> list[dict]:
    used = {}
    result = []
    for sample in samples:
        name = sample['sample_name']
        base = name
        suffix = 2
        while name in used:
            name = f'{base}_{suffix}'
            suffix += 1
        used[name] = True
        clone = dict(sample)
        clone['sample_name'] = name
        result.append(clone)
    return result


def split_matrix_by_samples(
    input_path: str,
    samples: list[dict],
    output_dir: str,
    progress_callback=None,
    progress_every: int = 200,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    delimiter = _detect_delimiter(input_path)
    samples = ensure_unique_names(samples)

    outputs = []
    writers = []
    handles = []
    try:
        for sample in samples:
            safe_name = sanitize_sample_name(sample['sample_name'])
            out_path = os.path.join(output_dir, f'{safe_name}.tsv.gz')
            handle = gzip.open(out_path, 'wt', encoding='utf-8', newline='')
            writer = csv.writer(handle, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
            header = ['gene'] + list(sample['cell_ids'])
            writer.writerow(header)
            handles.append(handle)
            writers.append((writer, sample['column_indexes']))
            outputs.append({
                'sample_name': sample['sample_name'],
                'group': sample['group'],
                'cell_count': sample['cell_count'],
                'data_type': 'Expression Matrix TSV',
                'data_path': out_path,
            })

        with _open_text(input_path) as source_handle:
            reader = csv.reader(source_handle, delimiter=delimiter)
            header = next(reader)
            preview_first = delimiter.join(header)
            first_row = next(reader, None)
            preview_second = delimiter.join(first_row) if first_row else ""
            profile = _profile_matrix_preview(preview_first, preview_second)
            metadata_offset = max(int(profile["metadata_columns"]) - 1, 0)
            processed_rows = 0
            row_iter = itertools.chain([first_row], reader) if first_row else reader
            for row in row_iter:
                if not row:
                    continue
                gene = _strip(row[0])
                values = row[1 + metadata_offset:]
                for writer, indexes in writers:
                    writer.writerow([gene] + [values[i] if i < len(values) else '0' for i in indexes])
                processed_rows += 1
                if progress_callback is not None and processed_rows % max(progress_every, 1) == 0:
                    progress_callback(processed_rows)
    finally:
        for handle in handles:
            handle.close()

    return outputs


def extract_tar_samples(
    archive_path: str,
    samples: list[dict],
    output_dir: str,
    progress_callback=None,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    samples = ensure_unique_names(samples)
    outputs = []
    with tarfile.open(archive_path, 'r:*') as archive:
        members = {m.name: m for m in archive.getmembers() if m.isfile()}
        bundle_members = samples[0].get('archive_bundle_members') if samples else None
        if bundle_members:
            matrix_member = members.get(bundle_members.get("matrix", ""))
            barcodes_member = members.get(bundle_members.get("barcodes", ""))
            features_member = members.get(bundle_members.get("features", ""))
            metadata_member = members.get(bundle_members.get("metadata", ""))
            if not (matrix_member and barcodes_member and features_member and metadata_member):
                raise FileNotFoundError('The tar archive is missing files required for the sparse matrix bundle.')

            feature_lines = _extract_tar_member_lines(archive, features_member.name)
            barcode_lines = _extract_tar_member_lines(archive, barcodes_member.name)
            n_genes = len(feature_lines)
            feature_target_name = 'genes.tsv.gz' if 'gene' in os.path.basename(features_member.name).lower() else 'features.tsv.gz'

            sample_dirs = []
            coord_temp_paths = []
            coord_counts = []
            sample_cells = []
            col_maps = []

            for sample in samples:
                safe_name = sanitize_sample_name(sample['sample_name'])
                sample_dir = os.path.join(output_dir, safe_name)
                os.makedirs(sample_dir, exist_ok=True)
                sample_dirs.append(sample_dir)
                coord_temp_paths.append(os.path.join(sample_dir, '_matrix_coords.tmp'))
                coord_counts.append(0)
                indexes = list(sample.get('column_indexes', []))
                sample_cells.append([barcode_lines[idx] for idx in indexes if idx < len(barcode_lines)])
                col_maps.append({orig + 1: new_idx + 1 for new_idx, orig in enumerate(indexes)})

                feature_payload = '\n'.join(feature_lines)
                if feature_lines:
                    feature_payload += '\n'
                with gzip.open(os.path.join(sample_dir, feature_target_name), 'wt', encoding='utf-8', newline='') as handle:
                    handle.write(feature_payload)
                alt_feature_name = 'features.tsv.gz' if feature_target_name == 'genes.tsv.gz' else 'genes.tsv.gz'
                with gzip.open(os.path.join(sample_dir, alt_feature_name), 'wt', encoding='utf-8', newline='') as handle:
                    handle.write(feature_payload)
                with gzip.open(os.path.join(sample_dir, 'barcodes.tsv.gz'), 'wt', encoding='utf-8', newline='') as handle:
                    handle.write('\n'.join(sample_cells[-1]))
                    if sample_cells[-1]:
                        handle.write('\n')

            coord_handles = [open(path, 'w', encoding='utf-8', newline='') for path in coord_temp_paths]
            try:
                with _open_tar_member_text(archive, matrix_member) as handle:
                    header_seen = False
                    for raw_line in handle:
                        text = raw_line.strip()
                        if not text or text.startswith('%'):
                            continue
                        if not header_seen:
                            header_seen = True
                            continue
                        parts = text.split()
                        if len(parts) < 3:
                            continue
                        row_idx = int(parts[0])
                        col_idx = int(parts[1])
                        value = parts[2]
                        for sample_index, col_map in enumerate(col_maps):
                            new_col = col_map.get(col_idx)
                            if new_col is None:
                                continue
                            coord_handles[sample_index].write(f"{row_idx} {new_col} {value}\n")
                            coord_counts[sample_index] += 1
            finally:
                for handle in coord_handles:
                    handle.close()

            total = len(samples)
            for index, sample in enumerate(samples, start=1):
                sample_dir = sample_dirs[index - 1]
                matrix_out = os.path.join(sample_dir, 'matrix.mtx.gz')
                with gzip.open(matrix_out, 'wt', encoding='utf-8', newline='') as out_handle:
                    out_handle.write('%%MatrixMarket matrix coordinate integer general\n')
                    out_handle.write('%\n')
                    out_handle.write(f"{n_genes} {len(sample_cells[index - 1])} {coord_counts[index - 1]}\n")
                    with open(coord_temp_paths[index - 1], 'r', encoding='utf-8', newline='') as coord_handle:
                        shutil.copyfileobj(coord_handle, out_handle)
                try:
                    os.remove(coord_temp_paths[index - 1])
                except OSError:
                    pass

                outputs.append({
                    'sample_name': sample['sample_name'],
                    'group': sample['group'],
                    'cell_count': sample.get('cell_count', 0),
                    'gene_count': sample.get('gene_count', n_genes),
                    'data_type': '10X Matrix Folder',
                    'data_path': sample_dir,
                })
                if progress_callback is not None:
                    progress_callback(index, total, sample['sample_name'])
            return outputs

        total = len(samples)
        for index, sample in enumerate(samples, start=1):
            safe_name = sanitize_sample_name(sample['sample_name'])
            archive_members = sample.get('archive_members') or {}
            if archive_members:
                sample_dir = os.path.join(output_dir, safe_name)
                os.makedirs(sample_dir, exist_ok=True)
                target_names = sample.get('archive_target_names') or {}
                nested_archive_name = sample.get('nested_archive_member', '')
                if nested_archive_name:
                    nested_member = members.get(nested_archive_name)
                    if nested_member is None:
                        raise FileNotFoundError(f'The tar archive is missing the nested archive: {nested_archive_name}')
                    with _open_nested_tar_member(archive, nested_member) as inner_archive:
                        inner_members = {m.name: m for m in inner_archive.getmembers() if m.isfile()}
                        for kind in ('matrix', 'features', 'barcodes'):
                            member_name = archive_members.get(kind, '')
                            member = inner_members.get(member_name)
                            if member is None:
                                raise FileNotFoundError(f'The nested tar archive is missing file: {member_name}')
                            target_name = target_names.get(kind)
                            if not target_name:
                                original_name = os.path.basename(member_name)
                                target_name = original_name
                            out_path = os.path.join(sample_dir, target_name)
                            with inner_archive.extractfile(member) as src, open(out_path, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
                else:
                    for kind in ('matrix', 'features', 'barcodes'):
                        member_name = archive_members.get(kind, '')
                        member = members.get(member_name)
                        if member is None:
                            raise FileNotFoundError(f'The tar archive is missing file: {member_name}')
                        target_name = target_names.get(kind)
                        if not target_name:
                            original_name = os.path.basename(member_name)
                            target_name = original_name
                        out_path = os.path.join(sample_dir, target_name)
                        with archive.extractfile(member) as src, open(out_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                outputs.append({
                    'sample_name': sample['sample_name'],
                    'group': sample['group'],
                    'cell_count': sample.get('cell_count', 0),
                    'data_type': '10X Matrix Folder',
                    'data_path': sample_dir,
                })
            else:
                member_name = sample.get('archive_member', '')
                member = members.get(member_name)
                if member is None:
                    raise FileNotFoundError(f'The tar archive is missing file: {member_name}')
                original_name = os.path.basename(member_name)
                lower_name = original_name.lower()
                if lower_name.endswith('.csv.gz'):
                    suffix = '.csv.gz'
                elif lower_name.endswith('.tsv.gz'):
                    suffix = '.tsv.gz'
                elif lower_name.endswith('.txt.gz'):
                    suffix = '.txt.gz'
                elif lower_name.endswith('.csv'):
                    suffix = '.csv'
                elif lower_name.endswith('.tsv'):
                    suffix = '.tsv'
                elif lower_name.endswith('.h5'):
                    suffix = '.h5'
                else:
                    suffix = '.txt'
                out_path = os.path.join(output_dir, f'{safe_name}{suffix}')
                with archive.extractfile(member) as src, open(out_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                outputs.append({
                    'sample_name': sample['sample_name'],
                    'group': sample['group'],
                    'cell_count': sample.get('cell_count', 0),
                    'data_type': sample.get('data_type', 'Expression Matrix File'),
                    'data_path': out_path,
                })
            if progress_callback is not None:
                progress_callback(index, total, sample['sample_name'])
    return outputs


def extract_rar_samples(
    archive_path: str,
    samples: list[dict],
    output_dir: str,
    progress_callback=None,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    samples = ensure_unique_names(samples)
    temp_dir = _make_archive_temp_dir('scflow_rar_extract_')
    try:
        if progress_callback is not None:
            progress_callback(0, len(samples), "Extracting outer RAR archive...")
        _run_system_tar_extract(archive_path, temp_dir)
        outputs = []
        total = len(samples)
        for index, sample in enumerate(samples, start=1):
            inner_rel = sample.get('rar_inner_archive', '')
            if not inner_rel:
                raise FileNotFoundError('The rar sample is missing nested archive location information.')
            inner_path = os.path.join(temp_dir, inner_rel.replace('/', os.sep))
            if not os.path.isfile(inner_path):
                raise FileNotFoundError(f'The nested archive is missing after rar extraction: {inner_rel}')
            outputs.extend(extract_tar_samples(inner_path, [sample], output_dir))
            if progress_callback is not None:
                progress_callback(index, total, sample['sample_name'])
        return outputs
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def import_rds_samples(
    input_path: str,
    samples: list[dict],
    output_dir: str,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    samples = ensure_unique_names(samples)
    outputs = []
    for sample in samples:
        safe_name = sanitize_sample_name(sample["sample_name"])
        out_path = os.path.join(output_dir, f"{safe_name}.rds")
        shutil.copy2(input_path, out_path)
        outputs.append({
            "sample_name": sample["sample_name"],
            "group": sample["group"],
            "cell_count": sample.get("cell_count", 0),
            "gene_count": sample.get("gene_count", 0),
            "data_type": "Seurat RDS",
            "data_path": out_path,
        })
    return outputs


def import_shared_matrix_samples(
    input_path: str,
    samples: list[dict],
    output_dir: str,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    samples = ensure_unique_names(samples)

    lower_name = os.path.basename(input_path).lower()
    if lower_name.endswith('.csv.gz'):
        suffix = '.csv.gz'
    elif lower_name.endswith('.tsv.gz'):
        suffix = '.tsv.gz'
    elif lower_name.endswith('.txt.gz'):
        suffix = '.txt.gz'
    elif lower_name.endswith('.csv'):
        suffix = '.csv'
    elif lower_name.endswith('.tsv'):
        suffix = '.tsv'
    else:
        suffix = '.txt'

    shared_name = sanitize_sample_name(_infer_matrix_sample_name(input_path)) + suffix
    shared_path = os.path.join(output_dir, shared_name)
    shutil.copy2(input_path, shared_path)

    outputs = []
    for sample in samples:
        outputs.append({
            'sample_name': sample['sample_name'],
            'group': sample['group'],
            'cell_count': sample.get('cell_count', 0),
            'gene_count': sample.get('gene_count', 0),
            'split_suffix': sample.get('split_suffix', ''),
            'data_type': 'Expression Matrix File',
            'data_path': shared_path,
        })
    return outputs


def split_sparse_bundle_folder(
    bundle_dir: str,
    samples: list[dict],
    output_dir: str,
    progress_callback=None,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    parsed = _parse_sparse_bundle_metadata(bundle_dir)
    samples = ensure_unique_names(samples)

    selected_libraries = OrderedDict()
    for sample in samples:
        library = sample.get('library_identity') or sample.get('sample_name')
        library = str(library).strip()
        if not library:
            raise ValueError('The sparse matrix bundle sample is missing library_identity.')
        selected_libraries[library] = sample

    genes = []
    with _open_text(parsed['genes_path']) as handle:
        next(handle, None)
        for line in handle:
            if not line.strip():
                continue
            fields = _split_preview_fields(line, '\t')
            gene_id = fields[0] if len(fields) >= 1 else ''
            gene_name = fields[1] if len(fields) >= 2 else gene_id
            genes.append((gene_id, gene_name, 'Gene Expression'))

    library_order = list(selected_libraries.keys())
    library_to_index = {library: idx for idx, library in enumerate(library_order)}
    sample_barcodes = [[] for _ in library_order]
    column_to_sample = [None]
    column_to_newcol = [0]
    cell_counts = [0 for _ in library_order]

    with _open_text(parsed['barcodes_path']) as handle:
        for column_index, raw_line in enumerate(handle, start=1):
            barcode = raw_line.strip()
            if not barcode:
                column_to_sample.append(None)
                column_to_newcol.append(0)
                continue
            library = barcode.split('_', 1)[0] if '_' in barcode else barcode
            sample_index = library_to_index.get(library)
            if sample_index is None:
                column_to_sample.append(None)
                column_to_newcol.append(0)
                continue
            cell_counts[sample_index] += 1
            sample_barcodes[sample_index].append(barcode)
            column_to_sample.append(sample_index)
            column_to_newcol.append(cell_counts[sample_index])

    matrix_path = parsed['matrix_path']
    matrix_size = max(os.path.getsize(matrix_path), 1)
    n_genes = len(genes)
    nnz_counts = [0 for _ in library_order]
    sample_dirs = []
    body_paths = []
    body_handles = []
    outputs = []
    try:
        for idx, library in enumerate(library_order):
            sample = selected_libraries[library]
            safe_name = sanitize_sample_name(sample['sample_name'])
            sample_dir = os.path.join(output_dir, safe_name)
            os.makedirs(sample_dir, exist_ok=True)
            sample_dirs.append(sample_dir)

            with gzip.open(os.path.join(sample_dir, 'barcodes.tsv.gz'), 'wt', encoding='utf-8', newline='') as handle:
                handle.write('\n'.join(sample_barcodes[idx]))
                handle.write('\n')

            with gzip.open(os.path.join(sample_dir, 'features.tsv.gz'), 'wt', encoding='utf-8', newline='') as handle:
                for gene_id, gene_name, feature_type in genes:
                    handle.write(f'{gene_id}\t{gene_name}\t{feature_type}\n')

            body_path = os.path.join(sample_dir, 'matrix.body.tmp')
            body_paths.append(body_path)
            body_handles.append(open(body_path, 'w', encoding='utf-8', newline=''))

            outputs.append({
                'sample_name': sample['sample_name'],
                'group': sample['group'],
                'cell_count': cell_counts[idx],
                'gene_count': n_genes,
                'data_type': '10X Matrix Folder',
                'data_path': sample_dir,
            })

        if progress_callback is not None:
            progress_callback(2, 'Splitting and writing sample matrices...')

        with open(matrix_path, 'rb') as raw_handle:
            with gzip.open(raw_handle, 'rt', encoding='utf-8', errors='replace', newline='') as handle:
                header_parsed = False
                for line in handle:
                    text = line.strip()
                    if not text or text.startswith('%'):
                        continue
                    if not header_parsed:
                        parts = text.split()
                        if len(parts) >= 2:
                            try:
                                n_genes = int(parts[0])
                            except ValueError:
                                pass
                        header_parsed = True
                        continue
                    parts = text.split()
                    if len(parts) < 3:
                        continue
                    try:
                        row_idx = int(parts[0])
                        col_idx = int(parts[1])
                    except ValueError:
                        continue
                    sample_index = column_to_sample[col_idx] if col_idx < len(column_to_sample) else None
                    if sample_index is None:
                        continue
                    new_col = column_to_newcol[col_idx]
                    body_handles[sample_index].write(f'{row_idx} {new_col} {parts[2]}\n')
                    nnz_counts[sample_index] += 1
                    if progress_callback is not None:
                        pct = 2 + int((raw_handle.tell() / matrix_size) * 88)
                        progress_callback(min(pct, 90), f'Writing sample matrix: {library_order[sample_index]}')
    finally:
        for handle in body_handles:
            handle.close()

    if progress_callback is not None:
        progress_callback(92, 'Finalizing matrix headers and compressing outputs...')

    for idx, sample_dir in enumerate(sample_dirs):
        final_matrix_path = os.path.join(sample_dir, 'matrix.mtx.gz')
        with gzip.open(final_matrix_path, 'wt', encoding='utf-8', newline='') as matrix_handle:
            matrix_handle.write('%%MatrixMarket matrix coordinate integer general\n')
            matrix_handle.write(f'{n_genes} {cell_counts[idx]} {nnz_counts[idx]}\n')
            with open(body_paths[idx], 'r', encoding='utf-8', newline='') as body_handle:
                shutil.copyfileobj(body_handle, matrix_handle)
        try:
            os.remove(body_paths[idx])
        except OSError:
            pass

    if progress_callback is not None:
        progress_callback(100, 'Sample splitting finished')

    return outputs
