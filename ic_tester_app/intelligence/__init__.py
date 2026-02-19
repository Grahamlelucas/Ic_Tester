# ic_tester_app/intelligence/__init__.py
# Last edited: 2026-01-19
# Purpose: Intelligent learning system for IC chip education and testing assistance
# Dependencies: None

"""
Intelligence module for IC Tester.

Provides AI-like capabilities for:
- Learning from test sessions
- Pattern recognition for wiring mistakes
- Educational hints about chip functionality
- Confidence scoring
- Common error detection
"""

from .knowledge_base import ChipKnowledge
from .session_tracker import SessionTracker
from .pattern_analyzer import PatternAnalyzer
from .educator import ChipEducator
from .datasheet_parser import DatasheetParser, check_pdf_requirements

__all__ = [
    'ChipKnowledge',
    'SessionTracker', 
    'PatternAnalyzer',
    'ChipEducator',
    'DatasheetParser',
    'check_pdf_requirements'
]
