#!/usr/bin/env python3
"""
Example of using usc_parser as a library with all enhanced features.
"""

import json
import usc_parser

# Ensure XML data exists (will offer to download if not present)
usc_parser.ensure_xml_data_exists()

# Example 1: Parse a single title and examine enhanced metadata
print("Example 1: Parse Title 5 and examine comprehensive law structure")
print("-" * 50)

laws = usc_parser.parse_single_title('xml_uscAll@119-12/usc05.xml', 5, True)
if laws:
    # Find a law with amendments to showcase all features
    example_law = next((law for law in laws if law['amendment_history']), laws[0])
    
    print(f"Citation: {example_law['citation']}")
    print(f"Title: {example_law['law_title']}")
    print(f"Status: {example_law['status']}")
    print(f"Parent Citation: {example_law['parent_citation']}")
    
    # Show hierarchy
    print("\nHierarchy:")
    h = example_law['law_hierarchy']
    print(f"  Title {h['title']['number']}: {h['title']['name']}")
    if h.get('chapter'):
        print(f"  {h['chapter']['number']} {h['chapter']['name']}")
    if h.get('section'):
        print(f"  Section {h['section']['number']}: {h['section']['name']}")
    
    # Show identifiers
    print("\nIdentifiers:")
    print(f"  GUID: {example_law['identifiers']['guid']}")
    print(f"  Path: {example_law['identifiers']['identifier']}")
    print(f"  Hash: {example_law['identifiers']['text_hash'][:32]}...")
    
    # Show source credit
    print("\nSource Credit:")
    sc = example_law['source_credit']
    if sc['original_public_law']:
        print(f"  Original Law: {sc['original_public_law']} ({sc['original_date']})")
        print(f"  Statutes: {sc['original_statutes']}")
    
    # Show amendments
    if example_law['amendment_history']:
        print(f"\nAmendments ({len(example_law['amendment_history'])}):")
        for amend in example_law['amendment_history'][:3]:
            print(f"  {amend['year']}: {amend['public_law']} - {amend['date']}")

# Example 2: Find all laws with a specific status
print("\n\nExample 2: Find repealed laws")
print("-" * 50)

repealed_laws = [law for law in laws if law['status'] == 'repealed']
print(f"Found {len(repealed_laws)} repealed laws")
if repealed_laws:
    print(f"First repealed law: {repealed_laws[0]['citation']} - {repealed_laws[0]['law_title']}")

# Example 3: Search for laws by text content
print("\n\nExample 3: Search for laws mentioning 'Secretary'")
print("-" * 50)

secretary_laws = [law for law in laws if 'Secretary' in law['text_of_law']]
print(f"Found {len(secretary_laws)} laws mentioning 'Secretary'")
for law in secretary_laws[:3]:
    print(f"  - {law['citation']}: {law['law_title']}")

# Example 4: Find laws with subsections
print("\n\nExample 4: Laws with subsections")
print("-" * 50)

laws_with_subsections = [law for law in laws if law['has_subsections']]
print(f"Found {len(laws_with_subsections)} laws with subsections")
# Show the law with the most subsections
most_subsections = max(laws_with_subsections, key=lambda x: x['subsection_count'])
print(f"Most subsections: {most_subsections['citation']} has {most_subsections['subsection_count']} subsections")

# Example 5: Analyze cross-references
print("\n\nExample 5: Most cross-referenced laws")
print("-" * 50)

from collections import Counter
all_refs = []
for law in laws:
    all_refs.extend(law['related_laws']['cross_references'])

ref_counts = Counter(all_refs)
print("Top 5 most referenced sections:")
for ref, count in ref_counts.most_common(5):
    print(f"  {ref}: referenced {count} times")

# Example 6: Export sample to JSON
print("\n\nExample 6: Export sample data")
print("-" * 50)

# Save a sample of 5 laws with all metadata
sample_laws = laws[:5]
with open('sample_laws.json', 'w') as f:
    json.dump(sample_laws, f, indent=2)
print(f"Exported {len(sample_laws)} laws to sample_laws.json")
print("Use this file to explore the complete data structure")