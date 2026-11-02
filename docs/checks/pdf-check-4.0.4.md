# AGS 4.0.4: JSON vs PDF

- JSON: `https://gitlab.com/AGS-DFWG-Web/ASG4/-/blob/710b1f08097264e6508be1397282aece79278fc4/AGS4/AGS4_0/groupsandheadings4-0-4.json`
- PDF: `https://gitlab.com/AGS-DFWG-Web/ASG4/-/blob/710b1f08097264e6508be1397282aece79278fc4/AGS4/downloads/AGS_4_0_4.pdf`

| | JSON | PDF |
|---|---|---|
| Groups | 124 | 124 |
| Headings (occurrences) | 2101 | 2101 |

Comparison after normalising whitespace, line-break hyphenation, quotes and dashes. The JSON is the authoritative source; "other" below means the PDF.

| Field | Differences |
|---|---|
| group title | 1 |
| example | 4 |
| description | 5 |
| data_type | 1 |

## group title (1)

| Group | Heading | JSON | PDF | Page/line |
|---|---|---|---|---|
| WINS |  | Window or Windowless Sampling Run Details | Dynamic Sampling Run Details |  |

## example (4)

| Group | Heading | JSON | PDF | Page/line |
|---|---|---|---|---|
| ASNS | ASNS_METH | BS 812 : Part 121- Magnesium sulfate | BS 812 : Part 121-Magnesium sulfate | 35 |
| GCHM | FILE_FSET | FS2 | FS23 | 58 |
| LBST | LBST_TEST | LLPL | Suite A | 73 |
| PMTL | PMTD_SEQ | 1 | 1 (Marked for deletion in next version) | 96 |

## description (5)

| Group | Heading | JSON | PDF | Page/line |
|---|---|---|---|---|
| CBRT | CBRT_MCT | Water/moisture content at top after test | Water / moisture content at top after test | 38 |
| GCHM | GCHM_DLM | Detection limit | Limit of detection | 58 |
| HDPH | HDPH_CONT | Drilling contractor | Contractor | 62 |
| LOCA | FILE_FSET | Associated file reference (eg boring or pitting instructions, location photographs) | Associated file reference (e.g. boring or pitting instructions, location photographs) | 81 |
| RDEN | RDEN_IDEN | Intact Dry Density | Intact dry density | 101 |

## data_type (1)

| Group | Heading | JSON | PDF | Page/line |
|---|---|---|---|---|
| GCHM | GCHM_DLM | X | U | 58 |
