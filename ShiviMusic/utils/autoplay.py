import re

from py_yt import VideosSearch

import config
from ShiviMusic.misc import db
from ShiviMusic.utils.database import is_autoplay
from ShiviMusic.utils.stream.queue import put_queue

_history = {}  # chat_id -> recently played video ids
HISTORY_SIZE = 25
AUTOPLAY_USER = "ᴀᴜᴛᴏᴘʟᴀʏ"


def remember(chat_id: int, vidid: str):
    hist = _history.setdefault(chat_id, [])
    if vidid in hist:
        hist.remove(vidid)
    hist.append(vidid)
    del hist[:-HISTORY_SIZE]


def _clean_title(title: str) -> str:
    title = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", title)  # (Official Video) etc.
    title = re.sub(r"\|\|.*$|\|.*$", " ", title)
    return re.sub(r"\s+", " ", title).strip()


async def find_next(chat_id: int, title: str, vidid: str):
    """Return (title, duration, vidid) of a similar song not played recently."""
    remember(chat_id, vidid)
    played = set(_history.get(chat_id, []))
    query = _clean_title(title) or title
    results = (await VideosSearch(f"{query} songs", limit=12).next())["result"]
    for r in results:
        rid = r.get("id")
        dur = r.get("duration")
        if not rid or rid in played or not dur:  # no duration = live stream
            continue
        try:
            if config.time_to_seconds(dur) > config.DURATION_LIMIT:
                continue
        except Exception:
            continue
        return r["title"], dur, rid
    return None


async def queue_autoplay_track(chat_id: int, popped: dict) -> bool:
    """When the queue has just run empty, queue a similar song if autoplay is on.

    Returns True when a track was added (db[chat_id] then has one item)."""
    try:
        if not await is_autoplay(chat_id):
            return False
        found = await find_next(chat_id, popped["title"], popped["vidid"])
        if not found:
            return False
        title, dur, vidid = found
        stype = "video" if str(popped.get("streamtype")) == "video" else "audio"
        await put_queue(
            chat_id,
            popped["chat_id"],
            f"vid_{vidid}",
            title,
            dur,
            AUTOPLAY_USER,
            vidid,
            popped.get("user_id"),
            stype,
        )
        return True
    except Exception:
        return False
