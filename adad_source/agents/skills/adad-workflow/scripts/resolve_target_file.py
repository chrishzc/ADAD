# -*- coding: utf-8 -*-
"""
resolve_target_file.py — 子地圖落點解析工具

目的：Agent 在 Phase 1（架構規劃）要新增一個模組之前，不該靠自己讀
system_map.md、追蹤 <!-- include --> 鏈、憑印象猜「這個 Domain/Subsystem
現在是不是已經被拆到某個子地圖檔案」。這支腳本把答案直接查表算出來。

用法：
  python resolve_target_file.py <domain> [subsystem]

回傳 JSON：
  - target_file      ：應該把新模組寫進哪個實體檔案
  - domain_exists     ：這個 Domain 是否已存在
  - subsystem_exists  ：這個 Subsystem 是否已存在（未提供 subsystem 時為 null）
  - hint              ：給 Agent 的下一步建議（含尚未拆檔案時的建議寫法）
"""
import sys
import json
from adad_core import ADADCore


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "請提供 Domain 名稱（必要）與 Subsystem 名稱（選填）。"
                     "用法: python resolve_target_file.py <domain> [subsystem]"
        }, ensure_ascii=False))
        sys.exit(1)

    domain = sys.argv[1]
    subsystem = sys.argv[2] if len(sys.argv) > 2 else None

    # ADADCore 建構子預設 check_validity=True：
    # 若 system_map.md（或其子地圖）比 system_map.yaml 新，會直接阻斷並提示先編譯，
    # 避免這支工具根據過期的 IR 給出錯誤的落點建議。
    core = ADADCore()
    domains = core.data.get("domains", {})

    if domain not in domains:
        slug = domain.lower().replace(" ", "_")
        print(json.dumps({
            "domain_exists": False,
            "subsystem_exists": None,
            "target_file": "system_map.md",
            "hint": (
                f"Domain `{domain}` 尚未存在於架構中，預設應寫入根檔案 system_map.md。"
                f"若預期這個 Domain 會持續成長，建議一開始就拆成獨立子地圖檔案"
                f"（例如 docs/domains/{slug}.md），在 system_map.md 對應位置加入 "
                f"`<!-- include docs/domains/{slug}.md -->`，再把 Domain/Subsystem/Module "
                f"定義寫進該檔案，避免根檔案繼續肥大。"
            )
        }, ensure_ascii=False, indent=2))
        sys.exit(0)

    dom_info = domains[domain]
    dom_file = dom_info.get("map_file", "system_map.md")

    if subsystem:
        subs = dom_info.get("subsystems", {})
        if subsystem not in subs:
            print(json.dumps({
                "domain_exists": True,
                "subsystem_exists": False,
                "target_file": dom_file,
                "hint": (
                    f"Subsystem `{subsystem}` 在 Domain `{domain}` 底下尚未存在，"
                    f"預設會寫入 Domain `{domain}` 目前的落腳檔案 `{dom_file}`。"
                    f"若預期這個 Subsystem 會持續成長，建議另外拆一個子地圖檔案，"
                    f"並在 `{dom_file}` 對應位置加入 include 把它串進來。"
                )
            }, ensure_ascii=False, indent=2))
            sys.exit(0)

        target = subs[subsystem].get("map_file", dom_file)
        print(json.dumps({
            "domain_exists": True,
            "subsystem_exists": True,
            "target_file": target,
            "hint": f"請直接在 `{target}` 這個檔案裡，於 `#### Subsystem: {subsystem}` 底下新增 `##### Module:` 節點。"
        }, ensure_ascii=False, indent=2))
        sys.exit(0)

    print(json.dumps({
        "domain_exists": True,
        "subsystem_exists": None,
        "target_file": dom_file,
        "hint": f"請直接在 `{dom_file}` 這個檔案裡，於 `### Domain: {domain}` 底下新增 Subsystem 或 `##### Module:` 節點。"
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
