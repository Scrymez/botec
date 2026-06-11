import logging
from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import db
import reports
import keyboards
from config import ADMIN_IDS

log = logging.getLogger(__name__)

# ConversationHandler states
NB_USER, NB_SERVICE, NB_CUSTOM_SERVICE, NB_AMOUNT, NB_DATE, NB_DATE_TEXT, NB_CONFIRM = range(7)

MAX_AMOUNT = 10_000_000


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def guard(update: Update) -> bool:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return False
    return True


# ── /report ───────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await update.message.reply_text(reports.full_report(), parse_mode="HTML")


# ── /users ────────────────────────────────────────────────────────────────────

async def cmd_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    users = db.get_all_users()
    if not users:
        await update.message.reply_text(
            "Пользователей нет.\n\nДобавь: /adduser <telegram_id> [имя]"
        )
        return
    for uid, user in users.items():
        pending = [b for b in user["bills"] if b["status"] == "pending"]
        paid    = [b for b in user["bills"] if b["status"] == "paid"]
        overdue = [b for b in pending if db.days_until(b["due_date"]) < 0]
        status_line = f"⏳ {len(pending)} ожидают"
        if overdue:
            status_line += f"  🔴 {len(overdue)} просроч."
        status_line += f"  ✅ {len(paid)} оплачено"
        await update.message.reply_text(
            f"👤 <b>{reports.user_display_name(user)}</b>\n{status_line}",
            reply_markup=keyboards.user_list_keyboard(uid),
            parse_mode="HTML",
        )


# ── /pending ──────────────────────────────────────────────────────────────────

async def cmd_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    items = db.get_pending_bills()
    if not items:
        await update.message.reply_text("✅ Все счета оплачены!")
        return
    await update.message.reply_text(
        f"⏳ <b>Неоплаченных счетов: {len(items)}</b>", parse_mode="HTML"
    )
    for item in sorted(items, key=lambda x: x["bill"]["due_date"]):
        u = item["user"]
        b = item["bill"]
        days = db.days_until(b["due_date"])
        due_fmt = date.fromisoformat(b["due_date"]).strftime("%d.%m.%Y")
        flag = "🔴" if days < 0 else ("🟡" if days <= 3 else "⏳")
        day_str = f"просрочено на {-days}д" if days < 0 else f"через {days}д"
        await update.message.reply_text(
            f"{flag} <b>{reports.user_display_name(u)}</b>\n"
            f"   {reports._e(b['service'])} — {reports._fmt(b['amount'])}\n"
            f"   Срок: {due_fmt} ({day_str})  #{b['id']}",
            reply_markup=keyboards.bill_keyboard(item["user_id"], b["id"]),
            parse_mode="HTML",
        )


# ── /adduser ──────────────────────────────────────────────────────────────────

async def cmd_adduser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Использование: /adduser <telegram_id> [имя]\n\n"
            "Пример: /adduser 123456789 Иван Иванов\n\n"
            "💡 Проще: попроси пользователя написать /start боту — "
            "он зарегистрируется автоматически."
        )
        return
    try:
        uid = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    name = " ".join(args[1:])[:100] if len(args) > 1 else str(uid)
    db.upsert_user(uid, "", name, uid)
    await update.message.reply_text(
        f"✅ Пользователь добавлен\nID: <code>{uid}</code>  Имя: {reports._e(name)}",
        parse_mode="HTML",
    )


# ── /remindall ────────────────────────────────────────────────────────────────

async def cmd_remindall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    items = db.get_pending_bills()
    if not items:
        await update.message.reply_text("✅ Нет неоплаченных счетов.")
        return
    sent = errors = 0
    for item in items:
        try:
            await ctx.bot.send_message(
                chat_id=item["user"]["chat_id"],
                text=reports.reminder_message(item["bill"]),
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            log.warning("remindall %s: %s", item["user_id"], e)
            errors += 1
    msg = f"📨 Напоминания отправлены: {sent}"
    if errors:
        msg += f"\n⚠️ Ошибок: {errors} (пользователь не писал боту?)"
    await update.message.reply_text(msg)


# ── /bots ─────────────────────────────────────────────────────────────────────

async def cmd_bots(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    bots = db.get_all_bots()
    if not bots:
        text = "🤖 Боты не добавлены."
    else:
        lines = "\n".join(f"• @{username}" for username in bots)
        text = f"🤖 <b>Зарегистрированные боты:</b>\n{lines}"
    await update.message.reply_text(text, reply_markup=keyboards.bots_keyboard(), parse_mode="HTML")


# ── /newbill + nb_pre — ConversationHandler ───────────────────────────────────

def _user_select_keyboard(preselect_uid: str | None = None) -> tuple[InlineKeyboardMarkup, bool]:
    """Returns (keyboard, has_users)."""
    users = db.get_all_users()
    if not users:
        return None, False
    keyboard = [
        [InlineKeyboardButton(reports.user_display_name(u), callback_data=f"nb_user:{uid}")]
        for uid, u in users.items()
    ]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="nb_cancel")])
    return InlineKeyboardMarkup(keyboard), True


async def cmd_newbill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Entry: /newbill command — shows user selection."""
    if not is_admin(update.effective_user.id):
        if update.message:
            await update.message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    kb, has_users = _user_select_keyboard()
    if not has_users:
        target = update.message or update.callback_query.message
        await target.reply_text("Сначала добавь пользователей: /adduser <id> <имя>")
        return ConversationHandler.END

    target = update.message if update.message else update.callback_query.message
    await target.reply_text(
        "💳 <b>Новый счёт</b>\n\nВыбери пользователя:",
        reply_markup=kb,
        parse_mode="HTML",
    )
    return NB_USER


async def nb_pre_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Entry: '➕ Счёт' button from user list — user already selected, skip to service."""
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    uid = query.data.split(":")[1]
    user = db.get_user(int(uid))
    if not user:
        await query.edit_message_text("❌ Пользователь не найден.")
        return ConversationHandler.END

    ctx.user_data.update({"nb_uid": uid, "nb_name": reports.user_display_name(user)})
    await query.edit_message_text(
        f"👤 <b>{ctx.user_data['nb_name']}</b>\n\nВыбери услугу:",
        reply_markup=keyboards.service_keyboard(),
        parse_mode="HTML",
    )
    return NB_SERVICE


async def nb_got_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "nb_cancel":
        await query.edit_message_text("❌ Отменено.")
        return ConversationHandler.END
    uid = query.data.split(":")[1]
    user = db.get_user(int(uid))
    if not user:
        await query.edit_message_text("❌ Пользователь не найден.")
        return ConversationHandler.END
    ctx.user_data.update({"nb_uid": uid, "nb_name": reports.user_display_name(user)})
    await query.edit_message_text(
        f"👤 <b>{ctx.user_data['nb_name']}</b>\n\nВыбери услугу:",
        reply_markup=keyboards.service_keyboard(),
        parse_mode="HTML",
    )
    return NB_SERVICE


async def nb_got_service(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "nb_cancel":
        await query.edit_message_text("❌ Отменено.")
        ctx.user_data.clear()
        return ConversationHandler.END
    val = query.data.split(":", 1)[1]
    if val == "__custom__":
        await query.edit_message_text("✏️ Введи название услуги (до 100 символов):")
        return NB_CUSTOM_SERVICE
    ctx.user_data["nb_service"] = val
    await query.edit_message_text(
        f"👤 {ctx.user_data['nb_name']}\n"
        f"🔧 Услуга: <b>{reports._e(val)}</b>\n\n"
        f"Введи сумму (только цифры):",
        parse_mode="HTML",
    )
    return NB_AMOUNT


async def nb_got_custom_service(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()[:100]
    if not name:
        await update.message.reply_text("❌ Название не может быть пустым.")
        return NB_CUSTOM_SERVICE
    ctx.user_data["nb_service"] = name
    await update.message.reply_text(
        f"🔧 Услуга: <b>{reports._e(name)}</b>\n\nВведи сумму (только цифры):",
        parse_mode="HTML",
    )
    return NB_AMOUNT


async def nb_got_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace(",", ".").replace(" ", "")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError("non-positive")
        if amount > MAX_AMOUNT:
            raise ValueError("too large")
    except ValueError as e:
        if "too large" in str(e):
            await update.message.reply_text(f"❌ Сумма не может превышать {reports._fmt(MAX_AMOUNT)}")
        else:
            await update.message.reply_text("❌ Введи положительное число. Например: 1500")
        return NB_AMOUNT
    ctx.user_data["nb_amount"] = amount
    await update.message.reply_text(
        f"💰 Сумма: <b>{reports._fmt(amount)}</b>\n\nВыбери срок оплаты:",
        reply_markup=keyboards.due_date_keyboard(),
        parse_mode="HTML",
    )
    return NB_DATE


async def nb_got_date_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "nb_cancel":
        await query.edit_message_text("❌ Отменено.")
        ctx.user_data.clear()
        return ConversationHandler.END
    choice = query.data.split(":")[1]
    if choice == "manual":
        await query.edit_message_text("📅 Введи дату в формате ДД.ММ.ГГГГ:")
        return NB_DATE_TEXT
    due = date.today() + timedelta(days=int(choice))
    ctx.user_data["nb_due"] = due.isoformat()
    await query.message.reply_text(**(await _nb_confirm_kwargs(ctx)))
    return NB_CONFIRM


async def nb_got_date_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        p = update.message.text.strip().split(".")
        due = date(int(p[2]), int(p[1]), int(p[0]))
    except Exception:
        await update.message.reply_text("❌ Неверный формат. Введи ДД.ММ.ГГГГ:")
        return NB_DATE_TEXT
    # FIX: reject past dates
    if due < date.today():
        await update.message.reply_text(
            f"❌ Дата {due.strftime('%d.%m.%Y')} уже прошла. Введи будущую дату:"
        )
        return NB_DATE_TEXT
    ctx.user_data["nb_due"] = due.isoformat()
    await update.message.reply_text(**(await _nb_confirm_kwargs(ctx)))
    return NB_CONFIRM


async def _nb_confirm_kwargs(ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    d = ctx.user_data
    due_fmt = date.fromisoformat(d["nb_due"]).strftime("%d.%m.%Y")
    text = (
        f"📋 <b>Подтверди счёт:</b>\n\n"
        f"👤 {d['nb_name']}\n"
        f"🔧 {reports._e(d['nb_service'])}\n"
        f"💰 {reports._fmt(d['nb_amount'])}\n"
        f"📅 до {due_fmt}\n"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Создать", callback_data="nb_confirm:yes"),
        InlineKeyboardButton("❌ Отмена",  callback_data="nb_confirm:no"),
    ]])
    return {"text": text, "reply_markup": kb, "parse_mode": "HTML"}


async def nb_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "nb_confirm:no":
        await query.edit_message_text("❌ Отменено.")
        ctx.user_data.clear()
        return ConversationHandler.END

    d = ctx.user_data
    bill = db.create_bill(int(d["nb_uid"]), d["nb_service"], d["nb_amount"], d["nb_due"])
    if not bill:
        await query.edit_message_text("❌ Ошибка создания счёта.")
        return ConversationHandler.END

    await query.edit_message_text(f"✅ Счёт создан  #{bill['id']}")

    user = db.get_user(int(d["nb_uid"]))
    if user and user.get("chat_id"):
        due_fmt = date.fromisoformat(d["nb_due"]).strftime("%d.%m.%Y")
        try:
            await ctx.bot.send_message(
                chat_id=user["chat_id"],
                text=(
                    f"💳 <b>Новый счёт к оплате</b>\n\n"
                    f"Услуга: <b>{reports._e(bill['service'])}</b>\n"
                    f"Сумма: <b>{reports._fmt(bill['amount'])}</b>\n"
                    f"Срок оплаты: <b>{due_fmt}</b>\n\n"
                    f"ID счёта: <code>{bill['id']}</code>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            log.warning("notify new bill %s: %s", d["nb_uid"], e)
            await query.message.reply_text(
                "⚠️ Уведомление не отправлено — пользователь ещё не писал боту."
            )

    ctx.user_data.clear()
    return ConversationHandler.END


async def nb_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    ctx.user_data.clear()
    return ConversationHandler.END


def newbill_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("newbill", cmd_newbill),
            # FIX: '➕ Счёт' button from user list — goes straight to service step
            CallbackQueryHandler(nb_pre_selected, pattern="^nb_pre:"),
        ],
        states={
            NB_USER: [
                CallbackQueryHandler(nb_got_user, pattern="^nb_user:|^nb_cancel$"),
            ],
            NB_SERVICE: [
                CallbackQueryHandler(nb_got_service, pattern="^nb_svc:|^nb_cancel$"),
            ],
            NB_CUSTOM_SERVICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nb_got_custom_service),
            ],
            NB_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nb_got_amount),
            ],
            NB_DATE: [
                CallbackQueryHandler(nb_got_date_btn, pattern="^nb_date:|^nb_cancel$"),
            ],
            NB_DATE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nb_got_date_text),
            ],
            NB_CONFIRM: [
                CallbackQueryHandler(nb_confirm, pattern="^nb_confirm:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", nb_cancel)],
        per_user=True,
    )
