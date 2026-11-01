"""How AGS4 data TYPEs are expressed as RDF literals and SHACL constraints.

AGS dictionary types are *suggested*: Rule 8 lets a data file declare another
type in its TYPE row (e.g. 3DP instead of 2DP). The shapes therefore split each
type into

* a **value space** (``datatypes``) enforced as an ``sh:Violation`` - e.g. a 2DP
  heading must hold a number, and
* an optional **exact format** (``format_pattern``) reported as an
  ``sh:Warning`` - e.g. exactly two decimal places.

Notes on rdflib/pySHACL: rdflib normalises the lexical form of ``xsd:integer``
and ``xsd:double`` literals (``7.31E4`` becomes ``73100.0``) but keeps
``xsd:decimal`` lexical forms, so format patterns are only used where the
lexical form survives (nDP as xsd:decimal, and string-valued types).

This table is the single place to change if the RDF representation of AGS
values changes (see also :mod:`ags_rdf.values`, which converts AGS file values
to literals using the same table).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rdflib import RDFS, XSD, URIRef

TEXT = (XSD.string,)
NUMERIC = (XSD.decimal, XSD.integer, XSD.double, XSD.float)
DATETIME = (XSD.dateTime, XSD.dateTimeStamp, XSD.date, XSD.time, XSD.gYearMonth, XSD.gYear)

_NUMERIC_TYPE = re.compile(r"^(\d+)(DP|SF|SCI)$")


@dataclass(frozen=True)
class TypeSpec:
    code: str
    datatypes: tuple[URIRef, ...]  # allowed literal datatypes (violation if none match)
    range: URIRef  # rdfs:range for the OWL datatype property
    literal_datatype: URIRef | None  # datatype used when converting an AGS value
    format_pattern: str | None = None  # suggested exact format (warning)
    format_label: str | None = None
    values: tuple[str, ...] | None = None  # closed value list (violation)
    generic: str | None = None  # generic dictionary type (2DP -> nDP)


def generic_code(code: str) -> str:
    """``2DP`` -> ``nDP``; other codes unchanged."""
    m = _NUMERIC_TYPE.match(code)
    return f"n{m.group(2)}" if m else code


def type_spec(code: str) -> TypeSpec:
    code = (code or "").strip()
    m = _NUMERIC_TYPE.match(code)
    if m:
        n, kind = int(m.group(1)), m.group(2)
        if kind == "DP":
            pattern = r"^[+-]?[0-9]+$" if n == 0 else rf"^[+-]?[0-9]+\.[0-9]{{{n}}}$"
            return TypeSpec(code, NUMERIC, XSD.decimal, XSD.decimal, pattern,
                            f"{n} decimal place{'s' if n != 1 else ''}", generic="nDP")
        if kind == "SF":
            return TypeSpec(code, NUMERIC, XSD.decimal, XSD.decimal, generic="nSF",
                            format_label=f"{n} significant figure{'s' if n != 1 else ''}")
        return TypeSpec(code, NUMERIC, XSD.double, XSD.double, generic="nSCI",
                        format_label=f"scientific notation with {n} decimal place{'s' if n != 1 else ''}")
    if code in ("ID", "X", "PA", "PT", "PU", "RL"):
        return TypeSpec(code, TEXT, XSD.string, XSD.string)
    if code == "XN":
        return TypeSpec(code, TEXT + NUMERIC, RDFS.Literal, None)
    if code in ("U", "MC"):
        return TypeSpec(code, NUMERIC, XSD.decimal, XSD.decimal)
    if code == "DT":
        return TypeSpec(code, DATETIME, RDFS.Literal, None)
    if code == "T":
        return TypeSpec(code, (XSD.duration, XSD.time, XSD.string), RDFS.Literal, XSD.string,
                        r"^(P.+|[0-9]+(:[0-5][0-9]){1,2}(\.[0-9]+)?)$", "elapsed time, e.g. hh:mm:ss")
    if code == "DMS":
        return TypeSpec(code, TEXT, XSD.string, XSD.string,
                        r"^[+-]?[0-9]{1,3}:\s?[0-9]{1,2}:\s?[0-9]{1,2}(\.[0-9]+)?$",
                        "degrees:minutes:seconds, e.g. 51:28:52.498")
    if code == "YN":
        return TypeSpec(code, TEXT + (XSD.boolean,), RDFS.Literal, XSD.string, values=("Y", "N"))
    # unknown or empty type: no value-space constraint
    return TypeSpec(code, (), RDFS.Literal, None)


_XSD_META = set("\\|.-^?*+{}()[]$")


def regex_escape(text: str) -> str:
    """Escape for SHACL ``sh:pattern`` (XPath/XSD regex syntax, also valid in Python ``re``).

    Python's :func:`re.escape` also escapes characters such as space, ``#`` or
    ``&``, which are *invalid* escapes in XSD regular expressions.
    """
    return "".join("\\" + c if c in _XSD_META else c for c in text)


def alternation(codes) -> str:
    """Regex alternation of literal codes, longest first."""
    return "|".join(regex_escape(c) for c in sorted(set(codes), key=lambda c: (-len(c), c)))


def codes_pattern(codes, concatenation: str = "+") -> str:
    """Regex matching one code, or several joined with the concatenation character (Rule 16a)."""
    alt = alternation(codes)
    return f"^({alt})({regex_escape(concatenation)}({alt}))*$"
