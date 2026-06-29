# 📋 ADAD (Architecture-Driven Agentic Development) 開發規範與工具鏈

本專案是一個專為 **Antigravity AI Agent** 設計的 Workspace Customization 擴充套件，旨在實行 **ADAD (架構驅動型智能體開發)** 開發模式。

ADAD 的核心理念是：**將「系統設計（架構）」與「程式碼實作（邏輯）」徹底解耦**。由人類把持高價值的架構與驗收 Checkpoint，並指派 Agent 在最小 Context 的約束下進行高精度的原子程式碼生成，以防範 AI 開發中的架構失控與 Context 膨脹問題。

---

## 📂 專案目錄結構

```
programming_design/
├── .agents/                      # Workspace Customizations 根目錄
│   ├── AGENTS.md                 # Antigravity Rules (定義四大全局規則與 CP 決策限制)
│   └── skills/                   # 自訂 Skills
│       └── adad-workflow/        # ADAD 輔助工具技能
│           ├── SKILL.md          # Skill 定義與 Antigravity 調用引導
│           └── scripts/          # Antigravity 藉由 run_command 執行的輔助 Python 腳本
│               ├── adad_core.py  # 核心邏輯 (YAML 讀寫、DAG 分析、Rule of Two 檢查)
│               ├── read_context.py
│               ├── check_normalization.py
│               ├── analyze_cascade.py
│               └── transit_state.py
├── checkpoints/                  # Checkpoint 決策歷史存檔目錄 (CP-X-XXX.yaml)
├── system_map.yaml               # 專案架構唯一事實來源 (SSOT)
├── 程式開發規範.md               # 人類閱讀的詳細規範說明書
├── install.py                    # 安裝、初始化與打包指令腳本
└── README.md                     # 本說明文件
```

---

## 🛠️ 快速開始

本工具鏈完全基於 **Python 標準庫** 實作，無須手動配置任何複雜的依賴套件。

### 1. 初始化當前專案
在新專案目錄下，執行以下指令初始化 ADAD 環境：
```bash
python install.py init
```
這將會在專案中建立 `checkpoints/` 資料夾以及 `system_map.yaml` 架構總表範本。

### 2. 全域安裝 (跨專案通用)
將本規範與 Skills 安裝至您目前電腦中 Antigravity 的全域設定目錄：
```bash
python install.py global
```
*這會自動將 ADAD 規則追加至您全域的 `AGENTS.md` 結尾，且具備防重複寫入機制。*

### 3. 打包分發
將目前專案的 ADAD 客製化目錄（`.agents/`）打包成 zip 壓縮檔，便於分發或上傳至 GitHub：
```bash
python install.py pack
```

---

## 🔄 ADAD 核心 CLI 工具說明

當前專案底下的 Antigravity Agent 可以直接調用以下指令來操作架構狀態：

| 工具腳本 | 功能說明 | 調用時機 |
| :--- | :--- | :--- |
| `read_context.py` | 讀取單一節點最小上下文 | Phase 2 開始編寫代碼前，獲取目標簽章 |
| `check_normalization.py` | 執行 Rule of Two 檢查 | Phase 1 架構規劃期，檢測是否重複造輪子 |
| `analyze_cascade.py` | 執行髒點依賴分析 (DAG 走查) | Phase 3 反向同步，架構變更時級聯標記 `dirty` |
| `transit_state.py` | 推進/變更模組生命週期狀態 | CP 審查通過、Lint 通過或被退回時更新狀態 |

---

## 🛡️ 四大全局規則 (Global Rules)

載入此規範後，Agent 將會嚴格遵循以下「開發憲法」：
1. **[RULE-01] SSOT 唯一性**：唯一 Fact 來源為 `system_map.yaml`。
2. **[RULE-02] 先架構後程式**：嚴禁 Code-First，節點需為 `planned` 或 `dirty` 始能寫 code。
3. **[RULE-03] 原子化操作**：每次變更只能影響單一節點，防止大規模程式碼 Patch。
4. **[RULE-04] 遇錯即停 (Fail-Fast)**：實作期發現規格缺陷，必須中斷生成並呈報 Schema Update Request。
