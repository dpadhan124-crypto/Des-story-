import logging
import threading
import time
import requests
import json
import os
import asyncio # ADDED: Required for async sleep
from flask import Flask
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- 1. CONFIGURATION ---
BOT_TOKEN = "8749988449:AAEbL0VXE1K3mHUZF4hWZI7h-imXpoj_8kY"
ADMIN_ID = (8323137024, 8205396055, 5855151459)
ADMIN_NAME = "Mota bhi" 
ADMIN_USERNAME = "YourUsername" 
GROUP_CHAT_ID = -1003292667248
UPI_ID = "motabhai1001@ptaxis" 

FORCE_SUB_CHANNELS = [
    {"chat_id": "@join_now101", "name": "BACKUP CHANNEL", "url": "https://t.me/join_now101"},
    {"chat_id": "@FREE_STORY_FM1", "name": "FREE_STORY", "url": "https://t.me/FREE_STORY_FM1"}
]

RENDER_EXTERNAL_URL = "https://des-story-tg.onrender.com"

# Image Links
IMG_MAIN = "https://files.catbox.moe/9zm269.jpg" 
IMG_ABOUT = "https://files.catbox.moe/65tg20.jpg"
IMG_SUPPORT = "https://files.catbox.moe/prrij6.jpg"
IMG_PRICING = "https://files.catbox.moe/kotokq.jpg"
IMG_PAYMENT = "https://files.catbox.moe/3y6vbj.jpg"
IMG_PLAN = "https://files.catbox.moe/wdldpl.jpg"

PRICING_PLANS = [
    {"id": "bronze", "title": "🥉 BRONZE | 30 Days", "price": "100", "days": 30, "desc": "🎙PREMIUM AUDIO ACCESS 🎧\n╭───────────⍟\n├PLAN :  🥉 BRONZE | 30 Days\n├PRICE:  ₹100\n├VALIDITY :  1 Month\n├BONUS: 🚫\n├FEATURES \n | • Ad-Free Listening Experience 🚫\n | • No Spoilers, Just Stories 🤫\n | • Background Play Supported 📱\n╰───────────────⍟"},
    {"id": "silver", "title": "🥈 SILVER | 90 Days", "price": "300", "days": 100, "desc": "🎙PREMIUM AUDIO ACCESS 🎧\n╭───────────⍟\n├PLAN :  🥈 SILVER | 90 Days\n├PRICE:  ₹300\n├VALIDITY :  3 Months\n├BONUS: 10 Days Extra\n├FEATURES \n | • Ad-Free Listening Experience 🚫\n | • No Spoilers, Just Stories 🤫\n | • Background Play Supported 📱\n | • Download for Offline Listening 📥\n╰───────────────⍟"},
    {"id": "gold", "title": "🥇 GOLD | 180 Days", "price": "600", "days": 205, "desc": "🎙PREMIUM AUDIO ACCESS 🎧\n╭───────────⍟\n├PLAN :  🥇 GOLD | 180 Days\n├PRICE:  ₹600\n├VALIDITY :  6 Months\n├BONUS: 25 Days Extra\n├FEATURES \n | • Ad-Free Listening Experience 🚫\n | • High-Bitrate Clear Sound 🔊\n | • No Spoilers, Just Stories 🤫\n | • Background Play Supported 📱\n | • Download for Offline Listening 📥\n╰───────────────⍟"}
]

SEP = "━━━━━━━━━━━━━━━━━━"
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 2. DATABASE / PERSISTENCE ---
DATA_FILE = "subscriptions.json"
subscriptions = {}
support_users = set() # Track users currently in "Live Chat" mode

def load_data():
    global subscriptions
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data_loaded = json.load(f)
                for uid, data in data_loaded.items():
                    subscriptions[int(uid)] = {
                        "join_date": datetime.fromisoformat(data["join_date"]),
                        "expiry_date": datetime.fromisoformat(data["expiry_date"]),
                        "plan_name": data["plan_name"],
                        "user_name": data.get("user_name", "Unknown")
                    }
        except Exception as e:
            logging.error(f"Failed to load data: {e}")

def save_data():
    data_to_save = {str(uid): {
        "join_date": data["join_date"].isoformat(),
        "expiry_date": data["expiry_date"].isoformat(),
        "plan_name": data["plan_name"],
        "user_name": data.get("user_name", "Unknown")
    } for uid, data in subscriptions.items()}
    with open(DATA_FILE, "w") as f:
        json.dump(data_to_save, f)

# --- 3. SERVER ---
flask_app = Flask('')
@flask_app.route('/')
def home(): return "Bot is running!"

def ping_self():
    while True:
        try: requests.get(RENDER_EXTERNAL_URL)
        except: pass
        time.sleep(840)

# --- 4. HELPERS ---
async def is_user_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id in ADMIN_ID: return True
    for channel in FORCE_SUB_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel["chat_id"], user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']: return False
        except: return False 
    return True

async def send_force_sub_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"🛑 **MANDATORY SUBSCRIPTION** 🛑\n{SEP}\nTo use this premium bot, you **must join our official channels** first."
    keyboard = [[InlineKeyboardButton(f"📢 Join {ch['name']}", url=ch['url'])] for ch in FORCE_SUB_CHANNELS]
    keyboard.append([InlineKeyboardButton("✅ Check Subscription", callback_data="check_sub")])
    if update.message: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif update.callback_query: await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def send_main_menu(chat_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE):
    text = f"👑 **OLD/COMPLETE STORY** 👑\n{SEP}\nHello **{first_name}**,\nSelect an option below to begin."
    keyboard = [
        [InlineKeyboardButton("🎧 PREMIUM AUDIO PLANS 🎧", callback_data="price_0")],
        [InlineKeyboardButton("📖 About Us", callback_data="about"), InlineKeyboardButton("💬 Support", callback_data="connect")],
        [InlineKeyboardButton("📢 Official Channel", url="https://t.me/DPS_Stories")]
    ]
    await context.bot.send_photo(chat_id=chat_id, photo=IMG_MAIN, caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- 5. COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_subscribed(update.effective_user.id, context):
        await send_force_sub_prompt(update, context)
        return
    await send_main_menu(update.effective_chat.id, update.effective_user.first_name, context)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_ID: return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a message (text/media) to broadcast it.")
        return
    
    msg = update.message.reply_to_message
    users = list(subscriptions.keys())
    count = 0
    
    status_msg = await update.message.reply_text(f"🚀 Broadcasting to {len(users)} users...")
    for uid in users:
        try:
            await context.bot.copy_message(chat_id=uid, from_chat_id=update.message.chat_id, message_id=msg.message_id)
            count += 1
            await asyncio.sleep(0.05) # FIXED: asyncio.sleep prevents blocking the bot loop
        except: pass
    await status_msg.edit_text(f"✅ Broadcast complete! Sent to {count} users.")

async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in subscriptions:
        await update.message.reply_text("❌ No active plan.")
        return
    sub = subscriptions[uid]
    text = f"👤 **MY SUBSCRIPTION**\n{SEP}\nName: **{sub.get('user_name', 'User')}**\nPlan: **{sub['plan_name']}**\nExpiry: `{sub['expiry_date'].strftime('%Y-%m-%d')}`"
    await update.message.reply_photo(photo=IMG_PLAN, caption=text, parse_mode="Markdown")

# --- 6. CALLBACK HANDLERS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data

    if data == "check_sub":
        if await is_user_subscribed(user_id, context):
            await query.message.delete()
            await send_main_menu(user_id, update.effective_user.first_name, context)
        else: await query.answer("❌ Join all channels first!", show_alert=True)
        return

    await query.answer()

    if data == "about":
        text = f"📜 **OUR MISSION**\n{SEP}\n● We collect and share complete audio stories.\n● Access full, uninterrupted versions.\n● No switching platforms.\n\nDeveloped by @D_Padhan"
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_ABOUT, caption=text, parse_mode="Markdown"), 
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="main")]]))

    elif data == "connect":
        support_users.add(user_id)
        text = f"📞 **LIVE SUPPORT MODE ON**\n{SEP}\nYou are now connected to admins. **Send any text, photo, or media** and we will reply here.\n\nClick below to stop support mode."
        keyboard = [[InlineKeyboardButton("🛑 Stop Support Chat", callback_data="main")]]
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_SUPPORT, caption=text, parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "main":
        support_users.discard(user_id) # Exit support mode
        await start(update, context)

    elif data.startswith("price_"):
        idx = int(data.split("_")[1])
        plan = PRICING_PLANS[idx]
        nav = []
        if idx > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"price_{idx-1}"))
        if idx < len(PRICING_PLANS)-1: nav.append(InlineKeyboardButton("➡️", callback_data=f"price_{idx+1}"))
        kb = [nav, [InlineKeyboardButton(f"💳 PURCHASE ₹{plan['price']}", callback_data=f"buy_{idx}")], [InlineKeyboardButton("🏠 Menu", callback_data="main")]]
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_PRICING, caption=plan['desc'], parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("buy_"):
        idx = int(data.split("_")[1])
        plan = PRICING_PLANS[idx]
        text = f"💳 **PAYMENT**\n{SEP}\nPlan: **{plan['title']}**\nPrice: `₹{plan['price']}`\nUPI: `{UPI_ID}`\n\n📸 **Send Screenshot** after paying."
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_PAYMENT, caption=text, parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"price_{idx}")]]))

    elif data.startswith("approve_"):
        if user_id not in ADMIN_ID: return
        uid, p_idx = int(data.split("_")[1]), int(data.split("_")[2])
        plan = PRICING_PLANS[p_idx]
        expiry = datetime.now() + timedelta(days=plan['days'])
        subscriptions[uid] = {"join_date": datetime.now(), "expiry_date": expiry, "plan_name": plan['title'], "user_name": "User"}
        save_data()
        try:
            link = await context.bot.create_chat_invite_link(chat_id=GROUP_CHAT_ID, member_limit=1)
            await context.bot.send_message(uid, f"✅ **Verified!**\nExpiry: {expiry.strftime('%Y-%m-%d')}\nJoin: {link.invite_link}")
            await query.edit_message_caption("🟢 User Approved.")
        except: pass

# --- 7. MESSAGE LOGIC (Live Support & Admin Replies) ---
async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user_id = update.effective_user.id

    # 1. ADMIN REPLIES (Livegram style)
    if user_id in ADMIN_ID and update.message.reply_to_message:
        reply_to = update.message.reply_to_message
        target_id = None
        
        # Check for forwarded info
        if reply_to.forward_from: target_id = reply_to.forward_from.id
        elif "ID:" in (reply_to.caption or reply_to.text or ""):
            try: target_id = int(reply_to.caption.split("ID:")[1].strip())
            except: pass
            
        if target_id:
            try:
                await context.bot.copy_message(chat_id=target_id, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
                await update.message.reply_text("✅ Reply sent to user.")
                return
            except: pass

    # 2. USER SENDING CONTENT
    if user_id not in ADMIN_ID:
        # If user is in support mode OR sends a photo (Payment proof)
        if user_id in support_users or update.message.photo:
            caption = f"💬 **Support Msg**\nFrom: {update.effective_user.first_name}\nID: {user_id}"
            kb = None
            if update.message.photo: # Payment Proof UI
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🥉 Bronze", callback_data=f"approve_{user_id}_0"), InlineKeyboardButton("🥈 Silver", callback_data=f"approve_{user_id}_1")],
                    [InlineKeyboardButton("🥇 Gold", callback_data=f"approve_{user_id}_2")]
                ])
            
            for adm in ADMIN_ID:
                try:
                    await context.bot.forward_message(chat_id=adm, from_chat_id=user_id, message_id=update.message.message_id)
                    if kb: await context.bot.send_message(chat_id=adm, text=caption, reply_markup=kb)
                except: pass
            
            if user_id in support_users: return # Stay in loop
            else: await update.message.reply_text("✅ Proof sent! Waiting for verification.")

def main():
    load_data()
    
    # FIXED: Render expects the app to bind to the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=port), daemon=True).start()
    
    threading.Thread(target=ping_self, daemon=True).start()
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("myplan", myplan))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & filters.ChatType.PRIVATE, global_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()

