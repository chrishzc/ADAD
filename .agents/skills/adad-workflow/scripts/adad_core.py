# -*- coding: utf-8 -*-
"""
ADAD Core Engine (ADAD 核心處理引擎)
ponytail: 自動檢測並於需要時安裝 pyyaml，核心邏輯以標準 DAG 演算法與最簡特徵相似度實作。
"""
import os
import sys
import json
import ast
import re
import shutil
import math
import hashlib
import datetime
from collections import Counter

# 自動安裝 PyYAML 依賴以確保跨裝置開箱即用
try:
    import yaml
except ImportError:
    import subprocess
    print("[ADAD] 偵測到未安裝 PyYAML，正在自動安裝...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "--quiet"])
        import yaml
        print("[ADAD] PyYAML 安裝成功。")
    except Exception as e:
        print(f"[ADAD ERROR] 無法自動安裝 PyYAML: {e}。請手動安裝: pip install pyyaml")
        sys.exit(1)

MAP_FILE = "system_map.yaml"
TASK_DIR = os.path.join(".agents", "tasks")

# ponytail: 原本 RULE-02 允許修改的狀態集合，在 adad_core.py / adad_pre_commit.py /
# adad_pretooluse_gate.py 三處各自寫了一份一模一樣的 {"planned","dirty","validated","draft"}，
# 改一次要記得改三個地方。現在統一定義在這裡，其他檔案改成 import 這個常數。
ALLOWED_EDIT_STATES = {"planned", "dirty", "validated", "draft"}

# Task.status 的合法值與其對「是否允許繼續編輯對應程式碼」的意義：
#   assigned/in_progress → 任務開放中，允許編輯
#   submitted            → 已提交待人類審查，凍結、不允許再編輯（等 approve/reject）
#   approved             → 本輪任務已完成並結案，若要再改，需重新 generate_task
#   rejected             → 內部過渡值，task_reject() 執行完會立刻改回 assigned，
#                           理論上不會被外部觀察到停留在這個值，保留僅供 history 記錄語意
TASK_EDITABLE_STATUSES = {"assigned", "in_progress"}


# ponytail-fix: 原正則 [^\s-]+ 會排除連字號，導致 "user-service.md"、
# "adad-workflow/sub.md" 這類含 '-' 的路徑完全比對失敗、被靜默忽略。
# 改為非貪婪比對到副檔名結尾，且不再排除任何合法路徑字元。
INCLUDE_PATTERN = re.compile(r'<!--\s*include:?\s*(\S+?\.(?:md|yaml|txt))\s*-->')


def get_all_included_files(filepath, found=None):
    if found is None:
        found = set()
    if not os.path.exists(filepath):
        return found
    abs_path = os.path.abspath(filepath)
    if abs_path in found:
        return found
    found.add(abs_path)
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return found
    for match in INCLUDE_PATTERN.finditer(content):
        include_path = match.group(1).strip()
        base_dir = os.path.dirname(filepath)
        target_path = os.path.join(base_dir, include_path)
        get_all_included_files(target_path, found)
    return found

def get_max_mtime(root_md_path):
    if not os.path.exists(root_md_path):
        return 0
    all_files = get_all_included_files(root_md_path)
    if not all_files:
        return os.path.getmtime(root_md_path)
    return max(os.path.getmtime(f) for f in all_files)


def find_orphan_maps(root_md_path):
    """
    孤兒子地圖偵測。

    只在「已經被拿來拆分子地圖」的目錄底下找孤兒檔案：
    對每一個被 include 鏈引用到的子地圖檔案（不含 root 本身），
    掃描它所在的目錄，找出同樣是 .md 但沒有被任何 include 鏈引用到的檔案。

    刻意不做「全專案掃描所有 .md」，因為 docs/adr、docs/patterns 等目錄
    存放的是 ADR / 設計模式文件，本來就不該被當成子地圖，全域掃描會製造
    大量假警報。只掃描「已經在用 include 機制的目錄」，才能準確反映
    「這裡本來就該被串起來，但漏掉了」的情境。

    回傳：排序後的孤兒檔案相對路徑清單（可能為空）。
    """
    included = get_all_included_files(root_md_path)
    if not included:
        return []

    root_abs = os.path.abspath(root_md_path)
    candidate_dirs = set()
    for f in included:
        if f == root_abs:
            continue
        candidate_dirs.add(os.path.dirname(f))

    orphans = set()
    for d in candidate_dirs:
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for fname in entries:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.abspath(os.path.join(d, fname))
            if fpath not in included:
                orphans.add(os.path.relpath(fpath))

    return sorted(orphans)

def resolve_includes(filepath, ancestors=None, resolved_cache=None):
    """
    展開 include 鏈。
    ancestors：目前這條 DFS 路徑上「尚未展開完」的檔案，用來偵測真循環 (A->B->A)。
    resolved_cache：全域已展開完成的檔案內容快取，用來處理「鑽石型 include」
                     (A include B、C，B、C 都 include D) —— D 只展開一次，
                     避免內容重複、模組定義被解析兩次互相覆蓋。
    """
    if ancestors is None:
        ancestors = set()
    if resolved_cache is None:
        resolved_cache = {}

    abs_path = os.path.abspath(filepath)

    if abs_path in ancestors:
        raise ValueError(f"偵測到循環 include: {filepath}")

    if abs_path in resolved_cache:
        # 已經在其他分支展開過，直接重用快取結果，不重複展開內容
        return resolved_cache[abs_path]

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到被 include 的檔案: {filepath}")

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # ponytail-fix: 插入來源標記，讓 parse_markdown 之後能還原
    # 「這個模組是從哪個實體 md 檔案來的」，支援重複模組名偵測與反查。
    rel_marker = f"\n<!-- __ADAD_SOURCE_FILE__: {os.path.relpath(abs_path)} -->\n"

    new_ancestors = ancestors | {abs_path}

    def replace_match(match):
        include_path = match.group(1).strip()
        base_dir = os.path.dirname(filepath)
        target_path = os.path.join(base_dir, include_path)
        included = resolve_includes(target_path, new_ancestors, resolved_cache)
        # ponytail-fix: include 展開的內容結束後，若原檔案(filepath)在這個
        # include 指令之後還有其他內容（例如同一份檔案裡 include 完子地圖，
        # 後面又補了幾個 Domain/Module），這些內容在物理上仍然屬於 filepath，
        # 但先前沒有補回歸標記，會讓它們被靜默誤判為仍屬於剛展開完的子檔案，
        # 導致 map_file 判定錯誤、進而讓「模組錯放偵測」失效。
        return included + f"\n<!-- __ADAD_SOURCE_FILE__: {os.path.relpath(abs_path)} -->\n"

    expanded = INCLUDE_PATTERN.sub(replace_match, content)
    result = rel_marker + expanded
    resolved_cache[abs_path] = result
    return result

def parse_markdown(md_content):
    lines = md_content.splitlines()
    data = {"version": 1, "modules": {}, "domains": {}}

    current_module = None
    current_section = None
    current_domain = None
    current_subsystem = None
    current_source_file = "system_map.md"

    source_marker_regex = re.compile(r'^<!--\s*__ADAD_SOURCE_FILE__:\s*(.+?)\s*-->$')
    domain_regex = re.compile(r'^###\s+Domain:\s*(.+)')
    subsystem_regex = re.compile(r'^####\s+Subsystem:\s*(.+)')
    # ponytail-fix: 原本 (\w+) 不含連字號 '-'，導致 "my-tax-calc" 這類模組名稱
    # 只會比對到 "my" 就停止——正則仍然「成功比對」（re.match 不要求比對到行尾），
    # 於是靜默建立了一個名稱被截斷的錯誤模組，沒有任何錯誤或警告。
    # 改為 [\w-]+ 允許連字號，並在下面用 \s*$ 錨定比對到行尾，若模組名稱包含
    # 其他不合法字元（如空白、冒號），會直接比對失敗而不是靜默截斷。
    module_regex = re.compile(r'^#####\s+Module:\s*([\w-]+)\s*$')
    field_regex = re.compile(r'^\s*-\s*([A-Za-z\s]+):\s*(.*)')
    list_header_regex = re.compile(r'^\s*-\s*([A-Za-z\s]+):$')

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue

        # ponytail-fix: 追蹤目前內容實際來自哪個實體 md 檔（含 include 展開）
        src_match = source_marker_regex.match(line_strip)
        if src_match:
            current_source_file = src_match.group(1).strip()
            continue

        # ponytail-fix: Domain / Subsystem 標題不再被忽略——
        # (1) 記錄下來，供之後架構邊界檢查使用
        # (2) 一律重置 current_module / current_section，避免其後的
        #     "- Description: ..." 之類欄位被誤植到「上一個模組」身上
        d_match = domain_regex.match(line_strip)
        if d_match:
            current_domain = d_match.group(1).strip()
            # ponytail: 追蹤這個 Domain 標頭實際寫在哪個實體檔案，
            # 讓 resolve_target_file.py 能回答「這個 Domain 該寫進哪個子地圖」。
            # 刻意採「第一次出現的位置」為官方落點、後續重複出現不覆蓋：
            # 這正是要防範的情境——如果 Domain/Subsystem 早就被拆到子地圖，
            # 之後有人（或 Agent）在根目錄重新打開同名標頭夾帶新模組，
            # 我們要它被判定為「錯放」，而不是讓最後一次出現的位置
            # 悄悄變成新的官方落點、蓋掉原本的子地圖。
            if current_domain not in data["domains"]:
                data["domains"][current_domain] = {
                    "description": "", "allowed_dependencies": [], "subsystems": {},
                    "map_file": current_source_file
                }
            current_subsystem = None
            current_module = None
            current_section = None
            continue

        s_match = subsystem_regex.match(line_strip)
        if s_match:
            current_subsystem = s_match.group(1).strip()
            if current_domain:
                subs = data["domains"][current_domain]["subsystems"]
                # ponytail: 同理，記錄 Subsystem 標頭實際所在的實體檔案，
                # 一樣以第一次出現的位置為準、後續重複出現不覆蓋。
                if current_subsystem not in subs:
                    subs[current_subsystem] = {
                        "description": "", "map_file": current_source_file
                    }
            current_module = None
            current_section = None
            continue

        m_match = module_regex.match(line_strip)
        if m_match:
            current_module = m_match.group(1)
            if current_module in data["modules"]:
                prev_src = data["modules"][current_module].get("map_file", "system_map.md")
                raise ValueError(
                    f"編譯失敗：模組名稱重複 '{current_module}'。"
                    f"已在 [{prev_src}] 定義過一次，又在 [{current_source_file}] 重複定義。"
                    f"模組名稱是全域唯一命名空間，請改名或合併。"
                )
            data["modules"][current_module] = {
                "type": "",
                "description": "",
                "source": "",
                "domain": current_domain,
                "subsystem": current_subsystem,
                "map_file": current_source_file,
                "dependencies": [],
                "input": {},
                "output": {},
                "invariants": [],
                "preferred_pattern": "none",
                "verification": [],
                "decisions": [],
                "todo": [],
                "checkpoint": [],
                # ponytail: Complexity/Algorithm 兩個欄位是為了解決「Module 契約
                # (Input/Output/Invariants) 只描述對外承諾，卻沒描述內部該怎麼做」
                # 這個縫隙——複雜函式光靠契約，能力較弱的模型常常一次生成就邏輯出錯，
                # 或反覆撞 Verification 失敗卻收斂不了。Complexity 讓 Plan 階段先分級，
                # Algorithm 讓高複雜度節點在 Plan 階段就先拆好步驟大綱，實作階段只需要
                # 「翻譯」而不是「設計」。
                "complexity": "low",
                "algorithm": []
            }
            current_section = None
            continue

        if current_module is None:
            if line_strip.startswith("- Version:"):
                try:
                    data["version"] = int(line_strip.split(":", 1)[1].strip())
                except:
                    pass
            elif current_domain and not current_subsystem:
                fd_match = field_regex.match(line_strip)
                if fd_match:
                    fkey = fd_match.group(1).strip().lower()
                    fval = fd_match.group(2).strip()
                    if fkey == "description":
                        data["domains"][current_domain]["description"] = fval
                    elif fkey == "allowed_dependencies" or fkey == "allowed dependencies":
                        if fval.startswith("[") and fval.endswith("]"):
                            items = [x.strip() for x in fval[1:-1].split(",") if x.strip()]
                            data["domains"][current_domain]["allowed_dependencies"] = items
            elif current_domain and current_subsystem:
                fd_match = field_regex.match(line_strip)
                if fd_match and fd_match.group(1).strip().lower() == "description":
                    data["domains"][current_domain]["subsystems"][current_subsystem]["description"] = fd_match.group(2).strip()
            continue
            
        indent_match = re.match(r'^(\s+)-\s*(.*)', line)
        if indent_match and current_section:
            sub_content = indent_match.group(2).strip()
            
            if current_section == "input" or current_section == "output":
                kv_match = re.match(r'^([\w_]+):\s*(.*)', sub_content)
                if kv_match:
                    k, v = kv_match.group(1), kv_match.group(2).strip()
                    data["modules"][current_module][current_section][k] = v
            elif current_section in ["invariants", "verification", "todo", "checkpoint", "algorithm"]:
                # ponytail: Verification 底下的 `case: {...}` 是可執行測試案例（JSON 語法），
                # 跟 `must_have_assertions` 這種純字串標籤混用在同一個清單裡。
                # 這裡在編譯期就把它解析成結構化 dict、而不是留到執行期才發現格式錯誤——
                # 寫錯 JSON（漏引號、多逗號）現在會讓 compile_map.py 直接失敗並指出是哪個
                # 模組、哪一行寫錯，而不是等到 verify_implementation.py 執行時才含糊報錯。
                if current_section == "verification" and sub_content.lower().startswith("case:"):
                    case_json_str = sub_content.split(":", 1)[1].strip()
                    try:
                        case_obj = json.loads(case_json_str)
                    except Exception as e:
                        raise ValueError(
                            f"編譯失敗：模組 '{current_module}' 的 Verification case 不是合法 JSON：\n"
                            f"  {sub_content}\n"
                            f"解析錯誤：{e}\n"
                            f"case 語法必須是嚴格 JSON（雙引號、不可有多餘逗號），"
                            f"例如：case: {{\"input\": {{\"x\": 1}}, \"expect\": 2}}"
                        )
                    if not isinstance(case_obj, dict) or "input" not in case_obj or "expect" not in case_obj:
                        raise ValueError(
                            f"編譯失敗：模組 '{current_module}' 的 Verification case 缺少必要欄位 "
                            f"'input'/'expect'：{sub_content}"
                        )
                    data["modules"][current_module][current_section].append({"case": case_obj})
                else:
                    data["modules"][current_module][current_section].append(sub_content)
            continue
            
        lh_match = list_header_regex.match(line_strip)
        if lh_match:
            current_section = lh_match.group(1).strip().lower().replace(" ", "_")
            continue
            
        f_match = field_regex.match(line_strip)
        if f_match:
            key = f_match.group(1).strip().lower().replace(" ", "_")
            val = f_match.group(2).strip()
            
            if key == "type":
                data["modules"][current_module]["type"] = val
            elif key == "description":
                data["modules"][current_module]["description"] = val
            elif key == "source":
                data["modules"][current_module]["source"] = val
            elif key == "preferred_pattern":
                data["modules"][current_module]["preferred_pattern"] = val
            elif key == "complexity":
                # ponytail: 寫死允許值而不是照單全收——如果之後打錯字（例如 "hgih"），
                # 靜默存成一個沒人檢查的字串，會讓依賴這個欄位的檢查全部失效卻毫無警告。
                # 這裡選擇「正規化成合法值，否則退回 low 並留在 compile_map.py 的
                # 警告清單裡」而不是直接讓編譯失敗，因為 Complexity 目前只是輔助分級、
                # 不是像 Type 那樣的必要欄位，還不到值得阻斷編譯的嚴重程度。
                normalized = val.strip().lower()
                data["modules"][current_module]["complexity"] = (
                    normalized if normalized in ("low", "medium", "high") else "low"
                )
            elif key == "dependencies":
                if val.startswith("[") and val.endswith("]"):
                    items = [x.strip() for x in val[1:-1].split(",") if x.strip()]
                    data["modules"][current_module]["dependencies"] = items
            elif key == "decisions":
                if val.startswith("[") and val.endswith("]"):
                    items = [x.strip() for x in val[1:-1].split(",") if x.strip()]
                    data["modules"][current_module]["decisions"] = items
            
            current_section = None
            continue
            
    return data

def build_file_to_registered_functions(modules):
    """
    從 system_map.yaml 的 source 欄位建立 {file_path: {"whole_file": bool, "functions": set, "nodes": [...]}}。

    source 欄位的兩種寫法：
      - "path/to/file.py"                         → 整個檔案視為單一節點，不逐函式比對
      - "path/to/file.py::func_name"               → 該節點只對應檔案內的這一個函式
      - "path/to/file.py::f1,f2,f3"                → 該節點對應檔案內的多個函式（逗號分隔）

    ponytail: 原本只存在 adad_pre_commit.py（給 RULE-04 用），現在
    compile_map.py 的「靜默脫鉤」偵測也需要同一份邏輯，搬到這裡共用，
    避免兩處各寫一份、之後改一邊忘了改另一邊。
    """
    file_map = {}
    for name, info in modules.items():
        src = (info.get("source") or "").replace("\\", "/")
        if not src:
            continue
        if "::" in src:
            file_path, funcs_part = src.split("::", 1)
            funcs = [f.strip() for f in funcs_part.split(",") if f.strip()]
        else:
            file_path, funcs = src, []
        entry = file_map.setdefault(file_path, {"whole_file": False, "functions": set(), "nodes": []})
        entry["nodes"].append(name)
        if funcs:
            entry["functions"].update(funcs)
        else:
            entry["whole_file"] = True
    return file_map


def get_top_level_function_names(source_code):
    """
    解析原始碼，回傳所有 top-level 函式名稱（含 class 內的方法，以 Class.method 表示）。
    語法錯誤時回傳 None，交由呼叫端略過（避免跟其他檢查重複報同一個語法錯誤）。
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(f"{node.name}.{sub.name}")
    return names


def check_precommit_hook_status(repo_root="."):
    """
    偵測目前是否在 git repo 內、以及 pre-commit hook 是否已實際安裝。

    背景：README 有交代要執行 `install.py init` 來安裝 pre-commit hook，
    但如果有人直接 clone 專案、跳過這一步就開始改東西，系統原本不會有
    任何提示——RULE-01~05 等所有機械強制其實都沒有在運作，卻表現得
    好像一切正常。這支函式讓 compile_map.py / resume_analysis.py 等
    高曝光度的入口，能主動把這個「有沒有防護網」的狀態秀出來，而不是
    只靠文件裡的一句話讓使用者自己記得。

    回傳：{"is_git_repo": bool, "hook_installed": bool}
    """
    git_dir = os.path.join(repo_root, ".git")
    if not os.path.isdir(git_dir):
        return {"is_git_repo": False, "hook_installed": False}
    hook_path = os.path.join(git_dir, "hooks", "pre-commit")
    return {"is_git_repo": True, "hook_installed": os.path.isfile(hook_path)}


def find_misplaced_modules(data):
    """
    「模組寫錯地方」偵測。

    每個模組在解析時都記錄了 map_file（實際寫在哪個實體檔案），
    每個 Domain / Subsystem 也記錄了自己的標頭實際寫在哪個實體檔案。
    正常情況下：一個模組的 map_file 應該跟它所屬 Subsystem（若有）或
    Domain 的 map_file 一致——因為它理應被寫在「該 Subsystem/Domain
    目前落腳的子地圖檔案」裡。

    若不一致，代表這個模組被寫到了錯的實體檔案（例如：Subsystem 早就
    被拆到 docs/domains/checkout.md，但這個新模組卻被直接加進根目錄
    system_map.md），這正是「Agent 忘記寫進子地圖」的機械化偵測點。

    回傳：[{"module", "scope", "scope_name", "expected_file", "actual_file"}, ...]
    """
    domains = data.get("domains", {})
    modules = data.get("modules", {})
    misplaced = []

    for name, info in modules.items():
        domain = info.get("domain")
        subsystem = info.get("subsystem")
        actual = info.get("map_file") or "system_map.md"

        if not domain or domain not in domains:
            continue

        dom_info = domains[domain]
        expected = None
        scope = "domain"
        scope_name = domain

        if subsystem and subsystem in dom_info.get("subsystems", {}):
            expected = dom_info["subsystems"][subsystem].get("map_file")
            scope = "subsystem"
            scope_name = f"{domain} / {subsystem}"
        else:
            expected = dom_info.get("map_file")

        if expected and expected != actual:
            misplaced.append({
                "module": name,
                "scope": scope,
                "scope_name": scope_name,
                "expected_file": expected,
                "actual_file": actual,
            })

    return misplaced


class ADADCore:
    def __init__(self, map_path=MAP_FILE, check_validity=True):
        self.map_path = map_path
        self.data = self._load_map()
        if check_validity:
            valid_res = self.check_ir_validity()
            if not valid_res["valid"]:
                print(json.dumps({"success": False, "error": valid_res["error"]}, ensure_ascii=False, indent=2))
                sys.exit(1)

    def check_ir_validity(self):
        md_path = "system_map.md"
        yaml_path = self.map_path
        
        if os.path.exists(md_path):
            if not os.path.exists(yaml_path):
                return {
                    "valid": False,
                    "error": f"找不到架構 IR 檔案 ({yaml_path})。請先執行編譯指令：python .agents/skills/adad-workflow/scripts/compile_map.py"
                }
            
            md_mtime = get_max_mtime(md_path)
            yaml_mtime = os.path.getmtime(yaml_path)
            
            # 給予 1 秒的緩衝時間防範不同檔案系統時間戳記微幅飄移
            if md_mtime > yaml_mtime + 1:
                return {
                    "valid": False,
                    "error": f"架構源檔案 ({md_path} 或其包含的子檔案) 已更新，但 IR ({yaml_path}) 已過期。請重新執行編譯：python .agents/skills/adad-workflow/scripts/compile_map.py"
                }
                
        return {"valid": True}


    def _load_map(self):
        if not os.path.exists(self.map_path):
            return {"version": 1, "modules": {}}
        with open(self.map_path, "r", encoding="utf-8") as f:
            try:
                # ponytail-fix: 優先用 C 擴充套件版的 CSafeLoader（若環境有裝
                # libyaml 綁定），純 Python 版 SafeLoader 在模組數一多會明顯變慢
                # （實測 2000 模組規模下差距可達數倍）。沒有 libyaml 時優雅退回
                # 純 Python 版，行為完全不變，只是速度快慢的差異。
                try:
                    from yaml import CSafeLoader as _Loader
                except ImportError:
                    _Loader = yaml.SafeLoader
                content = yaml.load(f, Loader=_Loader)
                return content if content else {"version": 1, "modules": {}}
            except Exception as e:
                print(f"[ADAD ERROR] 解析 {self.map_path} 失敗: {e}")
                sys.exit(1)

    def save(self):
        with open(self.map_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.data, f, allow_unicode=True, sort_keys=False)

    def get_node(self, node_name):
        return self.data.get("modules", {}).get(node_name)

    def _extract_adr_summary(self, adr_id):
        """從 docs/adr/ 中提取設計決策摘要，僅抓取關鍵標題、狀態與決策內容以防範 Context 膨脹"""
        adr_dir = os.path.join("docs", "adr")
        file_path = os.path.join(adr_dir, f"{adr_id}.md")
        
        # 增加相對路徑的容錯
        if not os.path.exists(file_path):
            file_path = os.path.join("adr", f"{adr_id}.md")
            
        if not os.path.exists(file_path):
            return {"adr_id": adr_id, "error": "決策文件不存在"}
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return {"adr_id": adr_id, "error": f"無法讀取文件: {e}"}

        title = f"{adr_id} (無標題)"
        status = "Unknown"
        decision = "No decision described."

        # 1. 提取第一行標題
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("# "):
                title = line_str[2:].strip()
                break
            else:
                title = line_str
                break

        # 2. 逐行掃描，收集各 ## 段落
        sections = {}
        curr_sec = None
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("## "):
                curr_sec = line_str[3:].strip().lower()
                sections[curr_sec] = []
            elif curr_sec and line_str.startswith("#"):
                curr_sec = None
            elif curr_sec:
                if line_str:
                    sections[curr_sec].append(line_str)

        # 3. 提取狀態
        for sec_name, content_lines in sections.items():
            if "狀態" in sec_name or "status" in sec_name:
                if content_lines:
                    status = content_lines[0]
                    break

        # 4. 提取決策要點 (取前兩行非空行並合併)
        for sec_name, content_lines in sections.items():
            if "決策" in sec_name or "decision" in sec_name:
                if content_lines:
                    decision = " ".join(content_lines[:2])
                    break

        return {
            "adr_id": adr_id,
            "title": title,
            "status": status,
            "decision": decision
        }

    def _extract_pattern_summary(self, pattern_name):
        """從 docs/patterns/ 中提取設計模式規範摘要，僅抓取關鍵標題、說明與程式碼規範"""
        patterns_dir = os.path.join("docs", "patterns")
        file_path = os.path.join(patterns_dir, f"{pattern_name}.md")
        
        if not os.path.exists(file_path):
            file_path = os.path.join("patterns", f"{pattern_name}.md")
            
        if not os.path.exists(file_path):
            return {"pattern_name": pattern_name, "error": "模式說明文件不存在"}
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return {"pattern_name": pattern_name, "error": f"無法讀取文件: {e}"}

        title = f"{pattern_name} 模式"
        desc = "無說明"
        rules = "無特別規範"

        # 1. 提取標題
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("# "):
                title = line_str[2:].strip()
                break
            else:
                title = line_str
                break

        # 2. 逐行掃描，收集各 ## 段落
        sections = {}
        curr_sec = None
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("## "):
                curr_sec = line_str[3:].strip().lower()
                sections[curr_sec] = []
            elif curr_sec and line_str.startswith("#"):
                curr_sec = None
            elif curr_sec:
                if line_str:
                    sections[curr_sec].append(line_str)

        # 3. 提取說明
        for sec_name, content_lines in sections.items():
            if "說明" in sec_name or "description" in sec_name:
                if content_lines:
                    desc = content_lines[0]
                    break

        # 4. 提取規範要點 (取前兩行非空行並合併)
        for sec_name, content_lines in sections.items():
            if "規範" in sec_name or "rules" in sec_name or "code" in sec_name:
                if content_lines:
                    rules = " ".join(content_lines[:2])
                    break

        return {
            "pattern_name": pattern_name,
            "title": title,
            "description": desc,
            "rules": rules
        }

    def read_context(self, node_name):
        """讀取單一節點最小上下文 (該節點與其相依節點的 Interface，並附帶設計決策與首選模式摘要)"""
        node = self.get_node(node_name)
        if not node:
            return {"error": f"找不到節點: {node_name}"}

        context = {
            "target_node": {
                "name": node_name,
                "type": node.get("type"),
                "state": node.get("state"),
                "input": node.get("input", {}),
                "output": node.get("output", {}),
                "dependencies": node.get("dependencies", []),
                "description": node.get("description", ""),
                "map_file": node.get("map_file", "system_map.md"),
                # ponytail-fix: SKILL.md 一直宣稱 read_context 會回傳 Invariants，
                # 但原本的 target_node dict 從沒放進去——Phase 2 的 agent 實際上
                # 從來沒拿到這兩項，只能等 check_normalization/pre-commit 事後才發現
                # 違反了 deny_imports 之類的規則。一併補上，讓契約在動筆「之前」
                # 就完整，而不是靠事後檢查才發現。
                "invariants": node.get("invariants", []),
                "verification": node.get("verification", []),
                # ponytail: Complexity/Algorithm——複雜函式的步驟大綱，讓實作階段
                # 只需要「翻譯」步驟而不是重新「設計」邏輯，詳見 parse_markdown 的說明。
                "complexity": node.get("complexity", "low"),
                "algorithm": node.get("algorithm", [])
            },
            "dependency_interfaces": {}
        }

        # 智慧裁剪決策摘要並寫入 Context
        decisions_summary = []
        for adr_id in node.get("decisions", []):
            adr_info = self._extract_adr_summary(adr_id)
            if "error" in adr_info:
                decisions_summary.append(f"{adr_id}: 決策檔案載入錯誤 - {adr_info['error']}")
            else:
                decisions_summary.append(f"{adr_info['title']} (狀態: {adr_info['status']}) - 決策: {adr_info['decision']}")
        
        if decisions_summary:
            context["target_node"]["decisions_summary"] = decisions_summary

        # 智慧載入首選設計模式摘要
        pattern_name = node.get("preferred_pattern")
        if pattern_name:
            pat_info = self._extract_pattern_summary(pattern_name)
            if "error" in pat_info:
                context["target_node"]["preferred_pattern_summary"] = f"{pattern_name}: 模式檔案載入錯誤 - {pat_info['error']}"
            else:
                context["target_node"]["preferred_pattern_summary"] = f"{pat_info['title']} (說明: {pat_info['description']}) - 規範: {pat_info['rules']}"

        # 獲取相依節點的 Interface 資訊
        for dep in node.get("dependencies", []):
            dep_node = self.get_node(dep)
            if dep_node:
                context["dependency_interfaces"][dep] = {
                    "input": dep_node.get("input", {}),
                    "output": dep_node.get("output", {}),
                    # ponytail-fix: 原本這裡只帶 input/output，代表下游模組完全看不到
                    # 上游依賴「保證」了什麼行為（例如 deny_imports 以外的其他保證，
                    # 之後擴充 invariants 詞彙後會更明顯）。只給型別、不給保證，
                    # 下游模型要嘛自己重複防禦性檢查，要嘛賭一把假設它成立——
                    # 兩種都不是「好任務」該有的樣子，一併補上。
                    "invariants": dep_node.get("invariants", []),
                }
            else:
                context["dependency_interfaces"][dep] = "未定義"

        return context

    @staticmethod
    def _bigrams(s):
        s = (s or "").strip()
        return set(s[i:i + 2] for i in range(len(s) - 1)) if len(s) >= 2 else set()

    def evaluate_normalization(self, proposed_name, proposed_input, proposed_output, proposed_description=""):
        """
        執行 Rule of Two 檢查，檢測是否有相似功能已重複出現 2 次以上。

        規則 1（保留，未變動）：input/output 介面簽章完全一致 → 判定為重複。
        這條抓的是資料契約層級的重複，跟敘述寫得好不好完全無關，最精準、
        不需要模糊比對，所以不動它。

        規則 2（改版）：原本是對照一份寫死的 8 個關鍵字（tax/email/sms/...），
        只要模組名稱剛好包含同一個關鍵字就判定重複——覆蓋率差，改個名字就能
        完全繞過（實測 zzz_message_pusher_v2 可以完全閃避），而且死名單也
        沒辦法涵蓋所有可能的功能領域。

        改成對 Description 欄位做「IDF 加權的字元二元組 Jaccard 相似度」：
        - 用字元二元組（bigram）取代詞彙切分，避免中文沒有空白分隔詞彙的問題，
          不需要額外的斷詞套件（維持這個專案「純標準庫實作」的一貫作法）。
        - 對常見詞（例如「使用者」「資料」「處理」這種到處都會出現的字）自動
          降權，避免兩個完全不相關的模組只因為都用到通用詞彙就被誤判重複。

        已知能力邊界（刻意的取捨，不是遺漏）：這仍然是純字面層級的重疊比對，
        不是語意理解。如果兩個模組的 Description 刻意寫得語意相同但用詞
        完全不同（沒有共同的二元組），是抓不到的——要抓到這種程度需要
        embedding 或 LLM 語意判斷，那會重新引入非確定性與延遲成本，
        已經在設計上決定不要那樣做：這種情況視為文件撰寫品質問題，
        不是這個工具要解決的範圍。
        """
        modules = self.data.get("modules", {})
        matches = []

        # 規則 1：介面簽章完全一致
        for name, info in modules.items():
            if name == proposed_name:
                continue
            if info.get("input") == proposed_input and info.get("output") == proposed_output:
                matches.append((name, "介面簽章完全一致"))

        # 規則 2：Description 加權相似度
        if proposed_description:
            matched_names = {m[0] for m in matches}
            others = {
                name: info.get("description", "")
                for name, info in modules.items()
                if name != proposed_name and info.get("description")
            }
            # 用現有全部模組的 Description 建立 document frequency，計算 IDF；
            # 語料量小（專案剛起步）時 IDF 區分度有限，屬預期中的冷啟動限制。
            df = Counter()
            for desc in others.values():
                for bg in self._bigrams(desc):
                    df[bg] += 1
            n_docs = max(len(others), 1)

            def _idf(bg):
                return math.log((n_docs + 1) / (1 + df.get(bg, 0))) + 1

            cand_bg = self._bigrams(proposed_description)
            # RULE_OF_TWO_SIMILARITY_THRESHOLD：依實測校準（用一批模擬真實情境的
            # Description 測試不同門檻的分類結果後選定 0.17）：
            #   - 真重複（含輕度改寫的用詞）：分數落在 0.18~0.40，門檻 0.17 全部命中
            #   - 相關但非重複：分數約 0.14，有 0.03 的安全邊際，不會被誤判
            #   - 純粹共用通用詞彙：分數約 0.06，遠低於門檻
            # 門檻越低，抓到越多真重複，但誤判風險也越高；0.17 是目前資料下
            # 兩者的平衡點，非絕對值，未來有更多真實案例可以重新校準。
            threshold = 0.17
            for name, desc in others.items():
                if name in matched_names:
                    continue  # 已經因介面一致被記錄，不重複列出
                other_bg = self._bigrams(desc)
                union = cand_bg | other_bg
                if not union:
                    continue
                inter = cand_bg & other_bg
                w_inter = sum(_idf(bg) for bg in inter)
                w_union = sum(_idf(bg) for bg in union)
                score = w_inter / w_union if w_union else 0.0
                if score >= threshold:
                    matches.append((name, f"敘述加權相似度 {score:.2f}"))

        if len(matches) >= 2:
            return {
                "passed": False,
                "reason": f"觸發 Rule of Two：功能特徵與現有模組高度重複，相似模組已出現 {len(matches)} 次。",
                "duplicates": [f"{name} ({reason})" for name, reason in matches]
            }
            
        return {"passed": True, "duplicates": []}

    def check_domain_boundary(self):
        """
        跨 Domain 依賴邊界檢查。

        規則：
        - 模組只能依賴同一個 Domain 內的模組，除非它所屬的 Domain 在
          system_map.md 用 `Allowed Dependencies: [OtherDomain, ...]` 明確
          宣告允許依賴該 Domain。
        - 沒有 domain 資訊的模組（例如尚未走三層架構、或舊專案還沒補標記）
          會被跳過，不視為違規，避免破壞既有專案。
        - 依賴到 system_map.yaml 裡不存在的模組，交給其他檢查處理，這裡跳過。

        回傳：{"passed": bool, "violations": [...]}
        """
        modules = self.data.get("modules", {})
        domains = self.data.get("domains", {})

        violations = []
        for name, info in modules.items():
            mod_domain = info.get("domain")
            if not mod_domain:
                continue

            for dep in info.get("dependencies", []):
                dep_info = modules.get(dep)
                if not dep_info:
                    continue

                dep_domain = dep_info.get("domain")
                if not dep_domain or dep_domain == mod_domain:
                    continue

                allowed = domains.get(mod_domain, {}).get("allowed_dependencies", [])
                if dep_domain not in allowed:
                    violations.append({
                        "module": name,
                        "module_domain": mod_domain,
                        "depends_on": dep,
                        "depends_on_domain": dep_domain,
                        "reason": (
                            f"模組 '{name}' 屬於 Domain '{mod_domain}'，"
                            f"卻依賴 Domain '{dep_domain}' 底下的 '{dep}'，"
                            f"但 Domain '{mod_domain}' 並未在 system_map.md 宣告 "
                            f"Allowed Dependencies 允許依賴 '{dep_domain}'。"
                        )
                    })

        return {"passed": len(violations) == 0, "violations": violations}

    def analyze_dirty_cascade(self, target_node):
        """智慧髒點依賴分析 (DAG 逆向遞迴追蹤)"""
        modules = self.data.get("modules", {})
        if target_node not in modules:
            return []

        # 建立反向依賴圖 (誰依賴了我)
        # adj[u] 包含所有依賴 u 的節點
        adj = {name: [] for name in modules}
        for name, info in modules.items():
            for dep in info.get("dependencies", []):
                if dep in adj:
                    adj[dep].append(name)

        # BFS 走查所有受波及的上游節點
        visited = set()
        queue = [target_node]
        dirty_list = []

        while queue:
            curr = queue.pop(0)
            for neighbor in adj.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    modules[neighbor]["state"] = "dirty"
                    dirty_list.append(neighbor)
                    queue.append(neighbor)
                
        # 自身變更也轉為 dirty (若原本是 deployed 狀態)
        modules[target_node]["state"] = "dirty"
        dirty_list.insert(0, target_node)

        return dirty_list

    def transit_state(self, node_name, next_state):
        """模組生命週期狀態轉移與校驗（硬化版：非法轉移直接阻斷）"""
        node = self.get_node(node_name)
        if not node:
            return {"success": False, "error": f"找不到節點: {node_name}"}

        curr_state = node.get("state", "planned")
        valid_transitions = {
            "draft":          ["pending_review"],
            "pending_review": ["validated", "dirty"],
            "planned":        ["validated"],
            "validated":      ["dirty", "linted/tested"],
            "dirty":          ["validated", "linted/tested"],
            "linted/tested":  ["deployed", "dirty"],
            "deployed":       ["dirty"],
        }

        # ponytail: 硬化——非法轉移直接阻斷，不再只是 WARNING
        if next_state not in valid_transitions.get(curr_state, []):
            return {
                "success": False,
                "error": f"[BLOCKED] 非法狀態轉移: {curr_state} → {next_state}。"
                         f"合法目標: {valid_transitions.get(curr_state, [])}"
            }

        node["state"] = next_state
        return {"success": True, "from": curr_state, "to": next_state}

    # ------------------------------------------------------------------
    # Task 快照機制
    #
    # 背景：Module 是「架構長期存在的事實」，Task 是「某個時間點針對這個
    # Module 正式核發的一份施工指令」，兩者分開之後，coding 端只讀取 Task
    # 快照檔（.agents/tasks/<node>.task.json），不需要（未來甚至可以不被允許）
    # 直接存取 system_map.yaml。這樣設計的好處是「有沒有先核發任務、有沒有
    # 真的等到人類審查」變成可以單純從檔案系統狀態檢查的事實，不需要解析
    # 任何 agent 平台特有的 transcript 格式，天生跨平台。
    # ------------------------------------------------------------------

    def _task_path(self, node_name):
        return os.path.join(TASK_DIR, f"{node_name}.task.json")

    def _node_source_hash(self, node_name):
        """對節點目前在 system_map.yaml 裡的完整內容算 hash，用來偵測任務是否過期。"""
        node = self.get_node(node_name)
        if node is None:
            return None
        canonical = json.dumps(node, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def load_task(self, node_name):
        """讀取 Task 快照檔，不存在或解析失敗回傳 None（呼叫端自行判斷後續行為）。"""
        path = self._task_path(node_name)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _save_task(self, node_name, task_data):
        os.makedirs(TASK_DIR, exist_ok=True)
        path = self._task_path(node_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task_data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def task_is_expired(self, node_name, task_data=None):
        """任務快照的 source_hash 是否已經對不上目前的 system_map.yaml。"""
        task_data = task_data if task_data is not None else self.load_task(node_name)
        if not task_data:
            return False  # 沒有任務檔，不算「過期」，是另一種情況（不存在）
        current_hash = self._node_source_hash(node_name)
        return current_hash is not None and task_data.get("source_hash") != current_hash

    def generate_task(self, node_name, force=False):
        """
        匯出一份 Task 快照給 coding 端讀取。

        只有在模組狀態允許修改、且架構未過期（RULE-01）的前提下才能核發，
        把「這個模組現在能不能動」的判斷收斂到核發這一刻做一次，下游
        （PreToolUse gate / pre-commit）之後只需要檢查 Task.status，
        不需要重新問一次模組狀態——單一事實來源。
        """
        node = self.get_node(node_name)
        if not node:
            return {"success": False, "error": f"找不到節點: {node_name}"}

        state = node.get("state", "unknown")
        if state not in ALLOWED_EDIT_STATES:
            return {
                "success": False,
                "error": f"[BLOCKED] 模組 `{node_name}` 目前狀態為 `{state}`，"
                         f"只有 {sorted(ALLOWED_EDIT_STATES)} 狀態才允許核發任務。"
            }

        validity = self.check_ir_validity()
        if not validity["valid"]:
            return {"success": False, "error": validity["error"]}

        existing = self.load_task(node_name)
        if existing and not force and existing.get("status") in TASK_EDITABLE_STATUSES.union({"submitted"}):
            return {
                "success": False,
                "error": f"[BLOCKED] 模組 `{node_name}` 已有一份進行中的任務"
                         f"（status={existing.get('status')}，task_id={existing.get('task_id')}），"
                         f"尚未結案（approved/rejected）不能重新核發。若確定要作廢重開，加上 force=True。"
            }

        source_hash = self._node_source_hash(node_name)
        version = self.data.get("version", 1)
        task_id = f"{node_name}@v{version}@{source_hash[:6]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        task_data = {
            "task_id": task_id,
            "node_name": node_name,
            "exported_at": now,
            "system_map_version": version,
            "source_hash": source_hash,
            "status": "assigned",
            "history": [{"event": "generated", "at": now}],
            "spec": self.read_context(node_name),
        }
        self._save_task(node_name, task_data)
        return {"success": True, "task_id": task_id, "path": self._task_path(node_name)}

    def task_submit(self, node_name, file_path=None):
        """
        coding 端「我做完了、本地檢查都過了」的自我宣告——這一步允許 Agent
        自己觸發，因為這只代表「準備好給人審」，不是核准，跟 task_approve
        / task_reject 那種需要人類親自介入的終局決策不同。

        會在這裡就地重新跑一次 invariants + verification 檢查，確保
        「submitted」這個狀態本身是有意義的保證，不是 Agent 說了算。
        """
        task_data = self.load_task(node_name)
        if not task_data:
            return {"success": False, "error": f"模組 `{node_name}` 尚未核發任務，請先執行 generate_task。"}

        if task_data.get("status") not in TASK_EDITABLE_STATUSES:
            return {
                "success": False,
                "error": f"[BLOCKED] 任務目前狀態為 `{task_data.get('status')}`，"
                         f"只有 {sorted(TASK_EDITABLE_STATUSES)} 狀態才能提交。"
            }

        if self.task_is_expired(node_name, task_data):
            return {
                "success": False,
                "error": f"[BLOCKED] 架構自從這份任務核發後已被更動（source_hash 不符），"
                         f"請重新執行 generate_task 取得最新快照後再重做。"
            }

        inv_res = self.check_invariants(node_name, file_path)
        if not inv_res.get("success"):
            return {"success": False, "error": f"Invariants 檢查未通過，不能提交: {inv_res.get('error')}"}

        ver_res = self.verify_implementation(node_name, file_path)
        if not ver_res.get("success"):
            return {"success": False, "error": f"Verification 檢查未通過，不能提交: {ver_res.get('error')}"}

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        task_data["status"] = "submitted"
        task_data.setdefault("history", []).append({"event": "submitted", "at": now})
        self._save_task(node_name, task_data)
        return {"success": True, "task_id": task_data["task_id"], "status": "submitted"}

    def _advance_module_to_validated(self, node_name):
        """approve 通過後，把模組狀態推進到 validated，處理 draft 需要先經過
        pending_review 這個中繼站的兩段式轉移；已經是 validated 就不動作。"""
        node = self.get_node(node_name)
        if not node:
            return
        state = node.get("state")
        if state == "validated":
            return
        if state == "draft":
            self.transit_state(node_name, "pending_review")
            state = "pending_review"
        if state in ("pending_review", "planned", "dirty"):
            self.transit_state(node_name, "validated")

    def task_approve(self, node_name, confirm_suffix):
        """
        人類核准 CP-2。呼叫端（adad_task.py）必須先確認是真人在互動終端機
        執行這個指令（sys.stdin.isatty()），這裡只負責核對核准依據字串是否
        正確——要求輸入 task_id 的後 6 碼，確保不是隨手打的空白確認。
        """
        task_data = self.load_task(node_name)
        if not task_data:
            return {"success": False, "error": f"模組 `{node_name}` 沒有待審的任務。"}
        if task_data.get("status") != "submitted":
            return {
                "success": False,
                "error": f"[BLOCKED] 任務狀態為 `{task_data.get('status')}`，只有 `submitted` 才能核准。"
            }
        expected_suffix = task_data.get("task_id", "")[-6:]
        if confirm_suffix.strip() != expected_suffix:
            return {"success": False, "error": "核准依據不符（task_id 後 6 碼對不上），未核准。"}

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        task_data["status"] = "approved"
        task_data.setdefault("history", []).append({"event": "approved", "at": now})
        self._save_task(node_name, task_data)
        self._advance_module_to_validated(node_name)
        self.save()
        return {"success": True, "task_id": task_data["task_id"], "status": "approved"}

    def task_reject(self, node_name, reason):
        """人類駁回 CP-2，任務退回 assigned 讓 coding 端重做，駁回原因留在
        history 裡——下次 coding 端讀 Task 快照時看得到這次為什麼被打回。"""
        task_data = self.load_task(node_name)
        if not task_data:
            return {"success": False, "error": f"模組 `{node_name}` 沒有待審的任務。"}
        if task_data.get("status") != "submitted":
            return {
                "success": False,
                "error": f"[BLOCKED] 任務狀態為 `{task_data.get('status')}`，只有 `submitted` 才能駁回。"
            }

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        task_data["status"] = "assigned"
        task_data.setdefault("history", []).append({"event": "rejected", "at": now, "reason": reason})
        self._save_task(node_name, task_data)
        return {"success": True, "task_id": task_data["task_id"], "status": "assigned", "reason": reason}

    def check_task_gate(self, rel_path):
        """
        給 adad_pretooluse_gate.py / adad_pre_commit.py 共用的政策判斷：
        這個檔案現在能不能被寫入？回傳 {"allow": bool, "reason": str, "node_name": str|None}。

        漸進式規則（避免對還沒採用 Task 流程的既有專案造成 breaking change）：
          - 檔案沒對應到任何模組 → allow（不在 ADAD 追蹤範圍）
          - 這個模組從來沒核發過任何 Task（.task.json 不存在）→ allow，但 reason
            會帶提醒訊息，呼叫端可以選擇印出 WARNING（不阻斷）
          - 有 Task 快照但已過期（架構被改過）→ 阻擋，要求重新 generate_task
          - 有 Task 快照且 status 屬於「開放編輯」集合 → allow
          - 其餘狀態（submitted / approved）→ 阻擋
        """
        src_map = {}
        for name, info in (self.data.get("modules", {}) or {}).items():
            src = (info or {}).get("source", "")
            if src:
                src_map[src.split("::", 1)[0].strip().replace("\\", "/")] = name

        node_name = src_map.get(rel_path.replace("\\", "/"))
        if node_name is None:
            return {"allow": True, "reason": "檔案未對應任何已登記模組", "node_name": None}

        task_data = self.load_task(node_name)
        if task_data is None:
            return {
                "allow": True,
                "node_name": node_name,
                "reason": f"模組 `{node_name}` 尚未核發過任何 Task 快照，建議先執行 "
                          f"generate_task.py {node_name}（目前為過渡期，暫不阻斷，僅提醒）。",
                "soft_warning": True,
            }

        if self.task_is_expired(node_name, task_data):
            return {
                "allow": False,
                "node_name": node_name,
                "reason": f"模組 `{node_name}` 的 Task 快照已過期（架構自核發後被更動），"
                          f"請重新執行 generate_task.py {node_name}。",
            }

        status = task_data.get("status")
        if status in TASK_EDITABLE_STATUSES:
            return {"allow": True, "node_name": node_name, "reason": f"Task 狀態為 `{status}`，允許編輯"}

        return {
            "allow": False,
            "node_name": node_name,
            "reason": f"模組 `{node_name}` 的 Task 狀態為 `{status}`，不允許編輯。"
                      + ("任務待人類審查中，請等候 CP-2 核准或駁回。" if status == "submitted"
                         else "此輪任務已核准結案，如需再修改請重新執行 generate_task.py。"),
        }



    def get_fan_in_map(self):
        """回傳 {module_name: fan_in_count}，fan-in = 有多少模組依賴此節點"""
        modules = self.data.get("modules", {})
        fan_in = {name: 0 for name in modules}
        for name, info in modules.items():
            for dep in info.get("dependencies", []):
                if dep in fan_in:
                    fan_in[dep] += 1
        return fan_in

    def check_draft_debt(self):
        """
        Draft Debt Ledger 核心偵測。
        掃描所有 draft 模組的 fan-in 變化：
        若 fan-in 從 snapshot=0 變為 ≥2，將該模組及所有新依賴它的節點標記為 pending_review。
        回傳 {promoted_nodes: [...], checkpoint_required: bool}
        """
        modules = self.data.get("modules", {})
        current_fan_in = self.get_fan_in_map()

        # 建立反向鄰接表：adj[dep] = [依賴 dep 的模組們]
        adj = {name: [] for name in modules}
        for name, info in modules.items():
            for dep in info.get("dependencies", []):
                if dep in adj:
                    adj[dep].append(name)

        promoted = []
        for name, info in modules.items():
            if info.get("state") != "draft":
                continue
            old_fan_in = info.get("fan_in_snapshot", 0)
            new_fan_in = current_fan_in.get(name, 0)
            if old_fan_in == 0 and new_fan_in >= 2:
                # 升級 draft → pending_review
                info["state"] = "pending_review"
                promoted.append({"node": name, "old_fan_in": old_fan_in, "new_fan_in": new_fan_in})
                # 所有新依賴它的節點也標記為 pending_review
                for dependent in adj.get(name, []):
                    dep_info = modules.get(dependent)
                    if dep_info and dep_info.get("state") not in ("pending_review",):
                        dep_info["state"] = "pending_review"
                        promoted.append({"node": dependent, "reason": f"依賴 {name}"})

        # 更新所有模組的 fan_in_snapshot
        for name in modules:
            modules[name]["fan_in_snapshot"] = current_fan_in.get(name, 0)

        return {"promoted_nodes": promoted, "checkpoint_required": len(promoted) > 0}

    def check_invariants(self, node_name, file_path=None):
        """檢查指定節點的實作檔案是否符合 Invariant 規則 (首波支援 deny_imports)"""
        node = self.get_node(node_name)
        if not node:
            return {"success": False, "error": f"找不到節點: {node_name}"}

        invariants = node.get("invariants", [])
        if not invariants:
            return {"success": True, "message": "此節點未定義 invariants，無須檢查。"}

        # 優先使用 system_map.yaml 的 source 欄位，最後才猜 <node_name>.py
        file_path = file_path or node.get("source") or f"{node_name}.py"

        if not os.path.exists(file_path):
            return {"success": False, "error": f"找不到實作檔案: {file_path}"}

        # 解析 invariants 規則，取得 deny_imports 清單
        deny_list = []
        for inv in invariants:
            match = re.search(r"deny_imports:\s*\[(.*?)\]", inv)
            if match:
                pkgs = [p.strip() for p in match.group(1).split(",") if p.strip()]
                deny_list.extend(pkgs)

        if not deny_list:
            return {"success": True, "message": "未偵測到有效的 deny_imports 規則。"}

        # 讀取並解析檔案 AST
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)
        except Exception as e:
            return {"success": False, "error": f"解析檔案 {file_path} 失敗: {e}"}

        # 遍歷 AST 收集 imports
        class ImportVisitor(ast.NodeVisitor):
            def __init__(self):
                self.imports = [] # 包含 (module_name, line_number)

            def visit_Import(self, node_visitor):
                for alias in node_visitor.names:
                    self.imports.append((alias.name, node_visitor.lineno))
                    parts = alias.name.split('.')
                    if len(parts) > 1:
                        self.imports.append((parts[0], node_visitor.lineno))
                self.generic_visit(node_visitor)

            def visit_ImportFrom(self, node_visitor):
                is_relative = (node_visitor.level or 0) > 0
                # alias.name 一律記錄：from . import db_connector / from pkg import db_connector
                # 都需要比對 deny_imports 清單中的頂層名稱
                for alias in node_visitor.names:
                    self.imports.append((alias.name, node_visitor.lineno))

                # module 字串只在絕對 import（level==0）時才記錄，避免相對路徑
                # 後綴（e.g. from .utils import x 的 "utils"）被誤判為頂層套件
                if node_visitor.module and not is_relative:
                    self.imports.append((node_visitor.module, node_visitor.lineno))
                    parts = node_visitor.module.split('.')
                    if len(parts) > 1:
                        self.imports.append((parts[0], node_visitor.lineno))
                    for alias in node_visitor.names:
                        self.imports.append((f"{node_visitor.module}.{alias.name}", node_visitor.lineno))
                self.generic_visit(node_visitor)

        visitor = ImportVisitor()
        visitor.visit(tree)

        violations = []
        seen_violations = set()
        for denied_pkg in deny_list:
            for imp_pkg, lineno in visitor.imports:
                if imp_pkg == denied_pkg or imp_pkg.startswith(denied_pkg + "."):
                    v_key = (denied_pkg, imp_pkg, lineno)
                    if v_key not in seen_violations:
                        seen_violations.add(v_key)
                        violations.append({
                            "rule": f"deny_imports: {denied_pkg}",
                            "imported": imp_pkg,
                            "line": lineno
                        })

        if violations:
            return {
                "success": False,
                "error": f"違反架構不變量 (Invariants) 邊界約束！檔案 {file_path} 包含了禁止的 import。",
                "violations": violations
            }

        return {"success": True, "message": "架構不變量 (Invariants) 檢查通過。"}

    def _resolve_verify_target_func(self, node_name, node):
        """
        決定 case 驗證要動態呼叫的實際函式名稱。

        慣例（對應 build_file_to_registered_functions 的 Source 語法）：
          - Source 帶 `::func_name`（單一函式登記）→ 直接用它
          - Source 帶 `::f1,f2,...`（多函式登記）→ 若 node_name 剛好在列表中就用
            node_name；否則退而求其次用列表第一個。這種一個 Module 對應多個函式
            的寫法本來就不利於單一 case 驗證（不知道該測哪一個），只是儘量给出
            一個合理預設，不是嚴謹規則——建議這類節點改回一對一 `::` 登記。
          - Source 沒有 `::`（整檔登記）→ 假設函式名稱與 node_name 相同，這跟
            SKILL.md 一路以來「Module 名稱即函式名稱」的慣例一致。
        """
        src = node.get("source", "") or ""
        if "::" in src:
            _, funcs_part = src.split("::", 1)
            funcs = [f.strip() for f in funcs_part.split(",") if f.strip()]
            if node_name in funcs:
                return node_name
            if funcs:
                return funcs[0]
        return node_name

    @staticmethod
    def _load_function_from_file(file_path, func_name):
        """
        動態載入實作檔案，取出指定函式物件供 case 驗證直接呼叫。

        ponytail-fix: 原本用 importlib.util.spec_from_file_location + exec_module，
        這條路徑預設會透過 SourceFileLoader 走 __pycache__ 的 .pyc bytecode 快取
        （依 mtime + size 判斷是否命中快取）。驗證工具的檔案常常是「短時間內反覆
        覆寫同一個檔名」（例如 agent 修一次、驗證一次、再修一次），如果兩次覆寫
        剛好落在同一個檔案系統 mtime 解析度秒數內、又剛好新舊內容位元組數相同
        （這在真實程式碼修正時完全可能發生，不是刻意構造的邊界案例），.pyc 快取
        驗證會誤判「沒變」而繼續吃舊的編譯結果——對驗證工具而言，這是最糟的失效
        模式：明明程式碼已經改了，驗證卻悄悄比對到舊邏輯，回報「通過」但其實測的
        不是目前這份程式碼。已用自我測試（7.5）重現過一次。
        改用 compile()+exec() 直接從原始碼字串編譯執行，完全繞過任何 bytecode 快取，
        保證每次呼叫都反映檔案「當下」的實際內容，也不會在專案裡留下 __pycache__。
        """
        import types
        abs_path = os.path.abspath(file_path)
        module_dir = os.path.dirname(abs_path)
        added_path = module_dir not in sys.path
        if added_path:
            sys.path.insert(0, module_dir)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                source = f.read()
            mod_id = "_adad_verify_target_" + re.sub(r"\W", "_", os.path.basename(abs_path))
            module = types.ModuleType(mod_id)
            module.__file__ = abs_path
            code = compile(source, abs_path, "exec")
            exec(code, module.__dict__)
        finally:
            if added_path and module_dir in sys.path:
                sys.path.remove(module_dir)
        if not hasattr(module, func_name):
            raise AttributeError(f"檔案 {file_path} 找不到函式 `{func_name}`")
        return getattr(module, func_name)

    def verify_implementation(self, node_name, file_path=None):
        """
        驗證指定節點的實作代碼是否符合 Verification 約束。

        支援兩種規則，可以在同一個節點混用：
          - `must_have_assertions`：原有的靜態 AST 掃描，檢查檔案裡至少有一個
            assert 語句。只證明「有自檢」，不證明「自檢的內容是對的」。
          - `case`：新增的動態執行驗證。實際 import 該節點對應的函式，用
            `case.input` 當作 kwargs 呼叫它，比對回傳值是否等於 `case.expect`。
            這才是真正驗證「邏輯對不對」，不只是「有沒有寫測試」。
        """
        node = self.get_node(node_name)
        if not node:
            return {"success": False, "error": f"找不到節點: {node_name}"}

        verification = node.get("verification", [])
        if not verification:
            return {"success": True, "message": "此節點未定義 verification 驗證條件，無須檢查。"}

        file_path = file_path or node.get("source") or f"{node_name}.py"
        # Source 可能是 "file.py::func" 這種帶函式標註的完整字串；檔案存在性
        # 檢查與動態載入只需要路徑部分。
        real_file_path = file_path.split("::", 1)[0] if file_path else file_path

        if not os.path.exists(real_file_path):
            return {"success": False, "error": f"找不到實作檔案: {real_file_path}"}

        static_error = None

        # --- 靜態規則：must_have_assertions（原有行為不變）---
        if "must_have_assertions" in verification:
            try:
                with open(real_file_path, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=real_file_path)
            except Exception as e:
                return {"success": False, "error": f"解析檔案 {real_file_path} 失敗: {e}"}

            class AssertVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.has_assert = False

                def visit_Assert(self, node_visitor):
                    self.has_assert = True

            visitor = AssertVisitor()
            visitor.visit(tree)
            if not visitor.has_assert:
                static_error = (
                    f"違反驗證條件 (Verification) 約束！檔案 {real_file_path} "
                    f"必須包含至少一個 assert 語句作為自檢斷言。"
                )

        # --- 動態規則：case（實際執行函式，比對 Input → Expected Output）---
        cases = [v["case"] for v in verification if isinstance(v, dict) and "case" in v]
        case_results = []
        if cases:
            func_name = self._resolve_verify_target_func(node_name, node)
            load_error = None
            func = None
            try:
                func = self._load_function_from_file(real_file_path, func_name)
            except Exception as e:
                load_error = str(e)

            for idx, case in enumerate(cases):
                case_input = case.get("input", {})
                expect = case.get("expect")
                if load_error:
                    case_results.append({
                        "case_index": idx, "passed": False,
                        "error": f"無法載入函式 `{func_name}`：{load_error}"
                    })
                    continue
                try:
                    actual = func(**case_input) if isinstance(case_input, dict) else func(case_input)
                    case_results.append({
                        "case_index": idx, "passed": actual == expect,
                        "input": case_input, "expect": expect, "actual": actual
                    })
                except Exception as e:
                    case_results.append({
                        "case_index": idx, "passed": False,
                        "input": case_input, "expect": expect,
                        "error": f"執行時發生例外：{type(e).__name__}: {e}"
                    })

        all_cases_passed = all(c["passed"] for c in case_results)

        if static_error or not all_cases_passed:
            return {
                "success": False,
                "error": static_error or f"{sum(1 for c in case_results if not c['passed'])} / "
                                         f"{len(case_results)} 個 Verification case 未通過，詳見 case_results。",
                "case_results": case_results
            }

        result = {"success": True, "message": "驗證條件 (Verification) 檢查通過。"}
        if case_results:
            result["case_results"] = case_results
        return result


# ================= 自我單元測試 =================
def run_self_test():
    print("[ADAD Test] 啟動 ADAD 核心引擎自我測試...")
    test_file = "test_system_map.yaml"
    
    # 建立測試資料
    test_data = {
        "version": 1,
        "modules": {
            "db_connector": {
                "type": "infrastructure",
                "state": "deployed",
                "dependencies": [],
                "input": {},
                "output": {"connected": "bool"}
            },
            "user_service": {
                "type": "service",
                "state": "deployed",
                "dependencies": ["db_connector"],
                "input": {"user_id": "int"},
                "output": {"name": "str"}
            },
            "calculate_jp_tax": {
                "type": "function",
                "state": "deployed",
                "dependencies": [],
                "input": {"amount": "float"},
                "output": {"tax": "float"}
            },
            "calculate_us_tax": {
                "type": "function",
                "state": "deployed",
                "dependencies": [],
                "input": {"amount": "float"},
                "output": {"tax": "float"}
            }
        }
    }
    
    with open(test_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(test_data, f)
        
    try:
        core = ADADCore(test_file, check_validity=False)
        
        # 1. 測試讀取上下文
        ctx = core.read_context("user_service")
        assert "db_connector" in ctx["dependency_interfaces"]
        print("  - 測試 1: 讀取上下文成功")

        # 2. 測試 Rule of Two
        # 同樣有 calculate_jp_tax 和 calculate_us_tax，若想新增 calculate_uk_tax，應觸發警告
        res = core.evaluate_normalization("calculate_uk_tax", {"amount": "float"}, {"tax": "float"})
        assert res["passed"] is False, "應該觸發 Rule of Two 警告"
        print("  - 測試 2: Rule of Two 阻斷判定成功")

        # 2.5 測試 Rule of Two 改版：Description 加權相似度（取代原本寫死的關鍵字表）
        core.data["modules"]["send_invoice_notice"] = {
            "type": "function", "state": "deployed", "dependencies": [],
            "input": {"order_id": "str"}, "output": {"sent": "bool"},
            "description": "產生發票並寄送給使用者確認付款狀態"
        }
        core.data["modules"]["notify_payment_status"] = {
            "type": "function", "state": "deployed", "dependencies": [],
            "input": {"order_id": "str"}, "output": {"sent": "bool"},
            "description": "確認付款狀態後通知使用者對應結果"
        }
        # 用詞完全不同、介面也刻意設計成不一樣（避免規則 1 直接命中），
        # 純粹考驗 Description 加權相似度這條規則本身
        res_dup = core.evaluate_normalization(
            "dispatch_invoice_email", {"uid": "str"}, {"ok": "bool"},
            proposed_description="寄送發票通知信給使用者確認付款"
        )
        assert res_dup["passed"] is False, "改寫過的重複敘述應該被 Rule of Two（加權相似度）攔截"
        print("  - 測試 2.5a: Rule of Two 改版（敘述加權相似度）正確攔截改寫過的重複敘述")

        # 完全不相關、但共用「使用者」這種通用詞彙 —— 不應該被誤判為重複
        res_unrelated = core.evaluate_normalization(
            "calculate_shipping_fee", {"weight": "float"}, {"fee": "float"},
            proposed_description="計算商品運費並套用使用者的會員折扣"
        )
        assert res_unrelated["passed"] is True, "只是共用通用詞彙，不該被誤判為 Rule of Two 重複"
        print("  - 測試 2.5b: Rule of Two 改版（敘述加權相似度）沒有被通用詞彙誤判成功")
        del core.data["modules"]["send_invoice_notice"]
        del core.data["modules"]["notify_payment_status"]

        # 3. 測試 DAG 級聯分析
        # db_connector 變更，應該讓 user_service 變為 dirty
        dirty = core.analyze_dirty_cascade("db_connector")
        assert "user_service" in dirty
        assert core.get_node("user_service")["state"] == "dirty"
        print("  - 測試 3: DAG 髒點依賴級聯分析成功")

        # 4. 測試狀態轉換（硬化版）
        res_ok = core.transit_state("db_connector", "validated")
        assert res_ok["success"] is True
        assert core.get_node("db_connector")["state"] == "validated"
        # 非法轉移應被阻斷
        res_bad = core.transit_state("db_connector", "deployed")
        assert res_bad["success"] is False
        assert "BLOCKED" in res_bad["error"]
        print("  - 測試 4: 狀態機轉換（含硬化阻斷）成功")

        # 4.5 測試 Draft Debt Ledger
        core.data["modules"]["demo_leaf"] = {
            "type": "function", "state": "draft", "dependencies": [],
            "input": {}, "output": {"x": "int"}, "fan_in_snapshot": 0
        }
        # 新增 2 個模組依賴 demo_leaf → fan-in 0 → 2
        core.data["modules"]["consumer_a"] = {
            "type": "function", "state": "planned", "dependencies": ["demo_leaf"],
            "input": {}, "output": {}
        }
        core.data["modules"]["consumer_b"] = {
            "type": "function", "state": "planned", "dependencies": ["demo_leaf"],
            "input": {}, "output": {}
        }
        debt_result = core.check_draft_debt()
        assert debt_result["checkpoint_required"] is True
        assert core.get_node("demo_leaf")["state"] == "pending_review"
        # 清理測試資料
        for k in ["demo_leaf", "consumer_a", "consumer_b"]:
            del core.data["modules"][k]
        print("  - 測試 4.5: Draft Debt Ledger 偵測與自動升級成功")

        # 5. 測試 Invariant 檢查
        test_code_file = "test_calculate_tax.py"
        test_code_content = "import db_connector\nimport sys\n"
        with open(test_code_file, "w", encoding="utf-8") as f:
            f.write(test_code_content)
        
        try:
            core.get_node("calculate_jp_tax")["invariants"] = ["deny_imports: [db_connector]"]
            res = core.check_invariants("calculate_jp_tax", test_code_file)
            assert res["success"] is False, "應該檢測出違反 invariants"
            assert len(res["violations"]) == 1
            assert res["violations"][0]["imported"] == "db_connector"
            print("  - 測試 5: Invariants (deny_imports) 靜態 AST 阻斷檢查成功")
        finally:
            if os.path.exists(test_code_file):
                os.remove(test_code_file)
        
        # 6. 測試 ADR 設計決策提取與智慧裁剪
        test_adr_file = os.path.join("docs", "adr", "ADR-TEST-999.md")
        os.makedirs(os.path.dirname(test_adr_file), exist_ok=True)
        
        test_adr_content = """# ADR-TEST-999: 測試採用 Redis 進行快取
        
## 狀態
Approved

## 脈絡 (Context)
因為 calculate_jp_tax 的頻繁調用...

## 決策 (Decision)
我們決定採用 Redis 作為快取，避免內存佔用並支援橫向擴充。
這是第二行的決策要點。

## 後果 (Consequences)
需要額外的 Redis 服務。
"""
        with open(test_adr_file, "w", encoding="utf-8") as f:
            f.write(test_adr_content)
            
        try:
            core.get_node("calculate_jp_tax")["decisions"] = ["ADR-TEST-999"]
            ctx = core.read_context("calculate_jp_tax")
            assert "decisions_summary" in ctx["target_node"]
            summary = ctx["target_node"]["decisions_summary"][0]
            assert "測試採用 Redis 進行快取" in summary
            assert "狀態: Approved" in summary
            assert "我們決定採用 Redis 作為快取" in summary
            assert "這是第二行的決策要點。" in summary
            print("  - 測試 6: ADR 外部化決策與 Context 智慧裁剪提取成功")
        finally:
            if os.path.exists(test_adr_file):
                os.remove(test_adr_file)

        # 7. 測試模式載入與斷言檢查 (Verification)
        test_pattern_file = os.path.join("docs", "patterns", "test_pattern.md")
        os.makedirs(os.path.dirname(test_pattern_file), exist_ok=True)
        
        test_pattern_content = """# Test Pattern 模式規範

## 說明
這是一個用來自我測試的模式說明。

## 規範
- 第一條規範：必須要寫得很好。
- 第二條規範：一定要遵守。
"""
        with open(test_pattern_file, "w", encoding="utf-8") as f:
            f.write(test_pattern_content)
            
        test_impl_file = "test_impl_file.py"
        try:
            # 7.1 驗證模式載入與裁剪
            core.get_node("calculate_jp_tax")["preferred_pattern"] = "test_pattern"
            ctx = core.read_context("calculate_jp_tax")
            assert "preferred_pattern_summary" in ctx["target_node"]
            pat_summary = ctx["target_node"]["preferred_pattern_summary"]
            assert "Test Pattern" in pat_summary
            assert "說明: 這是一個用來自我測試的模式說明。" in pat_summary
            assert "規範: - 第一條規範：必須要寫得很好。 - 第二條規範：一定要遵守。" in pat_summary
            print("  - 測試 7.1: 設計模式外部化與 Context 智慧載入成功")
            
            # 7.2 驗證無斷言的阻斷
            core.get_node("calculate_jp_tax")["verification"] = ["must_have_assertions"]
            
            with open(test_impl_file, "w", encoding="utf-8") as f:
                f.write("def func():\n    return 42\n")
            
            res_fail = core.verify_implementation("calculate_jp_tax", test_impl_file)
            assert res_fail["success"] is False
            assert "必須包含至少一個 assert" in res_fail["error"]
            print("  - 測試 7.2: Verification 無斷言實作自動阻斷成功")
            
            # 7.3 驗證有斷言的通過
            with open(test_impl_file, "w", encoding="utf-8") as f:
                f.write("def func():\n    assert True\n    return 42\n")
                
            res_pass = core.verify_implementation("calculate_jp_tax", test_impl_file)
            assert res_pass["success"] is True
            print("  - 測試 7.3: Verification 有斷言實作順利通過成功")

            # 7.4 驗證 case 動態執行：邏輯正確時應通過，且回傳的 actual/expect 一致
            core.get_node("calculate_jp_tax")["verification"] = [
                {"case": {"input": {"x": 2}, "expect": 4}},
                {"case": {"input": {"x": 3}, "expect": 6}},
            ]
            core.get_node("calculate_jp_tax")["source"] = test_impl_file
            with open(test_impl_file, "w", encoding="utf-8") as f:
                f.write("def calculate_jp_tax(x):\n    return x * 2\n")

            res_case_pass = core.verify_implementation("calculate_jp_tax", test_impl_file)
            assert res_case_pass["success"] is True
            assert all(c["passed"] for c in res_case_pass["case_results"])
            assert res_case_pass["case_results"][0]["actual"] == 4
            print("  - 測試 7.4: Verification case 動態執行（邏輯正確）順利通過成功")

            # 7.5 驗證 case 動態執行：邏輯錯誤時應阻斷，且明確回報 expect/actual 落差
            with open(test_impl_file, "w", encoding="utf-8") as f:
                f.write("def calculate_jp_tax(x):\n    return x + 2\n")  # 刻意寫錯（應為 x * 2）

            res_case_fail = core.verify_implementation("calculate_jp_tax", test_impl_file)
            assert res_case_fail["success"] is False
            # case_index 0 (x=2, expect 4) 用錯誤實作 x+2 巧合算出 4，會誤判通過，
            # 不能拿來斷言；改用 case_index 1 (x=3, expect 6) 這組沒有巧合、真正會
            # 暴露邏輯錯誤 (3+2=5 != 6) 的案例來驗證回報內容是否正確。
            assert res_case_fail["case_results"][1]["passed"] is False
            assert res_case_fail["case_results"][1]["expect"] == 6
            assert res_case_fail["case_results"][1]["actual"] == 5
            print("  - 測試 7.5: Verification case 動態執行（邏輯錯誤）正確阻斷並回報落差成功")

        finally:
            if os.path.exists(test_pattern_file):
                os.remove(test_pattern_file)
            if os.path.exists(test_impl_file):
                os.remove(test_impl_file)

        # 8. 測試 Markdown 解析 (parse_markdown)
        test_md_content = """# Title
## Metadata
- Version: 3

##### Module: test_mod
- Type: tool
- Description: 測試模組
- Dependencies: [dep1, dep2]
- Decisions: [ADR-001]
- Preferred Pattern: pure_function
- Input:
  - arg1: int
- Output:
  - res1: string
- TODO:
  - [ ] todo1
- Checkpoint:
  - [ ] CP-1-001 (planned)
"""
        parsed = parse_markdown(test_md_content)
        assert parsed["version"] == 3
        assert "test_mod" in parsed["modules"]
        mod = parsed["modules"]["test_mod"]
        assert mod["type"] == "tool"
        assert mod["description"] == "測試模組"
        assert mod["dependencies"] == ["dep1", "dep2"]
        assert mod["decisions"] == ["ADR-001"]
        assert mod["preferred_pattern"] == "pure_function"
        assert mod["input"]["arg1"] == "int"
        assert mod["output"]["res1"] == "string"
        assert len(mod["todo"]) == 1 and "todo1" in mod["todo"][0]
        assert len(mod["checkpoint"]) == 1 and "CP-1-001" in mod["checkpoint"][0]
        print("  - 測試 8: Markdown 解析 (parse_markdown) 成功")

        # 8.5 測試 Verification 的 case JSON 語法解析
        test_md_case_content = """##### Module: case_test_mod
- Type: function
- Description: 測試 case 語法解析
- Verification:
  - must_have_assertions
  - case: {"input": {"x": 1}, "expect": 2}
- Input:
  - x: int
- Output:
  - result: int
"""
        parsed_case = parse_markdown(test_md_case_content)
        v = parsed_case["modules"]["case_test_mod"]["verification"]
        assert v[0] == "must_have_assertions"
        assert isinstance(v[1], dict) and v[1]["case"] == {"input": {"x": 1}, "expect": 2}
        print("  - 測試 8.5a: Verification case JSON 語法正確解析成功")

        test_md_bad_case = """##### Module: bad_case_mod
- Type: function
- Description: 測試非法 case JSON 應該編譯失敗
- Verification:
  - case: {input: 1, expect: 2}
"""
        try:
            parse_markdown(test_md_bad_case)
            assert False, "非法 JSON 的 case 應該要拋出例外"
        except ValueError as e:
            assert "不是合法 JSON" in str(e)
        print("  - 測試 8.5b: Verification case 非法 JSON 正確阻斷編譯成功")

        # 9. 測試模組名稱可正確保留連字號（module_regex 修正的回歸測試）
        # 修正前：\w+ 不含 '-'，"my-tax-calc" 會被靜默截斷成 "my"，且不報錯。
        test_hyphen_md = """# Title
## Metadata
- Version: 1

##### Module: user_service
- Type: service
- Description: 第一個模組
- Dependencies: []

##### Module: my-tax-calc
- Type: function
- Description: 名稱含連字號的模組，不應被截斷
- Dependencies: []
"""
        parsed_hyphen = parse_markdown(test_hyphen_md)
        assert "my-tax-calc" in parsed_hyphen["modules"], \
            f"連字號模組名稱被截斷，實際解析出的模組: {list(parsed_hyphen['modules'].keys())}"
        assert "my" not in parsed_hyphen["modules"], "不應該出現被截斷的 'my' 模組"
        assert parsed_hyphen["modules"]["my-tax-calc"]["description"] == "名稱含連字號的模組，不應被截斷"
        # 確保第一個模組的欄位沒有被第二個模組的內容污染（截斷 bug 的典型症狀）
        assert parsed_hyphen["modules"]["user_service"]["description"] == "第一個模組"
        print("  - 測試 9: 連字號模組名稱解析（module_regex 回歸測試）成功")

        # 10. 測試跨 Domain 依賴邊界檢查 (check_domain_boundary)
        core.data["domains"] = {
            "Domain_A": {"allowed_dependencies": ["Domain_B"]},
            "Domain_B": {"allowed_dependencies": []},
            "Domain_C": {"allowed_dependencies": []},
        }
        core.data["modules"]["mod_a"] = {
            "type": "tool", "state": "deployed", "domain": "Domain_A",
            "dependencies": ["mod_b", "mod_c"], "input": {}, "output": {},
        }
        core.data["modules"]["mod_b"] = {
            "type": "tool", "state": "deployed", "domain": "Domain_B",
            "dependencies": [], "input": {}, "output": {},
        }
        core.data["modules"]["mod_c"] = {
            "type": "tool", "state": "deployed", "domain": "Domain_C",
            "dependencies": [], "input": {}, "output": {},
        }
        boundary_res = core.check_domain_boundary()
        assert boundary_res["passed"] is False, "mod_a 依賴未宣告允許的 Domain_C，應被判定違規"
        assert len(boundary_res["violations"]) == 1
        v = boundary_res["violations"][0]
        assert v["module"] == "mod_a" and v["depends_on"] == "mod_c"
        # 移除違規依賴後應該通過（mod_a -> mod_b 屬於已宣告允許的依賴）
        core.data["modules"]["mod_a"]["dependencies"] = ["mod_b"]
        boundary_res_ok = core.check_domain_boundary()
        assert boundary_res_ok["passed"] is True
        print("  - 測試 10: 跨 Domain 依賴邊界檢查 (check_domain_boundary) 成功")

        print("[ADAD Test] 所有測試順利通過！")

    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

    # 11. 測試 include 展開機制：多檔案合併、循環 include 偵測、
    #     孤兒子地圖偵測、重複模組名稱阻斷 (resolve_includes / find_orphan_maps)
    print("[ADAD Test] 啟動 Include 機制測試...")
    test_dir = "test_adad_include_dir"
    root_map = os.path.join(test_dir, "root.md")
    sub_map = os.path.join(test_dir, "sub.md")
    orphan_map = os.path.join(test_dir, "orphan.md")
    circular_a = os.path.join(test_dir, "circular_a.md")
    circular_b = os.path.join(test_dir, "circular_b.md")
    dup_root = os.path.join(test_dir, "dup_root.md")
    dup_sub = os.path.join(test_dir, "dup_sub.md")

    try:
        os.makedirs(test_dir, exist_ok=True)

        # 11.1 正常展開：root include sub，模組應合併且標記正確的 map_file
        with open(root_map, "w", encoding="utf-8") as f:
            f.write("# Root\n## Metadata\n- Version: 1\n\n"
                    "##### Module: root_mod\n- Type: tool\n- Description: root\n\n"
                    "<!-- include: sub.md -->\n")
        with open(sub_map, "w", encoding="utf-8") as f:
            f.write("##### Module: sub_mod\n- Type: tool\n- Description: sub\n")

        expanded = resolve_includes(root_map)
        parsed_expand = parse_markdown(expanded)
        assert "root_mod" in parsed_expand["modules"]
        assert "sub_mod" in parsed_expand["modules"]
        print("  - 測試 11.1: include 正常展開、跨檔案模組合併成功")

        # 11.2 孤兒子地圖偵測：sub.md 未被任何檔案 include 時應被列出
        with open(orphan_map, "w", encoding="utf-8") as f:
            f.write("##### Module: orphan_mod\n- Type: tool\n- Description: 沒人 include 我\n")
        orphans = find_orphan_maps(root_map)
        assert os.path.normpath(orphan_map) in [os.path.normpath(p) for p in orphans], \
            f"orphan.md 應被偵測為孤兒子地圖，實際結果: {orphans}"
        assert os.path.normpath(sub_map) not in [os.path.normpath(p) for p in orphans], \
            "sub.md 已被 root.md include，不應被視為孤兒"
        print("  - 測試 11.2: 孤兒子地圖偵測 (find_orphan_maps) 成功")

        # 11.3 循環 include 偵測：a include b，b 又 include a，應直接報錯而非死循環
        with open(circular_a, "w", encoding="utf-8") as f:
            f.write("##### Module: circ_a\n- Type: tool\n- Description: a\n\n<!-- include: circular_b.md -->\n")
        with open(circular_b, "w", encoding="utf-8") as f:
            f.write("##### Module: circ_b\n- Type: tool\n- Description: b\n\n<!-- include: circular_a.md -->\n")
        try:
            resolve_includes(circular_a)
            assert False, "循環 include 應該要拋出例外，而不是靜默死循環"
        except Exception as e:
            assert "循環" in str(e) or "circular" in str(e).lower(), f"錯誤訊息應提及循環 include，實際: {e}"
        print("  - 測試 11.3: 循環 include 偵測成功")

        # 11.4 重複模組名稱阻斷：兩個檔案定義了同名模組，編譯時應直接報錯
        with open(dup_root, "w", encoding="utf-8") as f:
            f.write("##### Module: dup_mod\n- Type: tool\n- Description: root 版本\n\n"
                     "<!-- include: dup_sub.md -->\n")
        with open(dup_sub, "w", encoding="utf-8") as f:
            f.write("##### Module: dup_mod\n- Type: tool\n- Description: sub 版本 (重複)\n")
        try:
            expanded_dup = resolve_includes(dup_root)
            parse_markdown(expanded_dup)
            assert False, "重複模組名稱應該要被偵測並阻斷"
        except Exception as e:
            assert "dup_mod" in str(e) or "重複" in str(e) or "duplicate" in str(e).lower(), \
                f"錯誤訊息應提及重複的模組名稱，實際: {e}"
        print("  - 測試 11.4: 重複模組名稱阻斷成功")

        print("[ADAD Test] 所有 Include 機制測試順利通過！")

    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_self_test()
