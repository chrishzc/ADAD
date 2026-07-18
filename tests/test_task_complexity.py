"""Direct regression tests for the Task complexity issuance policy."""

import importlib.util
from pathlib import Path

import pytest


_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "task_complexity.py"
)
_SPEC = importlib.util.spec_from_file_location("task_complexity", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


@pytest.mark.parametrize(
    ("complexity", "has_algorithm", "has_boundaries", "has_verification", "capability", "approved", "reason", "expected"),
    [
        ("low", False, False, False, "low", False, "", "issue"),
        ("medium", True, True, True, "standard", False, "", "issue"),
        ("medium", True, True, False, "standard", False, "", "complete_spec"),
        ("high", True, True, True, "high", False, "", "split"),
        ("high", True, True, True, "high", True, "atomic external transaction", "issue_override"),
        ("high", True, True, True, "standard", True, "atomic external transaction", "split"),
    ],
)
def test_evaluate_task_complexity_decision_matrix(
    complexity,
    has_algorithm,
    has_boundaries,
    has_verification,
    capability,
    approved,
    reason,
    expected,
):
    assert _MODULE.evaluate_task_complexity(
        complexity,
        has_algorithm,
        has_boundaries,
        has_verification,
        capability,
        approved,
        reason,
    ) == expected


@pytest.mark.parametrize(
    ("complexity", "capability"),
    [("unknown", "standard"), ("medium", "unknown"), (None, "standard")],
)
def test_evaluate_task_complexity_rejects_invalid_levels(complexity, capability):
    with pytest.raises(ValueError):
        _MODULE.evaluate_task_complexity(
            complexity,
            True,
            True,
            True,
            capability,
            False,
            "",
        )
