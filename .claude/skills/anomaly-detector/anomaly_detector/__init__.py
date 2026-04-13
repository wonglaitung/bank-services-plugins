"""
Anomaly detection package for time series data.

This package provides two-layer anomaly detection:
- Layer 1: Real-time Z-Score detection
- Layer 2: Isolation Forest deep analysis
"""

from .path_utils import (
    normalize_path,
    validate_path,
    validate_file_path,
    validate_dir_path,
    normalize_output_path,
)

__version__ = "1.0.0"

__all__ = [
    # Path utilities
    'normalize_path',
    'validate_path',
    'validate_file_path',
    'validate_dir_path',
    'normalize_output_path',
]
