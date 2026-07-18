import pytest

pytestmark = pytest.mark.regression_backlog





from adad_cli.workflow.verification_absence_contract import (
    validate_verification_absence_contract,
)


def test_accepts_explicit_absent_keys_without_treating_null_as_absent():
    verification_case = {
        "expect": {"CI": None},
        "expect_absent_keys": ["GITHUB_BASE_REF"],
    }

    result = validate_verification_absence_contract(verification_case)

    assert result == verification_case
    assert result is not verification_case
    assert result["expect"] is not verification_case["expect"]


@pytest.mark.parametrize(
    "verification_case",
    [
        {"expect": {"CI": None}, "expect_absent_keys": ["CI"]},
        {"expect_absent_keys": [""]},
        {"expect_absent_keys": ["CI", "CI"]},
        {"expect_absent_keys": "CI"},
    ],
)
def test_rejects_invalid_absence_contracts(verification_case):
    with pytest.raises(ValueError):
        validate_verification_absence_contract(verification_case)


def test_preserves_existing_verification_semantics_when_absence_is_undeclared():
    verification_case = {"expect": None, "input": {"value": 1}}

    result = validate_verification_absence_contract(verification_case)

    assert result == verification_case
    assert result is not verification_case
