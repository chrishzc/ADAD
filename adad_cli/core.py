# -*- coding: utf-8 -*-
"""
ADAD Installer & Packager 核心邏輯

ponytail-fix (CLI 化重構):
原本 install.py 的所有函式都假設「目前工作目錄就是這個 repo 的原始碼目錄」，
因此：
  1. `python install.py init` 只能在 clone 下來的 repo 內執行才有效——
     一旦你 `pip install` 這個工具後跑到別的專案目錄執行，
     `.agents/skills/adad-workflow/...` 這些相對路徑通通會找不到檔案。
  2. 就算裝了全域指令，`init` 也只建立了 checkpoints / docs / venv 等雜項，
     從未把 adad-workflow 的 scripts 複製進「目標專案」，
     導致 pre-commit hook 與 compile_map.py 呼叫的來源檔案根本不存在。

這裡的修正方式：所有需要用到的範本 / skill 原始檔一律改由
`adad_cli.resources` 從「套件安裝路徑」讀取，不再依賴呼叫時的 cwd；
`init_project()` 也補上了「把 adad-workflow 複製一份到目標專案」這一步，
讓每個用 `adad init` 初始化的專案都是自我完備 (self-contained) 的。

multi-agent 支援 (2026 新增):
ADAD 原本只認 Antigravity（Gemini）這一種 agent。現在 `adad init` /
`adad global install` 可以互動選擇要對哪些 agent（antigravity / claude）
設定，選擇結果會存進 .agents/.adad-agents.json，之後 `adad upgrade`
直接讀這個檔案就知道要同步哪些 agent 的檔案，不必每次都重問一次。

這個模組刻意不 import click——互動詢問（真正跳出選單問使用者）由
cli.py 負責，core.py 只負責「給定 agents 清單之後該做什麼事」這個
純邏輯部分，兩者職責分開，也方便未來寫測試。
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from adad_cli import __version__
from adad_cli.resources import agents_dir, templates_dir

# --------------------------------------------------------------------------
# 支援的 Agent 清單（唯一事實來源，cli.py 的互動選單也是從這裡讀）
# --------------------------------------------------------------------------
AGENT_CHOICES = {
    "antigravity": "Antigravity 2.0 / IDE (Gemini)",
    "claude": "Claude Code",
}

GEMINI_HOME = os.path.join(os.path.expanduser("~"), ".gemini")
CLAUDE_HOME = os.path.join(os.path.expanduser("~"), ".claude")

# 全域 Skills 候選安裝目錄（依證據強度排序，全部會寫入，互不排斥）。
GLOBAL_SKILLS_CANDIDATES_BY_AGENT = {
    "antigravity": [
        os.path.join(GEMINI_HOME, "config", "skills"),
    ],
    "claude": [
        os.path.join(CLAUDE_HOME, "skills"),
    ],
}

# 各 agent 「點擊 + Global 新增全域規則」實際寫入的檔案。
GLOBAL_RULES_FILE_BY_AGENT = {
    "antigravity": os.path.join(GEMINI_HOME, "GEMINI.md"),
    "claude": os.path.join(CLAUDE_HOME, "CLAUDE.md"),
}

# 各 agent 對應的「本機是否已安裝該工具」判斷路徑。
AGENT_HOME_DIR = {
    "antigravity": GEMINI_HOME,
    "claude": CLAUDE_HOME,
}

AGENT_RULES_BLOCK_START = "\n# === ADAD GLOBAL RULES START ===\n"
AGENT_RULES_BLOCK_END = "\n# === ADAD GLOBAL RULES END ===\n"

# 專案層級記錄「這個專案要同步哪些 agent」的設定檔，讓 `adad upgrade`
# 不用每次都重新詢問使用者。
PROJECT_AGENT_CONFIG = os.path.join(".agents", ".adad-agents.json")

# Claude Code 讀 CLAUDE.md、不吃 AGENTS.md，官方文件建議的作法是在
# CLAUDE.md 開頭用 @path 語法匯入既有規則檔，避免維護兩份重複內容。
CLAUDE_MD_IMPORT_LINE = "@.agents/AGENTS.md"


def _normalize_agents(agents) -> list:
    """驗證/正規化 agents 清單，不合法的名稱會直接丟例外，讓呼叫端提早發現打字錯誤。"""
    if not agents:
        raise ValueError("agents 不可為空清單，至少要選一個 agent。")
    invalid = [a for a in agents if a not in AGENT_CHOICES]
    if invalid:
        raise ValueError(f"不認得的 agent: {', '.join(invalid)}（可選: {', '.join(AGENT_CHOICES)}）")
    # 用 dict 去重同時保留順序，比 set() 更穩定（不會因為 hash 順序跳來跳去）
    return list(dict.fromkeys(agents))


def load_project_agents():
    """讀取這個專案先前 `adad init` 時記錄的 agent 選擇。找不到設定檔就回傳 None。"""
    if not os.path.exists(PROJECT_AGENT_CONFIG):
        return None
    try:
        with open(PROJECT_AGENT_CONFIG, "r", encoding="utf-8") as f:
            data = json.load(f)
        agents = [a for a in data.get("agents", []) if a in AGENT_CHOICES]
        return agents or None
    except Exception:
        return None


def save_project_agents(agents) -> None:
    """把這個專案要同步的 agent 清單寫進 .agents/.adad-agents.json。"""
    agents = _normalize_agents(agents)
    os.makedirs(os.path.dirname(PROJECT_AGENT_CONFIG) or ".", exist_ok=True)
    with open(PROJECT_AGENT_CONFIG, "w", encoding="utf-8") as f:
        json.dump({"agents": agents}, f, ensure_ascii=False, indent=2)


def _copy_file_if_absent(src: Path, dst: str) -> None:
    if os.path.exists(dst):
        print(f"  - {dst} 已存在，跳過")
        return
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"  - 建立 {dst} 成功")


def _setup_claude_project_skill(local_skill_dir: str) -> None:
    """把 adad-workflow 也複製一份到 .claude/skills/，讓 Claude Code 的
    Project Skills 機制能自動發現（Claude Code 讀 .claude/skills/<name>/SKILL.md，
    格式跟 .agents/skills/ 下的完全相同，不需要另外轉檔）。"""
    claude_skill_dir = os.path.join(".claude", "skills", "adad-workflow")
    if not os.path.exists(claude_skill_dir):
        os.makedirs(os.path.dirname(claude_skill_dir), exist_ok=True)
        shutil.copytree(local_skill_dir, claude_skill_dir)
        print("  - [Claude Code] 複製 adad-workflow skill 至 .claude/skills/ 成功")
    else:
        print("  - [Claude Code] .claude/skills/adad-workflow 已存在，跳過")


def _ensure_claude_md_import(claude_md_path: str = "CLAUDE.md") -> None:
    """確保專案根目錄的 CLAUDE.md 有匯入 .agents/AGENTS.md，不會動到使用者
    自己在 CLAUDE.md 裡寫的其他內容（新增一行匯入，而不是整份覆蓋）。"""
    if not os.path.exists(claude_md_path):
        with open(claude_md_path, "w", encoding="utf-8") as f:
            f.write(CLAUDE_MD_IMPORT_LINE + "\n")
        print(f"  - [Claude Code] 建立 {claude_md_path} 成功（已匯入 .agents/AGENTS.md）")
        return

    with open(claude_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    if CLAUDE_MD_IMPORT_LINE in content:
        print(f"  - [Claude Code] {claude_md_path} 已包含 AGENTS.md 匯入，跳過")
        return

    with open(claude_md_path, "w", encoding="utf-8") as f:
        f.write(CLAUDE_MD_IMPORT_LINE + "\n\n" + content)
    print(f"  - [Claude Code] 已在既有 {claude_md_path} 開頭補上 AGENTS.md 匯入（原內容保留在後面）")


def init_project(agents=None) -> None:
    """在當前目錄初始化 ADAD 模式（自我完備：連同 adad-workflow skill 一起複製進來）。

    agents: 要設定的 agent 清單（例如 ["antigravity", "claude"]）。
            傳 None 時預設全部 agent 都設定（供非互動/程式呼叫使用；
            互動選單本身在 cli.py 裡問，問完才把結果傳進來）。
    """
    if agents is None:
        agents = list(AGENT_CHOICES.keys())
    agents = _normalize_agents(agents)

    print(f"[ADAD] 正在初始化當前專案（目標 agent: {', '.join(AGENT_CHOICES[a] for a in agents)}）...")
    tpl = templates_dir()

    # 0. 複製 adad-workflow skill 到本專案（.agents/ 是 ADAD 的核心工作目錄，
    #    不管選了哪個 agent 都一定要有這份，因為 pre-commit hook 與
    #    compile_map.py 都是從這裡讀取原始檔）
    local_skill_dir = os.path.join(".agents", "skills", "adad-workflow")
    if not os.path.exists(local_skill_dir):
        os.makedirs(os.path.dirname(local_skill_dir), exist_ok=True)
        shutil.copytree(agents_dir() / "skills" / "adad-workflow", local_skill_dir)
        print("  - 複製 adad-workflow skill 至 .agents/skills/ 成功")
    else:
        print("  - .agents/skills/adad-workflow 已存在，跳過")

    local_agents_md = os.path.join(".agents", "AGENTS.md")
    _copy_file_if_absent(agents_dir() / "AGENTS.md", local_agents_md)

    # 0.5 針對個別 agent 的額外設定
    if "claude" in agents:
        _setup_claude_project_skill(local_skill_dir)
        _ensure_claude_md_import("CLAUDE.md")
    if "antigravity" in agents:
        print("  - [Antigravity] 會自動讀取 .agents/AGENTS.md 與 .agents/skills/，不需要額外設定")

    # 1. 建立 checkpoints 目錄
    if not os.path.exists("checkpoints"):
        os.makedirs("checkpoints")
        print("  - 建立 checkpoints/ 目錄成功")
    else:
        print("  - checkpoints/ 目錄已存在，跳過")

    # 1.2 建立 docs/adr 目錄與範本
    adr_dir = os.path.join("docs", "adr")
    os.makedirs(adr_dir, exist_ok=True)
    _copy_file_if_absent(tpl / "ADR-000_template.md", os.path.join(adr_dir, "ADR-000_template.md"))

    # 1.3 建立 docs/patterns 目錄與範本
    patterns_dir = os.path.join("docs", "patterns")
    os.makedirs(patterns_dir, exist_ok=True)
    _copy_file_if_absent(tpl / "pure_function.md", os.path.join(patterns_dir, "pure_function.md"))

    # 2. 建立 system_map.md 初始範本
    if not os.path.exists("system_map.md"):
        shutil.copyfile(tpl / "system_map.md", "system_map.md")
        print("  - 建立 system_map.md 初始範本成功")

        # 自動執行編譯以產生 system_map.yaml (IR)，使用剛複製進本專案的 compile_map.py
        compile_script = os.path.join(local_skill_dir, "scripts", "compile_map.py")
        try:
            print("  - 正在自動編譯架構源檔案...")
            subprocess.run([sys.executable, compile_script], check=True)
            print("  - 自動編譯成功，已產生 system_map.yaml")
        except Exception as e:
            print(f"  - [警告] 自動編譯架構源檔案失敗: {e}")
    else:
        print("  - system_map.md 已存在，跳過")

    # 3. 建立 Docker 相關範本與 .gitignore
    _copy_file_if_absent(tpl / "gitignore", ".gitignore")
    _copy_file_if_absent(tpl / "Dockerfile", "Dockerfile")
    _copy_file_if_absent(tpl / "docker-compose.yml", "docker-compose.yml")
    _copy_file_if_absent(tpl / "dockerignore", ".dockerignore")
    _copy_file_if_absent(tpl / "requirements.txt", "requirements.txt")

    # 4. Git 初始化
    if not os.path.exists(".git"):
        try:
            subprocess.run(["git", "init"], check=True)
            print("  - Git 初始化成功")
        except Exception as e:
            print(f"  - [警告] Git 初始化失敗 (可能系統未安裝 Git): {e}")
    else:
        print("  - .git 已存在，跳過")

    # 5. 建立 venv 虛擬環境
    if not os.path.exists("venv"):
        print("  - 正在建立 Python 虛擬環境 (venv)...")
        try:
            subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
            print("  - Python 虛擬環境 (venv) 建立成功")
        except Exception as e:
            print(f"  - [警告] 建立 Python 虛擬環境失敗: {e}")
    else:
        print("  - venv 虛擬環境已存在，跳過")

    # 6. 安裝 pre-commit hook（來源現在保證存在，因為第 0 步已把 skill 複製進本專案）
    #    這一步跟選了哪個 agent 完全無關：git hook 是由 git 本身觸發，
    #    不管是哪個 coding agent 寫的程式碼，commit 時都一樣會被擋下來檢查。
    hook_src = os.path.join(local_skill_dir, "scripts", "adad_pre_commit.py")
    hook_dst = os.path.join(".git", "hooks", "pre-commit")
    if os.path.exists(".git") and os.path.exists(hook_src):
        os.makedirs(os.path.dirname(hook_dst), exist_ok=True)
        try:
            # ponytail-fix: 寫死呼叫 "python" 在多數現代 Linux / macOS 上
            # 沒有這個指令（只有 python3），會導致 git commit 時 hook
            # 回傳 127 (command not found)，擋下所有 commit 且無明確錯誤訊息。
            # 改用 adad init 當下實際執行的直譯器絕對路徑，不依賴 commit
            # 當下 shell 的 PATH。
            hook_content = f"""#!/bin/sh
"{sys.executable}" "{hook_src}"
"""
            with open(hook_dst, "w", encoding="utf-8") as f:
                f.write(hook_content)
            try:
                os.chmod(hook_dst, 0o755)
            except Exception:
                pass
            print("  - 建立 pre-commit hook 成功")
        except Exception as e:
            print(f"  - [警告] 建立 pre-commit hook 失敗: {e}")

    # 7. 記錄這個專案選了哪些 agent，之後 `adad upgrade` 才不用每次都重問
    save_project_agents(agents)
    print(f"  - 已記錄本專案的 agent 選擇至 {PROJECT_AGENT_CONFIG}")

    print("[ADAD] 專案初始化完成！")


def _iter_relative_files(base: Path):
    """遞迴列出 base 底下所有檔案的相對路徑。"""
    for root, _dirs, files in os.walk(base):
        for name in files:
            full = Path(root) / name
            yield full.relative_to(base)


def _sync_file(src: Path, dst: str, report: dict) -> None:
    """把單一檔案從套件內建版本同步到專案裡。

    - 專案裡還沒有這個檔案 -> 直接新增。
    - 內容跟套件內建版本一模一樣 -> 跳過，不動它。
    - 內容不同（代表套件版本已更新，或使用者手動改過）
      -> 先備份成 .bak 再覆蓋，絕不無聲蓋掉。
    """
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copyfile(src, dst)
        report["added"].append(dst)
        return

    with open(src, "rb") as fa:
        src_bytes = fa.read()
    with open(dst, "rb") as fb:
        dst_bytes = fb.read()

    if src_bytes != dst_bytes:
        shutil.copyfile(dst, dst + ".bak")
        shutil.copyfile(src, dst)
        report["updated"].append(dst)
    else:
        report["unchanged"].append(dst)


def upgrade_project(agents=None, force_agents_md: bool = False) -> None:
    """安全地把「目前已安裝的 ADAD 套件版本」同步到一個已經 `adad init`
    過的既有專案，不會動到使用者自己的資產。

    agents: 要同步的 agent 清單。傳 None 時會先嘗試讀取
            .agents/.adad-agents.json（`adad init` 當初存的選擇）；
            如果連設定檔都沒有（例如專案是這個功能加入前建立的），
            才 fallback 成同步全部已知 agent，確保舊專案不會出錯。

    ponytail-fix: 在這個指令出現以前，`init_project()` 對已存在的檔案一律
    「跳過」，代表套件本身修好的 bug（例如 pre-commit hook 寫死呼叫
    "python" 的問題）永遠不會反映到舊專案裡，使用者只能被迫先
    `adad remove` 再 `adad init`，結果連 venv、checkpoints 都被砍掉重建。
    這裡改成只同步「vendored、完全由套件管理、使用者不會手動編輯」的
    檔案（adad-workflow 的 scripts、pre-commit hook），使用者資產
    （system_map.md、checkpoints/、docs/adr、docs/patterns 等）完全不觸碰；
    AGENTS.md 屬於灰色地帶，預設也不覆蓋，只提示差異。
    """
    if agents is None:
        agents = load_project_agents() or list(AGENT_CHOICES.keys())
    agents = _normalize_agents(agents)

    local_skill_dir = os.path.join(".agents", "skills", "adad-workflow")
    if not os.path.exists(local_skill_dir):
        print("[ADAD ERROR] 找不到 .agents/skills/adad-workflow，這個專案似乎還沒執行過 `adad init`。")
        print("             請先執行 `adad init`，之後才有東西可以升級。")
        sys.exit(1)

    print(f"[ADAD] 正在將目前套件版本（{__version__}）同步到本專案（僅限套件管理的檔案，目標 agent: "
          f"{', '.join(AGENT_CHOICES[a] for a in agents)}）...")

    report = {"added": [], "updated": [], "unchanged": []}

    # 1. 同步整個 adad-workflow skill 目錄（scripts/、SKILL.md 等）。
    #    這整個目錄都是套件管理範圍，使用者不會手動編輯，可安全覆蓋。
    #    不管選了哪個 agent，.agents/ 底下這份都是核心來源，一律同步。
    src_skill_dir = agents_dir() / "skills" / "adad-workflow"
    for rel_path in _iter_relative_files(src_skill_dir):
        src_file = src_skill_dir / rel_path
        dst_file = os.path.join(local_skill_dir, str(rel_path))
        _sync_file(src_file, dst_file, report)

    # 1.5 若專案有選 Claude Code，.claude/skills/adad-workflow 也要跟著同步，
    #     否則套件更新後兩邊的 skill 內容會兜不起來。
    if "claude" in agents:
        claude_skill_dir = os.path.join(".claude", "skills", "adad-workflow")
        for rel_path in _iter_relative_files(src_skill_dir):
            src_file = src_skill_dir / rel_path
            dst_file = os.path.join(claude_skill_dir, str(rel_path))
            _sync_file(src_file, dst_file, report)
        _ensure_claude_md_import("CLAUDE.md")

    # 2. 重新產生 pre-commit hook：即使腳本內容沒變，也順便修正
    #    sys.executable 路徑可能因為換了 Python 版本、搬動 venv 而失效的問題。
    hook_src = os.path.join(local_skill_dir, "scripts", "adad_pre_commit.py")
    hook_dst = os.path.join(".git", "hooks", "pre-commit")
    if os.path.exists(".git") and os.path.exists(hook_src):
        try:
            hook_content = f"""#!/bin/sh
"{sys.executable}" "{hook_src}"
"""
            old_content = None
            if os.path.exists(hook_dst):
                with open(hook_dst, "r", encoding="utf-8") as f:
                    old_content = f.read()
            if old_content != hook_content:
                if old_content is not None:
                    shutil.copyfile(hook_dst, hook_dst + ".bak")
                os.makedirs(os.path.dirname(hook_dst), exist_ok=True)
                with open(hook_dst, "w", encoding="utf-8") as f:
                    f.write(hook_content)
                try:
                    os.chmod(hook_dst, 0o755)
                except Exception:
                    pass
                report["updated"].append(hook_dst)
            else:
                report["unchanged"].append(hook_dst)
        except Exception as e:
            print(f"  - [警告] 重新產生 pre-commit hook 失敗: {e}")

    # 3. AGENTS.md 屬於灰色地帶：使用者可能已經客製化過規則內容，
    #    預設不覆蓋，只提示差異，避免無聲蓋掉使用者的客製規則。
    local_agents_md = os.path.join(".agents", "AGENTS.md")
    src_agents_md = agents_dir() / "AGENTS.md"
    if os.path.exists(local_agents_md) and os.path.exists(src_agents_md):
        with open(src_agents_md, "rb") as fa, open(local_agents_md, "rb") as fb:
            differs = fa.read() != fb.read()
        if differs:
            if force_agents_md:
                shutil.copyfile(local_agents_md, local_agents_md + ".bak")
                shutil.copyfile(src_agents_md, local_agents_md)
                report["updated"].append(local_agents_md)
            else:
                print(f"  - [提示] {local_agents_md} 與套件內建版本不同（可能是你自己客製化過規則），")
                print("           預設不覆蓋。若確定要用套件最新版本覆蓋，重新執行：")
                print("           adad upgrade --force-agents-md")

    # 4. 寫入版本戳記，方便之後追蹤這個專案目前對應套件的哪個版本。
    version_file = os.path.join(local_skill_dir, ".adad_version")
    try:
        with open(version_file, "w", encoding="utf-8") as f:
            f.write(__version__)
    except Exception:
        pass

    # 5. 確保這次用到的 agent 選擇也被寫回設定檔（涵蓋「舊專案沒有設定檔、
    #    這次 fallback 用了全部 agent」的情況，讓下次 upgrade 不用再重新推算）。
    save_project_agents(agents)

    # 6. 輸出報告，讓使用者清楚知道實際發生了什麼事，而不是靜默覆蓋。
    print()
    if report["added"]:
        print(f"[新增] {len(report['added'])} 個檔案：")
        for f in report["added"]:
            print(f"  + {f}")
    if report["updated"]:
        print(f"[更新] {len(report['updated'])} 個檔案（舊版本已備份為對應的 .bak）：")
        for f in report["updated"]:
            print(f"  * {f}")
    if not report["added"] and not report["updated"]:
        print("[ADAD] 已經是最新版本，沒有需要更新的檔案。")

    print(f"\n[ADAD] 升級完成，目前套件版本：{__version__}")
    print("       使用者資產（system_map.md、checkpoints/、docs/adr、docs/patterns 等）完全未被觸碰。")


def clean_project(purge_docs: bool = False) -> None:
    """復原/清理當前專案中的 ADAD 相關產出與環境。

    ponytail-fix: 原本無差別刪除 system_map.md / system_map.yaml /
    checkpoints/，但這些是使用者手寫的架構藍圖與決策歷程，跟 venv、
    pre-commit hook 這種「隨時可用 adad init 重新生成」的東西不是同一類，
    一旦刪除無法復原。改成預設只清理「環境/工具產出」，使用者資產
    （system_map.md/.yaml、checkpoints/、docs/adr、docs/patterns）預設保留，
    除非明確傳入 purge_docs=True（CLI 對應 `adad remove --purge-docs`）。
    """
    print("[ADAD] 正在還原專案環境並清理 ADAD 檔案...")

    hook_dst = os.path.join(".git", "hooks", "pre-commit")
    if os.path.exists(hook_dst):
        try:
            os.remove(hook_dst)
            print("  - 移除 pre-commit hook 成功")
        except Exception as e:
            print(f"  - 移除 pre-commit hook 失敗: {e}")

    if os.path.exists("venv"):
        try:
            shutil.rmtree("venv")
            print("  - 移除 venv 虛擬環境成功")
        except Exception as e:
            print(f"  - 移除 venv 虛擬環境失敗: {e}")

    local_skill_dir = os.path.join(".agents", "skills", "adad-workflow")
    if os.path.exists(local_skill_dir):
        try:
            shutil.rmtree(local_skill_dir)
            print("  - 移除本專案內的 adad-workflow skill 副本成功")
        except Exception as e:
            print(f"  - 移除 adad-workflow skill 副本失敗: {e}")

    # 同步清掉 Claude Code 那份 skill 副本，避免留下孤兒檔案。
    # CLAUDE.md 保留不動，因為使用者可能在裡面加了自己的其他規則，
    # 只提示一句，不擅自修改/刪除。
    claude_skill_dir = os.path.join(".claude", "skills", "adad-workflow")
    if os.path.exists(claude_skill_dir):
        try:
            shutil.rmtree(claude_skill_dir)
            print("  - 移除本專案內的 Claude Code adad-workflow skill 副本成功")
        except Exception as e:
            print(f"  - 移除 Claude Code adad-workflow skill 副本失敗: {e}")
    if os.path.exists("CLAUDE.md"):
        print("  - [提示] CLAUDE.md 可能包含你自己的其他規則，未自動刪除，如需清除請手動處理")

    if os.path.exists(PROJECT_AGENT_CONFIG):
        try:
            os.remove(PROJECT_AGENT_CONFIG)
            print(f"  - 移除 {PROJECT_AGENT_CONFIG} 成功")
        except Exception as e:
            print(f"  - 移除 {PROJECT_AGENT_CONFIG} 失敗: {e}")

    if purge_docs:
        print("  - [--purge-docs] 已指定，將一併移除使用者架構文件與決策紀錄...")
        for f in ("system_map.yaml", "system_map.md"):
            if os.path.exists(f):
                try:
                    os.remove(f)
                    print(f"  - 移除 {f} 成功")
                except Exception as e:
                    print(f"  - 移除 {f} 失敗: {e}")

        if os.path.exists("checkpoints"):
            try:
                shutil.rmtree("checkpoints")
                print("  - 移除 checkpoints/ 目錄成功")
            except Exception as e:
                print(f"  - 移除 checkpoints/ 失敗: {e}")
    else:
        kept = [f for f in ("system_map.md", "system_map.yaml", "checkpoints") if os.path.exists(f)]
        if kept:
            print(f"  - 保留使用者資產（未刪除）：{', '.join(kept)}")
            print("    若確定要連同架構文件與決策紀錄一起清除，請改執行 `adad remove --purge-docs`")

    print("[ADAD] 專案清理還原完成！")


def _write_global_rules_block(dest_file: str, agents_rules_content: str) -> None:
    """安全地將 ADAD 規則區塊寫入/更新至指定的全域規則檔案（不影響檔案中其他既有內容）"""
    global_rules_content = ""
    if os.path.exists(dest_file):
        with open(dest_file, "r", encoding="utf-8") as f:
            global_rules_content = f.read()

    if AGENT_RULES_BLOCK_START in global_rules_content:
        start_idx = global_rules_content.find(AGENT_RULES_BLOCK_START)
        end_idx = global_rules_content.find(AGENT_RULES_BLOCK_END) + len(AGENT_RULES_BLOCK_END)
        global_rules_content = global_rules_content[:start_idx] + global_rules_content[end_idx:]

    new_rules_block = f"{AGENT_RULES_BLOCK_START}{agents_rules_content}{AGENT_RULES_BLOCK_END}"
    global_rules_content = global_rules_content.rstrip() + "\n" + new_rules_block

    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(global_rules_content)


def install_global(agents=None) -> None:
    """將 ADAD 客製化安裝至全域設定，供所有專案共用。

    agents: 要安裝的 agent 清單。傳 None 時預設全部 agent
            （供非互動/程式呼叫使用；互動選單在 cli.py 問完才傳進來）。

    ponytail-fix: 來源固定改用套件內建的 resources/agents，
    因此這個指令現在「在任何目錄下都能執行」，不再要求你必須待在 repo 根目錄。
    """
    if agents is None:
        agents = list(AGENT_CHOICES.keys())
    agents = _normalize_agents(agents)

    src_skills_dir = agents_dir() / "skills" / "adad-workflow"
    src_agents_md = agents_dir() / "AGENTS.md"
    agents_rules_content = None
    if os.path.exists(src_agents_md):
        with open(src_agents_md, "r", encoding="utf-8") as f:
            agents_rules_content = f.read()

    any_agent_installed = False

    for agent in agents:
        label = AGENT_CHOICES[agent]
        home_dir = AGENT_HOME_DIR[agent]
        if not os.path.exists(home_dir):
            print(f"[ADAD ERROR] 找不到 {home_dir}，請確認 {label} 已安裝且至少執行過一次，跳過此 agent。")
            continue

        print(f"[ADAD] 正在安裝全域 Skills 至 {label}...")
        installed_any = False
        for base_dir in GLOBAL_SKILLS_CANDIDATES_BY_AGENT[agent]:
            dest_skills_dir = os.path.join(base_dir, "adad-workflow")
            try:
                os.makedirs(base_dir, exist_ok=True)
                if os.path.exists(dest_skills_dir):
                    shutil.rmtree(dest_skills_dir)
                shutil.copytree(src_skills_dir, dest_skills_dir)
                print(f"  完成 {dest_skills_dir}")
                installed_any = True
            except Exception as e:
                print(f"  跳過 {dest_skills_dir}（{e}）")

        if not installed_any:
            print(f"[ADAD ERROR] {label} 所有候選全域 Skills 目錄皆安裝失敗。")
            continue

        any_agent_installed = True

        if agents_rules_content is not None:
            rules_file = GLOBAL_RULES_FILE_BY_AGENT[agent]
            try:
                _write_global_rules_block(rules_file, agents_rules_content)
                print(f"  全域規則已安全寫入 {rules_file}")
            except Exception as e:
                print(f"  寫入全域規則檔案失敗: {e}")

    if not any_agent_installed:
        print("[ADAD ERROR] 所有選定的 agent 皆安裝失敗。")
        sys.exit(1)

    print("\n[ADAD] 全域安裝完成！")
    print("提醒：Antigravity 建議安裝後在 IDE 的「Global Skills / Rules」設定畫面確認載入；")
    print("      Claude Code 請開一個新的 session，問它「你現在有哪些 skills 可以用」")
    print("      來確認 adad-workflow 是否已被載入（Skills 只在 session 啟動時讀取一次）。")


def uninstall_global(agents=None) -> None:
    """自全域設定移除 ADAD 客製化與規則。

    agents: 傳 None 時預設清除全部已知 agent（移除本來就沒安裝的東西
            是安全的空操作，所以卸載不強制要求先知道當初裝了哪些）。
    """
    if agents is None:
        agents = list(AGENT_CHOICES.keys())
    agents = _normalize_agents(agents)

    print("[ADAD] 正在自全域移除...")

    for agent in agents:
        for base_dir in GLOBAL_SKILLS_CANDIDATES_BY_AGENT.get(agent, []):
            dest_skills_dir = os.path.join(base_dir, "adad-workflow")
            if os.path.exists(dest_skills_dir):
                try:
                    shutil.rmtree(dest_skills_dir)
                    print(f"  移除 {dest_skills_dir} 成功")
                except Exception as e:
                    print(f"  移除 {dest_skills_dir} 失敗: {e}")

        rules_file = GLOBAL_RULES_FILE_BY_AGENT.get(agent)
        if rules_file and os.path.exists(rules_file):
            try:
                with open(rules_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if AGENT_RULES_BLOCK_START in content:
                    start_idx = content.find(AGENT_RULES_BLOCK_START)
                    end_idx = content.find(AGENT_RULES_BLOCK_END) + len(AGENT_RULES_BLOCK_END)
                    content = content[:start_idx] + content[end_idx:]
                    with open(rules_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"  清除 {rules_file} 中的 ADAD 規則區塊成功")
            except Exception as e:
                print(f"  清除全域規則失敗: {e}")

    print("[ADAD] 全域卸載完成！")


def pack_dist() -> None:
    """打包目前專案內的 .agents（以及 .claude，若存在）為 zip 安裝包
    （開發者發布用，維持原行為，仍以 cwd 為準）"""
    print("[ADAD] 正在打包客製化套件...")
    zip_name = "adad-customizations.zip"

    if not os.path.exists(".agents"):
        print("[ADAD ERROR] 找不到 .agents 資料夾，無法打包。")
        sys.exit(1)

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _dirs, files in os.walk(".agents"):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, file_path)
        if os.path.exists(".claude"):
            for root, _dirs, files in os.walk(".claude"):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, file_path)

    print(f"[ADAD] 打包完成！已生成安裝包: {zip_name}")
