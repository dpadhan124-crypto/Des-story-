# Telegram Media Forwarder & Auto-Cleaner

## Setup on Render
1. Create a **Web Service**.
2. Connect this GitHub Repo.
3. Add these **Environment Variables**:
   - `API_ID`: Your Telegram API ID.
   - `API_HASH`: Your Telegram API Hash.
   - `BOT_TOKEN`: Your Bot Token.
   - `TARGET_GROUP_ID`: ID of the group with topics.
   - `ADMIN_IDS`: Your ID (e.g., 1234567).
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `python bot.py`
