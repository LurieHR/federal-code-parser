# USC Parser Enhancement TODO

## Core Dictionary Structure Improvements

### 1. Temporal/Version Tracking Fields
- [ ] Add `temporal_info` dictionary to each law:
  - [ ] Extract `createdDate` from section attributes
  - [ ] Extract `effectiveDate` from section attributes
  - [ ] Extract `startPeriod` and `endPeriod` for version validity
  - [ ] Implement `extract_last_amendment_date()` function
  - [ ] Add file modification date tracking

### 2. Enhanced Hierarchy Information
- [ ] Expand `law_hierarchy` to include full path:
  - [ ] Title (number and name)
  - [ ] Subtitle (if exists)
  - [ ] Chapter (number and title)
  - [ ] Subchapter (number and title)
  - [ ] Part (number and title)
  - [ ] Subpart (if exists)
  - [ ] Section number
- [ ] Add `parent_citation` field (e.g., "5 U.S.C. Ch. 12")
- [ ] Add `has_subsections` boolean field
- [ ] Add `subsection_count` field

### 3. Amendment History Tracking
- [ ] Create `amendment_history` list with:
  - [ ] Public Law number (e.g., "Pub. L. 117-286")
  - [ ] Amendment date
  - [ ] Statutes at Large reference
  - [ ] Description of changes
- [ ] Parse amendment information from notes sections
- [ ] Extract from sourceCredit elements

### 4. Unique Identifiers
- [ ] Add `identifiers` dictionary:
  - [ ] GUID from `@id` attribute
  - [ ] URL path from `@identifier` attribute
  - [ ] Temporal ID from `@temporalId`
  - [ ] Legacy ID from `@name` attribute
- [ ] Add SHA256 hash of law text for change detection

### 5. Legislative Source Information
- [ ] Create `legislative_source` dictionary:
  - [ ] Original act name
  - [ ] Original public law number
  - [ ] Original enactment date
  - [ ] Codification date
- [ ] Implement `extract_legislative_history()` function
- [ ] Parse sourceCredit for Public Law references

### 6. Enhanced Cross-References
- [ ] Expand `related_laws` structure:
  - [ ] `cites_to`: Laws this section references
  - [ ] `cited_by`: Laws that reference this section (requires post-processing)
  - [ ] `see_also`: Related provisions
  - [ ] `supersedes`: Laws this replaced
  - [ ] `superseded_by`: Laws that replaced this
- [ ] Implement bidirectional reference mapping

## New Functions to Implement

### 7. Parsing Functions
- [ ] `extract_legislative_history(section)` - Parse source credits
- [ ] `parse_source_credit(text)` - Extract Pub. L., dates, Stat. references
- [ ] `extract_last_amendment_date(section)` - Find most recent amendment
- [ ] `extract_subsection_info(section)` - Count and identify subsections
- [ ] `calculate_text_hash(text)` - Generate SHA256 for change detection

### 8. Post-Processing Functions
- [ ] `build_hierarchy_index(all_sections)` - Create parent-child relationships
- [ ] `build_citation_index(all_sections)` - Create lookup by citation
- [ ] `build_cross_reference_index(all_sections)` - Map bidirectional references
- [ ] `validate_references(all_sections)` - Ensure all refs resolve

### 9. Change Tracking
- [ ] Add `change_tracking` dictionary:
  - [ ] Version (e.g., "119-12")
  - [ ] Last updated timestamp
  - [ ] Change type (amendment/new/repeal)
  - [ ] Change summary
- [ ] Implement version comparison system
- [ ] Store previous versions for diff generation

## Processing Pipeline Enhancements

### 10. Two-Pass Processing
- [ ] First pass: Extract all sections with basic info
- [ ] Second pass: Build cross-references and relationships
- [ ] Third pass: Validate all references resolve correctly

### 11. Additional Metadata
- [ ] Add `extraction_date` timestamp
- [ ] Add `parser_version` for tracking
- [ ] Add `validation_status` field
- [ ] Add `processing_notes` for any issues

### 12. Output Enhancements
- [ ] Create separate index files:
  - [ ] Citation index (citation -> law dict)
  - [ ] Topic index (topic -> list of laws)
  - [ ] Date index (date -> laws modified)
  - [ ] Cross-reference map
- [ ] Add statistics output:
  - [ ] Total laws by status
  - [ ] Laws by title
  - [ ] Amendment frequency

## Data Quality Improvements

### 13. Validation
- [ ] Validate all citations follow proper format
- [ ] Check for orphaned references
- [ ] Verify hierarchy consistency
- [ ] Ensure required fields are present

### 14. Error Handling
- [ ] Add graceful handling for missing elements
- [ ] Log parsing errors with context
- [ ] Create error report for manual review
- [ ] Add retry logic for temporary failures

## Example Enhanced Dictionary Structure

```python
{
    # Core identification
    "citation": "5 U.S.C. § 1201",
    "law_title": "Appointment of judges",
    "law_number": "1201",
    "status": "operational",
    
    # Full text
    "text_of_law": "...",
    "text_hash": "sha256_hash_here",
    
    # Complete hierarchy
    "law_hierarchy": {
        "title": {"number": 5, "name": "Government Organization and Employees"},
        "chapter": {"number": "12", "title": "Merit Systems Protection Board"},
        "subchapter": {"number": "I", "title": "General"},
        "section": "1201"
    },
    "parent_citation": "5 U.S.C. Ch. 12",
    
    # Temporal tracking
    "temporal_info": {
        "created_date": "1978-10-13",
        "effective_date": "1979-01-11",
        "last_amended": "2022-12-27",
        "start_period": "2022-12-27",
        "end_period": None
    },
    
    # Legislative history
    "legislative_source": {
        "original_act": "Civil Service Reform Act of 1978",
        "original_public_law": "Pub. L. 95-454",
        "original_date": "1978-10-13",
        "codification_date": "1979-01-11"
    },
    
    "amendment_history": [
        {
            "public_law": "Pub. L. 117-286",
            "date": "2022-12-27",
            "statutes_at_large": "136 Stat. 4359",
            "description": "Technical amendment"
        }
    ],
    
    # Relationships
    "related_laws": {
        "cross_references": ["5 U.S.C. § 1202", "5 U.S.C. § 7701"],
        "cites_to": ["5 U.S.C. § 1202"],
        "cited_by": [],  # Populated in post-processing
        "see_also": [],
        "supersedes": [],
        "superseded_by": []
    },
    
    # Additional metadata
    "identifiers": {
        "guid": "ide2a14006-0974-11f0-af24-dd8d6c89485f",
        "identifier": "/us/usc/t5/s1201",
        "temporal_id": "s1201",
        "legacy_id": None
    },
    
    "file_source": "usc05.xml",
    "extraction_date": "2024-01-15T10:30:00",
    "parser_version": "2.0.0",
    "is_positive_law": True,
    "has_subsections": True,
    "subsection_count": 5,
    "notes": [...],
    "validation_status": "valid"
}
```

## Priority Order

1. **High Priority** (Core functionality):
   - Temporal tracking fields
   - Complete hierarchy extraction
   - Amendment history parsing
   - Enhanced cross-references

2. **Medium Priority** (Improves usability):
   - Two-pass processing
   - Citation index generation
   - Change tracking
   - Validation system

3. **Low Priority** (Nice to have):
   - Version comparison
   - Statistical reports
   - Topic indexing
   - Error reporting dashboard