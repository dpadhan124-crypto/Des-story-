import os
import asyncio
import aiosqlite
import aiohttp
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMemberUpdated
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatMemberStatus
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# --- FILLED CONFIGURATION ---
API_ID = 28515728
API_HASH = "c8df3dfc2cb3cc6b0aa1b6ad6a0f8830"
BOT_TOKEN = "8552684809:AAGSRPA-3k0huC9fKBAvJGGI-VYfDhe4RJQ"
TARGET_GROUP_ID = -1003742470706
ADMIN_IDS = [8323137024, 8205396055, 5855151459]

# Render automatically provides this URL if you set it in the dashboard, 
# otherwise, use your literal URL:
RENDER_URL = "https://des-story-tg.onrender.com/"

DB_NAME = "bot_data.db"
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- KEEP ALIVE LOGIC ---
async def handle_ping(request):
    return web.Response(text="Bot is Running!")

async def start_web_server():
    server = web.Application()
    server.add_routes([web.get('/', handle_ping)])
    runner = web.AppRunner(server)
    await runner.setup()
    # Render uses port 8080 by default for web services
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

async def ping_self():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(RENDER_URL) as resp:
                print(f"Self-Ping: {resp.status} at {datetime.now()}")
        except Exception as e:
            print(f"Ping failed: {e}")

# --- DATABASE HELPERS ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('CREATE TABLE IF NOT EXISTS topics (channel_id INTEGER PRIMARY KEY, thread_id INTEGER, title TEXT)')
        await db.execute('CREATE TABLE IF NOT EXISTS admin_channels (channel_id INTEGER PRIMARY KEY, title TEXT)')
        await db.commit()

async def update_admin_channel(chat_id, title, is_admin):
    async with aiosqlite.connect(DB_NAME) as db:
        if is_admin:
            await db.execute("INSERT OR REPLACE INTO admin_channels VALUES (?, ?)", (chat_id, title))
        else:
            await db.execute("DELETE FROM admin_channels WHERE channel_id = ?", (chat_id,))
        await db.commit()

# --- CORE LOGIC ---
@app.on_chat_member_updated(filters.channel)
async def track_admins(_, update: ChatMemberUpdated):
    bot = await app.get_me()
    if update.new_chat_member and update.new_chat_member.user.id == bot.id:
        is_admin = update.new_chat_member.status == ChatMemberStatus.ADMINISTRATOR
        await update_admin_channel(update.chat.id, update.chat.title, is_admin)

@app.on_message((filters.audio | filters.video) & filters.channel)
async def forwarder(_, message: Message):
    source_id = message.chat.id
    source_title = message.chat.title or "Media Channel"

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT thread_id FROM topics WHERE channel_id=?", (source_id,)) as c:
            row = await c.fetchone()
            thread_id = row[0] if row else None

    if not thread_id:
        try:
            topic = await app.create_forum_topic(TARGET_GROUP_ID, source_title)
            thread_id = topic.id
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("INSERT INTO topics VALUES (?, ?, ?)", (source_id, thread_id, source_title))
                await db.commit()
        except Exception as e:
            print(f"Failed to create topic: {e}")
            return

    try:
        await app.forward_messages(
            chat_id=TARGET_GROUP_ID,
            from_chat_id=source_id,
            message_ids=message.id,
            message_thread_id=thread_id
        )
    except Exception as e:
        print(f"Forwarding failed: {e}")

async def clean_old_members(client, channel_ids):
    limit = datetime.utcnow() - timedelta(days=7)
    for cid in channel_ids:
        print(f"Cleaning channel {cid}...")
        try:
            async for m in client.get_chat_members(cid):
                if m.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                    continue
                if m.joined_date and m.joined_date < limit:
                    try:
                        await client.ban_chat_member(cid, m.user.id)
                        await client.unban_chat_member(cid, m.user.id)
                        await asyncio.sleep(1.5)
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except:
                        pass
        except Exception as e:
            print(f"Error accessing channel {cid}: {e}")

async def auto_job():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT channel_id FROM admin_channels") as c:
            rows = await c.fetchall()
            ids = [r[0] for r in rows]
            if ids:
                await clean_old_members(app, ids)

# --- ADMIN COMMANDS ---
@app.on_message(filters.command("stack") & filters.user(ADMIN_IDS))
async def stack_cmd(_, m: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT title, channel_id FROM admin_channels") as c:
            res = await c.fetchall()
            if not res:
                await m.reply("Not an admin in any channels yet.")
                return
            msg = "**Channels Managed:**\n" + "\n".join([f"• {r[0]} (`{r[1]}`)" for r in res])
            await m.reply(msg)

@app.on_message(filters.command("clean") & filters.user(ADMIN_IDS))
async def manual_clean(_, m: Message):
    await m.reply("Starting manual cleanup in the background...")
    asyncio.create_task(auto_job())

# --- MAIN STARTUP ---
async def start():
    await init_db()
    await start_web_server()
    
    sch = AsyncIOScheduler()
    # Runs at 2:30 AM every day
    sch.add_job(auto_job, "cron", hour=2, minute=30) 
    # Pings the URL every 10 minutes to stay alive
    sch.add_job(ping_self, "interval", minutes=10)   
    sch.start()
    
    print("Bot starting...")
    await app.start()
    print("Bot is alive and running!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(start())
