import os
import json
import sqlite3
import asyncio
import threading
import time
import requests
from datetime import datetime, timedelta
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# 1. CONFIGURATION & CONSTANTS
BOT_TOKEN = "8749988449:AAEbL0VXE1K3mHUZF4hWZI7h-imXpoj_8kY"
ADMIN_ID = (8323137024, 8205396055, 5855151459)
ADMIN_NAME = "Mota bhi"
ADMIN_USERNAME = "YourUsername"
GROUP_CHAT_ID = -1003292667248
UPI_ID = "motabhai1001@ptaxis"
RENDER_EXTERNAL_URL = "https://des-story-tg.onrender.com"
TOPIC_FORWARD_GROUP_ID = -1003742470706
topic_map = {}
SEP = "━━━━━━━━━━━━━━━━━━"

FORCE_SUB_CHANNELS = [
    {"username": "@join_now101", "name": "BACKUP CHANNEL", "url": "https://t.me/join_now101"},
    {"username": "@FREE_STORY_FM1", "name": "FREE_STORY", "url": "https://t.me/FREE_STORY_FM1"},
]

IMG_MAIN = "https://files.catbox.moe/9zm269.jpg"
IMG_ABOUT = "https://files.catbox.moe/65tg20.jpg"
IMG_SUPPORT = "https://files.catbox.moe/prrij6.jpg"
IMG_PRICING = "https://files.catbox.moe/kotokq.jpg"
IMG_PAYMENT = "https://files.catbox.moe/3y6vbj.jpg"
IMG_PLAN = "https://files.catbox.moe/wdldpl.jpg"

PRICING_PLANS = [
    {
        "id": "bronze",
        "title": "🥉 BRONZE | 30 Days",
        "price": "100",
        "days": 30,
        "description": "🎙PREMIUM AUDIO ACCESS 🎧\n╭───────────⍟\n├PLAN :  🥉 BRONZE | 30 Days\n├PRICE:  ₹100\n├VALIDITY :  1 Month\n├BONUS: 🚫\n├FEATURES \n | • Ad-Free Listening Experience 🚫\n | • No Spoilers, Just Stories 🤫\n | • Background Play Supported 📱\n╰───────────────⍟"
    },
    {
        "id": "silver",
        "title": "🥈 SILVER | 90 Days",
        "price": "300",
        "days": 100,
        "description": "🎙PREMIUM AUDIO ACCESS 🎧\n╭───────────⍟\n├PLAN :  🥈 SILVER | 90 Days\n├PRICE:  ₹300\n├VALIDITY :  3 Months\n├BONUS: 10 Days Extra\n├FEATURES \n | • Ad-Free Listening Experience 🚫\n | • No Spoilers, Just Stories 🤫\n | • Background Play Supported 📱\n | • Download for Offline Listening 📥\n╰───────────────⍟"
    },
    {
        "id": "gold",
        "title": "🥇 GOLD | 180 Days",
        "price": "600",
        "days": 205,
        "description": "🎙PREMIUM AUDIO ACCESS 🎧\n╭───────────⍟\n├PLAN :  🥇 GOLD | 180 Days\n├PRICE:  ₹600\n├VALIDITY :  6 Months\n├BONUS: 25 Days Extra\n├FEATURES \n | • Ad-Free Listening Experience 🚫\n | • High-Bitrate Clear Sound 🔊\n | • No Spoilers, Just Stories 🤫\n | • Background Play Supported 📱\n | • Download for Offline Listening 📥\n╰───────────────⍟"
    }
]

# 2. DATABASE / PERSISTENCE (SQLite)
DB_FILE = "subscriptions.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id TEXT PRIMARY KEY,
                user_name TEXT,
                plan_name TEXT,
                join_date TEXT,
                expiry_date TEXT
            )
        ''')

def load_data():
    init_db()
    subs = {}
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("SELECT user_id, user_name, plan_name, join_date, expiry_date FROM subscriptions")
        for row in cursor:
            subs[str(row[0])] = {
                "user_name": row[1],
                "plan_name": row[2],
                "join_date": row[3],
                "expiry_date": row[4]
            }
    return subs

def save_subscription(user_id, data):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''
            INSERT INTO subscriptions (user_id, user_name, plan_name, join_date, expiry_date)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                user_name=excluded.user_name,
                plan_name=excluded.plan_name,
                join_date=excluded.join_date,
                expiry_date=excluded.expiry_date
        ''', (
            str(user_id), 
            data.get('user_name', 'Unknown'), 
            data.get('plan_name', 'N/A'), 
            data.get('join_date', ''), 
            data.get('expiry_date', '')
        ))

def delete_subscription(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM subscriptions WHERE user_id = ?", (str(user_id),))

subscriptions = load_data()

# 3. SERVER (Keep-Alive)
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

def ping_self():
    while True:
        try:
            requests.get(RENDER_EXTERNAL_URL)
        except Exception as e:
            print(f"Ping error: {e}")
        time.sleep(840)

# 4. FORCE SUBSCRIBE HELPER
async def is_user_subscribed(user_id, context: ContextTypes.DEFAULT_TYPE):
    if user_id in ADMIN_ID:
        return True
    
    for channel in FORCE_SUB_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel["username"], user_id)
            if member.status not in ["member", "administrator", "creator", "restricted"]:
                return False
        except Exception:
            return False
    return True

async def send_force_sub_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"🛑 **MANDATORY SUBSCRIPTION** 🛑\n{SEP}\nTo use this premium bot, you **must join our official channels** first.\n\nPlease join all the channels below, then click **✅ Check Subscription** to continue."
    
    buttons = []
    for channel in FORCE_SUB_CHANNELS:
        buttons.append([InlineKeyboardButton(channel["name"], url=channel["url"])])
    buttons.append([InlineKeyboardButton("✅ Check Subscription", callback_data="check_sub")])
    
    markup = InlineKeyboardMarkup(buttons)
    
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

# 5. COMMANDS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subscribed(user_id, context):
        await send_force_sub_prompt(update, context)
        return

    first_name = update.effective_user.first_name
    text = f"👑 **OLD/COMPLETE STORY PREMIUM** 👑\n{SEP}\nHello **{first_name}**,\nExperience the ultimate premium audio journey.\n\nSelect an option below to begin."
    
    buttons = [
        [InlineKeyboardButton("🎧 PREMIUM AUDIO PLANS 🎧", callback_data="price_0")],
        [InlineKeyboardButton("📖 About Us", callback_data="about"), InlineKeyboardButton("💬 Support", callback_data="connect")],
        [InlineKeyboardButton("📢 Official Channel", url="https://t.me/FREE_STORY_FM1")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_photo(IMG_MAIN, caption=text, reply_markup=markup, parse_mode="Markdown")

async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not await is_user_subscribed(update.effective_user.id, context):
        await send_force_sub_prompt(update, context)
        return

    if user_id in subscriptions:
        sub = subscriptions[user_id]
        text = f"👤 **MY SUBSCRIPTION**\n{SEP}\nName: **{sub.get('user_name', 'Unknown')}**\nPlan: **{sub.get('plan_name', 'N/A')}**\nExpiry: `{sub.get('expiry_date', 'N/A')}`"
    else:
        text = f"👤 **MY SUBSCRIPTION**\n{SEP}\nYou have no active premium plan.\nUse /start to view plans."

    await update.message.reply_photo(IMG_PLAN, caption=text, parse_mode="Markdown")

async def subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_ID:
        return

    await send_subscribers_list(update, context, 0)

async def send_subscribers_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    all_subs = list(subscriptions.items())
    total_users = len(all_subs)
    per_page = 20
    total_pages = (total_users + per_page - 1) // per_page if total_users > 0 else 1
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_subs = all_subs[start_idx:end_idx]
    
    text = f"📋 **SUBSCRIBERS LIST** (Page {page+1}/{total_pages})\nTotal Users: {total_users}\n{SEP}\n"
    
    for uid, data in page_subs:
        uname = data.get("user_name", "Unknown")
        short_name = (uname[:15] + "..") if len(uname) > 15 else uname
        exp = data.get("expiry_date", "N/A")
        plan = data.get("plan_name", "N/A")
        text += f"`{uid}` | 👤 {short_name} | ⏳ {exp}\n└ 🏷 {plan}\n"

    buttons = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"sub_page_{page-1}"))
    if end_idx < total_users:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"sub_page_{page+1}"))
    if nav_row:
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton("✏️ Edit Validity", callback_data="edit_sub_prompt")])
    markup = InlineKeyboardMarkup(buttons)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

# 6. CALLBACK HANDLERS
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data == "check_sub":
        if await is_user_subscribed(user_id, context):
            await query.answer("✅ Subscription verified!")
            # Trigger start logic
            first_name = query.from_user.first_name
            text = f"👑 **OLD/COMPLETE STORY PREMIUM** 👑\n{SEP}\nHello **{first_name}**,\nExperience the ultimate premium audio journey.\n\nSelect an option below to begin."
            buttons = [
                [InlineKeyboardButton("🎧 PREMIUM AUDIO PLANS 🎧", callback_data="price_0")],
                [InlineKeyboardButton("📖 About Us", callback_data="about"), InlineKeyboardButton("💬 Support", callback_data="connect")],
                [InlineKeyboardButton("📢 Official Channel", url="https://t.me/FREE_STORY_FM1")]
            ]
            markup = InlineKeyboardMarkup(buttons)
            await query.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
        else:
            await query.answer("❌ You haven't joined all channels yet! Please join them first.", show_alert=True)

    elif data.startswith("sub_page_"):
        page = int(data.split("_")[2])
        await send_subscribers_list(update, context, page)

    elif data == "edit_sub_prompt":
        await query.message.reply_text(
            "✍️ **EDIT USER VALIDITY**\nTo edit a user, reply to this exact message with the format:\n`[UserID] [Days]`\n\nExample: `123456789 30` (Sets validity to 30 days from today).",
            parse_mode="Markdown"
        )
        await query.answer()

    elif data == "about":
        text = (
            "📜 **OUR MISSION**\n━━━━━━━━━━━━━━━━━━━━\n"
            "● We collect and share complete audio stories from multiple different apps and websites so you can find them all in one spot.\n"
            "● You get access to the full, uninterrupted versions of both old classics and brand-new releases.\n"
            "● Enjoy a seamless listening experience without needing to switch between different platforms to hear your favorite content.\n\n"
            "bot developed by @D_Padhan"
        )
        await query.message.edit_media(InputMediaPhoto(IMG_ABOUT, caption=text, parse_mode="Markdown"))
        await query.message.edit_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main")]]))

    elif data == "connect":
        text = f"📞 **LIVE HELPLINE**\n{SEP}\nNeed help? Contact [{ADMIN_NAME}](https://t.me/{ADMIN_USERNAME}) or send a message here."
        await query.message.edit_media(InputMediaPhoto(IMG_SUPPORT, caption=text, parse_mode="Markdown"))
        await query.message.edit_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main")]]))

    elif data.startswith("price_"):
        idx = int(data.split("_")[1])
        plan = PRICING_PLANS[idx]
        
        buttons = []
        nav_row = []
        if idx > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"price_{idx-1}"))
        if idx < len(PRICING_PLANS) - 1:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"price_{idx+1}"))
        if nav_row:
            buttons.append(nav_row)
        
        buttons.append([InlineKeyboardButton(f"💳 PURCHASE ₹{plan['price']}", callback_data=f"buy_{idx}")])
        buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main")])
        
        await query.message.edit_media(InputMediaPhoto(IMG_PRICING, caption=plan["description"], parse_mode="Markdown"))
        await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))

    elif data.startswith("buy_"):
        idx = int(data.split("_")[1])
        plan = PRICING_PLANS[idx]
        text = f"💳 **PAYMENT GATEWAY**\n{SEP}\nPlan: **{plan['title']}**\nPrice: `₹{plan['price']}`\n\nUPI ID: `{UPI_ID}`\n\n📸 **Send the screenshot here** after payment."
        await query.message.edit_media(InputMediaPhoto(IMG_PAYMENT, caption=text, parse_mode="Markdown"))
        await query.message.edit_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main")]]))

    elif data.startswith("approve_"):
        parts = data.split("_")
        target_uid = parts[1]
        plan_idx = int(parts[2])
        plan = PRICING_PLANS[plan_idx]
        
        expiry = datetime.now() + timedelta(days=plan["days"])
        expiry_str = expiry.strftime("%Y-%m-%d %H:%M:%S")
        
        # Save to memory and then SQLite database
        subscriptions[target_uid] = {
            "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "expiry_date": expiry_str,
            "plan_name": plan["title"],
            "user_name": "Unknown" # Ideally fetch from message
        }
        save_subscription(target_uid, subscriptions[target_uid])
        
        try:
            invite = await context.bot.create_chat_invite_link(GROUP_CHAT_ID, member_limit=1)
            success_text = f"🎉 **CONGRATULATIONS!**\nYour payment has been approved.\n\nPlan: **{plan['title']}**\nExpiry: `{expiry_str}`\n\nJoin the premium group here: {invite.invite_link}"
            await context.bot.send_message(target_uid, success_text, parse_mode="Markdown")
            
            # FIX: Use edit_message_caption instead of edit_message_text for photo messages
            await query.edit_message_caption(f"🟢 Approved user (`{target_uid}`) for {plan['title']}", parse_mode="Markdown")
        except Exception as e:
            await query.answer(f"Error: {e}")

    elif data.startswith("dismiss_"):
        target_uid = data.split("_")[1]
        try:
            await context.bot.send_message(target_uid, "🔴 **PAYMENT REJECTED**\nYour payment verification failed. Please contact support if this is an error.", parse_mode="Markdown")
            
            # FIX: Use edit_message_caption instead of edit_message_text for photo messages
            await query.edit_message_caption(f"🔴 User {target_uid} rejected.", parse_mode="Markdown")
        except Exception as e:
            await query.answer(f"Error: {e}")

    elif data == "main":
        first_name = query.from_user.first_name
        text = f"👑 **OLD/COMPLETE STORY PREMIUM** 👑\n{SEP}\nHello **{first_name}**,\nExperience the ultimate premium audio journey.\n\nSelect an option below to begin."
        buttons = [
            [InlineKeyboardButton("🎧 PREMIUM AUDIO PLANS 🎧", callback_data="price_0")],
            [InlineKeyboardButton("📖 About Us", callback_data="about"), InlineKeyboardButton("💬 Support", callback_data="connect")],
            [InlineKeyboardButton("📢 Official Channel", url="https://t.me/FREE_STORY_FM1")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_media(InputMediaPhoto(IMG_MAIN, caption=text, parse_mode="Markdown"))
        await query.message.edit_reply_markup(markup)

# 7. GLOBAL MESSAGE HANDLER & LOGIC
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    text = update.message.text
    
    # Private Chat Logic
    if update.effective_chat.type == "private":
        # Admin Edits
        if user_id in ADMIN_ID and update.message.reply_to_message and "EDIT USER VALIDITY" in update.message.reply_to_message.text:
            try:
                parts = text.split()
                target_uid = parts[0]
                days = int(parts[1])
                
                expiry = datetime.now() + timedelta(days=days)
                expiry_str = expiry.strftime("%Y-%m-%d %H:%M:%S")
                
                if target_uid in subscriptions:
                    subscriptions[target_uid]["expiry_date"] = expiry_str
                else:
                    subscriptions[target_uid] = {
                        "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "expiry_date": expiry_str,
                        "plan_name": "Manual Extension",
                        "user_name": "Unknown"
                    }
                save_subscription(target_uid, subscriptions[target_uid])
                
                await update.message.reply_text(f"✅ **Updated Successfully!**\nUser: `{target_uid}`\nNew Expiry: `{expiry_str}`", parse_mode="Markdown")
                await context.bot.send_message(target_uid, f"🎉 **Your premium validity has been manually extended!**\nNew Expiry: `{expiry_str}`", parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ Error: {e}")
            return

        # Admin Support Reply
        if user_id in ADMIN_ID and update.message.reply_to_message:
            # Try to find original user ID from the forwarded message or caption
            reply_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
            if reply_text and "(" in reply_text and ")" in reply_text:
                try:
                    target_uid = reply_text.split("(")[-1].split(")")[0].strip("`")
                    await context.bot.copy_message(target_uid, update.effective_chat.id, update.message.message_id)
                    await update.message.reply_text("✅ Reply sent.")
                except Exception:
                    pass
            return

        # Payment Proofs
        if update.message.photo:
            name = update.effective_user.full_name
            uid = update.effective_user.id
            
            caption = f"🔔 **New Payment Proof**\nFrom: 👤 **{name}** (`{uid}`)\nSelect a plan to approve:"
            buttons = [
                [InlineKeyboardButton("🥉 Bronze", callback_data=f"approve_{uid}_0"), InlineKeyboardButton("🥈 Silver", callback_data=f"approve_{uid}_1")],
                [InlineKeyboardButton("🥇 Gold", callback_data=f"approve_{uid}_2"), InlineKeyboardButton("🔴 Reject", callback_data=f"dismiss_{uid}")]
            ]
            markup = InlineKeyboardMarkup(buttons)
            
            for admin in ADMIN_ID:
                try:
                    await context.bot.send_photo(admin, update.message.photo[-1].file_id, caption=caption, reply_markup=markup, parse_mode="Markdown")
                except Exception:
                    pass
            
            await update.message.reply_text("✅ **Screenshot Received!**\nOur admin is verifying your payment. You will be notified shortly.", parse_mode="Markdown")
            return

        # Standard Support
        if user_id not in ADMIN_ID:
            name = update.effective_user.full_name
            uid = update.effective_user.id
            forward_text = f"💬 **Support Message**\nFrom: 👤 **{name}** (`{uid}`)\n\n{text}"
            
            for admin in ADMIN_ID:
                try:
                    await context.bot.send_message(admin, forward_text, parse_mode="Markdown")
                except Exception:
                    pass
            await update.message.reply_text("✅ Message sent to support.")

    # Topic Forwarding (Non-private)
    else:
        if update.effective_chat.id != TOPIC_FORWARD_GROUP_ID:
            source_id = str(update.effective_chat.id)
            source_name = update.effective_chat.title
            
            if source_id not in topic_map:
                try:
                    topic = await context.bot.create_forum_topic(TOPIC_FORWARD_GROUP_ID, f"From: {source_name}")
                    topic_map[source_id] = topic.message_thread_id
                except Exception:
                    return
            
            thread_id = topic_map[source_id]
            try:
                await context.bot.forward_message(TOPIC_FORWARD_GROUP_ID, update.effective_chat.id, update.message.message_id, message_thread_id=thread_id)
            except Exception:
                pass

# 9. AUTO-REMOVE JOB
async def auto_remove_expired(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    to_remove = []
    
    for uid, data in subscriptions.items():
        try:
            expiry = datetime.strptime(data["expiry_date"], "%Y-%m-%d %H:%M:%S")
            if now > expiry:
                to_remove.append(uid)
        except Exception:
            pass
            
    for uid in to_remove:
        try:
            await context.bot.ban_chat_member(GROUP_CHAT_ID, int(uid))
            await context.bot.unban_chat_member(GROUP_CHAT_ID, int(uid))
            
            del subscriptions[uid]
            delete_subscription(uid)
            
            await context.bot.send_message(uid, "⌛ **Your premium access has expired!**\nRenew your plan via /start to regain access.", parse_mode="Markdown")
        except Exception:
            pass

def main():
    # Start Flask in background
    threading.Thread(target=run_flask, daemon=True).start()
    # Start Ping in background
    threading.Thread(target=ping_self, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myplan", myplan))
    app.add_handler(CommandHandler("subscribers", subscribers))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))
    
    # Job Queue
    job_queue = app.job_queue
    job_queue.run_repeating(auto_remove_expired, interval=60, first=10)
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()


