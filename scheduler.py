import logging
from datetime import time
import db
import reports
from config import ADMIN_IDS

log = logging.getLogger(__name__)

REMINDER_DAYS = [7, 3, 1, 0]


async def daily_check(context):
    """Runs daily: reminds users of upcoming/overdue bills, notifies admin."""
    pending = db.get_pending_bills()
    if not pending:
        return

    reminded_users = set()
    overdue = []
    upcoming = []

    for item in pending:
        bill = item["bill"]
        user = item["user"]
        days = db.days_until(bill["due_date"])

        if days < 0:
            overdue.append(item)
        elif days in REMINDER_DAYS:
            upcoming.append(item)
            # Remind user
            if user.get("chat_id"):
                try:
                    await context.bot.send_message(
                        chat_id=user["chat_id"],
                        text=reports.reminder_message(bill),
                        parse_mode="HTML",
                    )
                    reminded_users.add(item["user_id"])
                except Exception as e:
                    log.warning("Scheduler: cannot remind %s: %s", item["user_id"], e)

    # Send admin summary
    if overdue or upcoming:
        lines = ["🔔 <b>Ежедневный отчёт по платежам</b>\n"]

        if overdue:
            lines.append(f"🔴 <b>Просрочено ({len(overdue)}):</b>")
            for item in overdue:
                u = item["user"]
                b = item["bill"]
                lines.append(
                    f"  • {reports.user_display_name(u)} — {b['service']} "
                    f"{reports._fmt(b['amount'])}"
                )

        if upcoming:
            lines.append(f"\n⏳ <b>Скоро ({len(upcoming)}):</b>")
            for item in upcoming:
                u = item["user"]
                b = item["bill"]
                days = db.days_until(b["due_date"])
                lines.append(
                    f"  • {reports.user_display_name(u)} — {b['service']} "
                    f"{reports._fmt(b['amount'])} (через {days} дн.)"
                )

        if reminded_users:
            lines.append(f"\n📨 Напоминания отправлены: {len(reminded_users)} польз.")

        summary = "\n".join(lines)
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id, text=summary, parse_mode="HTML"
                )
            except Exception as e:
                log.warning("Scheduler: cannot notify admin %s: %s", admin_id, e)


def setup(app):
    """Register scheduled jobs."""
    app.job_queue.run_daily(
        daily_check,
        time=time(hour=9, minute=0),
        name="daily_payment_check",
    )
    log.info("Scheduler: daily check registered at 09:00")
