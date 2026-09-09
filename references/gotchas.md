# Gotchas learned the hard way (KSW-EOP-101, 2026-09)

## Word COM automation

- **Never build/reposition the canvas via COM `AddCanvas` + `WrapFormat.Type = wdWrapInline`.**
  The canvas reliably lands in the WRONG paragraph (a neighboring table cell), and the
  mistake is invisible until you diff page counts. Build the drawing XML and swap it in
  document.xml instead (fc_build.py).
- **`Shapes.AddConnector` returns a shape with `.Connector = False` (Type 9) in Word**;
  `ConnectorFormat.BeginConnect` throws "This member can only be accessed for a
  connector". Attachment must be done in XML: `<a:stCxn id="…" idx="…"/>` /
  `<a:endCxn …/>` inside `<wps:cNvCnPr/>` (the empty element sits right after the
  shape's `<wps:cNvPr id name/>`).
- `BuildFreeform` signature is `BuildFreeform(EditingType, X, Y[, Scale])` — the editing
  type is the FIRST argument (0 = msoEditingCorner). Omitting it → "Invalid number of
  parameters".
- If pywin32's dynamic dispatch starts failing with `AttributeError: Add.PageSetup` or
  gencache raises `module … has no attribute 'CLSIDToClassMap'`: kill zombie
  WINWORD.EXE processes and delete `%LOCALAPPDATA%\Temp\gen_py`.

## DrawingML details

- `rect` connection-site indices: **0=top, 1=left, 2=bottom, 3=right**.
- A straight attached connector always terminates at the edge CENTER site. The original
  artwork had three branches dropping vertically into the wide "Wait 1 hour" box at
  non-center x positions; attaching those routed diagonals to the box center. Any
  endpoint that is not an edge center must be a plain polyline (unattached) — visually
  identical, and moving that one box means dragging its drop line too.
- Connectors render with `flipH`/`flipV` as needed; Word normalizes on open. Do not try
  to compute flips yourself — give the geometry, let Word route.
- `wp:docPr/@id` must be unique document-wide; use an id range nothing else uses
  (fc_build.py uses 900001+, with a collision bump).
- The wpc/wps/a namespaces are declared inline on the generated elements, so the
  fragment is safe to drop into any Word 2010+ document.xml regardless of root
  declarations.
- Every connector shape keeps its empty `<wps:cNvCnPr/>` replaced by the stCxn/endCxn
  version — Word reroutes from the geometry at open time, so hand-computed xfrm
  offsets don't need to be perfect.
- The VML `<mc:Fallback>` copy of the drawing (if present) does NOT need the cxn
  references; Word 2010+ reads the Choice branch. Fine to omit in generated XML.

## Swapping / size

- Match the replaced image by its exact `wp:extent` (e.g. `7429500x3865197`). The
  original KSW-EOP-101 image had inconsistent `pic:spPr/a:ext` vs `wp:extent` — trust
  `wp:extent` (that is what reserves layout space).
- After a successful swap, opening the file once in Word and re-saving normalizes the
  XML (ids, style blocks). Do this before delivering if you want a Word-canonical file.
- Removing the dead image: delete its `<Relationship Id="rIdN" …/>` from
  `word/_rels/document.xml.rels` and the media zip entry. Keep the
  `[Content_Types].xml` default for the extension. (EOP-101: −174 KB.)
- Keep `[Compatibility]`/settings untouched; the swap only touches document.xml + rels.

## Verification is the gate

- `OpenAndRepair=False` open is the repair-dialog canary; any structurural mistake
  fails here first.
- Page count equality plus per-page render diff (<3% at 80 dpi, zero pages over) caught
  every real regression in practice: wrong placement (+1 page), reflow, deleted label.
- Expect ~1–2% residual diff on the flowchart page from font antialiasing — the
  original PNG was produced by a different rasterizer, so pixel-identical text is not
  a realistic target. Font forensics (glyph width/serif tests) rarely beats just using
  the document's own UI font (Meiryo UI in KSW docs).
