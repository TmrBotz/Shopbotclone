import time
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

from manager import settings as S

client = None
db = None


async def init():
    global client, db
    client = AsyncIOMotorClient(S.MONGO_URI)
    db = client[S.MANAGER_DB_NAME]


# ---------- admins ----------
async def is_allowed(uid):
    return uid == S.OWNER_ID or bool(await db.admins.find_one({"_id": uid}))


async def admin_list():
    return await db.admins.find().to_list(200)


async def add_admin(uid, name=""):
    await db.admins.update_one({"_id": uid}, {"$set": {"name": name}}, upsert=True)


async def remove_admin(uid):
    await db.admins.delete_one({"_id": uid})


# ---------- clones ----------
async def add_clone(d):
    cid = uuid.uuid4().hex[:8]
    d.update(_id=cid, db_name=f"{S.CLONE_DB_PREFIX}{cid}", enabled=True, created_at=time.time())
    await db.clones.insert_one(d)
    return d


async def get_clone(cid):
    return await db.clones.find_one({"_id": cid})


async def list_clones(created_by=None, enabled=None):
    q = {}
    if created_by is not None:
        q["created_by"] = created_by
    if enabled is not None:
        q["enabled"] = enabled
    return await db.clones.find(q).sort("created_at", 1).to_list(200)


async def count_clones():
    return await db.clones.count_documents({})


async def bot_taken(bot_id, except_id=None):
    q = {"bot_id": bot_id}
    if except_id:
        q["_id"] = {"$ne": except_id}
    return bool(await db.clones.find_one(q, {"_id": 1}))


async def update_clone(cid, fields):
    await db.clones.update_one({"_id": cid}, {"$set": fields})


async def delete_clone(cid):
    await db.clones.delete_one({"_id": cid})


async def drop_clone_db(db_name):
    await client.drop_database(db_name)


async def media_refs(db_name):
    """Clone ki DB me jitne store-channel message ids hain (products + welcome)."""
    d = client[db_name]
    ids = set()

    def add(v):
        if isinstance(v, str) and v.startswith("st:"):
            try:
                ids.add(int(v[3:]))
            except ValueError:
                pass

    async for p in d.products.find({}, {"photo": 1, "content": 1}):
        add(p.get("photo"))
        for it in p.get("content") or []:
            add(it.get("file_id"))
    w = await d.settings.find_one({"_id": "welcome"})
    add(((w or {}).get("value") or {}).get("photo"))
    return sorted(ids)
