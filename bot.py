import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = "7699128682:AAEO8ALej5lswYTRFsckXVvWoJhv5Ps93Gk"
CHANNEL_ID     = -1001003618409425

BANK_NAME    = "البنك الأهلي السعودي"
ACCOUNT_NAME = "بدر محمد الجعيد"
IBAN         = "SA7010000088050617000103"

PLANS = {
    "1m":  {"label": "شهري",   "months": 1,  "price": 200},
    "3m":  {"label": "3 أشهر", "months": 3,  "price": 500},
    "6m":  {"label": "6 أشهر", "months": 6,  "price": 1000},
    "12m": {"label": "سنوي",   "months": 12, "price": 1500},
}

DB_FILE = "db.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"subscribers": {}, "pending": {}, "admin_id": None}

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_admin():
    return load_db().get("admin_id")

def set_admin(uid):
    db = load_db()
    db["admin_id"] = uid
    save_db(db)

def plans_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📦 {p['label']} — {p['price']} ريال", callback_data=f"plan_{k}")]
        for k, p in PLANS.items()
    ])

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 اشترك الآن", callback_data="subscribe")],
        [InlineKeyboardButton("📊 حالة اشتراكي", callback_data="status")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"أهلاً {user.first_name}! 👋\n\n"
        "مرحباً بك في قناة *عقود الأوبشن* 📈\n\n"
        "اشترك الآن للحصول على:\n"
        "• ✅ إشارات يومية احترافية\n"
        "• 📊 تحليلات دقيقة لعقود الأوبشن\n"
        "• 🔔 تنبيهات فورية\n\n"
        "اختر من القائمة:",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    db   = load_db()

    if data == "subscribe":
        await query.edit_message_text(
            "📦 *خطط الاشتراك*\n\nاختر الخطة المناسبة:",
            parse_mode="Markdown",
            reply_markup=plans_keyboard()
        )

    elif data.startswith("plan_"):
        key  = data.replace("plan_", "")
        plan = PLANS[key]
        db["pending"][str(user.id)] = {
            "plan_key": key,
            "full_name": user.full_name,
            "username": user.username or "",
            "status": "awaiting_receipt",
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
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="subscribe")
            ]])
        )

    elif data == "status":
        uid = str(user.id)
        sub = db["subscribers"].get(uid)
        if sub:
            exp       = datetime.fromisoformat(sub["expires_at"])
            remaining = (exp - datetime.now()).days
            if remaining > 0:
                text = (
                    f"✅ *اشتراكك فعّال*\n\n"
                    f"• الخطة: {PLANS[sub['plan_key']]['label']}\n"
                    f"• ينتهي في: {exp.strftime('%Y/%m/%d')}\n"
                    f"• المتبقي: {remaining} يوم"
                )
            else:
                text = "❌ اشتراكك منتهٍ. اشترك مجدداً للوصول للقناة."
        else:
            text = "❌ لا يوجد اشتراك نشط.\nاضغط *اشترك الآن* للبدء."
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

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

        try:
            link = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                expire_date=expires,
                name=f"sub_{uid}"
            )
            invite_url = link.invite_link
            msg = (
                f"🎉 *تم تأكيد اشتراكك!*\n\n"
                f"• الخطة: {plan['label']}\n"
                f"• ينتهي في: {expires.strftime('%Y/%m/%d')}\n\n"
                f"🔗 *رابط دخولك الخاص:*\n{invite_url}\n\n"
                f"⚠️ هذا الرابط خاص بك فقط — لا تشاركه مع أحد."
            )
        except Exception as e:
            logger.error(f"Invite link error: {e}")
            msg = (
                f"🎉 *تم تأكيد اشتراكك!*\n\n"
                f"• الخطة: {plan['label']}\n"
                f"• ينتهي في: {expires.strftime('%Y/%m/%d')}\n\n"
                f"سيتم إضافتك للقناة خلال دقائق."
            )

        await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode="Markdown")
        await query.edit_message_text(
            f"✅ تم قبول اشتراك المستخدم `{uid}` — خطة {plan['label']}",
            parse_mode="Markdown"
        )

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
        await query.edit_message_text(f"❌ تم رفض طلب المستخدم `{uid}`", parse_mode="Markdown")

async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    db      = load_db()
    uid     = str(user.id)
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
    caption  = (
        f"📥 *طلب اشتراك جديد*\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"🆔 ID: `{uid}`\n"
        f"📦 الخطة: {plan['label']} — {plan['price']} ريال\n"
        f"🕐 الوقت: {datetime.now().strftime('%Y/%m/%d %H:%M')}"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول وإرسال رابط", callback_data=f"approve_{uid}_{plan_key}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject_{uid}"),
    ]])

    if update.message.photo:
        await context.bot.send_photo(
            chat_id=admin_id, photo=update.message.photo[-1].file_id,
            caption=caption, parse_mode="Markdown", reply_markup=kb
        )
    elif update.message.document:
        await context.bot.send_document(
            chat_id=admin_id, document=update.message.document.file_id,
            caption=caption, parse_mode="Markdown", reply_markup=kb
        )
    else:
        await update.message.reply_text("📎 أرسل صورة الإيصال من فضلك.")
        return

    db["pending"][uid]["status"] = "receipt_sent"
    save_db(db)
    await update.message.reply_text(
        "✅ *تم استلام إيصالك!*\n\nسيتم مراجعته وتفعيل اشتراكك خلال دقائق. 🙏",
        parse_mode="Markdown"
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    current = get_admin()
    if current is None:
        set_admin(uid)
        await update.message.reply_text(
            f"✅ تم تسجيلك كأدمن!\nID: `{uid}`\n\nسيتم إرسال طلبات الاشتراك إليك مباشرة.",
            parse_mode="Markdown"
        )
    elif current == uid:
        await update.message.reply_text(f"✅ أنت الأدمن المسجّل.\nID: `{uid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⛔ أدمن مسجّل مسبقاً.")

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
        exp  = datetime.fromisoformat(s["expires_at"])
        days = (exp - datetime.now()).days
        st   = f"{days} يوم متبقي" if days > 0 else "⚠️ منتهي"
        lines.append(f"• `{uid}` | {PLANS[s['plan_key']]['label']} | {st}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def check_expired(context: ContextTypes.DEFAULT_TYPE):
    db         = load_db()
    subs       = db.get("subscribers", {})
    now        = datetime.now()
    to_remove  = [uid for uid, s in subs.items() if now >= datetime.fromisoformat(s["expires_at"])]

    for uid in to_remove:
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
            await context.bot.send_message(
                chat_id=int(uid),
                text=(
                    "⏰ *انتهى اشتراكك*\n\n"
                    "تم إزالتك من القناة تلقائياً.\n"
                    "جدّد اشتراكك للاستمرار 👇"
                ),
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
        except Exception as e:
            logger.error(f"Error removing {uid}: {e}")
        del db["subscribers"][uid]

    if to_remove:
        save_db(db)
        logger.info(f"Removed {len(to_remove)} expired subscribers")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("admin",  admin_cmd))
    app.add_handler(CommandHandler("subs",   subs_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receive_receipt))
    app.job_queue.run_repeating(check_expired, interval=3600, first=10)
    print("✅ البوت شغّال!")
    app.run_polling()

if __name__ == "__main__":
    main()
