#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build an editable native-Word-shape flowchart from a JSON spec.

Two modes:
  1. Swap into a docx (replaces an existing inline image drawing):
     python fc_build.py spec.json --docx in.docx --out out.docx
  2. Emit the raw <w:drawing> fragment (for inserting into new documents):
     python fc_build.py spec.json --fragment fragment.xml

Spec JSON format (coordinates are in the spec's own pixel space, scaled to EMU):
{
  "px":  {"w": 1505, "h": 783},            // coordinate space of x/y values below
  "emu": {"cx": 7429500, "cy": 3865197},   // on-canvas size (EMU). For swap mode,
                                           // omit and it inherits the replaced image's extent.
  "style": {
    "font": "Meiryo UI", "font_size_pt": 5.5, "line_spacing_pt": 7.3,
    "text_color": "FFFFFF", "line_color": "33404F",
    "line_w_pt": 2.25, "border_w_pt": 1.0
  },
  "boxes": [
    {"name": "trig", "x": [11, 268], "y": [15, 82], "fill": "FF0000",
     "text": "TEPCO Power Outage", "text_color": "FFFFFF"}
  ],
  "connectors": [                    // straight, attached both ends (follow boxes)
    {"a": "trig", "sa": 3, "b": "p1", "sb": 1}
  ],                                 // sa/sb site: 1=top 2=left 3=bottom 4=right
  "polylines": [                     // plain unattached lines (fixed geometry)
    [[140,648],[140,686],[322,686],[322,171],[349,171]]
  ]
}

NOTE: a straight attached connector always lands on the box's site = edge CENTER.
If the original artwork has a vertical drop into a non-center point of a box edge,
use "polylines" for it instead (see references/gotchas.md).
"""
import argparse, json, re, sys, zipfile, shutil, os

W_NS = 'xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"'
WPS_NS = 'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"'
WP_NS = 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
A_NS = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def hexc(c):
    return c.lstrip("#").upper()

def build_fragment(spec):
    px = spec["px"]
    style = spec.get("style", {})
    font = style.get("font", "Meiryo UI")
    fsz = style.get("font_size_pt", 5.5)
    lsp = style.get("line_spacing_pt", 7.3)
    tcol = hexc(style.get("text_color", "FFFFFF"))
    lcol = hexc(style.get("line_color", "33404F"))
    lnw = int(round(style.get("line_w_pt", 2.25) * 12700))
    brw = int(round(style.get("border_w_pt", 1.0) * 12700))

    emu = spec.get("emu")
    sx = sy = None
    if emu:
        sx = emu["cx"] / px["w"]
        sy = emu["cy"] / px["h"]

    boxes = spec.get("boxes", [])
    bidx = {b["name"]: b for b in boxes}

    def ex(v): return int(round(v * sx))
    def ey(v): return int(round(v * sy))

    parts = []
    nid = [9001]

    def next_id():
        nid[0] += 1
        return nid[0]

    # boxes
    for b in boxes:
        x0, x1 = b["x"]; y0, y1 = b["y"]
        fill = hexc(b.get("fill", "7030A0"))
        tc = hexc(b.get("text_color", tcol))
        sz = int(round(b.get("font_size_pt", fsz) * 2))
        ls = int(round(b.get("line_spacing_pt", lsp) * 20))
        lines = b.get("text", "").split("\n")
        run_tpl = ('<w:r><w:rPr><w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s" w:eastAsia="%s"/>'
                   '<w:b/><w:color w:val="%s"/><w:sz w:val="%d"/><w:szCs w:val="%d"/></w:rPr>'
                   '<w:t xml:space="preserve">%s</w:t></w:r>')
        br = '<w:r><w:br/></w:r>'
        runs = br.join(run_tpl % (font, font, font, font, tc, sz, sz, esc(t)) for t in lines)
        parts.append(
            '<wps:wsp %s><wps:cNvPr id="%d" name="bx_%s"/><wps:cNvSpPr/>'
            '<wps:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
            '<a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:ln></wps:spPr>'
            '<wps:txbx><w:txbxContent><w:p><w:pPr>'
            '<w:spacing w:before="0" w:after="0" w:line="%d" w:lineRule="exact"/><w:jc w:val="center"/>'
            '</w:pPr>%s</w:p></w:txbxContent></wps:txbx>'
            '<wps:bodyPr rot="0" vert="horz" wrap="square" lIns="17780" tIns="0" rIns="17780" bIns="0" '
            'anchor="ctr" anchorCtr="0"><a:noAutofit/></wps:bodyPr></wps:wsp>'
            % (WPS_NS, next_id(), b["name"], ex(x0), ey(y0), ex(x1 - x0), ey(y1 - y0),
               fill, brw, lcol, ls, runs))

    # attached straight connectors
    SITES = {1: lambda b: ((b["x"][0] + b["x"][1]) / 2, b["y"][0]),
             2: lambda b: (b["x"][0], (b["y"][0] + b["y"][1]) / 2),
             3: lambda b: ((b["x"][0] + b["x"][1]) / 2, b["y"][1]),
             4: lambda b: (b["x"][1], (b["y"][0] + b["y"][1]) / 2)}
    IDX = {1: 0, 2: 1, 3: 2, 4: 3}
    box_xml_id = {}
    # cNvPr ids were assigned in box order; recompute deterministically
    for k, b in enumerate(boxes):
        box_xml_id[b["name"]] = 9002 + k

    for i, c in enumerate(spec.get("connectors", [])):
        A, B = bidx[c["a"]], bidx[c["b"]]
        (ax, ay) = SITES[c["sa"]](A); (bx, by) = SITES[c["sb"]](B)
        x, y = ex(min(ax, bx)), ey(min(ay, by))
        cx, cy = ex(max(ax, bx)) - x, ey(max(ay, by)) - y
        tail = ('<a:tailEnd type="triangle" w="med" len="med"/>'
                if c.get("arrow", spec.get("arrowheads", False)) else "")
        parts.append(
            '<wps:wsp %s><wps:cNvPr id="%d" name="cxn_%02d"/>'
            '<wps:cNvCnPr><a:stCxn id="%s" idx="%d"/><a:endCxn id="%s" idx="%d"/></wps:cNvCnPr>'
            '<wps:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="straightConnector1"><a:avLst/></a:prstGeom>'
            '<a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>%s</a:ln></wps:spPr>'
            '<wps:bodyPr/></wps:wsp>'
            % (WPS_NS, box_xml_id[c["a"]] + 500 + i, i,
               box_xml_id[c["a"]], IDX[c["sa"]], box_xml_id[c["b"]], IDX[c["sb"]],
               x, y, cx, cy, lnw, lcol, tail))

    # freeform polylines
    for i, entry in enumerate(spec.get("polylines", [])):
        if isinstance(entry, dict):
            pts = entry["pts"]; parr = entry.get("arrow", False)
        else:
            pts = entry; parr = False
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        mx, my = ex(min(xs)), ey(min(ys))
        w, h = ex(max(xs)) - mx, ey(max(ys)) - my
        nodes = '<a:moveTo><a:pt x="%d" y="%d"/></a:moveTo>' % (ex(pts[0][0]) - mx, ey(pts[0][1]) - my)
        for p in pts[1:]:
            nodes += '<a:lnTo><a:pt x="%d" y="%d"/></a:lnTo>' % (ex(p[0]) - mx, ey(p[1]) - my)
        parts.append(
            '<wps:wsp %s><wps:cNvPr id="%d" name="poly_%d"/><wps:cNvSpPr/>'
            '<wps:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/>'
            '<a:rect l="0" t="0" r="%d" b="%d"/>'
            '<a:pathLst><a:path w="%d" h="%d" fill="none">%s</a:path></a:pathLst></a:custGeom>'
            '<a:noFill/><a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>%s</a:ln></wps:spPr>'
            '<wps:bodyPr/></wps:wsp>'
            % (WPS_NS, next_id(), i, mx, my, w, h, w, h, w, h, nodes, lnw, lcol,
               '<a:tailEnd type="triangle" w="med" len="med"/>' if parr else ''))

    cx_e = emu["cx"] if emu else None
    cy_e = emu["cy"] if emu else None
    frag = (
        '<w:drawing><wp:inline %s distT="0" distB="0" distL="0" distR="0">'
        '<wp:extent cx="%d" cy="%d"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
        '<wp:docPr id="900001" name="Flowchart Canvas"/><wp:cNvGraphicFramePr/>'
        '<a:graphic %s><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas">'
        '<wpc:wpc %s><wpc:bg><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></wpc:bg><wpc:whole/>%s'
        '</wpc:wpc></a:graphicData></a:graphic></wp:inline></w:drawing>'
        % (WP_NS, cx_e, cy_e, A_NS, W_NS, "".join(parts)))
    return frag, boxes

def resolve_extent(spec, docx_xml):
    emu = spec.get("emu")
    if emu:
        return emu["cx"], emu["cy"]
    best, bv = None, -1
    for m in re.finditer(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', docx_xml):
        v = int(m.group(1)) * int(m.group(2))
        if v > bv: bv, best = v, (int(m.group(1)), int(m.group(2)))
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--docx"); ap.add_argument("--out")
    ap.add_argument("--fragment")
    ap.add_argument("--match-extent", help="cx x cy of the image to replace, e.g. 7429500x3865197")
    ap.add_argument("--texts", help="JSON {box_name: text} overlaid onto the spec's boxes")
    ap.add_argument("--remove-media", action="store_true",
                    help="drop the replaced image's rel + media entry (smaller file)")
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8"))
    if a.texts:
        texts = json.load(open(a.texts, encoding="utf-8"))
        for b in spec["boxes"]:
            if b["name"] in texts:
                b["text"] = texts[b["name"]]

    if a.fragment:
        frag, _ = build_fragment(spec)
        open(a.fragment, "w", encoding="utf-8").write(frag)
        print("fragment ->", a.fragment)
        return

    assert a.docx and a.out
    if a.match_extent:
        cx, cy = (int(v) for v in a.match_extent.lower().split("x"))
    else:
        cx, cy = None, None
    spec.setdefault("emu", {})
    zin = zipfile.ZipFile(a.docx)
    xml = zin.read("word/document.xml").decode("utf-8")

    if cx is None:
        best, bv = None, -1
        for m in re.finditer(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', xml):
            v = int(m.group(1)) * int(m.group(2))
            if v > bv: bv, best = v, (int(m.group(1)), int(m.group(2)))
        cx, cy = best
    spec["emu"] = {"cx": cx, "cy": cy}

    frag, _ = build_fragment(spec)
    mt = re.search(r'<wp:extent cx="%d" cy="%d"/>' % (cx, cy), xml)
    assert mt, "extent %dx%d not found in document.xml" % (cx, cy)
    g0 = xml.rfind("<w:drawing>", 0, mt.start())
    g1 = xml.find("</w:drawing>", mt.start()) + len("</w:drawing>")
    removed = xml[g0:g1]

    if "<wp:anchor" in removed:
        # floating image: preserve the original anchor (position/wrap/size) and
        # swap only the graphic content for the editable canvas
        attrs = re.search(r"<wp:anchor([^>]*)>", removed).group(1)
        def grab(pat, default=""):
            m = re.search(pat, removed, re.S)
            return m.group(0) if m else default
        simple = grab(r"<wp:simplePos[^>]*/>")
        posh = grab(r"<wp:positionH.*?</wp:positionH>")
        posv = grab(r"<wp:positionV.*?</wp:positionV>")
        extent = grab(r"<wp:extent[^>]*/>")
        eff = grab(r"<wp:effectExtent[^>]*/>", '<wp:effectExtent l="0" t="0" r="0" b="0"/>')
        wrap = grab(r"<wp:wrap(?:None|Square|Tight|Through|TopAndBottom)[^>]*/>",
                    "<wp:wrapNone/>")
        docpr = grab(r"<wp:docPr[^>]*/>", '<wp:docPr id="900001" name="Flowchart Canvas"/>')
        relh = grab(r"<wp14:sizeRelH.*?</wp14:sizeRelH>")
        relv = grab(r"<wp14:sizeRelV.*?</wp14:sizeRelV>")
        graphic = frag[frag.find("<a:graphic"):frag.rfind("</a:graphic>") + len("</a:graphic>")]
        frag = ('<w:drawing><wp:anchor%s>%s%s%s%s%s%s%s<wp:cNvGraphicFramePr/>%s%s%s'
                '</wp:anchor></w:drawing>'
                % (attrs, simple, posh, posv, extent, eff, wrap, docpr, graphic, relh, relv))

    xml = xml[:g0] + frag + xml[g1:]

    # docPr id must be unique in the document
    while 'id="900001"' in xml[:g0] or 'id="900001"' in xml[g0 + len(frag):]:
        frag = frag.replace('id="900001"', 'id="900002"')
        xml = xml[:g0] + frag + xml[g1:]

    old_rid = re.search(r'r:embed="(rId\d+)"', removed)
    drop_media = a.remove_media and old_rid
    rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")
    media_target = None
    if drop_media:
        rm = re.search(r'<Relationship Id="%s"[^>]*Target="([^"]+)"[^>]*/>' % old_rid.group(1), rels)
        if rm:
            media_target = "word/" + rm.group(1).lstrip("/")
            rels = re.sub(r'<Relationship Id="%s"[^>]*/>' % old_rid.group(1), "", rels)

    zout = zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED)
    for item in zin.infolist():
        if drop_media and item.filename == media_target:
            continue
        data = zin.read(item.filename)
        if item.filename == "word/document.xml":
            data = xml.encode("utf-8")
        elif item.filename == "word/_rels/document.xml.rels":
            data = rels.encode("utf-8")
        zout.writestr(item, data)
    zout.close()
    print("OK -> %s (swapped extent %dx%d)" % (a.out, cx, cy))

if __name__ == "__main__":
    main()
