import asyncio
import logging

import aiohttp

import config

log = logging.getLogger("verify")


async def verify_payment(utr, amount, order_id):
    """Returns (http_status, json). Network/timeout par 3 baar retry, status 0 = fail.
    404 par retry nahi hota. API key kabhi log nahi hoti."""
    url = f"{config.VERIFY_API_URL.rstrip('/')}/api/verify"
    body = {
        "utr": utr,
        "amount": int(amount) if float(amount).is_integer() else float(amount),
        "orderId": order_id,
    }
    headers = {"Content-Type": "application/json", "x-api-key": config.VERIFY_API_KEY}

    for attempt in range(1, 4):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                async with s.post(url, json=body, headers=headers) as r:
                    try:
                        data = await r.json(content_type=None)
                    except Exception:
                        data = {}
                    data = data if isinstance(data, dict) else {}
                    log.info("verify order=%s status=%s message=%s", order_id, r.status, data.get("message"))
                    if r.status == 404 and "success" not in data:
                        log.error("API route nahi mila (%s) -> VERIFY_API_URL galat hai", url)
                        return 0, {}
                    return r.status, data
        except (aiohttp.InvalidURL, ValueError) as e:
            log.error("verify request invalid, VERIFY_API_URL / VERIFY_API_KEY check karo: %r", e)
            return 0, {}
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("verify network error (try %s/3): %r", attempt, e)
            if attempt < 3:
                await asyncio.sleep(7)
    return 0, {}
