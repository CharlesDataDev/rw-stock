"""Render luslec's RW item market stock as a set of forum images.

Reads the item market listings for the API key in TORN_KEY and writes
out/stock-1.png ... out/stock-N.png. Unused slots become a 1x1 transparent
PNG so the forum post can always reference all N files.

Local test without the API:  python render.py --sample listings.json
"""
import json, os, sys, time, io, urllib.request
from PIL import Image, ImageDraw, ImageFont

# ---------- settings ----------
OWNER = os.environ.get("OWNER_NAME", "luslec")
DISCOUNT = float(os.environ.get("DIRECT_DISCOUNT", "0.05"))   # 5% off for buying direct
SLOTS = int(os.environ.get("IMAGE_SLOTS", "10"))              # number of image files in the post
W = 552                       # width as shown on the forum
S = 2                         # render at 2x for sharp text
MAX_H = 520                   # max height of one image (logical px)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
UA = {"User-Agent": f"{OWNER}-rw-stock-images/1.0"}

BG = (24, 26, 31)
ROW = (30, 33, 39)
LINE = (44, 48, 57)
FG = (231, 233, 237)
MUTED = (150, 157, 171)
GREEN = (92, 201, 138)
ACCENT = (217, 164, 65)
RARITY = {
    "yellow": ((38, 38, 38), (88, 86, 30)),
    "orange": ((38, 38, 38), (110, 58, 18)),
    "red": ((38, 38, 38), (108, 26, 26)),
}
CATS = [("Primary", "Primary"), ("Secondary", "Secondary"), ("Melee", "Melee"), ("Defensive", "Armor")]


FONT_DIRS = [FONTS, "/usr/share/fonts/opentype/inter", "/usr/share/fonts/truetype/inter",
             "/usr/share/fonts/truetype/dejavu"]


def font(names, size):
    """First font found from the list; Inter is installed by the workflow, DejaVu is the fallback."""
    for n in names:
        for d in FONT_DIRS:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, int(size * S))
    return ImageFont.load_default(int(size * S))


BOLD = ["InterDisplay-Bold.otf", "Inter-Bold.otf", "Inter-Bold.ttf", "DejaVuSans-Bold.ttf"]
SEMI = ["Inter-SemiBold.otf", "Inter-SemiBold.ttf", "Inter-Medium.otf", "DejaVuSans-Bold.ttf"]
REG = ["Inter-Regular.otf", "Inter-Regular.ttf", "DejaVuSans.ttf"]
F_TITLE = font(BOLD, 22)
F_SUB = font(REG, 11.5)
F_CAT = font(SEMI, 12)
F_NAME = font(SEMI, 14.5)
F_SMALL = font(REG, 11.5)
F_STRIKE = font(REG, 11)
F_PRICE = font(SEMI, 15.5)


def money(n):
    return "$" + f"{int(round(n)):,}"


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return json.load(r)


def fetch_listings(key):
    rows, offset = [], 0
    while True:
        d = get_json(f"https://api.torn.com/v2/user/itemmarket?offset={offset}&limit=100&key={key}")
        if "error" in d:
            raise SystemExit(f"Torn API error: {d['error']}")
        batch = d.get("itemmarket", [])
        rows += batch
        if len(batch) < 100:
            return rows
        offset += 100
        time.sleep(1)


def item_image(item_id):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{item_id}.png")
    if not os.path.exists(p):
        for size in ("large@4x", "large@2x", "large"):
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        f"https://www.torn.com/images/items/{item_id}/{size}.png", headers=UA), timeout=30) as r:
                    data = r.read()
                Image.open(io.BytesIO(data)).verify()
                open(p, "wb").write(data)
                break
            except Exception:
                continue
    try:
        return Image.open(p).convert("RGBA")
    except Exception:
        return None


def gradient(w, h, top, bot):
    g = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return g


def text_w(draw, s, f):
    return draw.textlength(s, font=f)


def clip(draw, s, f, maxw):
    if text_w(draw, s, f) <= maxw:
        return s
    while s and text_w(draw, s + "…", f) > maxw:
        s = s[:-1]
    return s + "…"


# ---------- blocks: each draws itself onto a canvas at a y offset ----------
class Header:
    h = 64

    def __init__(self, count, updated):
        self.count, self.updated = count, updated

    def draw(self, im, d, y):
        d.text((16 * S, (y + 12) * S), f"{OWNER}'s RW stock", font=F_TITLE, fill=FG)
        sub = f"{self.count} items  ·  green = {int(DISCOUNT * 100)}% off when you trade with me direct  ·  updated {self.updated}"
        d.text((16 * S, (y + 42) * S), clip(d, sub, F_SUB, (W - 32) * S), font=F_SUB, fill=MUTED)


class CatHead:
    h = 30

    def __init__(self, label, n):
        self.label, self.n = label, n

    def draw(self, im, d, y):
        d.rectangle([0, y * S, W * S, (y + self.h) * S], fill=BG)
        d.rectangle([16 * S, (y + 9) * S, 19 * S, (y + 21) * S], fill=ACCENT)
        d.text((26 * S, (y + 8) * S), f"{self.label.upper()}  ·  {self.n}", font=F_CAT, fill=FG)


class Row:
    h = 70

    def __init__(self, x):
        self.x = x

    def draw(self, im, d, y):
        x, it = self.x, self.x["item"]
        d.rectangle([0, y * S, W * S, (y + self.h) * S], fill=ROW)
        d.line([(0, y * S), (W * S, y * S)], fill=LINE, width=S)
        # picture on rarity background
        tw, th, tx, ty = 104, 52, 16, y + 9
        top, bot = RARITY.get(it.get("rarity"), ((38, 38, 38), (70, 74, 82)))
        tile = gradient(tw * S, th * S, top, bot)
        mask = Image.new("L", tile.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, tile.size[0] - 1, tile.size[1] - 1], radius=6 * S, fill=255)
        pic = item_image(it["id"])
        if pic:
            pic.thumbnail(((tw - 8) * S, (th - 6) * S), Image.LANCZOS)
            tile = tile.convert("RGBA")
            tile.alpha_composite(pic, ((tile.size[0] - pic.size[0]) // 2, (tile.size[1] - pic.size[1]) // 2))
        im.paste(tile.convert("RGB"), (tx * S, ty * S), mask)
        # price block (right)
        price = x["price"]
        direct = round(price * (1 - DISCOUNT))
        right = (W - 16) * S
        s1, s2 = money(price), money(direct)
        w1 = text_w(d, s1, F_STRIKE)
        d.text((right - w1, (y + 15) * S), s1, font=F_STRIKE, fill=MUTED)
        d.line([(right - w1, (y + 22) * S), (right, (y + 22) * S)], fill=MUTED, width=S)
        w2 = text_w(d, s2, F_PRICE)
        d.text((right - w2, (y + 32) * S), s2, font=F_PRICE, fill=GREEN)
        pw = max(w1, w2) / S
        # text block
        lx = tx + tw + 12
        maxw = (W - 16 - pw - 14 - lx) * S
        name = it["name"] + (f"  ×{x['amount']}" if x.get("amount", 1) > 1 else "")
        d.text((lx * S, (y + 10) * S), clip(d, name, F_NAME, maxw), font=F_NAME, fill=FG)
        bon = " · ".join(f"{b['title']} {b['value']}%" for b in it.get("bonuses") or []) or "No bonus"
        d.text((lx * S, (y + 31) * S), clip(d, bon, F_SMALL, maxw), font=F_SMALL, fill=ACCENT)
        st = it.get("stats") or {}
        parts = []
        if st.get("damage") is not None: parts.append(f"DMG {st['damage']}")
        if st.get("accuracy") is not None: parts.append(f"ACC {st['accuracy']}")
        if st.get("armor") is not None: parts.append(f"ARM {st['armor']}")
        if st.get("quality") is not None: parts.append(f"Q {st['quality']}")
        d.text((lx * S, (y + 48) * S), clip(d, "  ".join(parts), F_SMALL, maxw), font=F_SMALL, fill=MUTED)


class Note:
    h = 34

    def __init__(self, text):
        self.text = text

    def draw(self, im, d, y):
        d.text((16 * S, (y + 10) * S), self.text, font=F_SUB, fill=MUTED)


def build_blocks(listings):
    rw = [x for x in listings if (x.get("item") or {}).get("rarity") in RARITY]
    blocks = [Header(sum(x.get("amount", 1) for x in rw), time.strftime("%d %b %H:%M TCT", time.gmtime()))]
    for typ, label in CATS:
        g = sorted([x for x in rw if x["item"].get("type") == typ], key=lambda x: -x["price"])
        if g:
            blocks.append(CatHead(label, len(g)))
            blocks += [Row(x) for x in g]
    other = [x for x in rw if x["item"].get("type") not in dict(CATS)]
    if other:
        blocks.append(CatHead("Other", len(other)))
        blocks += [Row(x) for x in sorted(other, key=lambda x: -x["price"])]
    if len(blocks) == 1:
        blocks.append(Note("Nothing listed right now. Message me for what's coming in."))
    return blocks


def paginate(blocks):
    pages, cur, h = [], [], 0
    for b in blocks:
        # keep a category header with at least one row after it
        if cur and h + b.h > MAX_H and not isinstance(cur[-1], CatHead):
            pages.append(cur); cur, h = [], 0
        elif cur and isinstance(b, CatHead) and h + b.h + Row.h > MAX_H:
            pages.append(cur); cur, h = [], 0
        cur.append(b); h += b.h
    if cur:
        pages.append(cur)
    if len(pages) > SLOTS:
        keep = pages[:SLOTS]
        shown = sum(isinstance(b, Row) for p in keep for b in p)
        total = sum(isinstance(b, Row) for p in pages for b in p)
        last = keep[-1]
        while sum(b.h for b in last) + Note.h > MAX_H and len(last) > 1:
            last.pop()
        while len(last) > 1 and isinstance(last[-1], CatHead):
            last.pop()
        shown = sum(isinstance(b, Row) for p in keep for b in p)
        last.append(Note(f"+{total - shown} more listed on my item market."))
        pages = keep
    return pages


def render(listings):
    os.makedirs(OUT, exist_ok=True)
    pages = paginate(build_blocks(listings))
    for i in range(SLOTS):
        path = os.path.join(OUT, f"stock-{i + 1}.png")
        if i >= len(pages):
            Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(path)
            continue
        page = pages[i]
        h = sum(b.h for b in page) + (8 if i == len(pages) - 1 else 0)
        im = Image.new("RGB", (W * S, h * S), BG)
        d = ImageDraw.Draw(im)
        y = 0
        for b in page:
            b.draw(im, d, y)
            y += b.h
        im.save(path, optimize=True)
    print(f"Rendered {len(pages)} image(s) for {sum(isinstance(b, Row) for p in pages for b in p)} listing(s).")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--sample":
        data = json.load(open(sys.argv[2]))
        render(data.get("itemmarket", data))
    else:
        key = os.environ.get("TORN_KEY")
        if not key:
            raise SystemExit("Set TORN_KEY to a Torn API key (Limited access is enough).")
        render(fetch_listings(key))
