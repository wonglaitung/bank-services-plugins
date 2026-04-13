"""
Exception classes for Excel Auto Fill Skill.

Provides custom exceptions for better error handling and reporting.
"""


class ExcelAutoFillError(Exception):
    """Base exception for Excel Auto Fill errors."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class TemplateError(ExcelAutoFillError):
    """Exception raised for template-related errors."""
    pass


class TemplateNotFoundError(TemplateError):
    """Exception raised when template file is not found."""
    pass


class InvalidTemplateFormatError(TemplateError):
    """Exception raised when template format is invalid or corrupted."""
    pass


class UnsupportedFormatError(TemplateError):
    """Exception raised when file format is not supported."""
    pass


class NoFieldsFoundError(TemplateError):
    """Exception raised when no fields can be detected in template."""
    pass


class DataError(ExcelAutoFillError):
    """Exception raised for data-related errors."""
    pass


class InvalidDataFormatError(DataError):
    """Exception raised when input data format is invalid."""
    pass


class MissingRequiredFieldError(DataError):
    """Exception raised when required fields are missing."""
    pass


class MappingError(ExcelAutoFillError):
    """Exception raised for mapping-related errors."""
    pass


class NoMatchFoundError(MappingError):
    """Exception raised when no matching fields are found."""
    pass


class AmbiguousMappingError(MappingError):
    """Exception raised when field mapping is ambiguous."""
    pass


class OutputError(ExcelAutoFillError):
    """Exception raised for output-related errors."""
    pass


class OutputFileExistsError(OutputError):
    """Exception raised when output file exists and overwrite is disabled."""
    pass


class OutputWriteError(OutputError):
    """Exception raised when unable to write output file."""
    pass
