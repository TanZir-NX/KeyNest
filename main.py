# main.py
import os
import sqlite3
import threading
import datetime
import telebot
from flask import Flask

# ----------------- Configuration & Env ----------------- #
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = os.environ.get("ADMIN_IDS", "")
DB_FILE = "data.db"

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

user_states = {}

# ----------------- Database Setup ----------------- #
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # Tables creation
        c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS keywords (keyword TEXT PRIMARY KEY, type TEXT, content TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, username TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT, timestamp TEXT)''')
        
        # Default configuration values
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('welcome', 'Welcome to KeyNest Bot!')")
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('help', 'Send a keyword to get its content.')")
        conn.commit()

def sync_env_admins():
    if ADMIN_IDS:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            for aid in ADMIN_IDS.split(","):
                aid = aid.strip()
                if aid.isdigit():
                    c.execute("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (int(aid), "EnvAdmin"))
            conn.commit()

init_db()
sync_env_admins()

# ----------------- Helper Functions ----------------- #
def is_admin(user_id):
    env_admins =[int(x.strip()) for x in ADMIN_IDS.split(",") if x.strip().isdigit()]
    if user_id in env_admins:
        return True
    
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        if c.fetchone():
            return True
    return False

def register_user(user):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        username = user.username if user.username else "NoUsername"
        first_name = user.first_name if user.first_name else "NoName"
        c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", 
                  (user.id, username, first_name))
        conn.commit()

def set_state(user_id, state, **kwargs):
    user_states[user_id] = {"state": state}
    user_states[user_id].update(kwargs)

def clear_state(user_id):
    if user_id in user_states:
        del user_states[user_id]

def get_config(key):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = c.fetchone()
        return row[0] if row else ""

def chunk_send(chat_id, text):
    """Sends long text split by Telegram limit"""
    if not text:
        bot.send_message(chat_id, "No data available.")
        return
    for i in range(0, len(text), 4000):
        bot.send_message(chat_id, text[i:i+4000])

# ----------------- Bot Handlers (Commands) ----------------- #
@bot.message_handler(commands=['start'])
def start_cmd(message):
    register_user(message.from_user)
    clear_state(message.from_user.id)
    bot.reply_to(message, get_config('welcome'))

@bot.message_handler(commands=['help'])
def help_cmd(message):
    register_user(message.from_user)
    clear_state(message.from_user.id)
    bot.reply_to(message, get_config('help'))

@bot.message_handler(commands=['cancel'])
def cancel_cmd(message):
    register_user(message.from_user)
    if message.from_user.id in user_states:
        clear_state(message.from_user.id)
        bot.reply_to(message, "Your adding now cancelled")

@bot.message_handler(commands=['report'])
def report_cmd(message):
    register_user(message.from_user)
    set_state(message.from_user.id, "report")
    bot.reply_to(message, "Write Your report and send")

@bot.message_handler(commands=['new'])
def new_keyword_cmd(message):
    if not is_admin(message.from_user.id): return
    set_state(message.from_user.id, "new_key")
    bot.reply_to(message, "What is the keyword?")

@bot.message_handler(commands=['list_key'])
def list_key_cmd(message):
    if not is_admin(message.from_user.id): return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT keyword, type FROM keywords")
        rows = c.fetchall()
    
    if not rows:
        bot.reply_to(message, "No keywords found.")
        return
    
    res = "Stored Keywords:\n" + "\n".join([f"- {r[0]} ({r[1]})" for r in rows])
    chunk_send(message.chat.id, res)

@bot.message_handler(commands=['delete_key'])
def del_key_cmd(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /delete_key <keyword>")
        return
    kw = parts[1]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM keywords WHERE keyword = ?", (kw,))
        if c.rowcount > 0:
            bot.reply_to(message, f"Keyword '{kw}' deleted.")
        else:
            bot.reply_to(message, "Keyword not found.")
        conn.commit()

@bot.message_handler(commands=['wlcmc'])
def wlcmc_cmd(message):
    if not is_admin(message.from_user.id): return
    set_state(message.from_user.id, "wlcmc")
    bot.reply_to(message, "Give me the Welcome message")

@bot.message_handler(commands=['helpmc'])
def helpmc_cmd(message):
    if not is_admin(message.from_user.id): return
    set_state(message.from_user.id, "helpmc")
    bot.reply_to(message, "Send me the help message")

@bot.message_handler(commands=['status'])
def status_cmd(message):
    if not is_admin(message.from_user.id): return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        u_cnt = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        k_cnt = c.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
        a_cnt = c.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
        
    res = f"📊 *Bot Status*\n\nTotal Users: {u_cnt}\nTotal Keywords: {k_cnt}\nTotal Items: {k_cnt}\nTotal Admins: {a_cnt}"
    bot.reply_to(message, res, parse_mode="Markdown")

@bot.message_handler(commands=['add_admin'])
def add_admin_cmd(message):
    if not is_admin(message.from_user.id): return
    set_state(message.from_user.id, "add_admin")
    bot.reply_to(message, "Give me his id")

@bot.message_handler(commands=['see_admin'])
def see_admin_cmd(message):
    if not is_admin(message.from_user.id): return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, username FROM admins")
        rows = c.fetchall()
    res = "Admins:\n" + "\n".join([f"- {r[0]} (@{r[1]})" for r in rows])
    chunk_send(message.chat.id, res)

@bot.message_handler(commands=['delete_admin'])
def delete_admin_cmd(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /delete_admin <id>")
        return
    aid = parts[1]
    if not aid.isdigit():
        bot.reply_to(message, "Invalid ID format.")
        return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE user_id = ?", (int(aid),))
        if c.rowcount > 0:
            bot.reply_to(message, f"Admin {aid} deleted.")
        else:
            bot.reply_to(message, "Admin not found.")
        conn.commit()

@bot.message_handler(commands=['see_users'])
def see_users_cmd(message):
    if not is_admin(message.from_user.id): return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, username, first_name FROM users")
        rows = c.fetchall()
    res = "Users:\n" + "\n".join([f"- {r[0]} | @{r[1]} | {r[2]}" for r in rows])
    chunk_send(message.chat.id, res)

# ----------------- Main Catch-All Handler (States & Keywords) ----------------- #
@bot.message_handler(func=lambda m: True, content_types=['text', 'document', 'photo', 'video'])
def handle_all(message):
    register_user(message.from_user)
    uid = message.from_user.id
    state_info = user_states.get(uid)
    
    # 1. State Processing
    if state_info:
        st = state_info['state']
        
        if st == "new_key":
            if not message.text:
                bot.reply_to(message, "Please send text for the keyword.")
                return
            set_state(uid, "new_format", keyword=message.text)
            bot.reply_to(message, "Which format? docs / text / link / image / video")
            return
            
        elif st == "new_format":
            fmt = message.text.lower() if message.text else ""
            if fmt not in ["docs", "text", "link", "image", "video"]:
                bot.reply_to(message, "Invalid format. Choose: docs / text / link / image / video")
                return
            set_state(uid, "new_content", keyword=state_info['keyword'], format=fmt)
            bot.reply_to(message, "Send the docs/text/link/image/video now")
            return
            
        elif st == "new_content":
            fmt = state_info['format']
            kw = state_info['keyword']
            content = None
            
            if fmt in ["text", "link"] and message.text:
                content = message.text
            elif fmt == "docs" and message.document:
                content = message.document.file_id
            elif fmt == "image" and message.photo:
                content = message.photo[-1].file_id
            elif fmt == "video" and message.video:
                content = message.video.file_id
            
            if not content:
                bot.reply_to(message, f"Please send a valid {fmt}.")
                return
                
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("REPLACE INTO keywords (keyword, type, content) VALUES (?, ?, ?)", (kw, fmt, content))
                conn.commit()
                
            clear_state(uid)
            bot.reply_to(message, "Successful added")
            return
            
        elif st == "wlcmc":
            if message.text:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("REPLACE INTO config (key, value) VALUES ('welcome', ?)", (message.text,))
                    conn.commit()
                clear_state(uid)
                bot.reply_to(message, "Welcome message updated.")
            return
            
        elif st == "helpmc":
            if message.text:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("REPLACE INTO config (key, value) VALUES ('help', ?)", (message.text,))
                    conn.commit()
                clear_state(uid)
                bot.reply_to(message, "Help message updated.")
            return
            
        elif st == "add_admin":
            if message.text and message.text.isdigit():
                new_admin = int(message.text)
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (new_admin, "AddedAdmin"))
                    conn.commit()
                clear_state(uid)
                bot.reply_to(message, "Admin added.")
            else:
                bot.reply_to(message, "Please send a valid numeric user ID.")
            return
            
        elif st == "report":
            if message.text:
                report_text = message.text
                dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("INSERT INTO reports (user_id, text, timestamp) VALUES (?, ?, ?)", (uid, report_text, dt))
                    conn.commit()
                
                fwd_text = f"🚨 *New Report*\n\n*User ID:* `{uid}`\n*Username:* @{message.from_user.username}\n*Name:* {message.from_user.first_name}\n*Date:* {dt}\n\n*Report:* {report_text}"
                try:
                    bot.send_message("@tanzirn", fwd_text, parse_mode="Markdown")
                except Exception as e:
                    print(f"Failed to forward report: {e}")
                    
                clear_state(uid)
                bot.reply_to(message, "Your report has been sent.")
            else:
                bot.reply_to(message, "Please send text for the report.")
            return

    # 2. Keyword Lookup Processing
    if message.text and not message.text.startswith("/"):
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT type, content FROM keywords WHERE keyword = ?", (message.text,))
            row = c.fetchone()
            
        if row:
            ktype, content = row
            try:
                if ktype == "text" or ktype == "link":
                    bot.send_message(message.chat.id, content)
                elif ktype == "docs":
                    bot.send_document(message.chat.id, content)
                elif ktype == "image":
                    bot.send_photo(message.chat.id, content)
                elif ktype == "video":
                    bot.send_video(message.chat.id, content)
            except Exception as e:
                bot.reply_to(message, "Error sending content. It might be unavailable.")
        else:
            bot.reply_to(message, "Keyword not found. Please try another one.")

# ----------------- Flask Web Server ----------------- #
@app.route('/')
def health_check():
    return "KeyNest Bot is running smoothly!", 200

# ----------------- Deployment Execution ----------------- #
def start_bot_polling():
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print("Polling Error:", e)

threading.Thread(target=start_bot_polling, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
