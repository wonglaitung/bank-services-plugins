"""
Field Mapping Engine for Excel Auto Fill Skill.

Provides intelligent matching between input data fields and template fields.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from fuzzywuzzy import fuzz


@dataclass
class FieldMapping:
    """Represents a mapping between input field and template field."""
    input_field: str
    template_field: str
    confidence: float  # 0.0 to 1.0
    match_type: str  # "exact", "fuzzy", "custom"
    is_manual: bool = False


@dataclass
class MappingResult:
    """Result of the mapping process."""
    mappings: List[FieldMapping]
    matched_input_fields: List[str]
    matched_template_fields: List[str]
    unmatched_input_fields: List[str]
    unmatched_template_fields: List[str]
    mapping_dict: Dict[str, str]  # input_field -> template_field


class FieldMapper:
    """
    Maps input data fields to template fields using multiple matching strategies.

    Matching priority: Custom > Exact > Fuzzy
    """

    def __init__(
        self,
        fuzzy_threshold: int = 70,
        case_sensitive: bool = False
    ):
        """
        Initialize the field mapper.

        Args:
            fuzzy_threshold: Minimum similarity score (0-100) for fuzzy matching
            case_sensitive: Whether to use case-sensitive matching
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.case_sensitive = case_sensitive
        self.custom_mappings: Dict[str, str] = {}

    def load_custom_mappings(self, file_path: str) -> bool:
        """
        Load custom field mappings from a YAML or JSON file.

        Args:
            file_path: Path to the mapping configuration file

        Returns:
            True if loaded successfully

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Mapping file not found: {file_path}")

        content = path.read_text(encoding='utf-8')

        if path.suffix.lower() in ['.yaml', '.yml']:
            data = yaml.safe_load(content)
        elif path.suffix.lower() == '.json':
            data = json.loads(content)
        else:
            raise ValueError(
                f"Unsupported mapping file format: {path.suffix}. "
                "Supported: .yaml, .yml, .json"
            )

        # Support both simple dict and nested 'mappings' key
        if 'mappings' in data:
            self.custom_mappings = data['mappings']
        else:
            self.custom_mappings = data

        return True

    def set_custom_mappings(self, mappings: Dict[str, str]):
        """
        Set custom field mappings directly.

        Args:
            mappings: Dict of input_field -> template_field
        """
        self.custom_mappings = mappings

    def map_fields(
        self,
        input_fields: List[str],
        template_fields: List[str],
        allow_partial: bool = True
    ) -> MappingResult:
        """
        Map input fields to template fields.

        Args:
            input_fields: List of input field names
            template_fields: List of template field names
            allow_partial: Whether to allow partial matches in fuzzy matching

        Returns:
            MappingResult with all mapping information
        """
        mappings = []
        matched_input = set()
        matched_template = set()
        mapping_dict = {}

        # Normalize field names for matching
        normalized_template = {
            self._normalize(f): f for f in template_fields
        }

        # Step 1: Apply custom mappings (highest priority)
        for input_field in input_fields:
            if input_field in self.custom_mappings:
                template_field = self.custom_mappings[input_field]
                if template_field in template_fields:
                    mappings.append(FieldMapping(
                        input_field=input_field,
                        template_field=template_field,
                        confidence=1.0,
                        match_type="custom",
                        is_manual=True
                    ))
                    matched_input.add(input_field)
                    matched_template.add(template_field)
                    mapping_dict[input_field] = template_field

        # Step 2: Exact matching
        for input_field in input_fields:
            if input_field in matched_input:
                continue

            normalized_input = self._normalize(input_field)

            # Direct match
            if normalized_input in normalized_template:
                template_field = normalized_template[normalized_input]
                mappings.append(FieldMapping(
                    input_field=input_field,
                    template_field=template_field,
                    confidence=1.0,
                    match_type="exact"
                ))
                matched_input.add(input_field)
                matched_template.add(template_field)
                mapping_dict[input_field] = template_field

        # Step 3: Fuzzy matching for remaining fields
        unmatched_input = [f for f in input_fields if f not in matched_input]
        unmatched_template = [f for f in template_fields if f not in matched_template]

        for input_field in unmatched_input:
            best_match = None
            best_score = 0

            for template_field in unmatched_template:
                score = self._calculate_similarity(
                    input_field, template_field, allow_partial
                )

                if score >= self.fuzzy_threshold and score > best_score:
                    best_match = template_field
                    best_score = score

            if best_match:
                mappings.append(FieldMapping(
                    input_field=input_field,
                    template_field=best_match,
                    confidence=best_score / 100.0,
                    match_type="fuzzy"
                ))
                matched_input.add(input_field)
                matched_template.add(best_match)
                mapping_dict[input_field] = best_match

        # Build result
        all_matched_input = list(matched_input)
        all_matched_template = list(matched_template)
        final_unmatched_input = [f for f in input_fields if f not in matched_input]
        final_unmatched_template = [f for f in template_fields if f not in matched_template]

        return MappingResult(
            mappings=mappings,
            matched_input_fields=all_matched_input,
            matched_template_fields=all_matched_template,
            unmatched_input_fields=final_unmatched_input,
            unmatched_template_fields=final_unmatched_template,
            mapping_dict=mapping_dict
        )

    def _normalize(self, value: str) -> str:
        """
        Normalize a field name for comparison.

        Args:
            value: Field name to normalize

        Returns:
            Normalized field name
        """
        if self.case_sensitive:
            return value.replace('_', ' ').replace('-', ' ').strip().lower()
        return value.replace('_', ' ').replace('-', ' ').strip().lower()

    def _calculate_similarity(
        self,
        input_field: str,
        template_field: str,
        allow_partial: bool = True
    ) -> int:
        """
        Calculate similarity score between two field names.

        Uses multiple fuzzy matching strategies and returns the best score.

        Args:
            input_field: Input field name
            template_field: Template field name
            allow_partial: Whether to allow partial matches

        Returns:
            Similarity score (0-100)
        """
        # Normalize for comparison
        s1 = self._normalize(input_field)
        s2 = self._normalize(template_field)

        # Try different fuzzy matching strategies
        scores = [
            fuzz.ratio(s1, s2),  # Basic similarity
            fuzz.token_sort_ratio(s1, s2),  # Token-sorted
            fuzz.token_set_ratio(s1, s2),  # Token-set
        ]

        if allow_partial:
            scores.append(fuzz.partial_ratio(s1, s2))  # Partial match
            scores.append(fuzz.WRatio(s1, s2))  # Weighted ratio

        return max(scores)

    def preview_mapping(
        self,
        input_fields: List[str],
        template_fields: List[str]
    ) -> str:
        """
        Generate a human-readable preview of the mapping.

        Args:
            input_fields: List of input field names
            template_fields: List of template field names

        Returns:
            Formatted preview string
        """
        result = self.map_fields(input_fields, template_fields)

        lines = ["Field Mapping Preview", "=" * 50, ""]

        if result.mappings:
            lines.append("Matched Fields:")
            lines.append("-" * 40)
            for m in result.mappings:
                match_indicator = {
                    "exact": "[=]",
                    "fuzzy": "[~]",
                    "custom": "[*]"
                }.get(m.match_type, "[?]")
                lines.append(
                    f"  {match_indicator} '{m.input_field}' -> '{m.template_field}' "
                    f"({m.confidence:.0%})"
                )
            lines.append("")

        if result.unmatched_input_fields:
            lines.append("Unmatched Input Fields:")
            lines.append("-" * 40)
            for f in result.unmatched_input_fields:
                lines.append(f"  ? '{f}'")
            lines.append("")

        if result.unmatched_template_fields:
            lines.append("Unmatched Template Fields:")
            lines.append("-" * 40)
            for f in result.unmatched_template_fields:
                lines.append(f"  ! '{f}'")
            lines.append("")

        lines.append(f"Summary: {len(result.matched_input_fields)}/{len(input_fields)} matched")

        return "\n".join(lines)

    def adjust_mapping(
        self,
        mapping_result: MappingResult,
        adjustments: Dict[str, str]
    ) -> MappingResult:
        """
        Apply manual adjustments to the mapping result.

        Args:
            mapping_result: Original mapping result
            adjustments: Dict of input_field -> new_template_field

        Returns:
            Updated MappingResult
        """
        # Update mappings
        new_mappings = list(mapping_result.mappings)
        mapping_dict = dict(mapping_result.mapping_dict)

        for input_field, new_template_field in adjustments.items():
            # Remove existing mapping for this input field
            new_mappings = [
                m for m in new_mappings if m.input_field != input_field
            ]

            # Add new manual mapping
            new_mappings.append(FieldMapping(
                input_field=input_field,
                template_field=new_template_field,
                confidence=1.0,
                match_type="custom",
                is_manual=True
            ))
            mapping_dict[input_field] = new_template_field

        # Recalculate matched/unmatched lists
        all_input = list(set(m.input_field for m in new_mappings))
        all_template = list(set(m.template_field for m in new_mappings))

        return MappingResult(
            mappings=new_mappings,
            matched_input_fields=all_input,
            matched_template_fields=all_template,
            unmatched_input_fields=[
                f for f in mapping_result.unmatched_input_fields
                if f not in adjustments
            ],
            unmatched_template_fields=mapping_result.unmatched_template_fields,
            mapping_dict=mapping_dict
        )
