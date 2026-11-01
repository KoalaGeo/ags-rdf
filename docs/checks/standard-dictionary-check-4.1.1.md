# AGS 4.1.1: JSON vs standard dictionary

- JSON: `https://gitlab.com/AGS-DFWG-Web/ASG4/-/blob/710b1f08097264e6508be1397282aece79278fc4/AGS4/AGS4_1/AGS4_1_1/groupsandheadings4-1-1.JSON`
- standard dictionary: `Standard_dictionary_v4_1_1.ags`

| | JSON | standard dictionary |
|---|---|---|
| Groups | 148 | 148 |
| Headings (occurrences) | 2895 | 2895 |

Comparison after normalising whitespace, line-break hyphenation, quotes and dashes. The JSON is the authoritative source; "other" below means the standard dictionary.

| Field | Differences |
|---|---|
| description | 5 |

## description (5)

| Group | Heading | JSON | standard dictionary | Page/line |
|---|---|---|---|---|
| DICT | DICT_HDNG | Heading name (Note: This data is REQUIRED where DICT_TYPE="HEADING") | Heading name (Note: This data is REQUIRED where DICT_TYPE='HEADING') | 36 |
| DICT | DICT_STAT | Heading status KEY, REQUIRED or OTHER (Note: This data is REQUIRED where DICT_TYPE="HEADING") | Heading status KEY, REQUIRED or OTHER (Note: This data is REQUIRED where DICT_TYPE='HEADING') | 37 |
| DICT | DICT_DTYP | Type of data and format (Note: This data is REQUIRED where DICT_TYPE="HEADING") | Type of data and format (Note: This data is REQUIRED where DICT_TYPE='HEADING') | 38 |
| DICT | DICT_UNIT | Units (Note: This data is REQUIRED where DICT_TYPE="HEADING") | Units (Note: This data is REQUIRED where DICT_TYPE='HEADING') | 40 |
| DICT | DICT_PGRP | Parent group name (Note: This data is REQUIRED where DICT_TYPE="GROUP") | Parent group name (Note: This data is REQUIRED where DICT_TYPE='GROUP') | 42 |
