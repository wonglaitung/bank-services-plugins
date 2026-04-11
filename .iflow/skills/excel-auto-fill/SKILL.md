# Excel Auto Fill Skill

Automatically match and fill data into Excel templates.

## Description

This skill intelligently matches user-provided data to Excel template fields and fills them into the correct positions. It supports multiple input formats, matching strategies, and preserves template formatting.

## When to Use

Use this skill when you need to:
- Fill data into Excel report templates
- Populate form templates with structured data
- Batch process multiple Excel files with similar structure
- Automate repetitive Excel data entry tasks

## Invocation

```
skill: "excel-auto-fill"
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| template | string | Yes | Path to the Excel template file (.xlsx, .xls, .xlsm) |
| data | object/string | Yes | Data to fill (JSON object, dict, or key-value text) |
| output | string | No | Output file path (default: template_filled.xlsx) |
| mapping | string | No | Path to custom mapping configuration file (YAML/JSON) |
| threshold | number | No | Fuzzy matching threshold 0-100 (default: 70) |
| preview | boolean | No | Show mapping preview before filling (default: true) |
| default_value | string | No | Default value for missing fields (default: empty) |

## Input Formats

### JSON
```json
{
  "customer_name": "John Doe",
  "order_date": "2024-01-15",
  "amount": 1500.00
}
```

### Key-Value Text
```
customer_name: John Doe
order_date: 2024-01-15
amount: 1500.00
```

### Python Dictionary
```python
{
    "customer_name": "John Doe",
    "order_date": "2024-01-15",
    "amount": 1500.00
}
```

## Template Markers

The skill recognizes these field markers in templates:

- `${fieldName}` - Standard marker
- `{{fieldName}}` - Jinja-style marker

If no markers are found, the skill auto-detects field names from:
- First row (horizontal layout)
- First column (vertical layout)

## Custom Mapping Configuration

Create a YAML or JSON file to specify explicit field mappings:

```yaml
mappings:
  input_field_name: template_field_name
  cust_name: customer_name
  order_dt: order_date
```

## Examples

### Basic Usage
```
User: Fill this data into my invoice template:
{
  "invoice_number": "INV-2024-001",
  "customer": "Acme Corp",
  "total": 5000.00
}

Assistant: [Invokes excel-auto-fill skill]
```

### With Custom Mapping
```
User: Fill the report template with this data using the mapping file:
Data: {"nm": "Product A", "qty": 100}
Template: report_template.xlsx
Mapping: field_mapping.yaml
```

## Matching Strategies

1. **Exact Match**: Case-insensitive exact string comparison
2. **Fuzzy Match**: Handles typos, abbreviations, variations (threshold configurable)
3. **Custom Mapping**: Explicit user-defined mappings (highest priority)

## Output

- Filled Excel file at specified output path
- Mapping preview (if enabled)
- Summary of matched/unmatched fields

## Notes

- Original template is never modified
- Cell formatting (fonts, borders, colors) is preserved
- Supports .xlsx, .xls, and .xlsm formats
- Merged cells are preserved
