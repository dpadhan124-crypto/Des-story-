import logging
import threading
import time
import requests
from flask import Flask
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- 1. CONFIGURATION ---
BOT_TOKEN = "8585776527:AAETrFCcCnDNnpQS7FdqG_AkNrX4XDMrEY8"
ADMIN_ID = 8323137024
GROUP_CHAT_ID = -1003120753256
UPI_ID = "padhand171@okicici" 

# IMPORTANT: Replace this with your ACTUAL Render URL after you deploy
RENDER_EXTERNAL_URL = "https://your-app-name.onrender.com"

# Image Links
IMG_MAIN = "https://files.catbox.moe/wdldpl.jpg" 
IMG_ABOUT = "https://files.catbox.moe/65tg20.jpg"
IMG_SUPPORT = "https://files.catbox.moe/prrij6.jpg"
IMG_PRICING = "https://files.catbox.moe/hatjad.jpg"
IMG_PAYMENT = "https://files.catbox.moe/l9xvvz.jpg"

subscriptions = {}

PRICING_PLANS = [
    {"price": "₹99", "title": "🥉 BASIC", "desc": "• 1 month easy access to all stories\n• premium story access\n• serial-wise episodes \n• without any distubance", "style": "primary"},
    {"price": "₹149", "title": "🥈 STANDARD", "desc": "• 2 month easy access to all stories\n• premium story access\n• serial-wise episodes \n• without any distubance"},
    {"price": "₹299", "title": "🥇 PREMIUM", "desc": "• 5 month easy access to all stories\n• premium story access\n• serial-wise episodes \n• without any distubance", "style": "success"},
    {"price": "Custom", "title": "💎 VIP", "desc": "• lifetime access to all stories\n• premium story access\n• serial-wise episodes \n• without any distubance\n• Custom Requests", "style": "danger"}
]

SEP = "━━━━━━━━━━━━━━━━━━"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 2. KEEP-ALIVE SERVER (FLASK) ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is running and awake!"

def ping_self():
    """Function to ping the server every 14 minutes to prevent Render from sleeping."""
    time.sleep(30) # Wait for server to start
    while True:
        try:
            requests.get(RENDER_EXTERNAL_URL)
            logging.info("Self-ping successful: Staying alive.")
        except Exception as e:
            logging.error(f"Self-ping failed: {e}")
        time.sleep(840) # 14 minutes

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# --- 3. TELEGRAM UI FUNCTIONS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"👑 **DPS STORIES PREMIUM** 👑\n"
        f"{SEP}\n"
        f"Hello **{update.effective_user.first_name}**,\n"
        f"Step into the world of *Shunya Samrat*.\n\n"
        f"Select an option below to begin your journey.\n"
        f"[​​​​​​​​​​​]({IMG_MAIN})"
    )
    
    keyboard = [
        [InlineKeyboardButton("💎 EXPLORE PLANS 💎", callback_data="price_0")],
        [
            InlineKeyboardButton("📖 About Us", callback_data="about"),
            InlineKeyboardButton("💬 Support", callback_data="connect")
        ],
        [InlineKeyboardButton("📢 Official Channel", url="https://t.me/DPS_Stories")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "about":
        text = (
            f"📜 **OUR MISSION**\n"
            f"{SEP}\n"
            f"Bringing epic legends to life with premium Hindi translations and immersive audio experiences.\n"
            f"[​​​​​​​​​​​]({IMG_ABOUT})"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "connect":
        text = (
            f"📞 **LIVE HELPLINE**\n"
            f"{SEP}\n"
            f"Need help? Simply type your message below. Our support team will respond to you directly in this chat.\n"
            f"[​​​​​​​​​​​]({IMG_SUPPORT})"
        )
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("price_"):
        index = int(data.split("_")[1])
        plan = PRICING_PLANS[index]
        
        text = (
            f"⚡ **SELECT YOUR PLAN**\n"
            f"{SEP}\n"
            f"✨ **{plan['title']}**\n"
            f"💰 Price: `{plan['price']}`\n\n"
            f"{plan['desc']}\n"
            f"{SEP}\n"
            f"[​​​​​​​​​​​]({IMG_PRICING})"
        )
        
        nav_row = []
        if index > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"price_{index-1}"))
        if index < len(PRICING_PLANS) - 1:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"price_{index+1}"))
            
        keyboard = [
            nav_row, 
            [InlineKeyboardButton(f"💳 PURCHASE {plan['price']}", callback_data=f"buy_{index}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("buy_"):
        index = int(data.split("_")[1])
        plan = PRICING_PLANS[index]
        text = (
            f"💳 **PAYMENT GATEWAY**\n"
            f"{SEP}\n"
            f"Plan: **{plan['title']}**\n"
            f"Amount: `{plan['price']}`\n\n"
            f"Scan the QR or pay to UPI ID:\n"
            f"🆔 `{UPI_ID}`\n\n"
            f"📸 **IMPORTANT:** Send the payment screenshot here for verification.\n"
            f"[​​​​​​​​​​​]({IMG_PAYMENT})"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Plans", callback_data=f"price_{index}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("approve_"):
        user_id = int(data.split("_")[1])
        link = await context.bot.create_chat_invite_link(chat_id=GROUP_CHAT_ID, member_limit=1)
        subscriptions[user_id] = datetime.now() + timedelta(minutes=1) 
        await context.bot.send_message(chat_id=user_id, text=f"✅ **Verified!** Access granted.\n\nJoin here: {link.invite_link}")
        await query.edit_message_text(text=f"🟢 User {user_id} Approved.")

    elif data.startswith("dismiss_"):
        user_id = int(data.split("_")[1])
        await context.bot.send_message(chat_id=user_id, text="❌ **Verification Failed**\nWe couldn't verify your payment. Please contact support if this is an error.")
        await query.edit_message_text(text=f"🔴 User {user_id} Rejected.")

    elif data == "main":
        await start(update, context)

# --- 4. MESSAGE & ADMIN LOGIC ---

async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id == ADMIN_ID and update.message.reply_to_message:
        try:
            if update.message.reply_to_message.forward_origin:
                target_id = update.message.reply_to_message.forward_origin.sender_user.id
                await context.bot.send_message(chat_id=target_id, text=f"💬 **Support Response:**\n\n{update.message.text}")
                await update.message.reply_text("✅ Reply sent to user.")
            return
        except Exception:
            return

    if update.message.photo:
        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"dismiss_{user_id}")
        ]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **New Payment Proof**\nFrom User: `{user_id}`", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.forward(chat_id=ADMIN_ID)
        await update.message.reply_text("✅ **Screenshot Received!**\nPlease wait while our team verifies your payment.")
        return

    if user_id != ADMIN_ID:
        await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=update.message.chat_id, message_id=update.message.message_id)

async def auto_remove_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    expired = [uid for uid, time in subscriptions.items() if now > time]
    for uid in expired:
        try:
            await context.bot.ban_chat_member(chat_id=GROUP_CHAT_ID, user_id=uid)
            await context.bot.unban_chat_member(chat_id=GROUP_CHAT_ID, user_id=uid)
            del subscriptions[uid]
            await context.bot.send_message(chat_id=uid, text="⌛ **Subscription Expired!**\nRenew your plan to continue listening.")
        except: pass

def main():
    # 1. Start Flask in a background thread
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 2. Start the self-pinging loop in a background thread
    threading.Thread(target=ping_self, daemon=True).start()

    # 3. Start Telegram Bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, global_handler))
    
    if app.job_queue:
        app.job_queue.run_repeating(auto_remove_job, interval=10)
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
