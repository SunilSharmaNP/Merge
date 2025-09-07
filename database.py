# database.py - Enhanced MongoDB Database Management with Logging
import motor.motor_asyncio
from datetime import datetime
from config import config
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_URI)
        self.db = self.client[config.DATABASE_NAME]

        # Collections
        self.users = self.db.users
        self.authorized_chats = self.db.authorized_chats
        self.merge_logs = self.db.merge_logs
        self.file_logs = self.db.file_logs  # New collection for file logs
        self.broadcast_logs = self.db.broadcast_logs

    # ==================== USER MANAGEMENT ====================
    
    async def add_user(self, user_id: int, username: str = None, first_name: str = None):
        """Add new user to database (upsert) with enhanced logging."""
        try:
            user_data = {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "join_date": datetime.utcnow(),
                "is_banned": False,
                "merge_count": 0,
                "last_used": datetime.utcnow(),
                "total_uploads": 0,
                "total_file_size": 0
            }
            
            # Check if user already exists
            existing_user = await self.users.find_one({"user_id": user_id})
            if existing_user:
                # Update existing user info
                await self.users.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "username": username,
                            "first_name": first_name,
                            "last_used": datetime.utcnow()
                        }
                    }
                )
                return False  # User already existed
            else:
                # Insert new user
                await self.users.insert_one(user_data)
                logger.info(f"New user added: {user_id} - {first_name}")
                return True  # New user added
                
        except Exception as e:
            logger.error(f"Error add_user({user_id}): {e}")
            return False

    async def get_user(self, user_id: int):
        """Fetch user record."""
        try:
            return await self.users.find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"Error get_user({user_id}): {e}")
            return None

    async def update_user_activity(self, user_id: int):
        """Update last_used timestamp."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_used": datetime.utcnow()}}
            )
        except Exception as e:
            logger.error(f"Error update_user_activity({user_id}): {e}")

    async def increment_merge_count(self, user_id: int):
        """Increment merge_count."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$inc": {"merge_count": 1}}
            )
        except Exception as e:
            logger.error(f"Error increment_merge_count({user_id}): {e}")

    async def update_user_stats(self, user_id: int, file_size: int = 0):
        """Update user upload statistics."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {
                    "$inc": {
                        "total_uploads": 1,
                        "total_file_size": file_size
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error update_user_stats({user_id}): {e}")

    # ==================== BAN MANAGEMENT ====================
    
    async def ban_user(self, user_id: int, banned: bool = True):
        """Ban or unban a user."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_banned": banned, "ban_date": datetime.utcnow() if banned else None}}
            )
            return True
        except Exception as e:
            logger.error(f"Error ban_user({user_id}, {banned}): {e}")
            return False

    async def is_user_banned(self, user_id: int) -> bool:
        """Check ban status."""
        try:
            user = await self.users.find_one({"user_id": user_id})
            return user.get("is_banned", False) if user else False
        except Exception as e:
            logger.error(f"Error is_user_banned({user_id}): {e}")
            return False

    # ==================== USER STATISTICS ====================
    
    async def get_total_users(self) -> int:
        """Return total user count."""
        try:
            return await self.users.count_documents({})
        except Exception as e:
            logger.error(f"Error get_total_users: {e}")
            return 0

    async def get_all_users(self) -> list[int]:
        """Return list of all user_ids."""
        try:
            cursor = self.users.find({}, {"user_id": 1})
            return [doc["user_id"] async for doc in cursor]
        except Exception as e:
            logger.error(f"Error get_all_users: {e}")
            return []

    # ==================== AUTHORIZED CHATS ====================
    
    async def add_authorized_chat(self, chat_id: int, chat_title: str = None):
        """Add or upsert authorized group/chat."""
        try:
            data = {
                "chat_id": chat_id,
                "chat_title": chat_title,
                "added_date": datetime.utcnow(),
                "is_active": True
            }
            await self.authorized_chats.update_one(
                {"chat_id": chat_id},
                {"$setOnInsert": data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error add_authorized_chat({chat_id}): {e}")
            return False

    async def remove_authorized_chat(self, chat_id: int) -> bool:
        """Deactivate or delete authorized chat."""
        try:
            result = await self.authorized_chats.delete_one({"chat_id": chat_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error remove_authorized_chat({chat_id}): {e}")
            return False

    async def is_authorized_chat(self, chat_id: int) -> bool:
        """Check if chat is in authorized list."""
        try:
            doc = await self.authorized_chats.find_one({"chat_id": chat_id})
            return bool(doc and doc.get("is_active", False))
        except Exception as e:
            logger.error(f"Error is_authorized_chat({chat_id}): {e}")
            return False

    # ==================== MERGE LOGGING ====================
    
    async def log_merge(self, user_id: int, file_count: int, file_size: int, merge_time: float, output_filename: str = None):
        """Record merge activity with enhanced details."""
        try:
            merge_data = {
                "user_id": user_id,
                "file_count": file_count,
                "file_size": file_size,
                "merge_time": merge_time,
                "output_filename": output_filename,
                "timestamp": datetime.utcnow(),
                "success": True
            }
            await self.merge_logs.insert_one(merge_data)
            
            # Update user merge count
            await self.increment_merge_count(user_id)
            
            return True
        except Exception as e:
            logger.error(f"Error log_merge: {e}")
            return False

    async def log_merge_error(self, user_id: int, error_message: str, file_count: int = 0):
        """Log failed merge attempts."""
        try:
            error_data = {
                "user_id": user_id,
                "file_count": file_count,
                "error_message": error_message,
                "timestamp": datetime.utcnow(),
                "success": False
            }
            await self.merge_logs.insert_one(error_data)
            return True
        except Exception as e:
            logger.error(f"Error log_merge_error: {e}")
            return False

    # ==================== FILE LOGGING (NEW) ====================
    
    async def log_file_activity(self, user_id: int, file_name: str, file_size: int, upload_type: str, file_url: str = None):
        """Log file upload/merge activities for FLOG channel."""
        try:
            file_data = {
                "user_id": user_id,
                "file_name": file_name,
                "file_size": file_size,
                "upload_type": upload_type,  # "merge", "upload", "download"
                "file_url": file_url,
                "timestamp": datetime.utcnow()
            }
            await self.file_logs.insert_one(file_data)
            
            # Update user stats
            await self.update_user_stats(user_id, file_size)
            
            return True
        except Exception as e:
            logger.error(f"Error log_file_activity: {e}")
            return False

    async def get_recent_file_logs(self, limit: int = 50) -> list[dict]:
        """Get recent file activities."""
        try:
            cursor = self.file_logs.find().sort("timestamp", -1).limit(limit)
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error(f"Error get_recent_file_logs: {e}")
            return []

    # ==================== USER STATISTICS ====================
    
    async def get_user_stats(self, user_id: int) -> dict | None:
        """Return enhanced user stats."""
        try:
            user = await self.users.find_one({"user_id": user_id})
            if not user:
                return None
            return {
                "merge_count": user.get("merge_count", 0),
                "total_uploads": user.get("total_uploads", 0),
                "total_file_size": user.get("total_file_size", 0),
                "join_date": user.get("join_date"),
                "last_used": user.get("last_used"),
                "username": user.get("username"),
                "first_name": user.get("first_name")
            }
        except Exception as e:
            logger.error(f"Error get_user_stats({user_id}): {e}")
            return None

    async def get_bot_stats(self) -> dict:
        """Return enhanced bot stats."""
        try:
            total_users = await self.users.count_documents({})
            total_merges = await self.merge_logs.count_documents({"success": True})
            total_files = await self.file_logs.count_documents({})
            today_cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_merges = await self.merge_logs.count_documents({
                "timestamp": {"$gte": today_cutoff},
                "success": True
            })
            today_files = await self.file_logs.count_documents({
                "timestamp": {"$gte": today_cutoff}
            })
            
            return {
                "total_users": total_users,
                "total_merges": total_merges,
                "total_files": total_files,
                "today_merges": today_merges,
                "today_files": today_files
            }
        except Exception as e:
            logger.error(f"Error get_bot_stats: {e}")
            return {
                "total_users": 0, "total_merges": 0, "total_files": 0,
                "today_merges": 0, "today_files": 0
            }

    # ==================== BROADCAST LOGGING ====================
    
    async def log_broadcast(self, message_id: str, success: int, failed: int, total: int):
        """Record broadcast summary."""
        try:
            await self.broadcast_logs.insert_one({
                "message_id": message_id,
                "success": success,
                "failed": failed,
                "total": total,
                "timestamp": datetime.utcnow()
            })
            return True
        except Exception as e:
            logger.error(f"Error log_broadcast: {e}")
            return False

    async def get_broadcast_logs(self) -> list[dict]:
        """Fetch recent broadcast logs."""
        try:
            cursor = self.broadcast_logs.find().sort("timestamp", -1).limit(10)
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error(f"Error get_broadcast_logs: {e}")
            return []

# Global instance
db = Database()
