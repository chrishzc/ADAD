# -*- coding: utf-8 -*-
import sys
import os
import json
from adad_core import ADADCore, parse_markdown, resolve_includes

def main():
    # 強制重置標準輸出編碼為 utf-8 以支援 Windows 環境下的 Unicode 表情符號
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    md_path = "system_map.md"
    yaml_path = "system_map.yaml"
    
    if not os.path.exists(md_path):
        print(f"錯誤：找不到架構源檔案 {md_path}")
        sys.exit(1)
        
    # ponytail-fix: 原本直接 open(md_path).read()，完全沒有展開 <!-- include --> 鏈，
    # 導致專案一旦使用分區地圖（split-map）功能，所有寫在子地圖檔案裡的模組會被
    # 這份進度報告完全漏掉（沒有錯誤或警告），跟 compile_map.py 的行為不一致。
    # 改為比照 compile_map.py，統一透過 resolve_includes 展開後再解析。
    try:
        md_content = resolve_includes(md_path)
    except Exception as e:
        print(f"解析 include 檔案與讀取 {md_path} 失敗: {e}")
        sys.exit(1)
        
    compiled_data = parse_markdown(md_content)
    modules = compiled_data.get("modules", {})
    
    # 讀取當前 YAML 以獲得實際的生命週期狀態
    core = ADADCore(yaml_path, check_validity=False)
    actual_modules = core.data.get("modules", {})
    
    completed_modules = []
    dirty_modules = []
    planned_modules = []
    draft_modules = []
    
    todo_list = []
    pending_checkpoints = []
    
    for mod_name, mod_info in modules.items():
        actual_state = actual_modules.get(mod_name, {}).get("state", "planned")
        
        if actual_state == "deployed":
            completed_modules.append(mod_name)
        elif actual_state == "dirty":
            dirty_modules.append(mod_name)
        elif actual_state in ("draft", "pending_review"):
            draft_modules.append((mod_name, actual_state))
        else:
            planned_modules.append(mod_name)
            
        # 收集 TODO
        for t in mod_info.get("todo", []):
            todo_list.append(f"- [{mod_name}] {t}")
            
        # 收集未完成的 Checkpoint
        for cp in mod_info.get("checkpoint", []):
            if "[ ]" in cp:
                pending_checkpoints.append(f"- [{mod_name}] {cp.replace('[ ]', '').strip()}")
                
    # 智能下一步分析 (Topological Suggestion)
    next_suggestions = []
    for mod_name, mod_info in modules.items():
        actual_state = actual_modules.get(mod_name, {}).get("state", "planned")
        if actual_state != "deployed":
            deps = mod_info.get("dependencies", [])
            all_deps_deployed = True
            for dep in deps:
                dep_state = actual_modules.get(dep, {}).get("state", "planned")
                if dep_state != "deployed":
                    all_deps_deployed = False
                    break
            if all_deps_deployed:
                next_suggestions.append((mod_name, actual_state))
                
    # 計算 fan-in
    fan_in_map = {}
    for mod_name, mod_info in actual_modules.items():
        for dep in mod_info.get("dependencies", []):
            fan_in_map[dep] = fan_in_map.get(dep, 0) + 1

    # 輸出 Markdown 報告
    print(f"# 📊 ADAD Architecture Resume Analysis")

    # ponytail-fix: Resume 是 Agent 啟動/接手任務時最先看的報告，
    # 在這裡主動秀出「pre-commit hook 到底有沒有真的裝上」，
    # 避免文件寫了 install.py init、但沒人真的執行過，導致所有機械強制
    # 其實完全沒在運作，卻沒有任何地方會提醒。
    from adad_core import check_precommit_hook_status
    hook_status = check_precommit_hook_status()
    if hook_status["is_git_repo"] and not hook_status["hook_installed"]:
        print(
            "\n> ⚠️ **[NO GUARDRAIL]** 目前是 git repo，但尚未安裝 pre-commit hook——"
            "RULE-01~05、Invariants、Verification 等機械強制目前實際上完全沒有在運作。"
            "請執行 `python install.py init` 安裝 hook，或至少在 CI/CD 中另外執行 "
            "`adad_pre_commit.py` 作為最後防線。\n"
        )

    print(f"\n## 📈 目前架構進度")
    print(f"- **已完成部署 (Deployed)**: {len(completed_modules)}/{len(modules)}")
    for m in completed_modules:
        print(f"  - `{m}`")
    print(f"- **待修改 (Dirty)**: {len(dirty_modules)}")
    for m in dirty_modules:
        print(f"  - `{m}`")
    print(f"- **規劃中 (Planned/Validated)**: {len(planned_modules)}")
    for m in planned_modules:
        print(f"  - `{m}` (狀態: `{actual_modules.get(m, {}).get('state', 'planned')}`)")
    if draft_modules:
        print(f"- **草稿 (Draft/Pending Review)**: {len(draft_modules)}")
        for m, state in draft_modules:
            print(f"  - `{m}` (狀態: `{state}`)")
        
    print(f"\n## 📝 待辦事項 (TODO)")
    if todo_list:
        for t in todo_list:
            print(t)
    else:
        print("沒有未完成的 TODO 項目。")
        
    print(f"\n## 🚧 未完成的 Checkpoints")
    if pending_checkpoints:
        for cp in pending_checkpoints:
            print(cp)
    else:
        print("沒有未完成的 Checkpoints。")
        
    print(f"\n## 💡 下一步開發建議")
    if next_suggestions:
        print("依據依賴關係，以下模組的依賴項皆已部署完成，建議優先進行開發/驗證：")
        for m, state in next_suggestions:
            print(f"- [ ] `{m}` (當前狀態: `{state}`)")
    elif len(completed_modules) == len(modules):
        print("恭喜！所有規劃的架構模組均已完成部署。")
    else:
        print("由於存在循環依賴或未部署的底層依賴，請先檢查是否有依賴未定義。")

    # Draft Debt Ledger
    all_draft = [(name, info) for name, info in actual_modules.items()
                 if info.get("state") in ("draft", "pending_review")]
    if all_draft:
        print(f"\n## 📋 Draft Debt Ledger")
        print("以下模組仍處於 draft/pending_review 狀態，尚未經過正式 Checkpoint 審查：\n")
        print("| 模組名稱 | 當前 Fan-In | 狀態 | 風險等級 |")
        print("|----------|------------|------|---------|")
        for name, info in all_draft:
            fi = fan_in_map.get(name, 0)
            state = info.get("state", "draft")
            if state == "pending_review":
                risk = "🔴 高（已觸發，等待 CP）"
            elif fi >= 1:
                risk = "🟡 中（有依賴者）"
            else:
                risk = "🟢 低（無依賴者）"
            print(f"| `{name}` | {fi} | `{state}` | {risk} |")
        
if __name__ == "__main__":
    main()
