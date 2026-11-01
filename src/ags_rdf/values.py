"""Convert AGS field values (text, as found in an AGS file) to RDF literals.

Used to validate the dictionary's own example values against the shapes, and
intended as the starting point for an AGS-file-to-RDF converter.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from rdflib import XSD, Literal

from .datatypes import type_spec

_DATE_FORMS = [
    (re.compile(r"^\d{4}$"), XSD.gYear),
    (re.compile(r"^\d{4}-\d{2}$"), XSD.gYearMonth),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), XSD.date),
    (re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$"), XSD.dateTime),
    (re.compile(r"^\d{2}:\d{2}(:\d{2}(\.\d+)?)?$"), XSD.time),
]


def _is_decimal(value: str) -> bool:
    return bool(re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)", value))


def _is_double(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return bool(re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", value))


def to_literal(value: str, data_type: str) -> Literal | None:
    """The literal for an AGS VARIABLE of the given TYPE; ``None`` for null ("")."""
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
        v = value.replace(" ", "T") if re.match(r"^\d{4}-\d{2}-\d{2} \d", value) else value
        for rx, dt in _DATE_FORMS:
            if rx.match(v):
                if dt == XSD.dateTime and v.count(":") == 1:
                    v = v.replace(v[v.index("T"):v.index("T") + 6], v[v.index("T"):v.index("T") + 6] + ":00")
                if dt == XSD.time and v.count(":") == 1:
                    v += ":00"
                return Literal(v, datatype=dt)
        return Literal(value)
    return Literal(value)
