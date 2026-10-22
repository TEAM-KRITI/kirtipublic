import os
import re
import aiohttp
import aiofiles
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ═══════════════════════════════════════════════════════════════════
# THUMBNAIL GENERATOR - VERSION 5 (Framed Poster Edition)
# Layout: blurred dark bg, pink bevel frame, big art, title + meta below
# ═══════════════════════════════════════════════════════════════════

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE_DIR, "..", "assets")
FONT_TITLE = os.path.join(ASSETS, "f.ttf")          # Honey Salt (title)
FONT_META = os.path.join(ASSETS, "font.ttf")        # Poppins SemiBold
FONT_BOLD = os.path.join(ASSETS, "Poppins-Bold.ttf")  # Poppins Bold (watermarks)

W, H = 1280, 720

# ---- layout ----------------------------------------------------------------
FRAME = (187, 89, 1093, 566)     # outer frame box
FRAME_W = 32                     # frame thickness
ART = (219, 121, 1061, 533)      # artwork box inside the frame (842 x 412)

# ---- colours ---------------------------------------------------------------
FRAME_DARK = (160, 93, 147)
FRAME_LIGHT = (222, 154, 205)
GLOW = (214, 130, 200)
TEXT_WHITE = (255, 255, 255)
META_PINK = (221, 155, 201)
YELLOW = (255, 230, 50)

# ---- text ------------------------------------------------------------------
DEV_TEXT = "Dev :- @kirti_bots"
OWNER_TEXT = "@System_xd_III"
DEFAULT_PLAYER = "@Kirtiprobot"

FALLBACK_THUMB = "https://o.uguu.se/snWhWXPT.jpg"

_thumb_memory: dict = {}  # videoid -> output_path


@lru_cache(maxsize=16)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    for p in (path, FONT_META, FONT_TITLE):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _player_name() -> str:
    """Bot username shown as `Player`; falls back to the default handle."""
    try:
        from ShiviMusic import app

        if getattr(app, "username", None):
            return f"@{app.username}"
    except Exception:
        pass
    try:
        from config import BOT_USERNAME

        if BOT_USERNAME:
            return f"@{BOT_USERNAME.lstrip('@')}"
    except Exception:
        pass
    return DEFAULT_PLAYER


def _truncate(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "...", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "..."


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Resize + centre-crop so the image fully covers w x h."""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale) + 1, int(ih * scale) + 1
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _make_bg(song_img: Image.Image) -> Image.Image:
    bg = _cover(song_img.convert("RGB"), W, H).filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.5).convert("RGBA")

    # dark cinematic overlay
    bg = Image.alpha_composite(bg, Image.new("RGBA", (W, H), (6, 2, 2, 110)))

    # vignette
    vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vig)
    for i in range(200, 0, -8):
        vd.rectangle([0, 0, W, H], outline=(0, 0, 0, int(170 * (1 - i / 200))), width=i)
    vig = vig.filter(ImageFilter.GaussianBlur(60))
    return Image.alpha_composite(bg, vig)


def _draw_frame(base: Image.Image) -> Image.Image:
    x1, y1, x2, y2 = FRAME
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # soft outer glow
    for i in range(36, 0, -1):
        a = int(70 * (1 - i / 36) ** 1.6)
        d.rectangle([x1 - i, y1 - i, x2 + i, y2 + i], fill=(*GLOW, a))
    layer = layer.filter(ImageFilter.GaussianBlur(16))
    base = Image.alpha_composite(base.convert("RGBA"), layer)

    # bevelled frame: dark edge -> light ridge -> dark edge
    fl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fl)
    t = FRAME_W
    for i in range(t):
        k = 1 - abs((i + 0.5) - t / 2) / (t / 2)  # 0 at edges, 1 at middle
        k = k ** 0.8
        col = tuple(int(FRAME_DARK[c] + (FRAME_LIGHT[c] - FRAME_DARK[c]) * k) for c in range(3))
        fd.rectangle([x1 + i, y1 + i, x2 - i, y2 - i], outline=(*col, 255), width=1)
    return Image.alpha_composite(base, fl).convert("RGB")


def _paste_art(base: Image.Image, song_img: Image.Image) -> Image.Image:
    x1, y1, x2, y2 = ART
    art = _cover(song_img.convert("RGB"), x2 - x1, y2 - y1)
    base = base.copy()
    base.paste(art, (x1, y1))
    return base


async def get_thumb(videoid: str, user_name: str = None) -> str:
    output = f"cache/{videoid}.png"
    cache = f"cache/thumb{videoid}.jpg"
    os.makedirs("cache", exist_ok=True)

    # always regenerate so the player/views stay fresh
    if os.path.exists(output):
        try:
            os.remove(output)
        except Exception:
            pass

    # 1) metadata
    url = f"https://www.youtube.com/watch?v={videoid}"
    try:
        from py_yt import VideosSearch

        data = (await VideosSearch(url, limit=1).next())["result"][0]
        title = re.sub(r"[\x00-\x1f\x7f]", "", data.get("title", "Unknown")).strip()
        duration = data.get("duration", "00:00") or "00:00"
        thumb_url = data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0]
        v_raw = str((data.get("viewCount") or {}).get("short", "N/A"))
        vc = re.sub(r"\s*views?\s*", "", v_raw, flags=re.IGNORECASE).strip()
    except Exception:
        return FALLBACK_THUMB

    # 2) artwork
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(thumb_url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                async with aiofiles.open(cache, "wb") as f:
                    await f.write(await r.read())
        song_img = Image.open(cache).convert("RGB")
    except Exception:
        song_img = Image.new("RGB", (777, 458), (28, 10, 5))

    # 3) compose
    base = _make_bg(song_img).convert("RGB")
    base = _draw_frame(base)
    base = _paste_art(base, song_img)
    draw = ImageDraw.Draw(base)

    f_title = _font(FONT_TITLE, 34)
    f_meta = _font(FONT_META, 23)
    f_dev = _font(FONT_BOLD, 23)
    f_own = _font(FONT_BOLD, 24)

    # title (soft shadow + white)
    title_text = _truncate(draw, title, f_title, 840)
    draw.text((642, 609), title_text, font=f_title, fill=(0, 0, 0), anchor="mm")
    draw.text((640, 607), title_text, font=f_title, fill=TEXT_WHITE, anchor="mm")

    # meta line
    meta = f"YouTube : {vc} views | Time : {duration} | Player : {_player_name()}"
    meta = _truncate(draw, meta, f_meta, 1100)
    draw.text((641, 643), meta, font=f_meta, fill=(0, 0, 0), anchor="mm")
    draw.text((640, 641), meta, font=f_meta, fill=META_PINK, anchor="mm")

    # watermarks
    draw.text((1255, 47), DEV_TEXT, font=f_dev, fill=YELLOW, anchor="rm")
    draw.text((25, 691), OWNER_TEXT, font=f_own, fill=YELLOW, anchor="lm")

    base.save(output, "PNG", optimize=True)

    try:
        if os.path.exists(cache):
            os.remove(cache)
    except Exception:
        pass

    _thumb_memory[videoid] = output
    return output
