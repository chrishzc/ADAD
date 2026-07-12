"""
File: task_complexity.py
Description: 實作評估任務複雜度的決策政策，依據 Task 的 complexity、has_algorithm、has_boundaries、has_verification 以及模型的 model_capability 等參數，返回對應的決策結果（例如 issue, complete_spec, split, issue_override 等）。
"""

def evaluate_task_complexity(
    complexity: str,
    has_algorithm: bool,
    has_boundaries: bool,
    has_verification: bool,
    model_capability: str,
    override_approved: bool,
    override_reason: str
) -> str:
    # ponytail: 簡潔的純函式決策矩陣，無任何外部依賴與副作用

    if not isinstance(complexity, str) or not isinstance(model_capability, str):
        raise ValueError("complexity and model_capability must be strings")

    comp = complexity.lower()
    cap = model_capability.lower()

    if comp not in ("low", "medium", "high"):
        raise ValueError(f"Invalid complexity: {complexity}")
    if cap not in ("low", "standard", "high"):
        raise ValueError(f"Invalid model_capability: {model_capability}")

    if comp == "low":
        return "issue"

    if comp == "medium":
        if has_algorithm and has_boundaries and has_verification:
            return "issue"
        return "complete_spec"

    if comp == "high":
        reason_valid = bool(override_reason and override_reason.strip())
        if cap == "high" and override_approved and reason_valid:
            return "issue_override"
        return "split"

    raise ValueError("Unexpected complexity flow")


if __name__ == "__main__":
    # ponytail: 任務自我檢測斷言
    assert evaluate_task_complexity("low", False, False, False, "low", False, "") == "issue"
    assert evaluate_task_complexity("medium", True, True, True, "standard", False, "") == "issue"
    assert evaluate_task_complexity("medium", True, True, False, "standard", False, "") == "complete_spec"
    assert evaluate_task_complexity("high", True, True, True, "high", False, "") == "split"
    assert evaluate_task_complexity("high", True, True, True, "high", True, "atomic external transaction") == "issue_override"
    assert evaluate_task_complexity("high", True, True, True, "standard", True, "atomic external transaction") == "split"
    print("All task_complexity self-tests passed!")
