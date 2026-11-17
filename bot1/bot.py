import os
import time
import html
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
from telegram.error import TelegramError, RetryAfter
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

# ─── FIXED INVITE LINK ────────────────────────────────────────────────────────
INVITE_LINK = "https://t.me/addlist/6sPqdvmZIgA3N2Y1"

# ─── IMAGES ───────────────────────────────────────────────────────────────────
WELCOME_IMAGE      = "https://graph.org/file/95aa04ea6bacf4ace8816-ec4e9510ee1a94e33c.jpg"
PAYMENT_MAIN_IMAGE = "https://graph.org/file/bda4c8741cef3354d467f-2d3c7faabd36813f12.jpg"
DONATE_IMAGE       = "https://graph.org/file/d0108817594a1b51532a4-396122f7b54970bd86.jpg"

# ─── PLANS ────────────────────────────────────────────────────────────────────
PLANS = {
    "7days":    {"label": "⚡ 7-Day Access",    "price": "$8 / ₹499",  "days": 7,  "inr": 499,  "usd": 8},
    "1month":   {"label": "🔥 1-Month Access",  "price": "$10 / ₹699", "days": 30, "inr": 699,  "usd": 10},
    "lifetime": {"label": "👑 Lifetime Access", "price": "$12 / ₹899", "days": None,"inr": 899, "usd": 12},
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

DONATE_METHODS     = PAYMENT_METHODS
RATING             = "4.9★"
BASE_MEMBER_COUNT  = 200

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
    _known_users.discard(user_id)
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
    # limit(1): we only need the exact count header, not every row
    r = supabase.table("subscribers").select("user_id", count="exact").limit(1).execute()
    count = r.count or 0
    return max(count, BASE_MEMBER_COUNT)

def get_expiry(plan_key):
    days = PLANS[plan_key]["days"]
    if days is None:
        return None
    return now_utc() + timedelta(days=days)

# ─── SPEED HELPERS (/start fast-path) ─────────────────────────────────────────
# supabase-py is a *synchronous* client. Calling it directly inside an async
# handler freezes the whole event loop until the HTTP round-trip finishes, so
# every DB call from a handler goes through adb() (runs in a worker thread).
async def adb(fn, *args):
    return await asyncio.to_thread(fn, *args)

MEMBER_COUNT_TTL = 300          # seconds the "N+ members" number is cached
_member_count    = {"value": BASE_MEMBER_COUNT, "ts": 0.0}
_known_users: set = set()       # users already confirmed to be in the DB
_welcome_file_id = None         # Telegram file_id of the welcome photo (after 1st send)

async def _refresh_member_count():
    try:
        _member_count["value"] = await adb(db_total_users)
    except Exception as e:
        logger.warning(f"Member count refresh failed: {e}")

def get_member_count() -> int:
    """Instant: returns the cached count and refreshes it in the background when stale."""
    if time.monotonic() - _member_count["ts"] > MEMBER_COUNT_TTL:
        _member_count["ts"] = time.monotonic()   # stops several /start calls refreshing at once
        spawn(_refresh_member_count())
    return _member_count["value"]

def _register_user_sync(user_id: int, username: str, first_name: str):
    # ignore_duplicates -> INSERT ... ON CONFLICT DO NOTHING: one query instead of
    # get + upsert, and an existing subscriber's plan/expiry is never overwritten.
    supabase.table("subscribers").upsert({
        "user_id":    user_id,
        "username":   username,
        "first_name": first_name,
        "active":     False,
        "plan":       None,
        "expires_at": None,
        "joined_at":  now_utc().isoformat(),
    }, on_conflict="user_id", ignore_duplicates=True).execute()

async def register_user(user):
    if user.id in _known_users:
        return
    try:
        await adb(_register_user_sync, user.id, user.username or "", user.first_name or "")
        _known_users.add(user.id)
    except Exception as e:
        logger.error(f"register_user failed for {user.id}: {e}")

# ─── ADMIN STATE ──────────────────────────────────────────────────────────────
admin_state: dict = {}

# Keep a reference to every background task so Python can't silently
# garbage-collect (kill) a long-running broadcast half way.
bg_tasks: set = set()

def spawn(coro):
    task = asyncio.create_task(coro)
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)
    return task

def retry_seconds(e: RetryAfter) -> float:
    """Flood-wait time in seconds (works whether PTB gives an int or a timedelta)."""
    ra = e.retry_after
    return ra.total_seconds() if hasattr(ra, "total_seconds") else float(ra)

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def plans_keyboard():
    buttons = []
    for key, plan in PLANS.items():
        buttons.append([InlineKeyboardButton(
            f"{plan['label']} — {plan['price']}", callback_data=f"plan_{key}"
        )])
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
    buttons.append([InlineKeyboardButton("🔙 Back to Payment Methods", callback_data=f"backpay_{plan_key}")])
    return InlineKeyboardMarkup(buttons)

def donate_method_detail_keyboard(extra_buttons=None):
    buttons = list(extra_buttons or [])
    buttons.append([InlineKeyboardButton("🔙 Back to Donate", callback_data="donate_back")])
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

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _welcome_file_id
    user    = update.effective_user
    chat_id = update.effective_chat.id

    # Registering the user is NOT needed to show the welcome screen, so it runs
    # in the background and the user gets their reply immediately.
    spawn(register_user(user))

    text = welcome_text(html.escape(user.first_name or "there"), get_member_count())

    # Try the cached file_id first (no download on Telegram's side), then the URL.
    for source in filter(None, (_welcome_file_id, WELCOME_IMAGE)):
        try:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=source,
                caption=text,
                reply_markup=plans_keyboard(),
                parse_mode="HTML",
                protect_content=True,   # unforwardable
            )
            if msg.photo:
                _welcome_file_id = msg.photo[-1].file_id
            return
        except Exception as e:
            logger.warning(f"Welcome photo failed ({'file_id' if source == _welcome_file_id else 'url'}): {e}")
            if source == _welcome_file_id:
                _welcome_file_id = None   # stale/invalid -> fall through to the URL

    await context.bot.send_message(
        chat_id=chat_id, text=text,
        reply_markup=plans_keyboard(), parse_mode="HTML"
    )

# ─── /stats ───────────────────────────────────────────────────────────────────
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return

    await update.message.reply_text("⏳ Fetching stats...")

    try:
        # All subscribers
        all_users_r  = await adb(lambda: supabase.table("subscribers").select("*").execute())
        all_users    = all_users_r.data or []

        # Active subscribers
        active_users = [u for u in all_users if u.get("active")]

        # Pending payments
        pending_r    = await adb(lambda: supabase.table("pending_payments").select("*").execute())
        pending      = pending_r.data or []

        # Totals
        total_users   = max(len(all_users), BASE_MEMBER_COUNT)
        total_active  = len(active_users)
        total_inactive = len(all_users) - total_active
        total_pending = len(pending)

        # Per-plan breakdown of active subscribers
        plan_counts = {"7days": 0, "1month": 0, "lifetime": 0, "other": 0}
        for u in active_users:
            pk = u.get("plan") or "other"
            if pk in plan_counts:
                plan_counts[pk] += 1
            else:
                plan_counts["other"] += 1

        # Estimated earnings (INR & USD) from active subscribers by plan
        est_inr = sum(
            plan_counts.get(pk, 0) * PLANS[pk]["inr"]
            for pk in ("7days", "1month", "lifetime")
        )
        est_usd = sum(
            plan_counts.get(pk, 0) * PLANS[pk]["usd"]
            for pk in ("7days", "1month", "lifetime")
        )

        # Expiring within 24 hours
        now = now_utc()
        expiring_soon = 0
        for u in active_users:
            exp = u.get("expires_at")
            if not exp:
                continue
            try:
                dt = datetime.fromisoformat(exp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if now <= dt <= now + timedelta(hours=24):
                    expiring_soon += 1
            except:
                pass

        # Newest 3 subscribers
        newest = sorted(
            [u for u in all_users if u.get("joined_at")],
            key=lambda u: u["joined_at"], reverse=True
        )[:3]
        newest_lines = ""
        for u in newest:
            name = u.get("username") or u.get("first_name") or str(u["user_id"])
            newest_lines += f"  • @{name} — {u.get('plan') or 'no plan'}\n"

        text = (
            "📊 <b>Bot Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"

            "👥 <b>Users</b>\n"
            f"  Total registered : <b>{total_users:,}</b>\n"
            f"  Active (paid)    : <b>{total_active:,}</b>\n"
            f"  Inactive         : <b>{total_inactive:,}</b>\n"
            f"  Pending payment  : <b>{total_pending:,}</b>\n"
            f"  Expiring in 24h  : <b>{expiring_soon:,}</b>\n\n"

            "📦 <b>Active — Plan Breakdown</b>\n"
            f"  ⚡ 7-Day     : <b>{plan_counts['7days']:,}</b>\n"
            f"  🔥 1-Month   : <b>{plan_counts['1month']:,}</b>\n"
            f"  👑 Lifetime  : <b>{plan_counts['lifetime']:,}</b>\n\n"

            "💰 <b>Estimated Earnings (active subs)</b>\n"
            f"  INR : <b>₹{est_inr:,}</b>\n"
            f"  USD : <b>${est_usd:,}</b>\n\n"

            "🆕 <b>Latest Subscribers</b>\n"
            f"{newest_lines}"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>🕐 {now.strftime('%d %b %Y %H:%M UTC')}</i>"
        )

        await update.message.reply_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Stats error: {e}")
        await update.message.reply_text(f"❌ Error fetching stats: {e}")

# ─── BUTTON HANDLER ───────────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    # ── Back to plans: delete the plan/payment msg, original plans msg stays
    if data == "back_plans":
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message on back_plans: {e}")
        return

    # ── Donate hub — send new message
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

    # ── Back to donate hub — edit in place
    if data == "donate_back":
        text = (
            "💝 <b>Support This Bot</b>\n\n"
            "This bot runs on passion and your generosity.\n"
            "Every donation — big or small — keeps the servers alive,\n"
            "the content fresh, and the community growing. 🙏\n\n"
            "<i>Just pay what feels right.</i>\n\n"
            "👇 Choose your donation method:"
        )
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=DONATE_IMAGE, caption=text, parse_mode="HTML"),
                reply_markup=donate_keyboard(),
            )
        except Exception as e:
            logger.warning(f"edit_message_media failed for donate_back: {e}")
            try:
                await query.message.reply_photo(photo=DONATE_IMAGE, caption=text, reply_markup=donate_keyboard(), parse_mode="HTML")
            except:
                await query.message.reply_text(text, reply_markup=donate_keyboard(), parse_mode="HTML")
        return

    # ── Donate method — edit in place
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
        kb = donate_method_detail_keyboard(method.get("extra_buttons", []))
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=method["image"], caption=text, parse_mode="HTML"),
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning(f"edit_message_media failed for donate method: {e}")
            try:
                await query.message.reply_photo(photo=method["image"], caption=text, reply_markup=kb, parse_mode="HTML")
            except:
                await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
        return

    # ── Plan selected → send NEW message with payment methods
    if data.startswith("plan_"):
        plan_key = data[5:]
        plan = PLANS[plan_key]
        await adb(db_upsert_pending, user.id, {
            "plan":     plan_key,
            "method":   None,
            "username": user.username or user.first_name,
        })
        text = (
            f"🎯 You selected: <b>{plan['label']}</b>\n"
            f"💰 Price: <b>{plan['price']}</b>\n\n"
            "💳 <b>Choose your payment method:</b>"
        )
        try:
            await query.message.reply_photo(
                photo=PAYMENT_MAIN_IMAGE,
                caption=text,
                reply_markup=payment_methods_keyboard(plan_key),
                parse_mode="HTML"
            )
        except:
            await query.message.reply_text(text, reply_markup=payment_methods_keyboard(plan_key), parse_mode="HTML")
        return

    # ── Back to payment methods — edit image + keyboard in place
    if data.startswith("backpay_"):
        plan_key = data[8:]
        plan = PLANS[plan_key]
        text = (
            f"🎯 You selected: <b>{plan['label']}</b>\n"
            f"💰 Price: <b>{plan['price']}</b>\n\n"
            "💳 <b>Choose your payment method:</b>"
        )
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=PAYMENT_MAIN_IMAGE, caption=text, parse_mode="HTML"),
                reply_markup=payment_methods_keyboard(plan_key),
            )
        except Exception as e:
            logger.warning(f"edit_message_media failed for backpay_: {e}")
            try:
                await query.message.reply_photo(
                    photo=PAYMENT_MAIN_IMAGE, caption=text,
                    reply_markup=payment_methods_keyboard(plan_key), parse_mode="HTML"
                )
            except:
                await query.message.reply_text(text, reply_markup=payment_methods_keyboard(plan_key), parse_mode="HTML")
        return

    # ── Payment method selected — edit the current (plan) message in place
    if data.startswith("pay_"):
        _, method_key, plan_key = data.split("_", 2)
        method  = PAYMENT_METHODS[method_key]
        plan    = PLANS[plan_key]
        pending = await adb(db_get_pending, user.id) or {}
        pending["method"] = method_key
        await adb(db_upsert_pending, user.id, pending)

        body = method.get("text", method.get("details", ""))
        text = (
            f"📦 Plan: <b>{plan['label']}</b>\n"
            f"💰 Amount: <b>{plan['price']}</b>\n\n"
        ) + body

        kb = method_detail_keyboard(plan_key, method.get("extra_buttons", []))
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

    # ── Admin: Approve — auto-sends fixed invite link
    if data.startswith("approve_"):
        if user.id != ADMIN_ID:
            await query.answer("❌ Not authorized.", show_alert=True)
            return
        _, uid, plan_key = data.split("_", 2)
        uid = int(uid)

        expiry = get_expiry(plan_key)
        await adb(db_upsert_user, uid, {
            "active":     True,
            "plan":       plan_key,
            "expires_at": expiry.isoformat() if expiry else None,
        })
        await adb(db_delete_pending, uid)

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
                    f"🔗 <b>Your join link:</b>\n{INVITE_LINK}\n\n"
                    "👆 Tap the link above to join now!"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Approval notify error: {e}")

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
            spawn(send_upsell())

        try:
            await query.edit_message_caption(
                caption=f"✅ Approved — {plan['label']} — User <code>{uid}</code>",
                parse_mode="HTML"
            )
        except:
            pass

        await query.message.reply_text(
            f"✅ Approved user <code>{uid}</code> — {plan['label']}\nInvite link auto-sent.",
            parse_mode="HTML"
        )
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
    pending = await adb(db_get_pending, user.id)
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

    # ── dbroadcast: waiting for button text
    if admin_state.get("dbroadcast_waiting_btn_text"):
        admin_state.pop("dbroadcast_waiting_btn_text")
        admin_state["dbroadcast_btn_text"] = text.strip()
        await update.message.reply_text("📹 <b>Now send me the video for the broadcast.</b>", parse_mode="HTML")
        return

# ─── ADMIN VIDEO HANDLER ──────────────────────────────────────────────────────
DBROADCAST_DELETE_SECONDS = 30 * 60      # sent videos are deleted after 30 min
AUTO_BROADCAST_INTERVAL   = 4 * 60 * 60  # /autodeletebroadcast repeats every 4 hours
AUTO_JOB_NAME             = "auto_delete_broadcast"

async def handle_admin_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if "dbroadcast_btn_text" not in admin_state:
        return

    btn_text = admin_state.pop("dbroadcast_btn_text")
    mode     = admin_state.pop("dbroadcast_mode", "once")
    video    = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("⚠️ Please send a video file.")
        return

    file_id           = video.file_id
    main_bot_username = os.getenv('MAIN_BOT_USERNAME', '').lstrip('@')

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(btn_text, url=f"https://t.me/{main_bot_username}?start=start")
    ]])

    if mode == "auto":
        # Replace any auto-broadcast that is already running.
        for job in context.job_queue.get_jobs_by_name(AUTO_JOB_NAME):
            job.schedule_removal()
        context.job_queue.run_repeating(
            auto_broadcast_job,
            interval=AUTO_BROADCAST_INTERVAL,
            first=1,                       # first send right away, then every 4h
            name=AUTO_JOB_NAME,
            data={"file_id": file_id, "kb": kb, "cycle": 0},
        )
        await update.message.reply_text(
            "🔁 <b>Auto-delete broadcast started!</b>\n\n"
            "📤 First send: now\n"
            "⏱ Repeats every: <b>4 hours</b>\n"
            "🗑 Each batch auto-deletes after <b>30 min</b>\n\n"
            "Stop it anytime with /stopautobroadcast",
            parse_mode="HTML"
        )
        return

    user_ids   = await adb(db_all_user_ids)
    status_msg = await update.message.reply_text(f"📤 Sending to {len(user_ids)} users...")

    # Fire-and-forget: hand the send loop off to a background task so this
    # handler returns immediately and the bot keeps handling everything else.
    spawn(_run_dbroadcast(context, file_id, kb, status_msg, user_ids))


async def _run_dbroadcast(context, file_id, kb, status_msg, user_ids, label="D-Broadcast"):
    sent_msgs = []
    sent = failed = blocked = 0

    for uid in user_ids:
        for attempt in range(2):  # 2nd attempt only after a flood-wait
            try:
                msg = await context.bot.send_video(
                    chat_id=uid, video=file_id,
                    reply_markup=kb, parse_mode="HTML"
                )
                sent_msgs.append((uid, msg.message_id))
                sent += 1
                break
            except RetryAfter as e:
                logger.warning(f"Flood wait: sleeping {retry_seconds(e)}s")
                await asyncio.sleep(retry_seconds(e) + 1)
                if attempt == 1:
                    failed += 1
            except TelegramError as e:
                err = str(e).lower()
                if "blocked" in err or "deactivated" in err or "not found" in err or "forbidden" in err:
                    # run the DB call in a thread so it doesn't freeze the bot
                    await asyncio.to_thread(db_delete_user, uid)
                    blocked += 1
                else:
                    failed += 1
                break
        await asyncio.sleep(0.05)

    try:
        await status_msg.edit_text(
            f"📢 {label} done!\n✅ Sent: {sent}\n🚫 Blocked/removed: {blocked}\n❌ Failed: {failed}\n"
            f"⏰ Auto-deletes in {DBROADCAST_DELETE_SECONDS // 60} min."
        )
    except TelegramError as e:
        logger.warning(f"Could not edit {label} status message: {e}")

    async def delete_all():
        await asyncio.sleep(DBROADCAST_DELETE_SECONDS)
        for chat_id, message_id in sent_msgs:
            for attempt in range(2):
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    break
                except RetryAfter as e:
                    await asyncio.sleep(retry_seconds(e) + 1)
                except Exception:
                    break
            await asyncio.sleep(0.05)
    spawn(delete_all())


async def auto_broadcast_job(context: ContextTypes.DEFAULT_TYPE):
    """Runs every 4 hours: same as one /dbroadcast (send to everyone, delete after 30 min)."""
    data = context.job.data
    data["cycle"] += 1
    try:
        # Fresh user list every cycle, so new users get it and removed users are skipped.
        user_ids   = await adb(db_all_user_ids)
        status_msg = await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔁 Auto-broadcast #{data['cycle']}: sending to {len(user_ids)} users..."
        )
        spawn(_run_dbroadcast(
            context, data["file_id"], data["kb"], status_msg, user_ids,
            label=f"Auto-Broadcast #{data['cycle']}"
        ))
    except Exception as e:
        logger.error(f"Auto-broadcast cycle failed: {e}")

# ─── /broadcast ───────────────────────────────────────────────────────────────
async def _run_broadcast(context: ContextTypes.DEFAULT_TYPE, text: str, status_msg, user_ids):
    """Actual send loop, run as a background task so it never blocks other handlers."""
    sent = failed = blocked = 0

    for uid in user_ids:
        for attempt in range(2):  # 2nd attempt only after a flood-wait
            try:
                await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
                sent += 1
                break
            except RetryAfter as e:
                logger.warning(f"Flood wait: sleeping {retry_seconds(e)}s")
                await asyncio.sleep(retry_seconds(e) + 1)
                if attempt == 1:
                    failed += 1
            except TelegramError as e:
                err = str(e).lower()
                if "blocked" in err or "deactivated" in err or "not found" in err or "forbidden" in err:
                    # run the DB call in a thread so it doesn't freeze the bot
                    await asyncio.to_thread(db_delete_user, uid)
                    blocked += 1
                else:
                    failed += 1
                break
        await asyncio.sleep(0.05)

    try:
        await status_msg.edit_text(
            f"📢 Broadcast done!\n✅ Sent: {sent}\n🚫 Blocked/removed from DB: {blocked}\n❌ Failed: {failed}"
        )
    except TelegramError as e:
        logger.warning(f"Could not edit broadcast status message: {e}")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    text        = " ".join(context.args)
    user_ids    = await asyncio.to_thread(db_all_user_ids)
    status_msg  = await update.message.reply_text(f"📤 Broadcasting to {len(user_ids)} users...")

    # Fire-and-forget: the handler returns immediately, so the bot keeps
    # responding to every other command/button/message while this runs.
    spawn(_run_broadcast(context, text, status_msg, user_ids))

# ─── /dbroadcast ──────────────────────────────────────────────────────────────
async def dbroadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    admin_state.pop("dbroadcast_btn_text", None)
    admin_state["dbroadcast_mode"] = "once"
    admin_state["dbroadcast_waiting_btn_text"] = True
    await update.message.reply_text(
        "🔘 <b>Send the button text for the broadcast video:</b>\n\n"
        "<i>e.g.</i> <code>🚀 View Plans</code>",
        parse_mode="HTML"
    )

# ─── /autodeletebroadcast ─────────────────────────────────────────────────────
async def autodeletebroadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Same flow as /dbroadcast (button text -> video), but repeats every 4 hours."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    admin_state.pop("dbroadcast_btn_text", None)
    admin_state["dbroadcast_mode"] = "auto"
    admin_state["dbroadcast_waiting_btn_text"] = True
    await update.message.reply_text(
        "🔁 <b>Auto-delete broadcast (every 4 hours)</b>\n\n"
        "🔘 <b>Send the button text for the broadcast video:</b>\n\n"
        "<i>e.g.</i> <code>🚀 View Plans</code>",
        parse_mode="HTML"
    )

# ─── /stopautobroadcast ───────────────────────────────────────────────────────
async def stopautobroadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    jobs = context.job_queue.get_jobs_by_name(AUTO_JOB_NAME)
    for job in jobs:
        job.schedule_removal()
    await update.message.reply_text(
        "🛑 Auto-delete broadcast stopped. (Videos already sent still auto-delete on time.)"
        if jobs else "ℹ️ No auto-delete broadcast is running."
    )

# ─── EXPIRY CHECKER ───────────────────────────────────────────────────────────
async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    now          = now_utc()
    active_users = await asyncio.to_thread(db_all_active)

    for row in active_users:
        uid        = row["user_id"]
        expires_at = row.get("expires_at")
        if not expires_at:
            continue

        try:
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
        except:
            continue

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
                await asyncio.to_thread(db_upsert_user, uid, {"active": False, "plan": None, "expires_at": None})
                logger.info(f"Processed expired user {uid}")
            except TelegramError as e:
                logger.error(f"Expiry handler error for {uid}: {e}")
            continue

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

# ─── STARTUP WARM-UP ──────────────────────────────────────────────────────────
async def warm_up(app: Application):
    """Pre-load the member count and the welcome photo's file_id so even the
    very first /start after a restart is instant."""
    global _welcome_file_id
    _member_count["ts"] = time.monotonic()
    await _refresh_member_count()
    try:
        msg = await app.bot.send_photo(chat_id=ADMIN_ID, photo=WELCOME_IMAGE, disable_notification=True)
        if msg.photo:
            _welcome_file_id = msg.photo[-1].file_id
        await msg.delete()
    except Exception as e:
        logger.info(f"Welcome photo warm-up skipped: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        # Big pool + longer pool timeout: while a broadcast is sending, normal
        # replies (like /start) must never queue up waiting for a free connection.
        .connection_pool_size(256)
        .pool_timeout(30)
        .post_init(warm_up)
        .build()
    )

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("broadcast",  broadcast))
    app.add_handler(CommandHandler("dbroadcast", dbroadcast))
    app.add_handler(CommandHandler("autodeletebroadcast", autodeletebroadcast))
    app.add_handler(CommandHandler("stopautobroadcast", stopautobroadcast))
    app.add_handler(CommandHandler("stats",      stats))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(
        (filters.PHOTO | filters.Document.IMAGE) & ~filters.User(ADMIN_ID),
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
