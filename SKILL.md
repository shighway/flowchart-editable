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

## Pipeline (5 steps)

### 0. Scan the scope (leak-proof work list)

```bash
python fc_scan.py "<folder>"           # recursive; archives skipped
python fc_scan.py "<folder>" --rasters-only
```

Only drawings near a **"Flowchart:"** label are flowcharts; photos/figures/other
charts are out of scope by design and are never touched. The scan classifies each
labeled drawing as `raster` (needs swap), `canvas` (done), or `SmartArt` (out of
scope - already editable). The raster list IS the work list; after finishing,
re-run the scan and require **"raster flowcharts remaining: 0"** as the
completeness proof.

**Confirmation comes BEFORE the work.** Right after the scan, present the full plan -
every file that will be swapped, every backup path that will be created, the expected
box text language (EN / JP / bilingual) - and get explicit approval. Do not extract
charts, build, or write anything before approval. Once approved: run steps 1-4
without further asking, and deploy automatically on PASS. Only stop mid-way if
verification fails (report, do not deploy, re-confirm a revised plan).

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

### 2. Auto-spec + texts overlay

```bash
python fc_detect.py chart.png -o spec_draft.json --display-width-cm <cm>
```

The draft is complete: boxes auto-named `c<col>_<row>` (columns left-to-right, rows
top-down), routes auto-grouped into `connectors`/`polylines`, line color and font
size estimated. After **reading the PNG once**:
- write a texts overlay JSON `{"c01_r01": "...", "c01_r02": "..."}` - this is the
  only authoring step; copy the original line breaks (`
`)
- sanity-check the auto-routing against the PNG; edit `connectors`/`polylines` in
  the JSON only where they differ from the drawing
- check arrowheads in the raster; the canvas omits them today (see gotchas)
- bilingual rule from 2b applies to the texts: EN lines on top, JP lines below

Build:

```bash
python fc_build.py spec_draft.json --texts texts.json --docx in.docx   --out staging.docx [--match-extent cx x cy] [--remove-media]
```
### 2b. Flowchart in a bilingual SOP/MOP

If the document is bilingual (EN + JP) but its flowchart is **single-language**
(EN-only or JP-only raster), the swapped canvas must be **bilingual: English on
top, Japanese below in every box**:

```
"text": "Confirm UV Relay status,
UPS normally discharging
UVリレー状態確認、
UPS通常放电確認"
```

- translate the box labels following the document's own terminology
- reuse geometry from whichever single-language spec exists (EN or JP) - one build
  serves the bilingual deliverable (`--match-extent` = that document's extent)
- bilingual text roughly doubles the content: if it overflows a box, reduce font
  size (e.g. 6 -> 5 pt) and/or line spacing rather than resizing boxes
- if the document has BOTH an EN chart and a JP chart side by side, keep them as
  two separate single-language canvases (one per language), each editable
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

Deployment here was already approved in the pre-work confirmation (Step 0) - no
second confirmation is needed on PASS. If verification FAILS: nothing is deployed;
report the failure, fix, and re-confirm only if the plan itself changed.
   If a `.flowchart-bak.docx` already exists at the target (a previous swap), do NOT
   overwrite it - write the intermediate state to `.flowchart-bak2.docx` so the backup
   chain preserves every generation.

**Location mismatch = hands off.** A file whose project doesn't match its folder
(e.g. an EOP-101 file sitting inside the EOP-102 folder) is a misplaced leftover:
flag it to the user, never write to it, never put backups there. This includes
"helpfully" converting it - deploy only where the user confirmed.

**Nothing user-visible ever gets deleted.** Backups stay until the user says
otherwise. If a change must be reverted, restore the backup content in place and
remove only the extra backup file AFTER the restore is verified (zip integrity +
size), leaving the folder exactly as found. Report the restore with byte-level
evidence.

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
