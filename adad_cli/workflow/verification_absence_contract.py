"""Validation for explicit key-absence verification expectations."""

from copy import deepcopy


def validate_verification_absence_contract(verification_case: object) -> object:
    """Return a normalized copy of a verification case.

    ``None`` remains an ordinary expected value.  Key absence must be expressed
    explicitly through ``expect_absent_keys``.
    """
    if not isinstance(verification_case, dict):
        raise ValueError("verification_case must be an object")

    normalized_case = deepcopy(verification_case)
    if "expect_absent_keys" not in normalized_case:
        return normalized_case

    absent_keys = normalized_case["expect_absent_keys"]
    if not isinstance(absent_keys, list):
        raise ValueError("expect_absent_keys must be an array")
    if any(not isinstance(key, str) or not key for key in absent_keys):
        raise ValueError("expect_absent_keys must contain non-empty strings")
    if len(absent_keys) != len(set(absent_keys)):
        raise ValueError("expect_absent_keys must not contain duplicates")

    expected = normalized_case.get("expect", {})
    if not isinstance(expected, dict):
        raise ValueError("expect must be an object when expect_absent_keys is used")

    conflicting_keys = set(expected).intersection(absent_keys)
    if conflicting_keys:
        conflict = sorted(conflicting_keys)[0]
        raise ValueError(
            f"key {conflict!r} cannot appear in both expect and expect_absent_keys"
        )

    return normalized_case
