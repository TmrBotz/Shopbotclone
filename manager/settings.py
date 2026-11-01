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
MANAGER_BOT_TOKEN = _req("MANAGER_BOT_TOKEN")
MONGO_URI = _req("MONGO_URI")
OWNER_ID = int(_req("OWNER_ID"))
STORE_CHANNEL_ID = int(_req("STORE_CHANNEL_ID"))

MANAGER_DB_NAME = os.getenv("MANAGER_DB_NAME", "shopmanager")
CLONE_DB_PREFIX = os.getenv("CLONE_DB_PREFIX", "shopbot_")
MAX_CLONES = int(os.getenv("MAX_CLONES", "3"))
PORT = int(os.getenv("PORT", "8080"))

# Shop bot ka code (main.py wala folder) = manager ka parent folder
SHOP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
