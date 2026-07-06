"""
QR Scanner & Generator Telegram Bot
------------------------------------
- Send a photo containing a QR code -> bot decodes and replies with the content
- /gen <text> -> bot generates a QR code image for that text
- /start, /help -> usage info

Uses OpenCV's built-in QRCodeDetector (no external zbar dependency,
so it works cleanly on Termux/Android).
"""

import io
import logging
import os

import cv2
import numpy as np
import qrcode
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

detector = cv2.QRCodeDetector()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 QR Scanner Bot\n\n"
        "📷 Send me a photo with a QR code and I'll decode it.\n"
        "🧩 Use /gen <text or URL> to create a QR code image.\n"
        "❓ /help for more info."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n"
        "/gen <text> - generate a QR code image\n"
        "Just send a photo - I'll try to decode any QR code in it\n\n"
        "Tips for scanning:\n"
        "• Make sure the QR code is in focus and well lit\n"
        "• Avoid extreme angles or heavy glare"
    )


def decode_qr(image_bytes: bytes):
    """Decode QR code(s) from raw image bytes using OpenCV. Returns list of strings."""
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    results = []

    # Try multi-detect first (handles multiple QR codes in one image)
    try:
        ok, decoded_info, points, _ = detector.detectAndDecodeMulti(img)
        if ok:
            results = [text for text in decoded_info if text]
    except cv2.error:
        pass

    if results:
        return results

    # Fallback to single QR detection
    data, points, _ = detector.detectAndDecode(img)
    if data:
        results.append(data)

    return results


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    photo = msg.photo[-1]  # highest resolution
    file = await photo.get_file()

    image_bytes = bytes(await file.download_as_bytearray())

    results = decode_qr(image_bytes)

    if not results:
        await msg.reply_text(
            "❌ No QR code detected. Try a clearer, closer, well-lit shot."
        )
        return

    if len(results) == 1:
        await msg.reply_text(f"✅ QR Code content:\n\n{results[0]}")
    else:
        reply = "✅ Found multiple QR codes:\n\n"
        reply += "\n\n".join(f"{i+1}. {r}" for i, r in enumerate(results))
        await msg.reply_text(reply)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle images sent as uncompressed files (Telegram 'file' not 'photo')."""
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Please send an image file.")
        return

    file = await doc.get_file()
    image_bytes = bytes(await file.download_as_bytearray())
    results = decode_qr(image_bytes)

    if not results:
        await update.message.reply_text("❌ No QR code detected in that image.")
        return

    reply = "\n\n".join(results)
    await update.message.reply_text(f"✅ QR Code content:\n\n{reply}")


async def generate_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /gen <text or URL>")
        return

    text = " ".join(context.args)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    await update.message.reply_photo(photo=buf, caption=f"🧩 QR code for:\n{text}")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN not set. Create a .env file (see .env.example) or export it."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("gen", generate_qr))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))

    logger.info("Bot starting (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
