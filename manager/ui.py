import html

from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

esc = html.escape
STATE = {}  # {user_id: {"flow": "new"|"token"|"admin", "step": str, "data": {}, "cid": str}}


def btn(text, cb=None, url=None):
    return InlineKeyboardButton(text, callback_data=cb, url=url)


def kb(*rows):
    return InlineKeyboardMarkup([list(r) for r in rows if r])


async def edit(q, text, markup=None):
    try:
        await q.message.edit_text(text, reply_markup=markup)
    except MessageNotModified:
        pass


async def wipe(m):
    """Token / API key wala message turant delete."""
    try:
        await m.delete()
    except Exception:
        pass
