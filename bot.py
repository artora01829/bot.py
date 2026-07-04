import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import threading
import requests
import os
import time

TOKEN = "8910745794:AAHkN8mXTUvvn5T-IKTJZLJML5mEILzvjjE"
bot = telebot.TeleBot(TOKEN)

# رمز عبور مجاز
PASSWORD = "10008000lidokayn"

# دیکشنری برای ذخیره کاربران احراز هویت شده
authorized_users = set()

# دیتابیس
conn = sqlite3.connect('videos.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                  (id INTEGER PRIMARY KEY, file_id TEXT, name TEXT)''')
conn.commit()

# دیکشنری برای ذخیره موقت file_id هنگام درخواست اسم
temp_video = {}

# ========== تابع ارسال فیلم با تایمر حذف ==========
def send_video_with_timer(chat_id, file_id, caption="", delay=20):
    try:
        sent_msg = bot.send_video(chat_id, file_id, caption=caption)
        bot.send_message(chat_id, f"⏳ این فیلم {delay} ثانیه بعد پاک میشه!")
        timer = threading.Timer(delay, delete_message, args=[chat_id, sent_msg.message_id])
        timer.daemon = True
        timer.start()
        return sent_msg
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در ارسال فیلم: {str(e)}")
        return None

def delete_message(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception as e:
        print(f"❌ خطا در حذف پیام: {str(e)}")

# ========== تابع دانلود فیلم از لینک ==========
def download_video_from_url(url, chat_id):
    try:
        status_msg = bot.send_message(chat_id, "⏳ در حال دانلود فیلم از لینک...")
        
        response = requests.get(url, stream=True, timeout=30)
        
        if response.status_code != 200:
            bot.edit_message_text("❌ لینک معتبر نیست یا فیلم پیدا نشد!", chat_id, status_msg.message_id)
            return None
        
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > 50 * 1024 * 1024:
            bot.edit_message_text("❌ حجم فیلم بیشتر از ۵۰ مگابایت است!", chat_id, status_msg.message_id)
            return None
        
        filename = os.path.basename(url.split('?')[0])
        if not filename or '.' not in filename:
            filename = f"video_{int(time.time())}.mp4"
        
        file_path = os.path.join("/storage/emulated/0/Download/", filename)
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        bot.edit_message_text(f"✅ دانلود کامل شد! فیلم: {filename}", chat_id, status_msg.message_id)
        
        with open(file_path, 'rb') as video_file:
            sent_msg = bot.send_video(chat_id, video_file, caption=f"🎬 {filename}")
        
        os.remove(file_path)
        
        file_id = sent_msg.video.file_id
        cursor.execute("INSERT INTO videos (file_id, name) VALUES (?, ?)", (file_id, filename))
        conn.commit()
        
        bot.send_message(chat_id, f"✅ فیلم '{filename}' به لیست اضافه شد!")
        
        return sent_msg
        
    except requests.exceptions.Timeout:
        bot.send_message(chat_id, "❌ زمان دانلود به پایان رسید! لینک را بررسی کنید.")
        return None
    except requests.exceptions.ConnectionError:
        bot.send_message(chat_id, "❌ خطا در اتصال به سرور! لینک را بررسی کنید.")
        return None
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در دانلود: {str(e)}")
        return None

# ========== نمایش منوی اصلی ==========
def show_main_menu(chat_id, message_id=None):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_list = InlineKeyboardButton("📋 لیست فیلم‌ها", callback_data="list_videos")
    btn_random = InlineKeyboardButton("🎲 تصادفی", callback_data="random_video")
    btn_download = InlineKeyboardButton("📥 دریافت از لینک", callback_data="download_link")
    keyboard.add(btn_list, btn_random)
    keyboard.add(btn_download)
    
    if message_id:
        bot.edit_message_text("🎬 منوی اصلی:", chat_id, message_id, reply_markup=keyboard)
    else:
        bot.send_message(chat_id, "🎬 منوی اصلی:", reply_markup=keyboard)

# ========== درخواست رمز عبور ==========
def ask_for_password(chat_id):
    msg = bot.send_message(chat_id, 
        "🔐 لطفا رمز عبور را وارد کنید:\n"
        "اگر نمیدانید لطفا پیام ندهید.\n"
        "به استثنای افراد دعوت شده که باید صبور باشند."
    )
    bot.register_next_step_handler(msg, check_password)

def check_password(message):
    chat_id = message.chat.id
    user_input = message.text.strip()
    
    if user_input == PASSWORD:
        authorized_users.add(chat_id)
        bot.send_message(chat_id, "✅ رمز عبور صحیح! به ربات خوش آمدید.")
        show_main_menu(chat_id)
    else:
        bot.send_message(chat_id, "رمز عبور اشتباه بود")
        ask_for_password(chat_id)

# ========== دستور start ==========
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    if chat_id in authorized_users:
        show_main_menu(chat_id)
    else:
        ask_for_password(chat_id)

# ========== ذخیره فیلم با دریافت اسم (بدون نیاز به رمز) ==========
@bot.message_handler(commands=['save'])
def save_video(message):
    chat_id = message.chat.id
    
    # حذف بررسی رمز عبور - هر کسی میتونه استفاده کنه
    if not message.reply_to_message or not message.reply_to_message.video:
        bot.reply_to(message, "❌ لطفاً روی یک فیلم ریپلی کن و دوباره /save رو بفرست.")
        return
    
    video = message.reply_to_message.video
    file_id = video.file_id
    default_name = video.file_name or f"video_{file_id[:8]}"
    
    temp_video[chat_id] = file_id
    
    msg = bot.reply_to(message, f"📝 لطفاً یک اسم برای این فیلم وارد کن (پیش‌فرض: {default_name}):\n"
                                "یا برای استفاده از پیش‌فرض، /skip رو بفرست.")
    bot.register_next_step_handler(msg, get_video_name, default_name)

def get_video_name(message, default_name):
    chat_id = message.chat.id
    user_input = message.text.strip()
    
    if user_input.lower() == '/skip' or not user_input:
        final_name = default_name
    else:
        final_name = user_input
    
    if chat_id not in temp_video:
        bot.send_message(chat_id, "❌ خطا! لطفاً دوباره /save رو امتحان کن.")
        return
    
    file_id = temp_video[chat_id]
    
    try:
        cursor.execute("INSERT INTO videos (file_id, name) VALUES (?, ?)", (file_id, final_name))
        conn.commit()
        bot.send_message(chat_id, f"✅ فیلم با اسم '{final_name}' ذخیره شد!")
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در ذخیره: {str(e)}")
    finally:
        if chat_id in temp_video:
            del temp_video[chat_id]

# ========== دریافت لینک از کاربر ==========
@bot.message_handler(commands=['download'])
def ask_for_link(message):
    chat_id = message.chat.id
    
    if chat_id not in authorized_users:
        bot.reply_to(message, "🔐 ابتدا باید با /start رمز عبور را وارد کنید.")
        return
    
    msg = bot.reply_to(message, "🔗 لینک مستقیم فیلم رو بفرست (مثال: https://example.com/video.mp4):")
    bot.register_next_step_handler(msg, process_link)

def process_link(message):
    chat_id = message.chat.id
    url = message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        bot.send_message(chat_id, "❌ لینک معتبر نیست! لطفاً با http:// یا https:// شروع کن.")
        return
    
    download_video_from_url(url, chat_id)

# ========== Callback‌های دکمه‌ها ==========
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    
    if chat_id not in authorized_users:
        bot.answer_callback_query(call.id, "🔐 ابتدا رمز عبور را وارد کنید!")
        return
    
    if call.data == "list_videos":
        cursor.execute("SELECT rowid, name FROM videos ORDER BY name")
        videos = cursor.fetchall()
        if not videos:
            bot.send_message(chat_id, "📭 فیلمی ذخیره نشده!")
            return
        keyboard = InlineKeyboardMarkup(row_width=2)
        for rowid, name in videos[:30]:
            short = name[:18] + "..." if len(name) > 18 else name
            keyboard.add(InlineKeyboardButton(f"{short}", callback_data=f"play_{rowid}"))
        keyboard.add(InlineKeyboardButton("🔙 برگشت", callback_data="back"))
        bot.edit_message_text("📹 لیست فیلم‌ها (یکی رو انتخاب کن):", 
                              chat_id, call.message.message_id, reply_markup=keyboard)
    
    elif call.data.startswith("play_"):
        video_id = int(call.data.split("_")[1])
        cursor.execute("SELECT file_id, name FROM videos WHERE rowid = ?", (video_id,))
        result = cursor.fetchone()
        if result:
            send_video_with_timer(
                chat_id, 
                result[0], 
                caption=f"🎬 {result[1]}\n⏳ این فیلم ۲۰ ثانیه بعد پاک میشه!"
            )
        else:
            bot.answer_callback_query(call.id, "❌ فیلم پیدا نشد!")
    
    elif call.data == "random_video":
        cursor.execute("SELECT file_id, name FROM videos ORDER BY RANDOM() LIMIT 1")
        result = cursor.fetchone()
        if result:
            send_video_with_timer(
                chat_id, 
                result[0], 
                caption=f"🎲 {result[1]}\n⏳ این فیلم ۲۰ ثانیه بعد پاک میشه!"
            )
        else:
            bot.answer_callback_query(call.id, "❌ فیلمی ذخیره نشده!")
    
    elif call.data == "download_link":
        msg = bot.send_message(chat_id, "🔗 لینک مستقیم فیلم رو بفرست:")
        bot.register_next_step_handler(msg, process_link)
    
    elif call.data == "back":
        show_main_menu(chat_id, call.message.message_id)

# ========== اجرا ==========
print("🤖 ربات با save بدون رمز و قابلیت دریافت از لینک روشن شد...")
bot.infinity_polling()
