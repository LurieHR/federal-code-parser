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
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict


NAMESPACE = {'uslm': 'http://xml.house.gov/schemas/uslm/1.0'}
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


def extract_sections(doc: ET.Element) -> List[ET.Element]:
    """
    Find all section elements in the document.
    
    Args:
        doc: Root element of the USC XML document
        
    Returns:
        List of section elements
    """
    sections = doc.findall('.//uslm:section', NAMESPACE)
    return sections


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


def extract_notes(section: ET.Element) -> List[str]:
    """
    Extract notes from a section.
    
    Args:
        section: Section element
        
    Returns:
        List of note texts
    """
    notes = []
    
    # Extract source credit
    source_credit = section.find('.//uslm:sourceCredit', NAMESPACE)
    if source_credit is not None and source_credit.text:
        notes.append(f"Source: {source_credit.text.strip()}")
    
    # Extract other notes
    note_elements = section.findall('.//uslm:notes//uslm:note', NAMESPACE)
    for note in note_elements:
        note_text = ''.join(note.itertext()).strip()
        if note_text:
            notes.append(note_text)
    
    return notes


def extract_source_credit(section: ET.Element) -> Dict[str, Optional[str]]:
    """
    Extract source credit information from sourceCredit element.
    
    Args:
        section: Section element
        
    Returns:
        Dictionary with source credit information
    """
    source_credit_info = {
        'original_act': None,
        'original_public_law': None,
        'original_date': None,
        'original_statutes': None,
        'codification_authority': None
    }
    
    source_credit = section.find('.//uslm:sourceCredit', NAMESPACE)
    if source_credit is not None:
        # Get all refs and dates in sourceCredit
        refs = source_credit.findall('.//uslm:ref', NAMESPACE)
        dates = source_credit.findall('.//uslm:date', NAMESPACE)
        
        # The first Public Law reference is typically the original enacting law
        for i, ref in enumerate(refs):
            href = ref.get('href', '')
            if '/pl/' in href:
                # Extract public law info
                pl_match = re.search(r'/pl/(\d+)/(\d+)', href)
                if pl_match:
                    source_credit_info['original_public_law'] = f"Pub. L. {pl_match.group(1)}-{pl_match.group(2)}"
                    
                    # Get the corresponding date
                    if i < len(dates):
                        source_credit_info['original_date'] = dates[i].get('date')
                    
                    # Look for the next Stat reference
                    source_text = ''.join(source_credit.itertext())
                    stat_match = re.search(rf"Pub\. L\. {pl_match.group(1)}[–-]{pl_match.group(2)}.*?(\d+\s+Stat\.\s+\d+)", source_text)
                    if stat_match:
                        source_credit_info['original_statutes'] = stat_match.group(1)
                    
                    # For Title 5, check if it's the 1966 codification
                    if pl_match.group(1) == "89" and pl_match.group(2) == "554":
                        source_credit_info['codification_authority'] = "Title 5 Codification Act of 1966"
                    
                    break
        
        # Try to extract act name from notes if available
        notes = section.find('.//uslm:notes', NAMESPACE)
        if notes is not None:
            # Look for short title notes
            short_title_notes = notes.findall('.//uslm:note[@topic="shortTitle"]', NAMESPACE)
            for note in short_title_notes:
                note_text = ''.join(note.itertext())
                # Extract act name from quotes
                act_match = re.search(r'["\']([^"\']*?Act[^"\']*?)["\']', note_text)
                if act_match:
                    source_credit_info['original_act'] = act_match.group(1)
                    break
    
    return source_credit_info


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


def build_citation(title_num: str, section_num: str) -> str:
    """
    Create a legal citation string.
    
    Args:
        title_num: Title number
        section_num: Section number
        
    Returns:
        Formatted citation (e.g., "5 U.S.C. § 1201")
    """
    return f"{title_num} U.S.C. § {section_num}"


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


def get_law_hierarchy(section: ET.Element, title_number: int, doc_root: Optional[ET.Element] = None) -> Dict[str, Any]:
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


def build_law_dict(section: ET.Element, title_number: int, is_positive_law: bool = True, filename: str = '', doc_root: Optional[ET.Element] = None) -> Optional[Dict[str, Any]]:
    """
    Convert a section element to a comprehensive dictionary.
    
    Args:
        section: Section element
        title_number: USC title number
        is_positive_law: Whether this title is positive law
        filename: Source filename
        doc_root: Root document element for metadata extraction
        
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


def get_title_number_from_filename(filename: str) -> Optional[int]:
    """
    Extract title number from filename.
    
    Args:
        filename: XML filename (e.g., 'usc05.xml')
        
    Returns:
        Title number or None
    """
    match = re.match(r'usc(\d+)\.xml', filename)
    if match:
        return int(match.group(1))
    return None


def parse_single_title(filepath: str, title_number: int, is_positive_law: bool = True) -> List[Dict[str, Any]]:
    """
    Parse a single USC title file and extract all laws.
    
    Args:
        filepath: Path to the XML file
        title_number: USC title number
        is_positive_law: Whether this title is positive law
        
    Returns:
        List of law dictionaries
    """
    laws = []
    filename = os.path.basename(filepath)
    
    try:
        # Parse the file
        doc = parse_usc_file(filepath)
        
        # Extract all sections
        sections = extract_sections(doc)
        
        # Convert each section to a dictionary
        for section in sections:
            law_dict = build_law_dict(section, title_number, is_positive_law, filename, doc)
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
        title_num = get_title_number_from_filename(xml_file)
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
        json.dump(laws, f, indent=2)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    main()