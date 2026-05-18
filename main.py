
# BAMSPX Subscription Bot
# Generated for Badr

import os
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from db import (
    get_setting,
    set_setting,
    is_verified,
    save_verified,
    get_verified_phone,
    get_subscriber,
    save_subscriber,
    delete_subscriber,
    get_all_expired,
    get_pending,
    save_pending,
    update_pending_status,
    delete_pending,
    get_stats,
    search_users,
    get_all_active_subscribers,
    mark_reminder,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

CHANNEL_ID = -1003618409425
PUBLIC_CHANNEL = "https://t.me/bam_spx"
SUPPORT_URL = "https://t.me/BAMSPX"

BANK_NAME = "العربي الوطني"
ACCOUNT_NAME = "شركة برق | barq"
IBAN = "SA3830100991106159103174"

PLANS = {
    "1m": {"label": "شهري", "months": 1, "price": 250},
    "3m": {"label": "3 أشهر", "months": 3, "price": 550},
    "6m": {"label": "6 أشهر", "months": 6, "price": 1000},
    "12m": {"label": "سنوي", "months": 12, "price": 2500},
}

def phone_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 مشاركة رقم الجوال", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 اشتراك جديد", callback_data="subscribe")],
        [InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")],
        [InlineKeyboardButton("📊 حالة اشتراكي", callback_data="status")],
        [InlineKeyboardButton("📢 القناة العامة", url=PUBLIC_CHANNEL)],
        [InlineKeyboardButton("💬 التواصل مع الدعم", url=SUPPORT_URL)],
    ])

def plans_keyboard():
    rows = []
    for key, plan in PLANS.items():
        rows.append([
            InlineKeyboardButton(
                f"{plan['label']} — {plan['price']} ريال",
                callback_data=f"plan_{key}"
            )
        ])
    return InlineKeyboardMarkup(rows)

async def get_admin():
    return await get_setting("admin_id")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)

    if not await is_verified(uid):
        await update.message.reply_text(
            "مرحباً بكم في BAMSPX 🤝\n\nيُرجى تقديم رقم الهاتف المحمول للمتابعة واختيار باقة الاشتراك المناسبة 📱✨",
            reply_markup=phone_keyboard()
        )
        return

    await update.message.reply_text(
        "اختر من القائمة 👇",
        reply_markup=main_keyboard()
    )

async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact

    if contact.user_id != user.id:
        await update.message.reply_text("⚠️ يرجى مشاركة رقمك فقط.")
        return

    await save_verified(
        str(user.id),
        contact.phone_number,
        user.full_name,
        user.username or ""
    )

    await update.message.reply_text(
        "✅ تم التحقق بنجاح",
        reply_markup=ReplyKeyboardRemove()
    )

    await update.message.reply_text(
        "اختر من القائمة 👇",
        reply_markup=main_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    uid = str(query.from_user.id)

    if data == "subscribe":
        await query.edit_message_text(
            "اختر الباقة المناسبة 👇",
            reply_markup=plans_keyboard()
        )

    elif data.startswith("plan_"):
        key = data.replace("plan_", "")
        plan = PLANS[key]

        pending = await get_pending(uid)

        if pending and pending["status"] == "receipt_sent":
            await query.answer("تم إرسال إيصالك مسبقاً", show_alert=True)
            return

        phone = await get_verified_phone(uid)

        await save_pending(
            uid,
            key,
            query.from_user.full_name,
            query.from_user.username or "",
            phone,
            "awaiting_receipt"
        )

        text = f"""
📦 الباقة: {plan['label']}
💰 السعر: {plan['price']} ريال

🏦 البنك: {BANK_NAME}
👤 الاسم: {ACCOUNT_NAME}

📌 الآيبان:
{IBAN}

📎 أرسل إيصال التحويل الآن.
"""

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
            ])
        )

    elif data == "back":
        await query.edit_message_text(
            "اختر من القائمة 👇",
            reply_markup=main_keyboard()
        )

    elif data == "status":
        sub = await get_subscriber(uid)

        if not sub:
            text = "❌ لا يوجد اشتراك نشط"
        else:
            exp = datetime.fromisoformat(sub["expires_at"])
            left = exp - datetime.now()

            if left.total_seconds() <= 0:
                text = "❌ اشتراكك منتهي"
            else:
                text = f"✅ اشتراكك فعال\n\nينتهي بتاريخ:\n{exp.strftime('%Y-%m-%d')}"

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
            ])
        )

    elif data.startswith("approve_"):
        admin_id = await get_admin()

        if uid != str(admin_id):
            return

        _, target_uid, plan_key = data.split("_")

        plan = PLANS[plan_key]

        expires = datetime.now() + timedelta(days=plan["months"] * 30)

        await save_subscriber(target_uid, plan_key, expires)
        await delete_pending(target_uid)

        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int((datetime.now() + timedelta(minutes=5)).timestamp()),
            name=f"sub_{target_uid}"
        )

        await context.bot.send_message(
            chat_id=int(target_uid),
            text=invite.invite_link
        )

        await query.edit_message_text("✅ تم قبول الاشتراك وإرسال الرابط")

    elif data.startswith("reject_"):
        admin_id = await get_admin()

        if uid != str(admin_id):
            return

        target_uid = data.replace("reject_", "")

        await delete_pending(target_uid)

        await context.bot.send_message(
            chat_id=int(target_uid),
            text="❌ تم رفض الإيصال"
        )

        await query.edit_message_text("تم رفض الطلب")

async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)

    if not await is_verified(uid):
        return

    pending = await get_pending(uid)

    if not pending:
        return

    if pending["status"] == "receipt_sent":
        await update.message.reply_text(
            "✅ تم استلام إيصالك مسبقاً، يرجى انتظار مراجعة الإدارة."
        )
        return

    admin_id = await get_admin()

    if not admin_id:
        return

    plan = PLANS[pending["plan_key"]]

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ قبول",
                callback_data=f"approve_{uid}_{pending['plan_key']}"
            ),
            InlineKeyboardButton(
                "❌ رفض",
                callback_data=f"reject_{uid}"
            )
        ]
    ])

    caption = f"""
📥 طلب اشتراك جديد

👤 {user.full_name}
📱 {await get_verified_phone(uid)}
📦 {plan['label']}
💰 {plan['price']} ريال

🆔 {uid}
"""

    if update.message.photo:
        await context.bot.send_photo(
            chat_id=int(admin_id),
            photo=update.message.photo[-1].file_id,
            caption=caption,
            reply_markup=kb
        )

        await update_pending_status(uid, "receipt_sent")

        await update.message.reply_text(
            "✅ تم استلام الإيصال"
        )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    admin_id = await get_admin()

    if admin_id is None:
        await set_admin(uid)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
    ])

    await update.message.reply_text(
        "لوحة الأدمن",
        reply_markup=keyboard
    )

async def check_expired(context: ContextTypes.DEFAULT_TYPE):
    expired = await get_all_expired()

    for row in expired:
        uid = row["uid"]

        try:
            await context.bot.ban_chat_member(CHANNEL_ID, int(uid))
            await context.bot.unban_chat_member(CHANNEL_ID, int(uid))

            await context.bot.send_message(
                chat_id=int(uid),
                text="⏰ انتهى اشتراكك",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")]
                ])
            )

        except Exception as e:
            logger.error(e)

        await delete_subscriber(uid)

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    subscribers = await get_all_active_subscribers()

    for sub in subscribers:
        uid = sub["uid"]

        exp = datetime.fromisoformat(sub["expires_at"])
        left = exp - datetime.now()

        days = left.days

        if days <= 3 and not sub.get("reminder_3d_sent"):
            await context.bot.send_message(
                chat_id=int(uid),
                text="⏰ اشتراكك سينتهي خلال 3 أيام",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")]
                ])
            )
            await mark_reminder(uid, "3d")

        if days <= 1 and not sub.get("reminder_1d_sent"):
            await context.bot.send_message(
                chat_id=int(uid),
                text="⚠️ تبقى أقل من 24 ساعة على انتهاء اشتراكك",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")]
                ])
            )
            await mark_reminder(uid, "1d")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))

    app.add_handler(MessageHandler(filters.CONTACT, receive_contact))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.ALL, receive_message)
    )

    app.job_queue.run_repeating(check_expired, interval=3600, first=10)
    app.job_queue.run_repeating(check_reminders, interval=3600, first=20)

    print("BAMSPX BOT STARTED")
    app.run_polling()

if __name__ == "__main__":
    main()
