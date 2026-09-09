> **Note (2026-09):** this pipeline is now **bundled inside
> [shighway/bilingual-docx-translation](https://github.com/shighway/bilingual-docx-translation)**
> (`scripts/fc_*.py` + `references/flowchart-editable.md`). This repo remains as the
> standalone/legacy version. Update flowcharts via the bilingual skill unless you only
> need flowchart editing.

# flowchart-editable

A ZCode skill: replace flat (PNG/JPEG) flowchart images inside Word (.docx) documents
with **fully editable native Word shapes** — same page, same table cell, exact same
size (EMU), zero reflow — or generate brand-new editable flowcharts from a JSON spec.

Built for datacenter EOP/SOP document work (KSW / KIX1 style procedures), where
clients ask for "editable versions" of flowchart appendices so they can change the
diagrams later.

## Why

Raster flowcharts (PIL/matplotlib-rendered PNGs pasted into docs) cannot be edited by
clients. SmartArt cannot reproduce free-form layouts. Native Word shape canvases can:
the client edits box text directly in Word, and attached connectors follow when boxes
move.

## Install

Copy this folder to your skills directory:

```
~/.agents/skills/flowchart-editable/
```

## Requirements

- Windows + Microsoft Word (verification and rendering use Word COM)
- Python: `pywin32`, `PyMuPDF (fitz)`, `Pillow`

## Pipeline

```
fc_scan     enumerate flowcharts in scope; prove zero rasters remain when done
fc_detect   auto-detect boxes, colors, line runs; auto-route connectors/polylines;
            auto-name boxes (c<col>_<row>); estimate line color + font size
            [LLM] view the PNG once -> write a texts overlay JSON (the only
            authoring step); sanity-check the auto-routing
fc_build    spec (+texts overlay) -> shape-canvas XML -> swap the raster in place
fc_verify   Word repair-open check, page count, per-page pixel diff
[confirm]   show exact deploy plan (targets + backups), get user approval
--deploy    replace in place; original kept as .flowchart-bak.docx
```

Typical run:

```bash
python scripts/fc_scan.py "<folder>" --rasters-only          # work list
python scripts/fc_detect.py chart.png -o spec.json --display-width-cm 20.64
python scripts/fc_build.py spec.json --texts texts.json \
    --docx in.docx --out staging.docx --remove-media
python scripts/fc_verify.py staging.docx --baseline-docx in.docx --deploy in.docx
```

`--deploy` never runs before the verification gate passes, and the deploy list is
always confirmed with the user first. A file whose project doesn't match its folder
is flagged, never written.

## Bilingual SOP/MOP rule

If a bilingual document's flowchart is single-language (EN-only or JP-only raster),
the swapped canvas is **bilingual: English lines on top, Japanese below in every
box**, using the document's own terminology. If text overflows, reduce font size
and/or line spacing instead of resizing boxes. When the document has separate EN and
JP charts side by side, keep two single-language canvases (one per language).

## Arrowheads

Set per-connector / per-polyline arrow direction in the spec:

```json
"connectors": [{"a": "chk", "sa": 3, "b": "r1", "sb": 1, "arrow": true}],
"polylines": [{"pts": [[926,268],[1310,268],[1310,311]], "arrow": true}]
```

`arrow: true` renders a triangle `tailEnd` at the target end. Spec-level
`"arrowheads": true` applies arrows to all connectors.

## Verification gate

- opens in Word **without** the repair dialog (`OpenAndRepair=False`)
- page count unchanged
- per-page pixel diff vs baseline below threshold (default 3% at 80 dpi)

A small residual diff on the chart page is expected (the source raster was produced
by a different font rasterizer); eyeball the rendered chart page before consciously
accepting an over-threshold diff.

## Safety rules

- the deploy list is always confirmed before anything is written
- misplaced files (e.g. an EOP-101 file inside the EOP-102 folder) are flagged, never
  written
- nothing user-visible is ever deleted; backups accumulate as
  `.flowchart-bak.docx`, `.flowchart-bak2.docx`, …
- completeness is proven by re-running `fc_scan`: "raster flowcharts remaining: 0"

## Notes

- Use the document's own UI font (e.g. Meiryo UI bold in KSW docs); `w:eastAsia` is
  set so Japanese renders correctly. Pixel-identical text against the original raster
  is not a realistic target (different font rasterizer).
- A flowchart image may be **floating** (`wp:anchor`) rather than inline: fc_build
  preserves the anchor (position/size/wrap) and swaps only the graphic content.
- Straight attached connectors always terminate at a box edge **center**; drops into
  non-center points must be polylines (see `references/gotchas.md`).
