import os
import json
import logging
import threading
from flask import Flask
import telebot

# Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) 
USERS_FILE = "registered_users.json"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- Flask Keep-Alive Server ---
app = Flask(__name__)

@app.route("/")
def home():
    return "⚡ Light-Weight Anonymous Bot is Running ✅", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# --- Simple User ID Storage ---
db_lock = threading.Lock()

def load_users():
    with db_lock:
        if not os.path.exists(USERS_FILE):
            return {"users": [], "blocked": [], "selected_user": None}
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading users: {e}")
            return {"users": [], "blocked": [], "selected_user": None}

def save_users(data):
    with db_lock:
        try:
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Error saving users: {e}")

def register_user(user_id):
    data = load_users()
    user_str = str(user_id)
    if user_str not in data["users"]:
        data["users"].append(user_str)
        save_users(data)

SUPPORTED_TYPES = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"]

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id
    data = load_users()

    # 👑 ADMIN PANEL
    if chat_id == ADMIN_ID:
        selected = f"<code>{data.get('selected_user')}</code>" if data.get('selected_user') else "⭕ <i>None</i>"
        panel = f"""⚡ <b>LIGHTWEIGHT ADMIN CONTROL</b> ⚡
━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 <b>Selected Target:</b> {selected}

<b>COMMANDS:</b>
├ <code>/dm &lt;user_id&gt; &lt;text&gt;</code> ─ Direct Message (Kabhi bhi bhejne ke liye)
├ <code>/select &lt;user_id&gt;</code> ────── Direct Chat Lock
├ <code>/unselect</code> ───────────── Target Unlock
├ <code>/users</code> ────────────── All Registered Chat IDs List
├ <code>/ban &lt;user_id&gt;</code> ──────── Block User
└ <code>/unban &lt;user_id&gt;</code> ────── Unblock User
━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        bot.send_message(ADMIN_ID, panel)
        return

    # 👤 USER START
    user_id = str(chat_id)
    if user_id in data.get("blocked", []):
        return

    # Register user chat_id for future DM access
    register_user(user_id)

    welcome_msg = """🔒 <b>END-TO-END ANONYMOUS PORTAL</b>

<blockquote>Aapka connection hamaare system ke sath successfully establish ho chuka hai. 

🛡️ <b>Security Protocol:</b>
• Aapke dwara bheje gaye sabhi messages <b>fully encrypted</b> aur <b>anonymous</b> hain.
• Aapki identity kisi ke sath share nahi ki jaati.</blockquote>

✨ <i>Apna message niche type karke bhejein.</i>"""
    
    bot.send_message(chat_id, welcome_msg)
    
    # Notify Admin
    bot.send_message(
        ADMIN_ID, 
        f"⚡ <b>NEW USER REGISTERED</b>\n\n🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n👤 <b>Username:</b> @{message.from_user.username or 'N/A'}"
    )

@bot.message_handler(commands=["dm"])
def direct_msg(message):
    if message.chat.id != ADMIN_ID: return
    try:
        parts = message.text.split(" ", 2)
        user_id, text = parts[1], parts[2]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Usage:</b> <code>/dm &lt;user_id&gt; &lt;text&gt;</code>")
        return
    try:
        bot.send_message(int(user_id), text)
        bot.send_message(ADMIN_ID, f"✅ Message sent to <code>{user_id}</code>")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>Failed:</b> {e}\n(Kya pata user ne bot block kar diya ho?)")

@bot.message_handler(commands=["select"])
def select_user(message):
    if message.chat.id != ADMIN_ID: return
    try:
        user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Usage:</b> <code>/select &lt;user_id&gt;</code>")
        return
    data = load_users()
    data["selected_user"] = user_id
    save_users(data)
    bot.send_message(ADMIN_ID, f"🎯 Target Locked on <code>{user_id}</code>!")

@bot.message_handler(commands=["unselect"])
def unselect_user(message):
    if message.chat.id != ADMIN_ID: return
    data = load_users()
    data["selected_user"] = None
    save_users(data)
    bot.send_message(ADMIN_ID, "🎯 Target Unlocked.")

@bot.message_handler(commands=["users"])
def users_list(message):
    if message.chat.id != ADMIN_ID: return
    data = load_users()
    u_list = data.get("users", [])
    if not u_list:
        bot.send_message(ADMIN_ID, "👥 Koi user registered nahi hai.")
        return
    
    text = f"📊 <b>TOTAL REGISTERED USERS ({len(u_list)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, u_id in enumerate(u_list, 1):
        status = "⛔ [Banned]" if u_id in data.get("blocked", []) else "🟢 [Active]"
        text += f"{i}. <code>{u_id}</code> — {status}\n"
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=["ban"])
def ban_user(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Usage:</b> <code>/ban &lt;user_id&gt;</code>"); return
    data = load_users()
    if user_id not in data["blocked"]:
        data["blocked"].append(user_id)
        save_users(data)
        bot.send_message(ADMIN_ID, f"⛔ User <code>{user_id}</code> banned.")
    else:
        bot.send_message(ADMIN_ID, "⚠️ User pehle se banned hai.")

@bot.message_handler(commands=["unban"])
def unban_user(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Usage:</b> <code>/unban &lt;user_id&gt;</code>"); return
    data = load_users()
    if user_id in data["blocked"]:
        data["blocked"].remove(user_id)
        save_users(data)
        bot.send_message(ADMIN_ID, f"✅ User <code>{user_id}</code> unbanned.")

# --- MESSAGE ROUTING (ZERO DATA SAVED) ---

@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_messages(message):
    chat_id = message.chat.id
    data = load_users()

    # 1. ADMIN TO USER
    if chat_id == ADMIN_ID:
        target_user = data.get("selected_user")

        if not target_user:
            bot.send_message(ADMIN_ID, "⚠️ Pehle <code>/select &lt;user_id&gt;</code> karein ya <code>/dm &lt;user_id&gt; &lt;text&gt;</code> use karein.")
            return

        try:
            bot.copy_message(chat_id=int(target_user), from_chat_id=ADMIN_ID, message_id=message.message_id)
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ Message nahi gaya: {e}")
        return

    # 2. USER TO ADMIN
    user_id = str(chat_id)
    if user_id in data.get("blocked", []):
        return

    # Auto-register if not present
    register_user(user_id)

    try:
        # Direct Copy Message to Admin with User ID Tag
        bot.copy_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message.message_id)
        bot.send_message(ADMIN_ID, f"📩 <b>MSG FROM:</b> <code>{user_id}</code>")
    except Exception as e:
        logging.error(f"Routing Error: {e}")

# --- START SERVICES ---

def start_services():
    threading.Thread(target=run_flask, daemon=True).start()
    logging.info("Lightweight Bot Engine Started...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    try:
        start_services()
    except Exception as e:
        logging.exception(f"Fatal Startup Error: {e}")
