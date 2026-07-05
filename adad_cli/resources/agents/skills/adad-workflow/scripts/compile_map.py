# -*- coding: utf-8 -*-
import sys
import os
import json
from adad_core import ADADCore, parse_markdown

def main():
    md_path = "system_map.md"
    yaml_path = "system_map.yaml"
    
    if not os.path.exists(md_path):
        print(json.dumps({"success": False, "error": f"找不到架構源檔案 {md_path}"}, ensure_ascii=False))
        sys.exit(1)
        
    try:
        from adad_core import resolve_includes
        md_content = resolve_includes(md_path)
    except Exception as e:
        print(json.dumps({"success": False, "error": f"解析 include 檔案與讀取 {md_path} 失敗: {e}"}, ensure_ascii=False))
        sys.exit(1)
        
    # 1. 解析 Markdown
    try:
        compiled_data = parse_markdown(md_content)
    except Exception as e:
        print(json.dumps({"success": False, "error": f"解析 Markdown 失敗: {e}"}, ensure_ascii=False))
        sys.exit(1)
        
    # 驗證必要欄位
    for mod_name, mod_info in compiled_data.get("modules", {}).items():
        if not mod_info.get("type"):
            print(json.dumps({"success": False, "error": f"編譯失敗：模組 [{mod_name}] 缺少必要欄位 'Type'"}, ensure_ascii=False))
            sys.exit(1)
            
    # 2. 智慧狀態合併
    # 讀取舊的 YAML (若存在)
    core = ADADCore(yaml_path, check_validity=False)
    old_modules = core.data.get("modules", {})
    
    for mod_name, mod_info in compiled_data.get("modules", {}).items():
        # 如果舊 YAML 存在該模組
        if mod_name in old_modules:
            old_mod = old_modules[mod_name]
            # 比對結構 (input, output, dependencies)
            struct_match = (
                mod_info.get("input") == old_mod.get("input") and
                mod_info.get("output") == old_mod.get("output") and
                sorted(mod_info.get("dependencies", [])) == sorted(old_mod.get("dependencies", []))
            )
            if struct_match:
                # 結構無變動，繼承狀態
                mod_info["state"] = old_mod.get("state", "planned")
            else:
                # 結構有變動，重置為 dirty
                mod_info["state"] = "dirty"
        else:
            # 全新模組，狀態為 planned
            mod_info["state"] = "planned"
            
    # 3. 寫入並更新 YAML
    core.data["version"] = compiled_data.get("version", 1)
    core.data["modules"] = compiled_data.get("modules", {})
    # ponytail-fix: 原本編譯只寫回 modules，domains（含 Domain/Subsystem 的
    # map_file 落點資訊）解析完就被丟棄，導致 resolve_target_file.py 與
    # find_misplaced_modules 永遠查不到任何 Domain。必須一併持久化進 YAML。
    core.data["domains"] = compiled_data.get("domains", {})

    # 3.5 Draft Debt Ledger 偵測
    debt_result = core.check_draft_debt()
    core.save()
    
    # 強制確保 system_map.yaml 的修改時間稍微新於 system_map.md (大於 1.5 秒)
    # 這能確保編譯後 read_context 不會被過期阻斷判定誤導
    try:
        os.utime(yaml_path, None)
    except Exception:
        pass

    # 輸出 Draft Debt 警告（若有觸發）
    if debt_result["checkpoint_required"]:
        print("\n⚠️  [DRAFT DEBT] 以下模組因 fan-in 突破閾值，已自動升級為 pending_review：")
        for p in debt_result["promoted_nodes"]:
            if "old_fan_in" in p:
                print(f"   - {p['node']} (fan-in: {p['old_fan_in']} → {p['new_fan_in']})")
            else:
                print(f"   - {p['node']} (原因: {p.get('reason', 'N/A')})")
        print("🚧 需要觸發一次補做 Checkpoint（含 ADR），請執行架構審查。\n")

    # 孤兒子地圖偵測（不阻斷編譯，僅提示）
    from adad_core import find_orphan_maps
    orphans = find_orphan_maps(md_path)
    if orphans:
        print("\n⚠️  [ORPHAN MAP] 以下 .md 檔案位於子地圖目錄底下，但沒有被任何 include 鏈引用到：")
        for o in orphans:
            print(f"   - {o}")
        print("   請確認是否忘記在對應的父地圖加上 <!-- include ... --> ，否則這些內容不會被編譯進架構。\n")

    # 模組落點偵測（不阻斷編譯，僅提示；commit 前會由 adad_pre_commit.py 硬性阻擋）
    from adad_core import find_misplaced_modules
    misplaced = find_misplaced_modules(core.data)
    if misplaced:
        print("\n⚠️  [MISPLACED MODULE] 以下模組寫的實體檔案，跟它所屬 Domain/Subsystem 目前落腳的子地圖不一致：")
        for m in misplaced:
            print(f"   - {m['module']}（屬於 {m['scope']} `{m['scope_name']}`）："
                  f"目前寫在 [{m['actual_file']}]，應搬到 [{m['expected_file']}]")
        print("   請執行 python .agents/skills/adad-workflow/scripts/resolve_target_file.py <domain> [subsystem] 確認正確落點。\n")

    # ponytail-fix: 主動提醒 pre-commit hook 有沒有真的裝上，避免「README 有寫、
    # 但沒人真的執行過 install.py init」導致 RULE-01~05 等機械強制其實是關閉的假象。
    from adad_core import check_precommit_hook_status
    hook_status = check_precommit_hook_status()
    if hook_status["is_git_repo"] and not hook_status["hook_installed"]:
        print(
            "\n⚠️  [NO GUARDRAIL] 目前是 git repo，但尚未安裝 pre-commit hook——"
            "RULE-01~05、Invariants、Verification 等機械強制目前實際上完全沒有在運作。\n"
            "   請執行 python install.py init 安裝 hook，或至少在 CI/CD 中另外執行 "
            "python .agents/skills/adad-workflow/scripts/adad_pre_commit.py 作為最後防線。\n"
        )

    # 靜默脫鉤偵測（不阻斷編譯，僅提示）：
    # 整檔登記（非 ::逐函式）的模組，RULE-04 完全不會檢查它有沒有長出新函式，
    # 而且只要模組狀態還在 planned/draft/dirty/validated 這幾個「允許自由編輯」
    # 的階段，RULE-02 也不會攔——這代表這類模組可以在完全沒有任何提示的情況下
    # 悄悄長出新函式。這裡補一個非阻斷性警告：只要偵測到「上次編譯記錄過的
    # known_symbols」跟「這次實際掃到的 top-level 函式/方法」不一致，就提醒一聲，
    # 讓 Agent/人類下次跑編譯或 resume_analysis 時至少看得到。
    # 第一次編譯（尚無 known_symbols 記錄）只建立基準線，不算漂移、不發警告。
    from adad_core import build_file_to_registered_functions, get_top_level_function_names
    untracked = []
    file_map = build_file_to_registered_functions(core.data["modules"])
    for file_path, entry in file_map.items():
        if not entry["whole_file"] or not entry["nodes"]:
            continue
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                src = f.read()
        except Exception:
            continue
        current_symbols = get_top_level_function_names(src)
        if current_symbols is None:
            continue  # 語法錯誤，交給其他工具處理
        node_name = entry["nodes"][0]
        mod_info = core.data["modules"].get(node_name)
        if mod_info is None:
            continue
        # ponytail-fix: 這裡的 core.data["modules"] 在上面（第 62 行）已經被整個
        # 換成剛從 Markdown 重新解析出來的全新 dict，從來不會帶有 known_symbols
        # 欄位——用它當比對基準的話，known 永遠是空集合，警告永遠不會觸發。
        # 真正的「上次記錄」必須從編譯前讀進來的舊 yaml（old_modules）拿。
        known = set(old_modules.get(node_name, {}).get("known_symbols", []))
        new_symbols = current_symbols - known
        if known and new_symbols:
            untracked.append({
                "module": node_name,
                "file": file_path,
                "new_symbols": sorted(new_symbols)
            })
        mod_info["known_symbols"] = sorted(current_symbols)

    # ponytail-fix: 上面才把 known_symbols 寫進 core.data，但 core.save() 在更早
    # 之前就執行過了，這裡必須再存一次，否則 known_symbols 只存在記憶體裡、
    # 下次編譯又會被當成全新基準線，靜默脫鉤偵測永遠不會真的觸發。
    core.save()

    if untracked:
        print("\n⚠️  [UNTRACKED SYMBOL] 以下整檔登記的模組，偵測到先前沒見過的新函式/方法：")
        for u in untracked:
            print(f"   - {u['module']}（{u['file']}）：新出現 {u['new_symbols']}")
        print("   請確認這些新函式是否真的屬於這個模組的既定用途；"
              "若這個檔案的職責已經變得複雜，考慮改用 `Source: file.py::func1,func2` 逐函式登記，"
              "才能啟用 RULE-04 的硬性保護。\n")

    print(json.dumps({
        "success": True,
        "message": f"編譯成功！已將 {md_path} 編譯為 {yaml_path}，並完成狀態合併。",
        "draft_debt": debt_result,
        "orphan_maps": orphans,
        "misplaced_modules": misplaced,
        "untracked_symbols": untracked,
        "precommit_hook_installed": hook_status["hook_installed"]
    }, ensure_ascii=False, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    main()
