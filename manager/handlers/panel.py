import time

from pyrogram import Client, filters

from manager import runner, store
from manager import settings as S
from manager.handlers.common import MENU_TEXT, allowed_f, can_manage, menu, owner_f
from manager.ui import STATE, btn, edit, esc, kb


@Client.on_message(filters.command(["start", "cancel"]) & filters.private)
async def start_cmd(c, m):
    uid = m.from_user.id
    STATE.pop(uid, None)
    if not await store.is_allowed(uid):
        return await m.reply_text("🚫 Ye bot sirf authorised users ke liye hai.")
    await m.reply_text(MENU_TEXT, reply_markup=menu(uid))


@Client.on_callback_query(filters.regex(r"^m:home$") & allowed_f)
async def home_cb(c, q):
    STATE.pop(q.from_user.id, None)
    await edit(q, MENU_TEXT, menu(q.from_user.id))


# ---------- list + detail ----------
@Client.on_callback_query(filters.regex(r"^m:list:") & allowed_f)
async def list_cb(c, q):
    uid = q.from_user.id
    scope = q.data.split(":")[2]
    if scope == "all" and uid != S.OWNER_ID:
        return await q.answer("Sirf owner ke liye.", show_alert=True)
    clones = await store.list_clones(created_by=None if scope == "all" else uid)
    total = await store.count_clones()
    rows = [[btn(f"{runner.state(x['_id'])[:1]} @{x['username']}", f"m:b:{x['_id']}")] for x in clones]
    rows.append([btn("⬅️ Back", "m:home")])
    head = "📋 <b>All Bots</b>" if scope == "all" else "🤖 <b>My Bots</b>"
    text = f"{head} ({len(clones)})\nTotal clones: {total}/{S.MAX_CLONES}"
    if not clones:
        text += "\n\nAbhi koi clone nahi."
    await edit(q, text, kb(*rows))


def _detail(c):
    cid = c["_id"]
    text = (
        f"🤖 <b>@{esc(c['username'])}</b>\n{runner.state(cid)}\n\n"
        f"👤 Owner: <code>{c['owner_id']}</code>\n🛍 Store: {esc(c['store_name'])}\n"
        f"🏦 UPI: <code>{esc(c['upi_id'])}</code>\n"
        f"🗄 DB: <code>{esc(c['db_name'])}</code>\n"
        f"📅 Created: {time.strftime('%d %b %Y', time.localtime(c['created_at']))}"
    )
    running = runner.state(cid) != "🔴 Stopped"
    rows = [
        [btn("⏹ Stop", f"m:x:{cid}") if running else btn("▶️ Start", f"m:s:{cid}"),
         btn("🔄 Restart", f"m:r:{cid}")],
        [btn("📜 Logs", f"m:l:{cid}"), btn("🔑 Change Token", f"m:t:{cid}")],
        [btn("🗑 Delete", f"m:d:{cid}")],
        [btn("⬅️ Back", "m:list:me")],
    ]
    return text, kb(*rows)


async def _get(q):
    cid = q.data.split(":")[2]
    c = await store.get_clone(cid)
    if not can_manage(c, q.from_user.id):
        await q.answer("❌ Bot nahi mila.", show_alert=True)
        return None
    return c


@Client.on_callback_query(filters.regex(r"^m:b:") & allowed_f)
async def detail_cb(c, q):
    cl = await _get(q)
    if cl:
        text, markup = _detail(cl)
        await edit(q, text, markup)


@Client.on_callback_query(filters.regex(r"^m:[sxr]:") & allowed_f)
async def control_cb(c, q):
    cl = await _get(q)
    if not cl:
        return
    act = q.data.split(":")[1]
    if act == "s":
        await store.update_clone(cl["_id"], {"enabled": True})
        runner.start(cl["_id"])
        await q.answer("▶️ Start ho raha hai...")
    elif act == "x":
        await store.update_clone(cl["_id"], {"enabled": False})
        await runner.stop(cl["_id"])
        await q.answer("⏹ Stopped")
    else:
        await store.update_clone(cl["_id"], {"enabled": True})
        await runner.restart(cl["_id"])
        await q.answer("🔄 Restart ho raha hai...")
    text, markup = _detail(await store.get_clone(cl["_id"]))
    await edit(q, text, markup)


@Client.on_callback_query(filters.regex(r"^m:l:") & allowed_f)
async def logs_cb(c, q):
    cl = await _get(q)
    if not cl:
        return
    out = runner.tail(cl["_id"]) or "Abhi koi log nahi."
    text = f"📜 <b>Logs</b> @{esc(cl['username'])}\n\n<pre>{esc(out[-3200:])}</pre>"
    await edit(q, text, kb([btn("🔄 Refresh", f"m:l:{cl['_id']}"), btn("⬅️ Back", f"m:b:{cl['_id']}")]))


@Client.on_callback_query(filters.regex(r"^m:t:") & allowed_f)
async def token_cb(c, q):
    cl = await _get(q)
    if not cl:
        return
    await q.answer()
    STATE[q.from_user.id] = {"flow": "token", "step": "token", "data": {}, "cid": cl["_id"]}
    await q.message.delete()
    await c.send_message(
        q.from_user.id,
        f"🔑 @{esc(cl['username'])} ke liye <b>naya bot token</b> bhejo:\n"
        "(Message turant delete ho jayega. Data aur media safe rahenge.)",
        reply_markup=kb([btn("❌ Cancel", "m:cancel")]),
    )


# ---------- delete ----------
@Client.on_callback_query(filters.regex(r"^m:d:") & allowed_f)
async def del_ask_cb(c, q):
    cl = await _get(q)
    if cl:
        await edit(
            q,
            f"🗑 <b>@{esc(cl['username'])}</b> delete karna hai?\n\n"
            "⚠️ Clone ka <b>poora data</b> (products, orders, users, subscriptions) aur "
            "store channel me uski media <b>hamesha ke liye delete</b> ho jayegi.",
            kb([btn("✅ Yes, Delete", f"m:dy:{cl['_id']}")], [btn("⬅️ No", f"m:b:{cl['_id']}")]),
        )


@Client.on_callback_query(filters.regex(r"^m:dy:") & allowed_f)
async def del_go_cb(c, q):
    cl = await _get(q)
    if not cl:
        return
    await q.answer("⏳ Delete ho raha hai...")
    cid = cl["_id"]
    await store.update_clone(cid, {"enabled": False})
    await runner.stop(cid)

    removed, media_ok = 0, True
    try:
        ids = await store.media_refs(cl["db_name"])
        for i in range(0, len(ids), 100):
            await c.delete_messages(S.STORE_CHANNEL_ID, ids[i:i + 100])
            removed += len(ids[i:i + 100])
    except Exception as e:
        media_ok = False
        media_err = str(e)[:120]
    await store.drop_clone_db(cl["db_name"])
    await store.delete_clone(cid)
    runner.LOGS.pop(cid, None)

    text = f"🗑 <b>@{esc(cl['username'])}</b> delete ho gaya.\nDatabase: ✅ deleted\n"
    text += (f"Store media: ✅ {removed} files deleted" if media_ok else
             f"Store media: ⚠️ cleanup fail (<code>{esc(media_err)}</code>). "
             "Manager ko store channel me admin (Delete Messages) banao.")
    await edit(q, text, kb([btn("🏠 Home", "m:home")]))


# ---------- manager admins (owner only) ----------
@Client.on_callback_query(filters.regex(r"^m:al$") & owner_f)
async def admins_cb(c, q):
    admins = await store.admin_list()
    rows = [[btn(f"🗑 {a.get('name') or ''} {a['_id']}", f"m:ar:{a['_id']}")] for a in admins]
    rows += [[btn("➕ Add Admin", "m:aa")], [btn("⬅️ Back", "m:home")]]
    await edit(q, f"👥 <b>Manager Admins</b>\n\n👑 Owner: <code>{S.OWNER_ID}</code>\n"
                  f"Admins: {len(admins)} (tap to remove)", kb(*rows))


@Client.on_callback_query(filters.regex(r"^m:aa$") & owner_f)
async def add_admin_cb(c, q):
    await q.answer()
    STATE[q.from_user.id] = {"flow": "admin", "step": "admin", "data": {}}
    await q.message.delete()
    await c.send_message(q.from_user.id, "👤 Naye admin ka <b>User ID</b> bhejo (ya unka message forward karo):",
                         reply_markup=kb([btn("❌ Cancel", "m:cancel")]))


@Client.on_callback_query(filters.regex(r"^m:ar:") & owner_f)
async def rem_admin_cb(c, q):
    await store.remove_admin(int(q.data.split(":")[2]))
    await q.answer("✅ Removed")
    await admins_cb(c, q)
