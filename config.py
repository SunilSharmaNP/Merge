# config.py - ENHANCED VERSION with Advanced Validation & Health Monitoring
import os
import re
import logging
from typing import List, Union, Optional
from datetime import datetime

# Setup logging for config validation
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConfigValidator:
    """Advanced configuration validator with health checks"""
    
    @staticmethod
    def validate_api_id(api_id_str: str) -> int:
        """Validate and clean API_ID"""
        if not api_id_str:
            raise ValueError("API_ID is required")
        
        # Remove any non-digit characters (fix for "10457w3")
        clean_id = re.sub(r'[^\d]', '', str(api_id_str))
        
        if not clean_id:
            raise ValueError("API_ID must contain digits")
        
        api_id = int(clean_id)
        if api_id <= 0:
            raise ValueError("API_ID must be a positive integer")
        
        logger.info(f"✅ API_ID validated and cleaned: {api_id}")
        return api_id
    
    @staticmethod
    def validate_channel_id(channel_str: str) -> Optional[Union[str, int]]:
        """Parse and validate channel ID from environment variable"""
        if not channel_str:
            return None

        channel_str = str(channel_str).strip()
        
        # Handle integer IDs (including negative ones)
        try:
            channel_id = int(channel_str)
            logger.info(f"✅ Channel ID validated: {channel_id}")
            return channel_id
        except ValueError:
            pass
        
        # Handle string usernames (starting with @)
        if channel_str.startswith('@'):
            if len(channel_str) > 1:
                logger.info(f"✅ Channel username validated: {channel_str}")
                return channel_str
            else:
                raise ValueError(f"Invalid channel username: {channel_str}")
        
        # Handle t.me links
        elif channel_str.startswith('https://t.me/'):
            username = channel_str.split('/')[-1]
            if username:
                validated = f"@{username}"
                logger.info(f"✅ Channel URL converted to username: {validated}")
                return validated
            else:
                raise ValueError(f"Invalid t.me URL: {channel_str}")
        
        # Assume it's a username without @
        else:
            validated = f"@{channel_str}"
            logger.info(f"✅ Channel assumed as username: {validated}")
            return validated
    
    @staticmethod
    def parse_user_list(users_str: str) -> List[int]:
        """Parse comma-separated user IDs"""
        if not users_str:
            return []
        
        user_list = []
        for user_id_str in users_str.split(','):
            user_id_str = user_id_str.strip()
            if user_id_str:
                try:
                    user_id = int(user_id_str)
                    user_list.append(user_id)
                except ValueError:
                    logger.warning(f"⚠️ Invalid user ID skipped: {user_id_str}")
        
        logger.info(f"✅ Parsed {len(user_list)} valid user IDs")
        return user_list
    
    @staticmethod
    def parse_chat_list(chats_str: str) -> List[int]:
        """Parse comma-separated chat IDs"""
        if not chats_str:
            return []
        
        chat_list = []
        for chat_id_str in chats_str.split(','):
            chat_id_str = chat_id_str.strip()
            if chat_id_str:
                try:
                    chat_id = int(chat_id_str)
                    chat_list.append(chat_id)
                except ValueError:
                    logger.warning(f"⚠️ Invalid chat ID skipped: {chat_id_str}")
        
        logger.info(f"✅ Parsed {len(chat_list)} valid chat IDs")
        return chat_list

class EnhancedConfig:
    """Enhanced configuration class with validation and health monitoring"""
    
    def __init__(self):
        self.validation_errors = []
        self.warnings = []
        self._load_config()
        self._validate_config()
        self._log_config_status()
    
    def _load_config(self):
        """Load all configuration from environment variables"""
        try:
            # Bot Configuration (Required)
            self.API_ID = ConfigValidator.validate_api_id(os.environ.get("API_ID", "0"))
            self.API_HASH = os.environ.get("API_HASH", "")
            self.BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
            
            if not self.API_HASH:
                self.validation_errors.append("API_HASH is required")
            if not self.BOT_TOKEN:
                self.validation_errors.append("BOT_TOKEN is required")
            
            # Bot Info
            self.BOT_NAME = os.environ.get("BOT_NAME", "SS Merger Bot")
            self.DEVELOPER = os.environ.get("DEVELOPER", "𓆩Ꞩᵾꞥīł Ꞩħⱥɍᵯⱥ ƻ.Ꝋ [🇳🇵]𓆪")
            
            # Owner and Admins
            self.OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
            if self.OWNER_ID == 0:
                self.validation_errors.append("OWNER_ID is required")
            
            self.ADMINS = ConfigValidator.parse_user_list(os.environ.get("ADMINS", ""))
            if self.OWNER_ID not in self.ADMINS:
                self.ADMINS.append(self.OWNER_ID)
            
            # Authorized Users and Chats
            self.AUTHORIZED_USERS = ConfigValidator.parse_user_list(os.environ.get("AUTHORIZED_USERS", ""))
            self.AUTHORIZED_CHATS = ConfigValidator.parse_chat_list(os.environ.get("AUTHORIZED_CHATS", ""))
            
            # Channels Configuration
            self.FORCE_SUB_CHANNEL = ConfigValidator.validate_channel_id(os.environ.get("FORCE_SUB_CHANNEL"))
            self.UPDATE_CHANNEL = os.environ.get("UPDATE_CHANNEL", "")
            self.SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP", "")
            self.LOG_CHANNEL = ConfigValidator.validate_channel_id(os.environ.get("LOG_CHANNEL"))
            self.NEW_USER_LOG_CHANNEL = ConfigValidator.validate_channel_id(os.environ.get("NEW_USER_LOG_CHANNEL"))
            self.MERGED_FILE_LOG_CHANNEL = ConfigValidator.validate_channel_id(os.environ.get("MERGED_FILE_LOG_CHANNEL"))
            
            # Database Configuration
            self.MONGO_URI = os.environ.get("MONGO_URI", "")
            self.DB_NAME = os.environ.get("DB_NAME", "sunil_sharma_merger")
            
            # File Configuration
            self.DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "./downloads")
            self.MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", 80147483648))  # 80GB as per your config
            
            # GoFile Configuration
            self.GOFILE_TOKEN = os.environ.get("GOFILE_TOKEN", "")
            
            # Messages Configuration
            self.START_TEXT = """🎬 **Welcome to {bot_name}!**

👋 **Hello {user}!**

🚀 **What I can do:**
• 🎥 Merge multiple videos into one seamlessly
• 📂 Support various video formats (MP4, MKV, AVI, etc.)
• ⚡ Lightning-fast processing with smart queue management
• 🎨 High-quality output with professional results
• 📊 Real-time progress tracking
• ☁️ Multiple upload options (Telegram/GoFile)

💡 **How to use:**
1. 📤 Send me video files or paste video URLs
2. ➕ Add multiple videos to your merge queue
3. 🎬 Click "Merge Now" to combine them
4. 📥 Download your perfectly merged video!

⚡ **Ready to create something amazing?**
Use the buttons below to get started!

👨‍💻 **Developer:** {developer}"""

            self.START_PIC = os.environ.get("START_PIC", "")
            
            # Health Check Configuration
            self.HEALTH_CHECK_INTERVAL = int(os.environ.get("HEALTH_CHECK_INTERVAL", "300"))  # 5 minutes
            self.MAX_RETRY_ATTEMPTS = int(os.environ.get("MAX_RETRY_ATTEMPTS", "3"))
            
        except Exception as e:
            self.validation_errors.append(f"Configuration loading error: {str(e)}")
    
    def _validate_config(self):
        """Perform additional validation"""
        # Validate file size
        if self.MAX_FILE_SIZE <= 0:
            self.validation_errors.append("MAX_FILE_SIZE must be positive")
        
        # Check if download directory is writable
        try:
            os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
            if not os.access(self.DOWNLOAD_DIR, os.W_OK):
                self.validation_errors.append(f"Download directory is not writable: {self.DOWNLOAD_DIR}")
        except Exception as e:
            self.validation_errors.append(f"Cannot create download directory: {str(e)}")
        
        # Database validation
        if not self.MONGO_URI:
            self.warnings.append("MongoDB URI not provided - database features will be limited")
        
        # GoFile validation
        if not self.GOFILE_TOKEN:
            self.warnings.append("GoFile token not provided - external uploads will be limited")
    
    def _log_config_status(self):
        """Log configuration status"""
        logger.info("🔧 Configuration Loading Complete!")
        logger.info(f"📊 Bot Name: {self.BOT_NAME}")
        logger.info(f"👑 Owner ID: {self.OWNER_ID}")
        logger.info(f"👥 Admins: {len(self.ADMINS)} configured")
        logger.info(f"🏠 Authorized Chats: {len(self.AUTHORIZED_CHATS)} configured")
        logger.info(f"📁 Download Directory: {self.DOWNLOAD_DIR}")
        
        if self.validation_errors:
            logger.error("❌ Configuration Errors:")
            for error in self.validation_errors:
                logger.error(f"   • {error}")
        
        if self.warnings:
            logger.warning("⚠️ Configuration Warnings:")
            for warning in self.warnings:
                logger.warning(f"   • {warning}")
        
        if not self.validation_errors:
            logger.info("✅ Configuration validation passed!")
    
    def is_valid(self) -> bool:
        """Check if configuration is valid"""
        return len(self.validation_errors) == 0
    
    def get_health_status(self) -> dict:
        """Get configuration health status"""
        return {
            "valid": self.is_valid(),
            "errors": self.validation_errors,
            "warnings": self.warnings,
            "loaded_at": datetime.now().isoformat()
        }

# Create global config instance
config = EnhancedConfig()

# Export validation status
CONFIG_VALID = config.is_valid()
CONFIG_ERRORS = config.validation_errors
CONFIG_WARNINGS = config.warnings
