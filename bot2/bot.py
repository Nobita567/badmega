import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT2_TOKEN    = os.getenv("BOT2_TOKEN")
MAIN_BOT_USER = os.getenv("MAIN_BOT_USERNAME")

# ─── Preview image URLs — replace with your actual hosted image URLs ───────────
PREVIEW_IMAGES = [
    "https://your-image-host.com/preview1.jpg",
    "https://your-image-host.com/preview2.jpg",
    "https://your-image-host.com/preview3.jpg",
    "https://your-image-host.com/preview4.jpg",
]

PREVIEW_CAPTIONS = [
    "🔥 Exclusive Strategy #1 — Members-only alpha signals",
    "📊 Real-time market breakdowns every single day",
    "💡 Step-by-step tutorials from top experts",
    "🎯 Live calls & alerts — never miss a move",
]

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
    sent_msgs = []

    intro = await update.message.reply_text(
        f"👀 <b>Here's a sneak peek, {user.first_name}!</b>\n\n"
        "This is what our members get every day 👇\n\n"
        "<i>⚠️ These previews auto-disappear in 15 minutes.</i>",
        parse_mode="HTML"
    )
    sent_msgs.append((update.effective_chat.id, intro.message_id))

    for i, (img_url, caption) in enumerate(zip(PREVIEW_IMAGES, PREVIEW_CAPTIONS)):
        is_last  = (i == len(PREVIEW_IMAGES) - 1)
        keyboard = buy_now_kb() if is_last else None
        try:
            msg = await update.message.reply_photo(
                photo=img_url,
                caption=f"✨ <b>{caption}</b>",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            sent_msgs.append((update.effective_chat.id, msg.message_id))
        except Exception as e:
            logger.error(f"Preview image {i} error: {e}")
            # fallback text
            try:
                msg = await update.message.reply_text(
                    f"✨ <b>{caption}</b>",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                sent_msgs.append((update.effective_chat.id, msg.message_id))
            except:
                pass

    # Auto-delete all preview messages after 15 min
    async def delete_preview():
        await asyncio.sleep(AUTO_DELETE_SECONDS)
        for chat_id, message_id in sent_msgs:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Could not delete preview msg {message_id}: {e}")

    asyncio.create_task(delete_preview())

def main():
    app = Application.builder().token(BOT2_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("✅ Bot 2 (Preview) started.")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
