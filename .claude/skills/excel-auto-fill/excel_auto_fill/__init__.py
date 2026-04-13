"""
Excel Auto Fill Skill

Automatically match and fill data into Excel templates.
"""

from .auto_filler import AutoFiller, InputFormatParser
from .exceptions import (
    ExcelAutoFillError,
    InvalidDataFormatError,
    InvalidTemplateFormatError,
    MappingError,
    MissingRequiredFieldError,
    NoFieldsFoundError,
    OutputError,
    OutputFileExistsError,
    TemplateError,
    TemplateNotFoundError,
    UnsupportedFormatError,
)
from .field_mapper import FieldMapper, FieldMapping, MappingResult
from .path_utils import (
    normalize_path,
    normalize_output_path,
    validate_dir_path,
    validate_file_path,
    validate_path,
)
from .template_parser import FieldType, ParsedTemplate, TemplateField, TemplateParser
from .validators import (
    validate_data_input,
    validate_output_path,
    validate_template_path,
    validate_threshold,
)

__all__ = [
    # Template parsing
    'TemplateParser',
    'TemplateField',
    'ParsedTemplate',
    'FieldType',
    # Field mapping
    'FieldMapper',
    'FieldMapping',
    'MappingResult',
    # Auto filling
    'AutoFiller',
    'InputFormatParser',
    # Path utilities
    'normalize_path',
    'validate_path',
    'validate_file_path',
    'validate_dir_path',
    'normalize_output_path',
    # Exceptions
    'ExcelAutoFillError',
    'TemplateError',
    'TemplateNotFoundError',
    'InvalidTemplateFormatError',
    'UnsupportedFormatError',
    'NoFieldsFoundError',
    'DataError',
    'InvalidDataFormatError',
    'MissingRequiredFieldError',
    'MappingError',
    'OutputError',
    'OutputFileExistsError',
    # Validators
    'validate_template_path',
    'validate_data_input',
    'validate_output_path',
    'validate_threshold',
]

__version__ = '1.0.0'
