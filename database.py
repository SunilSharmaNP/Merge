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
        """Add new user to database (upsert)."""
        try:
            user_data = {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "join_date": datetime.utcnow(),
                "is_banned": False,
                "merge_count": 0,
                "last_used": datetime.utcnow()
            }
            await self.users.update_one(
                {"user_id": user_id},
                {"$setOnInsert": user_data},
                upsert=True
            )
            return True
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

    async def ban_user(self, user_id: int, banned: bool = True):
        """Ban or unban a user."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_banned": banned}}
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

    async def get_authorized_chats(self) -> list[dict]:
        """Fetch all active authorized chats."""
        try:
            cursor = self.authorized_chats.find({"is_active": True})
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error(f"Error get_authorized_chats: {e}")
            return []

    async def log_merge(self, user_id: int, file_count: int, file_size: int, merge_time: float):
        """Record merge activity."""
        try:
            await self.merge_logs.insert_one({
                "user_id": user_id,
                "file_count": file_count,
                "file_size": file_size,
                "merge_time": merge_time,
                "timestamp": datetime.utcnow()
            })
            return True
        except Exception as e:
            logger.error(f"Error log_merge: {e}")
            return False

    async def get_user_stats(self, user_id: int) -> dict | None:
        """Return basic user stats."""
        try:
            user = await self.users.find_one({"user_id": user_id})
            if not user:
                return None
            return {
                "merge_count": user.get("merge_count", 0),
                "join_date": user.get("join_date"),
                "last_used": user.get("last_used"),
                "username": user.get("username"),
                "first_name": user.get("first_name")
            }
        except Exception as e:
            logger.error(f"Error get_user_stats({user_id}): {e}")
            return None

    async def get_bot_stats(self) -> dict:
        """Return overall bot stats."""
        try:
            total_users = await self.users.count_documents({})
            total_merges = await self.merge_logs.count_documents({})
            today_cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_merges = await self.merge_logs.count_documents({"timestamp": {"$gte": today_cutoff}})
            return {
                "total_users": total_users,
                "total_merges": total_merges,
                "today_merges": today_merges
            }
        except Exception as e:
            logger.error(f"Error get_bot_stats: {e}")
            return {"total_users": 0, "total_merges": 0, "today_merges": 0}

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
