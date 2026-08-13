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
def home(): return "Telegram Bot is Alive ✅", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

def empty_db(): return {"history": {}, "reply_map": {}, "blocked": [], "msg_map": {}, "stealth": False, "alerts": [], "selected_user": None}

def load_data():
    with db_lock:
        if not os.path.exists(DATA_FILE): return empty_db()
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: data = json.load(f)
            for key in ["history", "reply_map", "msg_map", "blocked", "alerts"]: data.setdefault(key, {} if key in ["history","reply_map","msg_map"] else [])
            data.setdefault("stealth", False); data.setdefault("selected_user", None)
            for uid in data["history"]: data["history"][uid].setdefault("u", []); data["history"][uid].setdefault("a", [])
            return data
        except: return empty_db()

def save_data(data):
    with db_lock:
        temp = DATA_FILE + ".tmp"
        try:
            with open(temp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, DATA_FILE)
        except Exception as e: logging.error(f"DB Save Error: {e}")

def ensure_user(data, user_id):
    user_id = str(user_id)
    if user_id not in data["history"]: data["history"][user_id] = {"u": [], "a": []}

def add_history(data, user_id, user_message_id=None, admin_message_id=None, admin_msg_id=None):
    user_id = str(user_id); ensure_user(data, user_id)
    if user_message_id: data["history"][user_id]["u"].append(int(user_message_id))
    if admin_message_id:
        data["history"][user_id]["a"].append(int(admin_message_id))
        if admin_msg_id: data["msg_map"][str(admin_message_id)] = {"user": int(user_id), "user_msg": int(admin_msg_id)}

def auto_delete_worker():
    while True:
        time.sleep(DELETE_INTERVAL)
        data = load_data(); changed = False
        for user_id in list(data["history"].keys()):
            history = data["history"].get(user_id, {})
            for msg_id in history.get("u", [])[:]:
                try: bot.delete_message(int(user_id), int(msg_id))
                except: pass
            for msg_id in history.get("a", [])[:]:
                try: bot.delete_message(ADMIN_ID, int(msg_id))
                except: pass
            if history.get("u") or history.get("a"):
                data["history"][user_id]["u"] = []; data["history"][user_id]["a"] = []; changed = True
        if changed: save_data(data)

@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id; data = load_data()
    if chat_id == ADMIN_ID:
        selected = f"<code>{data['selected_user']}</code>" if data['selected_user'] else "Koi nahi"
        panel = f"""🛡️ <b>ADMIN PANEL</b>
🎯 <b>Selected:</b> {selected}
<b>COMMANDS:</b>
/dm &lt;id&gt; &lt;text&gt; - Direct msg
/select &lt;id&gt; - Chat mode ON
/unselect - Chat mode OFF
/clearall - Admin ke saare msg delete
/allclear - Sab kuch delete
/users /ban /unban /alert /delete /stealthon /stealthoff"""
        bot.send_message(ADMIN_ID, panel); return

    user_id = str(chat_id)
    if user_id in data["blocked"]:
        try: bot.delete_message(chat_id, message.message_id)
        except: pass; return

    bot.send_message(chat_id, "<b>✨ Swaagat hai!</b>\nAapka sandesh team tak pahuch gaya. 🙏")
    admin_msg = bot.send_message(ADMIN_ID, f"🔔 <b>NEW MESSAGE</b>\n\n🆔 <b>From:</b> <code>{chat_id}</code>")
    data["reply_map"][str(admin_msg.message_id)] = str(chat_id); save_data(data)

@bot.message_handler(commands=["select"])
def select_user(message):
    if message.chat.id!= ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except: bot.send_message(ADMIN_ID, "⚠️ Use: <code>/select &lt;user_id&gt;</code>"); return
    data = load_data(); data["selected_user"] = user_id; save_data(data)
    bot.send_message(ADMIN_ID, f"🎯 <b>Chat Mode ON</b>\nAb sab msg <code>{user_id}</code> ko jayenge.")

@bot.message_handler(commands=["unselect"])
def unselect_user(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data(); data["selected_user"] = None; save_data(data)
    bot.send_message(ADMIN_ID, "🎯 <b>Chat Mode OFF</b>")

@bot.message_handler(commands=["dm"])
def direct_msg(message):
    if message.chat.id!= ADMIN_ID: return
    try: parts = message.text.split(" ", 2); user_id = parts[1]; text = parts[2]
    except: bot.send_message(ADMIN_ID, "⚠️ Use: <code>/dm &lt;chat_id&gt; &lt;text&gt;</code>"); return
    data = load_data()
    try:
        sent = bot.send_message(int(user_id), text)
        add_history(data, user_id, admin_message_id=sent.message_id); save_data(data)
        bot.send_message(ADMIN_ID, f"✅ Message bhej diya <code>{user_id}</code> ko")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Error: {e}\n<b>Solution:</b> User ko ye link bhej: https://t.me/{bot.get_me().username}?start={user_id}")

@bot.message_handler(commands=["clearall"])
def clearall(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data(); count = 0
    for user_id in list(data["history"].keys()):
        history = data["history"][user_id]
        for msg_id in history.get("a", []):
            try: bot.delete_message(int(user_id), int(msg_id)); count+=1
            except: pass
        for msg_id in history.get("a", []):
            try: bot.delete_message(ADMIN_ID, int(msg_id))
            except: pass
        data["history"][user_id]["a"] = []
    save_data(data); bot.send_message(ADMIN_ID, f"🧹 Admin ke {count} messages user se delete kiye gaye.")

@bot.message_handler(commands=["allclear"])
def all_clear(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data(); count = 0
    for user_id in list(data["history"].keys()):
        history = data["history"][user_id]
        for msg_id in history.get("u", []):
            try: bot.delete_message(int(user_id), int(msg_id)); count+=1
            except: pass
        for msg_id in history.get("a", []):
            try: bot.delete_message(int(user_id), int(msg_id)); count+=1
            except: pass
        for msg_id in history.get("a", []):
            try: bot.delete_message(ADMIN_ID, int(msg_id))
            except: pass
        try: bot.send_message(int(user_id), "🧹 Chat saaf kar di gayi hai.")
        except: pass
    data = empty_db(); save_data(data)
    bot.send_message(ADMIN_ID, f"💥 <b>ALL CLEAR</b>\n{count} messages delete. DB reset.")

@bot.message_handler(commands=["users"])
def users(message):
    if message.chat.id!= ADMIN_ID: return
    data = load_data(); users_list = list(data["history"].keys())
    if not users_list: bot.send_message(ADMIN_ID, "👥 Koi user nahi hai."); return
    text = "<b>👥 SAVED USERS</b>\n\n"
    for i, user_id in enumerate(users_list, 1):
        status = "⛔" if user_id in data["blocked"] else "🚨" if user_id in data["alerts"] else "✅"
        text += f"{i}. {status} 🆔 <code>{user_id}</code>\n\n"
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

SUPPORTED_TYPES = ["text","photo","video","document","audio","voice","sticker","animation"]

@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_message(message):
    chat_id = message.chat.id; message_id = message.message_id; data = load_data()

    if chat_id == ADMIN_ID:
        if data["selected_user"] and not message.reply_to_message:
            target_user = data["selected_user"]
            try:
                sent = bot.copy_message(chat_id=int(target_user), from_chat_id=ADMIN_ID, message_id=message_id)
                add_history(data, target_user, admin_message_id=sent.message_id); save_data(data)
            except Exception as e: bot.send_message(ADMIN_ID, f"❌ Error: {e}")
            return

        if not message.reply_to_message:
            bot.send_message(ADMIN_ID, "⚠️ Reply karke bheje ya /select kare"); return

        target_user = data["reply_map"].get(str(message.reply_to_message.message_id))
        if not target_user: bot.send_message(ADMIN_ID, "❌ Ye message kisi saved user ka nahi hai."); return
        if target_user in data["blocked"]: bot.send_message(ADMIN_ID, "⛔ Ye user blocked hai."); return

        reply_to_id = data["msg_map"].get(str(message.reply_to_message.message_id),{}).get("user_msg")
        try:
            sent = bot.copy_message(chat_id=int(target_user), from_chat_id=ADMIN_ID, message_id=message_id, reply_to_message_id=reply_to_id)
            add_history(data, target_user, admin_message_id=sent.message_id, admin_msg_id=message_id); save_data(data)
        except Exception as e: bot.send_message(ADMIN_ID, f"❌ Error:\n{e}")
        return

    user_id = str(chat_id)
    if user_id in data["blocked"]:
        try: bot.delete_message(chat_id, message_id)
        except: pass; return

    try:
        ensure_user(data, user_id)
        reply_to_admin = None
        if message.reply_to_message:
            reply_to_admin = data["msg_map"].get(str(message.reply_to_message.message_id),{}).get("admin_msg_id")

        copied = bot.copy_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message_id, reply_to_message_id=reply_to_admin)
        admin_message_id = copied.message_id
        data["reply_map"][str(admin_message_id)] = user_id

        bot.send_message(ADMIN_ID, f"🆔 <b>From:</b> <code>{user_id}</code>", reply_to_message_id=admin_message_id)
        add_history(data, user_id, user_message_id=message_id, admin_message_id=admin_message_id); save_data(data)
    except Exception as e: logging.error(f"User → Admin error: {e}")

@bot.edited_message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def edit_handler(message):
    chat_id = message.chat.id; message_id = message.message_id; data = load_data()

    if chat_id == ADMIN_ID:
        admin_msg_id = str(message_id)
        if admin_msg_id in data["msg_map"]:
            info = data["msg_map"][admin_msg_id]
            try: bot.edit_message_text(message.text, info["user"], info["user_msg"])
            except: pass
    else:
        user_id = str(chat_id)
        for uid, hist in data["history"].items():
            if message_id in hist.get("u", []):
                for admin_msg_id, map_info in data["msg_map"].items():
                    if map_info["user"] == int(user_id) and map_info["user_msg"] == message_id:
                        try: bot.edit_message_text(message.text, ADMIN_ID, int(admin_msg_id))
                        except: pass
                        break

def start_services():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=auto_delete_worker, daemon=True).start()
    logging.info("Bot starting...")
    # FIX: drop_pending hata diya
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    try: start_services()
    except Exception as e: logging.exception(f"Fatal Error: {e}")
