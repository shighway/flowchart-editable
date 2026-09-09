#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detect boxes / connector segments / colors in a flowchart PNG.
Produces a draft spec JSON. Text fields are empty: transcribe them by viewing the PNG.

Usage: python fc_detect.py chart.png [-o spec_draft.json] [--display-width-cm 20.64]

--display-width-cm: on-page width of the chart (from wp:extent cx / 360000). With it,
the script estimates the box font size in points.

Outputs:
- boxes: fill-color bounding boxes (scan order is NOT visual order - rename by
  geometry, column then row, before writing connectors)
- _segments: connector line runs (box borders excluded, collinear runs merged).
  Group them using the PNG into "connectors" (box-edge-center to box-edge-center)
  and "polylines" (rails, elbows, drops into non-center edge points).
- _line_color, _estimated_font_size_pt: style suggestions (verify visually).
"""
import argparse, json
from collections import Counter, deque
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
            mnx = mxx = x0; mny = mxy = y0; n = 0
            while q:
                cx, cy = q.popleft()
                mnx = min(mnx, cx); mxx = max(mxx, cx)
                mny = min(mny, cy); mxy = max(mxy, cy); n += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < W and 0 <= ny < H and not seen[ny][nx]:
                        seen[ny][nx] = True
                        if close(px[nx, ny], target, tol):
                            q.append((nx, ny))
            if (mxx - mnx) >= min_w and (mxy - mny) >= min_h:
                area = float((mxx - mnx + 1) * (mxy - mny + 1))
                out.append({"bbox": [mnx, mny, mxx, mxy], "ratio": n / area})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png")
    ap.add_argument("-o", "--out", default="spec_draft.json")
    ap.add_argument("--display-width-cm", type=float,
                    help="on-page chart width in cm (= wp:extent cx / 360000); enables font size estimate")
    a = ap.parse_args()
    im = Image.open(a.png).convert("RGB")
    W, H = im.size
    px = im.load()

    c = Counter()
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            c[px[x, y]] += 1
    common = [col for col, n in c.most_common(12) if n > 50]
    dark = [col for col in common if sum(col) < 700]

    # classify dark colors: solid components with high fill ratio = box fills;
    # grayish dark colors with thin/complex components = lines/borders
    fills, line_colors = [], []
    for col in dark:
        comps = components(px, W, H, col, tol=28, min_w=30, min_h=20)
        ratio = max((cc["ratio"] for cc in comps), default=0)
        if ratio > 0.75:
            fills.append(col)
        elif max(col) - min(col) < 30:
            line_colors.append(col)
    if not line_colors:
        line_colors = [(51, 63, 80)]

    boxes = []
    for col in fills:
        for cc in components(px, W, H, col, tol=30, min_w=30, min_h=20):
            b = cc["bbox"]
            boxes.append({"x": [b[0], b[2]], "y": [b[1], b[3]],
                          "fill": "%02X%02X%02X" % col, "text": ""})
    boxes.sort(key=lambda b: (b["y"][0] // 50, b["x"][0]))

    # connector segments: mask of line-colored pixels, drop runs along box borders
    def is_line(x, y):
        return any(close(px[x, y], lc, 45) for lc in line_colors)
    segs = []
    for y in range(H):
        x = 0
        while x < W:
            if is_line(x, y):
                x0 = x
                while x < W and is_line(x, y): x += 1
                if x - x0 >= 18: segs.append(['H', x0, y, x - 1, y])
            else: x += 1
    for x in range(W):
        y = 0
        while y < H:
            if is_line(x, y):
                y0 = y
                while y < H and is_line(x, y): y += 1
                if y - y0 >= 18: segs.append(['V', x, y0, x, y - 1])
            else: y += 1

    def is_border(s):  # run lies along a box edge (border strokes match line color)
        k, x0, y0, x1, y1 = s
        for b in boxes:
            bx0, bx1 = b["x"]; by0, by1 = b["y"]
            if k == 'H' and abs(y0 - by0) <= 4 and x0 >= bx0 - 4 and x1 <= bx1 + 4: return True
            if k == 'H' and abs(y0 - by1) <= 4 and x0 >= bx0 - 4 and x1 <= bx1 + 4: return True
            if k == 'V' and abs(x0 - bx0) <= 4 and y0 >= by0 - 4 and y1 <= by1 + 4: return True
            if k == 'V' and abs(x0 - bx1) <= 4 and y0 >= by0 - 4 and y1 <= by1 + 4: return True
        return False
    def is_text_noise(s):  # fully inside a box = glyph strokes, not a connector
        k, x0, y0, x1, y1 = s
        for b in boxes:
            if (b["x"][0] + 2 <= x0 and x1 <= b["x"][1] - 2
                    and b["y"][0] + 2 <= y0 and y1 <= b["y"][1] - 2):
                return True
        return False
    segs = [s for s in segs if not is_border(s) and not is_text_noise(s)]

    def merge(seglist, horiz):
        out = []
        for s in seglist:
            placed = False
            for o in out:
                if horiz:
                    if abs(o[2] - s[2]) <= 3 and not (s[1] > o[3] + 10 or s[3] < o[1] - 10):
                        o[1] = min(o[1], s[1]); o[3] = max(o[3], s[3]); placed = True; break
                else:
                    if abs(o[1] - s[1]) <= 3 and not (s[2] > o[4] + 10 or s[4] < o[2] - 10):
                        o[2] = min(o[2], s[2]); o[4] = max(o[4], s[4]); placed = True; break
            if not placed:
                out.append(list(s))
        return out
    hs = merge([s for s in segs if s[0] == 'H'], True)
    vs = merge([s for s in segs if s[0] == 'V'], False)

    # font size: smallest white text block across boxes (single-line, no descender)
    est = None
    blocks = []
    for b in boxes:
        rows = [y for y in range(b["y"][0] + 3, b["y"][1] - 3)
                if sum(1 for x in range(b["x"][0] + 3, b["x"][1] - 3)
                       if all(v > 230 for v in px[x, y])) > 2]
        if rows:
            blocks.append(rows[-1] - rows[0] + 1)
    if blocks and a.display_width_cm:
        ptpp = a.display_width_cm * 28.35 / W
        est = round(min(blocks) * ptpp * 1.05, 1)

    spec = {
        "_notes": [
            "Transcribe texts by viewing the PNG; keep original line breaks (\\n).",
            "Rename boxes by GEOMETRY (column then row), not scan order - scan order interleaves columns.",
            "Group _segments: straight runs between box-edge CENTERS -> 'connectors';",
            "everything else (rails, elbows, drops into non-center edge points) -> 'polylines'.",
            "Check whether the raster has arrowheads; if yes note it in _arrowheads.",
        ],
        "px": {"w": W, "h": H},
        "_estimated_font_size_pt": est,
        "_line_color": "%02X%02X%02X" % (line_colors[0]),
        "_segments": {"H": [s[1:] for s in hs], "V": [s[1:] for s in vs]},
        "boxes": boxes,
        "connectors": [],
        "polylines": [],
    }
    json.dump(spec, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("boxes:", len(boxes), "| H segs:", len(hs), "| V segs:", len(vs),
          "| line:", spec["_line_color"], "| font est:", est, "->", a.out)
    print("Next: Read the PNG, transcribe texts, group segments into connectors/polylines.")

if __name__ == "__main__":
    main()
