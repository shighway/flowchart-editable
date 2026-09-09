#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan docx files for flowchart type. Used twice per job:
  before: list every doc that still has a raster (non-editable) flowchart
  after:  prove zero rasters remain in scope (completeness check)

Fast: only reads the zip directory + document.xml (no Word, no media extraction).

Usage:
  python fc_scan.py <folder-or-glob> [more globs...]
  python fc_scan.py "C:/Users/you/Downloads/KSW"          # recursive
Classifies the LARGEST inline drawing of each docx:
  raster         = picture (needs flowchart-editable swap)
  canvas/group   = already editable (done)
  SmartArt       = word/diagrams present (editable in Word; not this skill's target)
  none/no-drawing
Options:
  --min-area-emu N   ignore drawings smaller than this area (default 2000000)
  --rasters-only     print only docs that still contain a raster flowchart
"""
import argparse, glob, os, re, sys, zipfile

def classify(path, min_area):
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        return "ERROR:%s" % e, None
    names = z.namelist()
    if any(n.startswith("word/diagrams/") for n in names):
        return "SmartArt", None
    try:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        return "ERROR:no-document.xml", None
    # only drawings near a "Flowchart" label are flowcharts; other images are ignored.
    # a canvas drawing can be >50KB of XML, so match by drawing-block span, not window
    labels = [m.start() for m in re.finditer(r'>Flowchart', xml)]
    seen = {}
    for m in re.finditer(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', xml):
        a = int(m.group(1)) * int(m.group(2))
        if a < min_area:
            continue
        d0 = xml.rfind("<w:drawing>", 0, m.start())
        d1 = xml.find("</w:drawing>", m.start()) + len("</w:drawing>")
        if not any(d0 - 2500 <= L and L <= d1 + 3500 for L in labels):
            continue
        seg = xml[m.start():m.start() + 3000]
        if "<wpc:wpc" in seg:
            k = "canvas"
        elif "r:embed=" in seg:
            k = "raster"
        else:
            k = "other"
        seen[m.start()] = (k, "%sx%s %s" % (m.group(1), m.group(2), k))
    if not seen:
        return "no-flowchart-label", None
    kinds = [v[0] for v in seen.values()]
    details = [v[1] for v in seen.values()]
    n_r = kinds.count("raster")
    status = "raster(%d/%d charts)" % (n_r, len(kinds)) if n_r else "canvas(all %d)" % len(kinds)
    return status, "; ".join(details)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--min-area-emu", type=int, default=10**13,
                    help="ignore drawings smaller than this EMU^2 (~7.7e12 = 60cm^2); excludes photos/figures")
    ap.add_argument("--rasters-only", action="store_true")
    a = ap.parse_args()

    files = set()
    for r in a.roots:
        if os.path.isdir(r):
            for dirpath, dirnames, filenames in os.walk(r):
                dirnames[:] = [d for d in dirnames if d.lower() not in
                               ("00. archive", "archive", "~temp")]
                for f in filenames:
                    if f.lower().endswith(".docx") and not f.startswith("~$"):
                        files.add(os.path.join(dirpath, f))
        else:
            for g in glob.glob(r):
                if g.lower().endswith(".docx") and not os.path.basename(g).startswith("~$"):
                    files.add(g)

    rows = []
    for p in sorted(files):
        kind, ext = classify(p, a.min_area_emu)
        if a.rasters_only and not kind.startswith("raster"):
            continue
        rows.append((kind, os.path.getsize(p), ext, p))

    for kind, size, ext, p in rows:
        print("%-22s %10d  %-30s %s" % (kind, size, ext or "-", p))
    n_raster = sum(1 for k, *_ in rows if k.startswith("raster"))
    print("---")
    print("files: %d | raster flowcharts remaining: %d" % (len(rows), n_raster))
    sys.exit(0)

if __name__ == "__main__":
    main()
