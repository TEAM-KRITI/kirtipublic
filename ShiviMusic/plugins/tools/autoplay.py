from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message

from ShiviMusic import app
from ShiviMusic.misc import SUDOERS
from ShiviMusic.utils.database import is_autoplay, set_autoplay
from config import BANNED_USERS


async def _is_admin(message: Message) -> bool:
    user_id = message.from_user.id
    if user_id in SUDOERS:
        return True
    try:
        member = await app.get_chat_member(message.chat.id, user_id)
    except Exception:
        return False
    return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


@app.on_message(filters.command(["autoplay"]) & filters.group & ~BANNED_USERS)
async def autoplay_cmd(client, message: Message):
    if not message.from_user:
        return
    current = await is_autoplay(message.chat.id)
    if len(message.command) < 2:
        status = "ᴇɴᴀʙʟᴇᴅ ✅" if current else "ᴅɪsᴀʙʟᴇᴅ ❌"
        return await message.reply_text(
            f"**❖ ᴀᴜᴛᴏᴘʟᴀʏ ɪs {status}**\n\n"
            "ᴜsᴀɢᴇ : `/autoplay on` ᴏʀ `/autoplay off`"
        )
    if not await _is_admin(message):
        return await message.reply_text("**» ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴄʜᴀɴɢᴇ ᴀᴜᴛᴏᴘʟᴀʏ.**")
    arg = message.command[1].lower()
    if arg in ("on", "enable", "yes"):
        await set_autoplay(message.chat.id, True)
        await message.reply_text(
            "**❖ ᴀᴜᴛᴏᴘʟᴀʏ ᴇɴᴀʙʟᴇᴅ ✅**\n\n"
            "ᴡʜᴇɴ ᴛʜᴇ ǫᴜᴇᴜᴇ ᴇɴᴅs, ɪ ᴡɪʟʟ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴘʟᴀʏ ᴀ sɪᴍɪʟᴀʀ sᴏɴɢ."
        )
    elif arg in ("off", "disable", "no"):
        await set_autoplay(message.chat.id, False)
        await message.reply_text("**❖ ᴀᴜᴛᴏᴘʟᴀʏ ᴅɪsᴀʙʟᴇᴅ ❌**")
    else:
        await message.reply_text("ᴜsᴀɢᴇ : `/autoplay on` ᴏʀ `/autoplay off`")
