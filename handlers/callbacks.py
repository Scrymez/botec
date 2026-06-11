"""All inline keyboard callback handlers (u_* and b_* patterns)."""
import logging
from datetime import date
from telegram import Update
from telegram.ext import ContextTypes
import db
import reports
import keyboards
from config import ADMIN_IDS

log = logging.getLogger(__name__)


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # FIX: admin check BEFORE query.answer() so show_alert works
    if not is_admin(update.effective_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    # ── User actions ─────────────────────────────────────────────────────────

    if data.startswith("u_bills:"):
        await query.answer()
        uid = int(data.split(":")[1])
        user = db.get_user(uid)
        if not user:
            await query.edit_message_text("❌ Пользователь не найден.")
            return
        pending = [b for b in user.get("bills", []) if b["status"] == "pending"]
        if not pending:
            await query.edit_message_text(
                f"✅ У {reports.user_display_name(user)} нет неоплаченных счетов."
            )
            return
        # Edit original message to remove buttons, then send bill cards
        await query.edit_message_text(
            f"📋 Счета: <b>{reports.user_display_name(user)}</b>",
            parse_mode="HTML",
        )
        for bill in sorted(pending, key=lambda b: b["due_date"]):
            days = db.days_until(bill["due_date"])
            due_fmt = date.fromisoformat(bill["due_date"]).strftime("%d.%m.%Y")
            flag = "🔴" if days < 0 else ("🟡" if days <= 3 else "⏳")
            await query.message.reply_text(
                f"{flag} <b>{reports._e(bill['service'])}</b> — {reports._fmt(bill['amount'])}\n"
                f"Срок: {due_fmt}  |  #{bill['id']}",
                reply_markup=keyboards.bill_keyboard(str(uid), bill["id"]),
                parse_mode="HTML",
            )

    elif data.startswith("u_remind:"):
        uid = int(data.split(":")[1])
        user = db.get_user(uid)
        if not user:
            await query.answer("❌ Пользователь не найден", show_alert=True)
            return
        pending = [b for b in user.get("bills", []) if b["status"] == "pending"]
        if not pending:
            await query.answer("✅ У пользователя нет долгов", show_alert=True)
            return
        sent = 0
        for bill in pending:
            try:
                await ctx.bot.send_message(
                    chat_id=user["chat_id"],
                    text=reports.reminder_message(bill),
                    parse_mode="HTML",
                )
                sent += 1
            except Exception as e:
                log.warning("remind failed %s: %s", uid, e)
        await query.answer(f"📨 Отправлено {sent} напоминаний", show_alert=True)

    elif data.startswith("u_del_ask:"):
        await query.answer()
        uid = data.split(":")[1]
        user = db.get_user(int(uid))
        name = reports.user_display_name(user) if user else uid
        await query.edit_message_text(
            f"🗑 Удалить пользователя <b>{name}</b>?\nВсе его счета тоже удалятся.",
            reply_markup=keyboards.user_delete_confirm(uid),
            parse_mode="HTML",
        )

    elif data.startswith("u_del_yes:"):
        await query.answer()
        uid = int(data.split(":")[1])
        db.remove_user(uid)
        await query.edit_message_text("🗑 Пользователь удалён.")

    elif data.startswith("u_del_no:"):
        await query.answer()
        await query.edit_message_text("❌ Отменено.")

    # ── Bill actions ──────────────────────────────────────────────────────────

    elif data.startswith("b_paid_ask:"):
        await query.answer()
        _, uid, bill_id = data.split(":")
        user = db.get_user(int(uid))
        bill = next((b for b in user["bills"] if b["id"] == bill_id), None) if user else None
        if not bill:
            await query.edit_message_text("❌ Счёт не найден.")
            return
        if bill["status"] == "paid":
            await query.edit_message_text("✅ Этот счёт уже оплачен.")
            return
        await query.edit_message_text(
            f"✅ Подтвердить оплату?\n\n"
            f"Услуга: <b>{reports._e(bill['service'])}</b>\n"
            f"Сумма по счёту: <b>{reports._fmt(bill['amount'])}</b>",
            reply_markup=keyboards.bill_paid_keyboard(uid, bill_id, bill["amount"]),
            parse_mode="HTML",
        )

    elif data.startswith("b_paid_yes:"):
        await query.answer()
        _, uid, bill_id = data.split(":")
        bill = db.mark_paid(int(uid), bill_id)
        if not bill:
            await query.edit_message_text("❌ Счёт не найден.")
            return
        user = db.get_user(int(uid))
        await query.edit_message_text(
            f"✅ <b>Оплата подтверждена</b>\n"
            f"{reports.user_display_name(user)} — "
            f"{reports._e(bill['service'])} — {reports._fmt(bill['paid_amount'])}",
            parse_mode="HTML",
        )
        try:
            await ctx.bot.send_message(
                chat_id=user["chat_id"],
                text=(
                    f"✅ <b>Платёж подтверждён!</b>\n\n"
                    f"Услуга: <b>{reports._e(bill['service'])}</b>\n"
                    f"Сумма: <b>{reports._fmt(bill['paid_amount'])}</b>\n\nСпасибо!"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            log.warning("notify paid user %s: %s", uid, e)

    elif data.startswith("b_paid_custom:"):
        await query.answer()
        _, uid, bill_id = data.split(":")
        ctx.user_data["awaiting_custom_paid"] = {"uid": uid, "bill_id": bill_id}
        await query.edit_message_text("✏️ Введи фактическую сумму оплаты (только цифры):")

    elif data.startswith("b_paid_no:"):
        await query.answer()
        await query.edit_message_text("❌ Отменено.")

    elif data.startswith("b_remind:"):
        _, uid, bill_id = data.split(":")
        user = db.get_user(int(uid))
        bill = next((b for b in user["bills"] if b["id"] == bill_id), None) if user else None
        if not bill:
            await query.answer("❌ Счёт не найден", show_alert=True)
            return
        try:
            await ctx.bot.send_message(
                chat_id=user["chat_id"],
                text=reports.reminder_message(bill),
                parse_mode="HTML",
            )
            await query.answer("📨 Напоминание отправлено", show_alert=True)
        except Exception as e:
            log.warning("remind bill %s: %s", bill_id, e)
            await query.answer("⚠️ Не удалось: пользователь не начал диалог", show_alert=True)

    elif data.startswith("b_del_ask:"):
        await query.answer()
        _, uid, bill_id = data.split(":")
        user = db.get_user(int(uid))
        bill = next((b for b in user["bills"] if b["id"] == bill_id), None) if user else None
        if not bill:
            await query.edit_message_text("❌ Счёт не найден.")
            return
        await query.edit_message_text(
            f"🗑 Удалить счёт?\n\n"
            f"<b>{reports._e(bill['service'])}</b> — {reports._fmt(bill['amount'])}\n"
            f"Пользователь: {reports.user_display_name(user)}",
            reply_markup=keyboards.bill_delete_confirm(uid, bill_id),
            parse_mode="HTML",
        )

    elif data.startswith("b_del_yes:"):
        await query.answer()
        _, uid, bill_id = data.split(":")
        db.delete_bill(int(uid), bill_id)
        await query.edit_message_text(f"🗑 Счёт #{bill_id} удалён.")

    elif data.startswith("b_del_no:"):
        await query.answer()
        await query.edit_message_text("❌ Отменено.")


# ── Bots management actions ─────────────────────────────────────────────────

async def handle_bot_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if not is_admin(update.effective_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    if data == "bm_list":
        await query.answer()

    elif data == "bm_add":
        await query.answer()
        ctx.user_data["awaiting_bot_username"] = True
        await query.edit_message_text(
            "✏️ Пришли username бота, например: @name_bot"
        )

    elif data.startswith("bm_del:"):
        await query.answer()
        username = data.split(":", 1)[1]
        db.remove_bot(username)
        bots = db.get_all_bots()
        text = "🤖 Боты не добавлены." if not bots else (
            "🤖 <b>Зарегистрированные боты:</b>\n" + "\n".join(f"• @{u}" for u in bots)
        )
        await query.edit_message_text(text, reply_markup=keyboards.bots_keyboard(), parse_mode="HTML")

    elif data.startswith("ubn_pick:"):
        await query.answer()
        uid = data.split(":", 1)[1]
        await query.edit_message_text(
            "🤖 Выбери бота для привязки пользователя:",
            reply_markup=keyboards.user_bot_select_keyboard(uid),
        )

    elif data.startswith("ubn_set:"):
        await query.answer()
        _, uid, username = data.split(":")
        username = None if username == "__none__" else username
        db.set_user_bot(int(uid), username)
        user = db.get_user(int(uid))
        label = f"@{username}" if username else "—"
        await query.edit_message_text(
            f"✅ {reports.user_display_name(user)}\nПривязанный бот: {label}",
            parse_mode="HTML",
        )


async def handle_bot_username_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Called from text handler. Returns True if message was consumed.
    Handles @username input after pressing '➕ Добавить бота'.
    """
    if not ctx.user_data.get("awaiting_bot_username"):
        return False

    text = update.message.text.strip()
    username = text.lstrip("@").strip()
    if not username or " " in username:
        await update.message.reply_text("❌ Введи корректный username, например: @name_bot")
        return True

    ctx.user_data.pop("awaiting_bot_username", None)
    db.add_bot(username)
    await update.message.reply_text(
        f"✅ Бот @{username} добавлен.",
        reply_markup=keyboards.bots_keyboard(),
    )
    return True


async def handle_custom_paid_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Called from text handler. Returns True if message was consumed.
    Handles custom paid amount after pressing '✏️ Другая сумма'.
    """
    pending = ctx.user_data.get("awaiting_custom_paid")
    if not pending:
        return False

    try:
        amount = float(update.message.text.strip().replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введи положительное число. Например: 1200")
        return True

    uid = int(pending["uid"])
    bill_id = pending["bill_id"]
    bill = db.mark_paid(uid, bill_id, amount)
    ctx.user_data.pop("awaiting_custom_paid", None)

    if not bill:
        await update.message.reply_text("❌ Счёт не найден.")
        return True

    user = db.get_user(uid)
    await update.message.reply_text(
        f"✅ <b>Оплата подтверждена</b>\n"
        f"{reports.user_display_name(user)} — "
        f"{reports._e(bill['service'])} — {reports._fmt(bill['paid_amount'])}",
        parse_mode="HTML",
    )
    try:
        await ctx.bot.send_message(
            chat_id=user["chat_id"],
            text=(
                f"✅ <b>Платёж подтверждён!</b>\n\n"
                f"Услуга: <b>{reports._e(bill['service'])}</b>\n"
                f"Сумма: <b>{reports._fmt(bill['paid_amount'])}</b>\n\nСпасибо!"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        log.warning("notify paid %s: %s", uid, e)
    return True
