import telebot
import json
import os
import logging
import threading
import time
from threading import Lock
from flask import Flask
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8940270305

DATA_FILE = "bot_data.json"
DELETE_INTERVAL = 86400 # 24 ghante

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
db_lock = Lock()

app = Flask(__name__)

@app.route("/")
def home():
    return "Telegram Bot is Alive ✅", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

def empty_db():
    return {"history": {}, "reply_map": {}, "blocked": [], "msg_map": {}, "stealth": False, "alerts": []}

def load_data():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return empty_db()
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in ["history", "reply_map", "msg_map", "blocked", "alerts"]:
                data.setdefault(key, {} if key in ["history","reply_map","msg_map"] else [])
            data.setdefault("stealth", False)
            for uid in data["history"]:
                data["history"][uid].setdefault("name", "Unknown")
                data["history"][uid].setdefault("username", "N/A")
                data["history"][uid].setdefault("u", [])
                data["history"][uid].setdefault("a", [])
            return data
        except Exception as e:
            logging.error(f"DB Read Error: {e}")
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
    user_id = str(user_id)
    if user_id not in data["history"]:
        data["history"][user_id] = {"u": [], "a": [], "name": "Unknown", "username": "N/A"}

def add_history(data, user_id, user_message_id=None, admin_message_id=None, admin_msg_id=None, name="Unknown", username="N/A"):
    user_id = str(user_id)
    ensure_user(data, user_id)
    data["history"][user_id]["name"] = name
    data["history"][user_id]["username"] = username
    if user_message_id is not None:
        data["history"][user_id]["u"].append(int(user_message_id))
    if admin_message_id is not None:
        data["history"][user_id]["a"].append(int(admin_message_id))
        if admin_msg_id:
            data["msg_map"][str(admin_message_id)] = {"user": int(user_id), "user_msg": int(admin_msg_id)}

def auto_delete_worker():
    while True:
        time.sleep(DELETE_INTERVAL)
        data = load_data()
        changed = False
        for user_id in list(data["history"].keys()):
            history = data["history"].get(user_id, {})
            for msg_id in history.get("u", [])[:]:
                try: bot.delete_message(int(user_id), int(msg_id))
                except: pass
            for msg_id in history.get("a", [])[:]:
                try: bot.delete_message(ADMIN_ID, int(msg_id))
                except: pass
            if history.get("u") or history.get("a"):
                data["history"][user_id]["u"] = []
                data["history"][user_id]["a"] = []
                changed = True
        if changed: save_data(data)

@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id
    data = load_data()
    if chat_id == ADMIN_ID:
        stealth_status = "🟢 ON" if data["stealth"] else "🔴 OFF"
        alert_count = len(data["alerts"])
        panel = f"""🛡️ <b>ADMIN CONTROL PANEL</b>

↩️ <b>Reply</b> karke user ko jawab do
🕵️ <b>Stealth:</b> {stealth_status}
🚨 <b>Active Alerts:</b> {alert_count}

<b>COMMANDS:</b>
👥 /users - Saare users
📨 /msg &lt;id&gt; &lt;text&gt; - Direct msg
🚫 /blocked - Blocked list
⛔ /ban &lt;id&gt; - Ban user
✅ /unban &lt;id&gt; - Unban user
🗑️ /delete &lt;id&gt; - 1 User ki chat delete
🚨 /alert &lt;id&gt; - VIP Alert ON/OFF
🧹 /clearall - 24hr auto delete
💥 /allclear - SAB KUCH TURANT DELETE
🕵️ /stealthon - Anonymous reply ON
🕵️ /stealthoff - Anonymous reply OFF

⏱️ AutoDelete: 24 Hours"""
        bot.send_message(ADMIN_ID, panel)
        return

    user_id = str(chat_id)
    if user_id in data["blocked"]:
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        return

    name = message.from_user.first_name or "No Name"
    username = f"@{message.from_user.username}" if message.from_user.username else "N/A"
    ensure_user(data, chat_id)
    data["history"][user_id]["name"] = name
    data["history"][user_id]["username"] = username

    welcome = f"""<b>✨ Swaagat hai {name}!</b>

Aapka sandesh surakshit roop se hamare team tak pahucha diya gaya hai.
Humein aapse jald hi sampark kiya jayega.

Dhanyavaad 🙏"""
    bot.send_message(chat_id, welcome)

    time_now = datetime.now().strftime("%d-%m-%Y %H:%M")
    alert_text = " 🚨 <b>VIP ALERT</b>" if user_id in data["alerts"] else ""
    admin_msg = bot.send_message(ADMIN_ID, f"🔔 <b>NEW MESSAGE</b>{alert_text}\n\n👤 <b>Name:</b> {name}\n🆔 <b>ID:</b> <code>{chat_id}</code>\n👤 <b>Username:</b> {username}\n🕐 <b>Time:</b> {time_now}")

    data["reply_map"][str(admin_msg.message_id)] = str(chat_id)
    save_data(data)

@bot.message_handler(commands=["allclear"])
def all_clear(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data()
    count = 0
    for user_id in list(data["history"].keys()):
        history = data["history"][user_id]
        for msg_id in history.get("u", []):
            try: bot.delete_message(int(user_id), int(msg_id)); count+=1
            except: pass
        for msg_id in history.get("a", []):
            try: bot.delete_message(ADMIN_ID, int(msg_id)); count+=1
            except: pass
        try: bot.send_message(int(user_id), "🧹 Chat saaf kar di gayi hai.")
        except: pass

    data = empty_db()
    save_data(data)
    bot.send_message(ADMIN_ID, f"💥 <b>ALL CLEAR COMPLETE</b>\n\n{count} messages dono taraf se delete.\nDB reset ho gaya.")

@bot.message_handler(commands=["alert"])
def toggle_alert(message):
    if message.chat.id!= ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except: bot.send_message(ADMIN_ID, "⚠️ Use: <code>/alert &lt;user_id&gt;</code>"); return
    data = load_data()
    if user_id in data["alerts"]:
        data["alerts"].remove(user_id); msg = f"🔕 Alert OFF for <code>{user_id}</code>"
    else:
        data["alerts"].append(user_id); msg = f"🚨 Alert ON for <code>{user_id}</code>"
    save_data(data); bot.send_message(ADMIN_ID, msg)

@bot.message_handler(commands=["delete"])
def delete_user(message):
    if message.chat.id!= ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except: bot.send_message(ADMIN_ID, "⚠️ Use: <code>/delete &lt;user_id&gt;</code>"); return
    data = load_data()
    if user_id not in data["history"]: bot.send_message(ADMIN_ID, "❌ User mila nahi."); return
    count = 0
    history = data["history"][user_id]
    for msg_id in history.get("u", []):
        try: bot.delete_message(int(user_id), int(msg_id)); count+=1
        except: pass
    for msg_id in history.get("a", []):
        try: bot.delete_message(ADMIN_ID, int(msg_id)); count+=1
        except: pass
    del data["history"][user_id]
    if user_id in data["alerts"]: data["alerts"].remove(user_id)
    save_data(data); bot.send_message(ADMIN_ID, f"🗑️ User <code>{user_id}</code> ki {count} messages delete.")

@bot.message_handler(commands=["stealthon"])
def stealth_on(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data(); data["stealth"] = True; save_data(data)
    bot.send_message(ADMIN_ID, "🕵️ <b>Stealth Mode ON</b>\nAb reply anonymous jayenge.")

@bot.message_handler(commands=["stealthoff"])
def stealth_off(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data(); data["stealth"] = False; save_data(data)
    bot.send_message(ADMIN_ID, "🔴 <b>Stealth Mode OFF</b>\nAb normal copy reply jayega.")

@bot.message_handler(commands=["users"])
def users(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data(); users_list = list(data["history"].keys())
    if not users_list: bot.send_message(ADMIN_ID, "👥 Koi user nahi hai."); return
    text = "<b>👥 SAVED USERS</b>\n\n"
    for i, user_id in enumerate(users_list, 1):
        name = data["history"][user_id].get("name", "Unknown")
        status = "⛔" if user_id in data["blocked"] else "🚨" if user_id in data["alerts"] else "✅"
        text += f"{i}. {status} <b>{name}</b>\n🆔 <code>{user_id}</code>\n\n"
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=["blocked"])
def blocked(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data()
    if not data["blocked"]: bot.send_message(ADMIN_ID, "🚫 Koi blocked user nahi hai."); return
    text = "<b>🚫 BLOCKED USERS</b>\n"
    for i, user_id in enumerate(data["blocked"], 1):
        name = data["history"].get(user_id, {}).get("name", "Unknown")
        text += f"{i}. <b>{name}</b>\n🆔 <code>{user_id}</code>\n\n"
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=["ban"])
def ban(message):
    if message.chat.id!= ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except: bot.send_message(ADMIN_ID, "⚠️ Use: <code>/ban &lt;user_id&gt;</code>"); return
    data = load_data()
    if user_id not in data["blocked"]:
        data["blocked"].append(user_id); save_data(data)
        bot.send_message(ADMIN_ID, f"⛔ User <code>{user_id}</code> ban.")
        try: bot.send_message(int(user_id), "⛔ Aapko block kar diya gaya hai.")
        except: pass
    else: bot.send_message(ADMIN_ID, "⚠️ User pehle se banned hai.")

@bot.message_handler(commands=["unban"])
def unban(message):
    if message.chat.id!= ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except: bot.send_message(ADMIN_ID, "⚠️ Use: <code>/unban &lt;user_id&gt;</code>"); return
    data = load_data()
    if user_id in data["blocked"]:
        data["blocked"].remove(user_id); save_data(data)
        bot.send_message(ADMIN_ID, f"✅ User <code>{user_id}</code> unban.")
    else: bot.send_message(ADMIN_ID, "⚠️ User banned nahi hai.")

@bot.message_handler(commands=["msg"])
def send_msg(message):
    if message.chat.id!= ADMIN_ID: return
    try: parts = message.text.split(" ", 2); user_id = parts[1]; text = parts[2]
    except: bot.send_message(ADMIN_ID, "⚠️ Use: <code>/msg &lt;user_id&gt; &lt;text&gt;</code>"); return
    data = load_data()
    try:
        sent = bot.send_message(int(user_id), text)
        add_history(data, user_id, admin_message_id=sent.message_id)
        save_data(data); bot.send_message(ADMIN_ID, f"✅ Message bhej diya <code>{user_id}</code> ko")
    except Exception as e: bot.send_message(ADMIN_ID, f"❌ Error: {e}")

@bot.message_handler(commands=["clearall"])
def clearall(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data(); count = 0
    for user_id in data["history"]:
        history = data["history"][user_id]
        for msg_id in history.get("u", []):
            try: bot.delete_message(int(user_id), int(msg_id)); count+=1
            except: pass
        for msg_id in history.get("a", []):
            try: bot.delete_message(ADMIN_ID, int(msg_id)); count+=1
            except: pass
        data["history"][user_id]["u"] = []; data["history"][user_id]["a"] = []
    save_data(data); bot.send_message(ADMIN_ID, f"🧹 {count} messages delete kiye gaye.")

SUPPORTED_TYPES = ["text","photo","video","document","audio","voice","sticker","animation","contact","location"]

@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_message(message):
    chat_id = message.chat.id; message_id = message.message_id; data = load_data()

    if chat_id == ADMIN_ID:
        if not message.reply_to_message:
            bot.send_message(ADMIN_ID, "⚠️ User ke message par Reply karke jawab bheje."); return

        target_user = data["reply_map"].get(str(message.reply_to_message.message_id))
        if not target_user: bot.send_message(ADMIN_ID, "❌ Ye message kisi saved user ka nahi hai."); return
        if target_user in data["blocked"]: bot.send_message(ADMIN_ID, "⛔ Ye user blocked hai."); return

        try:
            sent = bot.copy_message(chat_id=int(target_user), from_chat_id=ADMIN_ID, message_id=message_id)
            add_history(data, target_user, admin_message_id=sent.message_id, admin_msg_id=message_id)
            save_data(data)
        except Exception as e:
            logging.error(f"Admin → User error: {e}"); bot.send_message(ADMIN_ID, f"❌ Error:\n{e}")
        return

    user_id = str(chat_id)
    if user_id in data["blocked"]:
        try: bot.delete_message(chat_id, message_id)
        except: pass
        return

    name = message.from_user.first_name or "No Name"
    username = f"@{message.from_user.username}" if message.from_user.username else "N/A"
    try:
        ensure_user(data, user_id)

        copied = bot.copy_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message_id)
        admin_message_id = copied.message_id
        data["reply_map"][str(admin_message_id)] = user_id

        bot.send_message(ADMIN_ID, f"👤 <b>From:</b> {name} | 🆔 <code>{user_id}</code>", reply_to_message_id=admin_message_id)

        add_history(data, user_id, user_message_id=message_id, admin_message_id=admin_message_id, name=name, username=username)
        save_data(data)
    except Exception as e: logging.error(f"User → Admin error: {e}")

@bot.edited_message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def edit_handler(message):
    data = load_data(); admin_msg_id = str(message.message_id)
    if admin_msg_id in data["msg_map"]:
        info = data["msg_map"][admin_msg_id]
        try: bot.edit_message_text(message.text, info["user"], info["user_msg"])
        except: pass

def start_services():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=auto_delete_worker, daemon=True).start()
    logging.info("Bot starting...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    try: start_services()
    except KeyboardInterrupt: logging.info("Bot stopped.")
    except Exception as e: logging.exception(f"Fatal Error: {e}")