import logging
import time
from datetime import datetime, timedelta, timezone

from pyrogram.errors import UserNotParticipant

import config
import database as db
from utils.ui import btn, esc, kb

log = logging.getLogger("access")


def _exp_text(ts):
    return db.fmt_time(ts) if ts else "Lifetime"


async def alert_admins(c, text):
    for a in await db.admin_ids():
        try:
            await c.send_message(a, text)
        except Exception:
            pass


async def _make_link(c, chat_id, order_id):
    exp = datetime.now(timezone.utc) + timedelta(hours=config.LINK_VALID_HOURS)
    l = await c.create_chat_invite_link(
        chat_id, name=order_id[:32], expire_date=exp, creates_join_request=True
    )
    return l.invite_link


async def _revoke(c, chat_id, link):
    if not link:
        return
    try:
        await c.revoke_chat_invite_link(chat_id, link)
    except Exception:
        pass


async def grant(c, uid, p, o, again):
    """Payment ke baad channel access. Returns (text, button_rows)."""
    chat_id, title = p["chat_id"], p.get("chat_title") or "Channel"
    days = o.get("plan_days") or 0
    sub = await db.find_sub(uid, chat_id)
    renew = [[btn("🔄 Renew", f"p:{p['_id']}", color="plan")]]

    if sub and sub["status"] == "active":
        if again:
            return f"✅ Aap pehle se member ho.\n⏰ Expires: {_exp_text(sub.get('expires_at'))}", []
        exp = await db.extend_sub(sub, days)
        return (f"✅ <b>Plan extend ho gaya!</b>\n📢 {esc(title)}\n⏰ Naya expiry: {_exp_text(exp)}"), []

    if sub and sub["status"] == "expired":
        if again:  # expire ke baad free access nahi
            return "⏰ Plan expire ho chuka hai.\nAccess ke liye Renew karo 👇", renew
        try:  # expiry par ban kiya tha, naye payment par unban
            await c.unban_chat_member(chat_id, uid)
        except Exception:
            pass

    try:
        link = await _make_link(c, chat_id, o["_id"])
    except Exception as e:
        log.error("invite link failed order=%s: %s", o["_id"], e)
        await alert_admins(
            c,
            "⚠️ <b>Invite link nahi bana</b>\n"
            f"🧾 <code>{o['_id']}</code>\n👤 <code>{uid}</code>\n📢 {esc(title)}\n"
            f"<code>{esc(str(e)[:200])}</code>\n\n"
            "Bot ko channel me admin banao (Invite Users), phir Orders → Resend Product karo.",
        )
        return "⚠️ Join link abhi nahi ban paya. Admin ko alert bhej diya, jaldi mil jayega.", []

    if sub and sub["status"] == "pending":
        await _revoke(c, chat_id, sub.get("link"))
        total = sub["days"] if again else sub["days"] + days
        await db.update_sub(sub["_id"], {"link": link, "days": total, "order_id": o["_id"]})
    else:
        total = days
        u = await db.get_user(uid) or {}
        await db.create_sub({
            "user_id": uid, "user_name": u.get("name"), "chat_id": chat_id, "chat_title": title,
            "product_id": p["_id"], "product_name": p["name"], "plan_name": o.get("plan_name") or "",
            "days": days, "order_id": o["_id"], "link": link,
        })

    validity = f"{total} din" if total else "Lifetime"
    text = (
        f"📢 <b>{esc(title)}</b>\n"
        f"⏳ Validity: <b>{validity}</b> (join karte hi shuru hoga)\n"
        f"🔗 Neeche button se join request bhejo, link {config.LINK_VALID_HOURS} ghante valid hai."
    )
    return text, [[btn(f"🔗 Join {title[:24]}", url=link, color="join")]]


async def remove_sub(c, sub, by_admin=False):
    """Channel se hatao (ban) + user ko alert. Renew par grant() unban kar deta hai."""
    try:
        await c.ban_chat_member(sub["chat_id"], sub["user_id"])
    except UserNotParticipant:
        pass
    await db.update_sub(sub["_id"], {"status": "expired", "removed_at": time.time()})
    head = "🚫 Admin ne aapka access hata diya." if by_admin else "⏰ <b>Plan expire ho gaya</b>"
    try:
        await c.send_message(
            sub["user_id"],
            f"{head}\n📢 {esc(sub['chat_title'])} se access hata diya gaya.\n\nPhir se access ke liye Renew karo 👇",
            reply_markup=kb([btn("🔄 Renew", f"p:{sub['product_id']}", color="plan")]),
        )
    except Exception:
        pass
