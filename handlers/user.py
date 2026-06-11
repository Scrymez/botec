import logging
from telegram import Update
from telegram.ext import ContextTypes
import db
import reports
from config import ADMIN_IDS
from keyboards import ADMIN_MENU, USER_MENU

log = logging.getLogger(__name__)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    uid = tg_user.id
    username = tg_user.username or ""
    full_name = tg_user.full_name or ""

    db.upsert_user(uid, username, full_name, uid)
    is_adm = uid in ADMIN_IDS

    if is_adm:
        text = (
            f"👋 Привет, <b>{full_name}</b>!\n\n"
            f"Ты администратор. Используй кнопки меню ниже.\n\n"
            f"Твой ID: <code>{uid}</code>"
        )
        keyboard = ADMIN_MENU
    else:
        text = (
            f"👋 Привет, <b>{full_name}</b>!\n\n"
            f"Ты в системе оплаты серверов.\n"
            f"Буду уведомлять о счетах и напоминать об оплате.\n\n"
            f"Твой ID: <code>{uid}</code>"
        )
        keyboard = USER_MENU

    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

    if not is_adm:
        for admin_id in ADMIN_IDS:
            try:
                await ctx.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"🆕 Новый пользователь:\n"
                        f"Имя: <b>{full_name}</b>\n"
                        f"Username: @{username or '—'}\n"
                        f"ID: <code>{uid}</code>"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                log.warning("notify admin %s: %s", admin_id, e)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = db.get_user(uid)
    if not user:
        await update.message.reply_text("Напиши /start для регистрации.")
        return
    pending = [b for b in user.get("bills", []) if b["status"] == "pending"]
    if not pending:
        await update.message.reply_text("✅ <b>Нет неоплаченных счетов!</b>", parse_mode="HTML")
        return
    await update.message.reply_text(reports.user_report(uid), parse_mode="HTML")


async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = db.get_user(uid)
    if not user:
        await update.message.reply_text("Напиши /start для регистрации.")
        return
    if not user.get("bills"):
        await update.message.reply_text("История платежей пуста.")
        return
    await update.message.reply_text(reports.user_report(uid), parse_mode="HTML")


async def handle_menu_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # First check if waiting for custom paid amount
    from handlers.callbacks import handle_custom_paid_amount, handle_bot_username_input
    if await handle_custom_paid_amount(update, ctx):
        return
    if await handle_bot_username_input(update, ctx):
        return

    text = update.message.text
    uid = update.effective_user.id
    is_adm = uid in ADMIN_IDS

    if text == "📊 Отчёт по бюджету":
        if is_adm:
            await update.message.reply_text(reports.full_report(), parse_mode="HTML")
        else:
            await update.message.reply_text("⛔ Нет доступа.")

    elif text == "⏳ Неоплаченные счета":
        if is_adm:
            from handlers.admin import cmd_pending
            await cmd_pending(update, ctx)
        else:
            await update.message.reply_text("⛔ Нет доступа.")

    elif text == "👥 Пользователи":
        if is_adm:
            from handlers.admin import cmd_users
            await cmd_users(update, ctx)
        else:
            await update.message.reply_text("⛔ Нет доступа.")

    elif text == "➕ Новый счёт":
        if is_adm:
            from handlers.admin import cmd_newbill
            await cmd_newbill(update, ctx)
        else:
            await update.message.reply_text("⛔ Нет доступа.")

    elif text == "📨 Напомнить всем":
        if is_adm:
            from handlers.admin import cmd_remindall
            await cmd_remindall(update, ctx)
        else:
            await update.message.reply_text("⛔ Нет доступа.")

    elif text == "💳 Мой статус":
        await cmd_status(update, ctx)

    elif text == "📜 История платежей":
        await cmd_history(update, ctx)

    elif text == "🤖 Боты":
        if is_adm:
            from handlers.admin import cmd_bots
            await cmd_bots(update, ctx)
        else:
            await update.message.reply_text("⛔ Нет доступа.")
