import os
import json
import logging
import asyncpg
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
DATABASE_URL   = os.environ["DATABASE_URL"]
CHANNEL_ID     = -1003618409425
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

# ── DB helpers ──
async def get_db():
    return await asyncpg.connect(DATABASE_URL)

async def get_admin():
    db = await get_db()
    try:
        row = await db.fetchrow("SELECT value FROM settings WHERE key='admin_id'")
        return row["value"] if row else None
    finally:
        await db.close()

async def set_admin(uid):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO settings(key,value) VALUES('admin_id',$1)
            ON CONFLICT(key) DO UPDATE SET value=$1
        """, str(uid))
    finally:
        await db.close()

async def is_verified(uid):
    db = await get_db()
    try:
        return await db.fetchrow("SELECT uid FROM verified WHERE uid=$1", str(uid)) is not None
    finally:
        await db.close()

async def save_verified(uid, phone, full_name, username):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO verified(uid,phone,full_name,username,verified_at)
            VALUES($1,$2,$3,$4,$5)
            ON CONFLICT(uid) DO UPDATE SET phone=$2,full_name=$3,username=$4
        """, str(uid), phone, full_name, username, datetime.now())
    finally:
        await db.close()

async def get_subscriber(uid):
    db = await get_db()
    try:
        return await db.fetchrow("SELECT * FROM subscribers WHERE uid=$1", str(uid))
    finally:
        await db.close()

async def save_subscriber(uid, plan_key, expires_at, is_trial=False):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO subscribers(uid,plan_key,expires_at,activated_at,is_trial)
            VALUES($1,$2,$3,$4,$5)
            ON CONFLICT(uid) DO UPDATE SET plan_key=$2,expires_at=$3,is_trial=$5
        """, str(uid), plan_key, expires_at, datetime.now(), is_trial)
    finally:
        await db.close()

async def delete_subscriber(uid):
    db = await get_db()
    try:
        await db.execute("DELETE FROM subscribers WHERE uid=$1", str(uid))
    finally:
        await db.close()

async def used_trial(uid):
    db = await get_db()
    try:
        return await db.fetchrow("SELECT uid FROM trials WHERE uid=$1", str(uid)) is not None
    finally:
        await db.close()

async def save_trial(uid, expires_at):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO trials(uid,started_at,expires_at) VALUES($1,$2,$3)
            ON CONFLICT(uid) DO NOTHING
        """, str(uid), datetime.now(), expires_at)
    finally:
        await db.close()

async def get_pending(uid):
    db = await get_db()
    try:
        return await db.fetchrow("SELECT * FROM pending WHERE uid=$1", str(uid))
    finally:
        await db.close()

async def save_pending(uid, plan_key, full_name, username, phone, status):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO pending(uid,plan_key,full_name,username,phone,status,requested_at)
            VALUES($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT(uid) DO UPDATE SET plan_key=$2,status=$6
        """, str(uid), plan_key, full_name, username, phone, status, datetime.now())
    finally:
        await db.close()

async def update_pending_status(uid, status):
    db = await get_db()
    try:
        await db.execute("UPDATE pending SET status=$1 WHERE uid=$2", status, str(uid))
    finally:
        await db.close()

async def delete_pending(uid):
    db = await get_db()
    try:
        await db.execute("DELETE FROM pending WHERE uid=$1", str(uid))
    finally:
        await db.close()

async def get_all_expired():
    db = await get_db()
    try:
        return await db.fetch("SELECT * FROM subscribers WHERE expires_at <= $1", datetime.now())
    finally:
        await db.close()

async def get_stats():
    db = await get_db()
    try:
        total_users  = await db.fetchval("SELECT COUNT(*) FROM verified")
        total_trials = await db.fetchval("SELECT COUNT(*) FROM trials")
        active_subs  = await db.fetchval("SELECT COUNT(*) FROM subscribers WHERE is_trial=FALSE AND expires_at > $1", datetime.now())
        expired_subs = await db.fetchval("SELECT COUNT(*) FROM subscribers WHERE is_trial=FALSE AND expires_at <= $1", datetime.now())
        return total_users, total_trials, active_subs, expired_subs
    finally:
        await db.close()

async def save_channel_user(uid, name, username):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO channel_users(uid,name,username,joined)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(uid) DO NOTHING
        """, str(uid), name, username, datetime.now())
    finally:
        await db.close()

async def get_channel_users_count():
    db = await get_db()
    try:
        return await db.fetchval("SELECT COUNT(*) FROM channel_users")
    finally:
        await db.close()

async def get_all_channel_users():
    db = await get_db()
    try:
        return await db.fetch("SELECT uid FROM channel_users")
    finally:
        await db.close()

async def get_verified_phone(uid):
    db = await get_db()
    try:
        row = await db.fetchrow("SELECT phone FROM verified WHERE uid=$1", str(uid))
        return row["phone"] if row else "—"
    finally:
        await db.close()

# ── Keyboards ──
def phone_keyboard():
    btn = KeyboardButton("📱 مشاركة رقم جوالي", request_contact=True)
    return ReplyKeyboardMarkup([[btn]], resize_keyboard=True, one_time_keyboard=True)

def plans_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📦 {p['label']} — {p['price']} ريال", callback_data=f"plan_{k}")]
        for k, p in PLANS.items()
    ])

def main_keyboard(show_trial=False):
    buttons = []
    if show_trial:
        buttons.append([InlineKeyboardButton("🎁 تجربة مجانية 48 ساعة", callback_data="trial")])
    buttons.append([InlineKeyboardButton("🛒 اشتراك جديد",       callback_data="subscribe")])
    buttons.append([InlineKeyboardButton("🔄 تجديد الاشتراك",    callback_data="subscribe")])
    buttons.append([InlineKeyboardButton("📊 حالة اشتراكي",      callback_data="status")])
    buttons.append([InlineKeyboardButton("💬 التواصل مع الدعم",  url=f"https://t.me/{SUPPORT_USER}")])
    return InlineKeyboardMarkup(buttons)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 نشر رسالة التحقق في القناة", callback_data="admin_verifypost")],
        [InlineKeyboardButton("👥 عدد المشتركين المحفوظين",   callback_data="admin_channelusers")],
        [InlineKeyboardButton("📨 إرسال رسالة للكل",          callback_data="admin_blast")],
        [InlineKeyboardButton("📊 الإحصائيات",                callback_data="admin_stats")],
        [InlineKeyboardButton("🗑 فحص المنتهين وإزالتهم",     callback_data="admin_checkexpired")],
    ])

# ── Handlers ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = str(user.id)
    admin_id = await get_admin()

    if str(user.id) == str(admin_id):
        await update.message.reply_text(
            "👑 *لوحة تحكم الأدمن*\n\nاختر من القائمة:",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )
        return

    if await is_verified(uid):
        trial_used = await used_trial(uid)
        sub        = await get_subscriber(uid)
        show_trial = not trial_used and not sub
        await update.message.reply_text(
            f"أهلاً {user.first_name}! 👋\n\n"
            "مرحباً بك في قناة *عقود الأوبشن* 📈\n\n"
            "اشترك الآن للحصول على:\n"
            "• ✅ إشارات يومية احترافية\n"
            "• 📊 تحليلات دقيقة لعقود الأوبشن\n"
            "• 🔔 تنبيهات فورية\n\n"
            "اختر من القائمة:",
            parse_mode="Markdown",
            reply_markup=main_keyboard(show_trial=show_trial)
        )
    else:
        await update.message.reply_text(
            f"أهلاً {user.first_name}! 👋\n\n"
            "للمتابعة نحتاج التحقق من هويتك.\n\n"
            "📱 اضغط الزر أدناه لمشاركة رقم جوالك:",
            parse_mode="Markdown",
            reply_markup=phone_keyboard()
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

    trial_used = await used_trial(uid)
    await update.message.reply_text(
        "مرحباً بك في قناة *عقود الأوبشن* 📈\n\n"
        "اشترك الآن للحصول على:\n"
        "• ✅ إشارات يومية احترافية\n"
        "• 📊 تحليلات دقيقة لعقود الأوبشن\n"
        "• 🔔 تنبيهات فورية\n\n"
        "اختر من القائمة:",
        parse_mode="Markdown",
        reply_markup=main_keyboard(show_trial=not trial_used)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    data     = query.data
    user     = query.from_user
    uid      = str(user.id)
    admin_id = await get_admin()
    is_admin = str(user.id) == str(admin_id)

    if not is_admin and not await is_verified(uid) and not data.startswith(("approve_", "reject_")):
        await query.answer("يرجى إرسال /start أولاً للتحقق من رقمك.", show_alert=True)
        return

    # ── Admin Panel ──
    if data == "admin_verifypost":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("تحقق خلال ثانية 👌", callback_data="channel_verify")]])
        await context.bot.send_message(chat_id=-1001934800979, text="اضغط الزر أدناه للتحقق 👇", reply_markup=kb)
        await query.edit_message_text("✅ تم نشر رسالة التحقق في القناة", reply_markup=admin_keyboard())

    elif data == "admin_channelusers":
        count = await get_channel_users_count()
        await query.edit_message_text(f"👥 *المشتركون المحفوظون:* {count} شخص", parse_mode="Markdown", reply_markup=admin_keyboard())

    elif data == "admin_blast":
        context.user_data["awaiting_blast"] = True
        await query.edit_message_text(
            "📨 أرسل نص الرسالة اللي تبغى ترسلها للكل:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_cancel")]])
        )

    elif data == "admin_stats":
        total_users, total_trials, active_subs, expired_subs = await get_stats()
        text = (
            "📊 *الإحصائيات*\n\n"
            f"👥 إجمالي المستخدمين: {total_users}\n"
            f"🎁 استخدموا التجربة: {total_trials}\n"
            f"✅ مشتركون نشطون: {active_subs}\n"
            f"❌ اشتراكات منتهية: {expired_subs}"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())

    elif data == "admin_checkexpired":
        expired = await get_all_expired()
        removed = 0
        for row in expired:
            try:
                await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(row["uid"]))
                await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(row["uid"]))
                msg = (
                    "⏰ *انتهت فترة التجربة المجانية*\n\nتم إزالتك من القناة.\nاشترك الآن للاستمرار 👇"
                ) if row["is_trial"] else (
                    "⏰ *انتهى اشتراكك*\n\nتم إزالتك من القناة تلقائياً.\nجدّد اشتراكك للاستمرار 👇"
                )
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

        expires     = datetime.now() + timedelta(hours=48)
        expires_str = expires.strftime('%Y/%m/%d الساعة %H:%M')
        await save_trial(uid, expires)
        await save_subscriber(uid, "trial", expires, is_trial=True)

        await query.edit_message_text(
            f"🎁 *تم تفعيل فترة التجربة المجانية!*\n\n• المدة: 48 ساعة\n• تنتهي في: {expires_str}\n\n⏳ سيتم إضافتك للقناة خلال دقائق.",
            parse_mode="Markdown"
        )

        try:
            link = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID, member_limit=1,
                expire_date=int((datetime.now() + timedelta(minutes=5)).timestamp()),
                name=f"trial_{uid}"
            )
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"🔗 *رابط دخولك للقناة:*\n{link.invite_link}\n\n⚠️ الرابط صالح لمدة *5 دقائق* فقط.\nادخل القناة الآن! ⏰",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Trial invite error: {e}")

        if admin_id:
            phone = await get_verified_phone(uid)
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🎁 *فترة تجربة جديدة*\n\n👤 {user.full_name}\n📱 {phone}\n🆔 `{uid}`\n⏰ تنتهي: {expires_str}",
                parse_mode="Markdown"
            )

    elif data.startswith("plan_"):
        key  = data.replace("plan_", "")
        plan = PLANS[key]
        phone = await get_verified_phone(uid)
        await save_pending(uid, key, user.full_name, user.username or "", phone, "awaiting_receipt")
        await query.edit_message_text(
            f"✅ اخترت خطة *{plan['label']}* بـ {plan['price']} ريال\n\n"
            f"💳 *بيانات التحويل البنكي:*\n• البنك: {BANK_NAME}\n• الاسم: {ACCOUNT_NAME}\n• الآيبان: `{IBAN}`\n\n"
            f"📌 *بعد التحويل:*\nأرسل صورة إيصال التحويل هنا وسيتم مراجعتها خلال دقائق.\n\n⚠️ تأكد أن اسمك ظاهر في الإيصال.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])
        )

    elif data == "back_main":
        trial_used = await used_trial(uid)
        sub        = await get_subscriber(uid)
        show_trial = not trial_used and not sub
        await query.edit_message_text(
            "مرحباً بك في قناة *عقود الأوبشن* 📈\n\nاختر من القائمة:",
            parse_mode="Markdown",
            reply_markup=main_keyboard(show_trial=show_trial)
        )

    elif data == "status":
        sub = await get_subscriber(uid)
        if sub:
            exp       = sub["expires_at"]
            remaining = exp - datetime.now()
            if remaining.total_seconds() > 0:
                if sub["is_trial"]:
                    hours = int(remaining.total_seconds() // 3600)
                    mins  = int((remaining.total_seconds() % 3600) // 60)
                    text  = f"🎁 *فترة التجربة المجانية فعّالة*\n\n• تنتهي في: {exp.strftime('%Y/%m/%d %H:%M')}\n• المتبقي: {hours} ساعة و{mins} دقيقة\n\nاشترك الآن للاستمرار 👇"
                else:
                    plan_label = PLANS.get(sub["plan_key"], {}).get("label", sub["plan_key"])
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
        parts    = data.split("_")
        t_uid    = parts[1]
        plan_key = parts[2]
        plan     = PLANS[plan_key]
        expires  = datetime.now() + timedelta(days=plan["months"] * 30)
        await save_subscriber(t_uid, plan_key, expires, is_trial=False)
        await delete_pending(t_uid)
        invite_url = None
        try:
            link = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID, member_limit=1,
                expire_date=int(expires.timestamp()), name=f"sub_{t_uid}"
            )
            invite_url = link.invite_link
        except Exception as e:
            logger.error(f"Invite link error: {e}")

        if invite_url:
            msg        = f"🎉 *تم تأكيد اشتراكك!*\n\n• الخطة: {plan['label']}\n• ينتهي في: {expires.strftime('%Y/%m/%d')}\n\n🔗 *رابط دخولك الخاص:*\n{invite_url}\n\n⚠️ هذا الرابط خاص بك فقط ويُستخدم مرة واحدة."
            admin_note = f"✅ تم قبول `{t_uid}` — {plan['label']}\n🔗 تم إرسال الرابط"
        else:
            msg        = f"🎉 *تم تأكيد اشتراكك!*\n\n• الخطة: {plan['label']}\n• ينتهي في: {expires.strftime('%Y/%m/%d')}\n\n⏳ سيتم إضافتك للقناة خلال دقائق."
            admin_note = f"✅ تم قبول `{t_uid}` — {plan['label']}\n⚠️ فشل توليد الرابط"

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

async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = str(user.id)

    # Blast handler for admin
    admin_id = await get_admin()
    if str(user.id) == str(admin_id) and context.user_data.get("awaiting_blast"):
        context.user_data.pop("awaiting_blast", None)
        msg      = update.message.text or ""
        users    = await get_all_channel_users()
        sent_ok  = 0
        sent_err = 0
        for row in users:
            try:
                await context.bot.send_message(chat_id=int(row["uid"]), text=msg)
                sent_ok += 1
            except:
                sent_err += 1
        await update.message.reply_text(f"✅ تم الإرسال لـ {sent_ok} شخص | ❌ فشل {sent_err}", reply_markup=admin_keyboard())
        return

    if not await is_verified(uid):
        await update.message.reply_text("📌 أرسل /start أولاً للتحقق من رقمك.")
        return

    pending = await get_pending(uid)
    if not pending or pending["status"] not in ("awaiting_receipt", "receipt_sent"):
        await update.message.reply_text("📌 لا يوجد طلب اشتراك مفتوح.\nاضغط /start للبدء.")
        return

    if not admin_id:
        await update.message.reply_text("⚠️ تواصل مع الدعم مباشرة.")
        return

    plan     = PLANS[pending["plan_key"]]
    plan_key = pending["plan_key"]
    phone    = await get_verified_phone(uid)
    caption  = (
        f"📥 *طلب اشتراك جديد*\n\n👤 الاسم: {user.full_name}\n📱 الجوال: `{phone}`\n"
        f"🆔 ID: `{uid}`\n📦 الخطة: {plan['label']} — {plan['price']} ريال\n"
        f"🕐 الوقت: {datetime.now().strftime('%Y/%m/%d %H:%M')}"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول وإرسال رابط", callback_data=f"approve_{uid}_{plan_key}"),
        InlineKeyboardButton("❌ رفض",               callback_data=f"reject_{uid}"),
    ]])

    if update.message.photo:
        await context.bot.send_photo(chat_id=admin_id, photo=update.message.photo[-1].file_id, caption=caption, parse_mode="Markdown", reply_markup=kb)
    elif update.message.document:
        await context.bot.send_document(chat_id=admin_id, document=update.message.document.file_id, caption=caption, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text("📎 أرسل صورة الإيصال من فضلك.")
        return

    await update_pending_status(uid, "receipt_sent")
    await update.message.reply_text("✅ *تم استلام إيصالك!*\n\nسيتم مراجعته وتفعيل اشتراكك خلال دقائق. 🙏", parse_mode="Markdown")

async def forceadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await set_admin(uid)
    await update.message.reply_text(f"✅ تم تسجيلك كأدمن!\nID: `{uid}`", parse_mode="Markdown")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid      = update.effective_user.id
    admin_id = await get_admin()
    if admin_id is None:
        await set_admin(uid)
        await update.message.reply_text(f"✅ تم تسجيلك كأدمن!\nID: `{uid}`", parse_mode="Markdown")
    elif str(uid) == str(admin_id):
        await update.message.reply_text(f"✅ أنت الأدمن.\nID: `{uid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⛔ أدمن مسجّل مسبقاً.")

async def reset_trial_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = await get_admin()
    if str(update.effective_user.id) != str(admin_id):
        return
    uid = str(update.effective_user.id)
    db  = await get_db()
    try:
        await db.execute("DELETE FROM trials WHERE uid=$1", uid)
        await db.execute("DELETE FROM subscribers WHERE uid=$1", uid)
    finally:
        await db.close()
    await update.message.reply_text("✅ تم مسح التجربة — أرسل /start مجدداً")

async def check_expired(context: ContextTypes.DEFAULT_TYPE):
    expired = await get_all_expired()
    for row in expired:
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(row["uid"]))
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(row["uid"]))
            msg = (
                "⏰ *انتهت فترة التجربة المجانية*\n\nتم إزالتك من القناة.\nاشترك الآن للاستمرار 👇"
            ) if row["is_trial"] else (
                "⏰ *انتهى اشتراكك*\n\nتم إزالتك من القناة تلقائياً.\nجدّد اشتراكك للاستمرار 👇"
            )
            await context.bot.send_message(chat_id=int(row["uid"]), text=msg, parse_mode="Markdown", reply_markup=main_keyboard())
        except Exception as e:
            logger.error(f"Error removing {row['uid']}: {e}")
        await delete_subscriber(row["uid"])

async def delete_system_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Could not delete system message: {e}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("admin",       admin_cmd))
    app.add_handler(CommandHandler("forceadmin",  forceadmin_cmd))
    app.add_handler(CommandHandler("reset_trial", reset_trial_cmd))
    app.add_handler(MessageHandler(filters.CONTACT, receive_contact))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, receive_receipt))
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS |
        filters.StatusUpdate.LEFT_CHAT_MEMBER |
        filters.StatusUpdate.NEW_CHAT_TITLE |
        filters.StatusUpdate.NEW_CHAT_PHOTO |
        filters.StatusUpdate.PINNED_MESSAGE,
        delete_system_messages
    ))
    app.job_queue.run_repeating(check_expired, interval=3600, first=10)
    print("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
