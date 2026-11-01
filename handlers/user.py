from pyrogram import Client, filters
from pyrogram.types import ForceReply

import config
import database as db
from utils.qr import make_qr, upi_link
from utils.ui import (STATE, btn, deliver, esc, get_plans, kb, money, order_title, product_kb,
                      product_text, send_page, show)


async def home_view(uid, name):
    """Welcome (admin se editable) + product buttons. Returns (text, markup, photo)."""
    prods = await db.list_products(active_only=True)
    w = await db.get_setting("welcome") or {}
    if w.get("text"):
        text = w["text"].replace("{name}", esc(name)).replace("{store}", esc(config.STORE_NAME))
        if not prods:
            text += "\n\nAbhi koi product available nahi hai."
    else:
        text = (
            f"🛍 <b>{esc(config.STORE_NAME)}</b>\n\nNamaste <b>{esc(name)}</b> 👋\n"
            + ("Neeche se product chuno 👇" if prods else "Abhi koi product available nahi hai.")
        )
    items = [btn(p["name"], f"p:{p['_id']}", color="product") for p in prods]
    rows = [items[i:i + 2] for i in range(0, len(items), 2)]
    last = [btn("🛒 My Orders", "orders", color="nav")]
    if config.SUPPORT_USERNAME:
        last.append(btn("☎️ Support", url=f"https://t.me/{config.SUPPORT_USERNAME}", color="nav"))
    rows.append(last)
    if await db.is_admin(uid):
        rows.append([btn("⚙️ Admin Panel", "a:home", color="admin")])
    return text, kb(*rows), w.get("photo")


async def _live_product(pid):
    p = await db.get_product(pid)
    return p if p and p.get("active") and not p.get("deleted") else None


@Client.on_message(filters.command("start") & filters.private)
async def start(c, m):
    STATE.pop(m.from_user.id, None)
    await db.add_user(m.from_user)
    text, markup, photo = await home_view(m.from_user.id, m.from_user.first_name)
    await send_page(c, m.chat.id, text, markup, photo)


@Client.on_callback_query(filters.regex(r"^home$"))
async def home_cb(c, q):
    text, markup, photo = await home_view(q.from_user.id, q.from_user.first_name)
    await show(c, q, text, markup, photo=photo)


@Client.on_callback_query(filters.regex(r"^p:"))
async def product_cb(c, q):
    p = await _live_product(q.data[2:])
    if not p:
        return await q.answer("❌ Ye product available nahi hai.", show_alert=True)
    await show(c, q, product_text(p), product_kb(p), photo=p.get("photo"))


@Client.on_callback_query(filters.regex(r"^buy:"))
async def buy_cb(c, q):
    parts = q.data.split(":")
    p = await _live_product(parts[1])
    plan_id = parts[2] if len(parts) > 2 else "0"
    plan = next((x for x in get_plans(p) if x["id"] == plan_id), None) if p else None
    if not p or not plan:
        return await q.answer("❌ Ye product/plan available nahi hai.", show_alert=True)
    await q.answer()
    await db.cancel_pending(q.from_user.id)
    o = await db.create_order(q.from_user.id, p, plan)
    amt = money(o["amount"])
    qr = make_qr(upi_link(o["amount"], o["_id"]))
    validity = (f"⏳ <b>Validity:</b> {plan['days']} din\n"
                if (plan["days"] and p.get("chat_id")) else "")
    text = (
        "💳 <b>Payment Details</b>\n\n"
        f"📦 <b>Product:</b> {order_title(o)}\n"
        f"{validity}"
        f"💰 <b>Amount:</b> ₹{amt}\n"
        f"🧾 <b>Order ID:</b> <code>{o['_id']}</code>\n"
        f"🏦 <b>UPI ID:</b> <code>{esc(config.UPI_ID)}</code>\n"
        f"⏱ <b>Valid:</b> {config.ORDER_EXPIRY_MIN} min\n\n"
        f"1️⃣ QR scan karke exact <b>₹{amt}</b> pay karo\n"
        "2️⃣ Payment ke baad <b>I've Paid</b> dabao aur 12 digit UTR bhejo"
    )
    markup = kb(
        [btn("✅ I've Paid – Send UTR", f"paid:{o['_id']}", color="paid")],
        [btn("❌ Cancel Order", f"cx:{o['_id']}", color="danger")],
    )
    await show(c, q, text, markup, photo=qr)


@Client.on_callback_query(filters.regex(r"^paid:"))
async def paid_cb(c, q):
    o = await db.get_order(q.data[5:])
    if not o or o["user_id"] != q.from_user.id or db.status(o) != "pending":
        return await q.answer("⚠️ Ye order active nahi hai. Naya order banao.", show_alert=True)
    await q.answer()
    await c.send_message(
        q.from_user.id,
        "✍️ Ab apna <b>12 digit UTR</b> number bhejo.",
        reply_markup=ForceReply(placeholder="12 digit UTR"),
    )


@Client.on_callback_query(filters.regex(r"^cx:"))
async def cancel_cb(c, q):
    await db.cancel_order(q.data[3:], q.from_user.id)
    await q.answer("❌ Order cancel ho gaya.")
    text, markup, photo = await home_view(q.from_user.id, q.from_user.first_name)
    await show(c, q, text, markup, photo=photo)


@Client.on_callback_query(filters.regex(r"^orders$"))
async def orders_cb(c, q):
    orders = await db.user_orders(q.from_user.id, 10)
    if not orders:
        text = "🧾 <b>My Orders</b>\n\nAbhi tak koi order nahi."
    else:
        lines = []
        for o in orders:
            s = db.status(o)
            lines.append(
                f"{db.ICON[s]} <b>{order_title(o)}</b> · ₹{money(o['amount'])} · {s.title()}\n"
                f"     <code>{o['_id']}</code>"
            )
        text = "🧾 <b>My Orders</b>\n\n" + "\n\n".join(lines)
    paid = [btn(f"📥 {o['product_name'][:18]}", f"get:{o['_id']}", color="plan")
            for o in orders if o["status"] == "paid"]
    rows = [paid[i:i + 2] for i in range(0, len(paid), 2)]
    rows.append([btn("🏠 Home", "home", color="home")])
    await show(c, q, text, kb(*rows))


@Client.on_callback_query(filters.regex(r"^get:"))
async def get_cb(c, q):
    o = await db.get_order(q.data[4:])
    if not o or o["user_id"] != q.from_user.id or o["status"] != "paid":
        return await q.answer("❌ Ye order paid nahi hai.", show_alert=True)
    await q.answer("📥 Bhej raha hu...")
    await deliver(c, q.from_user.id, await db.get_product(o["product_id"]), again=True, order=o)
