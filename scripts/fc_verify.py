#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify a flowchart-swapped docx:
  1. opens in Word WITHOUT the repair dialog (OpenAndRepair=False)
  2. page count matches the baseline
  3. per-page render diff vs baseline PDF (lists pages > threshold)

Usage:
  python fc_verify.py new.docx --baseline-pdf baseline.pdf
  python fc_verify.py new.docx --baseline-docx orig.docx   (exports baseline PDF via Word)
Exit code 0 = pass, 1 = fail.
"""
import argparse, io, os, sys
import fitz  # PyMuPDF

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--baseline-pdf")
    ap.add_argument("--baseline-docx")
    ap.add_argument("--dpi", type=int, default=80)
    ap.add_argument("--threshold", type=float, default=3.0)
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--deploy", metavar="TARGET",
                    help="after PASS: back up TARGET (TARGET.flowchart-bak.docx) and "
                         "overwrite it with the verified docx - i.e. replace the "
                         "original file in its own folder")
    a = ap.parse_args()
    if not (a.baseline_pdf or a.baseline_docx):
        sys.exit("need --baseline-pdf or --baseline-docx")

    import win32com.client as win32
    here = os.path.abspath(a.workdir)
    word = win32.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    fails = []
    try:
        doc = word.Documents.Open(FileName=os.path.abspath(a.docx),
                                  OpenAndRepair=False, ReadOnly=True)
    except Exception as e:
        print("FAIL: Word open/repair:", e)
        sys.exit(1)
    n_new = doc.ComputeStatistics(2)  # pages
    new_pdf = os.path.join(here, "_verify_new.pdf")
    doc.SaveAs2(new_pdf, 17)
    doc.Close(0)

    if a.baseline_docx:
        b = word.Documents.Open(FileName=os.path.abspath(a.baseline_docx),
                                OpenAndRepair=False, ReadOnly=True)
        n_base = b.ComputeStatistics(2)
        base_pdf = os.path.join(here, "_verify_base.pdf")
        b.SaveAs2(base_pdf, 17)
        b.Close(0)
    else:
        base_pdf = os.path.abspath(a.baseline_pdf)

    word.Quit()

    pb = fitz.open(base_pdf); pn = fitz.open(new_pdf)
    print("pages: baseline=%d new=%d" % (pb.page_count, pn.page_count))
    if pb.page_count != pn.page_count:
        fails.append("page count changed (reflow!)")
    mat = fitz.Matrix(a.dpi / 72.0, a.dpi / 72.0)
    from PIL import Image, ImageChops
    bad = []
    for i in range(min(pb.page_count, pn.page_count)):
        A = Image.open(io.BytesIO(pb[i].get_pixmap(matrix=mat, alpha=False).tobytes("png"))).convert("RGB")
        B = Image.open(io.BytesIO(pn[i].get_pixmap(matrix=mat, alpha=False).tobytes("png"))).convert("RGB")
        if A.size != B.size:
            bad.append((i + 1, "SIZE MISMATCH")); continue
        h = ImageChops.difference(A, B).convert("L").histogram()
        pct = 100.0 * sum(h[48:]) / sum(h)
        if pct > a.threshold:
            bad.append((i + 1, round(pct, 2)))
    if bad:
        fails.append("pages differing >%.1f%%: %s" % (a.threshold, bad))
    print("pages over %.1f%% diff: %s" % (a.threshold, bad if bad else "none"))
    if fails:
        print("FAIL:", "; ".join(fails)); sys.exit(1)
    print("PASS")

    if a.deploy:
        import shutil
        target = os.path.abspath(a.deploy)
        if os.path.exists(target):
            bak = target + ".flowchart-bak.docx"
            shutil.copy2(target, bak)
            print("backup:", bak)
        shutil.copy2(os.path.abspath(a.docx), target)
        print("deployed ->", target)

if __name__ == "__main__":
    main()
