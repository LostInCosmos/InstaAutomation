"""
Performance monitoring utilities for Instagram automation.
"""

import time
import logging
from typing import Dict, Any, Optional
from contextlib import contextmanager
from functools import wraps

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor and track performance metrics."""
    
    def __init__(self):
        self.metrics: Dict[str, Any] = {}
        self.start_times: Dict[str, float] = {}
        self.operation_counts: Dict[str, int] = {}
    
    def start_timer(self, operation: str) -> None:
        """Start timing an operation."""
        self.start_times[operation] = time.time()
        logger.debug(f"Started timing: {operation}")
    
    def end_timer(self, operation: str) -> float:
        """End timing an operation and return duration."""
        if operation not in self.start_times:
            logger.warning(f"No start time found for operation: {operation}")
            return 0.0
        
        duration = time.time() - self.start_times[operation]
        self.metrics[operation] = duration
        del self.start_times[operation]
        
        logger.debug(f"Completed {operation} in {duration:.2f}s")
        return duration
    
    def increment_counter(self, operation: str, count: int = 1) -> None:
        """Increment a counter for an operation."""
        self.operation_counts[operation] = self.operation_counts.get(operation, 0) + count
        logger.debug(f"Incremented {operation} counter by {count}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all performance metrics."""
        return {
            'timings': self.metrics.copy(),
            'counts': self.operation_counts.copy()
        }
    
    def get_summary(self) -> str:
        """Get a formatted summary of performance metrics."""
        if not self.metrics and not self.operation_counts:
            return "No performance data available."
        
        summary = "Performance Summary:\n"
        summary += "=" * 50 + "\n"
        
        if self.metrics:
            summary += "Timings:\n"
            for operation, duration in self.metrics.items():
                summary += f"  {operation}: {duration:.2f}s\n"
        
        if self.operation_counts:
            summary += "\nCounts:\n"
            for operation, count in self.operation_counts.items():
                summary += f"  {operation}: {count}\n"
        
        return summary


# Global performance monitor instance
perf_monitor = PerformanceMonitor()


def time_operation(operation_name: str):
    """
    Decorator to time a function execution.
    
    Args:
        operation_name: Name of the operation for timing
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            perf_monitor.start_timer(operation_name)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                perf_monitor.end_timer(operation_name)
        return wrapper
    return decorator


@contextmanager
def time_context(operation_name: str):
    """
    Context manager to time a block of code.
    
    Args:
        operation_name: Name of the operation for timing
    """
    perf_monitor.start_timer(operation_name)
    try:
        yield
    finally:
        perf_monitor.end_timer(operation_name)


def log_performance(func):
    """
    Decorator to log function performance.
    
    Logs execution time and any performance metrics.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        function_name = f"{func.__module__}.{func.__name__}"
        
        logger.info(f"Starting {function_name}")
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            logger.info(f"Completed {function_name} in {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Failed {function_name} after {duration:.2f}s: {e}")
            raise
    
    return wrapper


def get_memory_usage() -> Dict[str, float]:
    """
    Get current memory usage information.
    
    Returns:
        Dictionary with memory usage information in MB
    """
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            'rss': memory_info.rss / 1024 / 1024,  # Resident Set Size
            'vms': memory_info.vms / 1024 / 1024,  # Virtual Memory Size
            'percent': process.memory_percent()
        }
    except ImportError:
        logger.warning("psutil not available for memory monitoring")
        return {}
    except Exception as e:
        logger.error(f"Failed to get memory usage: {e}")
        return {}


def get_system_info() -> Dict[str, Any]:
    """
    Get system information for performance analysis.
    
    Returns:
        Dictionary with system information
    """
    import os
    import platform
    
    return {
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'cpu_count': os.cpu_count(),
        'memory_usage': get_memory_usage()
    }
