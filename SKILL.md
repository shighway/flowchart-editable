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
python fc_detect.py chart.png -o spec_draft.json
```

Then **Read the PNG visually** and finish the draft by hand:
- transcribe every box `text` (`\n` = forced line break; copy the original line breaks)
- trace connectors: attached straight connectors only where both endpoints hit an
  edge CENTER of a box; everything else (distributor rails, drops into a non-center
  edge point, multi-bend routes) goes to `polylines`
- set `px` = PNG size, `emu` = the replaced image's extent
- estimate font size from text-block height (detect script guesses); KSW/KIX charts
  are typically Meiryo UI bold 5.5–6 pt, exact line spacing, white on fill

### 3. Build + swap (staging copy — never touch the original yet)

```bash
python fc_build.py spec.json --docx in.docx --out in_staging.docx --remove-media
```

### 4. Verify, then deploy into the original folder

```bash
python fc_verify.py in_staging.docx --baseline-docx in.docx --deploy in.docx
```

Checks: opens without repair dialog, page count unchanged, every page render diff
< 3%. On PASS with `--deploy`, the original is backed up next to itself
(`in.docx.flowchart-bak.docx`) and overwritten **in place** — the replacement lands
in the folder where the original lives, which is what "置換して" means. Without
`--deploy` it only reports PASS/FAIL.

**Default behavior — deploy to every copy of the document.** If the same document
exists in more than one place (e.g. a Downloads copy + the OneDrive project folder),
replace ALL of them, each with its own `.flowchart-bak.docx` backup in its folder,
without being asked. Verify once (staging vs one baseline), then copy the same
verified staging file to every location.

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
