# config.py - FIXED VERSION with Bulletproof Configuration
import os
from typing import List

def parse_channel_id(channel_str):
    """Parse channel ID from environment variable - handles all formats"""
    if not channel_str:
        return None

    # Handle integer IDs (including negative ones)
    try:
        return int(channel_str)
    except ValueError:
        # Handle string usernames (starting with @)
        if channel_str.startswith('@'):
            return channel_str
        # Handle t.me links
        elif channel_str.startswith('https://t.me/'):
            username = channel_str.split('/')[-1]
            return f"@{username}"
        # Handle channel IDs that might be strings with -100 prefix
        elif channel_str.startswith('-100'):
            try:
                return int(channel_str)
            except ValueError:
                return channel_str
        # Assume it's a username without @
        else:
            return f"@{channel_str}"

class Config:
    # Bot Configuration
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

    # Bot Info
    BOT_NAME = os.environ.get("BOT_NAME", "Video Merger Bot")
    DEVELOPER = os.environ.get("DEVELOPER", "@YourUsername")

    # Owner and Admins - FIXED PARSING
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
    ADMINS = []
    if os.environ.get("ADMINS"):
        try:
            ADMINS = [int(x.strip()) for x in os.environ.get("ADMINS", "").split(",") if x.strip()]
        except ValueError:
            ADMINS = []

    # Authorized Users and Chats - FIXED PARSING
    AUTHORIZED_USERS = []
    if os.environ.get("AUTHORIZED_USERS"):
        try:
            AUTHORIZED_USERS = [int(x.strip()) for x in os.environ.get("AUTHORIZED_USERS", "").split(",") if x.strip()]
        except ValueError:
            AUTHORIZED_USERS = []

    AUTHORIZED_CHATS = []
    if os.environ.get("AUTHORIZED_CHATS"):
        try:
            AUTHORIZED_CHATS = [int(x.strip()) for x in os.environ.get("AUTHORIZED_CHATS", "").split(",") if x.strip()]
        except ValueError:
            AUTHORIZED_CHATS = []

    # Channels Configuration - USING THE FIXED PARSING FUNCTION
    FORCE_SUB_CHANNEL = parse_channel_id(os.environ.get("FORCE_SUB_CHANNEL"))
    UPDATE_CHANNEL = os.environ.get("UPDATE_CHANNEL", "")
    SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP", "")
    LOG_CHANNEL = parse_channel_id(os.environ.get("LOG_CHANNEL"))
    NEW_USER_LOG_CHANNEL = parse_channel_id(os.environ.get("NEW_USER_LOG_CHANNEL"))
    MERGED_FILE_LOG_CHANNEL = parse_channel_id(os.environ.get("MERGED_FILE_LOG_CHANNEL"))

    # Database Configuration
    MONGO_URI = os.environ.get("MONGO_URI", "")
    DB_NAME = os.environ.get("DB_NAME", "video_merger_bot")

    # File Configuration
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "./downloads")
    MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", 2097152000))  # 2GB

    # GoFile Configuration
    GOFILE_TOKEN = os.environ.get("GOFILE_TOKEN", "")

    # Messages Configuration
    START_TEXT = """🎬 **Welcome to {bot_name}!**

👋 **Hello {user}!**

🚀 **What I can do:**
• Merge multiple videos into one
• Support various video formats
• Fast processing with queue management
• High-quality output

💡 **How to use:**
1. Send me video files or URLs
2. Add multiple videos to queue
3. Click "Merge Now" to combine them
4. Download your merged video!

⚡ **Ready to start merging videos?**
Use the buttons below to navigate!

🔧 **Developer:** {developer}"""

    START_PIC = os.environ.get("START_PIC", "")

    HELP_TEXT = """📖 **Help & Instructions**

🎬 **How to use this bot:**

**Step 1:** Send Videos
• Send video files directly
• Send video URLs (YouTube, etc.)
• Add multiple videos to queue

**Step 2:** Queue Management
• "Add More Videos" - Add more files
• "Clear All Videos" - Remove all from queue
• "Merge Now" - Start merging (appears after 2+ videos)

**Step 3:** Download Result
• Bot will process and merge your videos
• Download link will be provided
• High-quality merged output

**Note:** This bot only works in authorized groups. Please join our authorized merging group to use merging features.

**📋 Available Commands:**
• `/start` - Start the bot
• `/help` - Show this help
• `/about` - About the bot
• `/cancel` - Clear queue and cancel

**⚡ Pro Tips:**
• Videos with same resolution merge faster
• Supported formats: MP4, AVI, MKV, MOV, etc.
• Maximum file size: 2GB per video

**🛠️ Need help?** Join our support group!"""

    ABOUT_TEXT = """ℹ️ **About Video Merger Bot**

🤖 **Bot Name:** {bot_name}
👨‍💻 **Developer:** {developer}
📅 **Version:** v2.0 Advanced
🚀 **Language:** Python
⚙️ **Framework:** Pyrogram

**🌟 Features:**
• ✅ Multiple video merging
• ✅ URL support (YouTube, etc.)
• ✅ Queue management system
• ✅ Professional UI
• ✅ MongoDB database
• ✅ Admin panel
• ✅ Broadcast system
• ✅ Force subscribe
• ✅ User management

**📊 Performance:**
• Fast processing
• High-quality output
• Multiple format support
• Cloud storage integration

**💝 Support Development:**
If you like this bot, please:
• ⭐ Star our repository
• 📢 Share with friends
• 💬 Join our community

**🔗 Links:**
• Update Channel: {update_channel}
• Support Group: {support_group}

© 2024 - Made with ❤️"""

# Create global config instance
config = Config()
