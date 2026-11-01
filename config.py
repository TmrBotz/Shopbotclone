import os

from dotenv import load_dotenv

load_dotenv()


def _req(key):
    val = (os.getenv(key) or "").strip().strip("\"'").strip()
    if not val:
        raise SystemExit(f"Missing env variable: {key}")
    return val


API_ID = int(_req("API_ID"))
API_HASH = _req("API_HASH")
BOT_TOKEN = _req("BOT_TOKEN")
MONGO_URI = _req("MONGO_URI")
OWNER_ID = int(_req("OWNER_ID"))
UPI_ID = _req("UPI_ID")
PAYEE_NAME = _req("PAYEE_NAME")
VERIFY_API_URL = _req("VERIFY_API_URL").rstrip("/")
if VERIFY_API_URL.endswith("/api/verify"):  # galti se poora endpoint daal diya ho
    VERIFY_API_URL = VERIFY_API_URL[: -len("/api/verify")]
if not VERIFY_API_URL.startswith(("http://", "https://")):
    VERIFY_API_URL = "https://" + VERIFY_API_URL
VERIFY_API_KEY = _req("VERIFY_API_KEY")

DB_NAME = os.getenv("DB_NAME", "shopbot")
STORE_NAME = os.getenv("STORE_NAME", "My Store")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").lstrip("@")
ORDER_EXPIRY_MIN = int(os.getenv("ORDER_EXPIRY_MIN", "15"))
LINK_VALID_HOURS = int(os.getenv("LINK_VALID_HOURS", "24"))

# Optional: store channel (media yahan save hoti hai, token badalne par MEDIA_EMPTY nahi aata)
STORE_CHANNEL_ID = int((os.getenv("STORE_CHANNEL_ID") or "0").strip().strip("\"'").strip() or 0)
