# USC Parser

A Python library for parsing United States Code (USC) XML files and extracting structured law data with comprehensive metadata.

## Features

- Parses USC XML files from the Office of Law Revision Counsel
- Extracts complete law text with all metadata
- Tracks amendment history and source credits
- Builds hierarchical structure (title → chapter → section)
- Generates unique identifiers and text hashes for change detection
- Auto-downloads USC XML data if not present

## Installation

```bash
git clone https://github.com/yourusername/usc-parser.git
cd usc-parser
pip install -r requirements.txt
```

## Quick Start

```python
import usc_parser

# Parse a single title
laws = usc_parser.parse_single_title('xml_uscAll@119-12/usc05.xml', 5, True)

# Parse all titles
all_laws = usc_parser.parse_all_titles('xml_uscAll@119-12')

# Access law data
for law in laws:
    print(f"{law['citation']}: {law['law_title']}")
    print(f"Status: {law['status']}")
    print(f"Text: {law['text_of_law'][:200]}...")
```

## Command Line Usage

```bash
# Parse Title 5 (default test)
python usc_parser.py

# Parse a specific title
python usc_parser.py --title 18

# Parse all titles
python usc_parser.py --all

# Specify output file
python usc_parser.py --title 5 --output title5_laws.json

# Use custom XML directory
python usc_parser.py --xml-dir /path/to/xml/files
```

## Data Structure

Each law is returned as a Python dictionary with the following structure:

```python
{
    # Section identification
    "law_number": "1201",
    "law_title": "Appointment of judges",
    "citation": "5 U.S.C. § 1201",
    "identifiers": {
        "guid": "unique-id-string",
        "identifier": "/us/usc/t5/s1201",
        "temporal_id": "s1201",
        "name": "legacy-name",
        "text_hash": "sha256-hash"
    },
    "status": "operational",  # or "repealed", "reserved", etc.
    
    # Hierarchy
    "title_number": 5,
    "is_positive_law": true,
    "law_hierarchy": {
        "title": {"number": 5, "name": "Government Organization and Employees"},
        "chapter": {"number": "12", "name": "Merit Systems Protection Board"},
        "subchapter": {"number": "I", "name": "General"},
        "part": null,
        "section": {"number": "1201", "name": "Appointment of judges"}
    },
    "parent_citation": "5 U.S.C. Ch. 12",
    
    # Content
    "text_of_law": "Full text of the law...",
    "has_subsections": true,
    "subsection_count": 5,
    
    # History and references
    "notes": ["Historical notes", "Editorial notes"],
    "amendment_history": [
        {
            "year": "2022",
            "date": "2022-12-27",
            "public_law": "Pub. L. 117-286",
            "statutes_at_large": "136 Stat. 4359",
            "text": "Amendment description..."
        }
    ],
    "source_credit": {
        "original_act": "Civil Service Reform Act of 1978",
        "original_public_law": "Pub. L. 95-454",
        "original_date": "1978-10-13",
        "original_statutes": "92 Stat. 1111"
    },
    
    # References
    "related_laws": {
        "cross_references": ["5 U.S.C. § 1202", "5 U.S.C. § 7701"],
        "executive_orders": ["Ex. Ord. No. 12107"],
        "public_laws": ["Pub. L. 117-286"],
        "statutes_at_large": ["136 Stat. 4359"]
    },
    
    # Temporal information
    "created_date": null,
    "effective_date": null,
    "start_period": null,
    "end_period": null,
    
    # Document metadata
    "file_source": "usc05.xml",
    "XML_creation_date_OLRC": "2025-03-25T08:30:00",
    "style": "-uslm-lc:I80"
}
```

## Data Source

The parser uses XML files from the Office of Law Revision Counsel. If the XML files are not present, the parser will offer to download them automatically (approximately 250MB).

The XML data represents the current United States Code through Public Law 119-12.

## Requirements

- Python 3.6+
- lxml (optional but recommended for better hierarchy extraction)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- XML data provided by the Office of Law Revision Counsel
- USLM schema documentation was invaluable for understanding the XML structure