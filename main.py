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
    get_verified_user,
    get_subscriber,
    save_subscriber,
    delete_subscriber,
    get_all_expired,
    get_pending,
    save_pending,
    update_pending_status,
    delete_pending,
    save_channel_user,
    get_channel_users_count,
    get_all_channel_users,
    get_stats,
    search_users,
    get_all_active_subscribers,
    mark_reminder,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003618409425"))
PUBLIC_CHANNEL_URL = os.environ.get("PUBLIC_CHANNEL_URL", "https://t.me/bam_spx")
SUPPORT_URL = os.environ.get("SUPPORT_URL", "https://t.me/BAMSPX")

BANK_NAME = os.environ.get("BANK_NAME", "العربي الوطني")
ACCOUNT_NAME = os.environ.get("ACCOUNT_NAME", "شركة برق | barq")
IBAN = os.environ.get("IBAN", "SA3830100991106159103174")

PLANS = {
    "1m": {"label": "شهري", "months": 1, "price": 250},
    "3m": {"label": "3 أشهر", "months": 3, "price": 550},
    "6m": {"label": "6 أشهر", "months": 6, "price": 1000},
    "12m": {"label": "سنوي", "months": 12, "price": 2500},
}


async def get_admin():
    return await get_setting("admin_id")


async def set_admin(uid):
    await set_setting("admin_id", uid)


def is_active_sub(sub):
    if not sub:
        return False
    try:
        return datetime.fromisoformat(sub["expires_at"]) > datetime.now()
    except Exception:
        return False


def phone_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 مشاركة رقم الجوال", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🛒 اشتراك جديد", callback_data="subscribe")],
            [InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")],
            [InlineKeyboardButton("📊 حالة اشتراكي", callback_data="status")],
            [InlineKeyboardButton("📢 القناة العامة", url=PUBLIC_CHANNEL_URL)],
            [InlineKeyboardButton("💬 التواصل مع الدعم", url=SUPPORT_URL)],
        ]
    )


def plans_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"📦 {plan['label']} — {plan['price']} ريال",
                    callback_data=f"plan_{key}",
                )
            ]
            for key, plan in PLANS.items()
        ]
    )


def admin_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 نشر رسالة التحقق في القناة", callback_data="admin_verifypost")],
            [InlineKeyboardButton("👥 عدد المستخدمين المحفوظين", callback_data="admin_channelusers")],
            [InlineKeyboardButton("📨 إرسال رسالة للكل", callback_data="admin_blast")],
            [InlineKeyboardButton("🔎 البحث عن مستخدم", callback_data="admin_search")],
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("🗑 فحص المنتهين وإزالتهم", callback_data="admin_checkexpired")],
        ]
    )


def back_admin_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للوحة الأدمن", callback_data="admin_back")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    admin_id = await get_admin()

    if uid == str(admin_id):
        await update.message.reply_text("👑 لوحة تحكم الأدمن\n\nاختر من القائمة:", reply_markup=admin_keyboard())
        return

    if not await is_verified(uid):
        await update.message.reply_text(
            "مرحباً بكم في BAMSPX 🤝\n\nيُرجى تقديم رقم الهاتف المحمول للمتابعة واختيار باقة الاشتراك المناسبة 📱✨",
            reply_markup=phone_keyboard(),
        )
        return

    await update.message.reply_text("اختر من القائمة 👇", reply_markup=main_keyboard())


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact
    uid = str(user.id)

    if contact.user_id != user.id:
        await update.message.reply_text("⚠️ يرجى مشاركة رقم جوالك الخاص فقط.", reply_markup=phone_keyboard())
        return

    await save_verified(uid, contact.phone_number, user.full_name, user.username or "")
    await update.message.reply_text("✅ تم التحقق بنجاح", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("اختر من القائمة 👇", reply_markup=main_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user
    uid = str(user.id)
    admin_id = await get_admin()
    is_admin = uid == str(admin_id)

    if not is_admin and not await is_verified(uid) and not data.startswith(("approve_", "reject_", "channel_verify")):
        await query.answer("يرجى إرسال /start أولاً.", show_alert=True)
        return

    if data == "admin_back":
        if not is_admin:
            return
        await query.edit_message_text("👑 لوحة تحكم الأدمن\n\nاختر من القائمة:", reply_markup=admin_keyboard())

    elif data == "admin_verifypost":
        if not is_admin:
            return
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("ابدأ الاشتراك", url=SUPPORT_URL)]])
        await query.edit_message_text("✅ استخدم زر القناة العامة داخل البوت للنشر اليدوي عند الحاجة.", reply_markup=admin_keyboard())

    elif data == "admin_channelusers":
        if not is_admin:
            return
        count = await get_channel_users_count()
        await query.edit_message_text(f"👥 عدد المستخدمين المحفوظين: {count}", reply_markup=admin_keyboard())

    elif data == "admin_blast":
        if not is_admin:
            return
        context.user_data["awaiting_blast"] = True
        context.user_data.pop("awaiting_search", None)
        await query.edit_message_text("📨 أرسل نص الرسالة للكل:", reply_markup=back_admin_keyboard())

    elif data == "admin_search":
        if not is_admin:
            return
        context.user_data["awaiting_search"] = True
        context.user_data.pop("awaiting_blast", None)
        await query.edit_message_text("🔎 أرسل رقم الجوال أو اليوزر أو ID أو الاسم للبحث:", reply_markup=back_admin_keyboard())

    elif data == "admin_stats":
        if not is_admin:
            return
        total_users, active, expired, pending = await get_stats()
        text = (
            "📊 الإحصائيات\n\n"
            f"👥 المستخدمون الموثقون: {total_users}\n"
            f"✅ الاشتراكات النشطة: {active}\n"
            f"❌ الاشتراكات المنتهية: {expired}\n"
            f"📥 طلبات معلقة: {pending}"
        )
        await query.edit_message_text(text, reply_markup=admin_keyboard())

    elif data == "admin_checkexpired":
        if not is_admin:
            return
        removed = await remove_expired_users(context)
        await query.edit_message_text(f"✅ تم فحص المنتهين وإزالة {removed} مستخدم.", reply_markup=admin_keyboard())

    elif data == "subscribe":
        await query.edit_message_text("اختر الباقة المناسبة 👇", reply_markup=plans_keyboard())

    elif data.startswith("plan_"):
        key = data.replace("plan_", "")
        if key not in PLANS:
            await query.answer("خطة غير صحيحة", show_alert=True)
            return

        pending = await get_pending(uid)
        if pending and pending.get("status") == "receipt_sent":
            await query.answer("✅ تم إرسال إيصالك مسبقاً، يرجى انتظار مراجعة الإدارة.", show_alert=True)
            return

        plan = PLANS[key]
        phone = await get_verified_phone(uid)

        await save_pending(uid, key, user.full_name, user.username or "", phone, "awaiting_receipt")

        text = (
            f"📦 الباقة: {plan['label']}\n"
            f"💰 السعر: {plan['price']} ريال\n\n"
            "بيانات التحويل البنكي:\n"
            f"🏦 البنك: {BANK_NAME}\n"
            f"👤 الاسم: {ACCOUNT_NAME}\n"
            f"📌 الآيبان:\n{IBAN}\n\n"
            "بعد التحويل، أرسل صورة إيصال التحويل هنا."
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))

    elif data == "back_main":
        await query.edit_message_text("اختر من القائمة 👇", reply_markup=main_keyboard())

    elif data == "status":
        sub = await get_subscriber(uid)
        if not sub:
            text = "❌ لا يوجد اشتراك نشط"
        else:
            exp = datetime.fromisoformat(sub["expires_at"])
            remaining = exp - datetime.now()
            if remaining.total_seconds() <= 0:
                text = "❌ اشتراكك منتهي"
            else:
                plan_label = PLANS.get(sub.get("plan_key"), {}).get("label", sub.get("plan_key", "—"))
                text = (
                    "✅ اشتراكك فعال\n\n"
                    f"الباقة: {plan_label}\n"
                    f"ينتهي بتاريخ: {exp.strftime('%Y-%m-%d')}\n"
                    f"المتبقي: {remaining.days} يوم"
                )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
                ]
            ),
        )

    elif data.startswith("approve_"):
        if not is_admin:
            await query.answer("غير مصرح", show_alert=True)
            return

        _, target_uid, plan_key = data.split("_")
        if plan_key not in PLANS:
            await query.edit_message_text("خطة غير صحيحة")
            return

        plan = PLANS[plan_key]
        expires = datetime.now() + timedelta(days=plan["months"] * 30)

        await save_subscriber(target_uid, plan_key, expires)
        await delete_pending(target_uid)

        try:
            link = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                expire_date=int((datetime.now() + timedelta(minutes=5)).timestamp()),
                name=f"sub_{target_uid}",
                creates_join_request=False,
            )
            await context.bot.send_message(chat_id=int(target_uid), text=link.invite_link)
            await query.edit_message_text("✅ تم قبول الاشتراك وإرسال رابط الدخول لمدة 5 دقائق.")
        except Exception as e:
            logger.error(f"Invite link error: {e}")
            await query.edit_message_text("✅ تم قبول الاشتراك لكن فشل توليد الرابط. تأكد أن البوت أدمن في القناة الخاصة.")

    elif data.startswith("reject_"):
        if not is_admin:
            await query.answer("غير مصرح", show_alert=True)
            return
        target_uid = data.replace("reject_", "")
        await delete_pending(target_uid)
        try:
            await context.bot.send_message(chat_id=int(target_uid), text="❌ تم رفض الإيصال")
        except Exception:
            pass
        await query.edit_message_text("❌ تم رفض الطلب")


async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    admin_id = await get_admin()

    if uid == str(admin_id) and context.user_data.get("awaiting_blast") and update.message.text:
        context.user_data.pop("awaiting_blast", None)
        users = await get_all_channel_users()
        sent_ok = sent_err = 0
        for row in users:
            try:
                await context.bot.send_message(chat_id=int(row["uid"]), text=update.message.text, protect_content=True)
                sent_ok += 1
            except Exception:
                sent_err += 1
        await update.message.reply_text(f"✅ تم الإرسال لـ {sent_ok} | ❌ فشل {sent_err}", reply_markup=admin_keyboard())
        return

    if uid == str(admin_id) and context.user_data.get("awaiting_search") and update.message.text:
        context.user_data.pop("awaiting_search", None)
        results = await search_users(update.message.text)
        if not results:
            await update.message.reply_text("لا توجد نتائج.", reply_markup=admin_keyboard())
            return

        lines = ["🔎 نتائج البحث:\n"]
        for u in results:
            sub = await get_subscriber(u["uid"])
            status = "غير مشترك"
            if sub:
                try:
                    exp = datetime.fromisoformat(sub["expires_at"])
                    status = "نشط" if exp > datetime.now() else "منتهي"
                except Exception:
                    status = "غير معروف"
            lines.append(
                f"👤 {u.get('full_name','—')}\n"
                f"@{u.get('username','—')}\n"
                f"📱 {u.get('phone','—')}\n"
                f"🆔 {u.get('uid','—')}\n"
                f"الحالة: {status}\n"
            )

        await update.message.reply_text("\n".join(lines), reply_markup=admin_keyboard())
        return

    if not await is_verified(uid):
        await update.message.reply_text("يرجى إرسال /start أولاً.")
        return

    pending = await get_pending(uid)
    if not pending:
        return

    if pending.get("status") == "receipt_sent":
        await update.message.reply_text("✅ تم استلام إيصالك مسبقاً، يرجى انتظار مراجعة الإدارة.")
        return

    if not admin_id:
        await update.message.reply_text("تواصل مع الدعم.")
        return

    plan = PLANS[pending["plan_key"]]
    phone = await get_verified_phone(uid)
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ قبول وإرسال الرابط", callback_data=f"approve_{uid}_{pending['plan_key']}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_{uid}"),
            ]
        ]
    )
    caption = (
        "📥 طلب اشتراك جديد\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"📱 الجوال: {phone}\n"
        f"🆔 ID: {uid}\n"
        f"📦 الباقة: {plan['label']}\n"
        f"💰 السعر: {plan['price']} ريال\n"
        f"🕐 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    if update.message.photo:
        await context.bot.send_photo(
            chat_id=int(admin_id),
            photo=update.message.photo[-1].file_id,
            caption=caption,
            reply_markup=kb,
            protect_content=True,
        )
    elif update.message.document:
        await context.bot.send_document(
            chat_id=int(admin_id),
            document=update.message.document.file_id,
            caption=caption,
            reply_markup=kb,
            protect_content=True,
        )
    else:
        await update.message.reply_text("📎 أرسل صورة إيصال التحويل من فضلك.")
        return

    await update_pending_status(uid, "receipt_sent")
    await update.message.reply_text("✅ تم استلام الإيصال")


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admin_id = await get_admin()

    if admin_id is None:
        await set_admin(uid)
        await update.message.reply_text(f"✅ تم تسجيلك كأدمن\nID: {uid}", reply_markup=admin_keyboard())
    elif uid == str(admin_id):
        await update.message.reply_text("👑 لوحة تحكم الأدمن\n\nاختر من القائمة:", reply_markup=admin_keyboard())
    else:
        await update.message.reply_text("غير مصرح.")


async def forceadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    await set_admin(uid)
    await update.message.reply_text(f"✅ تم تعيينك كأدمن\nID: {uid}", reply_markup=admin_keyboard())


async def remove_expired_users(context: ContextTypes.DEFAULT_TYPE):
    expired = await get_all_expired()
    removed = 0

    for row in expired:
        uid = row["uid"]
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
            await context.bot.send_message(
                chat_id=int(uid),
                text="⏰ انتهى اشتراكك في BAMSPX",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")]]),
            )
            removed += 1
        except Exception as e:
            logger.error(f"Remove expired error {uid}: {e}")

        await delete_subscriber(uid)

    return removed


async def check_expired(context: ContextTypes.DEFAULT_TYPE):
    await remove_expired_users(context)


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    subscribers = await get_all_active_subscribers()

    for sub in subscribers:
        uid = sub["uid"]
        try:
            exp = datetime.fromisoformat(sub["expires_at"])
            left = exp - datetime.now()

            if left.total_seconds() <= 0:
                continue

            if left <= timedelta(days=3) and not sub.get("reminder_3d_sent"):
                await context.bot.send_message(
                    chat_id=int(uid),
                    text="⏰ اشتراكك في BAMSPX سينتهي خلال 3 أيام",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")]]),
                )
                await mark_reminder(uid, "3d")

            if left <= timedelta(days=1) and not sub.get("reminder_1d_sent"):
                await context.bot.send_message(
                    chat_id=int(uid),
                    text="⚠️ تبقى أقل من 24 ساعة على انتهاء اشتراكك في BAMSPX",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")]]),
                )
                await mark_reminder(uid, "1d")
        except Exception as e:
            logger.error(f"Reminder error {uid}: {e}")


async def protect_private_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # يحذف رسائل دخول/خروج النظام، ويطرد أي عضو غير مشترك نشط إذا دخل القناة الخاصة.
    msg = update.message
    if not msg:
        return

    try:
        if msg.new_chat_members:
            for member in msg.new_chat_members:
                if member.is_bot:
                    continue

                sub = await get_subscriber(str(member.id))
                if not is_active_sub(sub):
                    await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=member.id)
                    await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=member.id)
                else:
                    await save_channel_user(str(member.id), member.full_name, member.username or "")

        await msg.delete()
    except Exception as e:
        logger.error(f"Protect channel error: {e}")


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("forceadmin", forceadmin_cmd))

    app.add_handler(MessageHandler(filters.CONTACT, receive_contact))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(
        MessageHandler(
            filters.Chat(chat_id=CHANNEL_ID)
            & (
                filters.StatusUpdate.NEW_CHAT_MEMBERS
                | filters.StatusUpdate.LEFT_CHAT_MEMBER
                | filters.StatusUpdate.NEW_CHAT_TITLE
                | filters.StatusUpdate.NEW_CHAT_PHOTO
                | filters.StatusUpdate.PINNED_MESSAGE
            ),
            protect_private_channel,
        )
    )

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, receive_message))

    app.job_queue.run_repeating(check_expired, interval=3600, first=10)
    app.job_queue.run_repeating(check_reminders, interval=3600, first=30)

    print("BAMSPX bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
