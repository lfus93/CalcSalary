"""
Performance optimization utilities
"""
import functools
import time
import logging
from typing import Any, Callable, Dict, Optional
import pandas as pd


class PerformanceCache:
    """Simple caching system for expensive operations"""
    
    def __init__(self, max_size: int = 128):
        self.cache: Dict[str, Any] = {}
        self.max_size = max_size
        self.access_times: Dict[str, float] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        if key in self.cache:
            self.access_times[key] = time.time()
            return self.cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set cached value"""
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = value
        self.access_times[key] = time.time()
    
    def _evict_oldest(self) -> None:
        """Remove oldest cached item"""
        if not self.access_times:
            return
        
        oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
        del self.cache[oldest_key]
        del self.access_times[oldest_key]
    
    def clear(self) -> None:
        """Clear all cached items"""
        self.cache.clear()
        self.access_times.clear()


# Global cache instance
_global_cache = PerformanceCache()


def cached(key_func: Optional[Callable] = None, ttl: Optional[float] = None):
    """
    Decorator for caching function results
    
    Args:
        key_func: Function to generate cache key from arguments
        ttl: Time to live in seconds (None for no expiration)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = f"{func.__name__}_{key_func(*args, **kwargs)}"
            else:
                cache_key = f"{func.__name__}_{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Check cache
            cached_result = _global_cache.get(cache_key)
            if cached_result is not None:
                result, timestamp = cached_result
                
                # Check TTL
                if ttl is None or (time.time() - timestamp) < ttl:
                    return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            _global_cache.set(cache_key, (result, time.time()))
            
            return result
        
        return wrapper
    return decorator


def timed(func: Callable) -> Callable:
    """Decorator to measure function execution time"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        logger = logging.getLogger(func.__module__)
        logger.debug(f"{func.__name__} executed in {end_time - start_time:.4f} seconds")
        
        return result
    return wrapper


class DataFrameOptimizer:
    """Utility class for optimizing DataFrame operations"""
    
    @staticmethod
    def optimize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
        """Optimize DataFrame data types to reduce memory usage"""
        optimized_df = df.copy()
        
        for col in optimized_df.columns:
            col_type = optimized_df[col].dtype
            
            if col_type == 'object':
                # Try to convert to category if it has few unique values
                unique_ratio = optimized_df[col].nunique() / len(optimized_df[col])
                if unique_ratio < 0.5:  # Less than 50% unique values
                    try:
                        optimized_df[col] = optimized_df[col].astype('category')
                    except (ValueError, TypeError):
                        pass
            
            elif col_type in ['int64', 'int32']:
                # Downcast integers
                try:
                    optimized_df[col] = pd.to_numeric(optimized_df[col], downcast='integer')
                except (ValueError, TypeError):
                    pass
            
            elif col_type in ['float64', 'float32']:
                # Downcast floats
                try:
                    optimized_df[col] = pd.to_numeric(optimized_df[col], downcast='float')
                except (ValueError, TypeError):
                    pass
        
        return optimized_df
    
    @staticmethod
    def batch_process(df: pd.DataFrame, func: Callable, batch_size: int = 1000) -> pd.DataFrame:
        """Process DataFrame in batches for large datasets"""
        if len(df) <= batch_size:
            return func(df)
        
        results = []
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            batch_result = func(batch)
            results.append(batch_result)
        
        return pd.concat(results, ignore_index=True)


def clear_cache():
    """Clear the global performance cache"""
    _global_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    return {
        'size': len(_global_cache.cache),
        'max_size': _global_cache.max_size,
        'keys': list(_global_cache.cache.keys())
    }