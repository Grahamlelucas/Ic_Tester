# ic_tester_app/intelligence/datasheet_parser.py
# Last edited: 2026-01-20
# Purpose: Parse TTL datasheet PDFs to extract chip definitions
# Dependencies: pdfplumber (optional), re, json

"""
Datasheet-to-definition extraction helper.

This module tries to bootstrap chip definitions from PDF datasheets or TTL data
books by mining the text layer for part numbers, descriptions, truth tables,
and package information. The output is intentionally partial: it is meant to
save manual effort, not replace human review.
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict

from ..logger import get_logger

logger = get_logger("intelligence.datasheet_parser")

# PDF support is optional so the rest of the application can run without the
# parsing stack installed.
PDF_AVAILABLE = False
try:
    import pdfplumber
    PDF_AVAILABLE = True
    logger.info("pdfplumber available for PDF parsing")
except ImportError:
    logger.warning("pdfplumber not installed - PDF parsing limited")

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


@dataclass
class ExtractedChip:
    """Chip data extracted from datasheet"""
    chip_id: str
    name: str
    description: str
    pin_count: int
    function_type: str  # 'gate', 'counter', 'flip_flop', etc.
    truth_table: List[Dict[str, str]] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    page_number: int = 0
    confidence: float = 0.0  # How confident we are in extraction
    needs_review: List[str] = field(default_factory=list)  # What needs manual check
    raw_text: str = ""
    
    def to_chip_json(self) -> Dict[str, Any]:
        """Convert to chip definition JSON format (partial)"""
        return {
            "chipId": self.chip_id,
            "name": self.name,
            "description": self.description,
            "pinCount": self.pin_count,
            "functionType": self.function_type,
            "extractedFrom": "TTL Data Book",
            "needsReview": self.needs_review,
            "confidence": self.confidence,
            "pinout": {
                "vcc": 14 if self.pin_count == 14 else (16 if self.pin_count == 16 else None),
                "gnd": 7 if self.pin_count == 14 else (8 if self.pin_count == 16 else None),
                "inputs": [{"pin": None, "name": name} for name in self.inputs],
                "outputs": [{"pin": None, "name": name} for name in self.outputs],
                "_note": "Pin numbers need manual entry from datasheet diagram"
            },
            "truthTable": self.truth_table,
            "testSequence": {
                "tests": [],
                "_note": "Tests need to be generated from truth table"
            }
        }


# Patterns for identifying chip information
CHIP_ID_PATTERNS = [
    r'SN74(\w{2,4})\b',           # SN7400, SN74LS00, SN74HC00
    r'\b74([A-Z]{0,3}\d{2,4})\b', # 74LS00, 7400, 74HC595
    r'SN54(\w{2,4})\b',           # Military spec versions
]

FUNCTION_KEYWORDS = {
    'gate': ['nand', 'and', 'or', 'nor', 'xor', 'xnor', 'not', 'inverter', 'buffer'],
    'flip_flop': ['flip-flop', 'flipflop', 'latch', 'd-type', 'jk', 'sr'],
    'counter': ['counter', 'decade', 'binary counter', 'divider'],
    'decoder': ['decoder', 'demultiplexer', 'demux'],
    'encoder': ['encoder', 'priority'],
    'multiplexer': ['multiplexer', 'mux', 'selector'],
    'shift_register': ['shift register', 'shift-register', 'serial'],
    'arithmetic': ['adder', 'comparator', 'alu', 'magnitude'],
    'buffer': ['buffer', 'driver', 'line driver', 'bus'],
}

# Truth table patterns
TRUTH_TABLE_HEADERS = [
    r'INPUTS?\s+OUTPUTS?',
    r'FUNCTION\s+TABLE',
    r'TRUTH\s+TABLE',
]


class DatasheetParser:
    """
    Parses TTL datasheet PDFs to extract chip definitions.
    
    Extracts text-based information and generates partial chip
    definitions that can be completed manually.
    """
    
    def __init__(self, pdf_path: Optional[str] = None):
        """
        Initialize the parser.
        
        Args:
            pdf_path: Path to PDF file (optional, can set later)
        """
        self.pdf_path = Path(pdf_path) if pdf_path else None
        self.extracted_chips: List[ExtractedChip] = []
        self.raw_pages: List[str] = []
        
        if not PDF_AVAILABLE:
            logger.warning("PDF parsing requires 'pdfplumber'. Install with: pip install pdfplumber")
    
    def load_pdf(self, pdf_path: str) -> bool:
        """
        Load a PDF file for parsing.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            True if loaded successfully
        """
        self.pdf_path = Path(pdf_path)
        
        if not self.pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return False
        
        if not PDF_AVAILABLE:
            logger.error("pdfplumber not installed")
            return False
        
        logger.info(f"Loading PDF: {pdf_path}")
        return True
    
    def extract_text_from_pages(self, start_page: int = 0, 
                                end_page: Optional[int] = None) -> List[str]:
        """
        Extract text from PDF pages.
        
        Args:
            start_page: First page to extract (0-indexed)
            end_page: Last page (None = all pages)
        
        Returns:
            List of page texts
        """
        if not PDF_AVAILABLE or not self.pdf_path:
            return []
        
        pages = []
        
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                total_pages = len(pdf.pages)
                end = min(end_page or total_pages, total_pages)
                
                logger.info(f"Extracting pages {start_page} to {end} of {total_pages}")
                
                for i in range(start_page, end):
                    page = pdf.pages[i]
                    text = page.extract_text() or ""
                    pages.append(text)
                    
                    if (i + 1) % 50 == 0:
                        logger.debug(f"Processed {i + 1}/{end} pages")
        
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
        
        self.raw_pages = pages
        return pages
    
    def find_chip_pages(self, text_pages: List[str]) -> Dict[str, List[int]]:
        """
        Find pages that contain chip definitions.
        
        Args:
            text_pages: List of page texts
        
        Returns:
            Dict mapping chip IDs to page numbers
        """
        chip_pages = {}
        
        for page_num, text in enumerate(text_pages):
            # Find all chip IDs on this page
            for pattern in CHIP_ID_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    chip_id = f"74{match.upper()}" if not match.startswith('74') else match.upper()
                    
                    if chip_id not in chip_pages:
                        chip_pages[chip_id] = []
                    
                    if page_num not in chip_pages[chip_id]:
                        chip_pages[chip_id].append(page_num)
        
        logger.info(f"Found {len(chip_pages)} unique chip IDs")
        return chip_pages
    
    def extract_chip_info(self, chip_id: str, page_text: str, 
                         page_num: int) -> Optional[ExtractedChip]:
        """
        Extract chip information from a page.
        
        Args:
            chip_id: Chip identifier
            page_text: Text content of the page
            page_num: Page number
        
        Returns:
            ExtractedChip or None if extraction failed
        """
        needs_review = []
        confidence = 0.0
        
        # Extract function/name
        name, func_type = self._extract_function_name(page_text, chip_id)
        if name:
            confidence += 0.2
        else:
            needs_review.append("Function name not found")
            name = f"IC {chip_id}"
        
        # Extract description
        description = self._extract_description(page_text, chip_id)
        if description:
            confidence += 0.15
        else:
            needs_review.append("Description not found")
            description = ""
        
        # Detect pin count
        pin_count = self._detect_pin_count(page_text)
        if pin_count:
            confidence += 0.15
        else:
            needs_review.append("Pin count not detected")
            pin_count = 14  # Default assumption for 74xx
        
        # Extract truth table
        truth_table, inputs, outputs = self._extract_truth_table(page_text)
        if truth_table:
            confidence += 0.3
        else:
            needs_review.append("Truth table not extracted - manual entry needed")
        
        # Always need manual pin mapping
        needs_review.append("Pin numbers need manual entry from diagram")
        
        return ExtractedChip(
            chip_id=chip_id,
            name=name,
            description=description,
            pin_count=pin_count,
            function_type=func_type or "unknown",
            truth_table=truth_table,
            inputs=inputs,
            outputs=outputs,
            page_number=page_num,
            confidence=min(confidence, 1.0),
            needs_review=needs_review,
            raw_text=page_text[:500]  # First 500 chars for reference
        )
    
    def _extract_function_name(self, text: str, chip_id: str) -> Tuple[str, Optional[str]]:
        """Extract the function name and type from text"""
        # Look for patterns like "QUAD 2-INPUT NAND GATE"
        patterns = [
            rf'{chip_id}\s*[-–]\s*([A-Z][A-Za-z0-9\s\-]+)',
            rf'({chip_id}[A-Z]*)\s+([A-Z][A-Za-z0-9\s\-]+(?:GATE|COUNTER|FLIP-?FLOP|DECODER|BUFFER))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Determine function type
                func_type = self._classify_function(name)
                return name.title(), func_type
        
        # Try to find function type from keywords
        func_type = self._classify_function(text[:500])
        return None, func_type
    
    def _classify_function(self, text: str) -> Optional[str]:
        """Classify chip function from text"""
        text_lower = text.lower()
        
        for func_type, keywords in FUNCTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return func_type
        
        return None
    
    def _extract_description(self, text: str, chip_id: str) -> str:
        """Extract description text"""
        # Look for description section
        patterns = [
            rf'DESCRIPTION[:\s]+(.+?)(?=FEATURES|APPLICATIONS|ABSOLUTE)',
            rf'{chip_id}[A-Z]*\s+(.+?)(?=\n\n|\nFEATURES)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                desc = match.group(1).strip()
                # Clean up
                desc = re.sub(r'\s+', ' ', desc)
                return desc[:300]  # Limit length
        
        return ""
    
    def _detect_pin_count(self, text: str) -> Optional[int]:
        """Detect pin count from text"""
        patterns = [
            r'(\d+)[- ]PIN',
            r'(\d+)P\s+PACKAGE',
            r'DIP[- ]?(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                count = int(match.group(1))
                if count in [8, 14, 16, 20, 24, 28, 40]:  # Valid DIP sizes
                    return count
        
        return None
    
    def _extract_truth_table(self, text: str) -> Tuple[List[Dict], List[str], List[str]]:
        """
        Extract truth table from text.
        
        Returns:
            (truth_table_rows, input_names, output_names)
        """
        truth_table = []
        inputs = []
        outputs = []
        
        # Look for truth table section
        for header_pattern in TRUTH_TABLE_HEADERS:
            match = re.search(header_pattern, text, re.IGNORECASE)
            if match:
                # Extract table area (next 20 lines or so)
                start_pos = match.end()
                table_text = text[start_pos:start_pos + 1000]
                
                # Try to parse as simple text table
                lines = table_text.split('\n')
                
                # Find header row with column names
                for i, line in enumerate(lines[:5]):
                    if re.search(r'[A-Z]\s+[A-Z]', line):
                        # This looks like a header
                        cols = line.split()
                        
                        # Classify as input or output
                        # Common output indicators: Y, Q, Z, OUT
                        for col in cols:
                            col = col.strip()
                            if col in ['Y', 'Q', 'Z', 'OUT', 'OUTPUT'] or col.endswith('Y'):
                                outputs.append(col)
                            elif col not in ['', 'INPUTS', 'OUTPUTS']:
                                inputs.append(col)
                        
                        # Parse data rows
                        for data_line in lines[i+1:i+20]:
                            values = data_line.split()
                            if len(values) == len(cols) and all(v in ['H', 'L', 'X', '0', '1', 'HIGH', 'LOW'] for v in values):
                                row = {}
                                for col, val in zip(cols, values):
                                    row[col] = 'HIGH' if val in ['H', '1', 'HIGH'] else 'LOW' if val in ['L', '0', 'LOW'] else 'X'
                                truth_table.append(row)
                        
                        break
        
        return truth_table, inputs, outputs
    
    def extract_all_chips(self, start_page: int = 0, 
                         end_page: Optional[int] = None) -> List[ExtractedChip]:
        """
        Extract all chips from the PDF.
        
        Args:
            start_page: First page to process
            end_page: Last page (None = all)
        
        Returns:
            List of extracted chips
        """
        if not self.raw_pages:
            self.extract_text_from_pages(start_page, end_page)
        
        chip_pages = self.find_chip_pages(self.raw_pages)
        
        for chip_id, pages in chip_pages.items():
            # Use first page where chip appears
            page_num = pages[0]
            page_text = self.raw_pages[page_num]
            
            chip = self.extract_chip_info(chip_id, page_text, page_num)
            if chip:
                self.extracted_chips.append(chip)
        
        # Sort by chip ID
        self.extracted_chips.sort(key=lambda c: c.chip_id)
        
        logger.info(f"Extracted {len(self.extracted_chips)} chip definitions")
        return self.extracted_chips
    
    def export_to_json(self, output_dir: str, 
                      min_confidence: float = 0.3) -> List[str]:
        """
        Export extracted chips to JSON files.
        
        Args:
            output_dir: Directory to save JSON files
            min_confidence: Minimum confidence to export
        
        Returns:
            List of created file paths
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        created_files = []
        
        for chip in self.extracted_chips:
            if chip.confidence >= min_confidence:
                filename = output_path / f"{chip.chip_id}_draft.json"
                
                with open(filename, 'w') as f:
                    json.dump(chip.to_chip_json(), f, indent=2)
                
                created_files.append(str(filename))
                logger.debug(f"Created {filename}")
        
        logger.info(f"Exported {len(created_files)} chip definitions to {output_dir}")
        return created_files
    
    def get_extraction_summary(self) -> str:
        """Get summary of extraction results"""
        if not self.extracted_chips:
            return "No chips extracted yet."
        
        high_conf = sum(1 for c in self.extracted_chips if c.confidence >= 0.5)
        med_conf = sum(1 for c in self.extracted_chips if 0.3 <= c.confidence < 0.5)
        low_conf = sum(1 for c in self.extracted_chips if c.confidence < 0.3)
        
        lines = [
            f"📄 Extraction Summary",
            f"   Total chips found: {len(self.extracted_chips)}",
            f"   High confidence (≥50%): {high_conf}",
            f"   Medium confidence (30-50%): {med_conf}",
            f"   Low confidence (<30%): {low_conf}",
            "",
            "   Note: All chips need manual pin mapping review",
        ]
        
        return "\n".join(lines)


def check_pdf_requirements() -> Dict[str, bool]:
    """Check which PDF libraries are available"""
    return {
        "pdfplumber": PDF_AVAILABLE,
        "PyMuPDF": PYMUPDF_AVAILABLE,
        "any_available": PDF_AVAILABLE or PYMUPDF_AVAILABLE
    }
