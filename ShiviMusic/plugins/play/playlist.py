import re

from pyrogram import filters
from pyrogram.types import Message

from ShiviMusic import YouTube, app
from ShiviMusic.misc import db
from ShiviMusic.utils.database import (
    _get_playlists,
    delete_playlist,
    save_playlist,
)
from ShiviMusic.utils.decorators.play import PlayWrapper
from ShiviMusic.utils.stream.stream import stream
from config import BANNED_USERS

MAX_SONGS = 50  # per user

# Personal playlists are stored per *user id* in the existing `playlist` collection.
# Layout: {video_id: {"title": str, "duration": str}}


async def _list(user_id: int):
    return list((await _get_playlists(user_id)).items())


@app.on_message(filters.command(["addplaylist"]) & ~BANNED_USERS)
async def add_playlist(client, message: Message):
    if not message.from_user:
        return
    user_id = message.from_user.id
    query = None
    if len(message.command) > 1:
        query = message.text.split(None, 1)[1].strip()
    else:
        playing = db.get(message.chat.id)
        if playing:
            query = playing[0]["vidid"]
    if not query:
        return await message.reply_text(
            "**❖ ᴜsᴀɢᴇ :**\n`/addplaylist <song name / youtube link>`\n\n"
            "ᴏʀ ᴜsᴇ `/addplaylist` ᴡʜɪʟᴇ ᴀ sᴏɴɢ ɪs ᴘʟᴀʏɪɴɢ ᴛᴏ sᴀᴠᴇ ɪᴛ."
        )
    mystic = await message.reply_text("**🔎 sᴇᴀʀᴄʜɪɴɢ...**")
    try:
        title, duration, _sec, _thumb, vidid = await YouTube.details(query)
    except Exception:
        return await mystic.edit_text("**» ᴄᴏᴜʟᴅ ɴᴏᴛ ғɪɴᴅ ᴛʜᴀᴛ sᴏɴɢ.**")
    saved = await _get_playlists(user_id)
    if vidid in saved:
        return await mystic.edit_text("**» ᴛʜɪs sᴏɴɢ ɪs ᴀʟʀᴇᴀᴅʏ ɪɴ ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ.**")
    if len(saved) >= MAX_SONGS:
        return await mystic.edit_text(
            f"**» ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ ɪs ғᴜʟʟ ({MAX_SONGS} sᴏɴɢs). ʀᴇᴍᴏᴠᴇ ᴏɴᴇ ᴡɪᴛʜ /delplaylist.**"
        )
    await save_playlist(
        user_id, vidid, {"title": title, "duration": str(duration)}
    )
    await mystic.edit_text(
        f"**✅ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ**\n\n`{title[:70]}` • {duration}\n\n"
        f"ᴛᴏᴛᴀʟ sᴏɴɢs : {len(saved) + 1}"
    )


@app.on_message(filters.command(["playlist"]) & ~BANNED_USERS)
async def show_playlist(client, message: Message):
    if not message.from_user:
        return
    items = await _list(message.from_user.id)
    if not items:
        return await message.reply_text(
            "**» ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ ɪs ᴇᴍᴘᴛʏ.**\n\nᴀᴅᴅ sᴏɴɢs ᴡɪᴛʜ `/addplaylist <song>`"
        )
    text = f"**❖ ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ ({len(items)} sᴏɴɢs)**\n\n"
    for i, (_vid, info) in enumerate(items, 1):
        text += f"**{i}.** {info['title'][:60]} • `{info['duration']}`\n"
    text += "\n» ᴘʟᴀʏ ɪɴ ɢʀᴏᴜᴘ : `/playplaylist`\n» ʀᴇᴍᴏᴠᴇ : `/delplaylist <number|all>`"
    await message.reply_text(text)


@app.on_message(filters.command(["delplaylist"]) & ~BANNED_USERS)
async def del_playlist(client, message: Message):
    if not message.from_user:
        return
    user_id = message.from_user.id
    items = await _list(user_id)
    if len(message.command) < 2:
        return await message.reply_text(
            "**❖ ᴜsᴀɢᴇ :** `/delplaylist <number>` ᴏʀ `/delplaylist all`"
        )
    if not items:
        return await message.reply_text("**» ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ᴇᴍᴘᴛʏ.**")
    arg = message.command[1].lower()
    if arg == "all":
        for vid, _info in items:
            await delete_playlist(user_id, vid)
        return await message.reply_text("**🗑 ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ ʜᴀs ʙᴇᴇɴ ᴄʟᴇᴀʀᴇᴅ.**")
    if not arg.isdigit() or not 1 <= int(arg) <= len(items):
        return await message.reply_text(
            f"**» ᴄʜᴏᴏsᴇ ᴀ ɴᴜᴍʙᴇʀ ʙᴇᴛᴡᴇᴇɴ 1 ᴀɴᴅ {len(items)} (sᴇᴇ /playlist).**"
        )
    vid, info = items[int(arg) - 1]
    await delete_playlist(user_id, vid)
    await message.reply_text(f"**🗑 ʀᴇᴍᴏᴠᴇᴅ :** `{info['title'][:70]}`")


@app.on_message(
    filters.command(["playplaylist", "vplayplaylist", "cplayplaylist"])
    & filters.group
    & ~BANNED_USERS
)
@PlayWrapper
async def play_my_playlist(
    client,
    message: Message,
    _,
    chat_id,
    video,
    channel,
    playmode,
    url,
    fplay,
):
    user_id = message.from_user.id
    items = await _list(user_id)
    if not items:
        return await message.reply_text(
            "**» ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ ɪs ᴇᴍᴘᴛʏ.**\n\nᴀᴅᴅ sᴏɴɢs ᴡɪᴛʜ `/addplaylist <song>`"
        )
    mystic = await message.reply_text(
        _["play_2"].format(channel) if channel else _["play_1"]
    )
    try:
        await stream(
            _,
            mystic,
            user_id,
            [vid for vid, _info in items],
            chat_id,
            message.from_user.first_name,
            message.chat.id,
            video,
            streamtype="playlist",
            spotify=False,
            forceplay=fplay,
        )
    except Exception as e:
        ex_type = type(e).__name__
        err = e if ex_type == "AssistantErr" else _["general_2"].format(ex_type)
        return await mystic.edit_text(err)
    return await mystic.delete()


@app.on_callback_query(filters.regex("favplay_song") & ~BANNED_USERS)
async def fav_song_cb(client, CallbackQuery):
    """❤️ button under the now-playing message: save the song to the clicker's playlist."""
    try:
        chat_id = int(CallbackQuery.data.split(None, 1)[1])
    except Exception:
        return await CallbackQuery.answer()
    queue = db.get(chat_id)
    if not queue:
        return await CallbackQuery.answer("» ɴᴏᴛʜɪɴɢ ɪs ᴘʟᴀʏɪɴɢ ʀɪɢʜᴛ ɴᴏᴡ.", show_alert=True)
    track = queue[0]
    vidid = track.get("vidid")
    if not vidid or not re.fullmatch(r"[\w-]{11}", str(vidid)):  # YouTube ids only
        return await CallbackQuery.answer("» ᴛʜɪs ᴛʀᴀᴄᴋ ᴄᴀɴ'ᴛ ʙᴇ sᴀᴠᴇᴅ.", show_alert=True)
    user_id = CallbackQuery.from_user.id
    saved = await _get_playlists(user_id)
    if vidid in saved:
        return await CallbackQuery.answer("» ᴀʟʀᴇᴀᴅʏ ɪɴ ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ ❤️", show_alert=True)
    if len(saved) >= MAX_SONGS:
        return await CallbackQuery.answer(
            f"» ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ ɪs ғᴜʟʟ ({MAX_SONGS}). ᴜsᴇ /delplaylist.", show_alert=True
        )
    await save_playlist(
        user_id, vidid, {"title": track["title"], "duration": str(track["dur"])}
    )
    await CallbackQuery.answer("❤️ sᴀᴠᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴘʟᴀʏʟɪsᴛ!", show_alert=True)
