# database.py - FIXED VERSION with Bulletproof MongoDB Integration

import motor.motor_asyncio
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional
from config import config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.users = None
        self.settings = None
        self.logs = None
        self.stats = None
        self.merges = None
        self.connected = False

    async def connect(self):
        """Connect to MongoDB with proper error handling"""
        try:
            # Check if MongoDB URI is provided
            if not config.MONGO_URI:
                logger.warning("MongoDB URI not provided. Database features will be disabled.")
                self.connected = False
                return False

            self.client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_URI)
            self.db = self.client[config.DB_NAME]

            # Collections
            self.users = self.db.users
            self.settings = self.db.settings
            self.logs = self.db.logs
            self.stats = self.db.stats
            self.merges = self.db.merges

            # Test connection
            await self.client.admin.command('ping')

            # Create indexes for better performance
            await self.users.create_index("user_id", unique=True)
            await self.logs.create_index("timestamp")
            await self.stats.create_index("date")
            await self.merges.create_index([("user_id", 1), ("timestamp", -1)])

            self.connected = True
            logger.info("✅ Connected to MongoDB successfully!")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            self.connected = False
            return False

    async def add_user(self, user_id: int, name: str, username: str = None):
        """Add new user to database with fallback"""
        if not self.connected:
            return False

        try:
            user_doc = {
                "user_id": user_id,
                "name": name,
                "username": username,
                "join_date": datetime.now(),
                "is_banned": False,
                "merge_count": 0,
                "last_activity": datetime.now(),
                "is_authorized": user_id in config.AUTHORIZED_USERS or user_id == config.OWNER_ID or user_id in config.ADMINS
            }

            result = await self.users.update_one(
                {"user_id": user_id},
                {"$setOnInsert": user_doc},
                upsert=True
            )

            # Update last activity for existing users
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_activity": datetime.now()}}
            )

            return result.upserted_id is not None

        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            return False

    async def update_user_activity(self, user_id: int) -> bool:
        """Update the user's last_activity timestamp"""
        if not self.connected:
            return False
        try:
            result = await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_activity": datetime.now()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating user activity for {user_id}: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information with fallback"""
        if not self.connected:
            return None

        try:
            return await self.users.find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    async def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned with fallback"""
        if not self.connected:
            return False

        try:
            user = await self.users.find_one({"user_id": user_id})
            return user.get("is_banned", False) if user else False
        except Exception as e:
            logger.error(f"Error checking ban status for {user_id}: {e}")
            return False

    async def is_user_authorized(self, user_id: int) -> bool:
        """Check if user is authorized with fallback"""
        try:
            # Check if user is owner, admin, or in authorized list
            if user_id == config.OWNER_ID or user_id in config.ADMINS or user_id in config.AUTHORIZED_USERS:
                return True

            if not self.connected:
                return False

            user = await self.users.find_one({"user_id": user_id})
            return user.get("is_authorized", False) if user else False

        except Exception as e:
            logger.error(f"Error checking authorization for {user_id}: {e}")
            return False

    async def ban_user(self, user_id: int, ban_status: bool) -> bool:
        """Ban or unban user with fallback"""
        if not self.connected:
            return False

        try:
            result = await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_banned": ban_status}}
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"Error updating ban status for {user_id}: {e}")
            return False

    async def authorize_user(self, user_id: int, auth_status: bool) -> bool:
        """Authorize or unauthorize user with fallback"""
        if not self.connected:
            return False

        try:
            result = await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_authorized": auth_status}}
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"Error updating authorization for {user_id}: {e}")
            return False

    async def increment_merge_count(self, user_id: int):
        """Increment user's merge count with fallback"""
        if not self.connected:
            return

        try:
            await self.users.update_one(
                {"user_id": user_id},
                {
                    "$inc": {"merge_count": 1},
                    "$set": {"last_activity": datetime.now()}
                }
            )

            # Update daily stats
            today = datetime.now().date()
            await self.stats.update_one(
                {"date": today},
                {
                    "$inc": {"merges": 1},
                    "$setOnInsert": {"date": today}
                },
                upsert=True
            )

        except Exception as e:
            logger.error(f"Error incrementing merge count for {user_id}: {e}")

    async def log_merge(self, user_id: int, user_name: str, video_count: int, file_size: int, merge_time: float):
        """Log merge activity with fallback"""
        if not self.connected:
            return

        try:
            merge_doc = {
                "user_id": user_id,
                "user_name": user_name,
                "video_count": video_count,
                "file_size": file_size,
                "merge_time": merge_time,
                "timestamp": datetime.now()
            }

            await self.merges.insert_one(merge_doc)

        except Exception as e:
            logger.error(f"Error logging merge for {user_id}: {e}")

    async def get_all_users(self) -> List[int]:
        """Get all user IDs (excluding banned) with fallback"""
        if not self.connected:
            return []

        try:
            cursor = self.users.find({"is_banned": {"$ne": True}}, {"user_id": 1})
            users = await cursor.to_list(length=None)
            return [user["user_id"] for user in users]

        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

    async def get_bot_stats(self) -> Dict:
        """Get comprehensive bot statistics with fallback"""
        if not self.connected:
            return {
                "total_users": 0,
                "banned_users": 0,
                "authorized_users": 0,
                "total_merges": 0,
                "today_merges": 0,
                "active_users_24h": 0,
                "bot_start_date": "Database not connected"
            }

        try:
            # Total users
            total_users = await self.users.count_documents({})

            # Banned users
            banned_users = await self.users.count_documents({"is_banned": True})

            # Authorized users
            authorized_users = await self.users.count_documents({"is_authorized": True})

            # Total merges
            total_merges_pipeline = [
                {"$group": {"_id": None, "total": {"$sum": "$merge_count"}}}
            ]
            total_merges_result = await self.users.aggregate(total_merges_pipeline).to_list(length=1)
            total_merges = total_merges_result[0]["total"] if total_merges_result else 0

            # Today's merges
            today = datetime.now().date()
            today_stats = await self.stats.find_one({"date": today})
            today_merges = today_stats.get("merges", 0) if today_stats else 0

            # Active users in last 24 hours
            yesterday = datetime.now() - timedelta(days=1)
            active_users_24h = await self.users.count_documents({
                "last_activity": {"$gte": yesterday}
            })

            # Bot start date
            first_user = await self.users.find_one({}, sort=[("join_date", 1)])
            bot_start_date = first_user["join_date"].strftime("%Y-%m-%d") if first_user else "Unknown"

            return {
                "total_users": total_users,
                "banned_users": banned_users,
                "authorized_users": authorized_users,
                "total_merges": total_merges,
                "today_merges": today_merges,
                "active_users_24h": active_users_24h,
                "bot_start_date": bot_start_date
            }

        except Exception as e:
            logger.error(f"Error getting bot stats: {e}")
            return {}

    async def log_broadcast(self, message_id: str, success: int, failed: int, total: int):
        """Log broadcast activity with fallback"""
        if not self.connected:
            return

        try:
            log_doc = {
                "type": "broadcast",
                "message_id": message_id,
                "success": success,
                "failed": failed,
                "total": total,
                "timestamp": datetime.now()
            }

            await self.logs.insert_one(log_doc)

        except Exception as e:
            logger.error(f"Error logging broadcast: {e}")

# Initialize database instance
db = Database()
