"""
services/grading.py — ASEAN coffee bean grading engine.

Implements the ASEAN Table of Defects grading rules:
- Calculates defect percentage per class.
- Assigns a class (extra_class | class_i | class_ii) to each defect type.
- Final grade = lowest class among all evaluations.
- Over-threshold flag set if any defect % exceeds Class II upper bound.
"""

from __future__ import annotations
from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# ASEAN Threshold Table
# Each entry: (extra_class_max, class_i_max, class_ii_max)
# A defect % that exceeds class_ii_max still resolves to class_ii + over_threshold flag.
# ─────────────────────────────────────────────────────────────────────────────
THRESHOLDS: Dict[str, tuple] = {
    #                  extra_max  class_i_max  class_ii_max
    "black_bean":     (4.0,       6.0,         15.0),
    "moldy_infested": (5.0,       6.0,          8.0),
    "immature":       (2.0,       3.0,          8.0),
    "broken":         (3.0,       5.0,         10.0),
    "dried_cherry":   (0.5,       1.0,          2.0),
    "foreign_matter": (1.0,       1.5,          2.0),
}

# Grade ordinal for comparison (higher = lower quality)
_GRADE_ORDINAL = {"extra_class": 0, "class_i": 1, "class_ii": 2}
_ORDINAL_GRADE = {v: k for k, v in _GRADE_ORDINAL.items()}


def _assign_class(defect_type: str, percentage: float) -> tuple[str, bool]:
    """
    Assign a quality class and over_threshold flag for one defect type.

    Returns (assigned_class, over_threshold)
    """
    extra_max, class_i_max, class_ii_max = THRESHOLDS[defect_type]

    if percentage < extra_max:
        return "extra_class", False
    elif percentage <= class_i_max:
        return "class_i", False
    elif percentage <= class_ii_max:
        return "class_ii", False
    else:
        # Exceeds Class II upper bound → still Class II, but flag it
        return "class_ii", True


def evaluate_grade(detection_result: Dict) -> Dict:
    """
    Apply grading rules to detection results.

    Args:
        detection_result: output of services.detection.run_detection()
            {
                "total_beans": int,
                "class_counts": {"black_bean": n, ...}
            }

    Returns:
        {
            "grade": str,               # "extra_class" | "class_i" | "class_ii"
            "over_threshold_flag": bool,
            "total_beans": int,
            "defect_breakdown": [
                {
                    "defect_type":    str,
                    "count":          int,
                    "percentage":     float,
                    "assigned_class": str,
                    "over_threshold": bool,
                },
                ...
            ]
        }
    """
    total_beans: int  = detection_result.get("total_beans", 0)
    class_counts: Dict = detection_result.get("class_counts", {})

    breakdown: List[Dict] = []
    worst_ordinal = 0          # start at extra_class
    any_over_threshold = False

    for defect_type, thresholds in THRESHOLDS.items():
        count = class_counts.get(defect_type, 0)

        if total_beans > 0:
            pct = (count / total_beans) * 100.0
        else:
            pct = 0.0

        assigned_class, over = _assign_class(defect_type, pct)

        if over:
            any_over_threshold = True

        ordinal = _GRADE_ORDINAL[assigned_class]
        if ordinal > worst_ordinal:
            worst_ordinal = ordinal

        breakdown.append({
            "defect_type":    defect_type,
            "count":          count,
            "percentage":     round(pct, 3),
            "assigned_class": assigned_class,
            "over_threshold": over,
        })

    final_grade = _ORDINAL_GRADE[worst_ordinal]

    return {
        "grade":              final_grade,
        "over_threshold_flag": any_over_threshold,
        "total_beans":        total_beans,
        "defect_breakdown":   breakdown,
    }
