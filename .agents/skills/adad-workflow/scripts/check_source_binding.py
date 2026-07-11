# -*- coding: utf-8 -*-
"""
check_source_binding.py — Source 綁定完整性檢查（代辦事項 #8）

獨立可執行的 CLI，對 system_map.yaml 目前所有模組的 `source` 欄位做歧義檢查，
確保「檔案/函式 → 模組」反查表是唯一、無歧義的——這是 adad_pre_commit.py /
adad_pretooluse_gate.py 所有機械強制賴以運作的地基（見 SKILL.md 的 Source 欄位
規範一節）。

用法：
  python check_source_binding.py

輸出 JSON：{"passed": bool, "violations": [...], "unbound": [...]}
違規時 exit code 為 1，通過為 0（`unbound` 只是軟提示，不影響 exit code）。
"""
import sys
import json
from adad_core import ADADCore


def main():
    core = ADADCore()
    result = core.check_source_binding()

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
