"""Private PDF-7 dry-run that returns counts and never persists source data."""

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from partner_reports.integrations.advbox.client import AdvboxClient
from partner_reports.pdf_imports.parser import (
    LAYOUT_VERSION,
    PARSER_VERSION,
    ParsedManifest,
    parse_pdf_manifest,
)
from partner_reports.pdf_imports.reconciliation import (
    collect_verified_snapshot,
    reconcile_items,
    summarize,
)
from partner_reports.pdf_imports.validation import PdfRejected


@dataclass(frozen=True)
class PrivateCorpus:
    source_files: int
    unique_sources: int
    page_count: int
    manifest_items: int
    parser_version: str
    layout_version: str
    quality_flags: dict[str, int]
    rejected: dict[str, int]
    manifests: tuple[ParsedManifest, ...] = field(repr=False)


def inspect_private_corpus(input_directory: Path) -> PrivateCorpus:
    """Parse an ignored private directory without returning names, hashes, or source text."""

    directory = input_directory.resolve(strict=True)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("PDF7_PRIVATE_DIRECTORY_INVALID")
    paths = sorted(path for path in directory.iterdir() if path.is_file() and path.suffix == ".pdf")
    if not paths:
        raise ValueError("PDF7_PRIVATE_CORPUS_EMPTY")

    manifests: list[ParsedManifest] = []
    rejected: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    digests: set[str] = set()
    page_count = 0
    item_count = 0
    for path in paths:
        if path.is_symlink():
            rejected["PDF7_SYMLINK_REJECTED"] += 1
            continue
        try:
            content = path.read_bytes()
            manifest = parse_pdf_manifest(content)
        except (OSError, PdfRejected) as exc:
            code = exc.code if isinstance(exc, PdfRejected) else "PDF7_SOURCE_UNAVAILABLE"
            rejected[code] += 1
            continue
        digest = hashlib.sha256(content).hexdigest()
        digests.add(digest)
        manifests.append(manifest)
        page_count += manifest.page_count
        item_count += len(manifest.items)
        flags.update(manifest.quality_flags)
        for item in manifest.items:
            flags.update(item.quality_flags)

    return PrivateCorpus(
        source_files=len(paths),
        unique_sources=len(digests),
        page_count=page_count,
        manifest_items=item_count,
        parser_version=PARSER_VERSION,
        layout_version=LAYOUT_VERSION,
        quality_flags=dict(sorted(flags.items())),
        rejected=dict(sorted(rejected.items())),
        manifests=tuple(manifests),
    )


async def execute_private_dry_run(input_directory: Path, client: AdvboxClient) -> dict:
    """Reconcile real manifests in memory against a verified GET-only API snapshot."""

    corpus = inspect_private_corpus(input_directory)
    if corpus.rejected or len(corpus.manifests) != corpus.source_files:
        raise ValueError("PDF7_PRIVATE_CORPUS_REJECTED")
    snapshot = await collect_verified_snapshot(client)
    all_items = tuple(item for manifest in corpus.manifests for item in manifest.items)
    totals = asdict(summarize(reconcile_items(all_items, snapshot)))
    return {
        "mode": "pdf7_private_dry_run_no_persistence",
        "corpus": {
            "source_files": corpus.source_files,
            "unique_sources": corpus.unique_sources,
            "page_count": corpus.page_count,
            "manifest_items": corpus.manifest_items,
            "parser_version": corpus.parser_version,
            "layout_version": corpus.layout_version,
            "quality_flags": corpus.quality_flags,
            "rejected": corpus.rejected,
        },
        "api_snapshot": {"lawsuits": snapshot.total, "verified_reads": 2},
        "reconciliation": totals,
        "persistence": {
            "source_rows_written": 0,
            "api_rows_written": 0,
            "links_written": 0,
            "reports_generated": 0,
        },
    }
