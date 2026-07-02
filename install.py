# -*- coding: utf-8 -*-
"""
ADAD Installer & Packager (ADAD 部署與打包工具)
ponytail: 完全使用 Python 標準庫實作，支援專案初始化、全域安裝與 zip 打包，防範重複寫入全域 AGENTS.md。
"""
import os
import sys
import shutil
import zipfile

GLOBAL_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".gemini", "config")
AGENT_RULES_BLOCK_START = "\n# === ADAD GLOBAL RULES START ===\n"
AGENT_RULES_BLOCK_END = "\n# === ADAD GLOBAL RULES END ===\n"

def init_project():
    """在當前目錄初始化 ADAD 模式"""
    print("[ADAD] 正在初始化當前專案...")
    import subprocess

    # 1. 建立 checkpoints 目錄
    if not os.path.exists("checkpoints"):
        os.makedirs("checkpoints")
        print("  - 建立 checkpoints/ 目錄成功")
    else:
        print("  - checkpoints/ 目錄已存在，跳過")

    # 1.2 建立 docs/adr 目錄與範本
    adr_dir = os.path.join("docs", "adr")
    if not os.path.exists(adr_dir):
        os.makedirs(adr_dir)
        print("  - 建立 docs/adr/ 目錄成功")
    else:
        print("  - docs/adr/ 目錄已存在，跳過")

    template_path = os.path.join(adr_dir, "ADR-000_template.md")
    if not os.path.exists(template_path):
        adr_template = """# ADR-000: 設計決策範本 (在此填寫決策標題)

## 狀態
Draft / Proposed / Approved / Rejected / Deprecated

## 脈絡 (Context)
在此說明此決策的背景脈絡、當前面臨的問題、需求或限制條件。

## 決策 (Decision)
在此寫下我們最終採用的方案（例如：採用 Redis 作為快取介質、採用 Event-Driven 進行模組解耦等），並扼要說明選擇此方案的原因。

## 後果 (Consequences)
在此列出採用此決策後帶來的優缺點、副作用或需要連帶調整的部分。
"""
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(adr_template)
        print("  - 建立 ADR-000_template.md 成功")
    else:
        print("  - ADR-000_template.md 已存在，跳過")

    # 1.3 建立 docs/patterns 目錄與範本
    patterns_dir = os.path.join("docs", "patterns")
    if not os.path.exists(patterns_dir):
        os.makedirs(patterns_dir)
        print("  - 建立 docs/patterns/ 目錄成功")
    else:
        print("  - docs/patterns/ 目錄已存在，跳過")

    pattern_template_path = os.path.join(patterns_dir, "pure_function.md")
    if not os.path.exists(pattern_template_path):
        pattern_template = """# Pure Function 模式規範

## 說明
此節點必須實作為無副作用的純函數 (Pure Function)。

## 程式碼規範
- 輸入引數必須為 immutable，禁止在函數內修改傳入的參數。
- 函數返回值僅由輸入引數決定，禁止存取 any 外部全域變量。
- 禁止呼叫 any side effect 函數 (I/O, DB, Network)...
"""
        with open(pattern_template_path, "w", encoding="utf-8") as f:
            f.write(pattern_template)
        print("  - 建立 pure_function.md 成功")
    else:
        print("  - pure_function.md 已存在，跳過")

    # 2. 建立 system_map.md 初始範本
    if not os.path.exists("system_map.md"):
        default_map = """# ADAD Architecture Source

## Metadata
- Version: 1
- Status: planning

## Domains

### Domain: Calculation
- Description: 專門進行核心稅率與商務計算的領域。

#### Subsystem: Core_Calculator
- Description: 負責各國與各類型稅務核心計算子系統。

##### Module: calculate_tax
- Type: function
- Description: 計算各國稅金的最簡原子函數
- Preferred Pattern: pure_function
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - amount: float
  - country: string
- Output:
  - tax: float
- TODO:
  - [ ] 補齊細部國家例外稅率支持
- Checkpoint:
  - [ ] CP-1-001 (planned)
"""
        with open("system_map.md", "w", encoding="utf-8") as f:
            f.write(default_map)
        print("  - 建立 system_map.md 初始範本成功")
        
        # 自動執行編譯以產生 system_map.yaml (IR)
        try:
            print("  - 正在自動編譯架構源檔案...")
            subprocess.run([sys.executable, ".agents/skills/adad-workflow/scripts/compile_map.py"], check=True)
            print("  - 自動編譯成功，已產生 system_map.yaml")
        except Exception as e:
            print(f"  - [警告] 自動編譯架構源檔案失敗: {e}")
    else:
        print("  - system_map.md 已存在，跳過")

    # 3. 建立 Docker 相關範本與 .gitignore
    # 建立 .gitignore
    gitignore_content = """# Python 暫存與虛擬環境
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.env

# 打包與壓縮檔
*.zip
*.tar.gz

# 系統檔案
.DS_Store
Thumbs.db
"""
    if not os.path.exists(".gitignore"):
        with open(".gitignore", "w", encoding="utf-8") as f:
            f.write(gitignore_content)
        print("  - 建立 .gitignore 成功")
    else:
        print("  - .gitignore 已存在，跳過")

    # 建立 Dockerfile
    dockerfile_content = """FROM python:3.11-slim

WORKDIR /app

# 複製依賴檔案並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製其餘代碼
COPY . .

CMD ["python", "main.py"]
"""
    if not os.path.exists("Dockerfile"):
        with open("Dockerfile", "w", encoding="utf-8") as f:
            f.write(dockerfile_content)
        print("  - 建立 Dockerfile 範本成功")
    else:
        print("  - Dockerfile 已存在，跳過")

    # 建立 docker-compose.yml
    docker_compose_content = """version: '3.8'

services:
  app:
    build: .
    volumes:
      - .:/app
    environment:
      - ENV=development
"""
    if not os.path.exists("docker-compose.yml"):
        with open("docker-compose.yml", "w", encoding="utf-8") as f:
            f.write(docker_compose_content)
        print("  - 建立 docker-compose.yml 範本成功")
    else:
        print("  - docker-compose.yml 已存在，跳過")

    # 建立 .dockerignore
    dockerignore_content = """venv/
.git/
__pycache__/
checkpoints/
*.zip
"""
    if not os.path.exists(".dockerignore"):
        with open(".dockerignore", "w", encoding="utf-8") as f:
            f.write(dockerignore_content)
        print("  - 建立 .dockerignore 成功")
    else:
        print("  - .dockerignore 已存在，跳過")

    # 建立 requirements.txt
    requirements_content = """pyyaml
"""
    if not os.path.exists("requirements.txt"):
        with open("requirements.txt", "w", encoding="utf-8") as f:
            f.write(requirements_content)
        print("  - 建立 requirements.txt 成功")
    else:
        print("  - requirements.txt 已存在，跳過")

    # 4. Git 初始化
    if not os.path.exists(".git"):
        try:
            # 檢查 git 是否可用
            subprocess.run(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
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

    # 6. 安裝 pre-commit hook
    hook_src = os.path.join(".agents", "skills", "adad-workflow", "scripts", "adad_pre_commit.py")
    hook_dst = os.path.join(".git", "hooks", "pre-commit")
    if os.path.exists(".git") and os.path.exists(hook_src):
        os.makedirs(os.path.dirname(hook_dst), exist_ok=True)
        try:
            hook_content = f"""#!/bin/sh
python "{hook_src}"
"""
            with open(hook_dst, "w", encoding="utf-8") as f:
                f.write(hook_content)
            try:
                os.chmod(hook_dst, 0o755)
            except:
                pass
            print("  - 建立 pre-commit hook 成功")
        except Exception as e:
            print(f"  - [警告] 建立 pre-commit hook 失敗: {e}")

    print("[ADAD] 專案初始化完成！")

def clean_project():
    """復原/清理當前專案中的 ADAD 相關產出與環境"""
    print("[ADAD] 正在還原專案環境並清理 ADAD 檔案...")
    
    # 1. 移除 pre-commit hook
    hook_dst = os.path.join(".git", "hooks", "pre-commit")
    if os.path.exists(hook_dst):
        try:
            os.remove(hook_dst)
            print("  - ✅ 移除 pre-commit hook 成功")
        except Exception as e:
            print(f"  - 移除 pre-commit hook 失敗: {e}")
            
    # 2. 刪除產生的 system_map.yaml
    if os.path.exists("system_map.yaml"):
        try:
            os.remove("system_map.yaml")
            print("  - 移除 system_map.yaml 成功")
        except Exception as e:
            print(f"  - 移除 system_map.yaml 失敗: {e}")

    # 刪除產生的 system_map.md
    if os.path.exists("system_map.md"):
        try:
            os.remove("system_map.md")
            print("  - 移除 system_map.md 成功")
        except Exception as e:
            print(f"  - 移除 system_map.md 失敗: {e}")

    # 3. 刪除虛擬環境 venv
    if os.path.exists("venv"):
        try:
            shutil.rmtree("venv")
            print("  - 移除 venv 虛擬環境成功")
        except Exception as e:
            print(f"  - 移除 venv 虛擬環境失敗: {e}")

    # 4. 刪除 checkpoints 目錄
    if os.path.exists("checkpoints"):
        try:
            shutil.rmtree("checkpoints")
            print("  - 移除 checkpoints/ 目錄成功")
        except Exception as e:
            print(f"  - 移除 checkpoints/ 失敗: {e}")

    print("[ADAD] 專案清理還原完成！")

def install_global():
    """將此 ADAD 客製化安裝至全域 Antigravity 設定"""
    print(f"[ADAD] 正在安裝至全域目錄: {GLOBAL_CONFIG_DIR}...")
    
    if not os.path.exists(GLOBAL_CONFIG_DIR):
        print(f"[ADAD ERROR] 找不到全域設定目錄: {GLOBAL_CONFIG_DIR}，請確認 Antigravity 已安裝且執行過。")
        sys.exit(1)

    # 1. 複製 Skills 到全域
    src_skills_dir = os.path.join(".agents", "skills", "adad-workflow")
    dest_skills_dir = os.path.join(GLOBAL_CONFIG_DIR, "skills", "adad-workflow")

    if not os.path.exists(src_skills_dir):
        print(f"[ADAD ERROR] 找不到專案內的 Skills 目錄: {src_skills_dir}")
        sys.exit(1)

    if os.path.exists(dest_skills_dir):
        print("  - 偵測到已存在全域 ADAD Skill，正在進行覆蓋更新...")
        shutil.rmtree(dest_skills_dir)
        
    shutil.copytree(src_skills_dir, dest_skills_dir)
    print("  - 複製 Skills 至全域成功")

    # 2. 安全寫入全域 AGENTS.md
    src_agents_md = os.path.join(".agents", "AGENTS.md")
    dest_agents_md = os.path.join(GLOBAL_CONFIG_DIR, "AGENTS.md")

    if os.path.exists(src_agents_md):
        with open(src_agents_md, "r", encoding="utf-8") as f:
            agents_rules_content = f.read()

        global_rules_content = ""
        if os.path.exists(dest_agents_md):
            with open(dest_agents_md, "r", encoding="utf-8") as f:
                global_rules_content = f.read()

        # 移除舊的 ADAD 規則區塊，避免重複追加
        if AGENT_RULES_BLOCK_START in global_rules_content:
            start_idx = global_rules_content.find(AGENT_RULES_BLOCK_START)
            end_idx = global_rules_content.find(AGENT_RULES_BLOCK_END) + len(AGENT_RULES_BLOCK_END)
            global_rules_content = global_rules_content[:start_idx] + global_rules_content[end_idx:]

        # 追加新規則
        new_rules_block = f"{AGENT_RULES_BLOCK_START}{agents_rules_content}{AGENT_RULES_BLOCK_END}"
        global_rules_content = global_rules_content.rstrip() + "\n" + new_rules_block

        with open(dest_agents_md, "w", encoding="utf-8") as f:
            f.write(global_rules_content)
        print("  - 全域 AGENTS.md 規則安全更新成功")
    
    print("[ADAD] 全域安裝完成！")

def uninstall_global():
    """自全域 Antigravity 設定移除 ADAD 客製化與規則"""
    print(f"[ADAD] 正在自全域移除...")
    
    # 1. 移除全域 Skill
    dest_skills_dir = os.path.join(GLOBAL_CONFIG_DIR, "skills", "adad-workflow")
    if os.path.exists(dest_skills_dir):
        try:
            shutil.rmtree(dest_skills_dir)
            print("  - 移除全域 ADAD Skill 成功")
        except Exception as e:
            print(f"  - 移除全域 ADAD Skill 失敗: {e}")
            
    # 2. 清除全域 AGENTS.md 中的規則區塊
    dest_agents_md = os.path.join(GLOBAL_CONFIG_DIR, "AGENTS.md")
    if os.path.exists(dest_agents_md):
        try:
            with open(dest_agents_md, "r", encoding="utf-8") as f:
                content = f.read()
            if AGENT_RULES_BLOCK_START in content:
                start_idx = content.find(AGENT_RULES_BLOCK_START)
                end_idx = content.find(AGENT_RULES_BLOCK_END) + len(AGENT_RULES_BLOCK_END)
                content = content[:start_idx] + content[end_idx:]
                with open(dest_agents_md, "w", encoding="utf-8") as f:
                    f.write(content)
                print("  - 清除全域 AGENTS.md 規則區塊成功")
        except Exception as e:
            print(f"  - 清除全域 AGENTS.md 規則失敗: {e}")

    print("[ADAD] 全域卸載完成！")

def pack_dist():
    """打包 .agents 為 zip 安裝包供 GitHub 發布"""
    print("[ADAD] 正在打包客製化套件...")
    zip_name = "adad-customizations.zip"
    
    if not os.path.exists(".agents"):
        print("[ADAD ERROR] 找不到 .agents 資料夾，無法打包。")
        sys.exit(1)

    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(".agents"):
            for file in files:
                file_path = os.path.join(root, file)
                # 寫入 zip，保留相對路徑
                zipf.write(file_path, file_path)

    print(f"[ADAD] 打包完成！已生成安裝包: {zip_name}")

def main():
    if len(sys.argv) < 2:
        print("ADAD 部署與復原工具說明：")
        print("  python install.py init      - 在當前專案目錄初始化 ADAD (建立 checkpoints, system_map.md, venv, hook 等)")
        print("  python install.py clean     - 還原專案環境並清理 ADAD 檔案 (刪除 checkpoints, venv, hook 與 yaml)")
        print("  python install.py global    - 將本規範與 Skill 部署至 Antigravity 全域設定 (供所有專案使用)")
        print("  python install.py uninstall - 自 Antigravity 全域設定移除 ADAD 客製化與規則")
        print("  python install.py pack      - 打包 .agents 客製化目錄為 zip 檔，便於上傳 GitHub 發布")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_project()
    elif cmd == "clean":
        clean_project()
    elif cmd == "global":
        install_global()
    elif cmd == "uninstall":
        uninstall_global()
    elif cmd == "pack":
        pack_dist()
    else:
        print(f"[ADAD ERROR] 未知的指令: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
