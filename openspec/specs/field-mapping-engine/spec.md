### Requirement: Perform exact field matching
The system SHALL match input field names to template field names using exact string comparison.

#### Scenario: Successful exact match
- **WHEN** input field name "customer_name" matches template field name "customer_name"
- **THEN** system creates a mapping between the two fields

#### Scenario: Case-insensitive match
- **WHEN** input field name "CustomerName" differs only in case from template field "customer_name"
- **THEN** system creates a mapping with case normalization

### Requirement: Perform fuzzy field matching
The system SHALL match field names with minor differences using fuzzy string matching.

#### Scenario: Match with typo
- **WHEN** input field name "custmer_name" has a typo
- **THEN** system matches it to template field "customer_name" with similarity score above threshold

#### Scenario: Match with abbreviation
- **WHEN** input field name "cust_name" is an abbreviation
- **THEN** system matches it to template field "customer_name"

#### Scenario: Reject low similarity match
- **WHEN** input field name has similarity score below threshold (e.g., "abc" vs "xyz")
- **THEN** system does not create a mapping and flags for manual review

### Requirement: Support custom mapping configuration
The system SHALL allow users to provide explicit field mappings via configuration file.

#### Scenario: Apply custom mapping
- **WHEN** user provides a mapping config specifying "input_field" → "template_field"
- **THEN** system uses the specified mapping instead of automatic matching

#### Scenario: Override automatic matching
- **WHEN** custom mapping conflicts with automatic matching result
- **THEN** custom mapping takes precedence

### Requirement: Provide matching preview
The system SHALL generate a preview of all field mappings before filling data.

#### Scenario: Display mapping preview
- **WHEN** matching process completes
- **THEN** system displays all matched fields, unmatched input fields, and unmatched template fields

#### Scenario: Allow manual adjustment
- **WHEN** user reviews preview
- **THEN** user can modify mappings or add new mappings before proceeding
