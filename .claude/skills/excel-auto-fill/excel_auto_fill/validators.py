"""
Validators for Excel Auto Fill Skill.

Provides validation functions for inputs and data.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .exceptions import (
    InvalidDataFormatError,
    InvalidTemplateFormatError,
    MissingRequiredFieldError,
    NoFieldsFoundError,
    TemplateNotFoundError,
    UnsupportedFormatError,
)


SUPPORTED_FORMATS = ['.xlsx', '.xls', '.xlsm']


def validate_template_path(file_path: str) -> Path:
    """
    Validate that the template path is valid and accessible.

    Args:
        file_path: Path to the template file

    Returns:
        Validated Path object

    Raises:
        TemplateNotFoundError: If file doesn't exist
        UnsupportedFormatError: If file format is not supported
    """
    path = Path(file_path)

    if not path.exists():
        raise TemplateNotFoundError(
            f"Template file not found: {file_path}",
            {"path": str(path.absolute())}
        )

    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise UnsupportedFormatError(
            f"Unsupported file format: {path.suffix}. "
            f"Supported formats: {', '.join(SUPPORTED_FORMATS)}",
            {"format": path.suffix, "supported": SUPPORTED_FORMATS}
        )

    return path


def validate_data_input(
    data: Any,
    required_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Validate and normalize data input.

    Args:
        data: Input data (dict, str, or other)
        required_fields: List of field names that must be present

    Returns:
        Validated data dictionary

    Raises:
        InvalidDataFormatError: If data format is invalid
        MissingRequiredFieldError: If required fields are missing
    """
    if isinstance(data, dict):
        result = data
    elif isinstance(data, str):
        result = _parse_string_data(data)
    else:
        raise InvalidDataFormatError(
            f"Unsupported data type: {type(data).__name__}. "
            "Expected dict or string.",
            {"type": type(data).__name__}
        )

    # Check required fields
    if required_fields:
        missing = [f for f in required_fields if f not in result]
        if missing:
            raise MissingRequiredFieldError(
                f"Missing required fields: {', '.join(missing)}",
                {"missing_fields": missing}
            )

    return result


def _parse_string_data(data: str) -> Dict[str, Any]:
    """
    Parse string data into a dictionary.

    Attempts JSON parsing first, then key-value format.

    Args:
        data: String data to parse

    Returns:
        Parsed dictionary

    Raises:
        InvalidDataFormatError: If string cannot be parsed
    """
    import json

    data = data.strip()

    # Try JSON
    if data.startswith('{') and data.endswith('}'):
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            pass  # Try key-value format

    # Try key-value format
    if ':' in data or '=' in data:
        result = {}
        for line in data.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Split on first : or =
            match = re.match(r'^([^:=]+)[=:](.*)$', line)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                result[key] = value

        if result:
            return result

    raise InvalidDataFormatError(
        "Could not parse input data. Expected JSON or key-value format.",
        {"sample": data[:100] if len(data) > 100 else data}
    )


def validate_mapping_config(
    config: Dict[str, str],
    input_fields: List[str],
    template_fields: List[str]
) -> Dict[str, str]:
    """
    Validate and filter mapping configuration.

    Args:
        config: Mapping configuration dict
        input_fields: Available input field names
        template_fields: Available template field names

    Returns:
        Validated mapping dict with only valid mappings
    """
    valid_mapping = {}
    invalid_mappings = []

    for input_field, template_field in config.items():
        # Check if template field exists
        if template_field not in template_fields:
            invalid_mappings.append({
                "input": input_field,
                "template": template_field,
                "reason": f"Template field '{template_field}' not found"
            })
            continue

        valid_mapping[input_field] = template_field

    return valid_mapping


def validate_output_path(
    output_path: str,
    overwrite: bool = False
) -> Path:
    """
    Validate output path and check for conflicts.

    Args:
        output_path: Desired output path
        overwrite: Whether to allow overwriting

    Returns:
        Validated Path object

    Raises:
        OutputFileExistsError: If file exists and overwrite is False
    """
    path = Path(output_path)

    if path.exists() and not overwrite:
        from exceptions import OutputFileExistsError
        raise OutputFileExistsError(
            f"Output file already exists: {output_path}",
            {"path": str(path.absolute())}
        )

    return path


def check_template_fields(
    field_names: List[str],
    min_fields: int = 1
) -> bool:
    """
    Check if template has sufficient fields.

    Args:
        field_names: List of detected field names
        min_fields: Minimum number of fields required

    Returns:
        True if sufficient fields found

    Raises:
        NoFieldsFoundError: If insufficient fields detected
    """
    if len(field_names) < min_fields:
        raise NoFieldsFoundError(
            f"Template has no detectable fields. "
            "Please use ${fieldName} or {{fieldName}} markers, "
            "or ensure field names are in the first row/column.",
            {"fields_found": len(field_names)}
        )

    return True


def validate_threshold(threshold: int) -> int:
    """
    Validate fuzzy matching threshold value.

    Args:
        threshold: Threshold value to validate

    Returns:
        Validated threshold value

    Raises:
        ValueError: If threshold is out of range
    """
    if not 0 <= threshold <= 100:
        raise ValueError(
            f"Threshold must be between 0 and 100, got {threshold}"
        )
    return threshold
