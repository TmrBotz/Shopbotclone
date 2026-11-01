import html
import logging

from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from utils import media

log = logging.getLogger("ui")

STATE = {}  # admin conversation state: {user_id: {...}}

# Colored buttons (green / red / blue). Purani Kurigram me style nahi hota to normal button banenge.
try:
    from pyrogram.enums import ButtonStyle

    InlineKeyboardButton("t", callback_data="t", style=ButtonStyle.PRIMARY)
    STYLED = True
except Exception:  # pragma: no cover
    STYLED = False

# Button groups: role -> (label, default color). Admin bot se color badal sakta hai.
ROLES = {
    "product": ("📦 Product buttons (home)", "PRIMARY"),
    "plan": ("📅 Plan / Buy buttons", "SUCCESS"),
    "paid": ("✅ I've Paid", "SUCCESS"),
    "join": ("🔗 Join channel button", "SUCCESS"),
    "confirm": ("💾 Save / Done / Add", "SUCCESS"),
    "danger": ("❌ Cancel / Delete / Remove", "DANGER"),
    "admin": ("⚙️ Admin menu buttons", "PRIMARY"),
    "home": ("🏠 Home button", "PRIMARY"),
    "nav": ("🧭 My Orders / Support / others", None),
    "back": ("⬅️ Back button", None),
    "link": ("🌐 Custom link buttons", None),
}
COLORS = {}  # admin overrides: {role: "SUCCESS" | "DANGER" | "PRIMARY" | "DEFAULT"}
_RAW = ("SUCCESS", "DANGER", "PRIMARY")

# purane aliases (payment.py me use hote hain)
G, R, P = "confirm", "danger", "home"

esc = html.escape


def _color(role):
    if role in _RAW:
        return role
    c = COLORS.get(role, ROLES.get(role, ("", None))[1])
    return None if c == "DEFAULT" else c


def btn(text, cb=None, url=None, color=None):
    c = _color(color) if color else None
    kw = {"style": getattr(ButtonStyle, c)} if (c and STYLED) else {}
    return InlineKeyboardButton(text, callback_data=cb, url=url, **kw)


def kb(*rows):
    return InlineKeyboardMarkup([list(r) for r in rows if r])


def money(n):
    return str(int(n)) if float(n).is_integer() else f"{float(n):.2f}"


# ---------- plans ----------
def get_plans(p):
    """Purane products (sirf price) ek default plan ban jaate hain."""
    return p.get("plans") or [{"id": "0", "name": "", "price": p["price"], "days": 0}]


def _num(s):
    v = round(float(s.replace("₹", "").replace(",", "").strip()), 2)
    if not v > 0:
        raise ValueError(s)
    return int(v) if v.is_integer() else v


def parse_plans(text):
    """Line = plan: 'Naam | Price | Days'. Sirf number = ek plan. Days na ho to bina expiry."""
    t = text.strip()
    try:
        return [{"id": "0", "name": "", "price": _num(t), "days": 0}]
    except ValueError:
        pass
    plans = []
    for line in t.splitlines():
        if not line.strip():
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) not in (2, 3) or not parts[0]:
            raise ValueError(line)
        days = int(parts[2]) if len(parts) == 3 and parts[2] else 0
        if days < 0:
            raise ValueError(line)
        plans.append({"id": str(len(plans)), "name": parts[0][:40], "price": _num(parts[1]), "days": days})
    if not 1 <= len(plans) <= 8:
        raise ValueError("1-8 plans")
    return plans


def order_title(o):
    t = esc(o["product_name"])
    return f"{t} — {esc(o['plan_name'])}" if o.get("plan_name") else t


# ---------- product views ----------
def url_rows(rows):
    return [[btn(b["text"], url=b["url"], color="link") for b in r] for r in (rows or [])]


def product_text(p):
    plans = get_plans(p)
    text = f"<b>{esc(p['name'])}</b>\n\n{p['desc']}"
    if len(plans) == 1 and not plans[0]["name"]:
        text += f"\n\n💰 <b>Price:</b> ₹{money(plans[0]['price'])}"
    return text


def product_kb(p, buy=True):
    rows = url_rows(p.get("buttons"))
    plans = get_plans(p)
    for pl in plans:
        cb = f"buy:{p['_id']}:{pl['id']}" if buy else "a:noop"
        if len(plans) == 1 and not pl["name"]:
            label = f"💳 Buy Now ₹{money(pl['price'])}"
        else:
            label = f"📅 {pl['name']} — ₹{money(pl['price'])}"
        rows.append([btn(label, cb, color="plan")])
    rows.append([btn("⬅️ Back", "home", color="back")])
    return kb(*rows)


async def send_page(c, chat_id, text, markup, photo=None):
    photo = await media.resolve(c, photo)
    if photo:
        return await c.send_photo(chat_id, photo, caption=text, reply_markup=markup)
    return await c.send_message(chat_id, text, reply_markup=markup)


async def show(c, q, text, markup, photo=None):
    """Ek hi message edit hota hai; text <-> photo switch par delete + resend."""
    m = q.message
    photo = await media.resolve(c, photo)
    try:
        if photo and isinstance(photo, str) and m.photo:
            await m.edit_media(
                InputMediaPhoto(photo, caption=text, parse_mode=ParseMode.HTML), reply_markup=markup
            )
        elif not photo and m.text:
            await m.edit_text(text, reply_markup=markup)
        else:
            await m.delete()
            await send_page(c, m.chat.id, text, markup, photo)
    except MessageNotModified:
        pass


# ---------- content helpers ----------
_FMT = {"BOLD", "ITALIC", "UNDERLINE", "STRIKETHROUGH", "SPOILER", "CODE", "PRE", "BLOCKQUOTE",
        "EXPANDABLE_BLOCKQUOTE", "TEXT_LINK", "TEXT_MENTION", "CUSTOM_EMOJI"}
_TYPES = ("photo", "video", "document", "audio", "voice", "animation", "sticker")


def html_of(m):
    """Raw HTML tags ya Telegram formatting dono chalenge."""
    s = m.text or m.caption
    if not s:
        return ""
    ents = m.entities or m.caption_entities or []
    return s.html if any(e.type.name in _FMT for e in ents) else str(s)


def to_item(m):
    for t in _TYPES:
        obj = getattr(m, t, None)
        if obj:
            return {"type": t, "file_id": obj.file_id, "text": html_of(m)}
    if m.text:
        return {"type": "text", "text": html_of(m)}
    return None


def parse_buttons(text):
    """Line = row. 'Text | link'. Ek row me 2 buttons: 'A | link && B | link'."""
    rows = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        row = []
        for part in line.split("&&"):
            if "|" not in part:
                raise ValueError(line)
            t, u = (x.strip() for x in part.split("|", 1))
            if not t or not u.startswith(("http://", "https://", "tg://")):
                raise ValueError(line)
            row.append({"text": t, "url": u})
        rows.append(row)
    return rows


# ---------- delivery ----------
async def deliver(c, uid, p, again=False, order=None):
    if not p:
        return await c.send_message(uid, "⚠️ Product mil nahi raha, support se contact karo.")
    if not again:
        await c.send_message(uid, "✅ <b>Payment verified!</b>\nYe raha tumhara product 👇")
    for it in p.get("content", []):
        t, f, txt = it["type"], it.get("file_id"), it.get("text") or ""
        try:
            f = await media.resolve(c, f)
            if t == "text":
                await c.send_message(uid, txt)
            elif t == "sticker":
                await c.send_sticker(uid, f)
            else:
                await getattr(c, f"send_{t}")(uid, f, caption=txt)
        except Exception as e:
            log.error("delivery item failed: %s", e)

    rows = url_rows(p.get("dbuttons"))
    extra = ""
    if order and p.get("chat_id"):  # channel/group access (invite link / extend)
        from utils import access

        extra, join_rows = await access.grant(c, uid, p, order, again)
        rows = join_rows + rows
    rows.append([btn("🏠 Home", "home", color="home"), btn("🧾 My Orders", "orders", color="nav")])

    title = order_title(order) if order else esc(p["name"])
    text = f"📦 <b>{title}</b> delivered ✅"
    if extra:
        text += f"\n\n{extra}"
    await c.send_message(uid, text + "\n\nShukriya! 🙏", reply_markup=kb(*rows))
