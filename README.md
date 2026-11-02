# ags-rdf

Generate **SHACL shapes**, an **OWL data model** and **SKOS vocabularies** — as Turtle (`.ttl`),
N-Triples (`.nt`) and **VocExcel** workbooks (`.xlsx`) — from the
[AGS4 data format](https://www.ags.org.uk/data-format/) data dictionary, using the JSON files
published by the AGS Data Format Working Group in
[gitlab.com/AGS-DFWG-Web/ASG4](https://gitlab.com/AGS-DFWG-Web/ASG4/-/tree/master/AGS4) as the
authoritative source.

Built with [rdflib](https://github.com/RDFLib/rdflib), [pySHACL](https://github.com/RDFLib/pySHACL),
[VocExcel](https://github.com/Kurrawong/VocExcel) and [kurra](https://github.com/Kurrawong/kurra);
each output folder also has a [kgm](https://kurrawong.github.io/kgm/) manifest.

```bash
uv sync                                 # or: pip install -e .
uv run ags-rdf build                    # latest release, scraped from GitLab, into dist/
```

```bash
uv run ags-rdf build --release all      # 4.0.3, 4.0.4, 4.1, 4.1.1 and 4.2.0
```

Each step is printed with the elapsed time, and the run ends with a `FINISHED` line (exit code 0
when every check passed, 1 otherwise). One release takes about 3 minutes and all five about
11 minutes on Linux; the dictionary workbook and its validation are the slowest steps. Use `-q` for
results only.

### Windows and WSL

Under WSL, don't create the virtual environment on a Windows drive (`/mnt/c/...`). uv then fails
to install the `ags-rdf` command with `failed to query metadata of file
.venv/lib/python3.12/site-packages/../../../bin/ags-rdf` (it also warns that it cannot hardlink).
Either work from the Linux filesystem, which is also much faster for the build:

```bash
git clone https://github.com/KoalaGeo/ags-rdf.git ~/src/ags-rdf && cd ~/src/ags-rdf
uv sync
```

or keep the checkout on `C:` and put only the environment on the Linux side:

```bash
rm -rf .venv
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/ags-rdf"   # add to ~/.bashrc to keep it
uv sync
```

Running uv natively in Windows PowerShell (`uv sync`, then `uv run ags-rdf build` in
`C:\GIT\ags-rdf`) should also work: the code is platform-independent and writes UTF-8 files with
`\n` line endings everywhere, but it has only been tested on Linux. If uv times out fetching
packages from PyPI, retry or set `UV_HTTP_TIMEOUT=120`.

## What gets generated

For each release, in `dist/<version>/`:

| File | Content |
|---|---|
| `ags4-<v>-shapes.ttl` / `.nt` | SHACL: one `sh:NodeShape` per GROUP, one `sh:PropertyShape` per HEADING |
| `ags4-<v>-ontology.ttl` / `.nt` | OWL: one class per GROUP, one datatype property per HEADING, plus the small `agso:` meta-model |
| `vocabs/ags4-<v>-dictionary.ttl` / `.nt` / `.xlsx` | SKOS: groups (top concepts) and headings (narrower than every group they occur in); group categories as collections |
| `vocabs/ags4-<v>-abbreviations.*` | SKOS: standard abbreviations (ABBR pick lists), one collection per heading |
| `vocabs/ags4-<v>-units.*` | SKOS: standard units (UNIT), collections per quantity type |
| `vocabs/ags4-<v>-data-types.*` | SKOS: data TYPEs; generic `nDP`, `nSF`, `nSCI` with the specific `2DP`, `3SF`… used |
| `vocabs/ags4-<v>-rules.*` | SKOS: the AGS4 rules; sub-rules (`10a`) narrower than main rules (`10`) |
| `vocabs/ags4-<v>-contaminant-codes.*` | SKOS: ELRG/ERES contaminant & determinand codes |
| `ags4-<v>-all.ttl` / `.nt` | everything above in one graph |
| `catalogue.ttl`, `manifest.ttl` | DCAT catalogue and a Prez/KGM manifest of the folder |
| `reports/data-quality.md`, `issues.json` | findings about the source JSON (see below) |
| `reports/validation.md` | results of all validation checks |

Every vocabulary is a single `skos:ConceptScheme` conforming to the
[VocPub](https://w3id.org/profile/vocpub) profile, so it can be opened, edited and converted back
with VocExcel (`vocexcel ags4-4.2.0-units.xlsx -o units.ttl`).

Generated outputs are **not committed** (`dist/` is git-ignored) — see
[Licensing](#licensing-of-the-ags-content).

## Source data

`--source` chooses where the JSON comes from:

| `--source` | |
|---|---|
| `gitlab` (default) / `gitlab:<ref>` | scrape `AGS4/` from GitLab: list the tree with the GitLab API, download every `.json` pinned to the resolved commit and verify it against the git blob SHA. Cached in `.cache/gitlab/<commit>/`. |
| `path/to/ASG4-master.zip` | a "Download source code" archive from GitLab (the commit SHA is read from the zip comment) |
| `path/to/checkout` | a clone or extracted copy of the repository |

Releases are **discovered**, not hard-coded: any `groupsandheadings<maj>-<min>[-<patch>].json`
becomes a release, with the `group_notes.json`, `Changelog.JSON` and `rules.json` next to it
(drafts such as `groupsandheadings4-2CPT.JSON` are ignored). Shared registers — `abbr4.json`,
`UNIT.json`, `data_types.json`, `ELRG.json` — are filtered by their `Version` tags (`"4.0,4.1,4.2"`).

```bash
uv run ags-rdf releases            # what the source contains
uv run ags-rdf fetch               # just download/cache
```

Set `GITLAB_TOKEN` to raise GitLab's API rate limit (the per-file commit-date lookups used for
`schema:dateCreated`/`dateModified` are rate-limited when anonymous; dates then fall back to the
snapshot's commit date).

Every generated document records its provenance: `prov:wasDerivedFrom` links to the source files at
the exact commit, a `skos:historyNote` naming the files and commit, and per-concept
`prov:wasDerivedFrom`.

## Is the JSON consistent with the PDF?

You asked for the JSON to be the authoritative source, but checked against the PDF. The only
dictionary PDF in the repository is `AGS4/downloads/AGS_4_0_4.pdf` (AGS 4.0.4), so that release was
compared table by table (`ags-rdf check-pdf`, needs `uv sync --extra check`). As a second check
each release was compared with the AGS *standard dictionary* `.ags` files
(`ags-rdf check-dictionary FILE -r <version>`; e.g. the `Standard_dictionary_v4_*.ags` files bundled
with [python-ags4](https://pypi.org/project/python-ags4/)). Those `.ags` files say they were
compiled from the AGS working group's repository, so they are a consistency check rather than an
independent source. Full reports are in [`docs/checks/`](docs/checks/).

Other dictionary PDFs can be compared by file or URL, e.g. the 4.1 and 4.2 editions on the AGS
website (the table reader reads the 4.0.4 and 4.2 layouts; headings reported "missing" would mean a
layout it does not understand):

```bash
uv run ags-rdf check-pdf -r 4.2.0 --pdf https://www.ags.org.uk/content/uploads/2026/01/AGS-v-4-2-December-2025.pdf
```

| Release | Compared with | Groups | Headings | Field differences |
|---|---|---|---|---|
| 4.0.4 | PDF (Feb 2017) | 124 = 124 | 2101 = 2101 | 11 |
| 4.0.4 | standard dictionary | 124 = 124 | 2101 = 2101 | 13 |
| 4.1.1 | standard dictionary | 148 = 148 | 2895 = 2895 | 5 |
| 4.2.0 | PDF (Dec 2025, from the AGS website) | 171 = 171 | 3412 = 3412 | 1 |
| 4.2.0 | standard dictionary | 171 = 171 | 3412 = 3412 | 0 |

The 4.2.0 PDF comparison was run outside this environment (the AGS website is not reachable from
it); its report lists 48 more "unit" differences, all PDF line-wrap artefacts (`hh:mm:ss` read
back as `hh:mm:s s`) that the checker now ignores.

**Conclusion: the JSON matches.** Every group and heading, the heading order, KEY/REQUIRED status,
data types and suggested units agree. The few differences are wording or examples, and in each case
the JSON had not been updated to match the PDF:

- 4.2.0 `ISTG_LINK` example: JSON `SCPG|327-16A|3`, PDF `CPTG|327-16A|3` (SCPG is deprecated in 4.2;
  CPTG replaces it).
- 4.0.4 `WINS` title: JSON "Window or Windowless Sampling Run Details", PDF "Dynamic Sampling Run
  Details" (4.0.4 renamed window sampling to dynamic sampling).
- 4.0.4 `GCHM_DLM`: JSON "Detection limit" / type `X`, PDF "Limit of detection" / type `U`.
- 4.0.4 `HDPH_CONT`: JSON "Drilling contractor", PDF "Contractor"; `LBST_TEST` example `LLPL` vs
  `Suite A`.

## Source data quality

Each build writes `reports/data-quality.md`. Nothing is silently "fixed"; values are only cleaned of
formatting artefacts (HTML, entities, non-breaking spaces, stray line breaks). Findings worth
raising with the AGS (4.2.0 unless stated):

- **Data type `U`** is used by 25 headings (e.g. `ELRG_RVAL`, `CBRT_TOP`) but `data_types.json`
  defines it only for 4.0 and 4.1. The 4.1 definition is used and noted in the vocabulary.
- **`ELRG.json` version tags look incomplete for 4.2**: 26 accepted codes are tagged for 4.2 against
  ~2,400 for 4.1. Tags are followed strictly; set `register_version_fallbacks = {"4.2" = ["4.1"]}`
  to also include the 4.1 codes.
- **Encoding**: `Rule�15/17` (mis-encoded non-breaking spaces) in the TYPE/UNIT group status.
- **Examples that do not match their own data type** (each group's examples are validated against
  the shapes): e.g. `ISTA_DATE` example `45842` (an Excel date serial number), `FGHT_RDNG` example
  `123.321, 2000 or 0.0023` for a numeric field, and key examples that differ between parent and
  child groups (`ECTN`/`ELRG`/`RCAG` sample keys versus `SAMP`).
- Group notes for `IPRG`/`IPRT`, which are no longer in 4.2.0; duplicate register entries (e.g.
  `GEOL_LEG` `302` is both Approved "Clay/Silt" and Proposed "Clayey SILT"; the Approved entry is kept).
- Earlier releases: in 4.1 the group-level columns are only filled on a group's first row (handled),
  and one heading has an empty data type.

## The RDF model

### Identifiers

All IRIs are minted in one place ([`iris.py`](src/ags_rdf/iris.py)) under a configurable base
(`--base-iri`, default `https://w3id.org/ags4/`, a **placeholder that is not registered**):

| Namespace | Prefix | Example |
|---|---|---|
| `{base}def/` | `ags:` | `ags:LOCA` (class), `ags:LOCA_ID` (property) |
| `{base}ont/` | `agso:` | `agso:Record`, `agso:parent`, `agso:dictionaryEntry` |
| `{base}shapes/` | `agssh:` | `agssh:LOCA`, `agssh:LOCA-LOCA_ID` |
| `{base}voc/<vocab>/` | `agsdict:` … | `agsdict:LOCA_ID`, `agsabbr:LOCA_TYPE-CP`, `agsunit:kN_per_m2` |

Term IRIs are **unversioned**: `LOCA_ID` has the same IRI in every release, and each release is a
new version of the documents (`owl:versionIRI <…/4.2.0>`, `schema:version`). Local names only use
`[A-Za-z0-9_.-]` so they survive a VocExcel round trip; codes such as `CP+RC`, `kN/m2` or
`% dry weight` are transliterated (`CP_plus_RC`, `kN_per_m2`, `pct_dry_weight`) with the original
kept as `skos:notation`.

### AGS data as RDF (what the shapes validate)

- each DATA row of a GROUP is a resource typed with the group's class (`a ags:SAMP`);
- each non-null field is one triple (`ags:SAMP_TOP "1.50"^^xsd:decimal`);
- `agso:parent` links a row to the row in its PARENT GROUP (Rule 10c).

See [`examples/ags4-sample.ttl`](examples/ags4-sample.ttl):

```bash
uv run kurra shacl validate examples/ags4-sample.ttl -s dist/4.2.0/ags4-4.2.0-shapes.ttl
```

### What the shapes check

| Check | Severity | AGS basis |
|---|---|---|
| at most one value per field | Violation | one VARIABLE per FIELD |
| REQUIRED fields present | Violation | Rule 10b |
| unique combination of KEY fields | Violation | Rule 10a (SPARQL constraints) |
| parent row is of the parent group; shared key fields match it | Violation | Rule 10c (SPARQL constraint) |
| only one PROJ / TRAN row | Violation | Rules 13, 14 (derived from the rule text) |
| value of the suggested type (number, date/time, Y/N…) | Warning | dictionary types are suggestions; a file may declare another TYPE (Rule 8) |
| exact suggested format, e.g. two decimal places for 2DP | Warning | as above |
| standard abbreviation / unit / data type code | Warning | non-standard values allowed if defined in ABBR/UNIT/TYPE (Rules 15–17) |

KEY fields may be null (Rule 10a), so they are only `sh:minCount 1` when also REQUIRED. Rules that
depend on what a particular file declares (its TYPE/UNIT rows and ABBR/UNIT/TYPE groups) are checked
by the converter instead (next section). The AGS→XSD type mapping lives in one table,
[`datatypes.py`](src/ags_rdf/datatypes.py). Regular expressions use XSD/XPath syntax so they work in
any SHACL engine, not only pySHACL.

The KEY check is written for speed in pySHACL/rdflib: rows with all KEY fields filled are matched by
a join on the group's own key values, and rows with a null KEY field by a guarded comparison. During
validation, `ags-rdf` also caches parsed SPARQL (pySHACL otherwise re-parses each query for every
row). A 3,000-row MOND table converts and validates in about 30 seconds.

## Converting AGS files to RDF

```bash
uv run ags-rdf convert my-file.ags --validate
```

This writes `my-file.ttl` (add `--format ttl nt` for N-Triples too) and, with `--validate`,
`my-file.validation.txt`. Several files can be given at once (`-o folder/` for the outputs). The
dictionary release follows the file's `TRAN_AGS` (`4.0` uses 4.0.4, `4.1` uses 4.1, …); override it
with `--release 4.1.1`. Use `--data-base https://your.org/ags/<project>/` for record identifiers you
control (the default is `https://example.org/ags/<file name>/`).

| AGS | RDF |
|---|---|
| DATA row | record `<base>SAMP/BH1/1.50/1/B/S1` (built from the KEY fields; `_` for a null key) typed `ags:SAMP` |
| VARIABLE | `ags:SAMP_TOP "1.50"^^xsd:decimal`, typed by the file's TYPE (and UNIT for dates); nulls are omitted |
| key link to the parent group | `agso:parent <base>LOCA/BH1` |
| UNIT and TYPE rows | an `agso:FieldDefinition` per heading (`agso:unit`, `agso:type`, `agso:position`) on the `agso:DataFile` |
| user-defined group/heading (DICT) | terms under `<base>def/`, labelled from `DICT_DESC` |

Values that do not fit their type are kept as plain strings, never "corrected", so validation reports
them. `--validate` combines the SHACL shapes with checks of the file itself, reported with line
numbers:

| Rule | Checked by the converter |
|---|---|
| 8 | each value fits the TYPE declared in the file (errors), with the declared number of decimal places (warnings) |
| 10a / 10c | repeated KEY combinations; rows without a matching parent row |
| 13, 14, 15, 17 | PROJ, TRAN, UNIT and TYPE groups present |
| 15 | units in UNIT rows and PU fields are listed in the UNIT group |
| 16 | codes in PA fields (split on `TRAN_RCON`, default `+`) are listed in ABBR |
| 17 | types in TYPE rows are listed in the TYPE group |

"Suggested type/format" warnings are left out for fields whose declared TYPE differs from the
dictionary's suggestion, since the converter checks those values against the declared TYPE.

All 19 example files in the ASG4 repository (`AGS4/examples/`, AGS 4.0) convert and validate with
no violations and no rule errors. The remaining warnings are real: for example, units `degC` (the
standard unit is `DegC`; units are case-sensitive), `Rad` and `-`.

Each property shape also carries documentation: `sh:name`, `sh:description`, `sh:order`,
`skos:example`, `agso:dataType`, `agso:suggestedUnit`, `agso:isKey`, `agso:isRequired`,
`agso:rule` and `agso:dictionaryEntry` (the heading's SKOS concept).

## Validation

`ags-rdf build` validates everything it writes and fails (exit code 1) if anything does not conform:

| Target | Check |
|---|---|
| shapes | W3C SHACL-SHACL meta-shapes, then **executed** with pySHACL against one instance of every class (SHACL-SHACL does not look inside SPARQL constraints) |
| each vocabulary | VocPub 5.1 profile (the one shipped with VocExcel) — 0 violations, 0 warnings |
| each workbook | VocExcel round trip: reading the `.xlsx` back gives the same concepts, labels, definitions, notations, hierarchy, statuses and collection members |
| dictionary examples | informative: the examples are turned into records and validated (see data quality) |

Two VocExcel quirks are worked around (and tested): its RDF→Excel writer writes the scheme status in
lower case, which its own reader rejects; and its reader treats `@` in a preferred label as a
language tag, so the one affected label ("Dry Solids @ 30 Deg.C", 4.0 contaminant codes) is written
with a full-width `＠` in the workbook only, and the workbook's history note says so.

## Extending (e.g. mapping to DIGGS or ISO dictionaries)

Mapping is not built yet. The design makes room for it:

- **Stable anchors**: unversioned IRIs for every group/heading concept (`agsdict:`), class and
  property (`ags:`); `agso:dictionaryEntry` connects the OWL/SHACL terms to the concepts.
- **Separate layers**: concept-level mappings (`skos:exactMatch`/`closeMatch` to DIGGS elements,
  ISO 23386 properties, ISO 14688 terms…) and model-level mappings (`owl:equivalentClass`,
  `rdfs:subPropertyOf` to DIGGS/ISO 28258 classes) can each be published as their own graph without
  touching the generated ones. [SSSOM](https://mapping-commons.github.io/sssom/) TSV is a good
  authoring format for such mapping sets.
- **Builder hook**: register a function in `ags_rdf.build.EXTRA_BUILDERS`; it receives the
  `BuildContext` (normalised dictionary, IRIs, settings) and returns `{name: Graph}`. The graphs are
  written to `dist/<v>/extras/` and included in the combined graph and manifest.
- **Model independent of JSON and RDF**: builders only see [`model.py`](src/ags_rdf/model.py), so
  another source (e.g. DIGGS XSD, an ISO 23386 dictionary) can be loaded into the same structures.

```python
from ags_rdf.build import EXTRA_BUILDERS

def diggs_mappings(ctx):
    g = ctx.new_graph({"diggs": "http://diggsml.org/schemas/2.6#"})
    ...  # e.g. read an SSSOM file and add skos:closeMatch triples
    return {"diggs-mappings": g}

EXTRA_BUILDERS.append(diggs_mappings)
```

Other extension points: add a vocabulary in
[`builders/vocabularies.py`](src/ags_rdf/builders/vocabularies.py) (`VOCABULARIES`); change how
values are typed in `datatypes.py`; add facts about releases in `releases.KNOWN_RELEASES`.

## Configuration

See [`ags-rdf.example.toml`](ags-rdf.example.toml) (`--config`): base IRI, publisher, which register
statuses to include (Approved/Accepted/Deprecated by default; Proposed and Declined entries are not
part of the standard), version-tag fallbacks and the size limit for abbreviation patterns.

The AGS is recorded as creator and copyright holder; the publisher defaults to KoalaGeo.

## Working with the outputs

```bash
# validate your own AGS-as-RDF data
uv run kurra shacl validate my-data.ttl -s dist/4.2.0/ags4-4.2.0-shapes.ttl

# print a vocabulary's hierarchy
uv run kurra file hierarchy dist/4.2.0/vocabs/ags4-4.2.0-rules.ttl

# load the release into a triplestore with kgm (kgm fetches its validators online on first use)
uv sync --extra kgm
uv run kgm load sparql dist/4.2.0/manifest.ttl http://localhost:3030/ags/
```

## Licensing of the AGS content

This repository's code is MIT licensed. The **dictionary content is the AGS's**: the ASG4
repository's licence file only says "Discuss", and the AGS website puts the data dictionary and
abbreviation lists behind (free for open-source developers) registration. The generated files
carry `schema:copyrightHolder` AGS and a rights statement, and no licence is asserted. For that
reason `dist/` is not committed; check with the AGS before publishing the generated RDF.

## Development

```bash
uv sync --extra dev --extra kgm
uv run pytest                                   # fast, uses tests/fixtures/asg4-mini
AGS_RDF_SOURCE=gitlab uv run pytest             # also build real releases and run the PDF check
```

`tests/fixtures/asg4-mini` is a small excerpt of the 4.2.0 JSON (a few groups and the related
register entries).
