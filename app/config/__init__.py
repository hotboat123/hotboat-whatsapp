"""
Configuration modules for availability and booking

Note: This package coexists with app.config.py (Settings module)
"""
# Import availability config
from app.config.availability_config import (
    AVAILABILITY_CONFIG,
    ServiceConfig,
    AvailabilityConfig,
    get_service_config
)

# Import accommodations config
from app.config.accommodations_config import ACCOMMODATION_IMAGES

# Also export get_settings from the parent config module
# This allows imports like "from app.config import get_settings" to work
import sys
import importlib.util

# Import the parent config.py module
spec = importlib.util.spec_from_file_location("app.config", "app/config.py")
if spec and spec.loader:
    config_module = importlib.util.module_from_spec(spec)
    sys.modules["app.config"] = config_module
    spec.loader.exec_module(config_module)
    
    # Re-export get_settings
    if hasattr(config_module, 'get_settings'):
        get_settings = config_module.get_settings
        __all__ = [
            'get_settings',
            'AVAILABILITY_CONFIG',
            'ServiceConfig',
            'AvailabilityConfig',
            'get_service_config',
            'ACCOMMODATION_IMAGES'
        ]
    else:
        __all__ = [
            'AVAILABILITY_CONFIG',
            'ServiceConfig',
            'AvailabilityConfig',
            'get_service_config',
            'ACCOMMODATION_IMAGES'
        ]
else:
    __all__ = [
        'AVAILABILITY_CONFIG',
        'ServiceConfig',
        'AvailabilityConfig',
        'get_service_config',
        'ACCOMMODATION_IMAGES'
    ]

