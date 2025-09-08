# logging_system.py - ADVANCED MULTI-LEVEL LOGGING SYSTEM
import logging
import logging.handlers
import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import traceback
from config import config

class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset_color = self.COLORS['RESET']
        
        # Add emoji indicators
        emoji_map = {
            'DEBUG': '🔍',
            'INFO': '📋',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🚨'
        }
        
        emoji = emoji_map.get(record.levelname, '📋')
        
        # Format the record
        formatted = super().format(record)
        return f"{log_color}{emoji} {formatted}{reset_color}"

class AdvancedLogger:
    """Advanced logging system with multiple outputs and real-time monitoring"""
    
    def __init__(self):
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        self.loggers = {}
        self.log_buffer = []
        self.max_buffer_size = 1000
        self.error_count = 0
        self.warning_count = 0
        
        self._setup_loggers()
        
    def _setup_loggers(self):
        """Setup different loggers for different components"""
        
        # Main bot logger
        self._create_logger(
            'bot',
            level=logging.INFO,
            console=True,
            file='bot.log',
            max_bytes=10*1024*1024,  # 10MB
            backup_count=5
        )
        
        # Error logger
        self._create_logger(
            'error',
            level=logging.ERROR,
            console=True,
            file='errors.log',
            max_bytes=5*1024*1024,   # 5MB
            backup_count=10
        )
        
        # System logger
        self._create_logger(
            'system',
            level=logging.DEBUG,
            console=False,
            file='system.log',
            max_bytes=20*1024*1024,  # 20MB
            backup_count=3
        )
        
        # Performance logger
        self._create_logger(
            'performance',
            level=logging.INFO,
            console=False,
            file='performance.log',
            max_bytes=10*1024*1024,  # 10MB
            backup_count=5
        )
        
        # User activity logger
        self._create_logger(
            'activity',
            level=logging.INFO,
            console=False,
            file='user_activity.log',
            max_bytes=15*1024*1024,  # 15MB
            backup_count=7
        )
    
    def _create_logger(self, name: str, level: int, console: bool, file: str, max_bytes: int, backup_count: int):
        """Create a configured logger"""
        logger = logging.getLogger(f"advanced_bot.{name}")
        logger.setLevel(level)
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # File handler with rotation
        if file:
            file_path = self.log_dir / file
            file_handler = logging.handlers.RotatingFileHandler(
                file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        # Console handler
        if console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ColoredFormatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            ))
            logger.addHandler(console_handler)
        
        # Add to buffer handler for real-time monitoring
        buffer_handler = BufferHandler(self)
        buffer_handler.setLevel(logging.INFO)
        logger.addHandler(buffer_handler)
        
        self.loggers[name] = logger
    
    def get_logger(self, name: str = 'bot') -> logging.Logger:
        """Get a specific logger"""
        return self.loggers.get(name, self.loggers['bot'])
    
    def log_user_activity(self, user_id: int, action: str, details: Dict[str, Any] = None):
        """Log user activity with structured data"""
        activity_data = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'action': action,
            'details': details or {}
        }
        
        self.loggers['activity'].info(
            f"User {user_id} - {action} - {json.dumps(details, default=str)}"
        )
    
    def log_performance(self, operation: str, duration: float, details: Dict[str, Any] = None):
        """Log performance metrics"""
        perf_data = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'duration': duration,
            'details': details or {}
        }
        
        self.loggers['performance'].info(
            f"{operation} completed in {duration:.2f}s - {json.dumps(details, default=str)}"
        )
    
    def log_system_event(self, event: str, data: Dict[str, Any] = None):
        """Log system events"""
        self.loggers['system'].info(
            f"SYSTEM EVENT: {event} - {json.dumps(data, default=str)}"
        )
    
    def log_error_with_context(self, error: Exception, context: Dict[str, Any] = None):
        """Log error with full context and traceback"""
        error_data = {
            'timestamp': datetime.now().isoformat(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
            'context': context or {}
        }
        
        self.error_count += 1
        
        self.loggers['error'].error(
            f"ERROR ({self.error_count}): {type(error).__name__}: {str(error)}\n"
            f"Context: {json.dumps(context, default=str)}\n"
            f"Traceback: {traceback.format_exc()}"
        )
    
    def get_recent_logs(self, level: str = 'INFO', limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent logs for dashboard"""
        filtered_logs = [
            log for log in self.log_buffer[-limit:]
            if log.get('level') == level or level == 'ALL'
        ]
        return filtered_logs[-limit:]
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Get logging statistics"""
        recent_logs = self.log_buffer[-100:] if self.log_buffer else []
        
        level_counts = {}
        for log in recent_logs:
            level = log.get('level', 'UNKNOWN')
            level_counts[level] = level_counts.get(level, 0) + 1
        
        return {
            'total_logs': len(self.log_buffer),
            'error_count': self.error_count,
            'warning_count': self.warning_count,
            'recent_level_counts': level_counts,
            'log_files_size': self._get_log_files_size(),
            'oldest_log': self.log_buffer[0]['timestamp'] if self.log_buffer else None,
            'newest_log': self.log_buffer[-1]['timestamp'] if self.log_buffer else None
        }
    
    def _get_log_files_size(self) -> Dict[str, int]:
        """Get size of all log files"""
        sizes = {}
        for file_path in self.log_dir.glob("*.log*"):
            try:
                sizes[file_path.name] = file_path.stat().st_size
            except OSError:
                sizes[file_path.name] = 0
        return sizes
    
    async def cleanup_old_logs(self, days: int = 30):
        """Clean up old log files"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_files = []
        
        for file_path in self.log_dir.glob("*.log.*"):
            try:
                if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_date:
                    file_path.unlink()
                    cleaned_files.append(file_path.name)
            except OSError:
                pass
        
        if cleaned_files:
            self.loggers['system'].info(f"Cleaned up old log files: {cleaned_files}")
        
        return len(cleaned_files)

class BufferHandler(logging.Handler):
    """Custom handler to buffer logs for real-time dashboard"""
    
    def __init__(self, advanced_logger):
        super().__init__()
        self.advanced_logger = advanced_logger
    
    def emit(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        self.advanced_logger.log_buffer.append(log_entry)
        
        # Keep buffer size manageable
        if len(self.advanced_logger.log_buffer) > self.advanced_logger.max_buffer_size:
            self.advanced_logger.log_buffer = self.advanced_logger.log_buffer[-self.advanced_logger.max_buffer_size//2:]
        
        # Count errors and warnings
        if record.levelname == 'ERROR':
            self.advanced_logger.error_count += 1
        elif record.levelname == 'WARNING':
            self.advanced_logger.warning_count += 1

# Initialize advanced logging system
advanced_logger = AdvancedLogger()

# Export convenience functions
def get_logger(name: str = 'bot'):
    return advanced_logger.get_logger(name)

def log_user_activity(user_id: int, action: str, details: Dict[str, Any] = None):
    return advanced_logger.log_user_activity(user_id, action, details)

def log_performance(operation: str, duration: float, details: Dict[str, Any] = None):
    return advanced_logger.log_performance(operation, duration, details)

def log_error(error: Exception, context: Dict[str, Any] = None):
    return advanced_logger.log_error_with_context(error, context)
