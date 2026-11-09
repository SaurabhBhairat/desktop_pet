r"""
make_texture.py - turns a picture of your dragon into the skin the desktop dragon wears.

    .\voice_env\Scripts\python.exe make_texture.py "C:\path\to\dragon_picture.png"

It finds the dragon in the picture (the biggest shape that differs from the background - dark,
light or transparent backgrounds all work), crops it tightly and saves  assets\models\dragon_texture.png.
The picture should show the whole dragon from the front, wing tip to wing tip and crest to feet.
"""
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError:
    sys.exit("Pillow is missing. Run:  .\\voice_env\\Scripts\\python.exe -m pip install pillow")

if len(sys.argv) < 2:
    sys.exit('Usage: make_texture.py "path\\to\\dragon_picture.png"')

src = Path(sys.argv[1].strip('"'))
out_dir = Path(__file__).resolve().parent / "assets" / "models"
out = out_dir / "dragon_texture.png"
if not src.is_file():
    sys.exit("Cannot find the picture: %s" % src)
if not out_dir.is_dir():
    sys.exit("Cannot find the folder: %s" % out_dir)

raw = Image.open(src)
alpha = None
if raw.mode in ("RGBA", "LA", "PA") or "transparency" in raw.info:
    rgba = raw.convert("RGBA")
    a_band = rgba.getchannel("A")
    if a_band.getextrema()[0] < 250:                      # the picture really has transparent parts
        alpha = a_band
        flat = Image.new("RGBA", rgba.size, (40, 15, 60, 255))
        flat.alpha_composite(rgba)                        # flatten onto dark purple
        im = flat.convert("RGB")
if alpha is None:
    im = raw.convert("RGB")
W, H = im.size

# "how different is each pixel from the background?"  (works for dark and light backgrounds)
bw = max(3, min(W, H) // 20)
pix = im.load()
edge = []
for cx0 in (0, W - bw):                    # the four corners: background even if the dragon touches the edges
    for cy0 in (0, H - bw):
        for x in range(cx0, cx0 + bw):
            for y in range(cy0, cy0 + bw):
                edge.append(pix[x, y])
bg = tuple(sorted(c[i] for c in edge)[len(edge) // 2] for i in range(3))
bg_light = int(0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2])
if bg_light < 128:                                        # dark background: the dragon is brighter
    lum = im.convert("L")
else:                                                     # light background: the dragon differs from it
    lum = ImageChops.difference(im.convert("L"), Image.new("L", im.size, bg_light))
if alpha is not None:
    lum = alpha                                           # transparency says exactly where the dragon is

# work on a small grid (about 200 cells wide)
scale = max(1, max(W, H) // 200)
gw, gh = (W + scale - 1) // scale, (H + scale - 1) // scale
sp = lum.resize((gw, gh), Image.BOX).load()

# automatic cut-off between "background" and "dragon" (Otsu), ignoring tiny differences
hist = lum.histogram()


def otsu(lo=30):
    total = sum(hist[lo:])
    allsum = sum(i * hist[i] for i in range(lo, 256))
    wb = sb = 0
    best_var, best_t = 0.0, 100
    for t in range(lo, 256):
        wb += hist[t]
        if wb == 0 or wb == total:
            continue
        sb += t * hist[t]
        wf = total - wb
        var = wb * wf * (sb / wb - (allsum - sb) / wf) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return best_t


def find_box(thr, reach=4):
    """Bounding box of the biggest shape of bright cells. Cells within `reach` of each other are
    joined (chin shadow, gaps between horns and wings); far-away bits such as UI icons stay apart."""
    bright = [[sp[x, y] > thr for x in range(gw)] for y in range(gh)]
    near = [[False] * gw for _ in range(gh)]
    for y in range(gh):
        for x in range(gw):
            if bright[y][x]:
                for yy in range(max(0, y - reach), min(gh, y + reach + 1)):
                    for xx in range(max(0, x - reach), min(gw, x + reach + 1)):
                        near[yy][xx] = True
    seen = [[False] * gw for _ in range(gh)]
    best = []
    for sy in range(gh):
        for sx in range(gw):
            if near[sy][sx] and not seen[sy][sx]:
                stack, cells = [(sx, sy)], []
                seen[sy][sx] = True
                while stack:
                    cx, cy = stack.pop()
                    cells.append((cx, cy))
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < gw and 0 <= ny < gh and near[ny][nx] and not seen[ny][nx]:
                                seen[ny][nx] = True
                                stack.append((nx, ny))
                members = [c for c in cells if bright[c[1]][c[0]]]
                if len(members) > len(best):
                    best = members
    if len(best) < 50:
        return None
    xs = [c[0] for c in best]
    ys = [c[1] for c in best]
    return (min(xs) * scale, min(ys) * scale, (max(xs) + 1) * scale, (max(ys) + 1) * scale)


# try a few cut-offs and keep the BIGGEST box that has a dragon-like shape (taller than wide).
# Too high a cut-off finds only the belly; too low a cut-off swallows the background.
t0 = otsu()
candidates, first = [], None
for thr in (t0, t0 + 15, t0 - 15, t0 + 30, t0 - 30):
    b = find_box(thr)
    if b is None:
        continue
    first = first or b
    w, h = b[2] - b[0], b[3] - b[1]
    if h > 0 and 0.35 <= w / h <= 0.8:
        candidates.append((w * h, b))
box = max(candidates)[1] if candidates else first
if box is None:
    sys.exit("Could not find the dragon in this picture (is it a dark background with the dragon in the middle?).")

pad = scale
left, top = max(0, box[0] - pad), max(0, box[1] - pad)
right, bottom = min(W, box[2] + pad), min(H, box[3] + pad)
crop = im.crop((left, top, right, bottom))
if crop.size[1] > 1100:                                   # keep the skin a sensible size
    k = 1100.0 / crop.size[1]
    crop = crop.resize((max(1, round(crop.size[0] * k)), 1100), Image.LANCZOS)
crop.save(out)
print("Picture size: %d x %d" % (W, H))
print("Dragon found at: left %d, top %d, right %d, bottom %d" % (left, top, right, bottom))
print("Saved %s  (%d x %d)" % (out, crop.size[0], crop.size[1]))
