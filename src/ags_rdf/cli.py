"""Command line interface: ``ags-rdf <command>`` (or ``python -m ags_rdf``).

Commands::

    ags-rdf releases                 list the dictionary releases found in the source
    ags-rdf fetch                    download (scrape) the AGS4 JSON from GitLab into the cache
    ags-rdf build                    generate TTL, N-Triples and VocExcel XLSX (+ validation, reports)
    ags-rdf check-pdf                compare the JSON with the published AGS dictionary PDF
    ags-rdf check-dictionary FILE    compare the JSON with an AGS standard dictionary (.ags) file

The source defaults to ``gitlab`` (https://gitlab.com/AGS-DFWG-Web/ASG4, branch
master). Use ``--source PATH`` for a local checkout, extracted archive or .zip.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import Settings


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--source", default="gitlab",
                   help="'gitlab', 'gitlab:<ref>', a local directory or a GitLab .zip (default: gitlab)")
    p.add_argument("--cache", type=Path, default=Path(".cache"), help="download cache (default: .cache)")
    p.add_argument("--no-history", action="store_true",
                   help="do not query GitLab for per-file commit dates (fewer API calls)")


def _snapshot(args):
    from .sources import load_snapshot

    return load_snapshot(args.source, args.cache, history=not args.no_history)


def cmd_releases(args) -> int:
    from .releases import discover_releases

    snap = _snapshot(args)
    print(f"Source: {snap.origin} commit={snap.commit or '?'} date={snap.committed_date or '?'}")
    for v, r in discover_releases(snap).items():
        print(f"  {v:7} {r.groups_and_headings}" + (f"  [{r.status}]" if r.status else ""))
    return 0


def cmd_fetch(args) -> int:
    snap = _snapshot(args)
    print(f"Snapshot of {snap.origin} at {snap.commit} in {snap.root} ({len(snap.files)} files)")
    return 0


def cmd_build(args) -> int:
    from .build import build_release, write_summary
    from .releases import discover_releases, select_releases

    settings = Settings.load(args.config, base_iri=args.base_iri)
    snap = _snapshot(args)
    releases = select_releases(discover_releases(snap), args.version)
    if not releases:
        print("No AGS4 dictionary releases found in the source", file=sys.stderr)
        return 2
    results = []
    for rel in releases:
        print(f"== AGS {rel.version}")
        r = build_release(snap, rel, args.out, settings, xlsx=not args.no_xlsx,
                          validate=not args.no_validate, examples=not args.no_examples)
        results.append(r)
        for x in r.results:
            print("  " + x.summary)
        print(f"  wrote {len(r.files)} files to {r.out_dir}")
    write_summary(results, args.out)
    failed = [r.version for r in results if not r.ok]
    if failed:
        print(f"Validation FAILED for {', '.join(failed)} - see reports/validation.md", file=sys.stderr)
        return 1
    return 0


def cmd_check_pdf(args) -> int:
    from .checks.pdf import compare_pdf
    from .releases import discover_releases

    snap = _snapshot(args)
    rel = discover_releases(snap)[args.version]
    if args.pdf:
        report = compare_pdf(snap, rel, args.pdf, label=args.pdf.name)
    else:
        report = compare_pdf(snap, rel, snap.path(args.pdf_path), label=snap.url_for(args.pdf_path))
    out = args.out / f"pdf-check-{args.version}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_markdown(), encoding="utf-8", newline="\n")
    print(report.summary())
    print(f"Report: {out}")
    return 0


def cmd_check_dictionary(args) -> int:
    from .checks.standard_dictionary import compare_standard_dictionary
    from .releases import discover_releases

    snap = _snapshot(args)
    rel = discover_releases(snap)[args.version]
    report = compare_standard_dictionary(snap, rel, args.file)
    out = args.out / f"standard-dictionary-check-{args.version}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_markdown(), encoding="utf-8", newline="\n")
    print(report.summary())
    print(f"Report: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ags-rdf", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"ags-rdf {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("releases", help="list releases found in the source")
    _common(p)
    p.set_defaults(func=cmd_releases)

    p = sub.add_parser("fetch", help="download the AGS4 JSON files into the cache")
    _common(p)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("build", help="generate RDF (ttl, nt) and VocExcel (xlsx) outputs")
    _common(p)
    p.add_argument("--release", "-r", dest="version", nargs="+", default=["latest"],
                   help="release(s) to build: 'latest' (default), 'all', or e.g. 4.1.1 4.2.0")
    p.add_argument("--out", type=Path, default=Path("dist"), help="output folder (default: dist)")
    p.add_argument("--config", type=Path, help="TOML settings file (see ags_rdf.config)")
    p.add_argument("--base-iri", help="base IRI for all generated identifiers")
    p.add_argument("--no-xlsx", action="store_true", help="skip VocExcel workbooks")
    p.add_argument("--no-validate", action="store_true", help="skip validation")
    p.add_argument("--no-examples", action="store_true",
                   help="skip validating the dictionary's example values against the shapes")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("check-pdf", help="compare the JSON with the dictionary PDF (needs pdfplumber)")
    _common(p)
    p.add_argument("--release", "-r", dest="version", default="4.0.4")
    p.add_argument("--pdf", type=Path, help="local PDF (default: the PDF in the source repository)")
    p.add_argument("--pdf-path", default="AGS4/downloads/AGS_4_0_4.pdf",
                   help="path of the PDF within the source repository")
    p.add_argument("--out", type=Path, default=Path("dist/checks"))
    p.set_defaults(func=cmd_check_pdf)

    p = sub.add_parser("check-dictionary", help="compare the JSON with an AGS standard dictionary .ags file")
    _common(p)
    p.add_argument("file", type=Path, help="AGS standard dictionary file (DICT group), e.g. "
                                           "Standard_dictionary_v4_2.ags")
    p.add_argument("--release", "-r", dest="version", required=True)
    p.add_argument("--out", type=Path, default=Path("dist/checks"))
    p.set_defaults(func=cmd_check_dictionary)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    from .sources import SourceError

    try:
        return args.func(args)
    except (SourceError, KeyError) as e:
        print(f"ags-rdf: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
