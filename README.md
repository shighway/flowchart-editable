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

## Usage

```
flowchart-editable/
├── SKILL.md                  4-step pipeline
├── references/gotchas.md     hard-won Word COM / DrawingML pitfalls
└── scripts/
    ├── fc_detect.py          PNG → box/color/font-size draft spec
    ├── fc_build.py           spec JSON → shape-canvas XML → swap into docx
    └── fc_verify.py          acceptance gate + --deploy (backup + in-place replace)
```

Typical run:

```bash
python scripts/fc_detect.py chart.png -o spec_draft.json   # auto-detect boxes
# transcribe box texts by viewing the PNG, trace connectors
python scripts/fc_build.py spec.json --docx in.docx --out staging.docx --remove-media
python scripts/fc_verify.py staging.docx --baseline-docx in.docx --deploy in.docx
```

On `PASS`, `--deploy` backs up the original next to itself
(`in.docx.flowchart-bak.docx`) and overwrites it in place.

## Verification gate

- opens in Word **without** the repair dialog (`OpenAndRepair=False`)
- page count unchanged
- per-page pixel diff vs baseline below threshold (default 3% at 80 dpi)

## Notes

- Font fidelity: use the document's own UI font (e.g. Meiryo UI bold in KSW docs).
  Pixel-identical text against the old raster is not a realistic target — different
  rasterizer.
- Straight attached connectors always terminate at a box edge **center**. Drops into
  non-center points of an edge must be plain polylines (see `references/gotchas.md`).
