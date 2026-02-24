# ic_tester_app/intelligence/session_tracker.py
# Last edited: 2026-01-19
# Purpose: Track test sessions and learn from user patterns over time
# Dependencies: json, pathlib, datetime

"""
Session Tracker module.

Records and analyzes test sessions to:
- Track which chips are tested most frequently
- Identify recurring failure patterns
- Measure user improvement over time
- Build personalized recommendations
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from ..config import Config
from ..logger import get_logger

logger = get_logger("intelligence.session_tracker")


@dataclass
class TestResult:
    """Record of a single test attempt"""
    chip_id: str
    timestamp: str
    success: bool
    tests_passed: int
    tests_failed: int
    tests_total: int
    failure_reasons: List[str] = field(default_factory=list)
    pin_mapping_used: Dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    notes: str = ""


@dataclass 
class ChipStats:
    """Aggregated statistics for a chip"""
    chip_id: str
    total_tests: int = 0
    successful_tests: int = 0
    failed_tests: int = 0
    first_tested: str = ""
    last_tested: str = ""
    common_failures: Dict[str, int] = field(default_factory=dict)
    average_duration: float = 0.0
    improvement_trend: float = 0.0  # Positive = improving


@dataclass
class UserProgress:
    """Track user learning progress"""
    chips_mastered: List[str] = field(default_factory=list)  # >90% success rate
    chips_learning: List[str] = field(default_factory=list)  # 50-90% success
    chips_struggling: List[str] = field(default_factory=list)  # <50% success
    total_sessions: int = 0
    total_chips_tested: int = 0
    overall_success_rate: float = 0.0
    learning_streak: int = 0  # Days in a row with testing
    last_session_date: str = ""


class SessionTracker:
    """
    Tracks test sessions and learns from user patterns.
    
    Stores session data locally and analyzes it to provide:
    - Performance trends
    - Common mistake identification
    - Personalized recommendations
    - Learning progress tracking
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize the session tracker.
        
        Args:
            data_dir: Directory for storing session data
        """
        self.data_dir = data_dir or Config.BASE_DIR / "session_data"
        self.data_dir.mkdir(exist_ok=True)
        
        self.history_file = self.data_dir / "test_history.json"
        self.stats_file = self.data_dir / "chip_stats.json"
        self.progress_file = self.data_dir / "user_progress.json"
        
        # Load existing data
        self.history: List[TestResult] = []
        self.chip_stats: Dict[str, ChipStats] = {}
        self.user_progress = UserProgress()
        
        self._load_data()
        logger.info(f"Session tracker initialized with {len(self.history)} historical records")
    
    def _load_data(self):
        """Load existing session data from files"""
        # Load history
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                self.history = [TestResult(**r) for r in data]
            except Exception as e:
                logger.warning(f"Could not load history: {e}")
        
        # Load chip stats
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                self.chip_stats = {k: ChipStats(**v) for k, v in data.items()}
            except Exception as e:
                logger.warning(f"Could not load stats: {e}")
        
        # Load user progress
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
                self.user_progress = UserProgress(**data)
            except Exception as e:
                logger.warning(f"Could not load progress: {e}")
    
    def _save_data(self):
        """Save session data to files"""
        try:
            # Save history
            with open(self.history_file, 'w') as f:
                json.dump([asdict(r) for r in self.history], f, indent=2)
            
            # Save chip stats
            with open(self.stats_file, 'w') as f:
                json.dump({k: asdict(v) for k, v in self.chip_stats.items()}, f, indent=2)
            
            # Save user progress
            with open(self.progress_file, 'w') as f:
                json.dump(asdict(self.user_progress), f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save session data: {e}")
    
    def record_test(self, chip_id: str, results: Dict[str, Any], 
                   pin_mapping: Dict[str, int] = None,
                   duration: float = 0.0) -> TestResult:
        """
        Record a test result.
        
        Args:
            chip_id: ID of the chip tested
            results: Test results dictionary
            pin_mapping: Pin mapping used for test
            duration: Test duration in seconds
        
        Returns:
            The recorded TestResult
        """
        now = datetime.now().isoformat()
        
        # Extract failure reasons from results
        failure_reasons = []
        if not results.get('pinsVerified', True):
            failure_reasons.append("pin_verification_failed")
        if results.get('failedTests'):
            for test in results['failedTests']:
                failure_reasons.append(f"test_{test.get('name', 'unknown')}")
        
        # Create test result
        result = TestResult(
            chip_id=chip_id,
            timestamp=now,
            success=results.get('success', False),
            tests_passed=results.get('testsPassed', 0),
            tests_failed=results.get('testsFailed', 0),
            tests_total=results.get('testsRun', 0),
            failure_reasons=failure_reasons,
            pin_mapping_used=pin_mapping or {},
            duration_seconds=duration
        )
        
        # Add to history
        self.history.append(result)
        
        # Update chip stats
        self._update_chip_stats(chip_id, result)
        
        # Update user progress
        self._update_user_progress()
        
        # Save to disk
        self._save_data()
        
        logger.info(f"Recorded test for {chip_id}: {'PASS' if result.success else 'FAIL'}")
        return result
    
    def _update_chip_stats(self, chip_id: str, result: TestResult):
        """Update aggregated statistics for a chip"""
        if chip_id not in self.chip_stats:
            self.chip_stats[chip_id] = ChipStats(
                chip_id=chip_id,
                first_tested=result.timestamp
            )
        
        stats = self.chip_stats[chip_id]
        stats.total_tests += 1
        stats.last_tested = result.timestamp
        
        if result.success:
            stats.successful_tests += 1
        else:
            stats.failed_tests += 1
            # Track common failures
            for reason in result.failure_reasons:
                stats.common_failures[reason] = stats.common_failures.get(reason, 0) + 1
        
        # Update average duration
        if result.duration_seconds > 0:
            n = stats.total_tests
            stats.average_duration = (
                (stats.average_duration * (n - 1) + result.duration_seconds) / n
            )
        
        # Calculate improvement trend (compare recent vs older tests)
        self._calculate_improvement_trend(chip_id)
    
    def _calculate_improvement_trend(self, chip_id: str):
        """Calculate if user is improving with a chip"""
        chip_history = [r for r in self.history if r.chip_id == chip_id]
        
        if len(chip_history) < 4:
            return  # Not enough data
        
        # Compare first half vs second half success rates
        mid = len(chip_history) // 2
        first_half = chip_history[:mid]
        second_half = chip_history[mid:]
        
        first_rate = sum(1 for r in first_half if r.success) / len(first_half)
        second_rate = sum(1 for r in second_half if r.success) / len(second_half)
        
        self.chip_stats[chip_id].improvement_trend = second_rate - first_rate
    
    def _update_user_progress(self):
        """Update overall user progress metrics"""
        if not self.chip_stats:
            return
        
        mastered = []
        learning = []
        struggling = []
        
        for chip_id, stats in self.chip_stats.items():
            if stats.total_tests < 2:
                continue
            
            success_rate = stats.successful_tests / stats.total_tests
            
            if success_rate >= 0.9:
                mastered.append(chip_id)
            elif success_rate >= 0.5:
                learning.append(chip_id)
            else:
                struggling.append(chip_id)
        
        self.user_progress.chips_mastered = mastered
        self.user_progress.chips_learning = learning
        self.user_progress.chips_struggling = struggling
        self.user_progress.total_sessions = len(self.history)
        self.user_progress.total_chips_tested = len(self.chip_stats)
        
        # Calculate overall success rate
        total_success = sum(s.successful_tests for s in self.chip_stats.values())
        total_tests = sum(s.total_tests for s in self.chip_stats.values())
        
        if total_tests > 0:
            self.user_progress.overall_success_rate = total_success / total_tests
        
        # Update last session date
        if self.history:
            self.user_progress.last_session_date = self.history[-1].timestamp[:10]
    
    def get_chip_stats(self, chip_id: str) -> Optional[ChipStats]:
        """Get statistics for a specific chip"""
        return self.chip_stats.get(chip_id)
    
    def get_success_rate(self, chip_id: str) -> float:
        """Get success rate for a chip (0.0 - 1.0)"""
        stats = self.chip_stats.get(chip_id)
        if not stats or stats.total_tests == 0:
            return 0.0
        return stats.successful_tests / stats.total_tests
    
    def get_common_failures(self, chip_id: str) -> List[tuple]:
        """Get most common failure reasons for a chip, sorted by frequency"""
        stats = self.chip_stats.get(chip_id)
        if not stats:
            return []
        
        return sorted(
            stats.common_failures.items(),
            key=lambda x: x[1],
            reverse=True
        )
    
    def get_recent_tests(self, limit: int = 10) -> List[TestResult]:
        """Get most recent test results"""
        return self.history[-limit:]
    
    def get_chip_history(self, chip_id: str, limit: int = 20) -> List[TestResult]:
        """Get test history for a specific chip"""
        return [r for r in self.history if r.chip_id == chip_id][-limit:]
    
    def get_struggling_chips(self) -> List[str]:
        """Get chips the user is struggling with"""
        return self.user_progress.chips_struggling
    
    def get_mastered_chips(self) -> List[str]:
        """Get chips the user has mastered"""
        return self.user_progress.chips_mastered
    
    def is_improving(self, chip_id: str) -> bool:
        """Check if user is improving with a chip"""
        stats = self.chip_stats.get(chip_id)
        return stats is not None and stats.improvement_trend > 0
    
    def get_recommendations(self) -> Dict[str, Any]:
        """Get personalized recommendations based on history"""
        recommendations = {
            "practice_more": [],  # Chips to practice more
            "ready_for_next": [],  # Ready to learn new chips
            "review_basics": False,
            "focus_areas": []
        }
        
        # Chips needing more practice (learning category with < 80% success)
        for chip_id in self.user_progress.chips_learning:
            rate = self.get_success_rate(chip_id)
            if rate < 0.8:
                recommendations["practice_more"].append(chip_id)
        
        # Check if struggling with basic chips (gates)
        basic_chips = ["7400", "7404", "7408", "7432"]
        struggling_basics = [c for c in basic_chips if c in self.user_progress.chips_struggling]
        
        if struggling_basics:
            recommendations["review_basics"] = True
            recommendations["focus_areas"].append(
                f"Review basic gate chips: {', '.join(struggling_basics)}"
            )
        
        # If mastering basics, suggest moving to flip-flops
        if all(c in self.user_progress.chips_mastered for c in basic_chips):
            recommendations["ready_for_next"].extend(["7474", "7475"])
        
        # Identify common failure patterns across all chips
        all_failures = defaultdict(int)
        for stats in self.chip_stats.values():
            for reason, count in stats.common_failures.items():
                all_failures[reason] += count
        
        if all_failures.get("power_verification_failed", 0) > 3:
            recommendations["focus_areas"].append(
                "Double-check power connections - VCC to 5V, GND to ground"
            )
        
        if all_failures.get("pin_verification_failed", 0) > 3:
            recommendations["focus_areas"].append(
                "Verify wire connections match pin mapping before testing"
            )
        
        return recommendations
    
    def get_progress_summary(self) -> str:
        """Get a human-readable progress summary"""
        p = self.user_progress
        
        if p.total_sessions == 0:
            return "No tests recorded yet. Start testing to track your progress!"
        
        lines = [
            f"📊 **Your Progress**",
            f"Total tests: {p.total_sessions}",
            f"Success rate: {p.overall_success_rate:.0%}",
            f"Chips tested: {p.total_chips_tested}",
            ""
        ]
        
        if p.chips_mastered:
            lines.append(f"✅ Mastered ({len(p.chips_mastered)}): {', '.join(p.chips_mastered)}")
        
        if p.chips_learning:
            lines.append(f"📚 Learning ({len(p.chips_learning)}): {', '.join(p.chips_learning)}")
        
        if p.chips_struggling:
            lines.append(f"⚠️ Need practice ({len(p.chips_struggling)}): {', '.join(p.chips_struggling)}")
        
        return "\n".join(lines)
    
    def export_data(self, filepath: Path) -> bool:
        """Export all session data to a JSON file"""
        try:
            export = {
                "exported_at": datetime.now().isoformat(),
                "history": [asdict(r) for r in self.history],
                "chip_stats": {k: asdict(v) for k, v in self.chip_stats.items()},
                "user_progress": asdict(self.user_progress)
            }
            
            with open(filepath, 'w') as f:
                json.dump(export, f, indent=2)
            
            logger.info(f"Exported session data to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export data: {e}")
            return False
