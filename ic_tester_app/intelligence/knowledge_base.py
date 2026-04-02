# ic_tester_app/intelligence/knowledge_base.py
# Last edited: 2026-01-19
# Purpose: Chip knowledge base with educational content and common patterns
# Dependencies: json, pathlib

"""
Structured chip knowledge base.

Unlike the runtime tester, this module is mostly static reference material. It
holds the curated facts the rest of the "teaching" features rely on:
- what a chip/family does in plain English,
- what mistakes are common for that part,
- what concepts should be learned before it,
- what related chips make sense next.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from ..logger import get_logger

logger = get_logger("intelligence.knowledge_base")


@dataclass
class ChipFamily:
    """Information about a chip family (e.g., gates, counters, flip-flops)"""
    name: str
    description: str
    typical_applications: List[str]
    related_families: List[str]
    learning_order: int  # For curriculum progression


@dataclass
class ChipInsight:
    """Educational insight about a specific chip"""
    chip_id: str
    family: str
    plain_english: str  # What the chip does in simple terms
    real_world_uses: List[str]
    common_mistakes: List[str]
    tips: List[str]
    related_chips: List[str]
    difficulty_level: int  # 1=beginner, 2=intermediate, 3=advanced
    prerequisite_concepts: List[str]


# Built-in knowledge about 74-series chip families
CHIP_FAMILIES = {
    "gates": ChipFamily(
        name="Logic Gates",
        description="Basic building blocks of digital logic. Perform fundamental Boolean operations.",
        typical_applications=[
            "Signal routing and switching",
            "Building complex logic from simple operations",
            "Input conditioning and signal cleaning",
            "Creating enable/disable circuits"
        ],
        related_families=["buffers", "inverters"],
        learning_order=1
    ),
    "flip_flops": ChipFamily(
        name="Flip-Flops & Latches",
        description="Memory elements that store one bit of data. Foundation of sequential logic.",
        typical_applications=[
            "Data storage and registers",
            "Frequency division",
            "Debouncing switches",
            "State machines"
        ],
        related_families=["counters", "shift_registers"],
        learning_order=2
    ),
    "counters": ChipFamily(
        name="Counters",
        description="Sequential circuits that count pulses. Can count up, down, or both.",
        typical_applications=[
            "Event counting",
            "Frequency measurement",
            "Timer circuits",
            "Address generation",
            "Sequencing operations"
        ],
        related_families=["flip_flops", "decoders"],
        learning_order=3
    ),
    "decoders": ChipFamily(
        name="Decoders & Encoders",
        description="Convert between different data representations (binary to one-hot, etc.)",
        typical_applications=[
            "Address decoding",
            "Display drivers",
            "Multiplexing",
            "Priority encoding"
        ],
        related_families=["multiplexers", "gates"],
        learning_order=3
    ),
    "multiplexers": ChipFamily(
        name="Multiplexers & Demultiplexers",
        description="Route signals between multiple sources and destinations.",
        typical_applications=[
            "Data selection",
            "Bus switching",
            "Time-division multiplexing",
            "Implementing logic functions"
        ],
        related_families=["decoders", "buffers"],
        learning_order=3
    ),
    "shift_registers": ChipFamily(
        name="Shift Registers",
        description="Move data bits in sequence. Can convert serial to parallel and vice versa.",
        typical_applications=[
            "Serial-to-parallel conversion",
            "LED drivers",
            "Data buffering",
            "Delay lines"
        ],
        related_families=["flip_flops", "counters"],
        learning_order=4
    ),
    "arithmetic": ChipFamily(
        name="Arithmetic Units",
        description="Perform mathematical operations like addition and comparison.",
        typical_applications=[
            "ALU building blocks",
            "Address calculation",
            "Magnitude comparison",
            "Parity generation"
        ],
        related_families=["gates", "multiplexers"],
        learning_order=4
    ),
    "buffers": ChipFamily(
        name="Buffers & Drivers",
        description="Amplify signals and provide isolation between circuits.",
        typical_applications=[
            "Bus driving",
            "Signal isolation",
            "Current boosting",
            "Tri-state outputs"
        ],
        related_families=["gates", "inverters"],
        learning_order=2
    )
}

# Built-in insights for common chips
CHIP_INSIGHTS = {
    "7400": ChipInsight(
        chip_id="7400",
        family="gates",
        plain_english="Four independent 2-input NAND gates. NAND outputs LOW only when BOTH inputs are HIGH.",
        real_world_uses=[
            "Building any other logic gate (NAND is universal)",
            "Simple alarm circuits",
            "Button debouncing",
            "Oscillator circuits"
        ],
        common_mistakes=[
            "Forgetting that unused inputs should be tied HIGH or LOW, not left floating",
            "Confusing NAND with AND - outputs are inverted!",
            "Not connecting VCC (pin 14) and GND (pin 7)"
        ],
        tips=[
            "NAND is a 'universal gate' - you can build ANY logic using only NANDs",
            "Two NANDs make an AND gate, one NAND with inputs tied makes an inverter",
            "Test with simple cases: both HIGH should give LOW output"
        ],
        related_chips=["7402", "7404", "7408", "7432"],
        difficulty_level=1,
        prerequisite_concepts=["binary logic", "truth tables"]
    ),
    "7404": ChipInsight(
        chip_id="7404",
        family="gates",
        plain_english="Six independent inverters (NOT gates). Each output is the opposite of its input.",
        real_world_uses=[
            "Signal inversion",
            "Logic level conversion",
            "Oscillator circuits (odd number of inverters)",
            "Buffer with inversion"
        ],
        common_mistakes=[
            "Using wrong pin pairs - check the pinout carefully",
            "Expecting amplification - TTL has specific voltage levels",
            "Creating oscillation by accident with feedback"
        ],
        tips=[
            "Great for learning: input HIGH → output LOW, input LOW → output HIGH",
            "Can create a simple oscillator with a resistor and capacitor",
            "Use for active-low signal generation"
        ],
        related_chips=["7400", "7406", "7414"],
        difficulty_level=1,
        prerequisite_concepts=["binary logic"]
    ),
    "7408": ChipInsight(
        chip_id="7408",
        family="gates",
        plain_english="Four independent 2-input AND gates. Output is HIGH only when BOTH inputs are HIGH.",
        real_world_uses=[
            "Enable/disable signals",
            "Gating clock signals",
            "Combining conditions",
            "Security interlocks"
        ],
        common_mistakes=[
            "Confusing with NAND (7400) - AND has non-inverted output",
            "Floating inputs act unpredictably",
            "Wrong power connections"
        ],
        tips=[
            "Think of AND as a 'both must be true' gate",
            "Useful for combining enable signals",
            "Can be built from two NAND gates"
        ],
        related_chips=["7400", "7411", "7421"],
        difficulty_level=1,
        prerequisite_concepts=["binary logic", "truth tables"]
    ),
    "7432": ChipInsight(
        chip_id="7432",
        family="gates",
        plain_english="Four independent 2-input OR gates. Output is HIGH if EITHER or both inputs are HIGH.",
        real_world_uses=[
            "Combining multiple trigger sources",
            "Interrupt aggregation",
            "Alarm systems (any sensor triggers)",
            "Parallel input selection"
        ],
        common_mistakes=[
            "Confusing with NOR (7402) - OR has non-inverted output",
            "Not realizing both inputs HIGH also gives HIGH output"
        ],
        tips=[
            "Think of OR as 'any input true makes output true'",
            "Good for combining multiple signals into one",
            "Can be built from NAND gates"
        ],
        related_chips=["7402", "7400", "7408"],
        difficulty_level=1,
        prerequisite_concepts=["binary logic", "truth tables"]
    ),
    "7486": ChipInsight(
        chip_id="7486",
        family="gates",
        plain_english="Four independent 2-input XOR (exclusive OR) gates. Output HIGH when inputs are DIFFERENT.",
        real_world_uses=[
            "Parity checking",
            "Comparators (detect difference)",
            "Controlled inversion",
            "Arithmetic circuits (half adder)"
        ],
        common_mistakes=[
            "Thinking XOR is the same as OR - XOR is HIGH only when inputs DIFFER",
            "Forgetting that both HIGH gives LOW output"
        ],
        tips=[
            "XOR is true when inputs are different, false when same",
            "XOR with one input HIGH acts as an inverter",
            "XOR with one input LOW passes the signal through",
            "Key component in adder circuits"
        ],
        related_chips=["7400", "7408", "7483"],
        difficulty_level=2,
        prerequisite_concepts=["binary logic", "truth tables", "basic gates"]
    ),
    "7474": ChipInsight(
        chip_id="7474",
        family="flip_flops",
        plain_english="Two independent D-type flip-flops with SET and RESET. Captures input D on rising clock edge.",
        real_world_uses=[
            "Data latching",
            "Frequency division (connect Q̅ to D)",
            "Shift register building block",
            "Synchronizing asynchronous signals"
        ],
        common_mistakes=[
            "Not understanding edge-triggered vs level-triggered",
            "Leaving SET/RESET floating (should be HIGH for normal operation)",
            "Clock signal quality issues causing multiple triggers"
        ],
        tips=[
            "D flip-flop captures D input at the rising edge of clock",
            "SET forces Q HIGH, RESET forces Q LOW (active LOW inputs)",
            "Connect Q̅ to D for a divide-by-2 counter",
            "Both SET and RESET LOW is an invalid state"
        ],
        related_chips=["7473", "7475", "7476", "74174"],
        difficulty_level=2,
        prerequisite_concepts=["binary logic", "clock signals", "edge triggering"]
    ),
    "7490": ChipInsight(
        chip_id="7490",
        family="counters",
        plain_english="Decade counter (counts 0-9). Has separate divide-by-2 and divide-by-5 sections.",
        real_world_uses=[
            "Frequency counters",
            "Digital clocks",
            "Event counters",
            "BCD output for displays"
        ],
        common_mistakes=[
            "Not connecting the internal sections together for 0-9 counting",
            "Forgetting reset pins need specific states",
            "Clock polarity confusion (negative-edge triggered)"
        ],
        tips=[
            "For 0-9 counting: connect QA to input B",
            "Reset pins R0(1), R0(2), R9(1), R9(2) control counter reset",
            "Both R0 pins HIGH resets to 0, both R9 pins HIGH sets to 9",
            "Output QD QC QB QA gives BCD (0000-1001)"
        ],
        related_chips=["7493", "74390", "74160"],
        difficulty_level=3,
        prerequisite_concepts=["binary counting", "BCD", "clock signals"]
    ),
    "7493": ChipInsight(
        chip_id="7493",
        family="counters",
        plain_english="4-bit binary counter (counts 0-15). Divide-by-2 and divide-by-8 sections.",
        real_world_uses=[
            "Binary frequency division",
            "Address generation",
            "Timing circuits",
            "Sequencing"
        ],
        common_mistakes=[
            "Not connecting QA to input B for full 0-15 counting",
            "Reset pin confusion",
            "Expecting synchronous operation (it's ripple counter)"
        ],
        tips=[
            "For 0-15 counting: connect QA to CKB",
            "CKA drives the first flip-flop, CKB drives the remaining three",
            "Both reset pins (R0) HIGH clears counter to 0000",
            "Ripple counter - outputs don't change simultaneously"
        ],
        related_chips=["7490", "74161", "74393"],
        difficulty_level=2,
        prerequisite_concepts=["binary numbers", "clock signals"]
    ),
    "74138": ChipInsight(
        chip_id="74138",
        family="decoders",
        plain_english="3-to-8 line decoder. Converts 3-bit binary input to one of 8 active-LOW outputs.",
        real_world_uses=[
            "Memory address decoding",
            "I/O port selection",
            "LED row/column drivers",
            "Demultiplexing"
        ],
        common_mistakes=[
            "Forgetting enable pins must be set correctly (G1=H, G2A=L, G2B=L)",
            "Not realizing outputs are active LOW",
            "Misreading which output corresponds to which binary value"
        ],
        tips=[
            "Address inputs A, B, C select which output goes LOW",
            "All other outputs stay HIGH",
            "Three enable inputs allow cascading for larger decoders",
            "Can implement any 3-input logic function"
        ],
        related_chips=["74139", "74154", "74238"],
        difficulty_level=3,
        prerequisite_concepts=["binary numbers", "active low logic"]
    ),
    "74595": ChipInsight(
        chip_id="74595",
        family="shift_registers",
        plain_english="8-bit shift register with output latches. Takes serial data in, provides 8 parallel outputs.",
        real_world_uses=[
            "Expanding output pins (common with Arduino)",
            "LED driver circuits",
            "7-segment display control",
            "SPI peripheral expansion"
        ],
        common_mistakes=[
            "Confusing SRCLK (shift) with RCLK (latch) - both needed",
            "Not pulsing latch clock after shifting all bits",
            "OE pin must be LOW to see outputs"
        ],
        tips=[
            "Shift 8 bits with SRCLK, then pulse RCLK to update outputs",
            "Can be cascaded - QH' connects to next chip's SER",
            "Great for expanding Arduino output pins",
            "SRCLR can reset shift register (active LOW)"
        ],
        related_chips=["74164", "74166", "74299"],
        difficulty_level=3,
        prerequisite_concepts=["serial communication", "shift registers", "latches"]
    )
}

# Common wiring patterns and what they achieve
WIRING_PATTERNS = {
    "inverter_from_nand": {
        "description": "Creating an inverter from a NAND gate",
        "chips": ["7400"],
        "how": "Tie both inputs of a NAND gate together",
        "why": "NAND with same input on both pins acts as NOT gate",
        "educational": "Demonstrates NAND universality"
    },
    "and_from_nands": {
        "description": "Creating AND from two NAND gates",
        "chips": ["7400"],
        "how": "NAND gate output feeds into NAND-as-inverter",
        "why": "NAND followed by NOT = AND",
        "educational": "Shows how any logic can be built from NANDs"
    },
    "divide_by_2": {
        "description": "Frequency divider using D flip-flop",
        "chips": ["7474"],
        "how": "Connect Q̅ (not Q) back to D input, clock is input frequency",
        "why": "Flip-flop toggles on each clock, output frequency is half",
        "educational": "Foundation of counter circuits"
    },
    "decade_counter": {
        "description": "0-9 counter using 7490",
        "chips": ["7490"],
        "how": "Connect QA to input B, clock goes to input A",
        "why": "Combines divide-by-2 and divide-by-5 sections",
        "educational": "BCD counting for digital displays"
    },
    "ripple_counter_16": {
        "description": "Count 0-15 with 7493",
        "chips": ["7493"],
        "how": "Connect QA to CKB, clock goes to CKA",
        "why": "Cascades divide-by-2 with divide-by-8",
        "educational": "Binary counting fundamentals"
    }
}


class ChipKnowledge:
    """
    Central knowledge base for IC chip intelligence.
    
    Provides educational content, common patterns, and insights
    that help users learn about and correctly use 74-series chips.
    """
    
    def __init__(self, custom_knowledge_path: Optional[Path] = None):
        """
        Initialize the knowledge base.
        
        Args:
            custom_knowledge_path: Optional path to custom knowledge JSON
        """
        # Start with the built-in curriculum/reference data, then optionally
        # layer custom JSON knowledge on top for local extensions.
        self.families = CHIP_FAMILIES.copy()
        self.insights = CHIP_INSIGHTS.copy()
        self.patterns = WIRING_PATTERNS.copy()
        
        # Load custom knowledge if provided
        if custom_knowledge_path and custom_knowledge_path.exists():
            self._load_custom_knowledge(custom_knowledge_path)
        
        logger.info(f"Knowledge base initialized with {len(self.insights)} chip insights")
    
    def _load_custom_knowledge(self, path: Path):
        """Load additional knowledge from JSON file"""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            # Merge by chip ID so custom entries can add new chips or override
            # the built-in description/tips for an existing one.
            for chip_id, insight_data in data.get('insights', {}).items():
                self.insights[chip_id] = ChipInsight(**insight_data)
            
            logger.info(f"Loaded custom knowledge from {path}")
        except Exception as e:
            logger.warning(f"Failed to load custom knowledge: {e}")
    
    def get_chip_insight(self, chip_id: str) -> Optional[ChipInsight]:
        """Get educational insight for a chip"""
        return self.insights.get(chip_id)
    
    def get_family_info(self, family_name: str) -> Optional[ChipFamily]:
        """Get information about a chip family"""
        return self.families.get(family_name)
    
    def get_chip_family(self, chip_id: str) -> Optional[str]:
        """Determine which family a chip belongs to"""
        insight = self.insights.get(chip_id)
        return insight.family if insight else None
    
    def get_common_mistakes(self, chip_id: str) -> List[str]:
        """Get list of common mistakes for a chip"""
        insight = self.insights.get(chip_id)
        return insight.common_mistakes if insight else []
    
    def get_tips(self, chip_id: str) -> List[str]:
        """Get tips for working with a chip"""
        insight = self.insights.get(chip_id)
        return insight.tips if insight else []
    
    def get_related_chips(self, chip_id: str) -> List[str]:
        """Get chips related to the specified one"""
        insight = self.insights.get(chip_id)
        return insight.related_chips if insight else []
    
    def get_plain_english(self, chip_id: str) -> str:
        """Get simple explanation of what the chip does"""
        insight = self.insights.get(chip_id)
        return insight.plain_english if insight else f"IC chip {chip_id}"
    
    def get_difficulty_level(self, chip_id: str) -> int:
        """Get difficulty level (1-3) for a chip"""
        insight = self.insights.get(chip_id)
        return insight.difficulty_level if insight else 1
    
    def get_prerequisite_concepts(self, chip_id: str) -> List[str]:
        """Get concepts the user should understand before this chip"""
        insight = self.insights.get(chip_id)
        return insight.prerequisite_concepts if insight else []
    
    def get_wiring_patterns(self, chip_id: str) -> List[Dict]:
        """Get known wiring patterns involving this chip"""
        patterns = []
        for name, pattern in self.patterns.items():
            if chip_id in pattern.get('chips', []):
                patterns.append({**pattern, 'name': name})
        return patterns
    
    def suggest_learning_path(self, current_chip: str) -> List[str]:
        """Suggest next chips to learn based on current chip"""
        insight = self.insights.get(current_chip)
        if not insight:
            return ["7400", "7404"]  # Default starting chips
        
        # Keep the recommendation simple: start from explicit related-chip links,
        # then sort them by difficulty so the path feels like a progression.
        related = []
        for chip_id in insight.related_chips:
            rel_insight = self.insights.get(chip_id)
            if rel_insight:
                related.append((chip_id, rel_insight.difficulty_level))
        
        # Sort by difficulty, then alphabetically
        related.sort(key=lambda x: (x[1], x[0]))
        return [chip_id for chip_id, _ in related]
    
    def get_all_insights_by_difficulty(self, level: int) -> List[str]:
        """Get all chips at a specific difficulty level"""
        return [
            chip_id for chip_id, insight in self.insights.items()
            if insight.difficulty_level == level
        ]
    
    def search_by_application(self, keyword: str) -> List[str]:
        """Find chips useful for a specific application"""
        keyword = keyword.lower()
        matches = []
        
        for chip_id, insight in self.insights.items():
            for use in insight.real_world_uses:
                if keyword in use.lower():
                    matches.append(chip_id)
                    break
        
        return matches
