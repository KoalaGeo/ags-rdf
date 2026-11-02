"""Command line interface: ``ags-rdf <command>`` (or ``python -m ags_rdf``).

Commands::

    ags-rdf releases                 list the dictionary releases found in the source
    ags-rdf fetch                    download (scrape) the AGS4 JSON from GitLab into the cache
    ags-rdf build                    generate TTL, N-Triples and VocExcel XLSX (+ validation, reports)
    ags-rdf convert FILE.ags         convert AGS data files to RDF (--validate to check them)
    ags-rdf check-pdf                compare the JSON with the published AGS dictionary PDF
    ags-rdf check-dictionary FILE    compare the JSON with an AGS standard dictionary (.ags) file

The source defaults to ``gitlab`` (https://gitlab.com/AGS-DFWG-Web/ASG4, branch
master). Use ``--source PATH`` for a local checkout, extracted archive or .zip.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
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
    started = time.monotonic()

    def progress(msg: str) -> None:
        if not args.quiet:
            print(f"  [{_elapsed(started)}] {msg}", flush=True)

    results = []
    for n, rel in enumerate(releases, start=1):
        print(f"== AGS {rel.version} ({n} of {len(releases)})", flush=True)
        r = build_release(snap, rel, args.out, settings, xlsx=not args.no_xlsx,
                          validate=not args.no_validate, examples=not args.no_examples, progress=progress)
        results.append(r)
        for x in r.results:
            print("  " + x.summary)
        print(f"  wrote {len(r.files)} files to {r.out_dir}", flush=True)
    write_summary(results, args.out)
    failed = [r.version for r in results if not r.ok]
    if failed:
        print(f"FINISHED in {_elapsed(started)}: validation FAILED for {', '.join(failed)} - see "
              "reports/validation.md", file=sys.stderr)
        return 1
    print(f"FINISHED in {_elapsed(started)}: {len(results)} release(s) built, all checks passed. "
          f"Outputs in {args.out}/")
    return 0


def _elapsed(started: float) -> str:
    s = int(time.monotonic() - started)
    return f"{s // 60}:{s % 60:02d}"


def cmd_convert(args) -> int:
    from .builders.common import BuildContext
    from .convert import (AgsConverter, check_file, declared_type_shapes, default_data_base, pick_release,
                          read_ags)
    from .export import write_rdf
    from .loader import load_dictionary
    from .releases import discover_releases

    settings = Settings.load(args.config, base_iri=args.base_iri)
    snap = _snapshot(args)
    releases = discover_releases(snap)
    contexts: dict[str, BuildContext] = {}
    shapes_cache: dict[str, tuple] = {}
    used_stems: set[Path] = set()
    worst = 0
    for path in args.files:
        ags = read_ags(path)
        rel = releases[args.version] if args.version != "auto" else pick_release(releases, ags.ags_version)
        if rel.version not in contexts:
            contexts[rel.version] = BuildContext(load_dictionary(snap, rel, settings), snap, settings)
        ctx = contexts[rel.version]
        base = args.data_base or default_data_base(path)
        g, issues = AgsConverter(ctx, base).convert(ags)
        out = args.out or path.with_suffix("")
        if args.out and len(args.files) > 1:
            out = args.out / path.stem
        stem = out.parent / out.name.removesuffix(".ttl").removesuffix(".nt")
        n = 2
        while stem in used_stems:  # two inputs with the same file name
            stem = stem.with_name(f"{stem.name.rsplit('~', 1)[0]}~{n}")
            n += 1
        used_stems.add(stem)
        written = write_rdf(g, stem, tuple(args.format))
        n_rec = len(set(g.subjects(predicate=ctx.iris.AGSO.dataFile)))
        print(f"{path}: AGS {ags.ags_version or '?'} -> {rel.version} dictionary; {len(ags.tables)} groups, "
              f"{n_rec} records, {len(g)} triples -> {', '.join(str(p) for p in written)}")
        for i in issues:
            print(f"  note: {i}")
        if args.validate:
            from .builders.ontology import OntologyBuilder
            from .builders.shapes import ShapesBuilder
            from .validate import shacl_validate

            if rel.version not in shapes_cache:
                shapes_cache[rel.version] = (ShapesBuilder(ctx).build(), OntologyBuilder(ctx).build())
            shapes, ont = shapes_cache[rel.version]
            r = shacl_validate(g, shapes, path.name, f"AGS {rel.version} shapes", ont=ont, limit=100_000,
                               ignore_shapes=declared_type_shapes(ags, ctx.dictionary, ctx.iris))
            file_issues = check_file(ags, ctx.dictionary)
            errors = [i for i in file_issues if i.severity == "error"]
            lines = [f"[{i.severity}] Rule {i.category.split('-')[1]}: {i.message}" for i in file_issues]
            lines += r.details
            report = stem.parent / f"{stem.name}.validation.txt"
            report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            ok = r.violations == 0 and not errors
            print(f"  {'valid' if ok else 'NOT valid'}: SHACL {r.violations} violations, {r.warnings} warnings; "
                  f"file rules {len(errors)} errors, {len(file_issues) - len(errors)} warnings (details: {report})")
            for line in lines[:args.show]:
                print(f"    {line}")
            worst = max(worst, 0 if ok else 1)
    return worst


def cmd_check_pdf(args) -> int:
    from .checks.pdf import compare_pdf
    from .releases import discover_releases

    snap = _snapshot(args)
    rel = discover_releases(snap)[args.version]
    if args.pdf and args.pdf.startswith(("http://", "https://")):
        report = compare_pdf(snap, rel, _download(args.pdf, args.cache / "pdfs"), label=args.pdf)
    elif args.pdf:
        report = compare_pdf(snap, rel, Path(args.pdf), label=Path(args.pdf).name)
    else:
        report = compare_pdf(snap, rel, snap.path(args.pdf_path), label=snap.url_for(args.pdf_path))
    out = args.out / f"pdf-check-{args.version}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_markdown(), encoding="utf-8", newline="\n")
    print(report.summary())
    print(f"Report: {out}")
    return 0


def _download(url: str, folder: Path) -> Path:
    """Download a file once into ``folder`` (used for PDFs given by URL)."""
    import requests

    from .sources import SourceError

    dest = folder / url.rstrip("/").rsplit("/", 1)[-1]
    if dest.is_file():
        return dest
    folder.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, timeout=120, headers={"User-Agent": "ags-rdf"})
        r.raise_for_status()
    except requests.RequestException as e:
        raise SourceError(f"could not download {url}: {e}") from e
    if not r.content.startswith(b"%PDF"):
        raise SourceError(f"{url} did not return a PDF")
    dest.write_bytes(r.content)
    return dest


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
    p.add_argument("-q", "--quiet", action="store_true", help="only print the results, not each step")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("convert", help="convert AGS data files (.ags) to RDF, optionally validating them")
    _common(p)
    p.add_argument("files", type=Path, nargs="+", help="AGS4 data files")
    p.add_argument("--release", "-r", dest="version", default="auto",
                   help="dictionary release to use; 'auto' (default) follows the file's TRAN_AGS")
    p.add_argument("--out", "-o", type=Path,
                   help="output file (one input) or folder (several); default: next to each input")
    p.add_argument("--format", "-f", nargs="+", default=["ttl"], choices=["ttl", "nt", "xml", "json-ld"],
                   help="output format(s) (default: ttl)")
    p.add_argument("--data-base", help="base IRI for the records (default: https://example.org/ags/<file>/)")
    p.add_argument("--validate", action="store_true", help="validate against the release's SHACL shapes")
    p.add_argument("--show", type=int, default=10, help="validation messages to print (default 10)")
    p.add_argument("--config", type=Path, help="TOML settings file")
    p.add_argument("--base-iri", help="base IRI of the AGS model (must match the shapes you use)")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("check-pdf", help="compare the JSON with the dictionary PDF (needs pdfplumber)")
    _common(p)
    p.add_argument("--release", "-r", dest="version", default="4.0.4")
    p.add_argument("--pdf", help="local PDF file or URL (default: the 4.0.4 PDF in the source repository)")
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
