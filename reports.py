from datetime import date
import db
from config import CURRENCY_SYMBOL


def _fmt(amount: float) -> str:
    return f"{amount:,.0f} {CURRENCY_SYMBOL}".replace(",", " ")


def _bill_status_line(bill: dict) -> str:
    days = db.days_until(bill["due_date"])
    due_fmt = date.fromisoformat(bill["due_date"]).strftime("%d.%m.%Y")

    if bill["status"] == "paid":
        paid_fmt = date.fromisoformat(bill["paid_date"]).strftime("%d.%m.%Y")
        return f"  ✅ {bill['service']} — {_fmt(bill['paid_amount'])} <i>(оплачено {paid_fmt})</i>"
    elif days < 0:
        return f"  🔴 {bill['service']} — {_fmt(bill['amount'])} <b>[просрочено {due_fmt}]</b> #{bill['id']}"
    elif days <= 3:
        return f"  🟡 {bill['service']} — {_fmt(bill['amount'])} <b>[до {due_fmt}, осталось {days}д]</b> #{bill['id']}"
    else:
        return f"  ⏳ {bill['service']} — {_fmt(bill['amount'])} [до {due_fmt}] #{bill['id']}"


def user_display_name(user: dict) -> str:
    name = user.get("full_name") or user.get("username") or "Без имени"
    uname = f" (@{user['username']})" if user.get("username") else ""
    return f"{name}{uname}"


def full_report() -> str:
    users = db.get_all_users()
    if not users:
        return "📭 Пользователей нет."

    total_expected = 0.0
    total_paid = 0.0
    total_pending = 0.0
    overdue_count = 0

    lines = []

    for uid, user in users.items():
        bills = user.get("bills", [])
        if not bills:
            continue

        u_expected = sum(b["amount"] for b in bills)
        u_paid = sum(b["paid_amount"] or 0 for b in bills if b["status"] == "paid")
        u_pending = sum(b["amount"] for b in bills if b["status"] == "pending")
        u_overdue = [b for b in bills if b["status"] == "pending" and db.days_until(b["due_date"]) < 0]

        total_expected += u_expected
        total_paid += u_paid
        total_pending += u_pending
        overdue_count += len(u_overdue)

        block = f"\n👤 <b>{user_display_name(user)}</b>\n"
        block += f"   Начислено: {_fmt(u_expected)} | Оплачено: {_fmt(u_paid)} | Долг: {_fmt(u_pending)}\n"
        for bill in sorted(bills, key=lambda b: b["due_date"]):
            block += _bill_status_line(bill) + "\n"
        lines.append(block)

    header = (
        "📊 <b>БЮДЖЕТНЫЙ ОТЧЁТ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Начислено всего:  <b>{_fmt(total_expected)}</b>\n"
        f"✅ Оплачено:         <b>{_fmt(total_paid)}</b>\n"
        f"⏳ Ожидает оплаты:  <b>{_fmt(total_pending)}</b>\n"
    )
    if overdue_count:
        header += f"🔴 Просрочено счетов: <b>{overdue_count}</b>\n"
    header += "━━━━━━━━━━━━━━━━━━━━━━"

    return header + "".join(lines)


def user_report(user_id: int) -> str:
    user = db.get_user(user_id)
    if not user:
        return "Пользователь не найден."

    bills = user.get("bills", [])
    if not bills:
        return f"👤 {user_display_name(user)}\n\nСчетов нет."

    pending = [b for b in bills if b["status"] == "pending"]
    paid = [b for b in bills if b["status"] == "paid"]

    total_pending = sum(b["amount"] for b in pending)
    total_paid = sum(b["paid_amount"] or 0 for b in paid)

    text = (
        f"👤 <b>{user_display_name(user)}</b>\n"
        f"Ожидает оплаты: <b>{_fmt(total_pending)}</b> | Оплачено: <b>{_fmt(total_paid)}</b>\n\n"
    )

    if pending:
        text += "<b>⏳ Активные счета:</b>\n"
        for bill in sorted(pending, key=lambda b: b["due_date"]):
            text += _bill_status_line(bill) + "\n"

    if paid:
        text += "\n<b>✅ Оплаченные:</b>\n"
        for bill in sorted(paid, key=lambda b: b.get("paid_date", ""), reverse=True):
            text += _bill_status_line(bill) + "\n"

    return text


def reminder_message(bill: dict) -> str:
    days = db.days_until(bill["due_date"])
    due_fmt = date.fromisoformat(bill["due_date"]).strftime("%d.%m.%Y")
    amt = _fmt(bill["amount"])

    if days < 0:
        return (
            f"🔴 <b>Просроченный платёж!</b>\n\n"
            f"Услуга: <b>{bill['service']}</b>\n"
            f"Сумма: <b>{amt}</b>\n"
            f"Срок истёк: <b>{due_fmt}</b>\n\n"
            f"Просьба оплатить как можно скорее.\n"
            f"ID счёта: <code>{bill['id']}</code>"
        )
    elif days == 0:
        return (
            f"⚠️ <b>Оплата сегодня!</b>\n\n"
            f"Услуга: <b>{bill['service']}</b>\n"
            f"Сумма: <b>{amt}</b>\n\n"
            f"ID счёта: <code>{bill['id']}</code>"
        )
    else:
        return (
            f"💳 <b>Напоминание об оплате</b>\n\n"
            f"Услуга: <b>{bill['service']}</b>\n"
            f"Сумма: <b>{amt}</b>\n"
            f"Срок оплаты: <b>{due_fmt}</b> (через {days} дн.)\n\n"
            f"ID счёта: <code>{bill['id']}</code>"
        )
