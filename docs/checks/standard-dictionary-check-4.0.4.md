# AGS 4.0.4: JSON vs standard dictionary

- JSON: `https://gitlab.com/AGS-DFWG-Web/ASG4/-/blob/710b1f08097264e6508be1397282aece79278fc4/AGS4/AGS4_0/groupsandheadings4-0-4.json`
- standard dictionary: `Standard_dictionary_v4_0_4.ags`

| | JSON | standard dictionary |
|---|---|---|
| Groups | 124 | 124 |
| Headings (occurrences) | 2101 | 2101 |

Comparison after normalising whitespace, line-break hyphenation, quotes and dashes. The JSON is the authoritative source; "other" below means the standard dictionary.

| Field | Differences |
|---|---|
| description | 9 |
| example | 3 |
| unit | 1 |

## description (9)

| Group | Heading | JSON | standard dictionary | Page/line |
|---|---|---|---|---|
| DICT | DICT_HDNG | Heading name (Note: This data is REQUIRED where DICT_TYPE="HEADING") | Heading name (Note: This data is REQUIRED where DICT_TYPE='HEADING') | 36 |
| DICT | DICT_STAT | Heading status KEY, REQUIRED or OTHER (Note: This data is REQUIRED where DICT_TYPE="HEADING") | Heading status KEY, REQUIRED or OTHER (Note: This data is REQUIRED where DICT_TYPE='HEADING') | 37 |
| DICT | DICT_DTYP | Type of data and format (Note: This data is REQUIRED where DICT_TYPE="HEADING") | Type of data and format (Note: This data is REQUIRED where DICT_TYPE='HEADING') | 38 |
| DICT | DICT_UNIT | Units (Note: This data is REQUIRED where DICT_TYPE="HEADING") | Units (Note: This data is REQUIRED where DICT_TYPE='HEADING') | 40 |
| DICT | DICT_PGRP | Parent group name (Note: This data is REQUIRED where DICT_TYPE="GROUP") | Parent group name (Note: This data is REQUIRED where DICT_TYPE='GROUP') | 42 |
| LLIN | LLIN_425 | Percentage passing 425µm sieve | Percentage passing 425�m sieve | 1162 |
| LLPL | LLPL_425 | Percentage passing 425µm sieve | Percentage passing 425�m sieve | 1183 |
| LSLT | LSLT_425 | Percentage passing 425µm sieve | Percentage passing 425�m sieve | 1339 |
| LSTG | LSTG_425 | Percentage of soil passing 425µm sieve | Percentage of soil passing 425�m sieve | 1360 |

## example (3)

| Group | Heading | JSON | standard dictionary | Page/line |
|---|---|---|---|---|
| CBRG | SPEC_PREP | Stored at constant water/moisture content for 7 days, then soaked for 7 days, maintained at 20±2°C throughout | Stored at constant water/moisture content for 7 days, then soaked for 7 days, maintained at 20�2�C throughout | 301 |
| CMPG | SPEC_PREP | Stored at constant water/moisture content for 7 days, then soaked for 7 days, maintained at 20±2°C throughout | Stored at constant water/moisture content for 7 days, then soaked for 7 days, maintained at 20�2�C throughout | 372 |
| MCVG | SPEC_PREP | Stored at constant water/moisture content for 7 days, then soaked for 7 days, maintained at 20±2°C throughout | Stored at constant water/moisture content for 7 days, then soaked for 7 days, maintained at 20�2�C throughout | 1433 |

## unit (1)

| Group | Heading | JSON | standard dictionary | Page/line |
|---|---|---|---|---|
| SCPT | SCPT_CON | µS/cm | �S/cm | 1972 |
