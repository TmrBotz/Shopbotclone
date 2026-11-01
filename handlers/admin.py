import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait

import config
import database as db
from utils import access, media
from utils.ui import (COLORS, ROLES, STATE, STYLED, btn, deliver, esc, get_plans, html_of, kb,
                      money, order_title, parse_buttons, parse_plans, product_kb, product_text,
                      send_page, show, to_item)

log = logging.getLogger("admin")

STEPS = ["name", "plans", "desc", "photo", "buttons", "dbuttons", "content", "chat"]
PROMPTS = {
    "name": "📝 Product ka <b>naam</b> bhejo:",
    "plans": ("📅 <b>Plans</b> bhejo — ek line = ek plan:\n<code>Naam | Price | Days</code>\n\n"
              "Jaise:\n<code>1 Month | 99 | 30\n3 Month | 249 | 90</code>\n\n"
              "• Days channel/group access ke liye hai, na likho to bina expiry\n"
              "• Sirf ek price ho to bas number bhejo, jaise <code>499</code>"),
    "desc": ("📄 <b>Description</b> bhejo (max 700 characters).\n"
             "HTML chalega: <code>&lt;b&gt; &lt;i&gt; &lt;u&gt; &lt;code&gt; &lt;blockquote&gt; "
             "&lt;a href=\"...\"&gt;</code>"),
    "photo": "🖼 Product <b>photo</b> bhejo:",
    "buttons": ("🔘 <b>Product page buttons</b> bhejo:\n<code>Demo | https://t.me/xyz</code>\n"
                "Ek line = ek row. Ek row me 2 buttons: <code>A | link &amp;&amp; B | link</code>"),
    "dbuttons": "🔘 <b>Delivery buttons</b> (payment ke baad dikhenge), same format me bhejo:",
    "content": ("📦 <b>Delivery content</b> bhejo — text / photo / video / file / link jo bhi.\n"
                "Multiple messages bhej sakte ho, phir <b>Done</b> dabao."),
    "chat": ("📢 <b>Channel/Group</b> ka ID bhejo (jaise <code>-1001234567890</code>) ya wahan ka koi "
             "message forward karo.\nBot wahan admin ho (<b>Invite Users</b> + <b>Ban Users</b>).\n"
             "Skip = koi channel nahi."),
    "add_admin": ("👤 Naye admin ka <b>User ID</b> bhejo (ya unka message forward karo).\n"
                  "Usne bot <b>/start</b> kiya hona chahiye."),
    "broadcast": "📢 Broadcast ka message bhejo (text / photo / video, kuch bhi):",
    "welcome_text": ("✏️ <b>Welcome text</b> bhejo (HTML allowed).\n"
                     "<code>{name}</code> = user ka naam, <code>{store}</code> = store ka naam.\n"
                     "Photo ke saath max 900 characters."),
    "welcome_photo": "🖼 Welcome ke liye <b>photo</b> bhejo:",
}
EDIT_FIELDS = [("name", "📝 Name"), ("plans", "📅 Plans"), ("desc", "📄 Description"),
               ("photo", "🖼 Photo"), ("buttons", "🔘 Page Buttons"),
               ("dbuttons", "🔘 Delivery Buttons"), ("content", "📦 Delivery Content"),
               ("chat", "📢 Channel")]
MARK = {"SUCCESS": "🟢", "DANGER": "🔴", "PRIMARY": "🔵", "DEFAULT": "⚪", None: "⚪"}

MENU_TEXT = "⚙️ <b>Admin Panel</b>\n\nKya manage karna hai?"


def menu_kb():
    return kb(
        [btn("📦 Products", "a:pl", color="admin"), btn("👥 Admins", "a:al", color="admin")],
        [btn("🧾 Orders", "a:ol:all", color="admin"), btn("📊 Stats", "a:st", color="admin")],
        [btn("✏️ Welcome", "a:wl", color="admin"), btn("🎨 Colors", "a:cl", color="admin")],
        [btn("📢 Broadcast", "a:bc", color="admin")],
        [btn("🏠 Home", "home", color="home")],
    )


async def _is_admin(_, __, u):
    return bool(u.from_user) and await db.is_admin(u.from_user.id)


admin_f = filters.create(_is_admin)
in_state = filters.create(lambda _, __, m: bool(m.from_user) and m.from_user.id in STATE)


# ---------- helpers ----------
def product_view(p):
    status = "🟢 Visible" if p["active"] else "🔴 Hidden"
    plans = get_plans(p)
    prices = [x["price"] for x in plans]
    rng = f"₹{money(min(prices))}" + (f"–₹{money(max(prices))}" if len(set(prices)) > 1 else "")
    chat = f"📢 {esc(p['chat_title'])}" if p.get("chat_id") else "📢 Channel: —"
    text = (product_text(p) + f"\n\n━━━━━━━━━━\n🆔 <code>{p['_id']}</code> · {status}\n"
            f"📅 Plans: {len(plans)} ({rng})\n{chat}\n📦 Delivery items: {len(p.get('content', []))}")
    pid = p["_id"]
    rows = [
        [btn("✏️ Edit", f"a:e:{pid}", color="admin"), btn("🗑 Delete", f"a:d:{pid}", color="danger")],
        [btn("🔴 Hide" if p["active"] else "🟢 Show", f"a:tg:{pid}", color="nav"),
         btn("📦 Test Delivery", f"a:t:{pid}", color="nav")],
    ]
    if p.get("chat_id"):
        rows.append([btn("👥 Subscribers", f"a:sb:{pid}", color="nav")])
    rows.append([btn("⬅️ Back", "a:pl", color="back")])
    return text, kb(*rows), p.get("photo")


def _fields(step, value):
    if step == "chat":
        return value or {"chat_id": None, "chat_title": None}
    if step == "plans":
        return {"plans": value, "price": min(x["price"] for x in value)}
    return {step: value}


async def ask(c, uid, st):
    step = st["step"]
    rows = []
    if step in ("photo", "buttons", "dbuttons", "chat"):
        rows.append([btn("🗑 Remove" if st.get("edit") else "⏭ Skip", "a:skip", color="nav")])
    if step == "content":
        rows.append([btn("✅ Done", "a:done", color="confirm")])
    rows.append([btn("❌ Cancel", "a:cancel", color="danger")])
    prefix = ""
    if step in STEPS and not st.get("edit"):
        prefix = f"<b>Step {STEPS.index(step) + 1}/{len(STEPS)}</b>\n"
    msg = prefix + PROMPTS[step]
    if step == "plans" and st.get("edit"):
        p = await db.get_product(st["edit"])
        cur = "\n".join(f"{x['name'] or 'Default'} | {money(x['price'])} | {x['days']}" for x in get_plans(p))
        msg += f"\n\n<b>Current:</b>\n<code>{esc(cur)}</code>"
    await c.send_message(uid, msg, reply_markup=kb(*rows))


async def start_flow(c, uid, step, edit=None):
    STATE[uid] = {"step": step, "edit": edit, "data": {}, "items": []}
    await ask(c, uid, STATE[uid])


async def begin(c, q, step, edit=None):
    await q.answer()
    try:
        await q.message.delete()
    except Exception:
        pass
    await start_flow(c, q.from_user.id, step, edit=edit)


async def advance(c, uid, st, value):
    step = st["step"]
    if st.get("edit"):  # single field edit
        pid = st["edit"]
        await db.update_product(pid, _fields(step, value))
        STATE.pop(uid, None)
        await c.send_message(uid, "✅ Updated!")
        text, markup, photo = product_view(await db.get_product(pid))
        return await send_page(c, uid, text, markup, photo)

    st["data"].update(_fields(step, value))
    nxt = STEPS.index(step) + 1
    if nxt < len(STEPS):
        st["step"] = STEPS[nxt]
        return await ask(c, uid, st)

    st["step"] = "confirm"
    p = st["data"]
    await send_page(c, uid, product_text(p), product_kb(p, buy=False), p.get("photo"))
    await c.send_message(
        uid,
        "👆 Ye user ko aisa dikhega.\n"
        f"📅 Plans: {len(p['plans'])}\n📢 Channel: {esc(p.get('chat_title') or '—')}\n"
        f"📦 Delivery items: {len(p['content'])}\n\nSave karun?",
        reply_markup=kb([btn("💾 Save Product", "a:save", color="confirm"),
                         btn("❌ Cancel", "a:cancel", color="danger")]),
    )


async def _check_html(c, uid, text):
    try:
        await c.send_message(uid, "👁 <b>Preview:</b>\n\n" + text)
    except Exception as e:
        return str(e)[:150]


# ---------- commands ----------
@Client.on_message(filters.command("admin") & filters.private & admin_f)
async def admin_cmd(c, m):
    STATE.pop(m.from_user.id, None)
    await m.reply_text(MENU_TEXT, reply_markup=menu_kb())


@Client.on_message(filters.command("cancel") & filters.private & admin_f)
async def cancel_cmd(c, m):
    STATE.pop(m.from_user.id, None)
    await m.reply_text("❌ Cancelled.", reply_markup=menu_kb())


@Client.on_message(filters.command(["ban", "unban"]) & filters.private & admin_f)
async def ban_cmd(c, m):
    try:
        uid = int(m.command[1])
    except Exception:
        return await m.reply_text("Use: <code>/ban user_id</code> ya <code>/unban user_id</code>")
    if await db.is_admin(uid):
        return await m.reply_text("⚠️ Admin ko ban nahi kar sakte.")
    ok = await db.set_ban(uid, m.command[0] == "ban")
    await m.reply_text("✅ Done." if ok else "⚠️ User nahi mila.")


# ---------- admin input (step by step) ----------
@Client.on_message(filters.private & in_state & ~filters.command(["start", "admin", "cancel"]))
async def on_input(c, m):
    uid = m.from_user.id
    st = STATE[uid]
    step = st["step"]
    txt = (m.text or "").strip()

    if step == "name":
        if not txt:
            return await m.reply_text("⚠️ Naam text me bhejo.")
        return await advance(c, uid, st, txt[:60])

    if step == "plans":
        try:
            plans = parse_plans(txt)
        except ValueError:
            return await m.reply_text(
                "⚠️ Format galat.\n\nHar line: <code>Naam | Price | Days</code>\n"
                "Jaise: <code>1 Month | 99 | 30</code>\nYa sirf price: <code>499</code> (max 8 plans)")
        return await advance(c, uid, st, plans)

    if step == "desc":
        d = html_of(m)
        if not d or len(d) > 700:
            return await m.reply_text(f"⚠️ Description 1-700 characters ka hona chahiye (abhi {len(d)}).")
        err = await _check_html(c, uid, d)
        if err:
            return await m.reply_text(f"⚠️ HTML galat hai: <code>{esc(err)}</code>\nDobara bhejo.")
        return await advance(c, uid, st, d)

    if step == "photo":
        if not m.photo:
            return await m.reply_text("⚠️ Photo bhejo (as photo, file nahi).")
        return await advance(c, uid, st, await media.save(m, m.photo.file_id))

    if step in ("buttons", "dbuttons"):
        try:
            rows = parse_buttons(txt)
        except ValueError as e:
            return await m.reply_text(
                f"⚠️ Format galat: <code>{esc(str(e))}</code>\n\nSahi: <code>Text | https://link</code>")
        return await advance(c, uid, st, rows)

    if step == "content":
        it = to_item(m)
        if not it:
            return await m.reply_text("⚠️ Ye type support nahi hai.")
        if it.get("file_id"):
            it["file_id"] = await media.save(m, it["file_id"])
        st["items"].append(it)
        return await m.reply_text(
            f"✅ Added ({len(st['items'])}). Aur bhejo ya Done dabao.",
            reply_markup=kb([btn("✅ Done", "a:done", color="confirm"),
                             btn("❌ Cancel", "a:cancel", color="danger")]),
        )

    if step == "chat":
        fc = getattr(m, "forward_from_chat", None) or getattr(getattr(m, "forward_origin", None), "chat", None)
        try:
            cid = fc.id if fc else int(txt)
        except Exception:
            return await m.reply_text(
                "⚠️ Sahi Chat ID bhejo (jaise <code>-1001234567890</code>) ya channel ka message forward karo.")
        try:
            chat = await c.get_chat(cid)
            me = await c.get_chat_member(cid, "me")
        except Exception as e:
            return await m.reply_text(
                f"⚠️ Chat access nahi hua. Bot ko pehle wahan admin banao.\n<code>{esc(str(e)[:120])}</code>")
        priv = getattr(me, "privileges", None)
        if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER) or \
                (priv and not priv.can_invite_users):
            return await m.reply_text("⚠️ Bot is chat me admin nahi hai ya <b>Invite Users</b> permission nahi hai.")
        if priv and not priv.can_restrict_members:
            await m.reply_text("⚠️ <b>Ban Users</b> permission nahi mili, expiry par user remove nahi ho paayega. "
                               "Permission de dena.")
        title = chat.title or str(chat.id)
        await m.reply_text(f"✅ Connected: <b>{esc(title)}</b>")
        return await advance(c, uid, st, {"chat_id": chat.id, "chat_title": title})

    if step == "add_admin":
        fu = getattr(m, "forward_from", None) or getattr(getattr(m, "forward_origin", None), "sender_user", None)
        try:
            nid = fu.id if fu else int(txt)
        except Exception:
            return await m.reply_text("⚠️ Sahi User ID bhejo ya message forward karo.")
        u = await db.get_user(nid)
        if not u:
            return await m.reply_text("⚠️ Is user ne bot start nahi kiya. Pehle /start karwao.")
        await db.add_admin(nid, u.get("name"))
        STATE.pop(uid, None)
        return await m.reply_text(
            f"✅ <b>{esc(u.get('name') or '-')}</b> (<code>{nid}</code>) ab admin hai.",
            reply_markup=kb([btn("👥 Admins", "a:al", color="admin")]),
        )

    if step == "broadcast":
        n = len(await db.user_ids())
        st.update(step="bc_confirm", msg=m.id)
        return await m.reply_text(
            f"📢 Ye message <b>{n}</b> users ko bhejna hai?",
            reply_markup=kb([btn("✅ Send", "a:bcgo", color="confirm"),
                             btn("❌ Cancel", "a:cancel", color="danger")]),
        )

    if step == "welcome_text":
        w = await db.get_setting("welcome") or {}
        d = html_of(m)
        limit = 900 if w.get("photo") else 3500
        if not d or len(d) > limit:
            return await m.reply_text(f"⚠️ Text 1-{limit} characters ka hona chahiye (abhi {len(d)}).")
        err = await _check_html(c, uid, d)
        if err:
            return await m.reply_text(f"⚠️ HTML galat hai: <code>{esc(err)}</code>\nDobara bhejo.")
        w["text"] = d
        await db.set_setting("welcome", w)
        STATE.pop(uid, None)
        return await m.reply_text("✅ Welcome text save ho gaya.",
                                  reply_markup=kb([btn("✏️ Welcome", "a:wl", color="admin")]))

    if step == "welcome_photo":
        if not m.photo:
            return await m.reply_text("⚠️ Photo bhejo (as photo, file nahi).")
        w = await db.get_setting("welcome") or {}
        if len(w.get("text") or "") > 900:
            return await m.reply_text("⚠️ Photo ke saath text max 900 characters ka ho sakta hai. "
                                      "Pehle welcome text chhota karo.")
        w["photo"] = await media.save(m, m.photo.file_id)
        await db.set_setting("welcome", w)
        STATE.pop(uid, None)
        return await m.reply_text("✅ Welcome photo save ho gayi.",
                                  reply_markup=kb([btn("✏️ Welcome", "a:wl", color="admin")]))


# ---------- admin buttons ----------
@Client.on_callback_query(filters.regex(r"^a:") & admin_f)
async def admin_cb(c, q):
    uid = q.from_user.id
    parts = q.data.split(":")
    act = parts[1]
    arg = parts[2] if len(parts) > 2 else None

    if act == "noop":
        return await q.answer("👁 Ye sirf preview hai.")

    if act == "home":
        STATE.pop(uid, None)
        return await show(c, q, MENU_TEXT, menu_kb())

    if act == "cancel":
        STATE.pop(uid, None)
        await q.answer("❌ Cancelled")
        return await show(c, q, MENU_TEXT, menu_kb())

    # ----- products -----
    if act == "pl":
        ps = await db.list_products()
        rows = [[btn(f"{'🟢' if p['active'] else '🔴'} {p['name']} · ₹{money(p['price'])}", f"a:p:{p['_id']}")]
                for p in ps]
        rows += [[btn("➕ Add Product", "a:add", color="confirm")], [btn("⬅️ Back", "a:home", color="back")]]
        return await show(c, q, f"📦 <b>Products</b> ({len(ps)})", kb(*rows))

    if act == "p":
        p = await db.get_product(arg)
        if not p or p.get("deleted"):
            return await q.answer("❌ Product nahi mila.", show_alert=True)
        text, markup, photo = product_view(p)
        return await show(c, q, text, markup, photo=photo)

    if act == "tg":
        p = await db.get_product(arg)
        await db.update_product(arg, {"active": not p["active"]})
        text, markup, photo = product_view(await db.get_product(arg))
        await q.answer("✅ Updated")
        return await show(c, q, text, markup, photo=photo)

    if act == "t":
        p = await db.get_product(arg)
        await q.answer("📦 Bhej diya" + (" (channel link sirf buyers ko milta hai)" if p.get("chat_id") else ""),
                       show_alert=bool(p.get("chat_id")))
        return await deliver(c, uid, p, again=True)

    if act == "d":
        p = await db.get_product(arg)
        return await show(
            c, q, f"🗑 <b>{esc(p['name'])}</b> delete karna hai?\nPurane orders ka record safe rahega.",
            kb([btn("✅ Yes, Delete", f"a:dc:{arg}", color="danger")], [btn("⬅️ No", f"a:p:{arg}", color="back")]))

    if act == "dc":
        await db.update_product(arg, {"deleted": True, "active": False})
        await q.answer("🗑 Deleted")
        q.data = "a:pl"
        return await admin_cb(c, q)

    if act == "e":
        fields = [btn(label, f"a:ef:{arg}:{key}", color="admin") for key, label in EDIT_FIELDS]
        rows = [fields[i:i + 2] for i in range(0, len(fields), 2)] + [[btn("⬅️ Back", f"a:p:{arg}", color="back")]]
        return await show(c, q, "✏️ <b>Edit</b> — kya badalna hai?", kb(*rows))

    if act == "ef":
        return await begin(c, q, parts[3], edit=arg)

    if act == "add":
        return await begin(c, q, "name")

    if act == "skip":
        st = STATE.get(uid)
        if not st:
            return await q.answer("Session khatam, /admin se dobara shuru karo.", show_alert=True)
        await q.answer()
        return await advance(c, uid, st, None if st["step"] in ("photo", "chat") else [])

    if act == "done":
        st = STATE.get(uid)
        if not st or st["step"] != "content":
            return await q.answer("Session khatam, /admin se dobara shuru karo.", show_alert=True)
        if not st["items"]:
            return await q.answer("⚠️ Kam se kam 1 item bhejo.", show_alert=True)
        await q.answer()
        return await advance(c, uid, st, st["items"])

    if act == "save":
        st = STATE.get(uid)
        if not st or st["step"] != "confirm":
            return await q.answer("Session khatam, /admin se dobara shuru karo.", show_alert=True)
        STATE.pop(uid, None)
        pid = await db.add_product(st["data"])
        await q.answer("✅ Saved!")
        return await q.message.edit_text(
            "✅ <b>Product saved!</b>",
            reply_markup=kb([btn("📦 Open Product", f"a:p:{pid}", color="admin")],
                            [btn("➕ Add Another", "a:add", color="confirm")]))

    # ----- subscribers -----
    if act == "sb":
        p = await db.get_product(arg)
        subs = await db.active_subs(arg)
        lines, rows = [], []
        for s in subs:
            who = str(s.get("user_name") or s["user_id"])
            exp = db.fmt_date(s["expires_at"]) if s.get("expires_at") else "Lifetime"
            lines.append(f"• {esc(who)} · <code>{s['user_id']}</code> · {exp}")
            rows.append([btn(f"🗑 {who[:20]} · {exp}", f"a:sr:{s['_id']}", color="danger")])
        text = (f"👥 <b>Subscribers</b> — {esc(p['name'])} ({len(subs)} active)\n\n"
                + ("\n".join(lines) or "Abhi koi active subscriber nahi."))
        rows.append([btn("⬅️ Back", f"a:p:{arg}", color="back")])
        return await show(c, q, text, kb(*rows))

    if act == "sr":
        s = await db.get_sub(arg)
        if not s:
            return await q.answer("❌ Nahi mila.", show_alert=True)
        return await show(
            c, q, f"🗑 <b>{esc(str(s.get('user_name') or s['user_id']))}</b> ko channel se hatana hai?",
            kb([btn("✅ Yes, Remove", f"a:src:{arg}", color="danger")],
               [btn("⬅️ No", f"a:sb:{s['product_id']}", color="back")]))

    if act == "src":
        s = await db.get_sub(arg)
        if not s:
            return await q.answer("❌ Nahi mila.", show_alert=True)
        try:
            await access.remove_sub(c, s, by_admin=True)
        except Exception as e:
            return await q.answer(f"❌ Remove nahi hua: {str(e)[:150]}", show_alert=True)
        await q.answer("✅ Removed")
        q.data = f"a:sb:{s['product_id']}"
        return await admin_cb(c, q)

    # ----- button colors -----
    if act == "cl":
        rows = [[btn(f"{label} {MARK[COLORS.get(role, default)]}", f"a:cr:{role}")]
                for role, (label, default) in ROLES.items()]
        rows += [[btn("♻️ Reset All", "a:crs", color="danger")], [btn("⬅️ Back", "a:home", color="back")]]
        warn = "" if STYLED else "\n\n⚠️ Ye Kurigram version colored buttons support nahi karta. <code>pip install -U kurigram</code>"
        return await show(c, q, "🎨 <b>Button Colors</b>\n\nGroup chuno, phir color:" + warn, kb(*rows))

    if act == "cr":
        label, default = ROLES[arg]
        cur = COLORS.get(arg, default)
        rows = [
            [btn("🟢 Green", f"a:cs:{arg}:SUCCESS", color="SUCCESS"),
             btn("🔴 Red", f"a:cs:{arg}:DANGER", color="DANGER"),
             btn("🔵 Blue", f"a:cs:{arg}:PRIMARY", color="PRIMARY")],
            [btn("⚪ Default", f"a:cs:{arg}:DEFAULT")],
            [btn("⬅️ Back", "a:cl", color="back")],
        ]
        return await show(c, q, f"🎨 <b>{label}</b>\n\nAbhi: {MARK[cur]}\nNaya color chuno 👇", kb(*rows))

    if act == "cs":
        role, val = arg, parts[3]
        if role not in ROLES or val not in ("SUCCESS", "DANGER", "PRIMARY", "DEFAULT"):
            return await q.answer("❌ Galat option.", show_alert=True)
        COLORS[role] = val
        await db.set_setting("colors", dict(COLORS))
        await q.answer("✅ Saved")
        q.data = f"a:cr:{role}"
        return await admin_cb(c, q)

    if act == "crs":
        COLORS.clear()
        await db.set_setting("colors", {})
        await q.answer("♻️ Reset ho gaya")
        q.data = "a:cl"
        return await admin_cb(c, q)

    # ----- welcome message -----
    if act == "wl":
        w = await db.get_setting("welcome") or {}
        t = f"set ✅ ({len(w['text'])} chars)" if w.get("text") else "default"
        text = (f"✏️ <b>Welcome Message</b>\n\n📝 Text: {t}\n🖼 Photo: {'set ✅' if w.get('photo') else 'nahi'}\n\n"
                "Placeholders: <code>{name}</code> <code>{store}</code>")
        rows = [
            [btn("📝 Set Text", "a:wt", color="confirm"), btn("🖼 Set Photo", "a:wph", color="confirm")],
            [btn("🗑 Remove Photo", "a:wr", color="danger"), btn("♻️ Reset", "a:wx", color="danger")],
            [btn("👁 Preview", "a:wp", color="nav")],
            [btn("⬅️ Back", "a:home", color="back")],
        ]
        return await show(c, q, text, kb(*rows))

    if act == "wt":
        return await begin(c, q, "welcome_text")

    if act == "wph":
        return await begin(c, q, "welcome_photo")

    if act in ("wr", "wx"):
        if act == "wx":
            await db.del_setting("welcome")
        else:
            w = await db.get_setting("welcome") or {}
            w.pop("photo", None)
            await db.set_setting("welcome", w)
        await q.answer("✅ Done")
        q.data = "a:wl"
        return await admin_cb(c, q)

    if act == "wp":
        from handlers.user import home_view

        text, markup, photo = await home_view(uid, q.from_user.first_name)
        await q.answer()
        return await send_page(c, uid, text, markup, photo)

    # ----- admins -----
    if act == "al":
        ads = await db.admin_list()
        text = f"👥 <b>Admins</b>\n\n👑 Owner: <code>{config.OWNER_ID}</code>\n" + "\n".join(
            f"• {esc(a.get('name') or '-')} · <code>{a['_id']}</code>" for a in ads)
        rows = [[btn(f"➖ {a.get('name') or a['_id']}", f"a:ar:{a['_id']}", color="danger")] for a in ads]
        rows += [[btn("➕ Add Admin", "a:aa", color="confirm")], [btn("⬅️ Back", "a:home", color="back")]]
        return await show(c, q, text, kb(*rows))

    if act == "aa":
        return await begin(c, q, "add_admin")

    if act == "ar":
        return await show(
            c, q, f"➖ Admin <code>{arg}</code> remove karna hai?",
            kb([btn("✅ Yes, Remove", f"a:arc:{arg}", color="danger")], [btn("⬅️ No", "a:al", color="back")]))

    if act == "arc":
        if int(arg) != config.OWNER_ID:
            await db.remove_admin(int(arg))
        await q.answer("✅ Removed")
        q.data = "a:al"
        return await admin_cb(c, q)

    # ----- orders -----
    if act == "ol":
        orders = await db.list_orders(arg)
        flt = [btn(x.title(), f"a:ol:{x}", color="admin" if x == arg else None) for x in ("all", "paid", "pending")]
        rows = [flt] + [[btn(f"{db.ICON[db.status(o)]} {o['_id']} · ₹{money(o['amount'])}", f"a:o:{o['_id']}:{arg}")]
                        for o in orders] + [[btn("⬅️ Back", "a:home", color="back")]]
        return await show(c, q, f"🧾 <b>Orders</b> — {arg} (latest {len(orders)})", kb(*rows))

    if act == "o":
        o = await db.get_order(arg)
        s = db.status(o)
        text = (f"🧾 <b>Order</b> <code>{o['_id']}</code>\n\n"
                f"👤 <a href=\"tg://user?id={o['user_id']}\">{o['user_id']}</a>\n"
                f"📦 {order_title(o)}\n💰 ₹{money(o['amount'])}\n"
                f"📌 {db.ICON[s]} {s.title()}\n🕐 {db.fmt_time(o['created_at'])}")
        if s == "paid":
            text += (f"\n\n🔢 UTR: <code>{o.get('utr')}</code>\n✅ Paid: {db.fmt_time(o['paid_at'])}\n"
                     f"🏦 {esc(o.get('sender') or '-')}")
        rows = ([[btn("🔄 Resend Product", f"a:or:{o['_id']}", color="confirm")]] if s == "paid" else [])
        rows.append([btn("⬅️ Back", f"a:ol:{parts[3] if len(parts) > 3 else 'all'}", color="back")])
        return await show(c, q, text, kb(*rows))

    if act == "or":
        o = await db.get_order(arg)
        await deliver(c, o["user_id"], await db.get_product(o["product_id"]), again=True, order=o)
        return await q.answer("✅ Resent", show_alert=True)

    # ----- stats -----
    if act == "st":
        s = await db.stats()
        line = lambda t: f"₹{money(t[0])} ({t[1]} orders)"
        text = (f"📊 <b>Stats</b>\n\n👥 Users: <b>{s['users']}</b>\n🧾 Orders: <b>{s['orders']}</b>\n\n"
                f"💰 <b>Revenue</b>\nAaj: {line(s['today'])}\n7 din: {line(s['week'])}\nTotal: {line(s['total'])}")
        return await show(c, q, text, kb([btn("🔄 Refresh", "a:st", color="nav")],
                                         [btn("⬅️ Back", "a:home", color="back")]))

    # ----- broadcast -----
    if act == "bc":
        return await begin(c, q, "broadcast")

    if act == "bcgo":
        st = STATE.pop(uid, None)
        if not st or st["step"] != "bc_confirm":
            return await q.answer("Session khatam.", show_alert=True)
        await q.answer("📢 Bhej raha hu...")
        await q.message.edit_text("📢 Broadcast chal raha hai...")
        asyncio.create_task(_broadcast(c, uid, st["msg"], q.message))


async def _broadcast(c, admin_id, msg_id, status_msg):
    ok = fail = 0
    for u in await db.user_ids():
        for _ in range(2):
            try:
                await c.copy_message(u, admin_id, msg_id)
                ok += 1
                break
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                fail += 1
                break
        else:
            fail += 1
        await asyncio.sleep(0.05)
    await status_msg.edit_text(f"📢 <b>Done</b> ✅\nSent: {ok} | Failed: {fail}",
                               reply_markup=kb([btn("⬅️ Back", "a:home", color="back")]))
