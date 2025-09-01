# config.py
import os
from dotenv import load_dotenv

# Load environment variables from config.env
load_dotenv('config.env')

class Config:
    """
    Configuration class for the bot.
    Reads all the necessary environment variables.
    Raises an error if any critical variable is missing.
    """
    
    # ==================== TELEGRAM BOT CONFIGURATION ====================
    API_ID = os.environ.get("API_ID")
    API_HASH = os.environ.get("API_HASH")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    
    # ==================== MONGODB CONFIGURATION ====================
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "video_merger_bot")
    
    # ==================== CHANNEL & GROUP CONFIGURATION ====================
    # Force Subscribe Channel (Required to use bot)
    FORCE_SUB_CHANNEL = os.environ.get("FORCE_SUB_CHANNEL", "")
    
    # Update Channel (For updates button)
    UPDATE_CHANNEL = os.environ.get("UPDATE_CHANNEL", "")
    
    # Support Group (For support button)
    SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP", "")
    
    # ==================== ADMIN CONFIGURATION ====================
    OWNER_ID = os.environ.get("OWNER_ID")
    ADMINS = os.environ.get("ADMINS", "")
    
    # ==================== LOGGING CHANNELS ====================
    # Main log channel for user activities
    LOG_CHANNEL = os.environ.get("LOG_CHANNEL")
    
    # Separate channel for merge activities
    MERGE_LOG_CHANNEL = os.environ.get("MERGE_LOG_CHANNEL")
    
    # ==================== FILE STORAGE ====================
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")
    GOFILE_TOKEN = os.environ.get("GOFILE_TOKEN")
    
    # ==================== BOT SETTINGS ====================
    BOT_NAME = os.environ.get("BOT_NAME", "Video Merger Bot")
    BOT_USERNAME = os.environ.get("BOT_USERNAME", "video_merger_bot")
    DEVELOPER = os.environ.get("DEVELOPER", "Your Name")
    
    # ==================== FORCE SUBSCRIBE SETTINGS ====================
    # Picture for force subscribe message (optional)
    FORCE_SUB_PIC = os.environ.get("FORCE_SUB_PIC", "")
    
    # Start picture (optional)
    START_PIC = os.environ.get("START_PIC", "")
    
    # ==================== AUTHORIZED CHATS ====================
    # List of authorized group/channel IDs (space separated)
    AUTH_CHATS = os.environ.get("AUTH_CHATS", "")
    
    # ==================== WELCOME MESSAGES ====================
    START_TEXT = os.environ.get("START_TEXT", """
🎬 **Welcome to {bot_name}!**

🚀 **Most Advanced Video Merger Bot**

✨ **Features:**
• Merge multiple videos instantly
• Support for direct links & file uploads  
• High-quality output with all streams preserved
• Professional UI with smart controls
• Custom thumbnails support

📝 **How to Use:**
1. Send videos or direct download links
2. Click "Merge Now" when ready (minimum 2 videos)
3. Choose upload destination (Telegram/GoFile)
4. Set custom thumbnail and filename
5. Get your merged file!

💫 **Developed by:** {developer}

🔥 **Ready to merge some videos?** Send me your first video!
""")

    # ==================== ADDITIONAL TEXTS ====================
    HELP_TEXT = os.environ.get("HELP_TEXT", """
📚 **How to Use Video Merger Bot**

🎬 **Basic Usage:**
1. Send me videos or direct download links
2. I'll add them to your merge queue  
3. When you have 2+ videos, click "🎬 Merge Now"
4. Choose upload destination (Telegram or GoFile)
5. Get your merged video!

📝 **Supported Formats:**
• Video files uploaded to Telegram
• Direct download links (HTTP/HTTPS)
• Multiple video formats (MP4, MKV, AVI, etc.)

⚡ **Features:**
• Fast merging for compatible videos
• Automatic quality optimization
• Custom thumbnails support
• Progress tracking
• Multiple upload options

💡 **Tips:**
• Videos with same resolution merge faster
• Use /cancel to clear your queue anytime
• Large files may take longer to process

❓ **Need Help?** Contact our support team!
""")
    
    ABOUT_TEXT = os.environ.get("ABOUT_TEXT", """
ℹ️ **About {bot_name}**

🚀 **Professional Video Merging Solution**

This bot uses advanced FFmpeg technology to merge multiple videos with high-quality output. Perfect for combining episodes, clips, or any video content.

🌟 **Key Features:**
• Lightning-fast processing
• High-quality output preservation
• Multi-format support  
• Smart compression algorithms
• Professional user interface

📈 **Version:** 2.0 Professional
🛠 **Engine:** FFmpeg + Python
💻 **Developer:** {developer}

💝 **Thank you for using our bot!**
""")

# ==================== VALIDATION & CONVERSION ====================

def validate_config():
    """Validate and convert configuration values"""
    
    # Check required variables
    required_vars = ["API_ID", "API_HASH", "BOT_TOKEN"]
    missing = []
    
    for var in required_vars:
        if not getattr(Config, var):
            missing.append(var)
    
    if missing:
        raise ValueError(f"❌ Missing required environment variables: {', '.join(missing)}")
    
    # Convert string values to appropriate types
    try:
        # Convert API_ID to int
        Config.API_ID = int(Config.API_ID)
        
        # Convert Owner ID
        if Config.OWNER_ID:
            Config.OWNER_ID = int(Config.OWNER_ID)
        else:
            raise ValueError("OWNER_ID is required!")
        
        # Convert Log Channels
        if Config.LOG_CHANNEL:
            Config.LOG_CHANNEL = int(Config.LOG_CHANNEL)
        
        if Config.MERGE_LOG_CHANNEL:
            Config.MERGE_LOG_CHANNEL = int(Config.MERGE_LOG_CHANNEL)
        
        # Parse ADMINS into list of ints
        if Config.ADMINS:
            Config.ADMINS = [int(x.strip()) for x in Config.ADMINS.split(",") if x.strip().isdigit()]
        else:
            Config.ADMINS = []
        
        # Always include owner in admins
        if Config.OWNER_ID not in Config.ADMINS:
            Config.ADMINS.append(Config.OWNER_ID)
        
        # Parse AUTH_CHATS 
        if Config.AUTH_CHATS:
            Config.AUTH_CHATS = [int(x.strip()) for x in Config.AUTH_CHATS.split(",") if x.strip().lstrip('-').isdigit()]
        else:
            Config.AUTH_CHATS = []
            
    except ValueError as e:
        raise ValueError(f"❌ Configuration error: {e}")
    
    # Ensure download directory exists
    if not os.path.isdir(Config.DOWNLOAD_DIR):
        os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
    
    # Validate channel formats
    channels = [
        ("FORCE_SUB_CHANNEL", Config.FORCE_SUB_CHANNEL),
        ("UPDATE_CHANNEL", Config.UPDATE_CHANNEL), 
        ("SUPPORT_GROUP", Config.SUPPORT_GROUP)
    ]
    
    for name, value in channels:
        if value and not (value.startswith('@') or value.startswith('-100') or value.isdigit()):
            print(f"⚠️ Warning: {name} should start with @ or be a channel ID")

# Run validation
validate_config()

# ==================== HELPER FUNCTIONS ====================

def get_config_info():
    """Get configuration summary for startup"""
    return f"""
🔧 **Bot Configuration**
├── 🤖 Bot: {Config.BOT_NAME} (@{Config.BOT_USERNAME})
├── 👤 Owner: {Config.OWNER_ID}
├── 👥 Admins: {len(Config.ADMINS)} user(s)
├── 🔔 Force Subscribe: {"✅ Enabled" if Config.FORCE_SUB_CHANNEL else "❌ Disabled"}
├── 📊 Logging: {"✅ Enabled" if Config.LOG_CHANNEL else "❌ Disabled"}
├── 💾 Database: {"✅ Connected" if Config.MONGO_URI else "❌ Not configured"}
└── 📁 Download Dir: {Config.DOWNLOAD_DIR}
"""

def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in Config.ADMINS or user_id == Config.OWNER_ID

def is_owner(user_id: int) -> bool:
    """Check if user is owner"""
    return user_id == Config.OWNER_ID

def is_auth_chat(chat_id: int) -> bool:
    """Check if chat is authorized"""
    return chat_id in Config.AUTH_CHATS

# ==================== EXPORT ====================

# Create singleton instance
config = Config()

# Export commonly used values
API_ID = config.API_ID
API_HASH = config.API_HASH
BOT_TOKEN = config.BOT_TOKEN
OWNER_ID = config.OWNER_ID
ADMINS = config.ADMINS
MONGO_URI = config.MONGO_URI
DATABASE_NAME = config.DATABASE_NAME
BOT_NAME = config.BOT_NAME
DEVELOPER = config.DEVELOPER
FORCE_SUB_CHANNEL = config.FORCE_SUB_CHANNEL
LOG_CHANNEL = config.LOG_CHANNEL
MERGE_LOG_CHANNEL = config.MERGE_LOG_CHANNEL
DOWNLOAD_DIR = config.DOWNLOAD_DIR
