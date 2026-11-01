import asyncio
import logging
import os

from aiohttp import web
from pyrogram import Client, idle
from pyrogram.enums import ParseMode

import config
import database
from utils import expiry, ui

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("pyrogram").setLevel(logging.WARNING)
log = logging.getLogger("main")


async def _health(_):
    return web.Response(text="ok")


async def main():
    await database.init()
    ui.COLORS.update(await database.get_setting("colors") or {})

    app = Client(
        "shopbot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        plugins=dict(root="handlers"),
        parse_mode=ParseMode.HTML,
        in_memory=True,
    )

    # Dummy web server (Render/Koyeb port scan + uptime ping ke liye)
    web_app = web.Application()
    web_app.router.add_get("/", _health)
    web_app.router.add_get("/health", _health)
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Health server on port %s", port)

    await app.start()
    me = await app.get_me()
    log.info("Bot started as @%s", me.username)
    expiry_task = asyncio.create_task(expiry.loop(app))
    await idle()
    expiry_task.cancel()
    await app.stop()
    if runner:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
