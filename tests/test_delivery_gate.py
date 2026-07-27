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
    / "delivery_gate.py"
)
_SPEC = importlib.util.spec_from_file_location("delivery_gate", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

has_architecture_impact = _MODULE.has_architecture_impact
evaluate_delivery_step = _MODULE.evaluate_delivery_step



def test_has_architecture_impact_ignores_state_changes():
    before = {"state": "validated", "domain": "adad_core", "dependencies": ["text_io"]}
    after = {"state": "linted/tested", "domain": "adad_core", "dependencies": ["text_io"]}
    assert has_architecture_impact(before, after) is False


def test_has_architecture_impact_detects_structural_changes():
    before = {"state": "validated", "domain": "adad_core", "dependencies": ["text_io"]}
    after = {"state": "validated", "domain": "adad_core", "dependencies": ["text_io", "task_complexity"]}
    assert has_architecture_impact(before, after) is True


def test_evaluate_delivery_step_blocks_on_gate_failures():
    # Lint failed
    res_lint = evaluate_delivery_step("validated", 1, 0, True, True, False)
    assert res_lint == "blocked"

    # Test failed
    res_test = evaluate_delivery_step("validated", 0, 1, True, True, False)
    assert res_test == "blocked"

    # Boundary failed
    res_bound = evaluate_delivery_step("validated", 0, 0, False, True, False)
    assert res_bound == "blocked"

    # Invariants failed
    res_inv = evaluate_delivery_step("validated", 0, 0, True, False, False)
    assert res_inv == "blocked"


def test_evaluate_delivery_step_requires_review_on_arch_impact():
    res = evaluate_delivery_step("validated", 0, 0, True, True, True)
    assert res == "requires_review"


def test_evaluate_delivery_step_advances_when_clean():
    res_validated = evaluate_delivery_step("validated", 0, 0, True, True, False)
    assert res_validated == "advance_to_linted_tested"

    res_linted = evaluate_delivery_step("linted/tested", 0, 0, True, True, False)
    assert res_linted == "advance_to_deployed"
