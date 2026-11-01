from pyrogram import Client, filters

import database as db


@Client.on_message(filters.private, group=-1)
async def guard_msg(c, m):
    if m.from_user and await db.is_banned(m.from_user.id):
        await m.reply_text("🚫 Aapko is bot se ban kar diya gaya hai.")
        m.stop_propagation()


@Client.on_callback_query(group=-1)
async def guard_cb(c, q):
    if await db.is_banned(q.from_user.id):
        await q.answer("🚫 Aap banned ho.", show_alert=True)
        q.stop_propagation()
