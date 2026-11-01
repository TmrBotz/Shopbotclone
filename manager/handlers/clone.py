import re

from pyrogram import Client, filters

from manager import runner, store
from manager import settings as S
from manager.handlers.common import (MENU_TEXT, allowed_f, can_manage, get_me, in_state,
                                     in_store_channel, menu)
from manager.ui import STATE, btn, edit, esc, kb, wipe

TOKEN_RE = re.compile(r"^\d{6,12}:[\w-]{30,}$")
STEPS = ["token", "owner", "upi", "payee", "store", "support", "api_url", "api_key"]
PROMPTS = {
    "token": "🤖 Naye bot ka <b>BotFather token</b> bhejo:\n(Message turant delete ho jayega)",
    "owner": ("👤 Is clone ke <b>Owner ka Telegram User ID</b> bhejo.\n"
              "Wo clone me full admin hoga. Khud ke liye neeche button dabao."),
    "upi": "🏦 Clone ki <b>UPI ID</b> bhejo (jaise <code>name@bank</code>):",
    "payee": "📝 <b>Payee name</b> bhejo (UPI me jo naam dikhta hai):",
    "store": "🛍 <b>Store name</b> bhejo (welcome me dikhega):",
    "support": "☎️ <b>Support username</b> bhejo (jaise <code>@username</code>), ya Skip karo:",
    "api_url": "🌐 Clone ka <b>Verify API URL</b> bhejo (jaise <code>https://myapi.onrender.com</code>):",
    "api_key": "🔑 Clone ka <b>Verify API Key</b> bhejo:\n(Message turant delete ho jayega)",
}


def _ask_markup(step, flow):
    rows = []
    if step == "owner":
        rows.append([btn("👤 Main hi owner hu", "m:me")])
    if step == "support":
        rows.append([btn("⏭ Skip", "m:skip")])
    rows.append([btn("❌ Cancel", "m:cancel")])
    return kb(*rows)


async def ask(c, uid, st):
    step = st["step"]
    prefix = ""
    if st["flow"] == "new":
        prefix = f"<b>Step {STEPS.index(step) + 1}/{len(STEPS)}</b>\n"
    await c.send_message(uid, prefix + PROMPTS[step], reply_markup=_ask_markup(step, st["flow"]))


async def _summary(c, uid, st):
    d = st["data"]
    st["step"] = "confirm"
    await c.send_message(
        uid,
        "📋 <b>Clone details</b>\n\n"
        f"🤖 @{esc(d['username'])}\n👤 Owner: <code>{d['owner_id']}</code>\n"
        f"🏦 UPI: <code>{esc(d['upi_id'])}</code> ({esc(d['payee'])})\n"
        f"🛍 Store: {esc(d['store_name'])}\n"
        f"☎️ Support: {('@' + esc(d['support'])) if d.get('support') else '—'}\n"
        f"🌐 API: {esc(d['api_url'])}\n🔑 Key: ••••{esc(d['api_key'][-4:])}\n\n"
        "Clone bana du?",
        reply_markup=kb([btn("✅ Create Clone", "m:go"), btn("❌ Cancel", "m:cancel")]),
    )


async def _advance(c, uid, st):
    nxt = STEPS.index(st["step"]) + 1
    if nxt < len(STEPS):
        st["step"] = STEPS[nxt]
        return await ask(c, uid, st)
    await _summary(c, uid, st)


async def _check_token(m, token, except_id=None):
    """Valid + naya + manager ka token nahi -> bot info, warna None (reply bhej deta hai)."""
    if token == S.MANAGER_BOT_TOKEN:
        await m.reply_text("⚠️ Ye Manager bot ka hi token hai. Naya bot banao.")
        return None
    if not TOKEN_RE.match(token):
        await m.reply_text("⚠️ Token ka format galat hai. BotFather se wapas copy karo.")
        return None
    me = await get_me(token)
    if not me:
        await m.reply_text("⚠️ Ye token valid nahi hai ya revoke ho chuka hai.")
        return None
    if await store.bot_taken(me["id"], except_id):
        await m.reply_text("⚠️ Ye bot pehle se clone ho chuka hai.")
        return None
    return me


# ---------- text input ----------
@Client.on_message(filters.private & allowed_f & in_state & ~filters.command(["start", "cancel"]))
async def on_input(c, m):
    uid = m.from_user.id
    st = STATE[uid]
    txt = (m.text or "").strip()
    flow, step = st["flow"], st["step"]

    if flow == "admin":
        if uid != S.OWNER_ID:
            return
        fu = getattr(m, "forward_from", None) or getattr(getattr(m, "forward_origin", None), "sender_user", None)
        try:
            nid = fu.id if fu else int(txt)
        except Exception:
            return await m.reply_text("⚠️ Sahi User ID bhejo ya unka message forward karo.")
        await store.add_admin(nid, fu.first_name if fu else "")
        STATE.pop(uid, None)
        return await m.reply_text(f"✅ <code>{nid}</code> ab Manager admin hai.",
                                  reply_markup=kb([btn("👥 Admins", "m:al")]))

    if not txt:
        return await m.reply_text("⚠️ Text me bhejo.")

    if flow == "token":  # token change
        await wipe(m)
        cl = await store.get_clone(st["cid"])
        if not can_manage(cl, uid):
            STATE.pop(uid, None)
            return
        me = await _check_token(m, txt, except_id=cl["_id"])
        if not me:
            return
        STATE.pop(uid, None)
        await store.update_clone(cl["_id"], {"token": txt, "bot_id": me["id"], "username": me["username"]})
        await runner.restart(cl["_id"])
        ok = await in_store_channel(txt, me["id"])
        warn = "" if ok else (f"\n\n⚠️ @{esc(me['username'])} ko <b>Store channel</b> me admin banao "
                              "(Post Messages), warna photos/media nahi dikhengi.")
        return await c.send_message(
            uid,
            f"✅ Token badal gaya, clone @{esc(me['username'])} restart ho gaya.\n"
            "Media safe hai (store channel me hai).\n\n"
            "⚠️ Naye bot ko apne product channels me bhi admin banana padega." + warn,
            reply_markup=kb([btn("🤖 Bot", f"m:b:{cl['_id']}")]),
        )

    d = st["data"]
    if step == "token":
        await wipe(m)
        me = await _check_token(m, txt)
        if not me:
            return
        d.update(token=txt, bot_id=me["id"], username=me["username"])
    elif step == "owner":
        if not txt.lstrip("-").isdigit():
            return await m.reply_text("⚠️ Sirf numeric User ID bhejo.")
        d["owner_id"] = int(txt)
    elif step == "upi":
        if "@" not in txt or " " in txt or len(txt) > 60:
            return await m.reply_text("⚠️ UPI ID sahi bhejo (jaise <code>name@bank</code>).")
        d["upi_id"] = txt
    elif step == "payee":
        d["payee"] = txt[:60]
    elif step == "store":
        d["store_name"] = txt[:60]
    elif step == "support":
        u = txt.lstrip("@")
        if not re.match(r"^[A-Za-z0-9_]{4,32}$", u):
            return await m.reply_text("⚠️ Username sahi bhejo ya Skip karo.")
        d["support"] = u
    elif step == "api_url":
        if len(txt) < 4 or " " in txt:
            return await m.reply_text("⚠️ API URL sahi bhejo.")
        d["api_url"] = txt
    elif step == "api_key":
        await wipe(m)
        d["api_key"] = txt
    await _advance(c, uid, st)


# ---------- buttons ----------
@Client.on_callback_query(filters.regex(r"^m:new$") & allowed_f)
async def new_cb(c, q):
    uid = q.from_user.id
    if await store.count_clones() >= S.MAX_CLONES:
        return await q.answer(f"⚠️ Limit poori: max {S.MAX_CLONES} clones.", show_alert=True)
    await q.answer()
    STATE[uid] = {"flow": "new", "step": "token", "data": {"created_by": uid}}
    await q.message.delete()
    await ask(c, uid, STATE[uid])


@Client.on_callback_query(filters.regex(r"^m:me$") & allowed_f)
async def me_cb(c, q):
    st = STATE.get(q.from_user.id)
    if not st or st["step"] != "owner":
        return await q.answer("Session khatam, /start se shuru karo.", show_alert=True)
    await q.answer()
    st["data"]["owner_id"] = q.from_user.id
    await _advance(c, q.from_user.id, st)


@Client.on_callback_query(filters.regex(r"^m:skip$") & allowed_f)
async def skip_cb(c, q):
    st = STATE.get(q.from_user.id)
    if not st or st["step"] != "support":
        return await q.answer("Session khatam, /start se shuru karo.", show_alert=True)
    await q.answer()
    st["data"]["support"] = ""
    await _advance(c, q.from_user.id, st)


@Client.on_callback_query(filters.regex(r"^m:cancel$") & allowed_f)
async def cancel_cb(c, q):
    STATE.pop(q.from_user.id, None)
    await q.answer("❌ Cancelled")
    await edit(q, MENU_TEXT, menu(q.from_user.id))


@Client.on_callback_query(filters.regex(r"^m:go$") & allowed_f)
async def go_cb(c, q):
    uid = q.from_user.id
    st = STATE.get(uid)
    if not st or st["step"] != "confirm":
        return await q.answer("Session khatam, /start se shuru karo.", show_alert=True)
    d = st["data"]
    if await store.count_clones() >= S.MAX_CLONES:
        return await q.answer(f"⚠️ Limit poori: max {S.MAX_CLONES} clones.", show_alert=True)
    if await store.bot_taken(d["bot_id"]):
        STATE.pop(uid, None)
        return await q.answer("⚠️ Ye bot pehle se clone hai.", show_alert=True)
    if not await in_store_channel(d["token"], d["bot_id"]):
        await q.answer()
        return await edit(
            q,
            f"⚠️ Pehle <b>@{esc(d['username'])}</b> ko <b>Store channel</b> me admin banao "
            "(Post Messages permission ke saath).\nPhir <b>Check Again</b> dabao.",
            kb([btn("🔄 Check Again", "m:go")], [btn("❌ Cancel", "m:cancel")]),
        )
    await q.answer("⏳ Bana raha hu...")
    STATE.pop(uid, None)
    d = await store.add_clone(d)
    runner.start(d["_id"])
    await edit(
        q,
        f"✅ <b>Clone ban gaya!</b>\n\n🤖 @{esc(d['username'])}\n"
        "Bot 10-20 sec me live ho jayega.\n\n"
        "📌 Clone owner ko ye karna hai:\n"
        "1. Bot ko <b>/start</b> kare\n"
        "2. Product channels me bot ko admin banaye (Invite Users + Ban Users)\n"
        "3. <b>/admin</b> se products add kare",
        kb([btn("🤖 Bot", f"m:b:{d['_id']}")], [btn("🏠 Home", "m:home")]),
    )
