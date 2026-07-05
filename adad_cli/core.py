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
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from adad_cli import __version__
from adad_cli.resources import agents_dir, templates_dir

GEMINI_HOME = os.path.join(os.path.expanduser("~"), ".gemini")

# 全域 Skills 候選安裝目錄（依證據強度排序，全部會寫入，互不排斥）。
GLOBAL_SKILLS_CANDIDATES = [
    os.path.join(GEMINI_HOME, "skills"),
    os.path.join(GEMINI_HOME, "config", "skills"),
    os.path.join(GEMINI_HOME, "antigravity", "skills"),
]

# Antigravity IDE 點擊「+ Global」新增全域規則時，實際寫入的檔案。
GLOBAL_RULES_FILE = os.path.join(GEMINI_HOME, "GEMINI.md")

AGENT_RULES_BLOCK_START = "\n# === ADAD GLOBAL RULES START ===\n"
AGENT_RULES_BLOCK_END = "\n# === ADAD GLOBAL RULES END ===\n"


def _copy_file_if_absent(src: Path, dst: str) -> None:
    if os.path.exists(dst):
        print(f"  - {dst} 已存在，跳過")
        return
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"  - 建立 {dst} 成功")


def init_project() -> None:
    """在當前目錄初始化 ADAD 模式（自我完備：連同 adad-workflow skill 一起複製進來）"""
    print("[ADAD] 正在初始化當前專案...")
    tpl = templates_dir()

    # 0. 複製 adad-workflow skill 到本專案（修正原本從未複製、造成 hook/編譯腳本
    #    找不到來源檔的問題）
    local_skill_dir = os.path.join(".agents", "skills", "adad-workflow")
    if not os.path.exists(local_skill_dir):
        os.makedirs(os.path.dirname(local_skill_dir), exist_ok=True)
        shutil.copytree(agents_dir() / "skills" / "adad-workflow", local_skill_dir)
        print("  - 複製 adad-workflow skill 至 .agents/skills/ 成功")
    else:
        print("  - .agents/skills/adad-workflow 已存在，跳過")

    local_agents_md = os.path.join(".agents", "AGENTS.md")
    _copy_file_if_absent(agents_dir() / "AGENTS.md", local_agents_md)

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


def upgrade_project(force_agents_md: bool = False) -> None:
    """安全地把「目前已安裝的 ADAD 套件版本」同步到一個已經 `adad init`
    過的既有專案，不會動到使用者自己的資產。

    ponytail-fix: 在這個指令出現以前，`init_project()` 對已存在的檔案一律
    「跳過」，代表套件本身修好的 bug（例如 pre-commit hook 寫死呼叫
    "python" 的問題）永遠不會反映到舊專案裡，使用者只能被迫先
    `adad remove` 再 `adad init`，結果連 venv、checkpoints 都被砍掉重建。
    這裡改成只同步「vendored、完全由套件管理、使用者不會手動編輯」的
    檔案（adad-workflow 的 scripts、pre-commit hook），使用者資產
    （system_map.md、checkpoints/、docs/adr、docs/patterns 等）完全不觸碰；
    AGENTS.md 屬於灰色地帶，預設也不覆蓋，只提示差異。
    """
    local_skill_dir = os.path.join(".agents", "skills", "adad-workflow")
    if not os.path.exists(local_skill_dir):
        print("[ADAD ERROR] 找不到 .agents/skills/adad-workflow，這個專案似乎還沒執行過 `adad init`。")
        print("             請先執行 `adad init`，之後才有東西可以升級。")
        sys.exit(1)

    print(f"[ADAD] 正在將目前套件版本（{__version__}）同步到本專案（僅限套件管理的檔案）...")

    report = {"added": [], "updated": [], "unchanged": []}

    # 1. 同步整個 adad-workflow skill 目錄（scripts/、SKILL.md 等）。
    #    這整個目錄都是套件管理範圍，使用者不會手動編輯，可安全覆蓋。
    src_skill_dir = agents_dir() / "skills" / "adad-workflow"
    for rel_path in _iter_relative_files(src_skill_dir):
        src_file = src_skill_dir / rel_path
        dst_file = os.path.join(local_skill_dir, str(rel_path))
        _sync_file(src_file, dst_file, report)

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

    # 5. 輸出報告，讓使用者清楚知道實際發生了什麼事，而不是靜默覆蓋。
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


def install_global() -> None:
    """將 ADAD 客製化安裝至全域 Antigravity（2.0 / IDE）設定。

    ponytail-fix: 來源固定改用套件內建的 resources/agents，
    因此這個指令現在「在任何目錄下都能執行」，不再要求你必須待在 repo 根目錄。
    """
    if not os.path.exists(GEMINI_HOME):
        print(f"[ADAD ERROR] 找不到 {GEMINI_HOME}，請確認 Antigravity 2.0 / IDE 已安裝且至少執行過一次。")
        sys.exit(1)

    src_skills_dir = agents_dir() / "skills" / "adad-workflow"

    print("[ADAD] 正在安裝全域 Skills（多候選路徑，盡力而為）...")
    installed_any = False
    for base_dir in GLOBAL_SKILLS_CANDIDATES:
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
        print("[ADAD ERROR] 所有候選全域 Skills 目錄皆安裝失敗。")
        sys.exit(1)

    src_agents_md = agents_dir() / "AGENTS.md"
    if os.path.exists(src_agents_md):
        with open(src_agents_md, "r", encoding="utf-8") as f:
            agents_rules_content = f.read()
        try:
            _write_global_rules_block(GLOBAL_RULES_FILE, agents_rules_content)
            print(f"  全域規則已安全寫入 {GLOBAL_RULES_FILE}")
        except Exception as e:
            print(f"  寫入全域規則檔案失敗: {e}")

    print("\n[ADAD] 全域安裝完成！")
    print("提醒：Antigravity 全域路徑約定仍在演進中，建議安裝後在 Antigravity")
    print("2.0 / IDE 的「Global Skills / Rules」設定畫面確認 adad-workflow 確實有被載入。")


def uninstall_global() -> None:
    """自全域 Antigravity（2.0 / IDE）設定移除 ADAD 客製化與規則"""
    print("[ADAD] 正在自全域移除...")

    for base_dir in GLOBAL_SKILLS_CANDIDATES:
        dest_skills_dir = os.path.join(base_dir, "adad-workflow")
        if os.path.exists(dest_skills_dir):
            try:
                shutil.rmtree(dest_skills_dir)
                print(f"  移除 {dest_skills_dir} 成功")
            except Exception as e:
                print(f"  移除 {dest_skills_dir} 失敗: {e}")

    if os.path.exists(GLOBAL_RULES_FILE):
        try:
            with open(GLOBAL_RULES_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            if AGENT_RULES_BLOCK_START in content:
                start_idx = content.find(AGENT_RULES_BLOCK_START)
                end_idx = content.find(AGENT_RULES_BLOCK_END) + len(AGENT_RULES_BLOCK_END)
                content = content[:start_idx] + content[end_idx:]
                with open(GLOBAL_RULES_FILE, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  清除 {GLOBAL_RULES_FILE} 中的 ADAD 規則區塊成功")
        except Exception as e:
            print(f"  清除全域規則失敗: {e}")

    print("[ADAD] 全域卸載完成！")


def pack_dist() -> None:
    """打包目前專案內的 .agents 為 zip 安裝包（開發者發布用，維持原行為，仍以 cwd 為準）"""
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

    print(f"[ADAD] 打包完成！已生成安裝包: {zip_name}")
