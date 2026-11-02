"""Har clone = shop bot ka ek alag process (main.py, bina kisi change ke)."""
import asyncio
import collections
import logging
import os
import sys
import time

from manager import settings as S
from manager import store

log = logging.getLogger("runner")

PROCS = {}   # clone_id -> asyncio subprocess
TASKS = {}   # clone_id -> supervisor task
LOGS = {}    # clone_id -> last output lines


def build_env(c):
    env = os.environ.copy()
    env.pop("MANAGER_BOT_TOKEN", None)
    env.update({
        "API_ID": str(S.API_ID),
        "API_HASH": S.API_HASH,
        "BOT_TOKEN": c["token"],
        "MONGO_URI": S.MONGO_URI,
        "OWNER_ID": str(c["owner_id"]),
        "UPI_ID": c["upi_id"],
        "PAYEE_NAME": c["payee"],
        "VERIFY_API_URL": c["api_url"],
        "VERIFY_API_KEY": c["api_key"],
        "DB_NAME": c["db_name"],
        "STORE_NAME": c["store_name"],
        "SUPPORT_USERNAME": c.get("support") or "",
        "STORE_CHANNEL_ID": str(S.STORE_CHANNEL_ID),
        "PORT": "0",  # health server ke liye random free port (conflict nahi hoga)
        "PYTHONUNBUFFERED": "1",
    })
    return env


async def _pump(cid, proc):
    buf = LOGS.setdefault(cid, collections.deque(maxlen=40))
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        buf.append(line.decode(errors="replace").rstrip())


async def _supervise(cid):
    delay = 5
    while True:
        c = await store.get_clone(cid)
        if not c or not c.get("enabled"):
            return
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "main.py", cwd=S.SHOP_DIR, env=build_env(c),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, limit=2 ** 20,
        )
        PROCS[cid] = proc
        started = time.time()
        log.info("clone %s (@%s) started pid=%s", cid, c.get("username"), proc.pid)
        pump = asyncio.create_task(_pump(cid, proc))
        try:
            rc = await proc.wait()
        finally:
            pump.cancel()
            PROCS.pop(cid, None)
        log.warning("clone %s exited code=%s", cid, rc)
        delay = 5 if time.time() - started > 120 else min(delay * 2, 300)
        await asyncio.sleep(delay)


def start(cid):
    t = TASKS.get(cid)
    if t and not t.done():
        return
    TASKS[cid] = asyncio.create_task(_supervise(cid))


async def _kill(p):
    if p and p.returncode is None:
        p.terminate()
        try:
            await asyncio.wait_for(p.wait(), 10)
        except asyncio.TimeoutError:
            p.kill()
            await p.wait()


async def stop(cid):
    p = PROCS.get(cid)  # task cancel hone se pehle pakdo (finally me PROCS se hat jata hai)
    t = TASKS.pop(cid, None)
    if t:
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
    PROCS.pop(cid, None)
    await _kill(p)


async def restart(cid):
    await stop(cid)
    start(cid)


def state(cid):
    p = PROCS.get(cid)
    if p and p.returncode is None:
        return "🟢 Running"
    t = TASKS.get(cid)
    return "🟡 Restarting" if t and not t.done() else "🔴 Stopped"


def tail(cid, n=25):
    return "\n".join(list(LOGS.get(cid, []))[-n:])


async def start_all():
    for c in await store.list_clones(enabled=True):
        start(c["_id"])
        await asyncio.sleep(3)  # ek saath load na pade


async def stop_all():
    for cid in list(TASKS):
        await stop(cid)
