# shared/uuid_utils.py
"""
UUIDv7 utilities for fairydust platform.

UUIDv7 provides time-ordered unique identifiers that improve database performance:
- Time-ordered prefix prevents B-tree index fragmentation
- Better cache locality for recent records
- Improved insert performance (up to 49% faster)
- Smaller index sizes and reduced WAL overhead

This module provides a consistent interface for generating UUIDv7 across all services.
"""
import uuid
from uuid import UUID
from typing import Union

try:
    from uuid_extensions import uuid7
    UUIDV7_AVAILABLE = True
except ImportError:
    UUIDV7_AVAILABLE = False
    import warnings
    warnings.warn(
        "uuid7 package not available. Install with: pip install uuid7==0.1.0 "
        "(imports as: from uuid_extensions import uuid7)",
        ImportWarning
    )


def generate_uuid7() -> UUID:
    """
    Generate a UUIDv7 (time-ordered UUID).
    
    UUIDv7 format:
    - 48-bit timestamp (milliseconds since Unix epoch)
    - 12-bit random data
    - 4-bit version (0111)
    - 2-bit variant (10)
    - 62-bit random data
    
    Returns:
        UUID: A time-ordered UUID that sorts chronologically
        
    Raises:
        RuntimeError: If uuid7 package is not installed
        
    Example:
        >>> user_id = generate_uuid7()
        >>> str(user_id)
        '018d3f5c-d5a0-7000-a000-123456789abc'
    """
    if not UUIDV7_AVAILABLE:
        raise RuntimeError(
            "uuid7 package is required for UUIDv7 generation. "
            "Install with: pip install uuid7==0.1.0 "
            "(imports as: from uuid_extensions import uuid7)"
        )
    
    return uuid7()


def generate_uuid4() -> UUID:
    """
    Generate a UUIDv4 (random UUID) for backward compatibility.
    
    Note: UUIDv4 should be avoided for new primary keys due to 
    index fragmentation issues. Use generate_uuid7() instead.
    
    Returns:
        UUID: A random UUID
    """
    return uuid.uuid4()


def is_valid_uuid(value: Union[str, UUID]) -> bool:
    """
    Check if a value is a valid UUID (any version).
    
    Args:
        value: String or UUID to validate
        
    Returns:
        bool: True if valid UUID, False otherwise
        
    Example:
        >>> is_valid_uuid('018d3f5c-d5a0-7000-a000-123456789abc')
        True
        >>> is_valid_uuid('invalid-uuid')
        False
    """
    try:
        if isinstance(value, str):
            UUID(value)
        elif isinstance(value, UUID):
            # Already a UUID object
            pass
        else:
            return False
        return True
    except (ValueError, TypeError):
        return False


def uuid_to_str(value: UUID) -> str:
    """
    Convert UUID to string representation.
    
    Args:
        value: UUID object to convert
        
    Returns:
        str: String representation of UUID
        
    Example:
        >>> uuid_obj = generate_uuid7()
        >>> uuid_to_str(uuid_obj)
        '018d3f5c-d5a0-7000-a000-123456789abc'
    """
    return str(value)


def str_to_uuid(value: str) -> UUID:
    """
    Convert string to UUID object with validation.
    
    Args:
        value: String representation of UUID
        
    Returns:
        UUID: UUID object
        
    Raises:
        ValueError: If string is not a valid UUID
        
    Example:
        >>> str_to_uuid('018d3f5c-d5a0-7000-a000-123456789abc')
        UUID('018d3f5c-d5a0-7000-a000-123456789abc')
    """
    return UUID(value)


def get_timestamp_from_uuid7(uuid_val: Union[str, UUID]) -> int:
    """
    Extract timestamp (milliseconds since Unix epoch) from UUIDv7.
    
    Args:
        uuid_val: UUIDv7 as string or UUID object
        
    Returns:
        int: Timestamp in milliseconds since Unix epoch
        
    Raises:
        ValueError: If not a valid UUID or not UUIDv7
        
    Example:
        >>> uuid_val = generate_uuid7()
        >>> timestamp = get_timestamp_from_uuid7(uuid_val)
        >>> print(f"Generated at: {timestamp}ms")
    """
    if isinstance(uuid_val, str):
        uuid_val = UUID(uuid_val)
    
    # Check if this is UUIDv7 (version 7)
    if uuid_val.version != 7:
        raise ValueError(f"UUID version {uuid_val.version} is not UUIDv7")
    
    # Extract timestamp from first 48 bits
    # UUIDv7 stores timestamp in first 6 bytes (48 bits)
    timestamp_bytes = uuid_val.bytes[:6]
    timestamp = int.from_bytes(timestamp_bytes, byteorder='big')
    
    return timestamp


# Convenience aliases for backward compatibility
generate_id = generate_uuid7  # Primary ID generator
generate_random_id = generate_uuid4  # For cases requiring random IDs


# Performance monitoring (optional)
import time
from functools import wraps
from typing import Callable, Any


def benchmark_uuid_generation(func: Callable) -> Callable:
    """
    Decorator to benchmark UUID generation performance.
    
    Usage:
        @benchmark_uuid_generation
        def create_users(count: int):
            return [generate_uuid7() for _ in range(count)]
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter_ns()
        result = func(*args, **kwargs)
        end_time = time.perf_counter_ns()
        
        duration_ns = end_time - start_time
        print(f"UUID generation benchmark: {func.__name__} took {duration_ns:,}ns")
        return result
    
    return wrapper


# Module-level constants
UUID_V7_VERSION = 7
UUID_V4_VERSION = 4
UUID_NIL = UUID('00000000-0000-0000-0000-000000000000')