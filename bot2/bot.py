import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT2_TOKEN    = os.getenv("BOT2_TOKEN")
MAIN_BOT_USER = os.getenv("MAIN_BOT_USERNAME")

# ─── 9 Preview image URLs — replace with your actual hosted image URLs ─────────
PREVIEW_IMAGES = [
    "https://graph.org/file/45e1729d6ef218477ae64-7e6e6058d1f08a783a.jpg",
    "https://graph.org/file/1e009a7310a3db57e1ed4-ed75581c29b98ad1ed.jpg",
    "https://graph.org/file/5715466aac5d33468c4eb-2473fdbf345f29285d.jpg",
    "https://graph.org/file/7c76ae073359af3466e81-7b6086159359789832.jpg",
    "https://graph.org/file/b6a3b7e05d3e11400ec0a-10ec271268b61bd32f.jpg",
    "https://graph.org/file/2172f6e490ab7242707f3-eaef348e7ceeb13bcb.jpg",
    "https://graph.org/file/c2b48f37dc9a7cdd8beaa-16b39a6f45cda05150.jpg",
    "https://graph.org/file/c25115d393de8f7a83e6f-7b661dda61eaf50c3f.jpg",
    "https://graph.org/file/ff8f5ef62a969c961788d-104b52f2a6bbc738c8.jpg",
]

# Caption only on the last image of the album (albums support one caption)
ALBUM_CAPTION = (
    "🔥 <b>This is what's waiting inside!</b>\n\n"
    "✅ Exclusive Videos\n"
    "✅ 10000+ content already uploaded\n"
    "👇 Tap below to get access:"
)

AUTO_DELETE_SECONDS = 15 * 60  # 15 minutes

def buy_now_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🚀 Buy Now — Get Instant Access!",
            url=f"https://t.me/{(MAIN_BOT_USER or 'YourBot').lstrip('@')}"
        )
    ]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user      = update.effective_user
    chat_id   = update.effective_chat.id
    sent_msgs = []

    # Intro message
    intro = await update.message.reply_text(
        f"👀 <b>Here's a sneak peek, {user.first_name}!</b>\n\n"
        "This is what our members get every day 👇\n\n"
        "<i>⚠️ These previews auto-disappear in 15 minutes.</i>",
        parse_mode="HTML",
        protect_content=True   # disables forward + download button
    )
    sent_msgs.append((chat_id, intro.message_id))

    # Build media group — caption only on last image
    media = []
    for i, url in enumerate(PREVIEW_IMAGES):
        is_last = (i == len(PREVIEW_IMAGES) - 1)
        media.append(InputMediaPhoto(
            media=url,
            caption=ALBUM_CAPTION if is_last else None,
            parse_mode="HTML" if is_last else None,
        ))

    # Send as album (max 10 per group — our 9 fits perfectly)
    try:
        album_msgs = await context.bot.send_media_group(
            chat_id=chat_id,
            media=media,
            protect_content=True,   # disables forward + download on every image
        )
        for msg in album_msgs:
            sent_msgs.append((chat_id, msg.message_id))
    except Exception as e:
        logger.error(f"Album send error: {e}")
        # Fallback: send individually if album fails
        for i, url in enumerate(PREVIEW_IMAGES):
            is_last = (i == len(PREVIEW_IMAGES) - 1)
            try:
                msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=url,
                    caption=ALBUM_CAPTION if is_last else None,
                    parse_mode="HTML" if is_last else None,
                    protect_content=True,
                )
                sent_msgs.append((chat_id, msg.message_id))
            except Exception as e2:
                logger.error(f"Fallback photo {i} error: {e2}")

    # Buy Now button — sent as separate message after the album
    # (inline buttons can't be attached to media_group messages)
    try:
        buy_msg = await update.message.reply_text(
            "👇 <b>Ready to join?</b>",
            reply_markup=buy_now_kb(),
            parse_mode="HTML",
            protect_content=True,
        )
        sent_msgs.append((chat_id, buy_msg.message_id))
    except Exception as e:
        logger.error(f"Buy Now button error: {e}")

    # Auto-delete everything after 15 minutes
    async def delete_preview():
        await asyncio.sleep(AUTO_DELETE_SECONDS)
        for c_id, m_id in sent_msgs:
            try:
                await context.bot.delete_message(chat_id=c_id, message_id=m_id)
            except Exception as e:
                logger.warning(f"Could not delete msg {m_id}: {e}")

    asyncio.create_task(delete_preview())

def main():
    app = Application.builder().token(BOT2_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("✅ Bot 2 (Preview) started.")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
