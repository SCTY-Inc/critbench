"""Tests for evaluation metrics modules."""

from critbench.evaluation.metrics.bias_detection import (
    BiasDetector,
    BiasReport,
)
from critbench.evaluation.metrics.cot_quality import (
    CoTAnalysis,
    CoTAnalyzer,
    analyze_cot_quality,
)
from critbench.evaluation.metrics.reliability import (
    ReliabilityMetrics,
    calculate_icc,
    calculate_krippendorff_alpha,
    calculate_pairwise_agreement,
    compute_reliability,
)


class TestBiasDetection:
    """Tests for bias detection module."""

    def test_bias_detector_init(self):
        detector = BiasDetector()
        assert detector.length_bias_threshold == 0.5
        assert detector.self_enhancement_threshold == 0.1

    def test_record_scores(self):
        detector = BiasDetector()
        detector.record_scores({"model_a": 0.8, "model_b": 0.6})
        detector.record_scores({"model_a": 0.7, "model_b": 0.5})

        report = detector.analyze()
        assert isinstance(report, BiasReport)
        assert "model_a" in report.model_leniency
        assert "model_b" in report.model_leniency

    def test_leniency_detection(self):
        detector = BiasDetector(leniency_spread_threshold=0.1)

        # Model A consistently scores higher
        for _ in range(5):
            detector.record_scores({"model_a": 0.9, "model_b": 0.5})

        report = detector.analyze()
        assert report.leniency_spread > 0.3
        assert len(report.flags) > 0

    def test_length_bias_detection(self):
        detector = BiasDetector(length_bias_threshold=0.3)

        # Positive correlation: longer = higher score
        for length, score in [(100, 0.5), (200, 0.6), (300, 0.7), (400, 0.8), (500, 0.9)]:
            detector.record_scores({"judge": score}, response_length=length)

        report = detector.analyze()
        assert report.length_bias is not None
        assert report.length_bias > 0.5

    def test_bias_report_to_dict(self):
        report = BiasReport(
            length_bias=0.6,
            length_bias_detected=True,
            flags=["Test flag"],
        )
        d = report.to_dict()
        assert d["length_bias"]["correlation"] == 0.6
        assert d["length_bias"]["detected"] is True
        assert d["bias_count"] == 1


class TestReliability:
    """Tests for reliability metrics module."""

    def test_krippendorff_alpha_perfect_agreement(self):
        # All raters give same scores
        ratings = [
            [0.8, 0.6, 0.7],
            [0.8, 0.6, 0.7],
            [0.8, 0.6, 0.7],
        ]
        alpha = calculate_krippendorff_alpha(ratings)
        assert alpha is not None
        assert alpha > 0.99

    def test_krippendorff_alpha_no_agreement(self):
        # Raters give opposite scores
        ratings = [
            [0.9, 0.1, 0.5],
            [0.1, 0.9, 0.5],
            [0.5, 0.5, 0.5],
        ]
        alpha = calculate_krippendorff_alpha(ratings)
        assert alpha is not None
        assert alpha < 0.5

    def test_krippendorff_alpha_insufficient_data(self):
        # Only one rater
        ratings = [[0.8, 0.6, 0.7]]
        alpha = calculate_krippendorff_alpha(ratings)
        assert alpha is None

    def test_icc_calculation(self):
        ratings = [
            [0.8, 0.6, 0.7, 0.5],
            [0.7, 0.5, 0.6, 0.4],
            [0.9, 0.7, 0.8, 0.6],
        ]
        icc = calculate_icc(ratings)
        assert icc is not None
        assert -1.0 <= icc <= 1.0

    def test_pairwise_agreement(self):
        scores = {
            "judge_a": [0.8, 0.6, 0.7],
            "judge_b": [0.75, 0.55, 0.65],  # Close to A
            "judge_c": [0.3, 0.9, 0.2],  # Very different
        }
        mean_agreement, pairwise = calculate_pairwise_agreement(scores, threshold=0.2)

        assert ("judge_a", "judge_b") in pairwise
        assert pairwise[("judge_a", "judge_b")] > pairwise.get(("judge_a", "judge_c"), 0)

    def test_compute_reliability(self):
        all_scores = {
            "coherence": {
                "model_a": [0.8, 0.7],
                "model_b": [0.75, 0.65],
            },
            "judgment": {
                "model_a": [0.6, 0.5],
                "model_b": [0.55, 0.45],
            },
        }
        metrics = compute_reliability(all_scores, ["model_a", "model_b"])

        assert isinstance(metrics, ReliabilityMetrics)
        assert metrics.krippendorff_alpha is not None or metrics.icc is not None


class TestCoTQuality:
    """Tests for chain-of-thought quality analysis."""

    def test_cot_analyzer_basic(self):
        analyzer = CoTAnalyzer()

        response = """
        BRIEF_UNDERSTANDING: 0.8

        The model demonstrates good understanding because it asks relevant
        clarifying questions. Specifically, it mentions the target audience
        and therefore shows comprehension of the brief.

        However, there are some minor issues with specificity.
        """

        analysis = analyzer.analyze_response(response, model="test", dimension="coherence")

        assert isinstance(analysis, CoTAnalysis)
        assert analysis.reasoning_depth > 0
        assert analysis.overall_quality > 0

    def test_cot_hedging_detection(self):
        analyzer = CoTAnalyzer()

        response = """
        This perhaps might be somewhat good. Maybe the response could possibly
        be better, but it seems to appear adequate. Perhaps it might work.
        """

        analysis = analyzer.analyze_response(response)
        assert analysis.uses_hedging is True
        assert analysis.logical_coherence < 1.0

    def test_cot_contradiction_detection(self):
        analyzer = CoTAnalyzer()

        response = """
        The response shows high quality reasoning throughout.
        However, the response is of poor quality in its execution.
        """

        analysis = analyzer.analyze_response(response)
        assert analysis.has_contradictions is True

    def test_cot_report_aggregation(self):
        analyzer = CoTAnalyzer()

        for i in range(5):
            analyzer.analyze_response(
                f"Good reasoning because of specific evidence {i}.",
                model="model_a",
                dimension="coherence",
            )

        report = analyzer.get_report()
        assert report.total_responses == 5
        assert report.mean_quality > 0
        assert "model_a" in report.quality_by_model

    def test_analyze_cot_quality_convenience(self):
        responses = [
            {"response": "Good because of reasons.", "model": "a", "dimension": "d1"},
            {"response": "Bad due to issues.", "model": "b", "dimension": "d2"},
        ]
        report = analyze_cot_quality(responses)
        assert report.total_responses == 2
