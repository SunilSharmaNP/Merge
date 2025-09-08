# database.py - ENHANCED VERSION with Advanced Health Monitoring
import motor.motor_asyncio
from datetime import datetime, timedelta
import logging
import asyncio
from typing import List, Dict, Optional, Any
from config import config
import traceback

logger = logging.getLogger(__name__)

class AdvancedDatabase:
    """Enhanced database class with health monitoring and advanced features"""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.collections = {}
        self.connected = False
        self.last_health_check = None
        self.connection_attempts = 0
        self.max_connection_attempts = 5
        self.health_status = {
            "status": "disconnected",
            "last_check": None,
            "error": None,
            "connection_attempts": 0,
            "uptime": None
        }
    
    async def connect(self) -> bool:
        """Enhanced connection with retry logic and health monitoring"""
        if not config.MONGO_URI:
            logger.warning("📡 MongoDB URI not provided. Running without database.")
            self.connected = False
            self.health_status.update({
                "status": "disabled",
                "error": "No MongoDB URI provided",
                "last_check": datetime.now()
            })
            return False
        
        self.connection_attempts += 1
        logger.info(f"🔌 Connecting to MongoDB... (Attempt {self.connection_attempts}/{self.max_connection_attempts})")
        
        try:
            # Create client with advanced options
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                config.MONGO_URI,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000,
                maxPoolSize=10,
                retryWrites=True
            )
            
            self.db = self.client[config.DB_NAME]
            
            # Initialize collections
            self.collections = {
                'users': self.db.users,
                'settings': self.db.settings,
                'logs': self.db.logs,
                'stats': self.db.stats,
                'merges': self.db.merges,
                'health': self.db.health,
                'broadcasts': self.db.broadcasts
            }
            
            # Test connection
            await self.client.admin.command('ping')
            
            # Create indexes for better performance
            await self._create_indexes()
            
            self.connected = True
            self.connection_attempts = 0
            connect_time = datetime.now()
            
            self.health_status.update({
                "status": "connected",
                "last_check": connect_time,
                "error": None,
                "connection_attempts": self.connection_attempts,
                "uptime": connect_time
            })
            
            logger.info("✅ Successfully connected to MongoDB!")
            await self._log_system_event("database_connected", {"connection_time": connect_time})
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to connect to MongoDB: {str(e)}"
            logger.error(f"❌ {error_msg}")
            
            self.connected = False
            self.health_status.update({
                "status": "error",
                "last_check": datetime.now(),
                "error": error_msg,
                "connection_attempts": self.connection_attempts
            })
            
            if self.connection_attempts < self.max_connection_attempts:
                await asyncio.sleep(5)  # Wait before retry
                return await self.connect()
            else:
                logger.error(f"🚫 Max connection attempts reached. Database will be disabled.")
                return False
    
    async def _create_indexes(self):
        """Create database indexes for optimal performance"""
        try:
            # Users collection indexes
            await self.collections['users'].create_index("user_id", unique=True)
            await self.collections['users'].create_index("username")
            await self.collections['users'].create_index("is_banned")
            await self.collections['users'].create_index("last_activity")
            
            # Logs collection indexes
            await self.collections['logs'].create_index("timestamp")
            await self.collections['logs'].create_index("log_type")
            await self.collections['logs'].create_index("user_id")
            
            # Stats collection indexes
            await self.collections['stats'].create_index("date", unique=True)
            
            # Merges collection indexes
            await self.collections['merges'].create_index([("user_id", 1), ("timestamp", -1)])
            await self.collections['merges'].create_index("timestamp")
            
            # Health collection indexes
            await self.collections['health'].create_index("timestamp")
            await self.collections['health'].create_index("component")
            
            # Broadcasts collection indexes
            await self.collections['broadcasts'].create_index("timestamp")
            await self.collections['broadcasts'].create_index("status")
            
            logger.info("📊 Database indexes created successfully!")
            
        except Exception as e:
            logger.error(f"⚠️ Error creating indexes: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive database health check"""
        if not self.connected:
            return self.health_status
        
        try:
            start_time = datetime.now()
            
            # Test basic connection
            await self.client.admin.command('ping')
            
            # Test read/write operations
            test_doc = {"test": True, "timestamp": start_time}
            result = await self.collections['health'].insert_one(test_doc)
            await self.collections['health'].delete_one({"_id": result.inserted_id})
            
            # Get database stats
            db_stats = await self.db.command("dbStats")
            
            response_time = (datetime.now() - start_time).total_seconds()
            
            health_data = {
                "status": "healthy",
                "last_check": datetime.now(),
                "response_time": response_time,
                "database_size": db_stats.get("dataSize", 0),
                "collections_count": db_stats.get("collections", 0),
                "indexes_count": db_stats.get("indexes", 0),
                "uptime": self.health_status.get("uptime"),
                "error": None
            }
            
            self.health_status.update(health_data)
            self.last_health_check = datetime.now()
            
            return health_data
            
        except Exception as e:
            error_msg = f"Database health check failed: {str(e)}"
            logger.error(f"💔 {error_msg}")
            
            health_data = {
                "status": "unhealthy",
                "last_check": datetime.now(),
                "error": error_msg,
                "uptime": self.health_status.get("uptime")
            }
            
            self.health_status.update(health_data)
            self.connected = False
            
            return health_data
    
    async def _log_system_event(self, event_type: str, data: Dict[str, Any]):
        """Log system events for monitoring"""
        if not self.connected:
            return
        
        try:
            log_doc = {
                "event_type": event_type,
                "timestamp": datetime.now(),
                "data": data,
                "source": "database_system"
            }
            await self.collections['logs'].insert_one(log_doc)
        except Exception as e:
            logger.error(f"Failed to log system event: {e}")
    
    async def add_user(self, user_id: int, name: str, username: str = None) -> bool:
        """Enhanced user addition with comprehensive tracking"""
        if not self.connected:
            logger.debug(f"Database not connected - skipping user addition for {user_id}")
            return False
        
        try:
            current_time = datetime.now()
            user_doc = {
                "user_id": user_id,
                "name": name,
                "username": username,
                "join_date": current_time,
                "last_activity": current_time,
                "is_banned": False,
                "is_authorized": user_id in config.AUTHORIZED_USERS or user_id == config.OWNER_ID or user_id in config.ADMINS,
                "merge_count": 0,
                "total_file_size": 0,
                "settings": {
                    "notifications": True,
                    "preferred_format": "mp4",
                    "quality_preference": "high"
                },
                "stats": {
                    "videos_uploaded": 0,
                    "videos_merged": 0,
                    "total_duration_processed": 0
                }
            }
            
            result = await self.collections['users'].update_one(
                {"user_id": user_id},
                {
                    "$setOnInsert": user_doc,
                    "$set": {"last_activity": current_time}
                },
                upsert=True
            )
            
            if result.upserted_id:
                await self._log_system_event("user_added", {
                    "user_id": user_id,
                    "name": name,
                    "username": username
                })
                logger.info(f"➕ New user added to database: {name} ({user_id})")
                return True
            else:
                await self.update_user_activity(user_id)
                return False
                
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            return False
    
    async def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics with advanced metrics"""
        if not self.connected:
            return {
                "database_status": "disconnected",
                "total_users": 0,
                "total_merges": 0,
                "error": "Database not connected"
            }
        
        try:
            stats = {}
            
            # Basic counts
            stats["total_users"] = await self.collections['users'].count_documents({})
            stats["banned_users"] = await self.collections['users'].count_documents({"is_banned": True})
            stats["authorized_users"] = await self.collections['users'].count_documents({"is_authorized": True})
            
            # Activity stats
            yesterday = datetime.now() - timedelta(days=1)
            last_week = datetime.now() - timedelta(days=7)
            
            stats["active_users_24h"] = await self.collections['users'].count_documents({
                "last_activity": {"$gte": yesterday}
            })
            
            stats["active_users_week"] = await self.collections['users'].count_documents({
                "last_activity": {"$gte": last_week}
            })
            
            # Merge statistics
            merge_pipeline = [
                {"$group": {
                    "_id": None,
                    "total_merges": {"$sum": "$merge_count"},
                    "total_file_size": {"$sum": "$total_file_size"}
                }}
            ]
            
            merge_result = await self.collections['users'].aggregate(merge_pipeline).to_list(1)
            if merge_result:
                stats.update({
                    "total_merges": merge_result[0].get("total_merges", 0),
                    "total_file_size_processed": merge_result[0].get("total_file_size", 0)
                })
            else:
                stats.update({"total_merges": 0, "total_file_size_processed": 0})
            
            # Today's stats
            today = datetime.now().date()
            today_stats = await self.collections['stats'].find_one({"date": today})
            stats["today_merges"] = today_stats.get("merges", 0) if today_stats else 0
            stats["today_new_users"] = today_stats.get("new_users", 0) if today_stats else 0
            
            # Top users
            top_users_cursor = self.collections['users'].find(
                {"merge_count": {"$gt": 0}},
                {"user_id": 1, "name": 1, "merge_count": 1}
            ).sort("merge_count", -1).limit(5)
            
            stats["top_users"] = await top_users_cursor.to_list(5)
            
            # System health
            stats["database_health"] = await self.health_check()
            stats["database_status"] = "connected"
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting comprehensive stats: {e}")
            return {
                "database_status": "error",
                "error": str(e),
                "total_users": 0,
                "total_merges": 0
            }
    
    async def log_broadcast(self, broadcast_data: Dict[str, Any]) -> str:
        """Enhanced broadcast logging with tracking"""
        if not self.connected:
            return None
        
        try:
            broadcast_doc = {
                "timestamp": datetime.now(),
                "message_text": broadcast_data.get("message"),
                "target_users": broadcast_data.get("target_count", 0),
                "successful_sends": 0,
                "failed_sends": 0,
                "status": "started",
                "errors": [],
                "duration": None
            }
            
            result = await self.collections['broadcasts'].insert_one(broadcast_doc)
            broadcast_id = str(result.inserted_id)
            
            await self._log_system_event("broadcast_started", {
                "broadcast_id": broadcast_id,
                "target_count": broadcast_data.get("target_count", 0)
            })
            
            return broadcast_id
            
        except Exception as e:
            logger.error(f"Error logging broadcast: {e}")
            return None
    
    async def update_broadcast_progress(self, broadcast_id: str, success_count: int, failed_count: int, errors: List[str] = None):
        """Update broadcast progress"""
        if not self.connected or not broadcast_id:
            return
        
        try:
            from bson import ObjectId
            update_data = {
                "successful_sends": success_count,
                "failed_sends": failed_count,
                "status": "in_progress"
            }
            
            if errors:
                update_data["$push"] = {"errors": {"$each": errors}}
            
            await self.collections['broadcasts'].update_one(
                {"_id": ObjectId(broadcast_id)},
                {"$set": update_data}
            )
            
        except Exception as e:
            logger.error(f"Error updating broadcast progress: {e}")
    
    async def finalize_broadcast(self, broadcast_id: str, duration: float):
        """Finalize broadcast with completion data"""
        if not self.connected or not broadcast_id:
            return
        
        try:
            from bson import ObjectId
            await self.collections['broadcasts'].update_one(
                {"_id": ObjectId(broadcast_id)},
                {
                    "$set": {
                        "status": "completed",
                        "duration": duration,
                        "completed_at": datetime.now()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error finalizing broadcast: {e}")

# Initialize enhanced database
db = AdvancedDatabase()
