# -*- coding: utf-8 -*-
"""
獨立於 parse_markdown/compile_map.py 的第二層防線：
驗證 system_map.yaml（compile_map.py 的產出）是否符合正式 JSON Schema 規格
（system_map.schema.json）。

為什麼需要這個，parse_markdown 明明已經在編譯時做過檢查（缺 Type、模組名稱重複等）？
因為「產生者」跟「檢查者」如果是同一段程式碼，程式碼本身的邏輯 bug 不會被自己抓到。
這支腳本刻意用一份跟 Python 實作完全脫鉤的標準 JSON Schema 檔案驗證，這樣：
  - compile_map.py 或 parse_markdown 未來如果被改壞了，這裡有機會抓到結構性錯誤
    （型別錯誤、非法 enum 值、缺少必要欄位）
  - 任何其他工具（IDE 外掛、CI、甚至非 Python 語言寫的工具）都可以直接拿同一份
    system_map.schema.json 驗證，不需要理解或依賴這份專案的 Python 實作

ponytail: 這裡刻意分兩層——
  1. 如果環境裝了 `jsonschema`（PyPI 標準套件），優先用它：功能最完整，
     完全遵循 JSON Schema 規格（$ref、oneOf、patternProperties...都支援）。
  2. 沒裝的話，退回一個只實作「這份 schema 實際用到的語法子集」的純標準庫
     驗證器（_MinimalValidator）——不是完整的 JSON Schema 引擎，但涵蓋
     type/required/properties/additionalProperties/enum/items/oneOf/$ref
     這幾種本專案 schema 檔案真正會用到的關鍵字，足以擋下型別錯誤、非法
     enum 值、缺必要欄位這幾種最常見的結構性錯誤。
  這樣不強迫使用者一定要多裝一個第三方套件才能用這層防線，但如果他們裝了
  更完整的 jsonschema，也能自動享有更嚴謹的驗證，不會被兩者打架。
"""
import sys
import os
import json

try:
    import yaml
except ImportError:
    import subprocess
    print("[ADAD] 偵測到未安裝 PyYAML，正在自動安裝...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "--quiet"])
        import yaml
    except Exception as e:
        print(json.dumps({"success": False, "error": f"無法自動安裝 PyYAML: {e}"}, ensure_ascii=False))
        sys.exit(1)

try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


class _MinimalValidator:
    """
    純標準庫實作的 JSON Schema 子集驗證器。只支援 system_map.schema.json
    實際用到的關鍵字：type / required / properties / additionalProperties /
    enum / items / oneOf / $ref（限 "#/$defs/..." 形式的內部參照）。

    刻意不支援 patternProperties、if/then/else、$dynamicRef 等更進階的
    JSON Schema 語法——這些本專案的 schema 檔案目前用不到，硬要支援只會
    增加維護負擔卻沒有實際驗證價值。若之後 schema 檔案真的需要這些語法，
    屆時再擴充，或改為要求安裝完整的 jsonschema 套件。
    """

    def __init__(self, schema):
        self.root_schema = schema

    def iter_errors(self, instance):
        errors = []
        self._validate(instance, self.root_schema, "", errors)
        for path, message in errors:
            yield _MinimalError(path, message)

    def _resolve(self, schema):
        if "$ref" in schema:
            ref = schema["$ref"]
            if not ref.startswith("#/"):
                raise ValueError(f"不支援的 $ref 格式（僅支援 '#/...' 內部參照）: {ref}")
            node = self.root_schema
            for part in ref[2:].split("/"):
                node = node[part]
            return node
        return schema

    @staticmethod
    def _type_ok(value, type_spec):
        if isinstance(type_spec, list):
            return any(_MinimalValidator._type_ok(value, t) for t in type_spec)
        mapping = {
            "object": dict, "array": list, "string": str,
            "integer": int, "number": (int, float), "boolean": bool, "null": type(None)
        }
        py_type = mapping.get(type_spec)
        if py_type is None:
            return True  # 未知型別敘述，不擋（保守起見，寧可漏放行也不誤擋）
        if type_spec == "integer" and isinstance(value, bool):
            return False  # bool 是 int 的子類別，Python isinstance 會誤判，需排除
        return isinstance(value, py_type)

    def _validate(self, data, schema, path, errors):
        schema = self._resolve(schema)

        if "type" in schema and not self._type_ok(data, schema["type"]):
            errors.append((path or "(root)", f"型別應為 {schema['type']}，實際是 {type(data).__name__}"))
            return  # 型別都不對，往下驗證欄位內容沒有意義

        if "enum" in schema and data not in schema["enum"]:
            errors.append((path or "(root)", f"值必須是 {schema['enum']} 之一，實際是 {data!r}"))

        if isinstance(data, dict):
            for req in schema.get("required", []):
                if req not in data:
                    errors.append((path or "(root)", f"缺少必要欄位 '{req}'"))
            props = schema.get("properties", {})
            additional = schema.get("additionalProperties")
            for key, value in data.items():
                sub_path = f"{path}/{key}" if path else key
                if key in props:
                    self._validate(value, props[key], sub_path, errors)
                elif isinstance(additional, dict):
                    self._validate(value, additional, sub_path, errors)
                elif additional is False:
                    errors.append((path or "(root)", f"不允許的額外欄位 '{key}'"))

        if isinstance(data, list) and "items" in schema:
            for i, item in enumerate(data):
                self._validate(item, schema["items"], f"{path}/{i}", errors)

        if "oneOf" in schema:
            matched = False
            for opt in schema["oneOf"]:
                tmp_errors = []
                self._validate(data, opt, path, tmp_errors)
                if not tmp_errors:
                    matched = True
                    break
            if not matched:
                errors.append((path or "(root)", f"不符合 oneOf 允許的任何一種格式：{data!r}"))


class _MinimalError:
    def __init__(self, path, message):
        self.path = [p for p in path.split("/") if p] if path and path != "(root)" else []
        self.message = message


def validate_schema_conformance(yaml_path="system_map.yaml", schema_path="system_map.schema.json"):
    """
    驗證 yaml_path 指向的檔案是否符合 schema_path 定義的正式規格。
    回傳 {"success": bool, "message"/"error": str, "errors": [...] (失敗時才有),
          "validator": "jsonschema" | "minimal"}。
    設計成可以被 compile_map.py 直接 import 呼叫（in-process），也可以獨立當 CLI 執行。
    """
    if not os.path.exists(schema_path):
        return {"success": False, "error": f"找不到 schema 檔案: {schema_path}"}
    if not os.path.exists(yaml_path):
        return {"success": False, "error": f"找不到 {yaml_path}，請先執行 compile_map.py"}

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        return {"success": False, "error": f"解析 schema 檔案 {schema_path} 失敗: {e}"}

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return {"success": False, "error": f"解析 {yaml_path} 失敗: {e}"}

    if _HAS_JSONSCHEMA:
        validator = jsonschema.Draft202012Validator(schema)
        validator_name = "jsonschema"
    else:
        validator = _MinimalValidator(schema)
        validator_name = "minimal"

    errors = sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.path)))

    if errors:
        error_list = []
        for e in errors:
            path = "/".join(str(p) for p in e.path) or "(root)"
            error_list.append({"path": path, "message": e.message})
        return {
            "success": False,
            "error": f"{yaml_path} 不符合 {schema_path} 的正式規格，共 {len(errors)} 項錯誤。",
            "errors": error_list,
            "validator": validator_name
        }

    return {
        "success": True,
        "message": f"{yaml_path} 符合 {schema_path} 的正式規格。",
        "validator": validator_name
    }


def main():
    yaml_path = sys.argv[1] if len(sys.argv) > 1 else "system_map.yaml"
    schema_path = sys.argv[2] if len(sys.argv) > 2 else "system_map.schema.json"
    result = validate_schema_conformance(yaml_path, schema_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
