# health_checker.py - COMPREHENSIVE SYSTEM HEALTH MONITORING
import asyncio
import aiohttp
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from config import config
from database import db
from logging_system import get_logger
import psutil
import os

logger = get_logger('system')

@dataclass
class HealthStatus:
    """Health status data class"""
    component: str
    status: str  # healthy, degraded, unhealthy, unknown
    response_time: Optional[float]
    last_check: datetime
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class ComponentHealthChecker:
    """Base class for component health checkers"""
    
    def __init__(self, name: str, check_interval: int = 300):
        self.name = name
        self.check_interval = check_interval
        self.last_status = None
        self.check_count = 0
        self.error_count = 0
        
    async def check_health(self) -> HealthStatus:
        """Override this method in subclasses"""
        raise NotImplementedError
    
    async def run_check(self) -> HealthStatus:
        """Run health check with error handling"""
        self.check_count += 1
        start_time = time.time()
        
        try:
            status = await self.check_health()
            status.response_time = time.time() - start_time
            status.last_check = datetime.now()
            
            if status.status in ['unhealthy', 'degraded']:
                self.error_count += 1
            
            self.last_status = status
            return status
            
        except Exception as e:
            self.error_count += 1
            error_status = HealthStatus(
                component=self.name,
                status='unhealthy',
                response_time=time.time() - start_time,
                last_check=datetime.now(),
                error=str(e)
            )
            self.last_status = error_status
            logger.error(f"Health check failed for {self.name}: {e}")
            return error_status

class DatabaseHealthChecker(ComponentHealthChecker):
    """Database health checker"""
    
    def __init__(self):
        super().__init__('database', 180)  # Check every 3 minutes
    
    async def check_health(self) -> HealthStatus:
        if not config.MONGO_URI:
            return HealthStatus(
                component='database',
                status='disabled',
                response_time=0,
                last_check=datetime.now(),
                details={'reason': 'No MongoDB URI configured'}
            )
        
        if not db.connected:
            return HealthStatus(
                component='database',
                status='unhealthy',
                response_time=0,
                last_check=datetime.now(),
                error='Database not connected'
            )
        
        # Perform database health check
        health_data = await db.health_check()
        
        if health_data['status'] == 'healthy':
            status = 'healthy'
        elif health_data.get('response_time', 0) > 5.0:
            status = 'degraded'
        else:
            status = 'unhealthy'
        
        return HealthStatus(
            component='database',
            status=status,
            response_time=health_data.get('response_time', 0),
            last_check=datetime.now(),
            error=health_data.get('error'),
            details={
                'database_size': health_data.get('database_size', 0),
                'collections': health_data.get('collections_count', 0),
                'indexes': health_data.get('indexes_count', 0)
            }
        )

class TelegramAPIHealthChecker(ComponentHealthChecker):
    """Telegram API health checker"""
    
    def __init__(self, client):
        super().__init__('telegram_api', 300)  # Check every 5 minutes
        self.client = client
    
    async def check_health(self) -> HealthStatus:
        try:
            # Test basic API call
            start_time = time.time()
            await self.client.get_me()
            response_time = time.time() - start_time
            
            status = 'healthy' if response_time < 2.0 else 'degraded'
            
            return HealthStatus(
                component='telegram_api',
                status=status,
                response_time=response_time,
                last_check=datetime.now(),
                details={'api_response_time': response_time}
            )
            
        except Exception as e:
            return HealthStatus(
                component='telegram_api',
                status='unhealthy',
                response_time=0,
                last_check=datetime.now(),
                error=str(e)
            )

class ChannelHealthChecker(ComponentHealthChecker):
    """Channel access health checker"""
    
    def __init__(self, client):
        super().__init__('channels', 600)  # Check every 10 minutes
        self.client = client
    
    async def check_health(self) -> HealthStatus:
        channels_to_check = [
            ('force_sub', config.FORCE_SUB_CHANNEL),
            ('log', config.LOG_CHANNEL),
            ('new_user_log', config.NEW_USER_LOG_CHANNEL),
            ('merged_file_log', config.MERGED_FILE_LOG_CHANNEL)
        ]
        
        channel_status = {}
        overall_status = 'healthy'
        errors = []
        
        for channel_name, channel_id in channels_to_check:
            if not channel_id:
                channel_status[channel_name] = 'not_configured'
                continue
            
            try:
                chat = await self.client.get_chat(channel_id)
                channel_status[channel_name] = 'accessible'
                
            except Exception as e:
                channel_status[channel_name] = 'inaccessible'
                errors.append(f"{channel_name}: {str(e)}")
                if channel_name in ['force_sub', 'log']:  # Critical channels
                    overall_status = 'degraded'
        
        if len(errors) > len(channels_to_check) // 2:
            overall_status = 'unhealthy'
        
        return HealthStatus(
            component='channels',
            status=overall_status,
            response_time=None,
            last_check=datetime.now(),
            error='; '.join(errors) if errors else None,
            details=channel_status
        )

class SystemResourceHealthChecker(ComponentHealthChecker):
    """System resource health checker"""
    
    def __init__(self):
        super().__init__('system_resources', 120)  # Check every 2 minutes
    
    async def check_health(self) -> HealthStatus:
        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Get download directory size
            download_dir_size = 0
            if os.path.exists(config.DOWNLOAD_DIR):
                try:
                    for dirpath, dirnames, filenames in os.walk(config.DOWNLOAD_DIR):
                        for filename in filenames:
                            filepath = os.path.join(dirpath, filename)
                            download_dir_size += os.path.getsize(filepath)
                except OSError:
                    pass
            
            # Determine status
            status = 'healthy'
            warnings = []
            
            if cpu_percent > 90:
                status = 'degraded'
                warnings.append(f"High CPU usage: {cpu_percent}%")
            
            if memory.percent > 85:
                status = 'degraded'
                warnings.append(f"High memory usage: {memory.percent}%")
            
            if disk.percent > 90:
                status = 'unhealthy'
                warnings.append(f"Low disk space: {disk.percent}% used")
            
            if download_dir_size > 5 * 1024 * 1024 * 1024:  # 5GB
                status = 'degraded'
                warnings.append(f"Large download directory: {download_dir_size / (1024**3):.1f}GB")
            
            return HealthStatus(
                component='system_resources',
                status=status,
                response_time=None,
                last_check=datetime.now(),
                error=' | '.join(warnings) if warnings else None,
                details={
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_used_gb': memory.used / (1024**3),
                    'memory_total_gb': memory.total / (1024**3),
                    'disk_percent': disk.percent,
                    'disk_free_gb': disk.free / (1024**3),
                    'download_dir_size_gb': download_dir_size / (1024**3)
                }
            )
            
        except Exception as e:
            return HealthStatus(
                component='system_resources',
                status='unhealthy',
                response_time=None,
                last_check=datetime.now(),
                error=str(e)
            )

class ExternalServiceHealthChecker(ComponentHealthChecker):
    """External services health checker"""
    
    def __init__(self):
        super().__init__('external_services', 600)  # Check every 10 minutes
    
    async def check_health(self) -> HealthStatus:
        services = {
            'gofile': 'https://api.gofile.io/servers',
            'telegram_api': 'https://api.telegram.org',
        }
        
        service_status = {}
        overall_status = 'healthy'
        errors = []
        
        async with aiohttp.ClientSession() as session:
            for service_name, url in services.items():
                try:
                    start_time = time.time()
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        response_time = time.time() - start_time
                        
                        if response.status == 200:
                            service_status[service_name] = {
                                'status': 'healthy',
                                'response_time': response_time
                            }
                        else:
                            service_status[service_name] = {
                                'status': 'degraded',
                                'response_time': response_time,
                                'http_status': response.status
                            }
                            overall_status = 'degraded'
                            
                except Exception as e:
                    service_status[service_name] = {
                        'status': 'unhealthy',
                        'error': str(e)
                    }
                    errors.append(f"{service_name}: {str(e)}")
                    overall_status = 'degraded'
        
        if len(errors) >= len(services):
            overall_status = 'unhealthy'
        
        return HealthStatus(
            component='external_services',
            status=overall_status,
            response_time=None,
            last_check=datetime.now(),
            error=' | '.join(errors) if errors else None,
            details=service_status
        )

class AdvancedHealthMonitor:
    """Advanced health monitoring system"""
    
    def __init__(self, client=None):
        self.client = client
        self.checkers: List[ComponentHealthChecker] = []
        self.health_history: Dict[str, List[HealthStatus]] = {}
        self.alerts_sent: Dict[str, datetime] = {}
        self.alert_cooldown = timedelta(minutes=15)  # Don't spam alerts
        self.running = False
        
        self._initialize_checkers()
    
    def _initialize_checkers(self):
        """Initialize all health checkers"""
        self.checkers = [
            DatabaseHealthChecker(),
            SystemResourceHealthChecker(),
            ExternalServiceHealthChecker()
        ]
        
        if self.client:
            self.checkers.extend([
                TelegramAPIHealthChecker(self.client),
                ChannelHealthChecker(self.client)
            ])
    
    def add_custom_checker(self, checker: ComponentHealthChecker):
        """Add a custom health checker"""
        self.checkers.append(checker)
        logger.info(f"Added custom health checker: {checker.name}")
    
    async def check_all_components(self) -> Dict[str, HealthStatus]:
        """Check health of all components"""
        results = {}
        
        for checker in self.checkers:
            try:
                status = await checker.run_check()
                results[checker.name] = status
                
                # Store in history
                if checker.name not in self.health_history:
                    self.health_history[checker.name] = []
                
                self.health_history[checker.name].append(status)
                
                # Keep only recent history (last 100 checks)
                if len(self.health_history[checker.name]) > 100:
                    self.health_history[checker.name] = self.health_history[checker.name][-50:]
                
                # Check if alert needed
                await self._check_alert_conditions(checker.name, status)
                
            except Exception as e:
                logger.error(f"Error checking {checker.name}: {e}")
                
        return results
    
    async def _check_alert_conditions(self, component: str, status: HealthStatus):
        """Check if alerts should be sent"""
        if status.status in ['unhealthy', 'degraded']:
            last_alert = self.alerts_sent.get(component)
            
            if not last_alert or datetime.now() - last_alert > self.alert_cooldown:
                await self._send_alert(component, status)
                self.alerts_sent[component] = datetime.now()
    
    async def _send_alert(self, component: str, status: HealthStatus):
        """Send health alert"""
        alert_message = f"""🚨 **HEALTH ALERT**

**Component:** {component}
**Status:** {status.status.upper()} 
**Time:** {status.last_check.strftime('%Y-%m-%d %H:%M:%S')}
**Error:** {status.error or 'N/A'}

Please check the system immediately!"""
        
        logger.error(f"HEALTH ALERT: {component} is {status.status}")
        
        # Try to send to log channel if available
        if self.client and config.LOG_CHANNEL:
            try:
                await self.client.send_message(config.LOG_CHANNEL, alert_message)
            except Exception as e:
                logger.error(f"Failed to send health alert to channel: {e}")
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary"""
        last_results = {}
        overall_status = 'healthy'
        component_count = {'healthy': 0, 'degraded': 0, 'unhealthy': 0, 'disabled': 0}
        
        for checker in self.checkers:
            if checker.last_status:
                last_results[checker.name] = asdict(checker.last_status)
                status = checker.last_status.status
                component_count[status] = component_count.get(status, 0) + 1
                
                if status == 'unhealthy':
                    overall_status = 'unhealthy'
                elif status == 'degraded' and overall_status == 'healthy':
                    overall_status = 'degraded'
        
        return {
            'overall_status': overall_status,
            'components': last_results,
            'component_summary': component_count,
            'total_components': len(self.checkers),
            'last_check': datetime.now().isoformat(),
            'uptime': self._calculate_uptime()
        }
    
    def _calculate_uptime(self) -> Dict[str, Any]:
        """Calculate system uptime metrics"""
        # This is a simple implementation - you might want to track actual start time
        import time
        uptime_seconds = time.time() - os.path.getctime(__file__)
        
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        return {
            'seconds': uptime_seconds,
            'formatted': f"{days}d {hours}h {minutes}m"
        }
    
    async def start_monitoring(self):
        """Start continuous health monitoring"""
        self.running = True
        logger.info("🏥 Starting advanced health monitoring system...")
        
        while self.running:
            try:
                await self.check_all_components()
                
                # Wait for the shortest check interval
                min_interval = min(checker.check_interval for checker in self.checkers)
                await asyncio.sleep(min_interval)
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    def stop_monitoring(self):
        """Stop health monitoring"""
        self.running = False
        logger.info("🛑 Stopping health monitoring system...")

# Global health monitor instance
health_monitor = AdvancedHealthMonitor()

async def initialize_health_monitor(client):
    """Initialize health monitor with client"""
    global health_monitor
    health_monitor = AdvancedHealthMonitor(client)
    return health_monitor

def get_health_monitor():
    """Get health monitor instance"""
    return health_monitor
