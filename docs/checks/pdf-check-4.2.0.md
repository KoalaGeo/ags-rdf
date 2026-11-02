> **Note.** This report was produced by `ags-rdf check-pdf -r 4.2.0 --pdf <URL>` outside this
> repository's CI (the AGS website cannot be reached from the build environment), with the version of
> the checker that still compared units character for character. The 48 "unit" differences are PDF
> text-extraction artefacts: the unit column is narrow, so values such as `hh:mm:ss` wrap and are read
> back as `hh:mm:s s`. The checker now ignores whitespace in units and data types, so a re-run should
> report only the `ISTG_LINK` example, which is a genuine difference: the JSON example refers to the
> deprecated SCPG group where the PDF uses its 4.2 replacement, CPTG.

# AGS 4.2.0: JSON vs PDF

- JSON: `https://gitlab.com/AGS-DFWG-Web/ASG4/-/blob/710b1f08097264e6508be1397282aece79278fc4/AGS4/AGS4_2/4_2_0/groupsandheadings4-2-0.json`
- PDF: `https://www.ags.org.uk/content/uploads/2026/01/AGS-v-4-2-December-2025.pdf`

| | JSON | PDF |
|---|---|---|
| Groups | 171 | 171 |
| Headings (occurrences) | 3412 | 3412 |

Comparison after normalising whitespace, line-break hyphenation, quotes and dashes. The JSON is the authoritative source; "other" below means the PDF.

| Field | Differences |
|---|---|
| unit | 48 |
| example | 1 |

## unit (48)

| Group | Heading | JSON | PDF | Page/line |
|---|---|---|---|---|
| FILE | FILE_DATE | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 19 |
| CHIS | CHIS_STAR | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 33 |
| CPDG | CPDG_DATE | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 38 |
| CPTG | CPTG_DATE | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 40 |
| CPTT | CPTT_TIME | yyyy-mm-ddThh:mm:ss.sss | yyyy-mm-ddThh:m m:ss.sss | 44 |
| CTRC | CTRC_ELAP | hh:mm:ss | hh:mm:s s | 47 |
| CTRD | CTRD_TIME | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 48 |
| DMDG | DMDG_DATE | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 56 |
| DMTG | DMTG_DATE | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 57 |
| DMTT | DMTT_TMST | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 60 |
| DMTZ | DMTZ_DATE | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 60 |
| DOBS | DOBS_DURN | hh:mm:ss | hh:mm:s s | 61 |
| DOBS | DOBS_STIM | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 61 |
| DOBS | DOBS_ETIM | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 61 |
| ELRG | ELRG_RDAT | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 65 |
| ELRG | ELRG_DTIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 65 |
| ELRG | ELRG_LDTM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 65 |
| FGHS | FGHS_STTM | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 71 |
| FGHS | FGHS_ENTM | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 71 |
| FGHT | FGHT_TIME | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 72 |
| FGHT | FGHT_DURN | hh:mm:ss | hh:mm:s s | 72 |
| GCHM | GCHM_RDAT | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 75 |
| GCHM | GCHM_DTIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 75 |
| HDPH | HDPH_STAR | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 79 |
| HDPH | HDPH_ENDD | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 79 |
| ISAT | ISAT_TIME | hh:mm:ss | hh:mm:s s | 86 |
| ISTG | ISTG_STAR | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 89 |
| ISTG | ISTG_END | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 89 |
| ISTS | ISTS_DTIM | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 90 |
| LOCA | LOCA_GLDT | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 100 |
| MOND | MOND_DTIM | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 111 |
| PMMG | PMMG_DATE | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 116 |
| PMTG | PMTG_STAD | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 119 |
| PMTG | PMTG_ENDD | yyyy-mm-ddThh:mm:ss | yyyy-mm-ddThh:m m:ss | 119 |
| PREM | PREM_DTIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 123 |
| PREM | PREM_DURN | hh:mm:ss | hh:mm:s s | 123 |
| PREM | PREM_ETIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 123 |
| PTIM | PTIM_DTIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 123 |
| PUMT | PUMT_DTIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 126 |
| RESC | RESC_ELAP | hh:mm:ss | hh:mm:s s | 130 |
| SAMP | SAMP_DTIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 141 |
| SAMP | SAMP_ETIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 142 |
| SAMP | SAMP_DURN | hh:mm:ss | hh:mm:s s | 142 |
| TREM | TREM_DTIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 151 |
| TREM | TREM_DURN | hh:mm:ss | hh:mm:s s | 151 |
| TREM | TREM_ETIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 152 |
| WINS | WINS_DURN | hh:mm:ss | hh:mm:s s | 157 |
| WSTG | WSTG_DTIM | yyyy-mm-ddThh:mm | yyyy-mm-ddThh:m m | 158 |

## example (1)

| Group | Heading | JSON | PDF | Page/line |
|---|---|---|---|---|
| ISTG | ISTG_LINK | SCPG\|327-16A\|3 | CPTG\|327-16A\|3 | 89 |
