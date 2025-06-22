# shared/json_utils.py
"""
Centralized JSON parsing utilities for the fairydust platform.
Provides consistent error handling and optimized parsing across all services.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

def safe_json_parse(
    value: Any, 
    default: T = None, 
    expected_type: type = None
) -> Union[T, Dict, List, str, int, float, bool]:
    """
    Safely parse JSON with consistent error handling.
    
    Args:
        value: Value to parse (string, dict, list, etc.)
        default: Default value to return on parse failure
        expected_type: Expected type for validation (dict, list, etc.)
        
    Returns:
        Parsed value or default on failure
    """
    # If already the expected type, return as-is
    if expected_type and isinstance(value, expected_type):
        return value
    
    # If not a string, return as-is or default
    if not isinstance(value, str):
        return value if value is not None else default
    
    # Try to parse JSON string
    try:
        parsed = json.loads(value)
        
        # Validate type if specified
        if expected_type and not isinstance(parsed, expected_type):
            logger.warning(f"Parsed JSON type {type(parsed)} doesn't match expected {expected_type}")
            return default
            
        return parsed
        
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.debug(f"JSON parse failed for value '{value[:100]}...': {e}")
        return default

def parse_jsonb_field(
    field_value: Any, 
    default: Dict = None, 
    field_name: str = "unknown"
) -> Dict:
    """
    Parse JSONB field from database with fallback to empty dict.
    
    Args:
        field_value: JSONB field value from database
        default: Default dict to return on parse failure
        field_name: Field name for logging purposes
        
    Returns:
        Parsed dictionary or default
    """
    if default is None:
        default = {}
    
    if field_value is None:
        return default
    
    # If already a dict, return as-is
    if isinstance(field_value, dict):
        return field_value
    
    # Parse JSON string
    parsed = safe_json_parse(field_value, default, dict)
    
    if parsed == default and field_value:
        logger.warning(f"Failed to parse JSONB field '{field_name}': {field_value}")
    
    return parsed

def parse_recipe_metadata(recipe_data: Dict) -> Dict:
    """
    Parse recipe metadata JSONB field with recipe-specific handling.
    
    Args:
        recipe_data: Recipe record from database
        
    Returns:
        Recipe dict with parsed metadata
    """
    recipe_dict = dict(recipe_data)
    
    # Parse metadata JSONB field
    metadata = parse_jsonb_field(
        recipe_dict.get('metadata'), 
        default={},
        field_name="recipe_metadata"
    )
    
    recipe_dict['metadata'] = metadata
    return recipe_dict

def parse_profile_data(profile_field_value: Any, field_name: str = "profile_data") -> Any:
    """
    Parse user profile data field value with type preservation.
    
    Args:
        profile_field_value: Field value from user_profile_data
        field_name: Field name for logging
        
    Returns:
        Parsed value with appropriate type
    """
    if profile_field_value is None:
        return None
    
    # If it's already a non-string type, return as-is
    if not isinstance(profile_field_value, str):
        return profile_field_value
    
    # Try to parse as JSON first (for arrays, objects)
    try:
        parsed = json.loads(profile_field_value)
        return parsed
    except (json.JSONDecodeError, ValueError):
        # If JSON parsing fails, return as string
        return profile_field_value

def parse_model_config_field(config_data: Dict, field_name: str) -> Any:
    """
    Parse LLM model configuration field with appropriate type handling.
    
    Args:
        config_data: Model configuration record
        field_name: Field name to parse
        
    Returns:
        Parsed field value
    """
    field_value = config_data.get(field_name)
    
    if field_value is None:
        return None
    
    # Handle specific field types
    if field_name in ['primary_parameters', 'fallback_models', 'cost_limits', 'feature_flags']:
        return parse_jsonb_field(field_value, default={}, field_name=field_name)
    
    return field_value

def parse_story_data(story_data: Dict) -> Dict:
    """
    Parse story data with JSONB field handling for characters and metadata.
    
    Args:
        story_data: Story record from database
        
    Returns:
        Story dict with parsed JSONB fields
    """
    story_dict = dict(story_data)
    
    # Parse characters_involved JSONB field
    characters = parse_jsonb_field(
        story_dict.get('characters_involved'),
        default=[],
        field_name="characters_involved"
    )
    story_dict['characters_involved'] = characters
    
    # Parse metadata JSONB field
    metadata = parse_jsonb_field(
        story_dict.get('metadata'),
        default={},
        field_name="story_metadata"
    )
    story_dict['metadata'] = metadata
    
    return story_dict

def parse_people_profile_data(profile_data: Any) -> List[Dict]:
    """
    Parse people profile data from SQL json_agg with safe handling.
    
    Args:
        profile_data: Profile data from SQL json_agg aggregation
        
    Returns:
        List of profile data dictionaries
    """
    # Parse profile_data if it's a JSON string
    if isinstance(profile_data, str):
        try:
            profile_data = json.loads(profile_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse people profile_data: {profile_data}")
            profile_data = []
    
    # Ensure profile_data is a list
    if not isinstance(profile_data, list):
        logger.warning(f"Profile data is not a list: {type(profile_data)}")
        profile_data = []
    
    return profile_data

def validate_json_structure(data: Any, schema: Dict) -> bool:
    """
    Validate JSON data against a simple schema.
    
    Args:
        data: Data to validate
        schema: Schema dict with field requirements
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(data, dict):
        return False
    
    # Check required fields
    required_fields = schema.get('required', [])
    for field in required_fields:
        if field not in data:
            logger.warning(f"Missing required field: {field}")
            return False
    
    # Check field types
    field_types = schema.get('types', {})
    for field, expected_type in field_types.items():
        if field in data and not isinstance(data[field], expected_type):
            logger.warning(f"Field {field} has wrong type: {type(data[field])} != {expected_type}")
            return False
    
    return True

def safe_json_dumps(obj: Any, default_str: str = "{}") -> str:
    """
    Safely serialize object to JSON string with fallback.
    
    Args:
        obj: Object to serialize
        default_str: Default string on serialization failure
        
    Returns:
        JSON string or default
    """
    try:
        return json.dumps(obj)
    except (TypeError, ValueError) as e:
        logger.warning(f"JSON serialization failed: {e}")
        return default_str

# Commonly used schemas for validation
RECIPE_METADATA_SCHEMA = {
    'required': [],
    'types': {
        'complexity': str,
        'dish': str,
        'include': str,
        'exclude': str,
        'generation_params': dict,
        'parsed_data': dict
    }
}

STORY_CHARACTER_SCHEMA = {
    'required': ['name', 'relationship'],
    'types': {
        'name': str,
        'relationship': str,
        'age': int,
        'traits': list
    }
}

USER_PROFILE_SCHEMA = {
    'required': ['field_name', 'field_value'],
    'types': {
        'field_name': str,
        'category': str,
        'confidence_score': float,
        'source': str
    }
}