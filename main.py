import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from db import (
    get_setting, set_setting, is_verified, save_verified, get_verified_phone,
    get_subscriber, save_subscriber, delete_subscriber, get_all_expired,
    used_trial, save_trial, get_pending, save_pending, update_pending_status, delete_pending,
    save_channel_user, get_channel_users_count, get_all_channel_users, get_stats
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID     = -1003618409425
PUBLIC_CHANNEL = -1001934800979
SUPPORT_USER   = "BAMSPX"

BANK_NAME    = "البنك الأهلي السعودي"
ACCOUNT_NAME = "بدر محمد الجعيد"
IBAN         = "SA7010000088050617000103"

PLANS = {
    "1m":  {"label": "شهري",   "months": 1,  "price": 200},
    "3m":  {"label": "3 أشهر", "months": 3,  "price": 500},
    "6m":  {"label": "6 أشهر", "months": 6,  "price": 1000},
    "12m": {"label": "سنوي",   "months": 12, "price": 1500},
}

async def get_admin():
    return await get_setting("admin_id")

async def set_admin(uid):
    await set_setting("admin_id", uid)

def phone_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("📱 مشاركة رقم جوالي", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)

def plans_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"📦 {p['label']} — {p['price']} ريال", callback_data=f"plan_{k}")] for k,p in PLANS.items()])

def main_keyboard(show_trial=False):
    b = []
    if show_trial:
        b.append([InlineKeyboardButton("🎁 تجربة مجانية 48 ساعة", callback_data="trial")])
    b.append([InlineKeyboardButton("🛒 اشتراك جديد",      callback_data="subscribe")])
    b.append([InlineKeyboardButton("🔄 تجديد الاشتراك",   callback_data="subscribe")])
    b.append([InlineKeyboardButton("📊 حالة اشتراكي",     callback_data="status")])
    b.append([InlineKeyboardButton("💬 التواصل مع الدعم", url=f"https://t.me/{SUPPORT_USER}")])
    return InlineKeyboardMarkup(b)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 نشر رسالة التحقق في القناة", callback_data="admin_verifypost")],
        [InlineKeyboardButton("👥 عدد المشتركين المحفوظين",   callback_data="admin_channelusers")],
        [InlineKeyboardButton("📨 إرسال رسالة للكل",          callback_data="admin_blast")],
        [InlineKeyboardButton("📊 الإحصائيات",                callback_data="admin_stats")],
        [InlineKeyboardButton("🗑 فحص المنتهين وإزالتهم",     callback_data="admin_checkexpired")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    uid      = str(user.id)
    admin_id = await get_admin()

    if uid == str(admin_id):
        await update.message.reply_text("👑 *لوحة تحكم الأدمن*\n\nاختر من القائمة:", parse_mode="Markdown", reply_markup=admin_keyboard())
        return

    if await is_verified(uid):
        show_trial = not await used_trial(uid) and not await get_subscriber(uid)
        await update.message.reply_text(
            f"أهلاً {user.first_name}! 👋\n\nمرحباً بك في قناة *عقود الأوبشن* 📈\n\nاشترك الآن للحصول على:\n• ✅ إشارات يومية احترافية\n• 📊 تحليلات دقيقة\n• 🔔 تنبيهات فورية\n\nاختر من القائمة:",
            parse_mode="Markdown", reply_markup=main_keyboard(show_trial=show_trial)
        )
    else:
        await update.message.reply_text(
            f"أهلاً {user.first_name}! 👋\n\nللمتابعة نحتاج التحقق من هويتك.\n\n📱 اضغط الزر أدناه:",
            parse_mode="Markdown", reply_markup=phone_keyboard()
        )

async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    contact = update.message.contact
    uid     = str(user.id)
    if contact.user_id != user.id:
        await update.message.reply_text("⚠️ يرجى مشاركة رقم جوالك الخاص فقط.", reply_markup=phone_keyboard())
        return
    await save_verified(uid, contact.phone_number, user.full_name, user.username or "")
    await update.message.reply_text("✅ *تم التحقق بنجاح!*\n\nأهلاً بك 🎉", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    show_trial = not await used_trial(uid)
    await update.message.reply_text(
        "مرحباً بك في قناة *عقود الأوبشن* 📈\n\nاشترك الآن للحصول على:\n• ✅ إشارات يومية احترافية\n• 📊 تحليلات دقيقة\n• 🔔 تنبيهات فورية\n\nاختر من القائمة:",
        parse_mode="Markdown", reply_markup=main_keyboard(show_trial=show_trial)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    data     = query.data
    user     = query.from_user
    uid      = str(user.id)
    admin_id = await get_admin()
    is_admin = uid == str(admin_id)

    if not is_admin and not await is_verified(uid) and not data.startswith(("approve_","reject_")):
        await query.answer("يرجى إرسال /start أولاً.", show_alert=True)
        return

    if data == "admin_verifypost":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("تحقق خلال ثانية 👌", callback_data="channel_verify")]])
        await context.bot.send_message(chat_id=PUBLIC_CHANNEL, text="اضغط الزر أدناه للتحقق 👇", reply_markup=kb)
        await query.edit_message_text("✅ تم نشر رسالة التحقق في القناة", reply_markup=admin_keyboard())

    elif data == "admin_channelusers":
        count = await get_channel_users_count()
        await query.edit_message_text(f"👥 *المشتركون المحفوظون:* {count} شخص", parse_mode="Markdown", reply_markup=admin_keyboard())

    elif data == "admin_blast":
        context.user_data["awaiting_blast"] = True
        await query.edit_message_text("📨 أرسل نص الرسالة للكل:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_cancel")]]))

    elif data == "admin_stats":
        total_users, total_trials, active, expired = await get_stats()
        text = f"📊 *الإحصائيات*\n\n👥 إجمالي المستخدمين: {total_users}\n🎁 استخدموا التجربة: {total_trials}\n✅ مشتركون نشطون: {active}\n❌ اشتراكات منتهية: {expired}"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())

    elif data == "admin_checkexpired":
        expired_list = await get_all_expired()
        removed = 0
        for row in expired_list:
            try:
                await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(row["uid"]))
                await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(row["uid"]))
                msg = "⏰ *انتهت فترة التجربة المجانية*\n\nتم إزالتك من القناة.\nاشترك الآن للاستمرار 👇" if row["is_trial"] else "⏰ *انتهى اشتراكك*\n\nتم إزالتك من القناة تلقائياً.\nجدّد اشتراكك للاستمرار 👇"
                await context.bot.send_message(chat_id=int(row["uid"]), text=msg, parse_mode="Markdown", reply_markup=main_keyboard())
                removed += 1
            except Exception as e:
                logger.error(f"Error removing {row['uid']}: {e}")
            await delete_subscriber(row["uid"])
        await query.edit_message_text(f"✅ تم إزالة {removed} مشترك منتهٍ.", reply_markup=admin_keyboard())

    elif data == "admin_cancel":
        context.user_data.pop("awaiting_blast", None)
        await query.edit_message_text("✅ تم الإلغاء.", reply_markup=admin_keyboard())

    elif data == "channel_verify":
        await save_channel_user(uid, user.full_name, user.username or "")

    elif data == "subscribe":
        await query.edit_message_text("📦 *خطط الاشتراك*\n\nاختر الخطة المناسبة:", parse_mode="Markdown", reply_markup=plans_keyboard())

    elif data == "trial":
        if await used_trial(uid):
            await query.answer("⚠️ لقد استخدمت فترة التجربة المجانية مسبقاً.", show_alert=True)
            return
        if await get_subscriber(uid):
            await query.answer("✅ أنت مشترك بالفعل.", show_alert=True)
            return
        expires = datetime.now() + timedelta(hours=48)
        expires_str = expires.strftime('%Y/%m/%d الساعة %H:%M')
        await save_trial(uid, expires)
        await save_subscriber(uid, "trial", expires, is_trial=True)
        await query.edit_message_text(f"🎁 *تم تفعيل فترة التجربة المجانية!*\n\n• المدة: 48 ساعة\n• تنتهي في: {expires_str}\n\n⏳ سيتم إضافتك للقناة خلال دقائق.", parse_mode="Markdown")
        try:
            link = await context.bot.create_chat_invite_link(chat_id=CHANNEL_ID, member_limit=1, expire_date=int((datetime.now()+timedelta(minutes=5)).timestamp()), name=f"trial_{uid}")
            await context.bot.send_message(chat_id=int(uid), text=f"🔗 *رابط دخولك للقناة:*\n{link.invite_link}\n\n⚠️ الرابط صالح لمدة *5 دقائق* فقط.\nادخل القناة الآن! ⏰", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Trial invite error: {e}")
        if admin_id:
            phone = await get_verified_phone(uid)
            await context.bot.send_message(chat_id=admin_id, text=f"🎁 *فترة تجربة جديدة*\n\n👤 {user.full_name}\n📱 {phone}\n🆔 `{uid}`\n⏰ تنتهي: {expires_str}", parse_mode="Markdown")

    elif data.startswith("plan_"):
        key  = data.replace("plan_", "")
        plan = PLANS[key]
        phone = await get_verified_phone(uid)
        await save_pending(uid, key, user.full_name, user.username or "", phone, "awaiting_receipt")
        await query.edit_message_text(
            f"✅ اخترت خطة *{plan['label']}* بـ {plan['price']} ريال\n\n💳 *بيانات التحويل البنكي:*\n• البنك: {BANK_NAME}\n• الاسم: {ACCOUNT_NAME}\n• الآيبان: `{IBAN}`\n\n📌 *بعد التحويل:*\nأرسل صورة إيصال التحويل هنا وسيتم مراجعتها خلال دقائق.\n\n⚠️ تأكد أن اسمك ظاهر في الإيصال.",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])
        )

    elif data == "back_main":
        show_trial = not await used_trial(uid) and not await get_subscriber(uid)
        await query.edit_message_text("مرحباً بك في قناة *عقود الأوبشن* 📈\n\nاختر من القائمة:", parse_mode="Markdown", reply_markup=main_keyboard(show_trial=show_trial))

    elif data == "status":
        sub = await get_subscriber(uid)
        if sub:
            exp       = datetime.fromisoformat(sub["expires_at"])
            remaining = exp - datetime.now()
            if remaining.total_seconds() > 0:
                if sub["is_trial"]:
                    h = int(remaining.total_seconds()//3600); m = int((remaining.total_seconds()%3600)//60)
                    text = f"🎁 *فترة التجربة المجانية فعّالة*\n\n• تنتهي في: {exp.strftime('%Y/%m/%d %H:%M')}\n• المتبقي: {h} ساعة و{m} دقيقة\n\nاشترك الآن للاستمرار 👇"
                else:
                    plan_label = PLANS.get(sub["plan_key"],{}).get("label", sub["plan_key"])
                    text = f"✅ *اشتراكك فعّال*\n\n• الخطة: {plan_label}\n• ينتهي في: {exp.strftime('%Y/%m/%d')}\n• المتبقي: {remaining.days} يوم"
            else:
                text = "❌ اشتراكك منتهٍ. اشترك مجدداً للوصول للقناة."
        else:
            text = "❌ لا يوجد اشتراك نشط.\nاضغط *اشترك الآن* للبدء."
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))

    elif data.startswith("approve_"):
        if not is_admin:
            await query.answer("⛔ غير مصرح", show_alert=True)
            return
        parts = data.split("_"); t_uid = parts[1]; plan_key = parts[2]
        plan  = PLANS[plan_key]
        expires = datetime.now() + timedelta(days=plan["months"]*30)
        await save_subscriber(t_uid, plan_key, expires, is_trial=False)
        await delete_pending(t_uid)
        invite_url = None
        try:
            link = await context.bot.create_chat_invite_link(chat_id=CHANNEL_ID, member_limit=1, expire_date=int(expires.timestamp()), name=f"sub_{t_uid}")
            invite_url = link.invite_link
        except Exception as e:
            logger.error(f"Invite link error: {e}")
        msg = f"🎉 *تم تأكيد اشتراكك!*\n\n• الخطة: {plan['label']}\n• ينتهي في: {expires.strftime('%Y/%m/%d')}\n\n🔗 *رابط دخولك الخاص:*\n{invite_url}\n\n⚠️ هذا الرابط خاص بك فقط ويُستخدم مرة واحدة." if invite_url else f"🎉 *تم تأكيد اشتراكك!*\n\n• الخطة: {plan['label']}\n• ينتهي في: {expires.strftime('%Y/%m/%d')}\n\n⏳ سيتم إضافتك للقناة خلال دقائق."
        admin_note = f"✅ تم قبول `{t_uid}` — {plan['label']}\n🔗 تم إرسال الرابط" if invite_url else f"✅ تم قبول `{t_uid}` — {plan['label']}\n⚠️ فشل توليد الرابط"
        await context.bot.send_message(chat_id=int(t_uid), text=msg, parse_mode="Markdown")
        await query.edit_message_text(admin_note, parse_mode="Markdown")

    elif data.startswith("reject_"):
        if not is_admin:
            await query.answer("⛔ غير مصرح", show_alert=True)
            return
        t_uid = data.replace("reject_", "")
        await delete_pending(t_uid)
        await context.bot.send_message(chat_id=int(t_uid), text="❌ *تم رفض طلبك.*\n\nتأكد من صحة الإيصال وأعد الإرسال أو تواصل معنا.", parse_mode="Markdown")
        await query.edit_message_text(f"❌ تم رفض طلب `{t_uid}`", parse_mode="Markdown")

async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    uid      = str(user.id)
    admin_id = await get_admin()

    # Blast handler
    if uid == str(admin_id) and context.user_data.get("awaiting_blast") and update.message.text:
        context.user_data.pop("awaiting_blast", None)
        users = await get_all_channel_users()
        sent_ok = sent_err = 0
        for row in users:
            try:
                await context.bot.send_message(chat_id=int(row["uid"]), text=update.message.text)
                sent_ok += 1
            except:
                sent_err += 1
        await update.message.reply_text(f"✅ تم الإرسال لـ {sent_ok} شخص | ❌ فشل {sent_err}", reply_markup=admin_keyboard())
        return

    # Receipt handler
    if not await is_verified(uid):
        await update.message.reply_text("📌 أرسل /start أولاً للتحقق من رقمك.")
        return
    pending = await get_pending(uid)
    if not pending or pending["status"] not in ("awaiting_receipt","receipt_sent"):
        await update.message.reply_text("📌 لا يوجد طلب اشتراك مفتوح.\nاضغط /start للبدء.")
        return
    if not admin_id:
        await update.message.reply_text("⚠️ تواصل مع الدعم مباشرة.")
        return
    plan     = PLANS[pending["plan_key"]]
    plan_key = pending["plan_key"]
    phone    = await get_verified_phone(uid)
    caption  = f"📥 *طلب اشتراك جديد*\n\n👤 الاسم: {user.full_name}\n📱 الجوال: `{phone}`\n🆔 ID: `{uid}`\n📦 الخطة: {plan['label']} — {plan['price']} ريال\n🕐 الوقت: {datetime.now().strftime('%Y/%m/%d %H:%M')}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ قبول وإرسال رابط", callback_data=f"approve_{uid}_{plan_key}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_{uid}")]])
    if update.message.photo:
        await context.bot.send_photo(chat_id=admin_id, photo=update.message.photo[-1].file_id, caption=caption, parse_mode="Markdown", reply_markup=kb)
    elif update.message.document:
        await context.bot.send_document(chat_id=admin_id, document=update.message.document.file_id, caption=caption, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text("📎 أرسل صورة الإيصال من فضلك.")
        return
    await update_pending_status(uid, "receipt_sent")
    await update.message.reply_text("✅ *تم استلام إيصالك!*\n\nسيتم مراجعته وتفعيل اشتراكك خلال دقائق. 🙏", parse_mode="Markdown")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid      = str(update.effective_user.id)
    admin_id = await get_admin()
    if admin_id is None:
        await set_admin(uid)
        await update.message.reply_text(f"✅ تم تسجيلك كأدمن!\nID: `{uid}`", parse_mode="Markdown")
    elif uid == str(admin_id):
        await update.message.reply_text(f"✅ أنت الأدمن.\nID: `{uid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⛔ أدمن مسجّل مسبقاً.")

async def forceadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    await set_admin(uid)
    await update.message.reply_text(f"✅ تم تسجيلك كأدمن!\nID: `{uid}`", parse_mode="Markdown")

async def reset_trial_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = await get_admin()
    if str(update.effective_user.id) != str(admin_id):
        return
    uid = str(update.effective_user.id)
    from db import _delete
    await _delete("trials",      f"uid=eq.{uid}")
    await _delete("subscribers", f"uid=eq.{uid}")
    await update.message.reply_text("✅ تم مسح التجربة — أرسل /start مجدداً")

async def check_expired(context: ContextTypes.DEFAULT_TYPE):
    expired_list = await get_all_expired()
    for row in expired_list:
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(row["uid"]))
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(row["uid"]))
            msg = "⏰ *انتهت فترة التجربة المجانية*\n\nتم إزالتك من القناة.\nاشترك الآن للاستمرار 👇" if row["is_trial"] else "⏰ *انتهى اشتراكك*\n\nتم إزالتك من القناة تلقائياً.\nجدّد اشتراكك للاستمرار 👇"
            await context.bot.send_message(chat_id=int(row["uid"]), text=msg, parse_mode="Markdown", reply_markup=main_keyboard())
        except Exception as e:
            logger.error(f"Error removing {row['uid']}: {e}")
        await delete_subscriber(row["uid"])

async def delete_system_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("admin",       admin_cmd))
    app.add_handler(CommandHandler("forceadmin",  forceadmin_cmd))
    app.add_handler(CommandHandler("reset_trial", reset_trial_cmd))
    app.add_handler(MessageHandler(filters.CONTACT, receive_contact))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, receive_message))
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER |
        filters.StatusUpdate.NEW_CHAT_TITLE | filters.StatusUpdate.NEW_CHAT_PHOTO | filters.StatusUpdate.PINNED_MESSAGE,
        delete_system_messages
    ))
    app.job_queue.run_repeating(check_expired, interval=3600, first=10)
    print("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
