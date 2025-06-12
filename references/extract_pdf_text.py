#!/usr/bin/env python3

import PyPDF2
import sys
import re
import os

def clean_text(text):
    """Clean and format extracted text for better readability"""
    # Remove excessive whitespace and normalize line breaks
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n ', '\n', text)
    
    # Fix common PDF extraction issues
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # Add space between lowercase and uppercase
    text = re.sub(r'(\w)(\d)', r'\1 \2', text)  # Add space between word and number
    text = re.sub(r'(\d)([A-Za-z])', r'\1 \2', text)  # Add space between number and letter
    
    # Clean up punctuation spacing
    text = re.sub(r'\s+([.,:;!?])', r'\1', text)  # Remove space before punctuation
    text = re.sub(r'([.,:;!?])([A-Za-z])', r'\1 \2', text)  # Add space after punctuation
    
    return text.strip()

def create_rtf_header():
    """Create RTF document header"""
    return r"""{\rtf1\ansi\deff0 {\fonttbl {\f0 Times New Roman;}}
\f0\fs24 """

def create_rtf_footer():
    """Create RTF document footer"""
    return "}"

def format_as_rtf(text):
    """Format text as RTF with basic formatting"""
    rtf_content = create_rtf_header()
    
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            rtf_content += r"\par "
            continue
            
        # Check if line looks like a heading (all caps, short, or starts with numbers/bullets)
        if (len(line) < 100 and 
            (line.isupper() or 
             re.match(r'^\d+\.?\s', line) or 
             re.match(r'^[A-Z][A-Z\s]{10,}$', line) or
             line.startswith('---'))):
            # Format as heading
            rtf_content += r"\par\b " + line.replace('---', '').strip() + r"\b0\par "
        else:
            # Regular paragraph
            rtf_content += line + r"\par "
    
    rtf_content += create_rtf_footer()
    return rtf_content

def extract_text_from_pdf(pdf_path):
    """Extract and clean text from PDF file"""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            
            # Extract text from all pages
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_text = page.extract_text()
                if page_text.strip():  # Only add non-empty pages
                    text += f"\n--- Page {page_num + 1} ---\n"
                    text += page_text
                    text += "\n\n"
            
            return clean_text(text)
    except Exception as e:
        return f"Error reading PDF: {str(e)}"

def save_to_rtf(text, output_path):
    """Save text to RTF file"""
    try:
        rtf_content = format_as_rtf(text)
        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(rtf_content)
        return True
    except Exception as e:
        print(f"Error saving RTF file: {str(e)}")
        return False

if __name__ == "__main__":
    pdf_path = "/Users/helen/hack/git/federalcodeparser/references/USLM-User-Guide.pdf"
    output_path = "/Users/helen/hack/git/federalcodeparser/references/USLM-User-Guide.rtf"
    
    print("Extracting text from PDF...")
    text = extract_text_from_pdf(pdf_path)
    
    if text.startswith("Error"):
        print(text)
        sys.exit(1)
    
    print("Creating RTF file...")
    if save_to_rtf(text, output_path):
        print(f"Successfully created RTF file: {output_path}")
    else:
        print("Failed to create RTF file")
        sys.exit(1)