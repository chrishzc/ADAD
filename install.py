# -*- coding: utf-8 -*-
"""
ADAD Installer & Packager (ADAD 部署與打包工具)
ponytail: 完全使用 Python 標準庫實作，支援專案初始化、全域安裝與 zip 打包，防範重複寫入全域 AGENTS.md。
"""
import os
import sys
import shutil
import zipfile

GLOBAL_CONFIG_DIR = r"C:\Users\chris\.gemini\config"
AGENT_RULES_BLOCK_START = "\n# === ADAD GLOBAL RULES START ===\n"
AGENT_RULES_BLOCK_END = "\n# === ADAD GLOBAL RULES END ===\n"

def init_project():
    """在當前目錄初始化 ADAD 模式"""
    print("[ADAD] 正在初始化當前專案...")
    
    # 1. 建立 checkpoints 目錄
    if not os.path.exists("checkpoints"):
        os.makedirs("checkpoints")
        print("  - 建立 checkpoints/ 目錄成功")
    else:
        print("  - checkpoints/ 目錄已存在，跳過")

    # 2. 建立 system_map.yaml 初始範本
    if not os.path.exists("system_map.yaml"):
        default_map = """version: 1
modules:
  # 範例節點：請使用 transit_state 推進其生命週期，或使用 read_context 讀取其介面
  calculate_tax:
    type: "function"
    state: "planned"
    dependencies: []
    input:
      amount: "float"
      country: "string"
    output:
      tax: "float"
    description: "計算各國稅金的最簡原子函數"
"""
        with open("system_map.yaml", "w", encoding="utf-8") as f:
            f.write(default_map)
        print("  - 建立 system_map.yaml 初始範本成功")
    else:
        print("  - system_map.yaml 已存在，跳過")

    print("[ADAD] 專案初始化完成！")

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
        print("ADAD 部署工具說明：")
        print("  python install.py init    - 在當前專案目錄初始化 ADAD (建立 checkpoints, system_map.yaml)")
        print("  python install.py global  - 將本規範與 Skill 部署至 Antigravity 全域設定 (供所有專案使用)")
        print("  python install.py pack    - 打包 .agents 客製化目錄為 zip 檔，便於上傳 GitHub 發布")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_project()
    elif cmd == "global":
        install_global()
    elif cmd == "pack":
        pack_dist()
    else:
        print(f"[ADAD ERROR] 未知的指令: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
