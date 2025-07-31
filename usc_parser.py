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
        print(law['references'])

Usage from command line:
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

# Define hierarchical structural elements that should be part of the path
HIERARCHICAL_TAGS = {
    'title', 'subtitle', 'part', 'subpart', 'division', 'subdivision',
    'chapter', 'subchapter', 'article', 'appendix', 'section',
    'subsection', 'paragraph', 'subparagraph', 'clause', 'subclause',
    'item', 'subitem'
}


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




def traverse_with_ancestor_paths(xml_element: ET.Element, current_path: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
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
    tag = xml_element.tag.split('}')[-1] if '}' in xml_element.tag else xml_element.tag
    
    
    # Get basic element info
    num_elem = xml_element.find('./uslm:num', NAMESPACE)
    num = num_elem.text if num_elem is not None and num_elem.text else ''
    
    heading_elem = xml_element.find('./uslm:heading', NAMESPACE)
    heading = heading_elem.text if heading_elem is not None and heading_elem.text else ''
    
    # Build element info with ALL attributes preserved
    element_info = {
        'tag': tag,
        'num': num,
        'heading': heading,
        'attributes': extract_all_element_attributes(xml_element)
    }
    
    # If this is a hierarchical element, add it to the path and continue
    if tag in HIERARCHICAL_TAGS:
        new_path = current_path + [element_info]
        
        # Continue traversing with the extended path
        for child in xml_element:
            results.extend(traverse_with_ancestor_paths(child, new_path))
    
    # For ALL elements (including hierarchical ones), extract them as content items
    results.append({
        'xml_element': xml_element,
        'element_info': element_info,
        'ancestor_path': current_path  # Everything above this element
    })
    
    # If not hierarchical, still traverse children
    if tag not in HIERARCHICAL_TAGS:
        for child in xml_element:
            results.extend(traverse_with_ancestor_paths(child, current_path))
    
    return results










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
                        'text': p_text,
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




def extract_all_references(xml_element: ET.Element) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract all types of references from any element, separating local from child references.
    
    Args:
        xml_element: Any XML element
        
    Returns:
        Dictionary with 'local_references' and 'child_references', each containing different types
    """
    def create_empty_refs():
        return {
            # From <ref> elements
            'usc_references': [],          # USC section/chapter references
            'act_references': [],          # Act references 
            'public_law_hrefs': [],        # Public law from href
            'statute_hrefs': [],           # Statutes from href
            
            # From text patterns
            'public_laws_text': [],        # Public law from text
            'statutes_text': [],           # Statutes from text
            'executive_orders': [],        # Executive orders (text only, no hrefs)
            'federal_register': [],        # Federal Register citations
        }
    
    local_refs = create_empty_refs()
    child_refs = create_empty_refs()
    
    # Process all ref elements in the document
    for ref in xml_element.findall('.//uslm:ref', NAMESPACE):
        # Determine if this ref belongs to a hierarchical child
        parent = ref.getparent()
        belongs_to_hierarchical_child = False
        
        # Walk up the tree to see if any ancestor is a hierarchical child
        while parent is not None and parent != xml_element:
            parent_tag = parent.tag.split('}')[-1] if '}' in parent.tag else parent.tag
            if parent_tag in HIERARCHICAL_TAGS:
                belongs_to_hierarchical_child = True
                break
            parent = parent.getparent()
        
        # Add to appropriate reference list
        if belongs_to_hierarchical_child:
            process_ref_element(ref, child_refs)
        else:
            process_ref_element(ref, local_refs)
    
    # Extract text patterns from local content only (excluding hierarchical children)
    local_text = extract_local_text_only(xml_element)
    extract_text_patterns(local_text, local_refs)
    
    # Extract text patterns from child content
    for child in xml_element:
        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if child_tag in HIERARCHICAL_TAGS:
            child_text = ''.join(child.itertext())
            extract_text_patterns(child_text, child_refs)
    
    # Remove duplicates
    for refs in [local_refs, child_refs]:
        for key in refs:
            refs[key] = list(set(refs[key]))
    
    # Check for text references without hrefs (only for local)
    check_text_only_refs(xml_element, local_refs)
    
    return {
        'local_references': local_refs,
        'child_references': child_refs
    }


def process_ref_element(ref: ET.Element, refs_dict: Dict[str, List[str]]) -> None:
    """Process a single ref element and add to appropriate reference list."""
    href = ref.get('href', '')
    if not href:
        return
        
    # USC references: /us/usc/t5/s1202 or /us/usc/t5/ch12
    usc_match = re.match(r'/us/usc/t(\d+[A-Za-z]*)/([sc])(\d+[A-Za-z]*)', href)
    if usc_match:
        title, type_char, num = usc_match.groups()
        if type_char == 's':
            citation = f"{title} U.S.C. § {num}"
        else:  # chapter
            citation = f"{title} U.S.C. Ch. {num}"
        refs_dict['usc_references'].append(citation)
        return
        
    # Act references: /us/act/1947-07-30/ch388
    act_match = re.match(r'/us/act/([^/]+)/(.+)', href)
    if act_match:
        date, details = act_match.groups()
        act_ref = f"Act of {date}, {details}"
        refs_dict['act_references'].append(act_ref)
        return
        
    # Public law references: /us/pl/117/286
    pl_match = re.match(r'/us/pl/(\d+)/(\d+)', href)
    if pl_match:
        congress, law_num = pl_match.groups()
        public_law = f"Pub. L. {congress}-{law_num}"
        refs_dict['public_law_hrefs'].append(public_law)
        return
        
    # Statute references: /us/stat/116/926
    stat_match = re.match(r'/us/stat/(\d+[A-Za-z]*)/(\d+)', href)
    if stat_match:
        volume, page = stat_match.groups()
        statute = f"{volume} Stat. {page}"
        refs_dict['statute_hrefs'].append(statute)


def extract_local_text_only(xml_element: ET.Element) -> str:
    """Extract text from element excluding hierarchical child elements."""
    text_parts = []
    
    # Add element's direct text
    if xml_element.text:
        text_parts.append(xml_element.text)
    
    # Process children but skip hierarchical ones
    for child in xml_element:
        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        
        if child_tag not in HIERARCHICAL_TAGS:
            # Include this child's text
            text_parts.append(''.join(child.itertext()))
        
        # Always include tail text
        if child.tail:
            text_parts.append(child.tail)
    
    return ' '.join(text_parts)


def extract_text_patterns(text: str, refs_dict: Dict[str, List[str]]) -> None:
    """Extract reference patterns from text and add to refs_dict."""
    # Public Laws in text: "Pub. L. 117-286"
    pl_text_matches = re.findall(r'Pub\. L\. \d+[-–]\d+', text)
    refs_dict['public_laws_text'].extend(pl_text_matches)
    
    # Statutes in text: "136 Stat. 4359"
    stat_text_matches = re.findall(r'\d+ Stat\. \d+', text)
    refs_dict['statutes_text'].extend(stat_text_matches)
    
    # Executive Orders: "Ex. Ord. No. 12107" or "Executive Order 13526"
    eo_matches = re.findall(r'(?:Ex\. Ord\. No\.|Executive Order) \d+', text)
    refs_dict['executive_orders'].extend(eo_matches)
    
    # Federal Register citations: "75 F.R. 707" or "75 F.R. 707, 1013"
    fr_matches = re.findall(r'\d+ F\.R\. [\d,\s]+', text)
    # Clean up the matches (remove trailing commas/spaces)
    fr_matches = [match.rstrip(', ') for match in fr_matches]
    refs_dict['federal_register'].extend(fr_matches)


def check_text_only_refs(xml_element: ET.Element, refs_dict: Dict[str, List[str]]) -> None:
    """Check if any text references don't have corresponding hrefs and warn."""
    text_only_pls = set(refs_dict['public_laws_text']) - set(refs_dict['public_law_hrefs'])
    text_only_stats = set(refs_dict['statutes_text']) - set(refs_dict['statute_hrefs'])
    
    if text_only_pls:
        element_tag = xml_element.tag.split('}')[-1] if '}' in xml_element.tag else xml_element.tag
        element_id = xml_element.get('id', 'no-id')
        element_identifier = xml_element.get('identifier', 'no-identifier')
        pass  # Suppress warning
    if text_only_stats:
        element_tag = xml_element.tag.split('}')[-1] if '}' in xml_element.tag else xml_element.tag
        element_id = xml_element.get('id', 'no-id')
        element_identifier = xml_element.get('identifier', 'no-identifier')
        pass  # Suppress warning


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







def build_dict(element_data: Dict[str, Any], filename: str, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert element data with ancestor paths to a comprehensive dictionary.
    
    Args:
        element_data: Element data with ancestor paths from traverse_with_ancestor_paths()
        filename: Source filename (e.g., 'usc50A.xml')
        metadata: Document-level metadata dictionary
        
    Returns:
        Dictionary with law information or None if element should be skipped
    """
    xml_element = element_data['xml_element']
    element_info = element_data['element_info']
    ancestor_path = element_data['ancestor_path']
    
    
    # Get element number and heading
    element_number = element_info['num']
    heading = element_info['heading']
    
    
    
    
    # Extract amendment history for all elements
    amendment_history = extract_amendment_history(xml_element)
    
    # Get element attributes
    element_attributes = element_info.get('attributes')
    if element_attributes is None:
        element_attributes = {}
    
    # Extract actual child elements that exist in the XML
    def extract_element_content(elem):
        """Recursively extract element content preserving document order"""
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # Get element attributes
        attrs = dict(elem.attrib) if elem.attrib else {}
        
        # Get direct text content
        text = elem.text if elem.text else ''
        
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
            full_text = ''.join(elem.itertext())
            if full_text:
                result['paragraph_text'] = full_text
        
        # If element has no attributes, text, or children, return the tail text if any
        if not result and elem.tail:
            return elem.tail
        
        return result if result else None
    
    child_elements = {}
    for child in xml_element:
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
    
    
    
    
    # Build computed fields
    computed_fields = {
        "processing_timestamp": time.time(),
        "processing_machine": socket.gethostname(),
        "file_source": filename,
        "ancestors": "; ".join(ancestors)
    }
    
    # Add amendment history to computed fields
    computed_fields["amendment_history"] = amendment_history
    
    # Add hierarchical element own content extraction
    own_content_data = {}
    child_pointers = []
    if element_info['tag'] in HIERARCHICAL_TAGS:
        own_content_data = extract_own_content_text(xml_element)
        computed_fields.update(own_content_data)
        # Extract child_pointers before building elastic_dict
        child_pointers = own_content_data.pop('child_pointers', [])
        own_content_data.pop('num_children', None)  # Remove this too since it's redundant

    # Extract all references
    all_references = extract_all_references(xml_element)

    # Create list of child identifiers for elastic_dict
    child_identifiers = [child['identifier'] for child in child_pointers if child.get('identifier')]

    # Build elastic_dict with fields chosen for final RAG dictionary metadata
    elastic_dict = {
        "guid": element_attributes.get('id', ''),  # Note: renamed from XML's @id attribute for clarity
        "element_type": element_info['tag'],
        "num": element_info['num'],
        "num_numeric": ''.join(c for c in element_info['num'] if c.isdigit()),
        "heading": element_info['heading'],
        "identifier": element_attributes.get('identifier', ''),
        "status": element_attributes.get('status') if element_attributes.get('status') else 'none',
        "is_positive_law": meta['property[@role="is-positive-law"]'],
        "references": all_references['local_references'],  # Only local references in elastic_dict
        "child_identifiers": child_identifiers,  # Simple list of child identifiers
        "meta": meta,
        **own_content_data  # Now only includes text_local, text_local_length, sourceCredit, notes
    }

    return {
        # Element info
        "tag": element_info['tag'],
        "num": element_info['num'],
        "heading": element_info['heading'],
        "attributes": element_attributes,
        
        # Actual child elements from XML
        **child_elements,
        
        # Computed/derived fields (not in original XML)
        "computed": computed_fields,
        
        # Child pointers (detailed info about hierarchical children)
        "child_pointers": child_pointers,
        
        # Child references (from all child hierarchical elements)
        "child_references": all_references['child_references'],
        
        # Hierarchical context (ancestor path without current element)
        "ancestor_path": ancestor_path,
        
        # Document metadata (from <meta> element)
        "meta": meta,
        
        # Fields chosen for final RAG dictionary metadata
        "elastic_dict": elastic_dict
    }



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
        header_text = ''.join(header.itertext())
    
    for item in toc_element.findall('.//uslm:tocItem', NAMESPACE):
        left_col = item.find('.//uslm:column[@class="twoColumnLeft"]', NAMESPACE)  
        right_col = item.find('.//uslm:column[@class="twoColumnRight"]', NAMESPACE)
        
        if left_col is not None and right_col is not None:
            left_text = ''.join(left_col.itertext())
            
            # Process right column: collect text with references, collect footnotes
            right_text_parts = []
            footnotes_in_this_item = []
            
            def process_right_col(elem):
                if elem.text:
                    right_text_parts.append(elem.text)
                
                for child in elem:
                    child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    
                    if child_tag == 'ref' and 'footnoteRef' in child.get('class', ''):
                        # Add inline reference
                        if child.text:
                            right_text_parts.append(f"[{child.text}]")
                    elif child_tag == 'note' and child.get('type') == 'footnote':
                        # Collect footnote for bottom section
                        footnote_text = ''.join(child.itertext())
                        if footnote_text:
                            footnotes_in_this_item.append(footnote_text)
                    else:
                        # Recursively process other elements
                        process_right_col(child)
                    
                    if child.tail:
                        right_text_parts.append(child.tail)
            
            process_right_col(right_col)
            right_text = ' '.join(right_text_parts)
            
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


def extract_table(table_elem: ET.Element) -> str:
    """
    Extract table content with basic formatting.
    
    Args:
        table_elem: Table XML element
        
    Returns:
        String with table content formatted with tabs between cells and newlines between rows
    """
    rows = []
    
    # Process all descendant elements looking for table rows
    for elem in table_elem.iter():
        if elem.tag.endswith('tr'):
            cells = []
            # Process all children looking for table cells
            for cell in elem:
                if cell.tag.endswith('th') or cell.tag.endswith('td'):
                    # Extract text from each <p> element within the cell
                    p_texts = []
                    for p in cell.iter():
                        if p.tag.endswith('p'):
                            p_text = ''.join(p.itertext())
                            if p_text:
                                p_texts.append(p_text)
                    
                    # If no <p> elements, just get all text
                    if not p_texts:
                        cell_text = ''.join(cell.itertext())
                    else:
                        # Join multiple <p> elements with space
                        cell_text = ' '.join(p_texts)
                    
                    if cell_text:
                        cells.append(cell_text)
            if cells:
                # Join cells with tabs to create tab-delimited format
                # Note: Tab width varies by display; empty cells may not be visually distinct
                rows.append('\t'.join(cells))
    
    return '\n'.join(rows) if rows else ''



def extract_notes(notes_elem: ET.Element) -> List[Dict[str, Any]]:
    """
    Extract all notes content in document order.
    
    Args:
        notes_elem: Notes element
        
    Returns:
        List of note dictionaries with topic, role, and content
    """
    notes_list = []
    
    # Process each note in document order
    for note in notes_elem:
        # Skip non-note elements
        if not note.tag.endswith('note'):
            continue
            
        topic = note.get('topic')
        if topic is None:
            continue  # Skip notes without topics
            
        role = note.get('role', 'none')
        
        # Extract note content with proper handling of tables and other elements
        content_parts = []
        
        # Add initial text if any
        if note.text:
            content_parts.append(note.text)
        
        # Process child elements
        for child in note:
            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            
            if child_tag == 'table':
                # Extract table with formatting
                table_text = extract_table(child)
                if table_text:
                    content_parts.append(f"\n{table_text}\n")
            elif child_tag == 'p':
                # Add paragraph with newlines
                p_text = ''.join(child.itertext())
                if p_text:
                    content_parts.append(f"\n{p_text}")
            else:
                # For other elements, just get text
                elem_text = ''.join(child.itertext())
                if elem_text:
                    content_parts.append(elem_text)
            
            # Add tail text after the child
            if child.tail:
                content_parts.append(child.tail)
        
        note_content = ' '.join(content_parts)
        
        if note_content:
            # Add note to list preserving document order
            notes_list.append({
                'topic': topic,
                'role': role,
                'content': note_content
            })
    
    return notes_list


def extract_own_content_text(xml_element: ET.Element) -> Dict[str, Any]:
    """
    Extract an element's own text content, excluding child sections/subchapters.
    Returns text content and child pointers.
    
    Args:
        xml_element: XML element
        
    Returns:
        Dictionary with own_content_text, child_pointers, sourceCredit, etc.
    """
    
    own_content_parts = []
    child_pointers = []
    source_credit_text = ''
    notes_dict = []
    
    # Process all child elements
    for child in xml_element:
        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        
        # Major structural elements - just create pointers
        if child_tag in HIERARCHICAL_TAGS:
            child_num_elem = child.find('./uslm:num', NAMESPACE)
            child_num = child_num_elem.text if child_num_elem is not None and child_num_elem.text else ''
            child_identifier = child.get('identifier', '')
            child_heading_elem = child.find('./uslm:heading', NAMESPACE)
            child_heading = child_heading_elem.text if child_heading_elem is not None and child_heading_elem.text else ''
            
            child_pointers.append({
                'tag': child_tag,
                'num': child_num,
                'heading': child_heading,
                'identifier': child_identifier
            })
            
        # Known element types with specialized parsers
        elif child_tag == 'toc':
            toc_text = parse_toc(child)
            if toc_text:
                own_content_parts.append(toc_text)
                
        elif child_tag == 'notes':
            notes_list = extract_notes(child)
            # Add notes to own_content_parts in document order
            for note in notes_list:
                own_content_parts.append(note['content'])
            # Store for structured access
            notes_dict = notes_list
                
        elif child_tag == 'sourceCredit':
            source_credit_text = ''.join(child.itertext())
            if source_credit_text:
                own_content_parts.append(source_credit_text)
                
        elif child_tag == 'table':
            # Extract table with proper formatting
            table_text = extract_table(child)
            if table_text:
                own_content_parts.append(table_text)
                
        elif child_tag == 'p':
            # Add paragraph text with proper spacing
            p_text = ''.join(child.itertext()).strip()
            if p_text:
                own_content_parts.append(p_text)
            
        # Default handler for unknown elements
        else:
            child_text = ''.join(child.itertext())
            if child_text:
                own_content_parts.append(child_text)
    
    text_local = '\n\n'.join(own_content_parts)
    
    return {
        "text_local": text_local,
        "text_local_length": len(text_local),
        "child_pointers": child_pointers,
        "num_children": len(child_pointers),
        "sourceCredit": source_credit_text,
        "notes": notes_dict
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
    
    # Parse the file
    tree = ET.parse(filepath)
    doc = tree.getroot()
    
    # Extract meta from the document
    meta = extract_meta(doc)
    
    # Get all elements with their complete ancestor paths
    elements_with_paths = traverse_with_ancestor_paths(doc)
    
    # Convert each element+path to a law dictionary
    for element_data in elements_with_paths:
        # Only process hierarchical elements
        if element_data['element_info']['tag'] in HIERARCHICAL_TAGS:
            law_dict = build_dict(
                element_data=element_data,
                filename=filename,
                meta=meta
            )
            if law_dict:
                laws.append(law_dict)
    
    return laws




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
        '--output-dir',
        default='output',
        help='Output directory for JSON files (default: output)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Parse all titles '
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
        
        print(f"Parsing Title {title_num} from {filename}...")
        laws = parse_single_title(filepath)
        print(f"Found {len(laws)} elements in Title {title_num}")
        
        output_file = os.path.join(args.output_dir, f"{args.title}.json")
        with open(output_file, 'w') as f:
            json.dump(laws, f, indent=2, ensure_ascii=False)
        print(f"Saved to {output_file}")
        
    elif args.all:
        # Parse all titles
        print("Parsing all USC titles...")
        xml_files = [f for f in os.listdir(args.xml_dir) if f.endswith('.xml') and f.startswith('usc')]
        xml_files.sort()
        
        total_elements = 0
        for xml_file in xml_files:
            filepath = os.path.join(args.xml_dir, xml_file)
            print(f"\nParsing {xml_file}...")
            laws = parse_single_title(filepath)
            print(f"Found {len(laws)} elements")
            total_elements += len(laws)
            
            # Save each title to its own file
            output_file = os.path.join(args.output_dir, f"{xml_file.replace('.xml', '')}.json")
            with open(output_file, 'w') as f:
                json.dump(laws, f, indent=2, ensure_ascii=False)
            print(f"Saved to {output_file}")
        
        print(f"\nTotal elements parsed: {total_elements}")
        
    else:
        parser.error("Please specify either --title or --all")


def filter_elements(elements: List[Dict[str, Any]], element_type: str = None, element_num: str = None) -> List[Dict[str, Any]]:
    """
    Filter elements by type and/or number.
    
    Args:
        elements: List of element dictionaries
        element_type: Element type to filter by (e.g., 'section', 'chapter')
        element_num: Element number to filter by (e.g., '552', '5')
        
    Returns:
        Filtered list of elements
    """
    filtered = elements
    
    if element_type:
        filtered = [elem for elem in filtered if elem['tag'] == element_type]
        print(f"Filtered to {len(filtered)} {element_type} elements")
    
    if element_num:
        def num_equals(elem, search_num):
            return elem['elastic_dict']['num_numeric'] == search_num
        
        filtered = [elem for elem in filtered if num_equals(elem, element_num)]
        print(f"Filtered to {len(filtered)} elements with num equal to '{element_num}'")
    
    return filtered


def print_dict(element: Dict[str, Any], elastic_only: bool = False) -> None:
    """
    Print a single element dictionary.
    
    Args:
        element: Element dictionary to print
        elastic_only: If True, only print elastic_dict portion
    """
    if elastic_only:
        elastic = element['elastic_dict']
        for key, value in elastic.items():
            print(f"\n----------------------{key}---------------------")
            if key == 'notes' and isinstance(value, dict):
                # Special handling for notes to show nested structure
                for note_type, note_content in value.items():
                    print(f"\n{note_type}:")
                    if isinstance(note_content, dict):
                        if 'content' in note_content:
                            print(note_content['content'])
                    elif isinstance(note_content, list):
                        for item in note_content:
                            if isinstance(item, dict) and 'content' in item:
                                print(item['content'])
                    else:
                        print(note_content)
            elif isinstance(value, dict):
                # For other dict values, print as JSON
                print(json.dumps(value, indent=2, ensure_ascii=False))
            else:
                print(value)
    else:
        print(json.dumps(element, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='Parse USC XML files')
    parser.add_argument('--title', required=True, help='USC title to parse (e.g., usc05, usc50A)')
    parser.add_argument('--xml-dir', default='xml_uscAll@119-12', help='Directory containing XML files')
    parser.add_argument('--output-dir', help='Output directory for JSON files (optional)')
    parser.add_argument('--type', help='Filter by element type (e.g., section, chapter, note)')
    parser.add_argument('--num', help='Filter by exact element number (e.g., 1, 10, 1201)')
    parser.add_argument('--elastic-only', action='store_true', help='Only display elastic_dict portion of results')
    parser.add_argument('--int', action='store_true', help='Interactive mode - query sections interactively')
    
    args = parser.parse_args()
    
    # Build filepath
    filepath = f"{args.xml_dir}/{args.title}.xml"
    
    print(f"Parsing {filepath}...")
    elements = parse_single_title(filepath)
    print(f"Found {len(elements)} elements")
    
    # Interactive mode
    if args.int:
        print("\nInteractive mode. Examples: sec 552, ch 5, q to quit")
        
        while True:
            query = input("\nQuery> ").strip().lower()
            if query == 'q' or query == 'quit':
                break
            
            # Parse query
            parts = query.split()
            if len(parts) < 2:
                print("Please enter a query like 'sec 552' or 'chapter 5'")
                continue
            
            # Determine element type
            query_type = parts[0]
            query_num = ' '.join(parts[1:])
            
            # Map common abbreviations to full names
            type_map = {
                'sec': 'section',
                'ch': 'chapter',
                'subch': 'subchapter',
                'pt': 'part',
                'subpt': 'subpart',
                'div': 'division',
                'subdiv': 'subdivision'
            }
            
            if query_type in type_map:
                query_type = type_map[query_type]
            
            # Filter and display
            filtered = filter_elements(elements, element_type=query_type, element_num=query_num)
            
            if not filtered:
                print(f"No matches found")
            else:
                for elem in filtered:
                    print(f"\n{'='*80}")
                    print_dict(elem, elastic_only=args.elastic_only)
    
    # Non-interactive mode
    else:
        # Apply filters
        filtered_elements = filter_elements(elements, element_type=args.type, element_num=args.num)
        
        # Save to JSON if requested
        if args.output_dir:
            output_file = os.path.join(args.output_dir, f"{args.title}.json")
            with open(output_file, 'w') as f:
                json.dump(filtered_elements, f, indent=2, ensure_ascii=False)
            print(f"\nSaved {len(filtered_elements)} elements to {output_file}")
        else:
            # Show filtered results with pretty printing
            display_elements = filtered_elements[:10]  # Show up to 10 results
            print(f"\nShowing first {len(display_elements)} results:")
            for i, elem in enumerate(display_elements):
                print(f"\n{i+1}. Element:")
                print_dict(elem, elastic_only=args.elastic_only)
            
            if len(filtered_elements) > 10:
                print(f"\n... and {len(filtered_elements) - 10} more results")