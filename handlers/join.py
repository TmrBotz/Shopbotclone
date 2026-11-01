import logging
import time

from pyrogram import Client

import database as db
from utils.ui import btn, esc, kb

log = logging.getLogger("join")


@Client.on_chat_join_request()
async def on_join(c, r):
    """Sirf buyer ki request approve hoti hai; link join hote hi revoke."""
    link = r.invite_link.invite_link if r.invite_link else None
    if not link:
        return
    sub = await db.sub_by_link(link)
    if not sub:  # hamara banaya link nahi, kuch mat karo
        return

    uid, chat_id = r.from_user.id, r.chat.id
    now = time.time()
    exp = now + sub["days"] * 86400 if sub["days"] else None

    if sub["user_id"] != uid or not await db.activate_sub(sub["_id"], now, exp):
        try:
            await c.decline_chat_join_request(chat_id, uid)
        except Exception:
            pass
        return

    try:
        await c.approve_chat_join_request(chat_id, uid)
    except Exception as e:
        log.error("approve failed uid=%s: %s", uid, e)
        await db.update_sub(sub["_id"], {"status": "pending", "joined_at": None, "expires_at": None})
        return

    try:
        await c.revoke_chat_invite_link(chat_id, link)
    except Exception:
        pass

    try:
        await c.send_message(
            uid,
            "🎉 <b>Joined!</b>\n\n"
            f"📢 {esc(sub['chat_title'])}\n"
            f"📅 Joined: {db.fmt_time(now)}\n"
            f"⏰ Expires: {db.fmt_time(exp) if exp else 'Lifetime'}",
            reply_markup=kb([btn("🏠 Home", "home", color="home")]),
        )
    except Exception:
        pass
