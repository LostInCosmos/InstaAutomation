"""
Error handling utilities for Instagram automation.
"""

import logging
import time
from typing import Callable, Any, Optional
from functools import wraps
import config

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries: int = None, delay: float = None, 
                    exceptions: tuple = (Exception,)):
    """
    Decorator to retry a function on failure.
    
    Args:
        max_retries: Maximum number of retries (uses config default if None)
        delay: Delay between retries in seconds (uses config default if None)
        exceptions: Tuple of exceptions to catch and retry on
    """
    if max_retries is None:
        max_retries = config.MAX_RETRIES
    if delay is None:
        delay = config.RETRY_DELAY
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")
                        raise last_exception
            
            return None
        return wrapper
    return decorator


def safe_execute(func: Callable, *args, **kwargs) -> tuple[bool, Any, Optional[Exception]]:
    """
    Safely execute a function and return success status, result, and exception.
    
    Args:
        func: Function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        Tuple of (success: bool, result: Any, exception: Optional[Exception])
    """
    try:
        result = func(*args, **kwargs)
        return True, result, None
    except Exception as e:
        logger.error(f"Function {func.__name__} failed: {e}")
        return False, None, e


def validate_file_path(file_path: str, must_exist: bool = True) -> bool:
    """
    Validate a file path.
    
    Args:
        file_path: Path to validate
        must_exist: Whether the file must exist
        
    Returns:
        True if valid, False otherwise
    """
    from pathlib import Path
    
    try:
        path = Path(file_path)
        if must_exist:
            return path.exists() and path.is_file()
        else:
            return path.parent.exists() or path.parent == Path.cwd()
    except Exception as e:
        logger.error(f"Invalid file path {file_path}: {e}")
        return False


def validate_url(url: str) -> bool:
    """
    Validate a URL format.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    import re
    
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(url))


class ErrorHandler:
    """Centralized error handling class."""
    
    def __init__(self):
        self.error_count = 0
        self.critical_errors = []
    
    def handle_error(self, error: Exception, context: str = "", critical: bool = False):
        """
        Handle an error with logging and tracking.
        
        Args:
            error: Exception to handle
            context: Context where the error occurred
            critical: Whether this is a critical error
        """
        self.error_count += 1
        error_msg = f"Error in {context}: {error}" if context else str(error)
        
        if critical:
            self.critical_errors.append(error_msg)
            logger.critical(error_msg)
        else:
            logger.error(error_msg)
    
    def has_critical_errors(self) -> bool:
        """Check if there are any critical errors."""
        return len(self.critical_errors) > 0
    
    def get_error_summary(self) -> str:
        """Get a summary of all errors."""
        if self.error_count == 0:
            return "No errors occurred."
        
        summary = f"Total errors: {self.error_count}"
        if self.critical_errors:
            summary += f"\nCritical errors: {len(self.critical_errors)}"
            for error in self.critical_errors:
                summary += f"\n  - {error}"
        
        return summary
