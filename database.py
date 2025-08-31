# database.py - MongoDB Database Management
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
        self.broadcast_logs = self.db.broadcast_logs
    
    async def add_user(self, user_id: int, username: str = None, first_name: str = None):
        """Add new user to database"""
        try:
            user_data = {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "join_date": datetime.now(),
                "is_banned": False,
                "merge_count": 0,
                "last_used": datetime.now()
            }
            
            # Use upsert to avoid duplicates
            await self.users.update_one(
                {"user_id": user_id},
                {"$setOnInsert": user_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            return False
    
    async def get_user(self, user_id: int):
        """Get user data from database"""
        try:
            return await self.users.find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    async def update_user_activity(self, user_id: int):
        """Update user's last activity"""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_used": datetime.now()}}
            )
        except Exception as e:
            logger.error(f"Error updating user activity {user_id}: {e}")
    
    async def increment_merge_count(self, user_id: int):
        """Increment user's merge count"""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$inc": {"merge_count": 1}}
            )
        except Exception as e:
            logger.error(f"Error incrementing merge count for {user_id}: {e}")
    
    async def ban_user(self, user_id: int, banned: bool = True):
        """Ban or unban a user"""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_banned": banned}}
            )
            return True
        except Exception as e:
            logger.error(f"Error {'banning' if banned else 'unbanning'} user {user_id}: {e}")
            return False
    
    async def is_user_banned(self, user_id: int):
        """Check if user is banned"""
        try:
            user = await self.users.find_one({"user_id": user_id})
            return user.get("is_banned", False) if user else False
        except Exception as e:
            logger.error(f"Error checking ban status for {user_id}: {e}")
            return False
    
    async def get_total_users(self):
        """Get total user count"""
        try:
            return await self.users.count_documents({})
        except Exception as e:
            logger.error(f"Error getting total users: {e}")
            return 0
    
    async def get_all_users(self):
        """Get all user IDs for broadcast"""
        try:
            cursor = self.users.find({}, {"user_id": 1})
            return [user["user_id"] async for user in cursor]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    async def add_authorized_chat(self, chat_id: int, chat_title: str = None):
        """Add authorized chat/group"""
        try:
            chat_data = {
                "chat_id": chat_id,
                "chat_title": chat_title,
                "added_date": datetime.now(),
                "is_active": True
            }
            
            await self.authorized_chats.update_one(
                {"chat_id": chat_id},
                {"$setOnInsert": chat_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding authorized chat {chat_id}: {e}")
            return False
    
    async def remove_authorized_chat(self, chat_id: int):
        """Remove authorized chat/group"""
        try:
            result = await self.authorized_chats.delete_one({"chat_id": chat_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error removing authorized chat {chat_id}: {e}")
            return False
    
    async def is_authorized_chat(self, chat_id: int):
        """Check if chat is authorized"""
        try:
            chat = await self.authorized_chats.find_one({"chat_id": chat_id})
            return chat.get("is_active", False) if chat else False
        except Exception as e:
            logger.error(f"Error checking authorization for chat {chat_id}: {e}")
            return False
    
    async def get_authorized_chats(self):
        """Get all authorized chats"""
        try:
            cursor = self.authorized_chats.find({"is_active": True})
            return [chat async for chat in cursor]
        except Exception as e:
            logger.error(f"Error getting authorized chats: {e}")
            return []
    
    async def log_merge(self, user_id: int, file_count: int, file_size: int, merge_time: float):
        """Log merge activity"""
        try:
            log_data = {
                "user_id": user_id,
                "file_count": file_count,
                "file_size": file_size,
                "merge_time": merge_time,
                "timestamp": datetime.now()
            }
            
            await self.merge_logs.insert_one(log_data)
            return True
        except Exception as e:
            logger.error(f"Error logging merge: {e}")
            return False
    
    async def get_user_stats(self, user_id: int):
        """Get user statistics"""
        try:
            user = await self.users.find_one({"user_id": user_id})
            if not user:
                return None
            
            merge_count = user.get("merge_count", 0)
            join_date = user.get("join_date", datetime.now())
            last_used = user.get("last_used", datetime.now())
            
            return {
                "merge_count": merge_count,
                "join_date": join_date,
                "last_used": last_used,
                "username": user.get("username"),
                "first_name": user.get("first_name")
            }
        except Exception as e:
            logger.error(f"Error getting user stats for {user_id}: {e}")
            return None
    
    async def get_bot_stats(self):
        """Get overall bot statistics"""
        try:
            total_users = await self.users.count_documents({})
            total_merges = await self.merge_logs.count_documents({})
            today_merges = await self.merge_logs.count_documents({
                "timestamp": {
                    "$gte": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                }
            })
            
            return {
                "total_users": total_users,
                "total_merges": total_merges,
                "today_merges": today_merges
            }
        except Exception as e:
            logger.error(f"Error getting bot stats: {e}")
            return None

# Global database instance
db = Database()
