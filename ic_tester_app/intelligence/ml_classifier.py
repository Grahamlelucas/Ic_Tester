# ic_tester_app/intelligence/ml_classifier.py
# Last edited: 2026-03-19
# Purpose: Machine learning fault classifier that learns from accumulated test data
# Dependencies: json, math, pathlib, dataclasses
# Related: intelligence/pattern_analyzer.py, diagnostics/diagnostic_report.py

"""
ML Fault Classifier module.

Lightweight ML classifier that runs entirely on the host PC (not the Arduino).
Uses a k-nearest-neighbors approach with feature extraction from test results
to classify hardware faults into categories:

- open_pin: Pin not physically connected
- shorted_pin: Pin shorted to VCC or GND
- floating_pin: Input left unconnected, reads random values
- timing_unstable: Pin responds but with inconsistent timing
- degraded_gate: Gate operates but with reduced drive strength

The model improves over time as test data accumulates in the training set.
No external ML libraries required — uses pure Python with distance-based classification.
"""

import json
import math
import time
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import Counter

from ..config import Config
from ..logger import get_logger

logger = get_logger("intelligence.ml_classifier")


# Fault categories with human-readable descriptions
FAULT_CATEGORIES = {
    "open_pin": "Pin not physically connected — no electrical path",
    "shorted_high": "Pin shorted to VCC — always reads HIGH",
    "shorted_low": "Pin shorted to GND — always reads LOW",
    "floating_pin": "Input floating — reads are random/inconsistent",
    "timing_unstable": "Timing instability — intermittent correct/incorrect reads",
    "degraded_gate": "Gate degraded — partially functional with reduced reliability",
    "healthy": "Pin operating within expected parameters",
}


@dataclass
class FaultFeatures:
    """Feature vector extracted from test data for a single pin."""
    pass_rate: float = 0.0
    error_rate: float = 0.0
    high_ratio: float = 0.0
    low_ratio: float = 0.0
    stability_score: float = 1.0
    consistency_across_runs: float = 1.0
    is_stuck: int = 0
    stuck_high: int = 0
    stuck_low: int = 0
    no_response: int = 0
    intermittent: int = 0
    propagation_delay_normalized: float = 0.0

    def to_vector(self) -> List[float]:
        """Convert to numeric feature vector for distance calculation."""
        return [
            self.pass_rate,
            self.error_rate,
            self.high_ratio,
            self.low_ratio,
            self.stability_score,
            self.consistency_across_runs,
            float(self.is_stuck),
            float(self.stuck_high),
            float(self.stuck_low),
            float(self.no_response),
            float(self.intermittent),
            self.propagation_delay_normalized,
        ]


@dataclass
class FaultPrediction:
    """Prediction result for a single pin."""
    pin_name: str
    predicted_fault: str
    confidence: float
    fault_description: str
    top_candidates: List[Tuple[str, float]] = field(default_factory=list)
    features: Optional[FaultFeatures] = None


@dataclass
class TrainingSample:
    """A labeled training sample for the classifier."""
    features: List[float]
    label: str
    chip_id: str = ""
    pin_name: str = ""
    timestamp: str = ""


class MLFaultClassifier:
    """
    K-Nearest Neighbors fault classifier trained on accumulated test data.

    Uses feature vectors extracted from test results (pass rate, stability,
    stuck state, etc.) to classify pin faults. Ships with a seed training set
    of synthetic examples representing each fault category, then improves
    as real test data is accumulated.

    Attributes:
        k: Number of neighbors for KNN classification
        training_data: List of labeled training samples
        data_file: Path to persistent training data file
    """

    DEFAULT_K = 5

    def __init__(self, data_dir: Optional[Path] = None, k: int = None):
        """
        Args:
            data_dir: Directory for storing training data
            k: Number of neighbors for KNN (default: 5)
        """
        self.k = k or self.DEFAULT_K
        self.data_dir = data_dir or Config.BASE_DIR / "session_data"
        self.data_dir.mkdir(exist_ok=True)
        self.data_file = self.data_dir / "ml_training_data.json"
        self.training_data: List[TrainingSample] = []

        self._load_training_data()
        if not self.training_data:
            self._seed_training_data()

        logger.info(
            f"MLFaultClassifier initialized: k={self.k}, "
            f"{len(self.training_data)} training samples"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_pin(self, features: FaultFeatures) -> FaultPrediction:
        """
        Classify a single pin's fault based on extracted features.

        Args:
            features: FaultFeatures extracted from test data

        Returns:
            FaultPrediction with classification and confidence
        """
        vec = features.to_vector()
        neighbors = self._find_neighbors(vec, self.k)

        if not neighbors:
            return FaultPrediction(
                pin_name="",
                predicted_fault="unknown",
                confidence=0.0,
                fault_description="Insufficient training data",
            )

        # Count votes from nearest neighbors, weighted by inverse distance
        votes: Dict[str, float] = {}
        for dist, sample in neighbors:
            weight = 1.0 / (dist + 1e-6)
            votes[sample.label] = votes.get(sample.label, 0.0) + weight

        total_weight = sum(votes.values())
        top_candidates = sorted(votes.items(), key=lambda x: x[1], reverse=True)
        predicted = top_candidates[0][0]
        confidence = top_candidates[0][1] / total_weight if total_weight > 0 else 0.0

        return FaultPrediction(
            pin_name="",
            predicted_fault=predicted,
            confidence=confidence,
            fault_description=FAULT_CATEGORIES.get(predicted, "Unknown fault"),
            top_candidates=[(label, w / total_weight) for label, w in top_candidates[:3]],
            features=features,
        )

    def classify_test_result(
        self, test_result: Dict, statistical_result=None, signal_report=None
    ) -> Dict[str, FaultPrediction]:
        """
        Classify all output pins from a test result.

        Args:
            test_result: Standard ICTester run_test() result dict
            statistical_result: Optional StatisticalResult for enriched features
            signal_report: Optional SignalReport for stability features

        Returns:
            Dict mapping pin_name → FaultPrediction
        """
        predictions = {}
        pin_diag = test_result.get("pinDiagnostics", {})

        for pin_name, diag in pin_diag.items():
            features = self._extract_features(
                pin_name, diag, statistical_result, signal_report
            )
            pred = self.classify_pin(features)
            pred.pin_name = pin_name
            predictions[pin_name] = pred

        return predictions

    def add_training_sample(
        self,
        features: FaultFeatures,
        label: str,
        chip_id: str = "",
        pin_name: str = "",
    ):
        """
        Add a labeled training sample to improve future classification.

        Args:
            features: Feature vector for the sample
            label: Fault category label (must be in FAULT_CATEGORIES)
            chip_id: Optional chip ID for context
            pin_name: Optional pin name for context
        """
        if label not in FAULT_CATEGORIES:
            logger.warning(f"Unknown fault label: {label}")
            return

        sample = TrainingSample(
            features=features.to_vector(),
            label=label,
            chip_id=chip_id,
            pin_name=pin_name,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.training_data.append(sample)
        self._save_training_data()
        logger.debug(f"Added training sample: {label} for {pin_name}")

    def auto_label_and_train(self, test_result: Dict):
        """
        Automatically generate training samples from a test result using
        heuristic labeling. Only labels high-confidence cases.

        Args:
            test_result: Standard ICTester run_test() result dict
        """
        chip_id = test_result.get("chipId", "")
        pin_diag = test_result.get("pinDiagnostics", {})
        added = 0

        for pin_name, diag in pin_diag.items():
            label = self._heuristic_label(diag)
            if label is None:
                continue

            features = self._extract_features(pin_name, diag)
            self.add_training_sample(features, label, chip_id, pin_name)
            added += 1

        if added > 0:
            logger.info(f"Auto-labeled {added} training samples from {chip_id}")

    def get_training_stats(self) -> Dict[str, int]:
        """Get count of training samples per fault category."""
        counts = Counter(s.label for s in self.training_data)
        return dict(counts)

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _extract_features(
        self,
        pin_name: str,
        diag: Dict,
        statistical_result=None,
        signal_report=None,
    ) -> FaultFeatures:
        """Extract feature vector from pin diagnostic data."""
        tested = diag.get("timesTested", 0)
        correct = diag.get("timesCorrect", 0)
        wrong = diag.get("timesWrong", 0)
        errors = diag.get("timesError", 0)
        stuck = diag.get("stuckState", "") or ""
        all_reads = diag.get("allReadValues", [])

        high_count = sum(1 for v in all_reads if v == "HIGH")
        low_count = sum(1 for v in all_reads if v == "LOW")
        total_valid = high_count + low_count

        f = FaultFeatures(
            pass_rate=correct / tested if tested > 0 else 0.0,
            error_rate=errors / tested if tested > 0 else 0.0,
            high_ratio=high_count / total_valid if total_valid > 0 else 0.5,
            low_ratio=low_count / total_valid if total_valid > 0 else 0.5,
            is_stuck=1 if stuck in ("HIGH", "LOW", "NO_RESPONSE") else 0,
            stuck_high=1 if stuck == "HIGH" else 0,
            stuck_low=1 if stuck == "LOW" else 0,
            no_response=1 if stuck == "NO_RESPONSE" else 0,
            intermittent=1 if stuck == "INTERMITTENT" else 0,
        )

        # Enrich from statistical result if available
        if statistical_result is not None:
            ps = statistical_result.per_pin_stats.get(pin_name)
            if ps:
                f.consistency_across_runs = ps.consistency_score
                if ps.intermittent:
                    f.intermittent = 1

        # Enrich from signal report if available
        if signal_report is not None:
            stab = signal_report.pin_stability.get(pin_name)
            if stab:
                f.stability_score = stab.stability_score
            for delay in signal_report.propagation_delays:
                if delay.output_pin_name == pin_name and not delay.timed_out:
                    # Normalize: typical TTL is 10-20ns, Arduino resolution ~4us
                    f.propagation_delay_normalized = min(1.0, delay.delay_us / 10000.0)

        return f

    # ------------------------------------------------------------------
    # KNN internals
    # ------------------------------------------------------------------

    def _find_neighbors(
        self, vec: List[float], k: int
    ) -> List[Tuple[float, TrainingSample]]:
        """Find k nearest neighbors by Euclidean distance."""
        distances = []
        for sample in self.training_data:
            dist = self._euclidean_distance(vec, sample.features)
            distances.append((dist, sample))
        distances.sort(key=lambda x: x[0])
        return distances[:k]

    @staticmethod
    def _euclidean_distance(a: List[float], b: List[float]) -> float:
        """Euclidean distance between two feature vectors."""
        if len(a) != len(b):
            return float("inf")
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    # ------------------------------------------------------------------
    # Heuristic labeling for auto-training
    # ------------------------------------------------------------------

    def _heuristic_label(self, diag: Dict) -> Optional[str]:
        """
        Assign a heuristic label to a pin diagnostic for auto-training.
        Only labels clear-cut cases; returns None for ambiguous data.
        """
        tested = diag.get("timesTested", 0)
        correct = diag.get("timesCorrect", 0)
        errors = diag.get("timesError", 0)
        stuck = diag.get("stuckState", "") or ""

        if tested == 0:
            return None

        pass_rate = correct / tested

        # Clear healthy
        if pass_rate >= 0.95 and stuck == "":
            return "healthy"

        # Clear no response
        if stuck == "NO_RESPONSE":
            return "open_pin"

        # Clear stuck
        if stuck == "HIGH" and pass_rate < 0.3:
            return "shorted_high"
        if stuck == "LOW" and pass_rate < 0.3:
            return "shorted_low"

        # Intermittent with decent overall pass rate → floating
        if stuck == "INTERMITTENT" and 0.3 <= pass_rate <= 0.7:
            return "floating_pin"

        # Intermittent but mostly passes → timing
        if stuck == "INTERMITTENT" and pass_rate > 0.7:
            return "timing_unstable"

        # Low pass rate but not stuck → degraded
        if 0.3 <= pass_rate < 0.8 and stuck == "":
            return "degraded_gate"

        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_training_data(self):
        """Load training data from JSON file."""
        if not self.data_file.exists():
            return
        try:
            data = json.loads(self.data_file.read_text(encoding="utf-8"))
            self.training_data = [
                TrainingSample(**s) for s in data
            ]
            logger.info(f"Loaded {len(self.training_data)} training samples")
        except Exception as e:
            logger.error(f"Failed to load training data: {e}")

    def _save_training_data(self):
        """Save training data to JSON file."""
        try:
            data = [asdict(s) for s in self.training_data]
            self.data_file.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Failed to save training data: {e}")

    def _seed_training_data(self):
        """Create initial synthetic training samples for each fault category."""
        seeds = [
            # healthy: high pass rate, stable, no stuck
            (FaultFeatures(pass_rate=1.0, stability_score=1.0, consistency_across_runs=1.0), "healthy"),
            (FaultFeatures(pass_rate=0.95, stability_score=0.98, consistency_across_runs=0.96), "healthy"),
            (FaultFeatures(pass_rate=1.0, high_ratio=0.5, low_ratio=0.5, stability_score=1.0), "healthy"),

            # open_pin: no response, all errors
            (FaultFeatures(pass_rate=0.0, error_rate=1.0, no_response=1, is_stuck=1), "open_pin"),
            (FaultFeatures(pass_rate=0.0, error_rate=0.8, no_response=1, is_stuck=1, stability_score=0.0), "open_pin"),

            # shorted_high: stuck HIGH, low pass rate
            (FaultFeatures(pass_rate=0.1, high_ratio=1.0, low_ratio=0.0, stuck_high=1, is_stuck=1), "shorted_high"),
            (FaultFeatures(pass_rate=0.25, high_ratio=1.0, stuck_high=1, is_stuck=1, stability_score=1.0), "shorted_high"),

            # shorted_low: stuck LOW, low pass rate
            (FaultFeatures(pass_rate=0.1, low_ratio=1.0, high_ratio=0.0, stuck_low=1, is_stuck=1), "shorted_low"),
            (FaultFeatures(pass_rate=0.25, low_ratio=1.0, stuck_low=1, is_stuck=1, stability_score=1.0), "shorted_low"),

            # floating_pin: random, intermittent, ~50/50 high/low
            (FaultFeatures(pass_rate=0.5, high_ratio=0.5, low_ratio=0.5, intermittent=1, stability_score=0.5, consistency_across_runs=0.4), "floating_pin"),
            (FaultFeatures(pass_rate=0.4, high_ratio=0.6, low_ratio=0.4, intermittent=1, stability_score=0.55), "floating_pin"),

            # timing_unstable: mostly passes but inconsistent across runs
            (FaultFeatures(pass_rate=0.8, stability_score=0.7, consistency_across_runs=0.75, intermittent=1), "timing_unstable"),
            (FaultFeatures(pass_rate=0.85, stability_score=0.8, consistency_across_runs=0.7, propagation_delay_normalized=0.3), "timing_unstable"),

            # degraded_gate: moderate pass rate, somewhat stable
            (FaultFeatures(pass_rate=0.6, stability_score=0.85, consistency_across_runs=0.6), "degraded_gate"),
            (FaultFeatures(pass_rate=0.5, stability_score=0.9, consistency_across_runs=0.55, propagation_delay_normalized=0.5), "degraded_gate"),
        ]

        for features, label in seeds:
            sample = TrainingSample(
                features=features.to_vector(),
                label=label,
                chip_id="SEED",
                pin_name="synthetic",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            self.training_data.append(sample)

        self._save_training_data()
        logger.info(f"Seeded {len(seeds)} synthetic training samples")
