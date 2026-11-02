"""Convert AGS field values (text, as found in an AGS file) to RDF literals.

Used by the AGS file converter (:mod:`ags_rdf.convert`) and to validate the
dictionary's own example values against the shapes.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation

from rdflib import XSD, Literal

from .datatypes import type_spec

_DATETIME = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$")
_TIME = re.compile(r"^(\d{2}:\d{2})(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$")
_DATE_FORMS = [
    (re.compile(r"^\d{4}$"), XSD.gYear),
    (re.compile(r"^\d{4}-\d{2}$"), XSD.gYearMonth),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), XSD.date),
]
# DT formats from the AGS UNIT list that are not ISO 8601
_UNIT_FORMATS = {"dd/mm/yyyy": ("%d/%m/%Y", XSD.date), "hhmm": ("%H%M", XSD.time), "hhmmss": ("%H%M%S", XSD.time)}


def _datetime_literal(value: str, unit: str | None) -> Literal | None:
    fmt = _UNIT_FORMATS.get((unit or "").strip().lower())
    if fmt:
        try:
            parsed = dt.datetime.strptime(value, fmt[0])
        except ValueError:
            return None
        lexical = parsed.date().isoformat() if fmt[1] == XSD.date else parsed.time().isoformat()
        return Literal(lexical, datatype=fmt[1])
    for rx, datatype in _DATE_FORMS:
        if rx.match(value):
            return Literal(value, datatype=datatype)
    m = _DATETIME.match(value)
    if m:  # xsd:dateTime needs seconds: "2011-06-01T10:30" -> "2011-06-01T10:30:00"
        return Literal(f"{m.group(1)}T{m.group(2)}{m.group(3) or ':00'}{m.group(5) or ''}", datatype=XSD.dateTime)
    m = _TIME.match(value)
    if m:
        return Literal(f"{m.group(1)}{m.group(2) or ':00'}{m.group(4) or ''}", datatype=XSD.time)
    return None


def _is_decimal(value: str) -> bool:
    return bool(re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)", value))


def _is_double(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return bool(re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", value))


def to_literal(value: str, data_type: str, unit: str | None = None) -> Literal | None:
    """The literal for an AGS VARIABLE of the given TYPE (and UNIT); ``None`` for null ("").

    Values that do not fit the type are returned as plain strings, so that the
    SHACL shapes report them rather than the conversion silently dropping them.
    """
    value = (value or "").strip()
    if value == "":
        return None
    spec = type_spec(data_type)
    if spec.values is not None:  # YN
        return Literal(value)
    if XSD.decimal in spec.datatypes or XSD.double in spec.datatypes:
        if _is_decimal(value) and spec.literal_datatype != XSD.double:
            try:
                Decimal(value)
                return Literal(value, datatype=XSD.decimal)
            except InvalidOperation:
                pass
        if _is_double(value):
            return Literal(value, datatype=XSD.double)
        return Literal(value)  # text in a numeric field: XN allows it, others will not validate
    if XSD.dateTime in spec.datatypes:
        return _datetime_literal(value, unit) or Literal(value)
    return Literal(value)
