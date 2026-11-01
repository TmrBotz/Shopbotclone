import aiohttp
from pyrogram import filters

from manager import settings as S
from manager import store
from manager.ui import STATE, btn, kb


async def _allowed(_, __, u):
    return bool(u.from_user) and await store.is_allowed(u.from_user.id)


allowed_f = filters.create(_allowed)
owner_f = filters.create(lambda _, __, u: bool(u.from_user) and u.from_user.id == S.OWNER_ID)
in_state = filters.create(lambda _, __, m: bool(m.from_user) and m.from_user.id in STATE)


def menu(uid):
    rows = [[btn("➕ Clone Bot", "m:new"), btn("🤖 My Bots", "m:list:me")]]
    if uid == S.OWNER_ID:
        rows.append([btn("📋 All Bots", "m:list:all"), btn("👥 Admins", "m:al")])
    return kb(*rows)


MENU_TEXT = (
    "🏭 <b>Shop Bot Manager</b>\n\n"
    "Yaha se shop bot ke clones banao aur manage karo.\n"
    "Har clone bilkul main shop bot jaisa hi chalta hai."
)


def can_manage(c, uid):
    return bool(c) and (uid == S.OWNER_ID or c.get("created_by") == uid)


async def tg_call(token, method, **params):
    """Telegram Bot API call (clone ke token se). Returns json dict."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(url, params=params) as r:
                return await r.json(content_type=None)
    except Exception:
        return {"ok": False}


async def get_me(token):
    j = await tg_call(token, "getMe")
    return j.get("result") if j.get("ok") else None


async def in_store_channel(token, bot_id):
    """Clone bot store channel me admin (post permission ke saath) hai ya nahi."""
    j = await tg_call(token, "getChatMember", chat_id=S.STORE_CHANNEL_ID, user_id=bot_id)
    if not j.get("ok"):
        return False
    r = j["result"]
    if r.get("status") == "creator":
        return True
    return r.get("status") == "administrator" and r.get("can_post_messages", True)
