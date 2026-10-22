import re
import time

from py_yt import VideosSearch

import config
from ShiviMusic.logging import LOGGER
from ShiviMusic.core.mongo import mongodb
from ShiviMusic.utils.database import is_autoplay
from ShiviMusic.utils.stream.queue import put_queue

AUTOPLAY_USER = "ᴀᴜᴛᴏᴘʟᴀʏ"
NO_REPEAT_SECONDS = 12 * 60 * 60  # a song is not autoplayed again for 12 hours

historydb = mongodb.autoplay_history
_history = {}  # chat_id -> {key: unix_time}; keys are video ids and "t:<title>"


def _title_key(title: str) -> str:
    return "t:" + re.sub(r"[^a-z0-9]+", " ", _clean_title(title).lower()).strip()


def _clean_title(title: str) -> str:
    title = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", title)  # (Official Video) etc.
    title = re.sub(r"\|\|.*$|\|.*$", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _prune(hist: dict):
    limit = time.time() - NO_REPEAT_SECONDS
    for k in [k for k, t in hist.items() if t < limit]:
        del hist[k]


async def _load(chat_id: int) -> dict:
    """History survives restarts: cached in memory, backed by MongoDB."""
    if chat_id not in _history:
        hist = {}
        try:
            doc = await historydb.find_one({"chat_id": chat_id})
            for item in (doc or {}).get("played", []):
                hist[item["k"]] = item["t"]
        except Exception as e:
            LOGGER(__name__).warning(f"autoplay history load failed: {e}")
        _history[chat_id] = hist
    _prune(_history[chat_id])
    return _history[chat_id]


async def remember(chat_id: int, vidid: str, title: str = ""):
    hist = await _load(chat_id)
    now = time.time()
    hist[vidid] = now
    if title:
        hist[_title_key(title)] = now
    try:
        await historydb.update_one(
            {"chat_id": chat_id},
            {"$set": {"played": [{"k": k, "t": t} for k, t in hist.items()]}},
            upsert=True,
        )
    except Exception as e:
        LOGGER(__name__).warning(f"autoplay history save failed: {e}")


async def find_next(chat_id: int, title: str, vidid: str):
    """Return (title, duration, vidid) of a similar song not played recently."""
    await remember(chat_id, vidid, title)
    played = await _load(chat_id)
    query = _clean_title(title) or title
    # try progressively looser searches until one gives a usable result
    for q in (f"{query} songs", query, f"{query} similar songs playlist"):
        try:
            results = (await VideosSearch(q, limit=25).next())["result"]
        except Exception as e:
            LOGGER(__name__).warning(f"autoplay search failed for '{q}': {e}")
            continue
        for r in results:
            rid = r.get("id")
            dur = r.get("duration")
            if not rid or not dur:  # no duration = live stream
                continue
            if rid in played or _title_key(r.get("title", "")) in played:
                continue  # played in the last 12 hours
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
        await remember(chat_id, vidid, title)  # block repeats right away
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
    except Exception as e:
        LOGGER(__name__).warning(f"autoplay failed in {chat_id}: {e}")
        return False
