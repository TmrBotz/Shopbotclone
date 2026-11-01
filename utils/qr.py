import io
from urllib.parse import quote

import qrcode

import config


def upi_link(amount, order_id):
    return (
        f"upi://pay?pa={quote(config.UPI_ID, safe='@')}"
        f"&pn={quote(config.PAYEE_NAME)}"
        f"&am={float(amount):.2f}&cu=INR&tn={quote(order_id)}"
    )


def make_qr(link):
    img = qrcode.make(link, box_size=10, border=3)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    buf.name = "payment_qr.png"
    return buf
