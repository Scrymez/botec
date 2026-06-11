import json
import os
import uuid
from datetime import date
from config import DB_PATH, CURRENCY

_DEFAULT = {
    "users": {},
    "bots": {},
    "settings": {
        "currency": CURRENCY,
        "reminder_days": [7, 3, 1],
    },
}


def load() -> dict:
    if not os.path.exists(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        save(_DEFAULT)
        return json.loads(json.dumps(_DEFAULT))
    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("bots", {})
    return data


def save(data: dict):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# --- Users ---

def upsert_user(user_id: int, username: str, full_name: str, chat_id: int):
    db = load()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "username": username,
            "full_name": full_name,
            "chat_id": chat_id,
            "registered_at": date.today().isoformat(),
            "bills": [],
            "bot": None,
        }
    else:
        db["users"][uid].update({"username": username, "full_name": full_name, "chat_id": chat_id})
    save(db)
    return db["users"][uid]


def get_user(user_id: int) -> dict | None:
    return load()["users"].get(str(user_id))


def get_all_users() -> dict:
    return load()["users"]


def remove_user(user_id: int) -> bool:
    db = load()
    uid = str(user_id)
    if uid in db["users"]:
        del db["users"][uid]
        save(db)
        return True
    return False


# --- Bills ---

def create_bill(user_id: int, service: str, amount: float, due_date: str, note: str = "") -> dict | None:
    db = load()
    uid = str(user_id)
    if uid not in db["users"]:
        return None
    bill = {
        "id": str(uuid.uuid4())[:8].upper(),
        "service": service,
        "amount": float(amount),
        "currency": db["settings"]["currency"],
        "issued_date": date.today().isoformat(),
        "due_date": due_date,
        "status": "pending",
        "paid_date": None,
        "paid_amount": None,
        "note": note,
    }
    db["users"][uid]["bills"].append(bill)
    save(db)
    return bill


def mark_paid(user_id: int, bill_id: str, paid_amount: float = None) -> dict | None:
    db = load()
    uid = str(user_id)
    if uid not in db["users"]:
        return None
    for bill in db["users"][uid]["bills"]:
        if bill["id"] == bill_id:
            bill["status"] = "paid"
            bill["paid_date"] = date.today().isoformat()
            bill["paid_amount"] = paid_amount if paid_amount is not None else bill["amount"]
            save(db)
            return bill
    return None


def delete_bill(user_id: int, bill_id: str) -> bool:
    db = load()
    uid = str(user_id)
    if uid not in db["users"]:
        return False
    before = len(db["users"][uid]["bills"])
    db["users"][uid]["bills"] = [b for b in db["users"][uid]["bills"] if b["id"] != bill_id]
    if len(db["users"][uid]["bills"]) < before:
        save(db)
        return True
    return False


def get_pending_bills() -> list[dict]:
    result = []
    for uid, user in load()["users"].items():
        for bill in user["bills"]:
            if bill["status"] == "pending":
                result.append({"user_id": uid, "user": user, "bill": bill})
    return result


def days_until(due_date_str: str) -> int:
    due = date.fromisoformat(due_date_str)
    return (due - date.today()).days


# --- Bots ---

def add_bot(username: str) -> dict:
    db = load()
    username = username.lstrip("@").strip()
    db["bots"][username] = {
        "username": username,
        "added_at": date.today().isoformat(),
    }
    save(db)
    return db["bots"][username]


def remove_bot(username: str) -> bool:
    db = load()
    if username not in db["bots"]:
        return False
    del db["bots"][username]
    for user in db["users"].values():
        if user.get("bot") == username:
            user["bot"] = None
    save(db)
    return True


def get_all_bots() -> dict:
    return load()["bots"]


def set_user_bot(user_id: int, bot_username: str | None) -> bool:
    db = load()
    uid = str(user_id)
    if uid not in db["users"]:
        return False
    db["users"][uid]["bot"] = bot_username
    save(db)
    return True
