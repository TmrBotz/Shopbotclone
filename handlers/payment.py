import logging
import re
import time

from pyrogram import Client, filters

import config
import database as db
from utils.ui import P, R, STATE, btn, deliver, esc, kb, money, order_title
from utils.verify import verify_payment

log = logging.getLogger("payment")

BUSY = set()   # per-user lock
LAST = {}      # last verify time per user
FAILS = {}     # uid -> (wrong count, blocked_until)
COOLDOWN, MAX_FAILS, BLOCK_SEC = 10, 5, 600

not_in_state = filters.create(lambda _, __, m: bool(m.from_user) and m.from_user.id not in STATE)
def HOME():
    return kb([btn("🏠 Home", "home", color=P)])


@Client.on_message(filters.private & filters.text & ~filters.regex(r"^/") & not_in_state)
async def utr_handler(c, m):
    uid = m.from_user.id
    order = await db.pending_order(uid)
    if not order:
        return await m.reply_text(
            "❌ Koi active order nahi hai.\nPehle product chuno aur <b>Buy Now</b> dabao.",
            reply_markup=HOME(),
        )

    utr = re.sub(r"\D", "", m.text)
    if len(utr) != 12:
        return await m.reply_text("⚠️ UTR sahi format me bhejo — <b>12 digit</b> number.")

    if uid in BUSY:  # double tap / spam
        return
    now = time.time()
    blocked_until = FAILS.get(uid, (0, 0))[1]
    if blocked_until > now:
        return await m.reply_text(
            f"🚫 Bahut galat UTR ho gaye. {int((blocked_until - now) // 60) + 1} min baad try karo."
        )
    if now - LAST.get(uid, 0) < COOLDOWN:
        return await m.reply_text(f"⏳ {int(COOLDOWN - (now - LAST[uid])) + 1} sec ruko, phir bhejo.")
    if await db.utr_used(utr):
        return await m.reply_text("❌ Ye UTR pehle hi use ho chuka hai.")

    BUSY.add(uid)
    LAST[uid] = now
    wait = await m.reply_text("⏳ <b>Verifying...</b>\nThoda ruko, kabhi kabhi 30-50 sec lag jaate hain.")
    try:
        await _handle(c, uid, wait, order, utr)
    except Exception:
        log.exception("verify flow failed")
        await wait.edit_text("⚠️ Abhi verify nahi ho pa raha, thodi der baad try karo.")
    finally:
        BUSY.discard(uid)


async def _handle(c, uid, wait, o, utr):
    status, data = await verify_payment(utr, o["amount"], o["_id"])

    if status == 200 and data.get("success"):
        FAILS.pop(uid, None)
        await wait.delete()
        if not await db.mark_paid(o["_id"], utr, data):  # already paid -> dobara deliver nahi
            return
        await deliver(c, uid, await db.get_product(o["product_id"]), order=o)
        await _notify_admins(c, uid, o, utr)
        return

    if status == 404:
        n = FAILS.get(uid, (0, 0))[0] + 1
        FAILS[uid] = (0, time.time() + BLOCK_SEC) if n >= MAX_FAILS else (n, 0)
        text = (
            "❌ <b>Payment verify nahi hui.</b>\n\n"
            "• UTR check karo\n"
            f"• Amount exact <b>₹{money(o['amount'])}</b> hona chahiye\n"
            "• Payment ke 10 min ke andar hi verify hota hai\n"
            "• Abhi pay kiya hai to 30 sec baad dobara UTR bhejo"
        )
    elif status == 400:
        text = "⚠️ UTR sahi format me bhejo (12 digit)."
    elif status == 429:
        text = "⏳ Thodi der baad try karo."
    else:
        log.error("verify failed status=%s order=%s", status, o["_id"])
        text = "⚠️ Abhi verify nahi ho pa raha, thodi der baad try karo."

    await wait.edit_text(
        text,
        reply_markup=kb([btn("❌ Cancel Order", f"cx:{o['_id']}", color=R)],
                        [btn("🏠 Home", "home", color=P)]),
    )


async def _notify_admins(c, uid, o, utr):
    text = (
        "💰 <b>New Payment</b>\n\n"
        f"📦 {order_title(o)}\n"
        f"💵 ₹{money(o['amount'])}\n"
        f"👤 <a href=\"tg://user?id={uid}\">{uid}</a>\n"
        f"🧾 <code>{o['_id']}</code>\n"
        f"🔢 UTR: <code>{utr}</code>"
    )
    for a in await db.admin_ids():
        try:
            await c.send_message(a, text)
        except Exception:
            pass
