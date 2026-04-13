"""
Path normalization utilities for cross-platform compatibility.

Handles mixed path formats (Unix ~/ with Windows backslashes) and provides
consistent path handling across different operating systems.

解决命令行中文路径编码问题：
- Windows CMD 默认使用 GBK/CP936 编码
- Python 3 内部使用 UTF-8 编码
- 通过重新编码解码来修复乱码问题
"""

import os
import sys
from pathlib import Path
from typing import Union


def fix_chinese_path_encoding(raw_path: str) -> str:
    """
    修复命令行传递的中文路径编码问题。

    问题根源：
    - Windows CMD 使用系统编码（GBK/CP936）传递参数
    - Python 3 使用 UTF-8 解码 sys.argv
    - 导致中文路径出现乱码

    解决方法：
    1. 将错误解码的字符串重新编码回原始字节
    2. 使用正确的编码（GBK/CP936）重新解码

    Args:
        raw_path: 原始路径字符串（可能包含乱码）

    Returns:
        修复编码后的路径字符串

    Examples:
        >>> # 假设命令行传递了 "D:\\测试\\data.csv"
        >>> # Python 错误解码后变成 "D:\\\\æµ\\x8bè¯\\x95\\\\data.csv"
        >>> fix_chinese_path_encoding(garbled_path)
        'D:\\测试\\data.csv'
    """
    # 仅在 Windows 系统下处理
    if sys.platform != 'win32':
        return raw_path

    try:
        # 尝试修复编码：
        # 1. encode('utf-8'): 将错误解码的字符串转回字节（使用 UTF-8，因为 sys.argv 已经被 Python 用 UTF-8 解码）
        # 2. decode('gbk'): 使用 Windows 系统编码正确解码
        #
        # 注意：这种方法适用于 Windows CMD/PowerShell 传递的中文路径
        # 如果路径已经是正确的 UTF-8 编码，这个操作会抛出异常，此时直接返回原路径
        fixed_path = raw_path.encode('utf-8').decode('gbk')
        return fixed_path
    except (UnicodeDecodeError, UnicodeEncodeError):
        # 如果编码转换失败，说明路径可能已经是正确的，直接返回
        return raw_path


def normalize_path(raw_path: str, fix_encoding: bool = True) -> str:
    """
    Normalize path to unified format (forward slashes).

    Handles:
    - Chinese path encoding fix (Windows CMD compatibility)
    - Tilde expansion (~ to home directory)
    - Backslash to forward slash conversion
    - Relative path resolution

    Args:
        raw_path: Raw path string, may contain ~, backslashes, or encoding issues
        fix_encoding: Whether to fix Chinese path encoding (default: True)

    Returns:
        Normalized path string with forward slashes

    Examples:
        >>> normalize_path("~/Documents\\My Projects/file.txt")
        '/home/user/Documents/My Projects/file.txt'

        >>> normalize_path("data/../config/settings.json")
        '/home/user/project/config/settings.json'

        >>> # Windows 中文路径
        >>> normalize_path("D:\\测试\\data.csv")
        'D:/测试/data.csv'
    """
    # Step 1: Fix encoding issues (Windows CMD 中文路径)
    if fix_encoding:
        raw_path = fix_chinese_path_encoding(raw_path)

    # Step 2: Use pathlib to parse path
    path = Path(raw_path).expanduser()

    # Step 3: Convert to absolute path if not already
    if not path.is_absolute():
        path = path.resolve()

    # Step 4: Normalize to forward slashes for consistency
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
