"""
Excel Auto Fill Skill - Main Execution Module.

Provides the main entry point for the skill.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .auto_filler import AutoFiller, InputFormatParser
from .exceptions import (
    ExcelAutoFillError,
    InvalidDataFormatError,
    NoFieldsFoundError,
    OutputFileExistsError,
    TemplateNotFoundError,
    UnsupportedFormatError,
)
from .field_mapper import FieldMapper, MappingResult
from .template_parser import ParsedTemplate, TemplateParser
from .validators import (
    check_template_fields,
    validate_data_input,
    validate_output_path,
    validate_template_path,
    validate_threshold,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('excel-auto-fill')


@dataclass
class FillResult:
    """Result of the fill operation."""
    success: bool
    output_path: Optional[str]
    stats: Dict[str, Any]
    mapping_result: Optional[MappingResult]
    errors: list


def excel_auto_fill(
    template: str,
    data: Union[str, Dict[str, Any]],
    output: Optional[str] = None,
    mapping: Optional[str] = None,
    threshold: int = 70,
    preview: bool = True,
    default_value: Any = "",
    overwrite: bool = False,
    label_column: Optional[int] = None
) -> FillResult:
    """
    Fill data into an Excel template.

    This is the main entry point for the Excel Auto Fill skill.

    Args:
        template: Path to the Excel template file
        data: Data to fill (JSON string, dict, or key-value text)
        output: Output file path (default: template_filled.xlsx)
        mapping: Path to custom mapping configuration file
        threshold: Fuzzy matching threshold (0-100)
        preview: Show mapping preview before filling
        default_value: Default value for missing fields
        overwrite: Whether to overwrite existing output file
        label_column: Column number (1-based) where field labels are located.
                     Use when labels are not in column A. Example: 2 for column B.

    Returns:
        FillResult with operation status and details

    Example:
        >>> result = excel_auto_fill(
        ...     template="invoice_template.xlsx",
        ...     data={"customer": "Acme Corp", "amount": 5000},
        ...     output="invoice_filled.xlsx"
        ... )
        >>> print(result.success)
        True
    """
    errors = []

    try:
        # Validate threshold
        validate_threshold(threshold)

        # Validate template path
        template_path = validate_template_path(template)
        logger.info(f"Template validated: {template_path}")

        # Set default output path
        if not output:
            output = str(template_path.with_stem(template_path.stem + '_filled'))

        # Validate output path
        output_path = validate_output_path(output, overwrite)

        # Parse input data with validation
        logger.info("Parsing input data...")
        parsed_data = validate_data_input(data)
        logger.info(f"Parsed {len(parsed_data)} data fields")

        # Parse template
        logger.info(f"Loading template: {template}")
        with TemplateParser(label_column=label_column) as template_parser:
            template_parser.load_template(str(template_path))
            parsed_template = template_parser.parse()

            logger.info(
                f"Template parsed: {len(parsed_template.field_names)} fields found, "
                f"markers={'yes' if parsed_template.has_markers else 'no'}, "
                f"layout={parsed_template.layout}"
            )

            # Check if template has fields
            check_template_fields(parsed_template.field_names)

            # Set up field mapper
            field_mapper = FieldMapper(fuzzy_threshold=threshold)

            # Load custom mappings if provided
            if mapping:
                logger.info(f"Loading custom mappings from: {mapping}")
                field_mapper.load_custom_mappings(mapping)

            # Map fields
            logger.info("Mapping input fields to template fields...")
            mapping_result = field_mapper.map_fields(
                list(parsed_data.keys()),
                parsed_template.field_names
            )

            logger.info(
                f"Mapping complete: {len(mapping_result.matched_input_fields)}/"
                f"{len(parsed_data)} fields matched"
            )

            # Show preview if requested
            if preview:
                print("\n" + field_mapper.preview_mapping(
                    list(parsed_data.keys()),
                    parsed_template.field_names
                ))

            # Check if all required fields are matched
            if mapping_result.unmatched_input_fields:
                logger.warning(
                    f"Unmatched input fields: {mapping_result.unmatched_input_fields}"
                )

            # Fill data
            logger.info("Filling data into template...")
            with AutoFiller(default_value=default_value) as filler:
                filler.load_template(str(template_path))
                stats = filler.fill(
                    parsed_data,
                    parsed_template,
                    mapping_result.mapping_dict
                )

                logger.info(f"Fill stats: {stats}")

                # Save output
                final_output = filler.save(str(output_path), overwrite=True)
                logger.info(f"Output saved to: {final_output}")

                return FillResult(
                    success=True,
                    output_path=final_output,
                    stats=stats,
                    mapping_result=mapping_result,
                    errors=[]
                )

    except TemplateNotFoundError as e:
        error_msg = f"Template error: {e.message}"
        logger.error(error_msg)
        errors.append(error_msg)

    except UnsupportedFormatError as e:
        error_msg = f"Format error: {e.message}"
        logger.error(error_msg)
        errors.append(error_msg)

    except InvalidDataFormatError as e:
        error_msg = f"Data error: {e.message}"
        logger.error(error_msg)
        errors.append(error_msg)

    except NoFieldsFoundError as e:
        error_msg = f"Template parsing error: {e.message}"
        logger.error(error_msg)
        errors.append(error_msg)

    except OutputFileExistsError as e:
        error_msg = f"Output error: {e.message}. Use overwrite=True to replace."
        logger.error(error_msg)
        errors.append(error_msg)

    except ExcelAutoFillError as e:
        error_msg = f"Error: {e.message}"
        logger.error(error_msg)
        errors.append(error_msg)

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.exception(error_msg)
        errors.append(error_msg)

    return FillResult(
        success=False,
        output_path=None,
        stats={},
        mapping_result=None,
        errors=errors
    )


# CLI entry point
if __name__ == '__main__':
    import argparse
    import json as json_module

    parser = argparse.ArgumentParser(
        description='Fill data into Excel templates'
    )
    parser.add_argument('template', help='Path to Excel template')
    parser.add_argument('data', help='Data to fill (JSON string or file path)')
    parser.add_argument('-o', '--output', help='Output file path')
    parser.add_argument('-m', '--mapping', help='Custom mapping file')
    parser.add_argument('-t', '--threshold', type=int, default=70,
                        help='Fuzzy matching threshold (0-100)')
    parser.add_argument('--no-preview', action='store_true',
                        help='Skip mapping preview')
    parser.add_argument('--default', default='',
                        help='Default value for missing fields')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing output file')

    args = parser.parse_args()

    # Handle data input
    data_input = args.data
    if Path(args.data).exists():
        with open(args.data, 'r', encoding='utf-8') as f:
            data_input = f.read()

    # Run the skill
    result = excel_auto_fill(
        template=args.template,
        data=data_input,
        output=args.output,
        mapping=args.mapping,
        threshold=args.threshold,
        preview=not args.no_preview,
        default_value=args.default,
        overwrite=args.overwrite
    )

    if result.success:
        print(f"\nSuccess! Output saved to: {result.output_path}")
    else:
        print(f"\nFailed: {result.errors}")
