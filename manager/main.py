import asyncio
import logging

from aiohttp import web
from pyrogram import Client, idle
from pyrogram.enums import ParseMode

from manager import runner, store
from manager import settings as S

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("pyrogram").setLevel(logging.WARNING)
log = logging.getLogger("manager")


async def _health(_):
    return web.Response(text="ok")


async def main():
    await store.init()

    app = Client(
        "manager",
        api_id=S.API_ID,
        api_hash=S.API_HASH,
        bot_token=S.MANAGER_BOT_TOKEN,
        plugins=dict(root="manager.handlers"),
        parse_mode=ParseMode.HTML,
        in_memory=True,
    )

    web_app = web.Application()
    web_app.router.add_get("/", _health)
    web_app.router.add_get("/health", _health)
    web_runner = web.AppRunner(web_app)
    await web_runner.setup()
    await web.TCPSite(web_runner, "0.0.0.0", S.PORT).start()

    await app.start()
    me = await app.get_me()
    log.info("Manager started as @%s", me.username)
    try:  # manager ko store channel me delete permission chahiye (clone delete par media cleanup)
        await app.get_chat_member(S.STORE_CHANNEL_ID, "me")
    except Exception as e:
        log.warning("Manager store channel me nahi hai (media cleanup nahi hoga): %s", e)

    starter = asyncio.create_task(runner.start_all())
    await idle()
    starter.cancel()
    await runner.stop_all()
    await app.stop()
    await web_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
