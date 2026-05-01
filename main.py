import os
import json
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, MenuButtonCommands, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
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

DB_FILE      = "db.json"
CHANNEL_USERS_FILE = "channel_users.json"

def load_channel_users():
    if os.path.exists(CHANNEL_USERS_FILE):
        with open(CHANNEL_USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_channel_users(data):
    with open(CHANNEL_USERS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"subscribers": {}, "pending": {}, "admin_id": None, "verified": {}, "trials": {}}

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_admin():
    return load_db().get("admin_id")

def set_admin(uid):
    db = load_db()
    db["admin_id"] = uid
    save_db(db)

def phone_keyboard():
    btn = KeyboardButton("📱 مشاركة رقم جوالي", request_contact=True)
    return ReplyKeyboardMarkup([[btn]], resize_keyboard=True, one_time_keyboard=True)

def plans_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📦 {p['label']} — {p['price']} ريال", callback_data=f"plan_{k}")]
        for k, p in PLANS.items()
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 نشر رسالة التحقق في القناة", callback_data="admin_verifypost")],
        [InlineKeyboardButton("👥 عدد المشتركين المحفوظين",   callback_data="admin_channelusers")],
        [InlineKeyboardButton("📨 إرسال رسالة للكل",          callback_data="admin_blast")],
        [InlineKeyboardButton("📊 الإحصائيات",                callback_data="admin_stats")],
        [InlineKeyboardButton("🗑 فحص المنتهين وإزالتهم",     callback_data="admin_checkexpired")],
    ])

def main_keyboard(show_trial=False):
    buttons = []
    if show_trial:
        buttons.append([InlineKeyboardButton("🎁 تجربة مجانية 48 ساعة", callback_data="trial")])
    buttons.append([InlineKeyboardButton("🛒 اشتراك جديد", callback_data="subscribe")])
    buttons.append([InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data="subscribe")])
    buttons.append([InlineKeyboardButton("📊 حالة اشتراكي", callback_data="status")])
    buttons.append([InlineKeyboardButton("💬 التواصل مع الدعم", url=f"https://t.me/{SUPPORT_USER}")])
    return InlineKeyboardMarkup(buttons)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db   = load_db()
    uid  = str(user.id)

    # لوحة الأدمن
    if str(user.id) == str(get_admin()):
        await update.message.reply_text(
            "👑 *لوحة تحكم الأدمن*\n\nاختر من القائمة:",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )
        return

    if uid in db.get("verified", {}):
        used_trial = uid in db.get("trials", {})
        has_sub    = uid in db.get("subscribers", {})
        show_trial = not used_trial and not has_sub
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
    db      = load_db()
    uid     = str(user.id)

    if contact.user_id != user.id:
        await update.message.reply_text("⚠️ يرجى مشاركة رقم جوالك الخاص فقط.", reply_markup=phone_keyboard())
        return

    if "verified" not in db:
        db["verified"] = {}
    db["verified"][uid] = {
        "phone":      contact.phone_number,
        "full_name":  user.full_name,
        "username":   user.username or "",
        "verified_at": datetime.now().isoformat()
    }
    save_db(db)

    await update.message.reply_text(
        "✅ *تم التحقق بنجاح!*\n\nأهلاً بك 🎉",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    used_trial = uid in db.get("trials", {})
    await update.message.reply_text(
        "مرحباً بك في قناة *عقود الأوبشن* 📈\n\n"
        "اشترك الآن للحصول على:\n"
        "• ✅ إشارات يومية احترافية\n"
        "• 📊 تحليلات دقيقة لعقود الأوبشن\n"
        "• 🔔 تنبيهات فورية\n\n"
        "اختر من القائمة:",
        parse_mode="Markdown",
        reply_markup=main_keyboard(show_trial=not used_trial)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    user  = query.from_user
    db    = load_db()
    uid   = str(user.id)

    if uid not in db.get("verified", {}) and not data.startswith(("approve_", "reject_")):
        await query.answer("يرجى إرسال /start أولاً للتحقق من رقمك.", show_alert=True)
        return

    if data == "subscribe":
        await query.edit_message_text(
            "📦 *خطط الاشتراك*\n\nاختر الخطة المناسبة:",
            parse_mode="Markdown",
            reply_markup=plans_keyboard()
        )

    elif data == "trial":
        if uid in db.get("trials", {}):
            await query.answer("⚠️ لقد استخدمت فترة التجربة المجانية مسبقاً.", show_alert=True)
            return
        if uid in db.get("subscribers", {}):
            await query.answer("✅ أنت مشترك بالفعل.", show_alert=True)
            return

        expires = datetime.now() + timedelta(hours=48)
        if "trials" not in db:
            db["trials"] = {}
        db["trials"][uid] = {
            "started_at": datetime.now().isoformat(),
            "expires_at": expires.isoformat()
        }
        db["subscribers"][uid] = {
            "plan_key":     "trial",
            "expires_at":   expires.isoformat(),
            "activated_at": datetime.now().isoformat(),
            "is_trial":     True
        }
        save_db(db)

        expires_str = expires.strftime('%Y/%m/%d الساعة %H:%M')
        await query.edit_message_text(
            f"🎁 *تم تفعيل فترة التجربة المجانية!*\n\n"
            f"• المدة: 48 ساعة\n"
            f"• تنتهي في: {expires_str}\n\n"
            f"⏳ سيتم إضافتك للقناة خلال دقائق.",
            parse_mode="Markdown"
        )

        try:
            link_expire = datetime.now() + timedelta(minutes=5)
            link = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                expire_date=int(link_expire.timestamp()),
                name=f"trial_{uid}"
            )
            await context.bot.send_message(
                chat_id=int(uid),
                text=(
                    f"🔗 *رابط دخولك للقناة:*\n{link.invite_link}\n\n"
                    f"⚠️ الرابط صالح لمدة *5 دقائق* فقط ويُستخدم مرة واحدة.\n"
                    f"ادخل القناة الآن قبل انتهاء الوقت! ⏰"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Trial invite error for {uid}: {e}")

        admin_id = get_admin()
        if admin_id:
            phone = db.get("verified", {}).get(uid, {}).get("phone", "—")
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🎁 *فترة تجربة جديدة*\n\n"
                    f"👤 {user.full_name}\n"
                    f"📱 {phone}\n"
                    f"🆔 `{uid}`\n"
                    f"⏰ تنتهي: {expires_str}"
                ),
                parse_mode="Markdown"
            )

    elif data.startswith("plan_"):
        key  = data.replace("plan_", "")
        plan = PLANS[key]
        db["pending"][uid] = {
            "plan_key":     key,
            "full_name":    user.full_name,
            "username":     user.username or "",
            "phone":        db["verified"].get(uid, {}).get("phone", "—"),
            "status":       "awaiting_receipt",
            "requested_at": datetime.now().isoformat()
        }
        save_db(db)
        await query.edit_message_text(
            f"✅ اخترت خطة *{plan['label']}* بـ {plan['price']} ريال\n\n"
            f"💳 *بيانات التحويل البنكي:*\n"
            f"• البنك: {BANK_NAME}\n"
            f"• الاسم: {ACCOUNT_NAME}\n"
            f"• الآيبان: `{IBAN}`\n\n"
            f"📌 *بعد التحويل:*\n"
            f"أرسل صورة إيصال التحويل هنا وسيتم مراجعتها خلال دقائق.\n\n"
            f"⚠️ تأكد أن اسمك ظاهر في الإيصال.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])
        )

    # ── Admin Panel ──
    elif data == "admin_verifypost":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("تحقق خلال ثانية 👌", callback_data="channel_verify")
        ]])
        await context.bot.send_message(
            chat_id=-1001934800979,
            text="اضغط الزر أدناه للتحقق 👇",
            reply_markup=kb
        )
        await query.edit_message_text("✅ تم نشر رسالة التحقق في القناة", reply_markup=admin_keyboard())

    elif data == "admin_channelusers":
        users = load_channel_users()
        await query.edit_message_text(
            f"👥 *المشتركون المحفوظون:* {len(users)} شخص",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_blast":
        context.user_data["awaiting_blast"] = True
        await query.edit_message_text(
            "📨 أرسل نص الرسالة اللي تبغى ترسلها للكل:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_cancel")]])
        )

    elif data == "admin_stats":
        db2         = load_db()
        verified    = db2.get("verified", {})
        subscribers = db2.get("subscribers", {})
        trials      = db2.get("trials", {})
        now2        = datetime.now()
        active      = [s for s in subscribers.values() if not s.get("is_trial") and now2 < datetime.fromisoformat(s["expires_at"])]
        revenue     = sum(PLANS.get(s.get("plan_key",""),{}).get("price",0) for s in subscribers.values() if not s.get("is_trial"))
        text = (
            "📊 *الإحصائيات*\n\n"
            f"👥 إجمالي المستخدمين: {len(verified)}\n"
            f"🎁 استخدموا التجربة: {len(trials)}\n"
            f"✅ مشتركون نشطون: {len(active)}\n"
            f"💰 الإيرادات: {revenue} ريال"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())

    elif data == "admin_checkexpired":
        db2       = load_db()
        subs      = db2.get("subscribers", {})
        now2      = datetime.now()
        to_remove = [uid for uid, s in subs.items() if now2 >= datetime.fromisoformat(s["expires_at"])]
        removed   = 0
        for uid in to_remove:
            try:
                await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
                await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
                is_trial = db2["subscribers"][uid].get("is_trial", False)
                msg = ("⏰ *انتهت فترة التجربة المجانية*\n\nتم إزالتك من القناة.\nاشترك الآن للاستمرار 👇") if is_trial else ("⏰ *انتهى اشتراكك*\n\nتم إزالتك من القناة تلقائياً.\nجدّد اشتراكك للاستمرار 👇")
                await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode="Markdown", reply_markup=main_keyboard())
                removed += 1
            except Exception as e:
                logger.error(f"Error removing {uid}: {e}")
            del db2["subscribers"][uid]
        save_db(db2)
        await query.edit_message_text(
            f"✅ تم إزالة {removed} مشترك منتهٍ.",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_cancel":
        context.user_data.pop("awaiting_blast", None)
        await query.edit_message_text("✅ تم الإلغاء.", reply_markup=admin_keyboard())

    elif data == "back_main":
        used_trial = uid in db.get("trials", {})
        has_sub    = uid in db.get("subscribers", {})
        show_trial = not used_trial and not has_sub
        await query.edit_message_text(
            "مرحباً بك في قناة *عقود الأوبشن* 📈\n\n"
            "اشترك الآن للحصول على:\n"
            "• ✅ إشارات يومية احترافية\n"
            "• 📊 تحليلات دقيقة لعقود الأوبشن\n"
            "• 🔔 تنبيهات فورية\n\n"
            "اختر من القائمة:",
            parse_mode="Markdown",
            reply_markup=main_keyboard(show_trial=show_trial)
        )

    elif data == "status":
        sub = db["subscribers"].get(uid)
        if sub:
            exp       = datetime.fromisoformat(sub["expires_at"])
            remaining = exp - datetime.now()
            is_trial  = sub.get("is_trial", False)
            if remaining.total_seconds() > 0:
                if is_trial:
                    hours = int(remaining.total_seconds() // 3600)
                    mins  = int((remaining.total_seconds() % 3600) // 60)
                    text  = (
                        f"🎁 *فترة التجربة المجانية فعّالة*\n\n"
                        f"• تنتهي في: {exp.strftime('%Y/%m/%d %H:%M')}\n"
                        f"• المتبقي: {hours} ساعة و{mins} دقيقة\n\n"
                        f"اشترك الآن للاستمرار بعد انتهاء التجربة 👇"
                    )
                else:
                    days = remaining.days
                    plan_label = PLANS.get(sub["plan_key"], {}).get("label", sub["plan_key"])
                    text = (
                        f"✅ *اشتراكك فعّال*\n\n"
                        f"• الخطة: {plan_label}\n"
                        f"• ينتهي في: {exp.strftime('%Y/%m/%d')}\n"
                        f"• المتبقي: {days} يوم"
                    )
            else:
                text = "❌ اشتراكك منتهٍ. اشترك مجدداً للوصول للقناة."
        else:
            text = "❌ لا يوجد اشتراك نشط.\nاضغط *اشترك الآن* للبدء."
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])
        )

    elif data.startswith("approve_"):
        if str(user.id) != str(get_admin()):
            await query.answer("⛔ غير مصرح", show_alert=True)
            return
        parts    = data.split("_")
        uid      = parts[1]
        plan_key = parts[2]
        plan     = PLANS[plan_key]
        expires  = datetime.now() + timedelta(days=plan["months"] * 30)
        db["subscribers"][uid] = {
            "plan_key":     plan_key,
            "expires_at":   expires.isoformat(),
            "activated_at": datetime.now().isoformat()
        }
        db["pending"].pop(uid, None)
        save_db(db)
        invite_url = None
        try:
            link = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                expire_date=int(expires.timestamp()),
                name=f"sub_{uid}"
            )
            invite_url = link.invite_link
        except Exception as e:
            logger.error(f"Invite link error for {uid}: {e}")

        if invite_url:
            msg = (
                f"🎉 *تم تأكيد اشتراكك!*\n\n"
                f"• الخطة: {plan['label']}\n"
                f"• ينتهي في: {expires.strftime('%Y/%m/%d')}\n\n"
                f"🔗 *رابط دخولك الخاص:*\n{invite_url}\n\n"
                f"⚠️ هذا الرابط خاص بك فقط ويُستخدم مرة واحدة. لا تشاركه."
            )
            admin_note = f"✅ تم قبول `{uid}` — {plan['label']}\n🔗 تم إرسال الرابط"
        else:
            msg = (
                f"🎉 *تم تأكيد اشتراكك!*\n\n"
                f"• الخطة: {plan['label']}\n"
                f"• ينتهي في: {expires.strftime('%Y/%m/%d')}\n\n"
                f"⏳ سيتم إضافتك للقناة خلال دقائق."
            )
            admin_note = f"✅ تم قبول `{uid}` — {plan['label']}\n⚠️ فشل توليد الرابط — أضف يدوياً"

        await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode="Markdown")
        await query.edit_message_text(admin_note, parse_mode="Markdown")

    elif data.startswith("reject_"):
        if str(user.id) != str(get_admin()):
            await query.answer("⛔ غير مصرح", show_alert=True)
            return
        uid = data.replace("reject_", "")
        db["pending"].pop(uid, None)
        save_db(db)
        await context.bot.send_message(
            chat_id=int(uid),
            text="❌ *تم رفض طلبك.*\n\nتأكد من صحة الإيصال وأعد الإرسال أو تواصل معنا.",
            parse_mode="Markdown"
        )
        await query.edit_message_text(f"❌ تم رفض طلب `{uid}`", parse_mode="Markdown")

async def handle_admin_blast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يرسل رسالة الأدمن لكل المشتركين المحفوظين"""
    if str(update.effective_user.id) != str(get_admin()):
        return
    if not context.user_data.get("awaiting_blast"):
        return
    context.user_data.pop("awaiting_blast", None)
    msg      = update.message.text
    users    = load_channel_users()
    sent_ok  = 0
    sent_err = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
            sent_ok += 1
        except:
            sent_err += 1
    await update.message.reply_text(
        f"✅ تم الإرسال لـ {sent_ok} شخص | ❌ فشل {sent_err}",
        reply_markup=admin_keyboard()
    )

async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    db      = load_db()
    uid     = str(user.id)
    if uid not in db.get("verified", {}):
        await update.message.reply_text("📌 أرسل /start أولاً للتحقق من رقمك.")
        return
    pending = db["pending"].get(uid)
    if not pending or pending.get("status") not in ("awaiting_receipt", "receipt_sent"):
        await update.message.reply_text("📌 لا يوجد طلب اشتراك مفتوح.\nاضغط /start للبدء.")
        return
    admin_id = get_admin()
    if not admin_id:
        await update.message.reply_text("⚠️ تواصل مع الدعم مباشرة.")
        return
    plan     = PLANS[pending["plan_key"]]
    plan_key = pending["plan_key"]
    phone    = db["verified"].get(uid, {}).get("phone", "—")
    caption  = (
        f"📥 *طلب اشتراك جديد*\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"📱 الجوال: `{phone}`\n"
        f"🆔 ID: `{uid}`\n"
        f"📦 الخطة: {plan['label']} — {plan['price']} ريال\n"
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
    db["pending"][uid]["status"] = "receipt_sent"
    save_db(db)
    await update.message.reply_text(
        "✅ *تم استلام إيصالك!*\n\nسيتم مراجعته وتفعيل اشتراكك خلال دقائق. 🙏",
        parse_mode="Markdown"
    )

async def channel_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يُحفظ ID المستخدم لما يضغط زر التحقق في القناة"""
    query = update.callback_query
    await query.answer("✅ تم التحقق!", show_alert=False)
    user = query.from_user
    if not user:
        return
    users = load_channel_users()
    users[str(user.id)] = {
        "name":     user.full_name,
        "username": user.username or "",
        "joined":   datetime.now().isoformat()
    }
    save_channel_users(users)

async def blast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يرسل رسالة لكل من تحقق في القناة"""
    if str(update.effective_user.id) != str(get_admin()):
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: /blast الرسالة هنا")
        return
    msg      = " ".join(context.args)
    users    = load_channel_users()
    sent_ok  = 0
    sent_err = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
            sent_ok += 1
        except:
            sent_err += 1
    await update.message.reply_text(f"✅ تم الإرسال لـ {sent_ok} شخص | ❌ فشل {sent_err}")

async def send_verify_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ينشر رسالة التحقق في القناة العامة"""
    if str(update.effective_user.id) != str(get_admin()):
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("تحقق خلال ثانية 👌", callback_data="channel_verify")
    ]])
    await context.bot.send_message(
        chat_id=-1001934800979,
        text="اضغط الزر أدناه للتحقق 👇",
        reply_markup=kb
    )
    await update.message.reply_text("✅ تم نشر رسالة التحقق في القناة")

async def channel_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض عدد المستخدمين المحفوظين"""
    if str(update.effective_user.id) != str(get_admin()):
        return
    users = load_channel_users()
    await update.message.reply_text(f"👥 عدد المستخدمين المحفوظين: {len(users)}")

async def check_now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(get_admin()):
        return
    await update.message.reply_text("⏳ جاري فحص المشتركين المنتهين...")
    db        = load_db()
    subs      = db.get("subscribers", {})
    now       = datetime.now()
    to_remove = [uid for uid, s in subs.items() if now >= datetime.fromisoformat(s["expires_at"])]
    if not to_remove:
        await update.message.reply_text("✅ لا يوجد مشتركون منتهون.")
        return
    removed = 0
    for uid in to_remove:
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
            is_trial = db["subscribers"][uid].get("is_trial", False)
            msg = (
                "⏰ *انتهت فترة التجربة المجانية*\n\n"
                "تم إزالتك من القناة.\n"
                "اشترك الآن للاستمرار في الحصول على الإشارات 👇"
            ) if is_trial else (
                "⏰ *انتهى اشتراكك*\n\n"
                "تم إزالتك من القناة تلقائياً.\n"
                "جدّد اشتراكك للاستمرار 👇"
            )
            await context.bot.send_message(
                chat_id=int(uid),
                text=msg,
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
            removed += 1
        except Exception as e:
            logger.error(f"Error removing {uid}: {e}")
        del db["subscribers"][uid]
    save_db(db)
    await update.message.reply_text(f"✅ تم إزالة {removed} مشترك منتهٍ.")

async def reset_trial_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(get_admin()):
        return
    db  = load_db()
    uid = str(update.effective_user.id)
    db.get("trials", {}).pop(uid, None)
    db.get("subscribers", {}).pop(uid, None)
    save_db(db)
    await update.message.reply_text("✅ تم مسح التجربة — أرسل /start مجدداً")

async def forceadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    set_admin(uid)
    await update.message.reply_text(f"✅ تم تسجيلك كأدمن!\nID: `{uid}`", parse_mode="Markdown")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    current = get_admin()
    if current is None:
        set_admin(uid)
        await update.message.reply_text(f"✅ تم تسجيلك كأدمن!\nID: `{uid}`", parse_mode="Markdown")
    elif current == uid:
        await update.message.reply_text(f"✅ أنت الأدمن.\nID: `{uid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⛔ أدمن مسجّل مسبقاً.")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(get_admin()):
        return
    db          = load_db()
    verified    = db.get("verified", {})
    subscribers = db.get("subscribers", {})
    trials      = db.get("trials", {})
    now         = datetime.now()
    total_users  = len(verified)
    total_trials = len(trials)
    active_subs  = [s for s in subscribers.values() if not s.get("is_trial") and now < datetime.fromisoformat(s["expires_at"])]
    expired_subs = [s for s in subscribers.values() if not s.get("is_trial") and now >= datetime.fromisoformat(s["expires_at"])]
    revenue = 0
    for s in subscribers.values():
        if not s.get("is_trial"):
            plan = PLANS.get(s.get("plan_key", ""), {})
            revenue += plan.get("price", 0)
    plan_counts = {}
    for s in subscribers.values():
        if not s.get("is_trial"):
            key = s.get("plan_key", "")
            plan_counts[key] = plan_counts.get(key, 0) + 1
    lines = [
        "📊 *إحصائيات البوت*\n",
        f"👥 إجمالي المستخدمين: {total_users}",
        f"🎁 استخدموا التجربة: {total_trials}",
        f"✅ مشتركون نشطون: {len(active_subs)}",
        f"❌ اشتراكات منتهية: {len(expired_subs)}",
        f"💰 إجمالي الإيرادات: {revenue} ريال\n",
        "*توزيع الخطط:*"
    ]
    for key, count in plan_counts.items():
        plan = PLANS.get(key, {})
        lines.append(f"• {plan.get('label', key)}: {count} مشترك")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def subs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(get_admin()):
        return
    db   = load_db()
    subs = db.get("subscribers", {})
    if not subs:
        await update.message.reply_text("لا يوجد مشتركين حالياً.")
        return
    lines = ["📋 *المشتركون:*\n"]
    for uid, s in subs.items():
        exp   = datetime.fromisoformat(s["expires_at"])
        days  = (exp - datetime.now()).days
        phone = db.get("verified", {}).get(uid, {}).get("phone", "—")
        st    = f"{days} يوم متبقي" if days > 0 else "⚠️ منتهي"
        lines.append(f"• `{uid}` | 📱{phone} | {PLANS[s['plan_key']]['label']} | {st}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def check_expired(context: ContextTypes.DEFAULT_TYPE):
    db        = load_db()
    subs      = db.get("subscribers", {})
    now       = datetime.now()
    to_remove = [uid for uid, s in subs.items() if now >= datetime.fromisoformat(s["expires_at"])]
    for uid in to_remove:
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
            is_trial = db["subscribers"][uid].get("is_trial", False)
            msg = (
                "⏰ *انتهت فترة التجربة المجانية*\n\n"
                "تم إزالتك من القناة.\n"
                "اشترك الآن للاستمرار في الحصول على الإشارات 👇"
            ) if is_trial else (
                "⏰ *انتهى اشتراكك*\n\n"
                "تم إزالتك من القناة تلقائياً.\n"
                "جدّد اشتراكك للاستمرار 👇"
            )
            await context.bot.send_message(
                chat_id=int(uid),
                text=msg,
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
        except Exception as e:
            logger.error(f"Error removing {uid}: {e}")
        del db["subscribers"][uid]
    if to_remove:
        save_db(db)

async def delete_system_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Could not delete system message: {e}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("admin",        admin_cmd))
    app.add_handler(CommandHandler("subs",         subs_cmd))
    app.add_handler(CommandHandler("stats",        stats_cmd))
    app.add_handler(CommandHandler("reset_trial",  reset_trial_cmd))
    app.add_handler(CommandHandler("forceadmin",   forceadmin_cmd))
    app.add_handler(CommandHandler("checkexpired",  check_now_cmd))
    app.add_handler(CommandHandler("blast",         blast_cmd))
    app.add_handler(CommandHandler("verifypost",    send_verify_post))
    app.add_handler(CommandHandler("channelusers",  channel_users_cmd))
    app.add_handler(CallbackQueryHandler(channel_verify, pattern="^channel_verify$"))
    app.add_handler(MessageHandler(filters.CONTACT, receive_contact))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID if (ADMIN_ID:=get_admin()) else 0), handle_admin_blast_msg))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receive_receipt))
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
