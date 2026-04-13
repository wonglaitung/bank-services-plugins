"""
Path normalization utilities for cross-platform compatibility.

Handles mixed path formats (Unix ~/ with Windows backslashes) and provides
consistent path handling across different operating systems.
"""

from pathlib import Path
from typing import Union


def normalize_path(raw_path: str) -> str:
    """
    Normalize path to unified format (forward slashes).
    
    Handles:
    - Tilde expansion (~ to home directory)
    - Backslash to forward slash conversion
    - Relative path resolution
    
    Args:
        raw_path: Raw path string, may contain ~, backslashes, etc.
    
    Returns:
        Normalized path string with forward slashes
    
    Examples:
        >>> normalize_path("~/Documents\\My Projects/file.txt")
        '/home/user/Documents/My Projects/file.txt'
        
        >>> normalize_path("data/../config/settings.json")
        '/home/user/project/config/settings.json'
    """
    # Use pathlib to parse path
    path = Path(raw_path).expanduser()
    
    # Convert to absolute path if not already
    if not path.is_absolute():
        path = path.resolve()
    
    # Normalize to forward slashes for consistency
    return str(path).replace('\\', '/')


def validate_path(raw_path: str, must_exist: bool = True) -> Path:
    """
    Validate and resolve path.
    
    Args:
        raw_path: Raw path string
        must_exist: Whether path must exist (default: True)
    
    Returns:
        Resolved Path object
    
    Raises:
        FileNotFoundError: If must_exist=True and path doesn't exist
    """
    path = Path(raw_path).expanduser().resolve()
    
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    
    return path


def validate_file_path(raw_path: str) -> Path:
    """
    Validate that path exists and is a file.
    
    Args:
        raw_path: Raw path string
    
    Returns:
        Resolved Path object
    
    Raises:
        FileNotFoundError: If path doesn't exist
        ValueError: If path is not a file
    """
    path = validate_path(raw_path)
    
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    
    return path


def validate_dir_path(raw_path: str) -> Path:
    """
    Validate that path exists and is a directory.
    
    Args:
        raw_path: Raw path string
    
    Returns:
        Resolved Path object
    
    Raises:
        FileNotFoundError: If path doesn't exist
        ValueError: If path is not a directory
    """
    path = validate_path(raw_path)
    
    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")
    
    return path


def normalize_output_path(raw_path: str, base_dir: str = None) -> str:
    """
    Normalize output path for saving files.
    
    Args:
        raw_path: Raw output path string
        base_dir: Optional base directory to resolve relative paths
    
    Returns:
        Normalized absolute path string
    """
    path = Path(raw_path).expanduser()
    
    # If relative path and base_dir provided, resolve relative to base_dir
    if not path.is_absolute() and base_dir:
        base = Path(base_dir).expanduser().resolve()
        path = base / path
    
    # Resolve to absolute path
    path = path.resolve()
    
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    return str(path).replace('\\', '/')
