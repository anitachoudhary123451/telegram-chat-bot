import os
import json
import time
import logging
import threading
from threading import Lock
from flask import Flask
import telebot

# --- ENVIRONMENT & CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Set Admin ID
DATA_FILE = "bot_data.json"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
db_lock = Lock()

# --- WEB SERVER (KEEP-ALIVE) ---
app = Flask(__name__)

@app.route("/")
def home():
    return "⚡ Gateway Service Active ✅", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# --- DATABASE CORE ---
def empty_db():
    return {
        "users": {},          # {user_id: {"admin_msgs": [], "user_msgs": []}}
        "reply_map": {},      # admin_msg_id -> user_id
        "msg_map_a2u": {},    # admin_msg_id -> user_msg_id
        "msg_map_u2a": {},    # f"{user_id}_{user_msg_id}" -> admin_msg_id
        "blocked": [],
        "alerts": [],
        "selected_user": None
    }

def load_data():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return empty_db()
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a", "blocked", "alerts"]:
                data.setdefault(k, {} if "map" in k or k == "users" else [])
            data.setdefault("selected_user", None)
            return data
        except Exception as e:
            logging.error(f"DB Load Error: {e}")
            return empty_db()

def save_data(data):
    with db_lock:
        temp = DATA_FILE + ".tmp"
        try:
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, DATA_FILE)
        except Exception as e:
            logging.error(f"DB Save Error: {e}")

def ensure_user(data, user_id):
    u_str = str(user_id)
    if u_str not in data["users"]:
        data["users"][u_str] = {"admin_msgs": [], "user_msgs": []}

SUPPORTED_TYPES = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"]

# --- ADMIN DASHBOARD & COMMANDS ---

@bot.message_handler(commands=["start"])
def handle_start(message):
    chat_id = message.chat.id
    data = load_data()

    # 👑 ADMIN INTERFACE
    if chat_id == ADMIN_ID:
        selected = f"<code>{data['selected_user']}</code>" if data['selected_user'] else "⭕ <i>None (Manual/Reply Mode)</i>"
        
        panel = f"""🎛️ <b>CONTROL CONSOLE | ADMIN</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Focused Target:</b> {selected}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📡 <b>ROUTING & MESSAGING:</b>
• <b>Reply directly</b> to any forwarded message to quote-reply.
• <code>/select &lt;user_id&gt;</code> ── Lock focus to a specific user
• <code>/unselect</code> ──────────── Release locked focus
• <code>/dm &lt;id&gt; &lt;text&gt;</code> ──────── Send instant standalone message

🧹 <b>PURGE & DELETION:</b>
• <code>/clearall &lt;id&gt;</code> ──────── Delete ALL admin messages from user's chat
• <code>/purge &lt;id&gt;</code> ─────────── Wipe entire chat (both user and admin sides)
• <code>/resetdb</code> ────────────── Reset database and session logs

👥 <b>MANAGEMENT:</b>
• <code>/users</code> ──────────────── List all active users & status
• <code>/ban &lt;id&gt;</code> ────────────── Restrict user from contacting
• <code>/unban &lt;id&gt;</code> ──────────── Restore user access
• <code>/alert &lt;id&gt;</code> ──────────── Toggle priority/alert flag
━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        bot.send_message(ADMIN_ID, panel)
        return

    # 👤 END USER WELCOME INTERFACE
    user_id = str(chat_id)
    if user_id in data["blocked"]:
        return

    ensure_user(data, user_id)
    save_data(data)

    welcome_text = """🔒 <b>ENCRYPTED SECURE CHANNEL</b>

<blockquote>Aapka direct communication session establish ho chuka hai. 

Aap yahan apna koi bhi message, photo, ya document bhej sakte hain. Hamaari team aapse isi chat me connect karegi.</blockquote>

💬 <i>Apna sandesh niche type karke send karein.</i>"""
    bot.send_message(chat_id, welcome_text)

@bot.message_handler(commands=["select"])
def select_user(message):
    if message.chat.id != ADMIN_ID: return
    try:
        user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/select &lt;user_id&gt;</code>")
        return
    data = load_data()
    data["selected_user"] = str(user_id)
    save_data(data)
    bot.send_message(ADMIN_ID, f"🎯 <b>Focus Locked:</b> <code>{user_id}</code>. Messages without reply will be delivered here.")

@bot.message_handler(commands=["unselect"])
def unselect_user(message):
    if message.chat.id != ADMIN_ID: return
    data = load_data()
    data["selected_user"] = None
    save_data(data)
    bot.send_message(ADMIN_ID, "🎯 <b>Focus Released.</b> Manual/Reply mode active.")

@bot.message_handler(commands=["dm"])
def direct_message(message):
    if message.chat.id != ADMIN_ID: return
    try:
        parts = message.text.split(" ", 2)
        user_id, text = parts[1], parts[2]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/dm &lt;user_id&gt; &lt;text&gt;</code>")
        return
    data = load_data()
    try:
        sent = bot.send_message(int(user_id), text)
        ensure_user(data, user_id)
        data["users"][str(user_id)]["admin_msgs"].append(sent.message_id)
        save_data(data)
        bot.send_message(ADMIN_ID, f"✅ <b>Sent to</b> <code>{user_id}</code>")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>Delivery Error:</b> {e}")

@bot.message_handler(commands=["clearall"])
def clear_admin_messages(message):
    """Deletes all messages sent by Admin from the target user's chat."""
    if message.chat.id != ADMIN_ID: return
    try:
        user_id = message.text.split()[1]
    except IndexError:
        # Fallback to selected user if argument missing
        data = load_data()
        user_id = data.get("selected_user")
        if not user_id:
            bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/clearall &lt;user_id&gt;</code>")
            return

    data = load_data()
    user_str = str(user_id)
    if user_str not in data["users"]:
        bot.send_message(ADMIN_ID, "⚠️ No message history found for this user.")
        return

    admin_msgs = data["users"][user_str].get("admin_msgs", [])
    count = 0
    for msg_id in admin_msgs:
        try:
            bot.delete_message(chat_id=int(user_str), message_id=msg_id)
            count += 1
        except Exception:
            pass

    data["users"][user_str]["admin_msgs"] = []
    save_data(data)
    bot.send_message(ADMIN_ID, f"🧹 <b>Cleared:</b> {count} Admin messages deleted from <code>{user_str}</code>'s chat.")

@bot.message_handler(commands=["purge"])
def purge_chat(message):
    """Deletes both Admin and User messages from user chat and local logs."""
    if message.chat.id != ADMIN_ID: return
    try:
        user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/purge &lt;user_id&gt;</code>")
        return

    data = load_data()
    user_str = str(user_id)
    if user_str not in data["users"]:
        bot.send_message(ADMIN_ID, "⚠️ User history not found.")
        return

    total = 0
    # Clean user msgs
    for msg_id in data["users"][user_str].get("user_msgs", []):
        try:
            bot.delete_message(chat_id=int(user_str), message_id=msg_id)
            total += 1
        except Exception: pass
    
    # Clean admin msgs
    for msg_id in data["users"][user_str].get("admin_msgs", []):
        try:
            bot.delete_message(chat_id=int(user_str), message_id=msg_id)
            total += 1
        except Exception: pass

    data["users"][user_str] = {"admin_msgs": [], "user_msgs": []}
    save_data(data)
    bot.send_message(ADMIN_ID, f"💥 <b>Purged:</b> {total} total messages cleared from <code>{user_str}</code>'s chat.")

@bot.message_handler(commands=["resetdb"])
def reset_database(message):
    if message.chat.id != ADMIN_ID: return
    data = empty_db()
    save_data(data)
    bot.send_message(ADMIN_ID, "♻️ <b>Database Reset:</b> All state logs and mappings cleared.")

@bot.message_handler(commands=["users"])
def list_users(message):
    if message.chat.id != ADMIN_ID: return
    data = load_data()
    users_dict = data.get("users", {})
    if not users_dict:
        bot.send_message(ADMIN_ID, "👥 <b>No registered users found.</b>")
        return

    text = "📊 <b>USER DIRECTORY</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, u_id in enumerate(users_dict.keys(), 1):
        status = "⛔ [Banned]" if u_id in data["blocked"] else "🚨 [Flagged]" if u_id in data["alerts"] else "🟢 [Active]"
        text += f"{i}. <code>{u_id}</code> ── {status}\n"
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=["ban"])
def ban_user(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/ban &lt;user_id&gt;</code>"); return
    data = load_data()
    if user_id not in data["blocked"]:
        data["blocked"].append(user_id)
        save_data(data)
        bot.send_message(ADMIN_ID, f"⛔ User <code>{user_id}</code> is now blocked.")
    else:
        bot.send_message(ADMIN_ID, "⚠️ User is already blocked.")

@bot.message_handler(commands=["unban"])
def unban_user(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/unban &lt;user_id&gt;</code>"); return
    data = load_data()
    if user_id in data["blocked"]:
        data["blocked"].remove(user_id)
        save_data(data)
        bot.send_message(ADMIN_ID, f"✅ User <code>{user_id}</code> unblocked.")
    else:
        bot.send_message(ADMIN_ID, "⚠️ User is not blocked.")

@bot.message_handler(commands=["alert"])
def toggle_alert(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/alert &lt;user_id&gt;</code>"); return
    data = load_data()
    if user_id not in data["alerts"]:
        data["alerts"].append(user_id)
        save_data(data)
        bot.send_message(ADMIN_ID, f"🚨 Alert flag ADDED to <code>{user_id}</code>.")
    else:
        data["alerts"].remove(user_id)
        save_data(data)
        bot.send_message(ADMIN_ID, f"🏳️ Alert flag REMOVED from <code>{user_id}</code>.")

# --- CORE ROUTING ENGINE & NATIVE QUOTE REPLIES ---

@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_all_messages(message):
    chat_id = message.chat.id
    message_id = message.message_id
    data = load_data()

    # 1. OUTGOING ROUTE: ADMIN -> USER
    if chat_id == ADMIN_ID:
        target_user = None
        target_quote_id = None

        # Scenario A: Admin is replying to a forwarded message in Admin chat
        if message.reply_to_message:
            replied_admin_id = str(message.reply_to_message.message_id)
            target_user = data["reply_map"].get(replied_admin_id)
            target_quote_id = data["msg_map_a2u"].get(replied_admin_id)

        # Scenario B: Admin uses /select target
        elif data.get("selected_user"):
            target_user = data["selected_user"]

        if not target_user:
            bot.send_message(ADMIN_ID, "⚠️ <b>Action Required:</b> Reply directly to a user's message, or select one via <code>/select &lt;id&gt;</code>")
            return

        if target_user in data["blocked"]:
            bot.send_message(ADMIN_ID, "⛔ Delivery failed: User is blocked.")
            return

        try:
            # Copy message to User without admin profile trace + Native quote mention
            sent = bot.copy_message(
                chat_id=int(target_user),
                from_chat_id=ADMIN_ID,
                message_id=message_id,
                reply_to_message_id=target_quote_id
            )

            ensure_user(data, target_user)
            data["users"][str(target_user)]["admin_msgs"].append(sent.message_id)

            # Store cross-reply reference
            admin_msg_str = str(message_id)
            data["msg_map_u2a"][f"{target_user}_{sent.message_id}"] = message_id
            data["msg_map_a2u"][admin_msg_str] = sent.message_id
            data["reply_map"][admin_msg_str] = str(target_user)
            save_data(data)

        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ <b>Send Failed:</b> {e}")
        return

    # 2. INCOMING ROUTE: USER -> ADMIN
    user_id = str(chat_id)
    if user_id in data["blocked"]:
        return

    ensure_user(data, user_id)
    data["users"][user_id]["user_msgs"].append(message_id)

    reply_to_admin_msg_id = None

    # Handle user replying to bot's prior message (Quote linking)
    if message.reply_to_message:
        user_replied_to = message.reply_to_message.message_id
        lookup_key = f"{user_id}_{user_replied_to}"
        reply_to_admin_msg_id = data["msg_map_u2a"].get(lookup_key)

    try:
        # Standard Forward: Reveals user profile & details to Admin
        forwarded = bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=chat_id,
            message_id=message_id
        )

        admin_forward_id = str(forwarded.message_id)

        # Store dual mappings
        data["reply_map"][admin_forward_id] = user_id
        data["msg_map_a2u"][admin_forward_id] = message_id
        data["msg_map_u2a"][f"{user_id}_{message_id}"] = forwarded.message_id

        # Alert header tag if marked
        if user_id in data["alerts"]:
            bot.send_message(ADMIN_ID, f"🚨 <b>ALERT: Flagged User Active</b> [<code>{user_id}</code>]", reply_to_message_id=forwarded.message_id)

        save_data(data)

    except Exception as e:
        logging.error(f"Inbound routing error: {e}")

# --- MESSAGE EDIT SYNCHRONIZATION ---

@bot.edited_message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_edits(message):
    chat_id = message.chat.id
    message_id = message.message_id
    data = load_data()

    if chat_id == ADMIN_ID:
        user_target_msg_id = data["msg_map_a2u"].get(str(message_id))
        target_user = data["reply_map"].get(str(message_id))
        if user_target_msg_id and target_user:
            try:
                bot.edit_message_text(message.text, int(target_user), int(user_target_msg_id))
            except Exception: pass
    else:
        user_id = str(chat_id)
        admin_ref_id = data["msg_map_u2a"].get(f"{user_id}_{message_id}")
        if admin_ref_id:
            try:
                bot.send_message(ADMIN_ID, f"✏️ <b>[User Edited Message]:</b>\n{message.text}", reply_to_message_id=int(admin_ref_id))
            except Exception: pass

# --- APP STARTUP ---

def start_services():
    threading.Thread(target=run_flask, daemon=True).start()
    logging.info("Core Gateway Server Running...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    try:
        start_services()
    except Exception as e:
        logging.exception(f"Fatal Service Error: {e}")
