import time
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

import config

db = None
IST = timezone(timedelta(hours=5, minutes=30))
ICON = {"paid": "🟢", "pending": "🟡", "expired": "⚪", "cancelled": "⚪"}


async def init():
    global db
    db = AsyncIOMotorClient(config.MONGO_URI)[config.DB_NAME]
    await db.orders.create_index([("user_id", 1), ("status", 1)])
    await db.orders.create_index("utr", sparse=True)
    await db.subs.create_index("link")
    await db.subs.create_index([("user_id", 1), ("chat_id", 1)])


def fmt_time(ts):
    return datetime.fromtimestamp(ts, IST).strftime("%d %b %Y, %I:%M %p")


# ---------- users ----------
async def add_user(u):
    await db.users.update_one(
        {"_id": u.id},
        {"$set": {"name": u.first_name, "username": u.username},
         "$setOnInsert": {"joined_at": time.time()}},
        upsert=True,
    )


async def get_user(uid):
    return await db.users.find_one({"_id": uid})


async def user_ids():
    return [x["_id"] async for x in db.users.find({}, {"_id": 1})]


async def is_banned(uid):
    d = await db.users.find_one({"_id": uid}, {"banned": 1})
    return bool(d and d.get("banned"))


async def set_ban(uid, value):
    r = await db.users.update_one({"_id": uid}, {"$set": {"banned": value}})
    return r.matched_count > 0


# ---------- admins ----------
async def is_admin(uid):
    return uid == config.OWNER_ID or bool(await db.admins.find_one({"_id": uid}))


async def admin_list():
    return await db.admins.find().to_list(200)


async def admin_ids():
    return [config.OWNER_ID] + [a["_id"] for a in await admin_list()]


async def add_admin(uid, name):
    await db.admins.update_one({"_id": uid}, {"$set": {"name": name}}, upsert=True)


async def remove_admin(uid):
    await db.admins.delete_one({"_id": uid})


# ---------- products ----------
async def add_product(d):
    d.update(_id=uuid.uuid4().hex[:6], active=True, deleted=False, created_at=time.time())
    await db.products.insert_one(d)
    return d["_id"]


async def get_product(pid):
    return await db.products.find_one({"_id": pid})


async def list_products(active_only=False):
    q = {"deleted": {"$ne": True}}
    if active_only:
        q["active"] = True
    return await db.products.find(q).sort("created_at", 1).to_list(100)


async def update_product(pid, fields):
    await db.products.update_one({"_id": pid}, {"$set": fields})


# ---------- orders ----------
def status(o):
    if o["status"] == "pending" and o["created_at"] + config.ORDER_EXPIRY_MIN * 60 < time.time():
        return "expired"
    return o["status"]


async def create_order(uid, p, plan=None):
    plan = plan or {"name": "", "price": p["price"], "days": 0}
    o = {
        "_id": "ORD" + uuid.uuid4().hex[:8].upper(),
        "user_id": uid,
        "product_id": p["_id"],
        "product_name": p["name"],
        "amount": plan["price"],
        "plan_name": plan["name"],
        "plan_days": plan["days"],
        "status": "pending",
        "created_at": time.time(),
    }
    await db.orders.insert_one(o)
    return o


async def get_order(oid):
    return await db.orders.find_one({"_id": oid})


async def pending_order(uid):
    cutoff = time.time() - config.ORDER_EXPIRY_MIN * 60
    await db.orders.update_many(
        {"user_id": uid, "status": "pending", "created_at": {"$lt": cutoff}},
        {"$set": {"status": "expired"}},
    )
    return await db.orders.find_one({"user_id": uid, "status": "pending"}, sort=[("created_at", -1)])


async def cancel_pending(uid):
    await db.orders.update_many({"user_id": uid, "status": "pending"}, {"$set": {"status": "cancelled"}})


async def cancel_order(oid, uid):
    await db.orders.update_one(
        {"_id": oid, "user_id": uid, "status": "pending"}, {"$set": {"status": "cancelled"}}
    )


async def mark_paid(oid, utr, data):
    """Atomic: sirf pending order hi paid hoga, isliye double delivery nahi hoti."""
    r = await db.orders.find_one_and_update(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": "paid", "utr": utr, "paid_at": time.time(),
                  "txn_id": data.get("txnId"), "sender": data.get("senderName")}},
    )
    return r is not None


async def utr_used(utr):
    return bool(await db.orders.find_one({"utr": utr}, {"_id": 1}))


async def user_orders(uid, n=10):
    return await db.orders.find({"user_id": uid}).sort("created_at", -1).to_list(n)


async def list_orders(flt, n=10):
    q = {} if flt == "all" else {"status": flt}
    return await db.orders.find(q).sort("created_at", -1).to_list(n)


# ---------- stats ----------
async def revenue(since=0):
    r = await db.orders.aggregate([
        {"$match": {"status": "paid", "paid_at": {"$gte": since}}},
        {"$group": {"_id": None, "sum": {"$sum": "$amount"}, "n": {"$sum": 1}}},
    ]).to_list(1)
    return (r[0]["sum"], r[0]["n"]) if r else (0, 0)


async def stats():
    day = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return {
        "users": await db.users.count_documents({}),
        "orders": await db.orders.count_documents({}),
        "today": await revenue(day),
        "week": await revenue(day - 6 * 86400),
        "total": await revenue(0),
    }


# ---------- settings (colors, welcome) ----------
async def get_setting(key):
    d = await db.settings.find_one({"_id": key})
    return d.get("value") if d else None


async def set_setting(key, value):
    await db.settings.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)


async def del_setting(key):
    await db.settings.delete_one({"_id": key})


# ---------- subscriptions (channel access) ----------
def fmt_date(ts):
    return datetime.fromtimestamp(ts, IST).strftime("%d %b %Y")


async def create_sub(d):
    d.update(_id=uuid.uuid4().hex[:8], status="pending", created_at=time.time(),
             joined_at=None, expires_at=None, reminded=False)
    await db.subs.insert_one(d)
    return d["_id"]


async def get_sub(sid):
    return await db.subs.find_one({"_id": sid})


async def find_sub(uid, chat_id):
    return await db.subs.find_one({"user_id": uid, "chat_id": chat_id}, sort=[("created_at", -1)])


async def sub_by_link(link):
    return await db.subs.find_one({"link": link})


async def update_sub(sid, fields):
    await db.subs.update_one({"_id": sid}, {"$set": fields})


async def activate_sub(sid, now, exp):
    """Atomic: sirf pending sub active hoga (ek hi baar join)."""
    r = await db.subs.find_one_and_update(
        {"_id": sid, "status": "pending"},
        {"$set": {"status": "active", "joined_at": now, "expires_at": exp, "reminded": False}},
    )
    return r is not None


async def extend_sub(sub, days):
    exp = sub.get("expires_at")
    new = None if (days == 0 or exp is None) else exp + days * 86400
    await db.subs.update_one(
        {"_id": sub["_id"]},
        {"$set": {"expires_at": new, "reminded": False}, "$inc": {"days": days}},
    )
    return new


async def active_subs(pid):
    return await db.subs.find({"product_id": pid, "status": "active"}).sort("expires_at", 1).to_list(30)


async def subs_to_remind(now):
    return await db.subs.find({
        "status": "active", "reminded": {"$ne": True}, "days": {"$gte": 2},
        "expires_at": {"$gt": now, "$lte": now + 86400},
    }).to_list(200)


async def subs_expired(now):
    return await db.subs.find({"status": "active", "expires_at": {"$lte": now}}).to_list(200)
