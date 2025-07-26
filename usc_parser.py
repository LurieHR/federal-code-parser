#!/usr/bin/env python3
"""
USC XML Parser Library

Parses United States Code XML files to extract individual laws into structured dictionaries.

Usage as a library:
    import usc_parser
    
    # Parse a single title
    laws = usc_parser.parse_single_title('xml_uscAll@119-12/usc05.xml', 5, True)
    
    # Parse all titles
    all_laws = usc_parser.parse_all_titles('xml_uscAll@119-12')
    
    # Access individual law data
    for law in laws:
        print(law['citation'])
        print(law['law_title'])
        print(law['text_of_law'])
        print(law['related_laws'])

Usage from command line:
    python usc_parser.py                    # Parse Title 5 as test
    python usc_parser.py --title 18         # Parse specific title
    python usc_parser.py --all              # Parse all titles
    python usc_parser.py --help             # Show all options
"""

try:
    from lxml import etree as ET
except ImportError:
    import xml.etree.ElementTree as ET
    print("Warning: lxml not available, hierarchy extraction will be limited")
import os
import json
import re
import hashlib
import zipfile
import urllib.request
import socket
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict


NAMESPACE = {
    'uslm': 'http://xml.house.gov/schemas/uslm/1.0',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/'
}
USC_XML_URL = "https://uscode.house.gov/download/releasepoints/us/pl/119/12/xml_uscAll@119-12.zip"
DEFAULT_XML_DIR = "xml_uscAll@119-12"


def ensure_xml_data_exists(xml_dir: str = DEFAULT_XML_DIR) -> bool:
    """
    Check if XML data directory exists, offer to download if not.
    
    Args:
        xml_dir: Directory to check for XML files
        
    Returns:
        True if directory exists or was successfully downloaded, False otherwise
    """
    if os.path.exists(xml_dir) and os.path.isdir(xml_dir):
        # Check if it contains XML files
        xml_files = [f for f in os.listdir(xml_dir) if f.endswith('.xml')]
        if xml_files:
            return True
        else:
            print(f"Directory {xml_dir} exists but contains no XML files.")
    
    print(f"USC XML data not found at '{xml_dir}'.")
    print(f"Would you like to download it from {USC_XML_URL}?")
    print("This will download approximately 250MB of data.")
    
    response = input("Download now? (y/n): ").strip().lower()
    if response != 'y':
        print("Download cancelled. Please download the XML files manually.")
        return False
    
    # Download the file
    zip_filename = "usc_xml_temp.zip"
    print(f"Downloading USC XML data...")
    
    try:
        # Download with progress indicator
        def download_progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            percent = min(100, (downloaded / total_size) * 100)
            print(f"\rProgress: {percent:.1f}%", end='', flush=True)
        
        urllib.request.urlretrieve(USC_XML_URL, zip_filename, reporthook=download_progress)
        print("\nDownload complete.")
        
        # Extract the zip file
        print("Extracting XML files...")
        with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
            zip_ref.extractall('.')
        
        # Clean up zip file
        os.remove(zip_filename)
        print(f"Extraction complete. XML files are now available in '{xml_dir}'.")
        
        return True
        
    except Exception as e:
        print(f"\nError downloading or extracting files: {e}")
        # Clean up partial download
        if os.path.exists(zip_filename):
            os.remove(zip_filename)
        return False


def parse_usc_file(filepath: str) -> ET.Element:
    """
    Load and parse a USC XML file.
    
    Args:
        filepath: Path to the USC XML file
        
    Returns:
        Root element of the parsed XML document
    """
    tree = ET.parse(filepath)
    return tree.getroot()


def helper_find_all_tags(element: ET.Element, tags_counter: Dict[str, int] = None) -> Dict[str, int]:
    """
    Recursively find all unique tags in the document.
    
    Args:
        element: XML element to process
        tags_counter: Dictionary to count tags (created if None)
        
    Returns:
        Dictionary with tag names as keys and counts as values
    """
    if tags_counter is None:
        tags_counter = {}
    
    # Get tag without namespace
    tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
    tags_counter[tag] = tags_counter.get(tag, 0) + 1
    
    # Recurse through children
    for child in element:
        helper_find_all_tags(child, tags_counter)
    
    return tags_counter


def get_element_text_content(element: ET.Element) -> str:
    """
    Extract all text content from an element, similar to get_section_text.
    
    Args:
        element: XML element
        
    Returns:
        Complete text content of the element
    """
    text_parts = []
    
    def extract_text_recursive(elem):
        if elem.text:
            text_parts.append(elem.text.strip())
        for child in elem:
            # Skip certain metadata elements
            if not child.tag.endswith(('sourceCredit', 'meta')):
                extract_text_recursive(child)
            if child.tail:
                text_parts.append(child.tail.strip())
    
    extract_text_recursive(element)
    return ' '.join(text_parts)


def traverse_with_ancestor_paths(element: ET.Element, current_path: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Traverse document and extract ALL elements with their complete ancestor paths.
    
    Args:
        element: XML element to process
        current_path: Current ancestor path (list of ancestor info)
        
    Returns:
        List of all element data with ancestor paths
    """
    if current_path is None:
        current_path = []
    
    results = []
    
    # Get element tag without namespace
    tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
    
    # Define hierarchical structural elements that should be part of the path
    hierarchical_tags = {
        'title', 'subtitle', 'part', 'subpart', 'division', 'subdivision',
        'chapter', 'subchapter', 'article', 'appendix'
    }
    
    # Get basic element info
    num_elem = element.find('./uslm:num', NAMESPACE)
    num = num_elem.text.strip() if num_elem is not None and num_elem.text else ''
    
    heading_elem = element.find('./uslm:heading', NAMESPACE)
    heading = heading_elem.text.strip() if heading_elem is not None and heading_elem.text else ''
    
    # Get text content and length
    text_content = get_element_text_content(element)
    content_length = len(text_content)
    
    # Build element info with ALL attributes preserved
    element_info = {
        'tag': tag,
        'num': num,
        'heading': heading,
        'attributes': extract_all_element_attributes(element)
    }
    
    # If this is a hierarchical element, add it to the path and continue
    if tag in hierarchical_tags:
        new_path = current_path + [element_info]
        
        # Continue traversing with the extended path
        for child in element:
            results.extend(traverse_with_ancestor_paths(child, new_path))
    
    # For ALL elements (including hierarchical ones), extract them as content items
    # Only extract if they have some text content or are leaf nodes
    if content_length > 0 or len(list(element)) == 0:
        results.append({
            'content_element': element,
            'element_info': element_info,
            'ancestor_path': current_path,  # Everything above this element
            'full_path': current_path + [element_info],  # Including the element
            'text_content': text_content
        })
    
    # If not hierarchical, still traverse children
    if tag not in hierarchical_tags:
        for child in element:
            results.extend(traverse_with_ancestor_paths(child, current_path))
    
    return results




def get_section_text(section: ET.Element) -> str:
    """
    Extract all text content from a section element.
    
    Args:
        section: Section element
        
    Returns:
        Complete text content of the section
    """
    text_parts = []
    
    # Function to recursively extract text from an element
    def extract_text(elem):
        if elem.text:
            text_parts.append(elem.text.strip())
        for child in elem:
            # Skip certain elements like sourceCredit and notes
            if child.tag.endswith(('sourceCredit', 'notes')):
                continue
            extract_text(child)
            if child.tail:
                text_parts.append(child.tail.strip())
    
    # Extract text from content elements
    content_elems = section.findall('.//uslm:content', NAMESPACE)
    for content in content_elems:
        extract_text(content)
    
    # Also check for chapeau and continuation elements
    chapeau = section.find('.//uslm:chapeau', NAMESPACE)
    if chapeau is not None:
        extract_text(chapeau)
        
    continuation = section.find('.//uslm:continuation', NAMESPACE)
    if continuation is not None:
        extract_text(continuation)
    
    return ' '.join(text_parts)


def get_cross_references(section: ET.Element) -> List[str]:
    """
    Find all cross-references in a section.
    
    Args:
        section: Section element
        
    Returns:
        List of cross-reference citations
    """
    references = []
    ref_elements = section.findall('.//uslm:ref', NAMESPACE)
    
    for ref in ref_elements:
        # Get the href attribute which contains the reference
        href = ref.get('href')
        if href:
            # Convert href to citation format
            # Example: /us/usc/t5/s1202 -> 5 U.S.C. § 1202
            match = re.match(r'/us/usc/t(\d+)/s(\d+)', href)
            if match:
                title, section_num = match.groups()
                citation = f"{title} U.S.C. § {section_num}"
                references.append(citation)
    
    return list(set(references))  # Remove duplicates


def get_section_status(section: ET.Element) -> str:
    """
    Determine the status of a section.
    
    Args:
        section: Section element
        
    Returns:
        Status string (operational, repealed, vacant, reserved)
    """
    # Check for status attribute
    status = section.get('status')
    if status:
        return status
    
    # Check heading for common indicators
    heading = section.find('.//uslm:heading', NAMESPACE)
    if heading is not None and heading.text:
        heading_text = heading.text.lower()
        if 'repealed' in heading_text:
            return 'repealed'
        elif 'reserved' in heading_text:
            return 'reserved'
    
    # Default to operational
    return 'operational'


def extract_notes_structure(element: ET.Element) -> Dict[str, Any]:
    """
    Extract structured notes from an element.
    
    Args:
        element: XML element
        
    Returns:
        Dictionary with structured notes information
    """
    notes_structure = {}
    
    # Find notes container
    notes_container = element.find('.//uslm:notes', NAMESPACE)
    if notes_container is not None:
        notes_structure['attributes'] = extract_all_element_attributes(notes_container)
        notes_structure['topics'] = {}
        
        # Extract each note by topic
        note_elements = notes_container.findall('./uslm:note', NAMESPACE)
        for note in note_elements:
            topic = note.get('topic', 'unknown')
            role = note.get('role', '')
            
            note_data = {
                'attributes': extract_all_element_attributes(note),
                'content': ''.join(note.itertext()).strip()
            }
            
            # Extract heading if present
            heading_elem = note.find('./uslm:heading', NAMESPACE)
            if heading_elem is not None:
                note_data['heading'] = {
                    'text': heading_elem.text.strip() if heading_elem.text else '',
                    'attributes': extract_all_element_attributes(heading_elem)
                }
            
            # Group by topic, handle multiple notes with same topic
            if topic not in notes_structure['topics']:
                notes_structure['topics'][topic] = []
            notes_structure['topics'][topic].append(note_data)
    
    return notes_structure




def extract_amendment_history(section: ET.Element) -> List[Dict[str, str]]:
    """
    Extract all amendments with dates and public law references.
    
    Args:
        section: Section element
        
    Returns:
        List of dictionaries with amendment information
    """
    amendments = []
    
    # First, extract all source credit info with dates
    source_dates = {}
    source_credit = section.find('.//uslm:sourceCredit', NAMESPACE)
    if source_credit is not None:
        # Parse the source credit text to match Public Laws with dates
        source_text = ''.join(source_credit.itertext())
        
        # Find all ref elements and following date elements
        refs = source_credit.findall('.//uslm:ref', NAMESPACE)
        dates = source_credit.findall('.//uslm:date', NAMESPACE)
        
        # Create a map of public law to date
        for i, ref in enumerate(refs):
            href = ref.get('href', '')
            if '/pl/' in href:
                pl_match = re.search(r'/pl/(\d+)/(\d+)', href)
                if pl_match:
                    pl_num = f"{pl_match.group(1)}-{pl_match.group(2)}"
                    # Find the next date element after this ref
                    ref_text = ref.text or ''
                    for date in dates:
                        date_text = date.text or ''
                        # Check if this date follows this public law in the text
                        if pl_num in source_text and date.get('date'):
                            idx_pl = source_text.find(f"Pub. L. {pl_num}")
                            idx_date = source_text.find(date_text)
                            if idx_pl >= 0 and idx_date > idx_pl:
                                source_dates[pl_num] = date.get('date')
                                break
    
    # Now extract amendment info from notes
    notes_section = section.find('.//uslm:notes', NAMESPACE)
    if notes_section is not None:
        # Find amendment notes
        amendment_notes = notes_section.findall('.//uslm:note[@topic="amendments"]', NAMESPACE)
        for note in amendment_notes:
            # Get all paragraph elements within the note
            paragraphs = note.findall('.//uslm:p', NAMESPACE)
            for p in paragraphs:
                p_text = ''.join(p.itertext())
                
                # Match pattern like "2022—Pub. L. 117–286..."
                year_match = re.match(r'^(\d{4})—', p_text)
                if year_match:
                    amendment = {
                        'year': year_match.group(1),
                        'text': p_text.strip(),
                        'date': None,
                        'public_law': None,
                        'statutes_at_large': None
                    }
                    
                    # Extract Public Law
                    pl_match = re.search(r'Pub\. L\. ([\d–-]+)', p_text)
                    if pl_match:
                        amendment['public_law'] = f"Pub. L. {pl_match.group(1)}"
                        # Try to find date from source_dates
                        pl_num = pl_match.group(1)
                        if pl_num in source_dates:
                            amendment['date'] = source_dates[pl_num]
                    
                    # Extract Statutes at Large
                    stat_match = re.search(r'(\d+\s+Stat\.\s+\d+)', p_text)
                    if stat_match:
                        amendment['statutes_at_large'] = stat_match.group(1)
                    
                    amendments.append(amendment)
    
    return amendments

def calculate_text_hash(text: str) -> str:
    """
    Calculate SHA256 hash of law text for change detection.
    
    Args:
        text: Law text to hash
        
    Returns:
        SHA256 hash as hex string
    """
    # Normalize text by removing extra whitespace and converting to lowercase
    # This helps detect meaningful changes while ignoring formatting differences
    normalized_text = ' '.join(text.split()).lower()
    return hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()




def build_parent_citation(hierarchy: Dict[str, Any], title_number: int) -> Optional[str]:
    """
    Build citation for the parent container of a section.
    
    Args:
        hierarchy: Hierarchy dictionary
        title_number: USC title number
        
    Returns:
        Parent citation string or None
    """
    # Check from most specific to least specific parent
    if hierarchy.get('subpart'):
        parent_type = "Subpart"
        parent_num = hierarchy['subpart'].get('number', '')
    elif hierarchy.get('part'):
        parent_type = "Part"
        parent_num = hierarchy['part'].get('number', '')
    elif hierarchy.get('subchapter'):
        parent_type = "Subch."
        parent_num = hierarchy['subchapter'].get('number', '')
    elif hierarchy.get('chapter'):
        parent_type = "Ch."
        parent_num = hierarchy['chapter'].get('number', '')
    elif hierarchy.get('subtitle'):
        parent_type = "Subtitle"
        parent_num = hierarchy['subtitle'].get('number', '')
    else:
        # Parent is the title itself
        return f"{title_number} U.S.C."
    
    # Clean up the parent number (remove "CHAPTER", "PART", etc.)
    parent_num = re.sub(r'^(CHAPTER|SUBCHAPTER|PART|SUBPART|SUBTITLE)\s*', '', parent_num, flags=re.IGNORECASE)
    parent_num = parent_num.strip('—- ')
    
    return f"{title_number} U.S.C. {parent_type} {parent_num}"


def count_subsections(section: ET.Element) -> Dict[str, Any]:
    """
    Count and analyze subsections within a section.
    
    Args:
        section: Section element
        
    Returns:
        Dictionary with subsection information
    """
    subsection_info = {
        'has_subsections': False,
        'subsection_count': 0,
        'subsection_levels': []
    }
    
    # Look for paragraph elements (subsections)
    paragraphs = section.findall('.//uslm:paragraph', NAMESPACE)
    if paragraphs:
        subsection_info['has_subsections'] = True
        subsection_info['subsection_count'] = len(paragraphs)
        
        # Get the subsection identifiers
        for para in paragraphs:
            num_elem = para.find('./uslm:num', NAMESPACE)
            if num_elem is not None and num_elem.text:
                subsection_info['subsection_levels'].append(num_elem.text.strip())
    
    # Also check for subsections that might be marked as subsection elements
    subsections = section.findall('.//uslm:subsection', NAMESPACE)
    if subsections:
        subsection_info['has_subsections'] = True
        subsection_info['subsection_count'] += len(subsections)
        
        for subsec in subsections:
            num_elem = subsec.find('./uslm:num', NAMESPACE)
            if num_elem is not None and num_elem.text:
                subsection_info['subsection_levels'].append(num_elem.text.strip())
    
    return subsection_info


def get_law_hierarchy(section: ET.Element, title_str: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the complete hierarchical structure for a section.
    
    Args:
        section: Section element
        title_number: USC title number
        doc_root: Root document element for title info
        
    Returns:
        Dictionary with complete hierarchy information
    """
    hierarchy = {
        'title': {
            'number': title_number,
            'name': None
        },
        'subtitle': None,
        'chapter': None,
        'subchapter': None,
        'part': None,
        'subpart': None,
        'section': {
            'number': None,
            'name': None
        }
    }
    
    # Get title name from document root
    if doc_root is not None:
        title_elem = doc_root.find('.//uslm:title', NAMESPACE)
        if title_elem is not None:
            heading = title_elem.find('.//uslm:heading', NAMESPACE)
            if heading is not None and heading.text:
                hierarchy['title']['name'] = heading.text.strip()
    
    # Get section number from the section element
    num_elem = section.find('.//uslm:num', NAMESPACE)
    if num_elem is not None and num_elem.text:
        # Extract just the number (e.g., "§ 1201." -> "1201")
        section_match = re.search(r'§?\s*(\d+[a-zA-Z]?)', num_elem.text)
        if section_match:
            hierarchy['section']['number'] = section_match.group(1)
    
    # Get section heading
    heading_elem = section.find('.//uslm:heading', NAMESPACE)
    if heading_elem is not None and heading_elem.text:
        hierarchy['section']['name'] = heading_elem.text.strip()
    
    # Try to find parent elements if lxml is available
    if hasattr(section, 'getparent'):
        parent = section.getparent()
        while parent is not None:
            tag = parent.tag.split('}')[-1] if '}' in parent.tag else parent.tag
            
            if tag == 'title':
                # Already handled above
                pass
                
            elif tag == 'subtitle':
                subtitle_info = {}
                num = parent.find('./uslm:num', NAMESPACE)
                heading = parent.find('./uslm:heading', NAMESPACE)
                if num is not None and num.text:
                    subtitle_info['number'] = num.text.strip()
                if heading is not None and heading.text:
                    subtitle_info['name'] = heading.text.strip()
                if subtitle_info:
                    hierarchy['subtitle'] = subtitle_info
                    
            elif tag == 'chapter':
                chapter_info = {}
                num = parent.find('./uslm:num', NAMESPACE)
                heading = parent.find('./uslm:heading', NAMESPACE)
                if num is not None and num.text:
                    chapter_info['number'] = num.text.strip()
                if heading is not None and heading.text:
                    chapter_info['name'] = heading.text.strip()
                if chapter_info:
                    hierarchy['chapter'] = chapter_info
                    
            elif tag == 'subchapter':
                subchapter_info = {}
                num = parent.find('./uslm:num', NAMESPACE)
                heading = parent.find('./uslm:heading', NAMESPACE)
                if num is not None and num.text:
                    subchapter_info['number'] = num.text.strip()
                if heading is not None and heading.text:
                    subchapter_info['name'] = heading.text.strip()
                if subchapter_info:
                    hierarchy['subchapter'] = subchapter_info
                    
            elif tag == 'part':
                part_info = {}
                num = parent.find('./uslm:num', NAMESPACE)
                heading = parent.find('./uslm:heading', NAMESPACE)
                if num is not None and num.text:
                    part_info['number'] = num.text.strip()
                if heading is not None and heading.text:
                    part_info['name'] = heading.text.strip()
                if part_info:
                    hierarchy['part'] = part_info
                    
            elif tag == 'subpart':
                subpart_info = {}
                num = parent.find('./uslm:num', NAMESPACE)
                heading = parent.find('./uslm:heading', NAMESPACE)
                if num is not None and num.text:
                    subpart_info['number'] = num.text.strip()
                if heading is not None and heading.text:
                    subpart_info['name'] = heading.text.strip()
                if subpart_info:
                    hierarchy['subpart'] = subpart_info
            
            parent = parent.getparent()
    
    return hierarchy


def get_related_laws(section: ET.Element) -> Dict[str, List[str]]:
    """
    Extract all types of related laws and references.
    
    Args:
        section: Section element
        
    Returns:
        Dictionary with different types of related laws
    """
    related = {
        'cross_references': [],
        'executive_orders': [],
        'public_laws': [],
        'statutes_at_large': []
    }
    
    # Cross-references from ref elements
    ref_elements = section.findall('.//uslm:ref', NAMESPACE)
    for ref in ref_elements:
        href = ref.get('href')
        if href:
            # Convert href to citation format
            match = re.match(r'/us/usc/t(\d+)/s(\d+[a-zA-Z]*)', href)
            if match:
                title, section_num = match.groups()
                citation = f"{title} U.S.C. § {section_num}"
                related['cross_references'].append(citation)
    
    # Extract from notes
    notes_section = section.find('.//uslm:notes', NAMESPACE)
    if notes_section is not None:
        note_text = ''.join(notes_section.itertext())
        
        # Find Public Law references
        pl_matches = re.findall(r'Pub\. L\. \d+[-–]\d+', note_text)
        related['public_laws'].extend(pl_matches)
        
        # Find Statutes at Large references
        stat_matches = re.findall(r'\d+ Stat\. \d+', note_text)
        related['statutes_at_large'].extend(stat_matches)
        
        # Find Executive Order references
        eo_matches = re.findall(r'Ex\. Ord\. No\. \d+', note_text)
        related['executive_orders'].extend(eo_matches)
    
    # Remove duplicates
    for key in related:
        related[key] = list(set(related[key]))
    
    return related


def build_law_dict(section: ET.Element, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert a section element to a comprehensive dictionary.
    
    Args:
        section: Section element
        filename: Source filename (e.g., 'usc50A.xml')
        metadata: Document-level metadata dictionary
        
    Returns:
        Dictionary with law information or None if section should be skipped
    """
    # Get section status
    status = get_section_status(section)
    
    # Include all sections, not just operational ones
    
    # Get section number
    num_elem = section.find('.//uslm:num', NAMESPACE)
    if num_elem is None:
        return None
        
    section_num_text = num_elem.text or ''
    # Extract just the number (e.g., "§ 1201." -> "1201")
    section_match = re.search(r'§?\s*(\d+[a-zA-Z]?)', section_num_text)
    if not section_match:
        return None
    section_number = section_match.group(1)
    
    # Get heading
    heading_elem = section.find('.//uslm:heading', NAMESPACE)
    heading = heading_elem.text.strip() if heading_elem is not None and heading_elem.text else ''
    
    # Get section text
    text = get_section_text(section)
    
    # Get hierarchy
    hierarchy = get_law_hierarchy(section, title_number, doc_root)
    
    # Get parent citation
    parent_citation = build_parent_citation(hierarchy, title_number)
    
    # Get subsection information
    subsection_info = count_subsections(section)
    
    # Get related laws
    related_laws = get_related_laws(section)
    
    # Get notes
    notes = extract_notes(section)
    
    # Get all identifiers
    identifiers = {
        'guid': section.get('id'),  # GUID from @id attribute
        'identifier': section.get('identifier', ''),  # URL path
        'temporal_id': section.get('temporalId'),  # Temporal ID
        'name': section.get('name'),  # Legacy name
        'text_hash': calculate_text_hash(text)  # SHA256 of normalized text
    }
    
    # Get style attribute
    style = section.get('style', '')
    
    # Build citation
    citation = build_citation(str(title_number), section_number)
    
    # Get temporal information
    created_date = section.get('createdDate')
    effective_date = section.get('effectiveDate')
    start_period = section.get('startPeriod')
    end_period = section.get('endPeriod')
    
    # Get XML creation date from document metadata
    xml_creation_date_olrc = None
    if doc_root is not None:
        meta = doc_root.find('.//uslm:meta', NAMESPACE)
        if meta is not None:
            # Look for dcterms:created
            for elem in meta:
                if elem.tag.endswith('created'):
                    xml_creation_date_olrc = elem.text
                    break
    
    # Get amendment history
    amendment_history = extract_amendment_history(section)
    
    # Get source credit information
    source_credit = extract_source_credit(section)
    
    return {
        # Section identification (from section element attributes and children)
        "law_number": section_number,
        "law_title": heading,
        "citation": citation,
        "identifiers": identifiers,
        "status": status,
        
        # Hierarchy (from parent elements)
        "title_number": title_number,
        "is_positive_law": is_positive_law,
        "law_hierarchy": hierarchy,
        "parent_citation": parent_citation,
        
        # Content (from section content elements)
        "text_of_law": text,
        "has_subsections": subsection_info['has_subsections'],
        "subsection_count": subsection_info['subsection_count'],
        
        # Notes and history (from notes elements)
        "notes": notes,
        "amendment_history": amendment_history,
        
        # Source credit (from sourceCredit element)
        "source_credit": source_credit,
        
        # References (from ref elements throughout)
        "related_laws": related_laws,
        
        # Temporal attributes (from section and document metadata)
        "created_date": created_date,
        "effective_date": effective_date,
        "start_period": start_period,
        "end_period": end_period,
        
        # Document metadata
        "file_source": filename,
        "XML_creation_date_OLRC": xml_creation_date_olrc,
        "style": style
    }


def extract_meta(doc: ET.Element) -> Dict[str, Any]:
    """
    Extract all metadata from the USC XML document.
    
    Args:
        doc: Root element of the USC XML document
        
    Returns:
        Dictionary containing all metadata fields
    """
    metadata = {}
    meta_elem = doc.find('.//uslm:meta', NAMESPACE)
    
    if meta_elem is not None:
        # Extract Dublin Core metadata
        dc_title = meta_elem.find('.//dc:title', NAMESPACE)
        if dc_title is not None and dc_title.text:
            metadata['dc:title'] = dc_title.text
            
        dc_type = meta_elem.find('.//dc:type', NAMESPACE)
        if dc_type is not None and dc_type.text:
            metadata['dc:type'] = dc_type.text
            
        dc_publisher = meta_elem.find('.//dc:publisher', NAMESPACE)
        if dc_publisher is not None and dc_publisher.text:
            metadata['dc:publisher'] = dc_publisher.text
            
        dc_creator = meta_elem.find('.//dc:creator', NAMESPACE)
        if dc_creator is not None and dc_creator.text:
            metadata['dc:creator'] = dc_creator.text
            
        dcterms_created = meta_elem.find('.//dcterms:created', NAMESPACE)
        if dcterms_created is not None and dcterms_created.text:
            metadata['dcterms:created'] = dcterms_created.text
            
        # Extract USLM-specific metadata
        doc_number = meta_elem.find('.//uslm:docNumber', NAMESPACE)
        if doc_number is not None and doc_number.text:
            metadata['docNumber'] = doc_number.text
            
        doc_pub_name = meta_elem.find('.//uslm:docPublicationName', NAMESPACE)
        if doc_pub_name is not None and doc_pub_name.text:
            metadata['docPublicationName'] = doc_pub_name.text
            
        # Extract properties
        properties = meta_elem.findall('.//uslm:property', NAMESPACE)
        for prop in properties:
            role = prop.get('role')
            if role and prop.text:
                metadata[f'property[@role="{role}"]'] = prop.text
                
    return metadata


def extract_all_element_attributes(element: ET.Element) -> Dict[str, Any]:
    """
    Extract all attributes from an XML element preserving original names.
    
    Args:
        element: XML element
        
    Returns:  
        Dictionary with all element attributes
    """
    return dict(element.attrib)


def build_hierarchy_from_path(full_path: List[Dict[str, Any]], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build hierarchy dictionary from ancestor path.
    
    Args:
        full_path: Complete path including section (from traverse_with_ancestor_paths)
        metadata: Document-level metadata
        
    Returns:
        Hierarchy dictionary with all available levels
    """
    hierarchy = {
        'title': None,
        'subtitle': None, 
        'part': None,
        'subpart': None,
        'division': None,
        'subdivision': None,
        'chapter': None,
        'subchapter': None,
        'article': None,
        'appendix': None,
        'section': None
    }
    
    # Process each element in the path
    for path_element in full_path:
        tag = path_element['tag']
        if tag in hierarchy:
            # Extract all available info including all attributes
            element_info = {
                'num': path_element['num'],
                'heading': path_element['heading'],
                'attributes': path_element.get('attributes', {})
            }
            # Remove empty values to keep clean
            element_info = {k: v for k, v in element_info.items() if v}
            hierarchy[tag] = element_info
    
    # Add title info from metadata if available
    if hierarchy['title'] is None and metadata.get('dc:title'):
        title_text = metadata['dc:title']
        # Extract title number and name
        title_match = re.match(r'Title (\d+[A-Za-z]*)\s*[-—]\s*(.*)', title_text)
        if title_match:
            hierarchy['title'] = {
                'num': title_match.group(1),
                'heading': title_match.group(2)
            }
    
    return hierarchy






def build_law_dict_with_path(element_data: Dict[str, Any], filename: str, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert element data with ancestor paths to a comprehensive dictionary.
    
    Args:
        element_data: Element data with ancestor paths from traverse_with_ancestor_paths()
        filename: Source filename (e.g., 'usc50A.xml')
        metadata: Document-level metadata dictionary
        
    Returns:
        Dictionary with law information or None if element should be skipped
    """
    element = element_data['content_element']
    element_info = element_data['element_info']
    ancestor_path = element_data['ancestor_path']
    full_path = element_data['full_path']
    text_content = element_data['text_content']
    
    # Get element status (use general status function)
    status = element.get('status', 'operational')
    
    # Get element number and heading
    element_number = element_info['num']
    heading = element_info['heading']
    
    
    
    
    # Extract structured notes for all elements
    notes_structure = extract_notes_structure(element)
    
    # Get additional information only for section elements
    if element_info['tag'] == 'section':
        subsection_info = count_subsections(element)
        related_laws = get_related_laws(element)
        amendment_history = extract_amendment_history(element)
    
    # Get element attributes
    element_attributes = element_info.get('attributes', {})
    
    
    # Determine if positive law (simplified logic for now)
    try:
        title_num_int = int(re.match(r'(\d+)', title_number).group(1))
        is_positive_law = title_num_int in {1, 3, 4, 5, 9, 10, 11, 13, 14, 17, 18, 23, 
                                          28, 31, 32, 35, 36, 37, 38, 39, 40, 41, 44, 
                                          46, 49, 51, 52, 54}
    except:
        is_positive_law = False
    
    # Extract actual child elements that exist in the XML
    def extract_element_content(elem):
        """Recursively extract element content preserving document order"""
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # Get element attributes
        attrs = dict(elem.attrib) if elem.attrib else {}
        
        # Get direct text content
        text = elem.text.strip() if elem.text else ''
        
        # Get child elements in document order
        children_in_order = []
        for child in elem:
            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            child_content = extract_element_content(child)
            if child_content:
                children_in_order.append({
                    'tag': child_tag,
                    'content': child_content
                })
        
        # Build result
        result = {}
        if attrs:
            result['attributes'] = attrs
        if text:
            result['text'] = text
        if children_in_order:
            result['children_in_order'] = children_in_order
            
        # For elements with children, also capture the complete text content
        if children_in_order and tag == 'p':
            full_text = ''.join(elem.itertext()).strip()
            if full_text:
                result['paragraph_text'] = full_text
        
        # If element has no attributes, text, or children, return the tail text if any
        if not result and elem.tail and elem.tail.strip():
            return elem.tail.strip()
        
        return result if result else None
    
    child_elements = {}
    for child in element:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        content = extract_element_content(child)
        if content:
            child_elements[tag] = content
    
    # Build ancestors list from top to bottom (furthest to nearest)
    ancestors = []
    for ancestor in ancestor_path:
        tag = ancestor['tag'].capitalize()
        identifier = ancestor.get('attributes', {}).get('identifier', '')
        if identifier:
            ancestors.append(f"{tag}:{identifier}")
    
    
    # List child elements in document order
    def list_child_elements_in_order():
        """List child elements in the order they appear in the document"""
        child_order = []
        for child in element:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            child_order.append(tag)
        return child_order
    
    # Create document-order readable text
    def create_document_order_text():
        """Walk through child elements in order and extract all text"""
        result_parts = []
        tag_order = []
        
        for child in element:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            child_text = ''.join(child.itertext())
            
            result_parts.append(child_text)
            tag_order.append(tag)
        
        return {
            'text': '\n\n'.join(result_parts),
            'tag_order': ' -> '.join(tag_order)
        }
    
    # Build computed fields
    computed_fields = {
        "processing_timestamp": time.time(),
        "processing_machine": socket.gethostname(),
        "content_length": len(text_content),
        "file_source": filename,
        "ancestors": "; ".join(ancestors),
        "child_elements_order": list_child_elements_in_order(),
        "document_order_text": create_document_order_text()
    }
    
    # Add section-specific computed fields only for sections
    if element_info['tag'] == 'section':
        computed_fields.update({
            "has_subsections": subsection_info['has_subsections'],
            "subsection_count": subsection_info['subsection_count'],
            "amendment_history": amendment_history,
            "related_laws": related_laws
        })
    
    # Add hierarchical element own content extraction
    hierarchical_tags = {'title', 'subtitle', 'part', 'subpart', 'division', 'subdivision',
                        'chapter', 'subchapter', 'article', 'appendix'}
    
    if element_info['tag'] in hierarchical_tags:
        own_content_data = extract_own_content_text(element)
        computed_fields.update(own_content_data)

    return {
        # Element info
        "tag": element_info['tag'],
        "attributes": element_attributes,
        
        # Actual child elements from XML
        **child_elements,
        
        # Computed/derived fields (not in original XML)
        "computed": computed_fields,
        
        # Hierarchical context (ancestor path without current element)
        "ancestor_path": ancestor_path,
        
        # Document metadata (from <meta> element)
        "meta": meta
    }


def extract_text_skip_footnote_content(element: ET.Element) -> str:
    """
    Extract text with footnote references inline and footnote content at bottom.
    """
    text_parts = []
    footnotes = []
    
    def collect_text_and_footnotes(elem):
        # Add element's direct text
        if elem.text:
            text_parts.append(elem.text.strip())
        
        # Process children
        for child in elem:
            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            
            if child_tag == 'note' and child.get('type') == 'footnote':
                # Collect footnote content for bottom section
                footnote_text = ''.join(child.itertext()).strip()
                if footnote_text:
                    footnotes.append(footnote_text)
            elif child_tag == 'ref' and 'footnoteRef' in child.get('class', ''):
                # Include footnote reference inline
                if child.text:
                    text_parts.append(f"[{child.text.strip()}]")
            else:
                # Recursively process other children
                collect_text_and_footnotes(child)
            
            # Add tail text
            if child.tail:
                text_parts.append(child.tail.strip())
    
    # Start the collection
    collect_text_and_footnotes(element)
    
    # Combine main text with footnotes at bottom
    main_text = ' '.join(text_parts).strip()
    if footnotes:
        footnote_section = '\n\nFootnotes:\n' + '\n'.join(footnotes)
        return main_text + footnote_section
    else:
        return main_text


def parse_toc(toc_element: ET.Element) -> str:
    """
    Parse table of contents with footnote references inline and all footnotes at bottom.
    """
    lines = []
    all_footnotes = []
    
    # Check for header (like "Sec.")
    header = toc_element.find('.//uslm:header[@role="tocColumnHeader"]', NAMESPACE)
    header_text = ""
    if header is not None:
        header_text = ''.join(header.itertext()).strip()
    
    for item in toc_element.findall('.//uslm:tocItem', NAMESPACE):
        left_col = item.find('.//uslm:column[@class="twoColumnLeft"]', NAMESPACE)  
        right_col = item.find('.//uslm:column[@class="twoColumnRight"]', NAMESPACE)
        
        if left_col is not None and right_col is not None:
            left_text = ''.join(left_col.itertext()).strip()
            
            # Process right column: collect text with references, collect footnotes
            right_text_parts = []
            footnotes_in_this_item = []
            
            def process_right_col(elem):
                if elem.text:
                    right_text_parts.append(elem.text.strip())
                
                for child in elem:
                    child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    
                    if child_tag == 'ref' and 'footnoteRef' in child.get('class', ''):
                        # Add inline reference
                        if child.text:
                            right_text_parts.append(f"[{child.text.strip()}]")
                    elif child_tag == 'note' and child.get('type') == 'footnote':
                        # Collect footnote for bottom section
                        footnote_text = ''.join(child.itertext()).strip()
                        if footnote_text:
                            footnotes_in_this_item.append(footnote_text)
                    else:
                        # Recursively process other elements
                        process_right_col(child)
                    
                    if child.tail:
                        right_text_parts.append(child.tail.strip())
            
            process_right_col(right_col)
            right_text = ' '.join(right_text_parts).strip()
            
            # Add this line to TOC
            if left_text and right_text:
                lines.append(f"{left_text} {right_text}")
            
            # Add footnotes to master list
            all_footnotes.extend(footnotes_in_this_item)
    
    # Build final TOC
    toc_parts = ["Table of Contents:"]
    if header_text:
        toc_parts.append(header_text)
    toc_parts.extend(lines)
    toc_text = "\n".join(toc_parts)
    
    # Add all footnotes at bottom
    if all_footnotes:
        footnote_section = "\n\nFootnotes:\n" + "\n".join(all_footnotes)
        return toc_text + footnote_section
    else:
        return toc_text


def format_element_text(element: ET.Element) -> str:
    """
    Format element text with better spacing and line breaks.
    """
    if element.tag.endswith('num'):
        return element.text.strip() if element.text else ''
    elif element.tag.endswith('heading'):
        return element.text.strip() if element.text else ''
    elif element.tag.endswith('toc'):
        # Use dedicated TOC parser
        return parse_toc(element)
    elif element.tag.endswith('notes'):
        # Format notes section nicely  
        notes_parts = []
        for note in element.findall('.//uslm:note', NAMESPACE):
            topic = note.get('topic', '')
            if topic == 'amendments':
                notes_parts.append("Amendments:")
                for p in note.findall('.//uslm:p', NAMESPACE):
                    p_text = ''.join(p.itertext()).strip()
                    if p_text:
                        notes_parts.append(f"  {p_text}")
            elif topic == 'editorialNotes':
                heading = note.find('.//uslm:heading', NAMESPACE)
                if heading is not None:
                    heading_text = ''.join(heading.itertext()).strip()
                    if heading_text:
                        notes_parts.append(heading_text)
        return "\n".join(notes_parts) if notes_parts else ""
    else:
        # Default: just extract text with some spacing
        return ''.join(element.itertext()).strip()


def extract_own_content_text(element: ET.Element) -> Dict[str, Any]:
    """
    Extract an element's own text content, excluding child sections/subchapters.
    Returns text content and child pointers.
    
    Args:
        element: XML element
        
    Returns:
        Dictionary with own_content_text, child_pointers, etc.
    """
    hierarchical_tags = {'title', 'subtitle', 'part', 'subpart', 'division', 'subdivision',
                        'chapter', 'subchapter', 'article', 'appendix'}
    
    own_content_parts = []
    child_pointers = []
    
    for child in element:
        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        
        # Skip child hierarchical elements and sections - create pointers
        if child_tag in hierarchical_tags or child_tag == 'section':
            child_num_elem = child.find('./uslm:num', NAMESPACE)
            child_num = child_num_elem.text.strip() if child_num_elem is not None and child_num_elem.text else ''
            child_identifier = child.get('identifier', '')
            child_heading_elem = child.find('./uslm:heading', NAMESPACE)
            child_heading = child_heading_elem.text.strip() if child_heading_elem is not None and child_heading_elem.text else ''
            
            child_pointers.append({
                'tag': child_tag,
                'num': child_num,
                'heading': child_heading,
                'identifier': child_identifier
            })
        else:
            # Include this as own content with better formatting
            child_text = format_element_text(child)
            if child_text:
                own_content_parts.append(child_text)
    
    own_content_text = '\n\n'.join(own_content_parts)
    
    return {
        "own_content_text": own_content_text,
        "own_content_length": len(own_content_text),
        "child_pointers": child_pointers,
        "num_children": len(child_pointers)
    }


def extract_hierarchical_own_content(element_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a hierarchical element's own content, excluding child sections/subchapters.
    Returns a dictionary similar to other parsed elements but only with the element's
    direct content (like toc, notes, etc.) and pointers to children.
    
    Args:
        element_data: Element data from traverse_with_ancestor_paths()
        
    Returns:
        Dictionary with element's own content and child pointers
    """
    element = element_data['content_element']
    element_info = element_data['element_info']
    
    tag = element_info['tag']
    
    # Only process hierarchical container elements
    hierarchical_tags = {'title', 'subtitle', 'part', 'subpart', 'division', 'subdivision',
                        'chapter', 'subchapter', 'article', 'appendix'}
    
    if tag not in hierarchical_tags:
        return None
    
    # Define helper function first
    def extract_element_content(elem):
        """Recursively extract element content preserving document order"""
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        attrs = dict(elem.attrib) if elem.attrib else {}
        text = elem.text.strip() if elem.text else ''
        
        children_in_order = []
        for child in elem:
            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            child_content = extract_element_content(child)
            if child_content:
                children_in_order.append({
                    'tag': child_tag,
                    'content': child_content
                })
        
        result = {}
        if attrs:
            result['attributes'] = attrs
        if text:
            result['text'] = text
        if children_in_order:
            result['children_in_order'] = children_in_order
        
        return result if result else None
    
    # Extract own content (skip child hierarchical elements and sections)
    own_child_elements = {}
    child_pointers = []
    
    for child in element:
        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        
        # Skip child hierarchical elements and sections - just create pointers
        if child_tag in hierarchical_tags or child_tag == 'section':
            child_num_elem = child.find('./uslm:num', NAMESPACE)
            child_num = child_num_elem.text.strip() if child_num_elem is not None and child_num_elem.text else ''
            child_identifier = child.get('identifier', '')
            child_heading_elem = child.find('./uslm:heading', NAMESPACE)
            child_heading = child_heading_elem.text.strip() if child_heading_elem is not None and child_heading_elem.text else ''
            
            child_pointers.append({
                'tag': child_tag,
                'num': child_num,
                'heading': child_heading,
                'identifier': child_identifier
            })
        else:
            # Include this as part of the element's own content
            content = extract_element_content(child)
            if content:
                if child_tag in own_child_elements:
                    # Handle multiple children with same tag
                    if not isinstance(own_child_elements[child_tag], list):
                        own_child_elements[child_tag] = [own_child_elements[child_tag]]
                    own_child_elements[child_tag].append(content)
                else:
                    own_child_elements[child_tag] = content
    
    # Extract readable text content (excluding sections/subchapters)
    content_text_parts = []
    for child in element:
        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        
        # Skip child hierarchical elements and sections
        if child_tag not in hierarchical_tags and child_tag != 'section':
            child_text = ''.join(child.itertext()).strip()
            if child_text:
                content_text_parts.append(child_text)
    
    chapter_content_text = '\n\n'.join(content_text_parts)
    
    # Add computed field for child pointers
    computed_fields = {
        "child_pointers": child_pointers,
        "num_children": len(child_pointers),
        "content_text": chapter_content_text,
        "content_length": len(chapter_content_text)
    }
    
    return {
        # Element info
        "tag": element_info['tag'],
        "attributes": element_info.get('attributes', {}),
        
        # Own content (excluding child sections/subchapters)
        **own_child_elements,
        
        # Computed fields
        "computed": computed_fields,
        
        # Context
        "ancestor_path": element_data['ancestor_path'],
        "meta": element_data.get('meta', {})
    }


def parse_single_title(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a single USC title file and extract all laws using ancestor path traversal.
    
    Args:
        filepath: Path to the XML file
        
    Returns:
        List of law dictionaries
    """
    laws = []
    filename = os.path.basename(filepath)
    
    try:
        # Parse the file
        doc = parse_usc_file(filepath)
        
        # Extract meta from the document
        meta = extract_meta(doc)
        
        # Get all elements with their complete ancestor paths
        elements_with_paths = traverse_with_ancestor_paths(doc)
        
        # Convert each element+path to a law dictionary
        for element_data in elements_with_paths:
            law_dict = build_law_dict_with_path(
                element_data=element_data,
                filename=filename,
                meta=meta
            )
            if law_dict:
                laws.append(law_dict)
                
    except Exception as e:
        print(f"Error parsing {filepath}: {str(e)}")
    
    return laws


def parse_all_titles(xml_dir: str) -> List[Dict[str, Any]]:
    """
    Parse all USC title files in a directory.
    
    Args:
        xml_dir: Directory containing USC XML files
        
    Returns:
        List of all law dictionaries
    """
    all_laws = []
    
    # Titles marked as positive law (from the brief)
    positive_law_titles = {1, 3, 4, 5, 9, 10, 11, 13, 14, 17, 18, 23, 
                          28, 31, 32, 35, 36, 37, 38, 39, 40, 41, 44, 
                          46, 49, 51, 52, 54}
    
    # Get all XML files
    xml_files = [f for f in os.listdir(xml_dir) if f.endswith('.xml') and f.startswith('usc')]
    xml_files.sort()
    
    for xml_file in xml_files:
        title_num = get_title_from_filename(xml_file)
        if title_num is None:
            continue
            
        filepath = os.path.join(xml_dir, xml_file)
        is_positive_law = title_num in positive_law_titles
        
        print(f"Parsing {xml_file} (Title {title_num})...")
        laws = parse_single_title(filepath, title_num, is_positive_law)
        all_laws.extend(laws)
        print(f"  Found {len(laws)} operational sections")
    
    return all_laws


def main():
    """Main function for command line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Parse United States Code XML files to extract laws with metadata'
    )
    parser.add_argument(
        '--xml-dir', 
        default='xml_uscAll@119-12',
        help='Directory containing USC XML files (default: xml_uscAll@119-12)'
    )
    parser.add_argument(
        '--title',
        type=int,
        help='Parse only a specific title number (e.g., 5 for Title 5)'
    )
    parser.add_argument(
        '--output',
        help='Output JSON file path (default: output/title{N}_laws.json or output/usc_laws.json)'
    )
    parser.add_argument(
        '--output-dir',
        default='output',
        help='Output directory for JSON files (default: output)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Parse all titles (default: parse only Title 5 as test)'
    )
    
    args = parser.parse_args()
    
    # Check if XML data exists, offer to download if not
    ensure_xml_data_exists(args.xml_dir)
    
    # Create output directory if it doesn't exist
    if not args.output and not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        print(f"Created output directory: {args.output_dir}")
    
    if args.title:
        # Parse specific title
        title_num = args.title
        filename = f"usc{title_num:02d}.xml"
        filepath = os.path.join(args.xml_dir, filename)
        
        if not os.path.exists(filepath):
            print(f"Error: File {filepath} not found")
            return
        
        print(f"Parsing Title {title_num}...")
        laws = parse_single_title(filepath, title_num, True)
        print(f"Found {len(laws)} laws in Title {title_num}")
        
        output_file = args.output or os.path.join(args.output_dir, f"title{title_num}_laws.json")
        
    elif args.all:
        # Parse all titles
        print("Parsing all USC titles...")
        laws = parse_all_titles(args.xml_dir)
        print(f"\nTotal laws extracted: {len(laws)}")
        
        output_file = args.output or os.path.join(args.output_dir, "usc_laws.json")
        
    else:
        # Default: test with Title 5
        print("Testing parser with Title 5...")
        test_file = os.path.join(args.xml_dir, 'usc05.xml')
        
        if not os.path.exists(test_file):
            print(f"Error: Test file {test_file} not found")
            return
            
        laws = parse_single_title(test_file, 5, True)
        print(f"Found {len(laws)} laws in Title 5")
        
        output_file = args.output or os.path.join(args.output_dir, "title5_laws.json")
    
    # Show status breakdown
    status_counts = defaultdict(int)
    for law in laws:
        status_counts[law['status']] += 1
    
    print("\nStatus breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(laws, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='Parse USC XML files')
    parser.add_argument('--title', required=True, help='USC title to parse (e.g., usc05, usc50A)')
    parser.add_argument('--xml-dir', default='xml_uscAll@119-12', help='Directory containing XML files')
    parser.add_argument('--output', help='Output JSON file (optional)')
    parser.add_argument('--type', help='Filter by element type (e.g., section, chapter, note)')
    parser.add_argument('--num', help='Filter by element number (e.g., 10, 1201)')
    
    args = parser.parse_args()
    
    # Build filepath
    filepath = f"{args.xml_dir}/{args.title}.xml"
    
    print(f"Parsing {filepath}...")
    laws = parse_single_title(filepath)
    print(f"Found {len(laws)} elements")
    
    # Apply filters
    filtered_laws = laws
    if args.type:
        filtered_laws = [law for law in filtered_laws if law['tag'] == args.type]
        print(f"Filtered to {len(filtered_laws)} {args.type} elements")
    
    if args.num:
        def num_contains(law, search_num):
            num_field = law.get('num', '')
            if isinstance(num_field, dict):
                # Check in text field and value attribute
                text = num_field.get('text', '')
                value = num_field.get('attributes', {}).get('value', '')
                return search_num in text or search_num in value
            else:
                # Fallback for string format
                return search_num in str(num_field)
        
        filtered_laws = [law for law in filtered_laws if num_contains(law, args.num)]
        print(f"Filtered to {len(filtered_laws)} elements with num containing '{args.num}'")
    
    # Show summary by element type if no specific filters
    if not args.type and not args.num:
        from collections import Counter
        element_counts = Counter(law['tag'] for law in laws)
        print("\nElement types found:")
        for tag, count in sorted(element_counts.items()):
            print(f"  {tag}: {count}")
    
    # Save to JSON if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(filtered_laws, f, indent=2, ensure_ascii=False)
        print(f"\nSaved {len(filtered_laws)} elements to {args.output}")
    else:
        # Show filtered results with pretty printing
        display_laws = filtered_laws[:10]  # Show up to 10 results
        print(f"\nShowing first {len(display_laws)} results:")
        for i, law in enumerate(display_laws):
            print(f"\n{i+1}. Element:")
            
            # Pretty print the own_content_text if it exists
            if 'computed' in law and 'own_content_text' in law['computed']:
                own_content = law['computed']['own_content_text']
                law_copy = law.copy()
                law_copy['computed'] = law['computed'].copy()
                law_copy['computed']['own_content_text'] = "[PRETTY PRINTED BELOW]"
                
                print(json.dumps(law_copy, indent=4, ensure_ascii=False))
                print("\nPRETTY PRINTED CONTENT:")
                print("=" * 50)
                print(own_content)
                print("=" * 50)
            else:
                print(json.dumps(law, indent=4, ensure_ascii=False))
        
        if len(filtered_laws) > 10:
            print(f"\n... and {len(filtered_laws) - 10} more results")