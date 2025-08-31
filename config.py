# config.py
import os
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv('config.env')

class Config:
    # Telegram Bot Configuration
    API_ID = int(environ.get("API_ID"))
    API_HASH = environ.get("API_HASH")
    BOT_TOKEN = environ.get("BOT_TOKEN")
    
    # MongoDB Configuration
    MONGO_URI = environ.get("MONGO_URI", "mongodb://localhost:27017")
    DATABASE_NAME = environ.get("DATABASE_NAME", "video_merger_bot")
    
    # Channel & Group Configuration
    FORCE_SUB_CHANNEL = environ.get("FORCE_SUB_CHANNEL", "")  # @channel_username or channel_id
    UPDATE_CHANNEL = environ.get("UPDATE_CHANNEL", "")
    SUPPORT_GROUP = environ.get("SUPPORT_GROUP", "")
    
    # Admin Configuration
    OWNER_ID = int(environ.get("OWNER_ID", 0))
    ADMINS = [int(x) for x in environ.get("ADMINS", f"{OWNER_ID}").split()]
    
    # Logging Channels
    LOG_CHANNEL = int(environ.get("LOG_CHANNEL", 0))  # New User Log Channel
    MERGE_LOG_CHANNEL = int(environ.get("MERGE_LOG_CHANNEL", 0))  # Merged File Log Channel
    
    # File Storage
    DOWNLOAD_DIR = environ.get("DOWNLOAD_DIR", "downloads")
    GOFILE_TOKEN = environ.get("GOFILE_TOKEN", "")
    
    # Bot Settings
    BOT_NAME = environ.get("BOT_NAME", "Video Merger Bot")
    BOT_USERNAME = environ.get("BOT_USERNAME", "video_merger_bot")
    DEVELOPER = environ.get("DEVELOPER", "Your Name")
    
    # Welcome Message
    START_TEXT = """
🎬 **Welcome to {bot_name}!**

🚀 **Most Advanced Video Merger Bot**

✨ **Features:**
• Merge multiple videos instantly
• Support for direct links & file uploads
• High-quality output with all streams preserved
• Professional UI with smart controls

📝 **How to Use:**
1. Send videos or direct download links
2. Click "Merge Now" when ready
3. Choose upload destination
4. Get your merged file!

💫 **Developed by:** {developer}
"""

config = Config()
