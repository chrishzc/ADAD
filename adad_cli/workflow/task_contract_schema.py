"""
File: task_contract_schema.py
Description: 將 Task 的自然語言 description 升級為可驗證的結構化 Semantic Contract，並提供機器可驗證的目標與完成條件。
"""

import json

def validate_semantic_contract(description: str) -> dict:
    """將 Task 的自然語言 description 升級為可驗證的結構化 Semantic Contract。

    - description: 自然語言描述或已結構化的 JSON 字串。
    - 回傳: 包含 summary (str) 與 goals (list[str]) 的結構化語意契約字典。
    """
    # ponytail: 用標準庫 dict 檢查替代 jsonschema 依賴，避免引入新套件
    if not description:
        raise ValueError("description cannot be empty")

    description_stripped = description.strip()

    # 嘗試將其解析為 JSON
    if description_stripped.startswith("{") and description_stripped.endswith("}"):
        try:
            data = json.loads(description_stripped)
            if not isinstance(data, dict):
                raise ValueError("Parsed JSON must be an object")
            if "summary" not in data or not isinstance(data["summary"], str):
                raise ValueError("Semantic Contract must contain a string 'summary'")
            if "goals" not in data or not isinstance(data["goals"], list) or len(data["goals"]) == 0:
                raise ValueError("Semantic Contract must contain a non-empty list 'goals'")
            for g in data["goals"]:
                if not isinstance(g, str):
                    raise ValueError("All items in 'goals' must be strings")
            return data
        except Exception as e:
            # 如果是明確的 JSON 格式但格式錯誤，拋出異常；否則當作普通文字處理
            if isinstance(e, ValueError):
                raise

    # 普通文字：自動結構化為 summary 和 goals
    return {
        "summary": description_stripped,
        "goals": [description_stripped]
    }


def validate_non_goals(non_goals: list) -> list:
    """驗證並確保 Task 明確定義了 Non-goal 清單。

    - non_goals: 限制工作範圍的 non-goal 字串列表。
    - 回傳: 驗證後的 non_goals 列表。
    """
    # ponytail: 限制 Agent 不得自行擴張範圍，且空陣列代表已明確確認，故禁止為 None
    if non_goals is None:
        raise ValueError("non_goals contract must be explicitly provided (empty list '[]' is allowed but cannot be omitted or None)")

    if not isinstance(non_goals, list):
        raise ValueError("non_goals must be a list")

    for i, item in enumerate(non_goals):
        if not isinstance(item, str):
            raise ValueError(f"non_goals item at index {i} must be a string")

    return non_goals


def validate_verification_conditions(verification_cases: list) -> list:
    """驗證 Verification cases 是否以 input、expect 或 expect_exception 正確表達 Pre/Post 條件。

    - verification_cases: 驗證案例列表。
    - 回傳: 驗證後的 cases 列表。
    """
    # ponytail: 沿用既有 Verification 結構表達 Pre/Post 條件，不新增重複欄位
    if verification_cases is None:
        raise ValueError("verification_cases contract must be explicitly provided (cannot be None)")

    if not isinstance(verification_cases, list):
        raise ValueError("verification_cases must be a list")

    for i, case in enumerate(verification_cases):
        if not isinstance(case, dict):
            raise ValueError(f"verification_cases item at index {i} must be an object (dict)")

        # Preconditions: 必須具有 input 欄位
        if "input" not in case:
            raise ValueError(f"verification_cases item at index {i} must specify 'input' (Preconditions)")

        # Postconditions: 必須具有 expect 或 expect_exception 之一
        has_expect = "expect" in case
        has_expect_exception = "expect_exception" in case

        if not has_expect and not has_expect_exception:
            raise ValueError(f"verification_cases item at index {i} must specify either 'expect' or 'expect_exception' (Postconditions)")

        if has_expect and has_expect_exception:
            raise ValueError(f"verification_cases item at index {i} cannot specify both 'expect' and 'expect_exception'")

        if has_expect_exception:
            if not isinstance(case["expect_exception"], str):
                raise ValueError(f"expect_exception in verification_cases item at index {i} must be a string")

    return verification_cases


def validate_assumptions(assumptions: list) -> list:
    """驗證並確保 Task 明確定義了 Assumptions 清單。

    - assumptions: 任務所依賴外部事實的假設字串列表。
    - 回傳: 驗證後的 assumptions 列表。
    """
    # ponytail: 為 Task 增加可快照可審核之外部依賴假設，不可為 None (空陣列代表明確確認無額外假設)
    if assumptions is None:
        raise ValueError("assumptions contract must be explicitly provided (empty list '[]' is allowed but cannot be omitted or None)")

    if not isinstance(assumptions, list):
        raise ValueError("assumptions must be a list")

    for i, item in enumerate(assumptions):
        if not isinstance(item, str):
            raise ValueError(f"assumptions item at index {i} must be a string")

    return assumptions


def _validate_json_schema_subset(schema: dict, field_name: str) -> dict:
    """內部共用：將既有通用 schema 驗證能力套用至 per-task JSON Schema。"""
    # ponytail: 沿用 validate_schema 的支援子集與錯誤格式，不建立第二套 JSON Schema 引擎
    if schema is None:
        raise ValueError(f"{field_name} must be explicitly provided (cannot be None)")

    if not isinstance(schema, dict):
        raise ValueError(f"{field_name} must be a dict")

    # 沿用 validate_schema 支援的關鍵字子集
    supported_keywords = {
        "type", "properties", "required", "additionalProperties",
        "enum", "items", "oneOf", "$ref", "$schema", "description"
    }

    # 第一步：檢查是否有不支援的進階關鍵字，防止 Agent 使用了系統無法機械驗證的語法
    for key in schema.keys():
        if key not in supported_keywords:
            raise ValueError(f"Unsupported JSON Schema keyword '{key}' (only sub-set used by validate_schema is supported)")

    # 第二步：驗證基本 JSON Schema 格式
    if "type" in schema:
        allowed_types = {"object", "array", "string", "integer", "number", "boolean", "null"}
        val_type = schema["type"]
        if isinstance(val_type, list):
            for t in val_type:
                if t not in allowed_types:
                    raise ValueError(f"Invalid type '{t}' in {field_name}")
        elif val_type not in allowed_types:
            raise ValueError(f"Invalid type '{val_type}' in {field_name}")

    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            raise ValueError("properties must be a dict")
        for prop_name, prop_val in schema["properties"].items():
            if not isinstance(prop_val, dict):
                raise ValueError(f"Property '{prop_name}' must be a dict")
            _validate_json_schema_subset(prop_val, field_name)

    if "required" in schema:
        if not isinstance(schema["required"], list):
            raise ValueError("required must be a list")
        for req_item in schema["required"]:
            if not isinstance(req_item, str):
                raise ValueError("All items in 'required' must be strings")
            if "properties" in schema and req_item not in schema["properties"]:
                raise ValueError(f"Required property '{req_item}' is not defined in 'properties'")

    if "enum" in schema:
        if not isinstance(schema["enum"], list):
            raise ValueError("enum must be a list")

    if "items" in schema:
        if not isinstance(schema["items"], dict):
            raise ValueError("items must be a dict")
        _validate_json_schema_subset(schema["items"], field_name)

    return schema


def validate_task_input_schema(input_schema: dict) -> dict:
    """將既有通用 schema 驗證能力套用至 per-task Input JSON Schema。

    - input_schema: 輸入參數的 JSON Schema 對象。
    - 回傳: 驗證後的 input_schema 對象。
    """
    return _validate_json_schema_subset(input_schema, "input_schema")


def validate_task_output_schema(output_schema: dict) -> dict:
    """將既有通用 schema 驗證能力套用至 per-task Output JSON Schema。

    - output_schema: 輸出參數的 JSON Schema 對象。
    - 回傳: 驗證後的 output_schema 對象。
    """
    return _validate_json_schema_subset(output_schema, "output_schema")




