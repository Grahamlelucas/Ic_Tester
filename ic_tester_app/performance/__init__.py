# ic_tester_app/performance/__init__.py
# Last edited: 2026-03-19
# Purpose: Performance analysis and benchmarking package
# Dependencies: See individual modules

"""
Performance Analysis Package for IC Tester.

Provides:
- Benchmark: Arduino communication and pin I/O performance measurement
- Limits documentation for the Arduino Mega 2560 platform
"""

from .benchmark import PerformanceBenchmark

__all__ = ['PerformanceBenchmark']
