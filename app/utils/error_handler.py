"""Error handling utilities for Instagram automation."""

import logging
import time
from typing import Callable, Any
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
