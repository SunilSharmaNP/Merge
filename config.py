# config.py - Enhanced Configuration with better channel parsing
import os
from typing import List, Union

def parse_channel_id(channel_str: str) -> Union[int, str, None]:
    """Enhanced channel ID parsing with better error handling"""
    if not channel_str:
        return None
    
    channel_str = channel_str.strip()
    
    # Handle integer IDs (including negative ones for supergroups)
    try:
        channel_id = int(channel_str)
        return channel_id
    except ValueError:
        pass
    
    # Handle string usernames
    if channel_str.startswith('@'):
        return channel_str
    elif channel_str.startswith('https://t.me/'):
        # Extract username from t.me link
        username = channel_str.split('/')[-1]
        if username and not username.isdigit():
            return f"@{username}"
        else:
            # It might be a private group link
            return channel_str
    else:
        # Assume it's a username without @
        if not channel_str.isdigit():
            return f"@{channel_str}"
        else:
            # It's a numeric string, convert to int
            try:
                return int(channel_str)
            except ValueError:
                return channel_str

def parse_list_from_env(env_var: str, default: list = None) -> List[int]:
    """Parse list of integers from environment variable"""
    if default is None:
        default = []
    
    env_value = os.environ.get(env_var, "")
    if not env_value:
        return default
    
    try:
        return [int(x.strip()) for x in env_value.split(",") if x.strip().isdigit()]
    except ValueError:
        return default

class Config:
    # ===================== BOT CONFIGURATION =====================
    
    # Required API credentials
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    
    # Bot Information
    BOT_NAME = os.environ.get("BOT_NAME", "Professional Video Merger Bot")
    DEVELOPER = os.environ.get("DEVELOPER", "@YourUsername")
    
    # ===================== USER MANAGEMENT =====================
    
    # Owner and Admins
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
    ADMINS = parse_list_from_env("ADMINS")
    
    # Authorized Users and Chats
    AUTHORIZED_USERS = parse_list_from_env("AUTHORIZED_USERS")
    AUTHORIZED_CHATS = parse_list_from_env("AUTHORIZED_CHATS")
    
    # ===================== CHANNELS CONFIGURATION =====================
    
    # Force Subscribe Channel (REQUIRED)
    FORCE_SUB_CHANNEL = parse_channel_id(os.environ.get("FORCE_SUB_CHANNEL"))
    
    # Optional Channels
    UPDATE_CHANNEL = os.environ.get("UPDATE_CHANNEL", "")
    SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP", "")
    
    # Logging Channels
    LOG_CHANNEL = parse_channel_id(os.environ.get("LOG_CHANNEL"))
    NEW_USER_LOG_CHANNEL = parse_channel_id(os.environ.get("NEW_USER_LOG_CHANNEL"))
    MERGED_FILE_LOG_CHANNEL = parse_channel_id(os.environ.get("MERGED_FILE_LOG_CHANNEL"))
    
    # ===================== DATABASE CONFIGURATION =====================
    
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME = os.environ.get("DB_NAME", "video_merger_bot")
    
    # ===================== FILE CONFIGURATION =====================
    
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "./downloads")
    MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "2147483648"))  # 2GB default
    
    # ===================== EXTERNAL SERVICES =====================
    
    # GoFile Configuration
    GOFILE_TOKEN = os.environ.get("GOFILE_TOKEN", "")
    
    # ===================== BOT MESSAGES =====================
    
    START_TEXT = """🎬 **Welcome to {bot_name}!**

👋 **Hello {user}!** Welcome to the most advanced video merger bot!

🚀 **What I can do:**
• 🎬 Merge unlimited videos into one
• 📱 Support all video formats (MP4, AVI, MKV, MOV, etc.)
• 🔗 Download from URLs (YouTube, etc.)
• ⚡ Lightning-fast processing with queue management
• 🎯 Lossless quality output
• 📊 Real-time progress tracking

💡 **How to use:**
1. **Send Videos:** Upload files or send URLs
2. **Add to Queue:** Build your video collection  
3. **Merge Now:** Combine them seamlessly
4. **Download:** Get your merged masterpiece!

⚡ **Ready to create amazing merged videos?**
Use the buttons below to explore!

🔧 **Developer:** {developer}

*Professional Video Merging at Your Fingertips* ✨"""
    
    START_PIC = os.environ.get("START_PIC", "")
    
    HELP_TEXT = """📖 **Complete User Guide**

🎬 **Welcome to the most advanced video merger bot!**

**🚀 Quick Start:**
1. Join our required channel (if prompted)
2. Use /merge command to begin
3. Send your videos or URLs
4. Click "Merge Now" when ready
5. Choose download method

**📤 Supported Input:**
• **Video Files:** MP4, AVI, MKV, MOV, WMV, FLV, WEBM, M4V
• **Video URLs:** YouTube, Vimeo, Dailymotion, etc.
• **File Size:** Up to 2GB per video
• **Quantity:** Unlimited videos in queue

**🎯 Merging Process:**
• **Queue System:** Add multiple videos before merging
• **Smart Processing:** Automatic quality optimization
• **Progress Tracking:** Real-time status updates
• **Quality Preservation:** Lossless merging when possible

**📋 Available Commands:**
• `/start` - Welcome & main menu
• `/help` - This comprehensive guide
• `/about` - Bot information & features
• `/merge` - Start merging process
• `/cancel` - Clear queue & cancel operation
• `/stats` - Statistics (Admin only)

**🔒 Access Control:**
• **Private Chat:** Owner and authorized users only
• **Group Chat:** Authorized groups only
• **Contact:** Message owner for access authorization

**⚡ Pro Tips for Best Results:**
• Videos with identical resolution merge fastest
• Use consistent frame rates for smooth playback
• MP4 format recommended for best compatibility
• Queue similar quality videos together
• Large files may take longer to process

**🛠️ Troubleshooting:**
• **Slow Processing:** Large files take time, be patient
• **Format Issues:** Try converting to MP4 first
• **Upload Failures:** Check file size and internet connection
• **Access Denied:** Join authorized groups or contact owner

**📞 Support:**
Need help? Join our support group or contact the developer!

**Made with ❤️ for seamless video merging**"""

    ABOUT_TEXT = """ℹ️ **About {bot_name}**

🤖 **Bot Information:**
• **Name:** {bot_name}
• **Developer:** {developer}
• **Version:** v2.0 Professional Edition
• **Language:** Python 3.11+
• **Framework:** Pyrogram (Advanced)
• **Database:** MongoDB Atlas

**🌟 Advanced Features:**

**Core Functionality:**
• ✅ Multi-video merging with queue system
• ✅ URL download support (YouTube, etc.)
• ✅ Professional progress indicators
• ✅ Lossless quality preservation
• ✅ Multiple output format support
• ✅ Smart error handling & recovery

**User Experience:**
• ✅ Intuitive button-based interface
• ✅ Real-time operation feedback
• ✅ Advanced queue management
• ✅ Custom filename support
• ✅ Thumbnail generation
• ✅ Comprehensive help system

**Administration:**
• ✅ Force subscribe system
• ✅ User authorization controls
• ✅ Broadcasting system
• ✅ Comprehensive logging
• ✅ Statistics & analytics
• ✅ Admin panel interface

**Security & Performance:**
• ✅ Group-based access control
• ✅ User ban/unban system
• ✅ Rate limiting protection
• ✅ Error logging & monitoring
• ✅ Automatic cleanup system
• ✅ Optimized file handling

**📊 Technical Specifications:**
• **Processing:** FFmpeg with hardware acceleration
• **Storage:** Cloud-based with auto-cleanup
• **Upload Methods:** Telegram & GoFile.io
• **Max File Size:** 2GB per video
• **Supported Formats:** All major video formats
• **Concurrent Users:** Unlimited with queuing

**🔗 Important Links:**
• **Updates:** {update_channel}
• **Support:** {support_group}
• **Developer:** Contact for business inquiries

**📈 Usage Statistics:**
This bot processes thousands of videos daily with 99.9% uptime and user satisfaction!

**💝 Acknowledgments:**
Special thanks to our community for feedback and support in making this the best video merger bot on Telegram!

© 2024 - Crafted with passion by {developer}

*Setting new standards in video merging technology* 🚀"""

# Create config instance
config = Config()

# Validation
if not config.API_ID or not config.API_HASH or not config.BOT_TOKEN:
    raise ValueError("Missing required bot credentials in environment variables!")

if not config.OWNER_ID:
    raise ValueError("OWNER_ID is required in environment variables!")

# Create download directory if it doesn't exist
os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

print(f"✅ Configuration loaded successfully!")
print(f"🤖 Bot Name: {config.BOT_NAME}")
print(f"👨‍💻 Developer: {config.DEVELOPER}")
print(f"🆔 Owner ID: {config.OWNER_ID}")
print(f"👥 Admins: {len(config.ADMINS)}")
print(f"🔒 Authorized Users: {len(config.AUTHORIZED_USERS)}")
print(f"💬 Authorized Chats: {len(config.AUTHORIZED_CHATS)}")
print(f"📢 Force Sub Channel: {config.FORCE_SUB_CHANNEL}")
print(f"📁 Download Directory: {config.DOWNLOAD_DIR}")
