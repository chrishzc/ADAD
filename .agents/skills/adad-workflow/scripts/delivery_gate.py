"""
ADAD Delivery Gate: Phase-2 交付門禁純函式模組
專責評估模組在 validated -> linted/tested -> deployed 的轉移條件，無副作用、無 LLM 呼叫。
"""
import sys

STRUCTURAL_KEYS = {
    "dependencies",
    "domain",
    "type",
    "algorithm",
    "invariants",
    "verification",
    "sub_maps",
    "owner",
}


def has_architecture_impact(node_before: dict, node_after: dict) -> bool:
    """
    比較 approve 當下 vs 上一次 CP-2 approved 快照中的結構欄位。
    明確排除 state 欄位，避免 delivery_gate 自身狀態推進誤觸發架構審查警報。
    若欠缺 node_before 快照，安全偏向 (fail-safe) 視為需要審查 (True)。
    """
    if not node_before or not node_after:
        return True
    keys = STRUCTURAL_KEYS & (node_before.keys() | node_after.keys())
    return any(node_before.get(k) != node_after.get(k) for k in keys)



def evaluate_delivery_step(
    current_state: str,
    lint_exit_code: int,
    test_exit_code: int,
    domain_boundary_ok: bool,
    invariants_ok: bool,
    architecture_impact: bool,
) -> str:
    """
    評估模組下一步交付狀態。
    回傳值:
      - "blocked": 絕對阻斷門禁失敗 (fail-closed)
      - "requires_review": 通過門禁但有架構/規格欄位變更，需人工/Reviewer 審查
      - "advance_to_linted_tested": 無架構影響且零違規，可推進至 linted/tested
      - "advance_to_deployed": 無架構影響且零違規，可推進至 deployed
      - "no_action": 無需變更狀態
    """
    # 1. 絕對阻斷 gate 優先於一切 (fail-closed)
    if not domain_boundary_ok or not invariants_ok:
        return "blocked"
    if lint_exit_code != 0 or test_exit_code != 0:
        return "blocked"

    # 2. 阻斷 gate 通過後，判斷是否需要人工/語意層審查
    if architecture_impact:
        return "requires_review"

    # 3. 無架構影響且門禁全 Pass，依當前狀態自動推進
    if current_state == "validated":
        return "advance_to_linted_tested"
    if current_state == "linted/tested":
        return "advance_to_deployed"

    return "no_action"


def _self_test():
    """純函式單元自測 (Assertion Check)"""
    # 測試 0: 欠缺 node_before 快照時回傳 True
    assert has_architecture_impact(None, {"domain": "core"}), "Missing node_before must trigger fail-safe review"

    # 測試 1: 僅變更 state 欄位時 has_architecture_impact 應回傳 False
    before = {"state": "validated", "domain": "core", "dependencies": ["a"]}
    after = {"state": "linted/tested", "domain": "core", "dependencies": ["a"]}
    assert not has_architecture_impact(before, after), "State change should not trigger architecture impact"


    # 測試 2: 變更 dependencies 欄位時應回傳 True
    after_dept = {"state": "validated", "domain": "core", "dependencies": ["a", "b"]}
    assert has_architecture_impact(before, after_dept), "Dependency change must trigger architecture impact"

    # 測試 3: 不變量/邊界檢查失敗時，即使無架構影響也必須 blocked
    res_blocked = evaluate_delivery_step(
        current_state="validated",
        lint_exit_code=0,
        test_exit_code=0,
        domain_boundary_ok=False,
        invariants_ok=True,
        architecture_impact=False,
    )
    assert res_blocked == "blocked", "Boundary fail must block advance"

    # 測試 4: 乾淨改動且在 validated 時，回傳 advance_to_linted_tested
    res_adv1 = evaluate_delivery_step(
        current_state="validated",
        lint_exit_code=0,
        test_exit_code=0,
        domain_boundary_ok=True,
        invariants_ok=True,
        architecture_impact=False,
    )
    assert res_adv1 == "advance_to_linted_tested", "Clean change in validated should advance to linted/tested"

    # 測試 5: 乾淨改動且在 linted/tested 時，回傳 advance_to_deployed
    res_adv2 = evaluate_delivery_step(
        current_state="linted/tested",
        lint_exit_code=0,
        test_exit_code=0,
        domain_boundary_ok=True,
        invariants_ok=True,
        architecture_impact=False,
    )
    assert res_adv2 == "advance_to_deployed", "Clean change in linted/tested should advance to deployed"

    # 測試 6: 有架構變更時應回傳 requires_review
    res_rev = evaluate_delivery_step(
        current_state="validated",
        lint_exit_code=0,
        test_exit_code=0,
        domain_boundary_ok=True,
        invariants_ok=True,
        architecture_impact=True,
    )
    assert res_rev == "requires_review", "Architecture impact must require review"

    print("delivery_gate.py self-test passed!")


if __name__ == "__main__":
    _self_test()
