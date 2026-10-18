"""
tests/test_grading.py — Unit tests for the ASEAN grading engine.

Run with: pytest backend/tests/test_grading.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from services.grading import evaluate_grade, _assign_class, THRESHOLDS


# ── _assign_class boundary tests ─────────────────────────────────────────────

class TestAssignClass:
    def test_black_bean_extra_class(self):
        assert _assign_class("black_bean", 0.0)   == ("extra_class", False)
        assert _assign_class("black_bean", 3.99)  == ("extra_class", False)

    def test_black_bean_class_i_lower_boundary(self):
        assert _assign_class("black_bean", 4.0)   == ("class_i", False)

    def test_black_bean_class_i_upper_boundary(self):
        assert _assign_class("black_bean", 6.0)   == ("class_i", False)

    def test_black_bean_class_ii(self):
        assert _assign_class("black_bean", 6.01)  == ("class_ii", False)
        assert _assign_class("black_bean", 15.0)  == ("class_ii", False)

    def test_black_bean_over_threshold(self):
        assert _assign_class("black_bean", 15.01) == ("class_ii", True)
        assert _assign_class("black_bean", 99.0)  == ("class_ii", True)

    def test_dried_cherry_extra_class(self):
        assert _assign_class("dried_cherry", 0.0)  == ("extra_class", False)
        assert _assign_class("dried_cherry", 0.49) == ("extra_class", False)

    def test_dried_cherry_class_i(self):
        assert _assign_class("dried_cherry", 0.5)  == ("class_i", False)
        assert _assign_class("dried_cherry", 1.0)  == ("class_i", False)

    def test_dried_cherry_class_ii(self):
        assert _assign_class("dried_cherry", 1.01) == ("class_ii", False)
        assert _assign_class("dried_cherry", 2.0)  == ("class_ii", False)

    def test_dried_cherry_over_threshold(self):
        assert _assign_class("dried_cherry", 2.01) == ("class_ii", True)

    def test_all_defect_types_have_thresholds(self):
        expected = {"black_bean", "moldy_infested", "immature", "broken", "dried_cherry", "foreign_matter"}
        assert set(THRESHOLDS.keys()) == expected


# ── evaluate_grade integration tests ─────────────────────────────────────────

def _make_result(counts: dict, total: int = None) -> dict:
    """Helper to build a detection result dict."""
    all_counts = {
        "black_bean": 0, "moldy_infested": 0, "immature": 0,
        "broken": 0, "dried_cherry": 0, "foreign_matter": 0,
    }
    all_counts.update(counts)
    computed_total = total if total is not None else sum(all_counts.values())
    return {"total_beans": computed_total, "class_counts": all_counts}


class TestEvaluateGrade:

    def test_all_zero_defects_extra_class(self):
        result = evaluate_grade(_make_result({}, total=100))
        assert result["grade"] == "extra_class"
        assert result["over_threshold_flag"] is False

    def test_single_class_i_defect_gives_class_i(self):
        # black_bean at 5% (4–6% = class_i) out of 100 beans
        result = evaluate_grade(_make_result({"black_bean": 5}, total=100))
        assert result["grade"] == "class_i"
        assert result["over_threshold_flag"] is False

    def test_single_class_ii_defect_gives_class_ii(self):
        # black_bean at 10% (>6% = class_ii) out of 100 beans
        result = evaluate_grade(_make_result({"black_bean": 10}, total=100))
        assert result["grade"] == "class_ii"
        assert result["over_threshold_flag"] is False

    def test_lowest_class_wins_over_higher(self):
        # black_bean 5% (class_i) + broken 8% (class_ii) → class_ii
        result = evaluate_grade(_make_result({"black_bean": 5, "broken": 8}, total=100))
        assert result["grade"] == "class_ii"

    def test_over_threshold_flag_set(self):
        # black_bean 20% → exceeds 15% upper bound
        result = evaluate_grade(_make_result({"black_bean": 20}, total=100))
        assert result["grade"] == "class_ii"
        assert result["over_threshold_flag"] is True

    def test_over_threshold_single_defect_still_class_ii(self):
        # No rejection class; exceeding Class II max → still class_ii + flag
        result = evaluate_grade(_make_result({"broken": 15}, total=100))  # 15% > 10% max
        assert result["grade"] == "class_ii"
        assert result["over_threshold_flag"] is True

    def test_defect_breakdown_contains_all_six_defects(self):
        result = evaluate_grade(_make_result({}, total=100))
        defect_types = {dr["defect_type"] for dr in result["defect_breakdown"]}
        assert defect_types == {
            "black_bean", "moldy_infested", "immature",
            "broken", "dried_cherry", "foreign_matter",
        }

    def test_zero_total_beans_returns_extra_class(self):
        result = evaluate_grade({"total_beans": 0, "class_counts": {}})
        assert result["grade"] == "extra_class"
        assert result["over_threshold_flag"] is False

    def test_percentage_calculation_correct(self):
        # 10 broken beans out of 200 total = 5% → exactly class_i boundary
        result = evaluate_grade(_make_result({"broken": 10}, total=200))
        breakdown = {dr["defect_type"]: dr for dr in result["defect_breakdown"]}
        assert breakdown["broken"]["percentage"] == pytest.approx(5.0, abs=0.001)
        assert breakdown["broken"]["assigned_class"] == "class_i"

    def test_multiple_over_threshold_defects(self):
        # Two defects both over threshold
        result = evaluate_grade(_make_result({"black_bean": 20, "immature": 10}, total=100))
        assert result["grade"] == "class_ii"
        assert result["over_threshold_flag"] is True
        over_types = [dr["defect_type"] for dr in result["defect_breakdown"] if dr["over_threshold"]]
        assert "black_bean" in over_types
        assert "immature" in over_types
