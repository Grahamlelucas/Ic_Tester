# ic_tester_app/intelligence/educator.py
# Last edited: 2026-01-19
# Purpose: Educational assistant that provides contextual learning hints and explanations
# Dependencies: knowledge_base, session_tracker

"""
Chip Educator module.

Provides contextual educational content including:
- Just-in-time learning hints
- Explanations of test failures
- Chip functionality tutorials
- Wiring guidance
- Progress-aware suggestions
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .knowledge_base import ChipKnowledge, ChipInsight
from .session_tracker import SessionTracker
from ..logger import get_logger

logger = get_logger("intelligence.educator")


@dataclass
class LearningHint:
    """A contextual learning hint"""
    title: str
    content: str
    hint_type: str  # 'tip', 'warning', 'explanation', 'challenge'
    priority: int  # 1=high, 2=medium, 3=low
    related_chips: List[str]


@dataclass
class TestExplanation:
    """Explanation of what a test does and why it matters"""
    test_name: str
    what_it_tests: str
    why_it_matters: str
    common_failure_causes: List[str]
    learning_points: List[str]


class ChipEducator:
    """
    Educational assistant for IC chip learning.
    
    Provides contextual, adaptive educational content based on:
    - Current chip being tested
    - User's learning history
    - Test results and failures
    - Progression through chip families
    """
    
    def __init__(self, knowledge: ChipKnowledge, tracker: SessionTracker):
        """
        Initialize the educator.
        
        Args:
            knowledge: ChipKnowledge instance
            tracker: SessionTracker instance
        """
        self.knowledge = knowledge
        self.tracker = tracker
        logger.debug("ChipEducator initialized")
    
    def get_chip_introduction(self, chip_id: str) -> Dict[str, Any]:
        """
        Get an introduction to a chip for learning purposes.
        
        Args:
            chip_id: Chip ID to introduce
        
        Returns:
            Dict with educational content about the chip
        """
        insight = self.knowledge.get_chip_insight(chip_id)
        family_name = self.knowledge.get_chip_family(chip_id)
        family = self.knowledge.get_family_info(family_name) if family_name else None
        
        intro = {
            "chip_id": chip_id,
            "plain_english": insight.plain_english if insight else f"IC chip {chip_id}",
            "difficulty": insight.difficulty_level if insight else 1,
            "family": family_name or "unknown",
            "family_description": family.description if family else "",
            "real_world_uses": insight.real_world_uses if insight else [],
            "prerequisites": insight.prerequisite_concepts if insight else [],
            "tips_before_testing": [],
            "user_history": None
        }
        
        # Add tips for first-time users
        if insight:
            intro["tips_before_testing"] = [
                f"📌 {tip}" for tip in insight.tips[:3]
            ]
        
        # Add user-specific context
        stats = self.tracker.get_chip_stats(chip_id)
        if stats:
            success_rate = stats.successful_tests / stats.total_tests if stats.total_tests > 0 else 0
            intro["user_history"] = {
                "times_tested": stats.total_tests,
                "success_rate": f"{success_rate:.0%}",
                "improving": self.tracker.is_improving(chip_id),
                "last_tested": stats.last_tested[:10] if stats.last_tested else "never"
            }
            
            # Add personalized tip if struggling
            if success_rate < 0.5 and stats.total_tests >= 3:
                common_failures = self.tracker.get_common_failures(chip_id)
                if common_failures:
                    intro["tips_before_testing"].insert(0, 
                        f"⚠️ Watch out! You often have issues with: {common_failures[0][0].replace('_', ' ')}"
                    )
        
        return intro
    
    def get_pre_test_hints(self, chip_id: str) -> List[LearningHint]:
        """
        Get hints to show before running a test.
        
        Args:
            chip_id: Chip ID about to be tested
        
        Returns:
            List of relevant hints
        """
        hints = []
        insight = self.knowledge.get_chip_insight(chip_id)
        stats = self.tracker.get_chip_stats(chip_id)
        
        # First time testing this chip
        if not stats or stats.total_tests == 0:
            hints.append(LearningHint(
                title="First Time Testing",
                content=f"This is your first time testing the {chip_id}. "
                       f"Take your time verifying your wiring before running the test.",
                hint_type="tip",
                priority=1,
                related_chips=[chip_id]
            ))
            
            if insight:
                hints.append(LearningHint(
                    title="What This Chip Does",
                    content=insight.plain_english,
                    hint_type="explanation",
                    priority=1,
                    related_chips=[chip_id]
                ))
        
        # Common mistakes for this chip
        if insight and insight.common_mistakes:
            for mistake in insight.common_mistakes[:2]:
                hints.append(LearningHint(
                    title="Common Mistake Alert",
                    content=mistake,
                    hint_type="warning",
                    priority=2,
                    related_chips=[chip_id]
                ))
        
        # User-specific warnings based on history
        if stats and stats.total_tests >= 2:
            success_rate = stats.successful_tests / stats.total_tests
            
            if success_rate < 0.5:
                common_failures = self.tracker.get_common_failures(chip_id)
                if common_failures:
                    top_failure, count = common_failures[0]
                    hints.append(LearningHint(
                        title="From Your History",
                        content=f"You've had '{top_failure.replace('_', ' ')}' issues "
                               f"{count} times with this chip. Double-check before testing.",
                        hint_type="warning",
                        priority=1,
                        related_chips=[chip_id]
                    ))
        
        # Sort by priority
        hints.sort(key=lambda h: h.priority)
        return hints
    
    def get_post_test_explanation(self, chip_id: str, 
                                  results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get educational explanation after a test.
        
        Args:
            chip_id: Chip that was tested
            results: Test results
        
        Returns:
            Dict with explanation, learning points, and next steps
        """
        explanation = {
            "summary": "",
            "learning_points": [],
            "what_to_try_next": [],
            "related_concepts": [],
            "celebration": None
        }
        
        insight = self.knowledge.get_chip_insight(chip_id)
        success = results.get('success', False)
        tests_passed = results.get('testsPassed', 0)
        tests_total = results.get('testsRun', 0)
        
        if success:
            # Test passed - celebrate and suggest next steps
            explanation["summary"] = f"✅ Great job! The {chip_id} passed all tests."
            explanation["celebration"] = self._get_celebration(chip_id)
            
            # Learning points for successful test
            if insight:
                explanation["learning_points"] = [
                    f"You verified that this {insight.family} chip works correctly.",
                    f"The {chip_id} is a {insight.plain_english.lower()}"
                ]
                
                # Suggest related chips
                for related in insight.related_chips[:2]:
                    explanation["what_to_try_next"].append(
                        f"Try testing the {related} - it's related to the {chip_id}"
                    )
            
            # Check if user just mastered this chip
            stats = self.tracker.get_chip_stats(chip_id)
            if stats and stats.total_tests >= 3:
                rate = stats.successful_tests / stats.total_tests
                if rate >= 0.9:
                    explanation["learning_points"].append(
                        f"🏆 You've mastered the {chip_id}! ({rate:.0%} success rate)"
                    )
        else:
            # Test failed - provide educational explanation
            explanation["summary"] = self._explain_failure(chip_id, results)
            
            # Learning points from failure
            if not results.get('pinsVerified', True):
                explanation["learning_points"].extend([
                    "Each wire must connect the correct chip pin to Arduino pin",
                    "Double-check your pin mapping matches your physical wiring",
                    "Loose connections are a common cause of failures"
                ])
            
            if tests_passed > 0 and tests_passed < tests_total:
                pct = tests_passed / tests_total * 100
                explanation["learning_points"].append(
                    f"You passed {tests_passed}/{tests_total} tests ({pct:.0f}%) - "
                    f"this suggests a partial wiring issue, not a bad chip"
                )
            
            # Suggest what to try
            explanation["what_to_try_next"] = [
                "Review your wiring carefully against the pin mapping",
                "Check that all connections are firm",
                "Verify the chip orientation (notch indicates pin 1)"
            ]
            
            # Add common mistakes for this chip
            if insight:
                for mistake in insight.common_mistakes[:2]:
                    if mistake not in explanation["learning_points"]:
                        explanation["learning_points"].append(f"Common issue: {mistake}")
        
        # Related concepts
        if insight:
            explanation["related_concepts"] = insight.prerequisite_concepts
        
        return explanation
    
    def _explain_failure(self, chip_id: str, results: Dict[str, Any]) -> str:
        """Generate a human-readable failure explanation"""
        if not results.get('pinsVerified', True):
            return (f"❌ Pin connection issues detected for {chip_id}. "
                   f"Some wires may be loose or connected to wrong pins.")
        
        tests_passed = results.get('testsPassed', 0)
        tests_total = results.get('testsRun', 0)
        
        if tests_total == 0:
            return f"❌ No tests could run for {chip_id}. Check connections."
        
        if tests_passed == 0:
            return (f"❌ All {tests_total} tests failed for {chip_id}. "
                   f"This may indicate wrong chip or reversed orientation.")
        
        return (f"❌ {chip_id} failed {tests_total - tests_passed}/{tests_total} tests. "
               f"Partial failures usually indicate wiring issues.")
    
    def _get_celebration(self, chip_id: str) -> str:
        """Get a celebration message for passing a test"""
        stats = self.tracker.get_chip_stats(chip_id)
        
        if not stats:
            return "🎉 First successful test of this chip!"
        
        if stats.total_tests == 1:
            return "🎉 Perfect on your first try!"
        
        if stats.successful_tests >= 5:
            return f"🌟 You're getting really good at this! {stats.successful_tests} successful tests!"
        
        if self.tracker.is_improving(chip_id):
            return "📈 You're improving with this chip!"
        
        return "✓ Test passed successfully!"
    
    def get_wiring_guide(self, chip_id: str, chip_data: Dict) -> Dict[str, Any]:
        """
        Get a step-by-step wiring guide for a chip.
        
        Args:
            chip_id: Chip ID
            chip_data: Chip definition data
        
        Returns:
            Dict with wiring instructions
        """
        pinout = chip_data.get('pinout', {})
        
        guide = {
            "chip_id": chip_id,
            "steps": [],
            "warnings": [],
            "verification_tips": []
        }
        
        # Step 1: Always start with power
        vcc_pin = pinout.get('vcc', 14)
        gnd_pin = pinout.get('gnd', 7)
        
        guide["steps"].append({
            "step": 1,
            "title": "Connect Power First",
            "description": f"Connect chip pin {vcc_pin} (VCC) to Arduino 5V",
            "why": "Power must be connected before any other pins"
        })
        
        guide["steps"].append({
            "step": 2,
            "title": "Connect Ground",
            "description": f"Connect chip pin {gnd_pin} (GND) to Arduino GND",
            "why": "Ground provides the reference for all signals"
        })
        
        # Steps for inputs
        inputs = pinout.get('inputs', [])
        for i, inp in enumerate(inputs):
            guide["steps"].append({
                "step": 3 + i,
                "title": f"Connect Input: {inp.get('name', f'Input {i+1}')}",
                "description": f"Connect chip pin {inp.get('pin')} to your assigned Arduino pin",
                "why": f"This is an input - the Arduino will send signals here"
            })
        
        # Steps for outputs
        outputs = pinout.get('outputs', [])
        for i, out in enumerate(outputs):
            guide["steps"].append({
                "step": 3 + len(inputs) + i,
                "title": f"Connect Output: {out.get('name', f'Output {i+1}')}",
                "description": f"Connect chip pin {out.get('pin')} to your assigned Arduino pin",
                "why": f"This is an output - the Arduino will read signals from here"
            })
        
        # Add warnings
        guide["warnings"] = [
            "⚠️ Double-check VCC and GND before powering on",
            "⚠️ Ensure chip notch/dot is at pin 1 position",
            "⚠️ Don't leave input pins floating (unconnected)"
        ]
        
        # Verification tips
        guide["verification_tips"] = [
            "Count pins from the notch - pin 1 is left of notch",
            "Verify each wire by tracing from chip to Arduino",
            "Use the Validate button before running tests"
        ]
        
        return guide
    
    def get_concept_explanation(self, concept: str) -> Dict[str, str]:
        """
        Get explanation of a digital logic concept.
        
        Args:
            concept: Concept name (e.g., 'truth_tables', 'edge_triggering')
        
        Returns:
            Dict with title, explanation, and example
        """
        concepts = {
            "truth_tables": {
                "title": "Truth Tables",
                "explanation": "A truth table shows all possible input combinations and "
                              "their corresponding outputs. Each row is one test case.",
                "example": "For AND gate: 0,0→0 | 0,1→0 | 1,0→0 | 1,1→1"
            },
            "edge_triggering": {
                "title": "Edge Triggering",
                "explanation": "Edge-triggered devices respond to signal transitions, not levels. "
                              "A rising edge is when signal goes from LOW to HIGH.",
                "example": "D flip-flop captures D input only at rising clock edge"
            },
            "active_low": {
                "title": "Active Low Signals",
                "explanation": "Active low means the signal is 'on' or 'active' when LOW (0V). "
                              "Often shown with a bar over the name or 'n' suffix.",
                "example": "Reset̅ is active low - hold it HIGH for normal operation"
            },
            "propagation_delay": {
                "title": "Propagation Delay",
                "explanation": "Time it takes for an input change to appear at the output. "
                              "In ripple counters, delays accumulate.",
                "example": "7493 outputs don't change simultaneously due to ripple delay"
            },
            "fan_out": {
                "title": "Fan-Out",
                "explanation": "Maximum number of inputs one output can drive. "
                              "Exceeding fan-out causes unreliable logic levels.",
                "example": "Standard TTL output can drive about 10 TTL inputs"
            },
            "floating_inputs": {
                "title": "Floating Inputs",
                "explanation": "Unconnected inputs pick up noise and act unpredictably. "
                              "Always tie unused inputs to VCC or GND.",
                "example": "Unused NAND inputs should be tied HIGH"
            }
        }
        
        return concepts.get(concept, {
            "title": concept.replace('_', ' ').title(),
            "explanation": "Concept explanation not available.",
            "example": ""
        })
    
    def get_curriculum_suggestion(self) -> Dict[str, Any]:
        """
        Suggest a learning curriculum based on user progress.
        
        Returns:
            Dict with suggested learning path
        """
        progress = self.tracker.user_progress
        mastered = set(progress.chips_mastered)
        learning = set(progress.chips_learning)
        
        curriculum = {
            "current_level": "beginner",
            "next_chips": [],
            "concepts_to_review": [],
            "suggested_projects": []
        }
        
        # Determine level
        basic_gates = {"7400", "7404", "7408", "7432"}
        if basic_gates.issubset(mastered):
            curriculum["current_level"] = "intermediate"
            curriculum["next_chips"] = ["7474", "7486", "7493"]
            curriculum["suggested_projects"] = [
                "Build a divide-by-4 counter with 7474",
                "Create a parity checker with 7486"
            ]
        elif len(mastered) > 0:
            curriculum["current_level"] = "beginner"
            remaining_basic = basic_gates - mastered
            curriculum["next_chips"] = list(remaining_basic)[:2]
            curriculum["suggested_projects"] = [
                "Wire an AND gate to control an LED",
                "Build an inverter from a NAND gate (7400)"
            ]
        else:
            curriculum["next_chips"] = ["7404", "7400"]
            curriculum["suggested_projects"] = [
                "Start with 7404 inverter - simplest to understand",
                "Learn input/output by inverting a signal"
            ]
        
        # Concepts to review based on failures
        if progress.chips_struggling:
            curriculum["concepts_to_review"] = [
                "truth_tables",
                "floating_inputs"
            ]
        
        return curriculum
