import logging

import config

log = logging.getLogger("media")

PREFIX = "st:"
_CACHE = {}  # "st:<msg_id>" -> is bot ka file_id
_TYPES = ("photo", "video", "document", "audio", "voice", "animation", "sticker")


def is_ref(v):
    return isinstance(v, str) and v.startswith(PREFIX)


async def save(m, file_id):
    """Media ko store channel me copy karo, DB me 'st:<msg_id>' jayega.
    STORE_CHANNEL_ID na ho ya copy fail ho to purana file_id hi chalta hai."""
    if not config.STORE_CHANNEL_ID:
        return file_id
    try:
        copied = await m.copy(config.STORE_CHANNEL_ID)
        return f"{PREFIX}{copied.id}"
    except Exception as e:
        log.error("store channel copy failed (bot channel me admin hai?): %s", e)
        return file_id


async def resolve(c, v):
    """'st:<msg_id>' -> is bot ka valid file_id. Purane file_id / bytes jaise the waise.
    Fail hone par None (page text-only dikhega, crash nahi)."""
    if not is_ref(v):
        return v
    if v in _CACHE:
        return _CACHE[v]
    try:
        msg = await c.get_messages(config.STORE_CHANNEL_ID, int(v[len(PREFIX):]))
        for t in _TYPES:
            obj = getattr(msg, t, None)
            if obj:
                _CACHE[v] = obj.file_id
                return obj.file_id
        log.error("store message %s me media nahi mili", v)
    except Exception as e:
        log.error("store channel read failed %s: %s", v, e)
    return None
