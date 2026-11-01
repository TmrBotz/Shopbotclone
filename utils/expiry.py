import asyncio
import logging
import time

import database as db
from utils import access
from utils.ui import btn, esc, kb

log = logging.getLogger("expiry")
INTERVAL = 600  # har 10 min


async def tick(c):
    now = time.time()

    # 1 din pehle alert
    for s in await db.subs_to_remind(now):
        await db.update_sub(s["_id"], {"reminded": True})
        plan = f" — {esc(s['plan_name'])}" if s.get("plan_name") else ""
        try:
            await c.send_message(
                s["user_id"],
                "⚠️ <b>Plan kal expire ho jayega</b>\n\n"
                f"📦 {esc(s['product_name'])}{plan}\n📢 {esc(s['chat_title'])}\n"
                f"⏰ Expires: {db.fmt_time(s['expires_at'])}\n\nAccess na ruke isliye Renew karo 👇",
                reply_markup=kb([btn("🔄 Renew", f"p:{s['product_id']}", color="plan")]),
            )
        except Exception as e:
            log.warning("reminder failed uid=%s: %s", s["user_id"], e)

    # expire hone par channel se remove
    for s in await db.subs_expired(now):
        try:
            await access.remove_sub(c, s)
        except Exception as e:
            log.error("remove failed uid=%s chat=%s: %s", s["user_id"], s["chat_id"], e)
            if not s.get("alerted"):
                await db.update_sub(s["_id"], {"alerted": True})
                await access.alert_admins(
                    c,
                    "⚠️ <b>User ko remove nahi kar paya</b>\n"
                    f"👤 <code>{s['user_id']}</code>\n📢 {esc(s['chat_title'])}\n"
                    f"<code>{esc(str(e)[:150])}</code>\n\nBot ko <b>Ban Users</b> permission do. Bot khud dobara try karega.",
                )


async def loop(c):
    await asyncio.sleep(15)
    while True:
        try:
            await tick(c)
        except Exception:
            log.exception("expiry tick failed")
        await asyncio.sleep(INTERVAL)
