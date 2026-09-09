#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detect boxes / auto-route connectors / colors in a flowchart PNG.
Produces a complete spec JSON. The LLM only fills box texts (via --texts overlay for
fc_build) and sanity-checks the auto-routing against the PNG.

Usage:
  python fc_detect.py chart.png -o spec_draft.json [--display-width-cm 20.64]

Outputs a complete spec:
- boxes: named by geometry (c<col>_<row>), fill colors, empty texts
- connectors: straight box-to-box runs auto-attached at edge centers ({a, sa, b, sb}
  with sa/sb: 1=top 2=left 3=bottom 4=right)
- polylines: every non-center-to-center route (rails, elbows, drops), auto-grouped
  from the detected line runs
- _line_color, _estimated_font_size_pt
Verify the routing visually after reading the PNG; adjust the JSON if needed.
"""
import argparse, json
from collections import Counter, deque, defaultdict
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

def find_boxes(px, W, H):
    c = Counter()
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            c[px[x, y]] += 1
    common = [col for col, n in c.most_common(12) if n > 50]
    dark = [col for col in common if sum(col) < 700]
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
    # geometry naming: cluster columns by x-center, number rows top-down
    cols = []
    for b in sorted(boxes, key=lambda b: (b["x"][0] + b["x"][1]) / 2):
        xc = (b["x"][0] + b["x"][1]) / 2
        for cl in cols:
            if abs(cl["xc"] - xc) < 60:
                cl["bs"].append(b)
                break
        else:
            cols.append({"xc": xc, "bs": [b]})
    cols.sort(key=lambda cl: cl["xc"])
    for ci, cl in enumerate(cols, 1):
        for ri, b in enumerate(sorted(cl["bs"], key=lambda b: b["y"][0]), 1):
            b["name"] = "c%02d_r%02d" % (ci, ri)
    boxes.sort(key=lambda b: b["name"])
    return boxes, line_colors

def segments(px, W, H, boxes, line_colors, min_len=15):
    def is_line(x, y):
        return any(close(px[x, y], lc, 45) for lc in line_colors)
    raw = []
    for y in range(H):
        x = 0
        while x < W:
            if is_line(x, y):
                x0 = x
                while x < W and is_line(x, y): x += 1
                if x - x0 >= min_len: raw.append(('H', x0, y, x - 1, y))
            else: x += 1
    for x in range(W):
        y = 0
        while y < H:
            if is_line(x, y):
                y0 = y
                while y < H and is_line(x, y): y += 1
                if y - y0 >= min_len: raw.append(('V', x, y0, x, y - 1))
            else: y += 1

    def is_border(s):  # run lies along a box edge (borders share the line color)
        k, x0, y0, x1, y1 = s
        for b in boxes:
            bx0, bx1 = b["x"]; by0, by1 = b["y"]
            if k == 'H' and abs(y0 - by0) <= 4 and x0 >= bx0 - 4 and x1 <= bx1 + 4: return True
            if k == 'H' and abs(y0 - by1) <= 4 and x0 >= bx0 - 4 and x1 <= bx1 + 4: return True
            if k == 'V' and abs(x0 - bx0) <= 4 and y0 >= by0 - 4 and y1 <= by1 + 4: return True
            if k == 'V' and abs(x0 - bx1) <= 4 and y0 >= by0 - 4 and y1 <= by1 + 4: return True
    raw = [s for s in raw if not is_border(s)]

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
    hs = merge([s for s in raw if s[0] == 'H'], True)
    vs = merge([s for s in raw if s[0] == 'V'], False)
    def in_box(s):  # runs fully inside a box are glyph strokes
        k, x0, y0, x1, y1 = s
        for b in boxes:
            if (b["x"][0] + 2 <= x0 and x1 <= b["x"][1] - 2
                    and b["y"][0] + 2 <= y0 and y1 <= b["y"][1] - 2):
                return True
        return False
    return ([s for s in hs if not in_box(s)], [s for s in vs if not in_box(s)])

def route(hs, vs, boxes):
    """Group line runs into attached straight connectors and polylines."""
    edges = []
    coords = []
    def ckey(pt):
        for i, c in enumerate(coords):
            if abs(c[0] - pt[0]) <= 6 and abs(c[1] - pt[1]) <= 6:
                return i
        coords.append(pt)
        return len(coords) - 1
    for s in hs + vs:
        if s[0] == 'H':
            pa, pb = (s[1], s[2]), (s[3], s[2])
        else:
            pa, pb = (s[1], s[2]), (s[1], s[4])
        na, nb = ckey(pa), ckey(pb)
        if na == nb:
            continue
        # merge parallel strokes: same node pair -> one edge
        for e in edges:
            if {e[0], e[1]} == {na, nb}:
                e[2] = min(e[2], pa, key=lambda p: (p[0], p[1])) if False else e[2]
                break
        else:
            edges.append([na, nb, pa, pb])
    adj = defaultdict(list)
    for i, e in enumerate(edges):
        adj[e[0]].append(i)
        adj[e[1]].append(i)

    used = [False] * len(edges)
    paths = []
    while any(not u for u in used):
        ei0 = next(i for i, u in enumerate(used) if not u)
        e = edges[ei0]
        deg = {n: len([j for j in adj[n] if not used[j]]) for n in (e[0], e[1])}
        cur = e[0] if deg.get(e[0], 0) == 1 else e[1]
        ei = ei0
        pts = []
        while True:
            used[ei] = True
            e = edges[ei]
            pt = e[2] if e[0] == cur else e[3]
            far = e[3] if e[0] == cur else e[2]
            other = e[1] if e[0] == cur else e[0]
            pts.append(pt)
            cur = other
            nxt = None
            for j in adj[cur]:
                if not used[j]:
                    nxt = j; break
            if nxt is None:
                pts.append(far)
                break
            ei = nxt
        clean = [pts[0]]
        for p in pts[1:]:
            if len(clean) >= 2:
                (x1, y1), (x2, y2) = clean[-2], clean[-1]
                if (x1 == x2 == p[0]) or (y1 == y2 == p[1]):
                    clean.pop()
            clean.append(p)
        if len(clean) >= 2:
            paths.append(clean)

    def attach(p):
        for b in boxes:
            x0, x1 = b["x"]; y0, y1 = b["y"]
            cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2
            for site, (sx, sy) in (("t", (cxm, y0)), ("b", (cxm, y1)),
                                   ("l", (x0, cym)), ("r", (x1, cym))):
                if abs(p[0] - sx) <= 6 and abs(p[1] - sy) <= 6:
                    return b["name"], site
        return None
    SITE = {"t": 1, "l": 2, "b": 3, "r": 4}

    connectors, polylines, seen_pairs = [], [], set()
    for pts in paths:
        a = attach(pts[0]); z = attach(pts[-1])
        straight = len(pts) == 2 and (pts[0][0] == pts[1][0] or pts[0][1] == pts[1][1])
        if a and z and a[0] != z[0] and straight:
            key = tuple(sorted([a[0] + a[1], z[0] + z[1]]))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            connectors.append({"a": a[0], "sa": SITE[a[1]], "b": z[0], "sb": SITE[z[1]]})
        else:
            polylines.append([[int(px_), int(py_)] for px_, py_ in pts])
    return connectors, polylines

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

    boxes, line_colors = find_boxes(px, W, H)
    hs, vs = segments(px, W, H, boxes, line_colors)
    connectors, polylines = route(hs, vs, boxes)

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
            "Boxes are auto-named c<col>_r<row>; fill texts via a --texts overlay JSON.",
            "Routes are auto-grouped. Read the PNG once and sanity-check routing;",
            "edit connectors/polylines only where the drawing differs.",
            "Check arrowheads in the raster; note in _arrowheads.",
        ],
        "px": {"w": W, "h": H},
        "_estimated_font_size_pt": est,
        "_line_color": "%02X%02X%02X" % (line_colors[0]),
        "boxes": boxes,
        "connectors": connectors,
        "polylines": polylines,
    }
    json.dump(spec, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("boxes:", len(boxes), "| connectors:", len(connectors), "| polylines:",
          len(polylines), "| line:", spec["_line_color"], "| font est:", est, "->", a.out)

if __name__ == "__main__":
    main()
