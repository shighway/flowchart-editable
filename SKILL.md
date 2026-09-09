---
name: flowchart-editable
description: >
  Replace a flat (PNG/JPEG) flowchart image inside a datacenter EOP/SOP .docx with a
  fully editable native Word shape canvas (DrawingML) at the exact same size/position,
  or generate a brand-new editable flowchart from a JSON spec. Use whenever the user
  says フローチャートを編集可能に/置換, wants an "editable version" of a flowchart,
  asks to make diagrams editable for a client, or wants new flowcharts produced
  editable (最初から編集可能) instead of raster images. Also use instead of PIL/PNG
  flowchart generators (e.g. the raster build_flowchart_bilingual.py approach) when
  the deliverable should stay editable in Word.
---

# Editable flowcharts in Word (native shapes, not images)

Goal: the client can edit box text, colors, and move boxes in Word itself, with the
lines following. Result replaces the old flat PNG 1:1 — same page, same table cell,
same EMU extent, no reflow anywhere.

## Pipeline (4 steps)

### 1. Locate the flowchart image in the docx

```bash
mkdir t && cd t && unzip -o -q FILE.docx -d doc
python - <<'EOF'
import zipfile, re
xml = zipfile.ZipFile("FILE.docx").read("word/document.xml").decode()
for m in re.finditer(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', xml):
    print(m.group(0), "at", m.start())
EOF
```

The flowchart is usually the largest inline extent. Extract the matching media file
(find `r:embed="rIdN"` in the same drawing, map via `word/_rels/document.xml.rels`).

### 2. Build the spec JSON

```bash
python fc_detect.py chart.png -o spec_draft.json --display-width-cm <cm>
```

`--display-width-cm` = replaced image's `wp:extent cx / 360000`. The draft contains
boxes, candidate line runs (`_segments`), the line color, and a font-size estimate.

Then **Read the PNG visually** and finish the draft by hand:
- transcribe every box `text` (`
` = forced line break; copy the original line breaks)
- **rename boxes by geometry (column, then row)** - the detector's scan order
  interleaves columns, so wiring connectors "by index" connects the wrong boxes
- group `_segments` using the PNG: runs between box-edge CENTERS -> attached
  `connectors`; everything else (distributor rails, elbows, drops into a non-center
  edge point, multi-bend routes) goes to `polylines`
- set `px` = PNG size, `emu` = the replaced image's extent
- style: start from the detected line color / font estimate, then verify visually;
  KSW/KIX charts are typically Meiryo UI bold 5.5-6 pt, exact line spacing, white
  on fill. fc_build sets `w:eastAsia` so Japanese text renders correctly.

### 2b. Translated variant of a chart you already built

If a translated doc (e.g. `_JP_EN`) contains the same flowchart as a raster, **reuse
the existing spec**: copy it, replace only the box `text` fields with the translated
strings (match the language the raster shows), and swap it into that document at its
own extent (`--match-extent`). Same topology, zero re-tracing.

### 3.### 3. Build + swap (staging copy — never touch the original yet)

```bash
python fc_build.py spec.json --docx in.docx --out in_staging.docx --remove-media
```

### 4. Verify, then deploy into the original folder

```bash
python fc_verify.py in_staging.docx --baseline-docx in.docx --deploy in.docx
```

Checks: opens without repair dialog, page count unchanged, every page render diff
< 3%. On PASS, `--deploy` backs up the target next to itself
(`in.docx.flowchart-bak.docx`) and overwrites it **in place**. Without `--deploy`
it only reports PASS/FAIL.

**Confirmation gate (mandatory).** Never deploy without explicit user approval:
1. after PASS, list the exact plan — every target file path that will be replaced and
   every backup path that will be created (`*.flowchart-bak.docx`)
2. ask the user to confirm (e.g. "このファイルを置換していいですか？")
3. deploy only the approved paths. Never touch other copies, archives, or old drafts
   on your own initiative — if the same document exists in several folders, show the
   list and let the user pick.

## New flowcharts (editable from the start)

Write the spec JSON directly (you already know the geometry — no detection step), then
`fc_build.py --fragment frag.xml` and paste the fragment into the target paragraph, or
swap an existing placeholder image the same way. Do **not** generate PIL/PNG charts for
deliverables anymore; rasters are exactly what clients complain about.

## Gotchas (read before deviating)

See [references/gotchas.md](references/gotchas.md) — Word COM shape placement and
connector attachment are unreliable; the XML-surgery path in fc_build.py exists
because of that. If Word reports a repair dialog on your output, read it before
inventing fixes.
