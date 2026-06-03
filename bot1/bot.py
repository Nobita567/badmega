import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.error import TelegramError
from supabase import create_client, Client

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT1_TOKEN")
ADMIN_ID    = int(os.getenv("ADMIN_ID"))
CHANNEL_IDS = [int(x.strip()) for x in os.getenv("CHANNEL_IDS", "").split(",") if x.strip()]
PREVIEW_BOT = os.getenv("PREVIEW_BOT_USERNAME")
SUPA_URL    = os.getenv("SUPABASE_URL")
SUPA_KEY    = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPA_URL, SUPA_KEY)

# ─── PLANS — dual INR/USD pricing ─────────────────────────────────────────────
PLANS = {
    "7days":    {"label": "⚡ 7-Day Access",    "price": "$8 / ₹499",  "days": 7},
    "1month":   {"label": "🔥 1-Month Access",  "price": "$10 / ₹699", "days": 30},
    "lifetime": {"label": "👑 Lifetime Access", "price": "$12 / ₹899", "days": None},
}

# ─── PAYMENT METHODS ──────────────────────────────────────────────────────────
PAYMENT_METHODS = {
    "qr": {
        "label": "📷 QR Code",
        "text": (
            "🧾 <b>QR Code Payment</b>\n\n"
            "Scan the QR code above to complete your payment.\n\n"
            "📸 <b>Once paid:</b> send your payment screenshot right here.\n\n"
            "⏳ <i>Window closes in 15 minutes.</i>"
        ),
        "image": "https://i.ibb.co/bMP4nQ7S/ee15c8361b23.jpg",
        "extra_buttons": [],
    },
    "paytm": {
        "label": "💸 Paytm / UPI",
        "text": (
            "💸 <b>Paytm / UPI Payment</b>\n\n"
            "Send payment to the UPI ID below:\n\n"
            "🔑 UPI ID: <code>womp@ptyes</code>\n\n"
            "📸 <b>Once paid:</b> send your payment screenshot right here.\n\n"
            "⏳ <i>Window closes in 15 minutes.</i>"
        ),
        "image": "https://i.ibb.co/Gf4dxt28/bdb68f4ab32e.jpg",
        "extra_buttons": [],
    },
    "paypal": {
        "label": "🌐 PayPal",
        "text": (
            "🌐 <b>PayPal Payment</b>\n\n"
            "Send payment to:\n\n"
            "📧 <code>Ankitmallick5790@gmail.com</code>\n\n"
            "📸 <b>Once paid:</b> send your payment screenshot right here.\n\n"
            "⏳ <i>Window closes in 15 minutes.</i>"
        ),
        "image": "https://i.ibb.co/gLPBppVv/1d77334f059d.jpg",
        "extra_buttons": [],
    },
    "crypto": {
        "label": "🪙 Crypto (USDT)",
        "text": (
            "🪙 <b>Crypto Payment — USDT (BEP20)</b>\n\n"
            "Send USDT to:\n\n"
            "👛 <code>0x1da04f30bdc147612a625b203217f50cdb84e2f6</code>\n\n"
            "⚠️ <i>Send on BEP20 network only!</i>\n\n"
            "📸 <b>Once paid:</b> send your payment screenshot right here.\n\n"
            "⏳ <i>Window closes in 15 minutes.</i>"
        ),
        "image": "https://graph.org/file/60cf45bb50cf108f47196-28db3241840c7bc2db.jpg",
        "extra_buttons": [],
    },
    "others": {
        "label": "💳 Other Methods",
        "text": (
            "💳 <b>Other Payment Methods</b>\n\n"
            "Message the admin directly for other payment methods.\n\n"
        ),
        "image": "https://i.ibb.co/Sw8CMtvz/b856f157559b.jpg",
        "extra_buttons": [
            [InlineKeyboardButton(text="👤 Message Admin", url="https://t.me/ProSeller_69")]
        ],
    },
}

PAYMENT_MAIN_IMAGE = "https://graph.org/file/bda4c8741cef3354d467f-2d3c7faabd36813f12.jpg"
DONATE_IMAGE       = "https://graph.org/file/d0108817594a1b51532a4-396122f7b54970bd86.jpg"
DONATE_METHODS     = PAYMENT_METHODS

RATING            = "4.9★"
BASE_MEMBER_COUNT = 200

# ─── SUPABASE HELPERS ─────────────────────────────────────────────────────────
def now_utc():
    return datetime.now(timezone.utc)

def db_get_user(user_id: int):
    r = supabase.table("subscribers").select("*").eq("user_id", user_id).execute()
    return r.data[0] if r.data else None

def db_upsert_user(user_id: int, data: dict):
    data["user_id"] = user_id
    supabase.table("subscribers").upsert(data, on_conflict="user_id").execute()

def db_delete_user(user_id: int):
    supabase.table("subscribers").delete().eq("user_id", user_id).execute()

def db_get_pending(user_id: int):
    r = supabase.table("pending_payments").select("*").eq("user_id", user_id).execute()
    return r.data[0] if r.data else None

def db_upsert_pending(user_id: int, data: dict):
    data["user_id"] = user_id
    supabase.table("pending_payments").upsert(data, on_conflict="user_id").execute()

def db_delete_pending(user_id: int):
    supabase.table("pending_payments").delete().eq("user_id", user_id).execute()

def db_all_active():
    r = supabase.table("subscribers").select("*").eq("active", True).execute()
    return r.data or []

def db_all_user_ids():
    r = supabase.table("subscribers").select("user_id").execute()
    return [row["user_id"] for row in (r.data or [])]

def db_total_users() -> int:
    r = supabase.table("subscribers").select("user_id", count="exact").execute()
    count = r.count or 0
    return max(count, BASE_MEMBER_COUNT)

def get_expiry(plan_key):
    days = PLANS[plan_key]["days"]
    if days is None:
        return None
    return now_utc() + timedelta(days=days)

# ─── ADMIN STATE ──────────────────────────────────────────────────────────────
admin_state: dict = {}

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def plans_keyboard():
    buttons = []
    for key, plan in PLANS.items():
        buttons.append([InlineKeyboardButton(
            f"{plan['label']} — {plan['price']}", callback_data=f"plan_{key}"
        )])
    # CHANGE 3: Preview Content and Donate on separate rows
    buttons.append([InlineKeyboardButton("🔍 Preview Content", url=f"https://t.me/{PREVIEW_BOT.lstrip('@')}")])
    buttons.append([InlineKeyboardButton("💝 Donate", callback_data="donate")])
    return InlineKeyboardMarkup(buttons)

def payment_methods_keyboard(plan_key):
    buttons = []
    row = []
    for key, method in PAYMENT_METHODS.items():
        row.append(InlineKeyboardButton(method["label"], callback_data=f"pay_{key}_{plan_key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Back to Plans", callback_data="back_plans")])
    return InlineKeyboardMarkup(buttons)

def method_detail_keyboard(plan_key, extra_buttons=None):
    buttons = list(extra_buttons or [])
    buttons.append([InlineKeyboardButton("🔙 Back to Payment Methods", callback_data=f"plan_{plan_key}")])
    return InlineKeyboardMarkup(buttons)

def admin_approval_keyboard(user_id, plan_key):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{plan_key}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{user_id}"),
    ]])

def upsell_keyboard():
    p = PLANS["lifetime"]["price"]
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"👑 Upgrade to Lifetime — {p}", callback_data="plan_lifetime")
    ]])

def renew_keyboard():
    p = PLANS["lifetime"]["price"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Renew Now",          callback_data="back_plans")],
        [InlineKeyboardButton(f"👑 Go Lifetime — {p}", callback_data="plan_lifetime")],
    ])

def donate_keyboard():
    buttons = []
    row = []
    for key, method in PAYMENT_METHODS.items():
        row.append(InlineKeyboardButton(method["label"], callback_data=f"donate_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Back to Plans", callback_data="back_plans")])
    return InlineKeyboardMarkup(buttons)

# ─── WELCOME TEXT ─────────────────────────────────────────────────────────────
def welcome_text(name: str, member_count: int) -> str:
    deadline = (now_utc() + timedelta(hours=24)).strftime("%d %b, %H:%M UTC")
    return (
        f"👋 Welcome, <b>{name}</b>!\n\n"
        f"🔥 Join <b>{member_count:,}+ members</b> already inside — rated <b>{RATING}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🚨 <b>LIMITED TIME OFFER</b>\n"
        f"⏰ Price increases after: <b>{deadline}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📦 <b>Choose a plan to get started:</b>\n"
        "<i>Prices shown in USD & INR</i>"
    )

# ─── SEND HELPERS ─────────────────────────────────────────────────────────────
async def reply_with_image(message, caption: str, keyboard, image_url: str = None, parse_mode="HTML"):
    try:
        if image_url:
            await message.reply_photo(photo=image_url, caption=caption, reply_markup=keyboard, parse_mode=parse_mode)
        else:
            await message.reply_text(caption, reply_markup=keyboard, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"reply_with_image error: {e}")
        try:
            await message.reply_text(caption, reply_markup=keyboard, parse_mode=parse_mode)
        except Exception as e2:
            logger.error(f"Fallback text also failed: {e2}")

# CHANGE 1: edit_or_reply now accepts an optional image_url and uses edit_message_media
# so the photo stays correct after every back button press.
async def edit_or_reply(query, caption: str, keyboard, image_url: str = None, parse_mode="HTML"):
    """
    If image_url is supplied and the current message has a photo, swap the media so
    the correct image is always shown — even after Back button presses.
    Falls back gracefully to caption-only or text edits.
    """
    if image_url:
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=image_url, caption=caption, parse_mode=parse_mode),
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            logger.warning(f"edit_message_media failed, falling back: {e}")

    try:
        await query.edit_message_caption(caption=caption, reply_markup=keyboard, parse_mode=parse_mode)
    except:
        try:
            await query.edit_message_text(caption, reply_markup=keyboard, parse_mode=parse_mode)
        except:
            await query.message.reply_text(caption, reply_markup=keyboard, parse_mode=parse_mode)

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db_get_user(user.id):
        db_upsert_user(user.id, {
            "username":   user.username or "",
            "first_name": user.first_name or "",
            "active":     False,
            "plan":       None,
            "expires_at": None,
            "joined_at":  now_utc().isoformat(),
        })
    member_count = db_total_users()
    await update.message.reply_text(
        welcome_text(user.first_name, member_count),
        reply_markup=plans_keyboard(),
        parse_mode="HTML"
    )

# ─── BUTTON HANDLER ───────────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    # ── Back to plans — keep PAYMENT_MAIN_IMAGE
    if data == "back_plans":
        member_count = db_total_users()
        await edit_or_reply(
            query,
            welcome_text(user.first_name, member_count),
            plans_keyboard(),
            image_url=PAYMENT_MAIN_IMAGE,   # CHANGE 1: restore correct image
        )
        return

    # ── Donate hub — keep DONATE_IMAGE
    if data == "donate":
        text = (
            "💝 <b>Support This Bot</b>\n\n"
            "This bot runs on passion and your generosity.\n"
            "Every donation — big or small — keeps the servers alive,\n"
            "the content fresh, and the community growing. 🙏\n\n"
            "<i>Just pay what feels right.</i>\n\n"
            "👇 Choose your donation method:"
        )
        try:
            await query.message.reply_photo(
                photo=DONATE_IMAGE,
                caption=text,
                reply_markup=donate_keyboard(),
                parse_mode="HTML"
            )
        except:
            await query.message.reply_text(text, reply_markup=donate_keyboard(), parse_mode="HTML")
        return

    # ── Donate method — keep that method's image
    if data.startswith("donate_"):
        method_key = data[7:]
        method = DONATE_METHODS.get(method_key)
        if not method:
            return
        body = method.get("text", method.get("details", ""))
        text = (
            f"💝 <b>{method['label']} — Donate</b>\n\n"
            + body +
            "\n\nThank you for keeping this community alive! 🌟\n"
            "<i>After donating, no action needed — just enjoy!</i>"
        )
        extra_buttons = method.get("extra_buttons", [])
        kb = InlineKeyboardMarkup(
            list(extra_buttons) + [[InlineKeyboardButton("🔙 Back to Donate", callback_data="donate")]]
        )
        try:
            await query.message.reply_photo(photo=method["image"], caption=text, reply_markup=kb, parse_mode="HTML")
        except:
            await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
        return

    # ── Plan selected → payment methods — keep PAYMENT_MAIN_IMAGE
    if data.startswith("plan_"):
        plan_key = data[5:]
        plan = PLANS[plan_key]
        db_upsert_pending(user.id, {
            "plan":     plan_key,
            "method":   None,
            "username": user.username or user.first_name,
        })
        text = (
            f"🎯 You selected: <b>{plan['label']}</b>\n"
            f"💰 Price: <b>{plan['price']}</b>\n\n"
            "💳 <b>Choose your payment method:</b>"
        )
        await edit_or_reply(
            query, text, payment_methods_keyboard(plan_key),
            image_url=PAYMENT_MAIN_IMAGE,   # CHANGE 1: keep the main payment image
        )
        return

    # ── Payment method selected — switch to that method's image
    if data.startswith("pay_"):
        _, method_key, plan_key = data.split("_", 2)
        method  = PAYMENT_METHODS[method_key]
        plan    = PLANS[plan_key]
        pending = db_get_pending(user.id) or {}
        pending["method"] = method_key
        db_upsert_pending(user.id, pending)

        body = method.get("text", method.get("details", ""))
        text = (
            f"📦 Plan: <b>{plan['label']}</b>\n"
            f"💰 Amount: <b>{plan['price']}</b>\n\n"
        ) + body

        kb = method_detail_keyboard(plan_key, method.get("extra_buttons", []))
        # CHANGE 1: edit media in-place to swap to this method's image
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=method["image"], caption=text, parse_mode="HTML"),
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning(f"edit_message_media failed for pay_: {e}")
            try:
                await query.message.reply_photo(photo=method["image"], caption=text, reply_markup=kb, parse_mode="HTML")
            except:
                await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
        return

    # ── Admin: Approve — ask for invite link
    if data.startswith("approve_"):
        if user.id != ADMIN_ID:
            await query.answer("❌ Not authorized.", show_alert=True)
            return
        _, uid, plan_key = data.split("_", 2)
        uid = int(uid)
        admin_state["approving"] = uid
        admin_state["plan_key"]  = plan_key
        await query.message.reply_text(
            f"🔗 <b>Send the invite link for user <code>{uid}</code></b>\n\n"
            f"Plan: <b>{PLANS[plan_key]['label']}</b>\n\n"
            "Paste the unique channel invite link now:",
            parse_mode="HTML"
        )
        try:
            await query.edit_message_caption(caption="⏳ Waiting for invite link from admin...", parse_mode="HTML")
        except:
            pass
        return

    # ── Admin: Reject
    if data.startswith("reject_"):
        if user.id != ADMIN_ID:
            await query.answer("❌ Not authorized.", show_alert=True)
            return
        uid = int(data[7:])
        admin_state["rejecting"] = uid
        await query.message.reply_text(
            f"✏️ <b>Send the rejection reason for user <code>{uid}</code>:</b>",
            parse_mode="HTML"
        )
        try:
            await query.edit_message_caption(caption="⏳ Waiting for rejection reason...", parse_mode="HTML")
        except:
            pass
        return

# ─── SCREENSHOT ───────────────────────────────────────────────────────────────
async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    pending = db_get_pending(user.id)
    if not pending:
        await update.message.reply_text("⚠️ Please select a plan first — use /start")
        return

    plan         = PLANS[pending["plan"]]
    method_key   = pending.get("method") or "unknown"
    method_label = PAYMENT_METHODS.get(method_key, {}).get("label", method_key)
    username     = pending.get("username", "Unknown")

    caption = (
        f"📸 <b>New Payment Screenshot</b>\n\n"
        f"👤 User: @{username} (<code>{user.id}</code>)\n"
        f"📦 Plan: <b>{plan['label']}</b> — <b>{plan['price']}</b>\n"
        f"💳 Method: <b>{method_label}</b>\n"
        f"🕐 Time: {now_utc().strftime('%d %b %Y %H:%M UTC')}"
    )

    photo = update.message.photo[-1] if update.message.photo else None
    doc   = update.message.document

    try:
        if photo:
            await context.bot.send_photo(
                chat_id=ADMIN_ID, photo=photo.file_id, caption=caption,
                reply_markup=admin_approval_keyboard(user.id, pending["plan"]), parse_mode="HTML"
            )
        elif doc:
            await context.bot.send_document(
                chat_id=ADMIN_ID, document=doc.file_id, caption=caption,
                reply_markup=admin_approval_keyboard(user.id, pending["plan"]), parse_mode="HTML"
            )
        else:
            await update.message.reply_text("⚠️ Please send a photo or image file.")
            return

        await update.message.reply_text(
            "✅ <b>Screenshot received!</b>\n\n"
            "⏳ Under review — you'll hear back within 1–24 hours.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Screenshot forward error: {e}")
        await update.message.reply_text("❌ Error sending screenshot. Try again.")

# ─── ADMIN TEXT HANDLER ───────────────────────────────────────────────────────
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text or ""

    # ── Waiting for invite link
    if "approving" in admin_state:
        uid        = admin_state.pop("approving")
        plan_key   = admin_state.pop("plan_key", None)
        invite_url = text.strip()

        if not invite_url.startswith("http"):
            await update.message.reply_text("⚠️ That doesn't look like a valid link. Try again.")
            return

        expiry = get_expiry(plan_key)
        db_upsert_user(uid, {
            "active":     True,
            "plan":       plan_key,
            "expires_at": expiry.isoformat() if expiry else None,
        })
        db_delete_pending(uid)

        plan       = PLANS[plan_key]
        expiry_txt = expiry.strftime("%d %b %Y") if expiry else "Lifetime ♾️"

        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"✅ <b>Payment Approved!</b>\n\n"
                    f"🎉 Welcome to the premium channel!\n\n"
                    f"📦 Plan: <b>{plan['label']}</b>\n"
                    f"💰 Amount: <b>{plan['price']}</b>\n"
                    f"📅 Expires: <b>{expiry_txt}</b>\n\n"
                    f"🔗 <b>Your unique join link:</b>\n{invite_url}\n\n"
                    "⚠️ This is a one-time link. Join immediately!"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Approval notify error: {e}")

        # Upsell (non-lifetime only)
        if plan_key != "lifetime":
            async def send_upsell():
                await asyncio.sleep(4)
                savings = "Save ₹400+ vs renewing monthly!" if plan_key == "7days" else "Pay once, keep access forever!"
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=(
                            f"💡 <b>Special offer for new members!</b>\n\n"
                            f"Upgrade to <b>Lifetime Access</b> for just <b>{PLANS['lifetime']['price']}</b>\n"
                            f"✨ {savings}\n\n"
                            "No renewals. No expiry. Pay once — stay forever.\n\n"
                            "👇 Tap below to upgrade:"
                        ),
                        reply_markup=upsell_keyboard(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Upsell error: {e}")
            asyncio.create_task(send_upsell())

        await update.message.reply_text(
            f"✅ Approved user <code>{uid}</code> — {plan['label']}\nInvite link sent.",
            parse_mode="HTML"
        )
        return

    # ── Waiting for rejection reason
    if "rejecting" in admin_state:
        uid = admin_state.pop("rejecting")
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"❌ <b>Payment Rejected</b>\n\n"
                    f"📝 Reason: {text}\n\n"
                    "Please resubmit or contact support."
                ),
                parse_mode="HTML"
            )
            await update.message.reply_text(f"✅ Rejection sent to <code>{uid}</code>.", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Could not notify user: {e}")
        return

    # CHANGE 2: dbroadcast — waiting for button text (no caption)
    if admin_state.get("dbroadcast_waiting_btn_text"):
        admin_state.pop("dbroadcast_waiting_btn_text")
        admin_state["dbroadcast_btn_text"] = text.strip()
        await update.message.reply_text("📹 <b>Now send me the video for the broadcast.</b>", parse_mode="HTML")
        return

# ─── ADMIN VIDEO HANDLER ──────────────────────────────────────────────────────
async def handle_admin_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if "dbroadcast_btn_text" not in admin_state:   # CHANGE 2
        return

    btn_text = admin_state.pop("dbroadcast_btn_text")   # CHANGE 2: use button text, no caption
    video    = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("⚠️ Please send a video file.")
        return

    file_id      = video.file_id
    main_bot_username = os.getenv('MAIN_BOT_USERNAME', '').lstrip('@')

    # CHANGE 2: button uses t.me/<bot>?start=start so it opens/starts the bot
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(btn_text, url=f"https://t.me/{main_bot_username}?start=start")
    ]])

    user_ids  = db_all_user_ids()
    sent_msgs = []
    sent = failed = blocked = 0
    status_msg = await update.message.reply_text(f"📤 Sending to {len(user_ids)} users...")

    for uid in user_ids:
        try:
            msg = await context.bot.send_video(
                chat_id=uid, video=file_id,
                reply_markup=kb, parse_mode="HTML"
                # CHANGE 2: no caption kwarg — video sent without caption
            )
            sent_msgs.append((uid, msg.message_id))
            sent += 1
        except TelegramError as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "not found" in err or "forbidden" in err:
                db_delete_user(uid)
                blocked += 1
            else:
                failed += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"📢 D-Broadcast done!\n✅ Sent: {sent}\n🚫 Blocked/removed: {blocked}\n❌ Failed: {failed}\n"
        f"⏰ Auto-deletes in 30 min."
    )

    async def delete_all():
        await asyncio.sleep(30 * 60)
        for chat_id, message_id in sent_msgs:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except:
                pass
    asyncio.create_task(delete_all())

# ─── /broadcast ───────────────────────────────────────────────────────────────
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    text       = " ".join(context.args)
    user_ids   = db_all_user_ids()
    sent = failed = blocked = 0
    status_msg = await update.message.reply_text(f"📤 Broadcasting to {len(user_ids)} users...")

    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            sent += 1
        except TelegramError as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "not found" in err or "forbidden" in err:
                db_delete_user(uid)
                blocked += 1
            else:
                failed += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"📢 Broadcast done!\n✅ Sent: {sent}\n🚫 Blocked/removed from DB: {blocked}\n❌ Failed: {failed}"
    )

# ─── /dbroadcast ──────────────────────────────────────────────────────────────
async def dbroadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    # CHANGE 2: ask for button text only, not a caption
    admin_state["dbroadcast_waiting_btn_text"] = True
    await update.message.reply_text(
        "🔘 <b>Send the button text for the broadcast video:</b>\n\n"
        "<i>e.g.</i> <code>🚀 View Plans</code>",
        parse_mode="HTML"
    )

# ─── EXPIRY CHECKER ───────────────────────────────────────────────────────────
async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    now          = now_utc()
    active_users = db_all_active()

    for row in active_users:
        uid        = row["user_id"]
        expires_at = row.get("expires_at")
        if not expires_at:
            continue  # lifetime

        try:
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
        except:
            continue

        # ── Kick expired user from all channels
        if now >= exp:
            try:
                for ch_id in CHANNEL_IDS:
                    try:
                        await context.bot.ban_chat_member(chat_id=ch_id, user_id=uid)
                        await context.bot.unban_chat_member(chat_id=ch_id, user_id=uid)
                        logger.info(f"Kicked {uid} from {ch_id}")
                    except TelegramError as kick_err:
                        logger.error(f"Could not kick {uid} from {ch_id}: {kick_err}")

                await context.bot.send_message(
                    chat_id=uid,
                    text=(
                        "⚠️ <b>Your subscription has expired.</b>\n\n"
                        "You've been removed from the channel(s).\n\n"
                        "🔄 Tap below to renew and get back in:"
                    ),
                    reply_markup=renew_keyboard(),
                    parse_mode="HTML"
                )
                db_upsert_user(uid, {"active": False, "plan": None, "expires_at": None})
                logger.info(f"Processed expired user {uid}")
            except TelegramError as e:
                logger.error(f"Expiry handler error for {uid}: {e}")
            continue

        # ── Renewal reminder 23-25h before expiry
        time_left = exp - now
        if timedelta(hours=23) <= time_left <= timedelta(hours=25):
            try:
                plan_key   = row.get("plan", "1month")
                plan_label = PLANS.get(plan_key, {}).get("label", "your plan")
                await context.bot.send_message(
                    chat_id=uid,
                    text=(
                        f"⏰ <b>Subscription Expiring Soon!</b>\n\n"
                        f"📦 Plan: <b>{plan_label}</b>\n"
                        f"📅 Expires: <b>{exp.strftime('%d %b %Y at %H:%M UTC')}</b>\n\n"
                        "Renew now to avoid losing access.\n"
                        "👑 Or upgrade to <b>Lifetime</b> — pay once, never worry again!"
                    ),
                    reply_markup=renew_keyboard(),
                    parse_mode="HTML"
                )
                logger.info(f"Sent renewal reminder to {uid}")
            except TelegramError as e:
                logger.error(f"Renewal reminder failed for {uid}: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("broadcast",  broadcast))
    app.add_handler(CommandHandler("dbroadcast", dbroadcast))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.IMAGE & ~filters.User(ADMIN_ID),
        handle_screenshot
    ))
    app.add_handler(MessageHandler(
        filters.User(ADMIN_ID) & (filters.VIDEO | filters.Document.VIDEO),
        handle_admin_video
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID),
        handle_admin_text
    ))

    app.job_queue.run_repeating(check_expirations, interval=3600, first=60)

    logger.info("✅ Bot 1 (Main) started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
