#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detect boxes / connector segments / text blocks in a flowchart PNG.
Produces a draft spec JSON (text fields empty - transcribe them by viewing the PNG).

Usage: python fc_detect.py chart.png [-o spec_draft.json]
Requires Pillow (+ numpy optional).
"""
import argparse, json, sys
from collections import deque
from PIL import Image

def close(c, t, tol):
    return all(abs(a - b) <= tol for a, b in zip(c, t))

def components(px, W, H, target, tol, min_w, min_h):
    seen = [[False] * W for _ in range(H)]
    out = []
    for y0 in range(0, H, 2):
        for x0 in range(0, W, 2):
            if seen[y0][x0]:
                continue
            if not close(px[x0, y0], target, tol):
                seen[y0][x0] = True
                continue
            q = deque([(x0, y0)]); seen[y0][x0] = True
            mnx = mxx = x0; mny = mxy = y0
            while q:
                cx, cy = q.popleft()
                mnx = min(mnx, cx); mxx = max(mxx, cx)
                mny = min(mny, cy); mxy = max(mxy, cy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < W and 0 <= ny < H and not seen[ny][nx]:
                        seen[ny][nx] = True
                        if close(px[nx, ny], target, tol):
                            q.append((nx, ny))
            if (mxx - mnx) >= min_w and (mxy - mny) >= min_h:
                out.append([mnx, mny, mxx, mny + mxy - mny])  # fixed below
                out[-1] = [mnx, mny, mxx, mxy]
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png")
    ap.add_argument("-o", "--out", default="spec_draft.json")
    a = ap.parse_args()
    im = Image.open(a.png).convert("RGB")
    W, H = im.size
    px = im.load()
    from collections import Counter
    c = Counter()
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            c[px[x, y]] += 1
    common = [col for col, n in c.most_common(8) if n > 50]
    bg = common[0]
    fills = [col for col in common[1:] if sum(col) < 700][:3]  # non-white, non-line colors

    boxes = []
    for col in fills:
        for b in components(px, W, H, col, tol=30, min_w=30, min_h=20):
            boxes.append({"x": [b[0], b[2]], "y": [b[1], b[3]],
                          "fill": "%02X%02X%02X" % col, "text": ""})
    boxes.sort(key=lambda b: (b["y"][0] // 50, b["x"][0]))

    # text block height (white pixels inside first box) to estimate font size
    fsz = None
    if boxes:
        b = boxes[0]
        rows = [y for y in range(b["y"][0], b["y"][1])
                if sum(1 for x in range(b["x"][0], b["x"][1])
                       if all(v > 230 for v in px[x, y])) > 2]
        if rows:
            dpi = W / 8.27  # assume A4-width rendering; refine manually
            fsz = round((rows[-1] - rows[0]) / dpi * 72 * 1.35, 1)

    spec = {
        "_notes": "Fill text fields by viewing the PNG. Set px to PNG size; emu to the "
                  "replaced image extent from document.xml. Connectors/polylines must be "
                  "traced manually from the PNG (see SKILL.md).",
        "px": {"w": W, "h": H},
        "_estimated_font_size_pt": fsz,
        "boxes": boxes,
        "connectors": [],
        "polylines": [],
    }
    json.dump(spec, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("boxes:", len(boxes), "->", a.out)
    print("Now: Read the PNG to transcribe box texts, then trace connectors/polylines.")

if __name__ == "__main__":
    main()
