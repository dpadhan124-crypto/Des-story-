import logging
import threading
import time
import requests
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
BOT_TOKEN = "8585776527:AAETrFCcCnDNnpQS7FdqG_AkNrX4XDMrEY8"
ADMIN_ID = 8323137024
GROUP_CHAT_ID = -1003120753256
UPI_ID = "padhand171@okicici" 

RENDER_EXTERNAL_URL = "https://des-story-tg.onrender.com"

# Image Links
IMG_MAIN = "https://files.catbox.moe/wdldpl.jpg" 
IMG_ABOUT = "https://files.catbox.moe/65tg20.jpg"
IMG_SUPPORT = "https://files.catbox.moe/prrij6.jpg"
IMG_PRICING = "https://files.catbox.moe/3rd6b3.jpg"
IMG_PAYMENT = "https://files.catbox.moe/l9xvvz.jpg"
IMG_PLAN = "https://files.catbox.moe/wdldpl.jpg" # Image for /myplan

# Database to store user subscriptions
# Structure: {user_id: {"join_date": dt, "expiry_date": dt, "plan_name": str}}
subscriptions = {}

PRICING_PLANS = [
    {"price": "99", "title": "🥉 BASIC", "desc": "• 1 month easy access\n• Premium stories\n• No disturbance"},
    {"price": "149", "title": "🥈 STANDARD", "desc": "• 2 month easy access\n• Premium stories\n• No disturbance"},
    {"price": "299", "title": "🥇 PREMIUM", "desc": "• 5 month easy access\n• Premium stories\n• No disturbance"},
    {"price": "Custom", "title": "💎 VIP", "desc": "• Lifetime access\n• Custom Requests"}
]

SEP = "━━━━━━━━━━━━━━━━━━"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 2. KEEP-ALIVE SERVER (FLASK) ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is running!"

def ping_self():
    time.sleep(30)
    while True:
        try:
            requests.get(RENDER_EXTERNAL_URL)
        except: pass
        time.sleep(840)

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# --- 3. TELEGRAM UI FUNCTIONS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"👑 **DPS STORIES PREMIUM** 👑\n"
        f"{SEP}\n"
        f"Hello **{update.effective_user.first_name}**,\n"
        f"Step into the world of *Shunya Samrat*.\n\n"
        f"Select an option below to begin your journey."
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
        await update.message.reply_photo(photo=IMG_MAIN, caption=text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_media(
            media=InputMediaPhoto(media=IMG_MAIN, caption=text, parse_mode="Markdown"),
            reply_markup=reply_markup
        )

async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in subscriptions:
        await update.message.reply_text("❌ **No Active Plan Found.**\nUse /start to view our premium plans.")
        return

    sub = subscriptions[user_id]
    join_dt = sub['join_date'].strftime("%Y-%m-%d")
    expiry_dt = sub['expiry_date'].strftime("%Y-%m-%d")
    remind_dt = (sub['expiry_date'] - timedelta(days=2)).strftime("%Y-%m-%d")
    
    text = (
        f"👤 **YOUR SUBSCRIPTION**\n"
        f"{SEP}\n"
        f"🏷 Plan: **{sub['plan_name']}**\n"
        f"📅 Joined: `{join_dt}`\n"
        f"⏳ Expires: `{expiry_dt}`\n"
        f"🔔 Renewal Reminder: `{remind_dt}`\n"
        f"{SEP}\n"
        f"Thank you for being a part of DPS Stories!"
    )
    
    await update.message.reply_photo(photo=IMG_PLAN, caption=text, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "about":
        text = f"📜 **OUR MISSION**\n{SEP}\nBringing epic legends to life with premium Hindi translations."
        keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main")]]
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_ABOUT, caption=text, parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "connect":
        text = f"📞 **LIVE HELPLINE**\n{SEP}\nType your message below. Our support team will respond directly."
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main")]]
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_SUPPORT, caption=text, parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("price_"):
        index = int(data.split("_")[1])
        plan = PRICING_PLANS[index]
        text = f"⚡ **{plan['title']}**\n💰 Price: `₹{plan['price']}`\n\n{plan['desc']}"
        
        nav_row = []
        if index > 0: nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"price_{index-1}"))
        if index < len(PRICING_PLANS) - 1: nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"price_{index+1}"))
            
        keyboard = [nav_row, [InlineKeyboardButton(f"💳 PURCHASE", callback_data=f"buy_{index}")], [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]]
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_PRICING, caption=text, parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_"):
        index = int(data.split("_")[1])
        plan = PRICING_PLANS[index]
        text = f"💳 **PAYMENT**\n{SEP}\nPlan: **{plan['title']}**\nUPI: `{UPI_ID}`\n[QR Code](https://files.catbox.moe/8g6guc.jpg)\n\n📸 Send screenshot here."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"price_{index}")]]
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_PAYMENT, caption=text, parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("approve_"):
        user_id = data.split("_")[1]
        await query.message.reply_text(f"✍️ **Admin, please reply to this message with the validity in days (e.g., 30) for User `{user_id}`**")

    elif data.startswith("dismiss_"):
        user_id = int(data.split("_")[1])
        await context.bot.send_message(chat_id=user_id, text="❌ **Verification Failed.** Contact support.")
        await query.edit_message_caption(caption=f"🔴 User {user_id} Rejected.")

    elif data == "main":
        await start(update, context)

# --- 4. MESSAGE & ADMIN LOGIC ---

async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg_text = update.message.text

    # ADMIN LOGIC: Approval with validity entry
    if user_id == ADMIN_ID and update.message.reply_to_message:
        reply_msg = update.message.reply_to_message
        
        # Check if Admin is providing validity days
        if "Admin, please reply" in reply_msg.text:
            try:
                days = int(msg_text)
                # Extract target user ID from the prompt text
                target_id = int(reply_msg.text.split("User `")[1].split("`")[0])
                
                # Update Subscription
                expiry = datetime.now() + timedelta(days=days)
                subscriptions[target_id] = {
                    "join_date": datetime.now(),
                    "expiry_date": expiry,
                    "plan_name": f"{days} Days Access"
                }
                
                link = await context.bot.create_chat_invite_link(chat_id=GROUP_CHAT_ID, member_limit=1)
                await context.bot.send_message(chat_id=target_id, text=f"✅ **Verified!** Plan active until {expiry.strftime('%Y-%m-%d')}.\n\nJoin: {link.invite_link}")
                await update.message.reply_text(f"🟢 User {target_id} approved for {days} days.")
                return
            except Exception as e:
                await update.message.reply_text("⚠️ Please enter a valid number of days.")
                return

        # Admin Support Reply
        if reply_msg.forward_origin:
            target_id = reply_msg.forward_origin.sender_user.id
            await context.bot.send_message(chat_id=target_id, text=f"💬 **Support:** {msg_text}")
            await update.message.reply_text("✅ Reply sent.")
            return

    # USER LOGIC: Sending payment screenshot
    if update.message.photo:
        keyboard = [[InlineKeyboardButton("✅ Approve (Enter Days)", callback_data=f"approve_{user_id}"),
                     InlineKeyboardButton("❌ Reject", callback_data=f"dismiss_{user_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **Payment Proof**\nUser: `{user_id}`", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.forward(chat_id=ADMIN_ID)
        await update.message.reply_text("✅ **Screenshot Received!** Please wait for verification.")
        return

    # Regular Support Forwarding
    if user_id != ADMIN_ID:
        await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=update.message.chat_id, message_id=update.message.message_id)

async def auto_remove_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    expired = [uid for uid, data in subscriptions.items() if now > data['expiry_date']]
    for uid in expired:
        try:
            await context.bot.ban_chat_member(chat_id=GROUP_CHAT_ID, user_id=uid)
            await context.bot.unban_chat_member(chat_id=GROUP_CHAT_ID, user_id=uid)
            del subscriptions[uid]
            await context.bot.send_message(chat_id=uid, text="⌛ **Expired!** Renew your plan.")
        except: pass

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=ping_self, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myplan", myplan))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, global_handler))
    
    if app.job_queue:
        app.job_queue.run_repeating(auto_remove_job, interval=60)
    
    print("Bot is live...")
    app.run_polling()

if __name__ == "__main__":
    main()
