---
name: adad-workflow
description: 用於執行 ADAD (Architecture-Driven Agentic Development) 的架構與工作流管理工具。當人類或流程要求進行「架構規劃」、「Checkpoint 狀態轉換」、「相依髒點級聯分析」、「讀取節點上下文」或「編譯與分析進度」時觸發。
---

# 🛠️ ADAD (Architecture-Driven Agentic Development) Workflow Skills

此 Skill 賦予 Antigravity Agent 操作架構 Markdown Source (`system_map.md`)、編譯架構 IR (`system_map.yaml`) 與流程狀態推演的能力。
當觸發此技能時，你應優先透過執行 `.agents/skills/adad-workflow/scripts/` 目錄下的輔助 Python 腳本來完成操作。

---

## 📁 分區地圖與子模組編輯規範 (Split-Map Directives)

本專案支援利用 `<!-- include 檔案路徑 -->` 將主架構地圖 `system_map.md` 拆分至多個子目錄中進行分區管理。
作為 Agent，你必須遵循以下編輯規則：
1. **定位目標檔案**：當你準備新增、修改或刪除某個模組（Module）或子系統（Subsystem）的架構時，**優先檢查其是否屬於某個子目錄模組**。
2. **追蹤 Include 鏈**：你必須先讀取根目錄的 `system_map.md`，確認你要變更的區塊是否已被 `<!-- include path/to/subfolder_map.md -->` 引入。若是，請直接編輯對應的子地圖 Markdown 檔案，而非根目錄檔案。
3. **完成編輯後編譯**：不論你修改了主地圖或是任何一個子地圖，**都必須立刻執行編譯指令**：`python .agents/skills/adad-workflow/scripts/compile_map.py`，將其彙整編譯為中間表示 `system_map.yaml` 以更新狀態。

---

## 🛠️ 核心指令對照與調用指引

你必須透過 `run_command` 呼叫以下 CLI 指令來執行對應的架構操作，禁止手動用正則表達式或直接文字覆寫去修改 `system_map.yaml` 中的狀態或依賴結構。

### 0. 🏗️ 編譯架構源檔案 (Markdown ➔ YAML)
* **指令**：`python .agents/skills/adad-workflow/scripts/compile_map.py`
* **時機**：任何時候當人類修改了 `system_map.md`，或是 Agent 進行了架構展開（Architecture Growth）後，**必須首要執行此編譯指令**，以更新架構中間表示 IR (`system_map.yaml`) 並自動繼承與比對生命週期狀態。
* **重要**：如果 `system_map.md` 的修改時間晚於 `system_map.yaml`，其他查詢指令（如 `read_context.py`）將被自動阻斷並要求執行此編譯。

### 1. 🎯 讀取單一節點上下文
* **指令**：`python .agents/skills/adad-workflow/scripts/read_context.py <node_name>`
* **時機**：在 Phase 2（原子生成）開始編寫特定節點的程式碼前，必須先執行此指令獲取該節點的 Input、Output、Invariants、Preferred Pattern 以及相依 Interface 定義。

### 2. 🛡️ 執行 Rule of Two 邊界檢查
* **指令**：`python .agents/skills/adad-workflow/scripts/check_normalization.py "<proposed_function_json_or_yaml_string>"`
* **時機**：在 Phase 1（架構規劃）想建立新功能/函數時，必須執行此指令判定該功能的特徵是否已在架構中重複出現過 2 次以上。若觸發規則，你必須改為使用已存在的 Shared Module。

### 3. 🔍 執行髒點級聯依賴分析 (DAG 走查)
* **指令**：`python .agents/skills/adad-workflow/scripts/analyze_cascade.py <changed_node_name>`
* **時機**：在 Phase 3（反向同步）人類批准 Schema 變更後，或任何節點規格變更時，必須執行此指令來更新 DAG 依賴，自動將所有受影響的上層節點標記為 `dirty`。

### 4. 🔄 推進模組生命週期狀態
* **指令**：`python .agents/skills/adad-workflow/scripts/transit_state.py <node_name> <next_state>`
* **時機**：當 Checkpoint 通過，或者 Lint/Test 通過時，呼叫此指令來安全推進 `system_map.yaml` 中節點的生命週期狀態。

### 5. 🐳 Docker Compose 環境與容器編排規劃 (Phase 1.5)
* **時機**：Phase 1 架構規劃 (CP-1) 核准後，開始 Phase 2 代碼生成前。
* **行為**：
  1. 於 `system_map.md` 的模組外層或 YAML 最外層加入 `environment` 結構，規劃所有 Docker 容器服務，將 environment 狀態設為 `planned`。
  2. 呈報 **CP-1.5** 審查 Payload 供人類確認。
  3. 核准後，自動為各服務產生對應的 `Dockerfile`、`docker-compose.yml` 與 `.dockerignore`。

### 6. 🛡️ 執行架構不變量 (Invariants) 檢查
* **指令**：`python .agents/skills/adad-workflow/scripts/check_invariants.py <node_name> [file_path]`
* **時機**：在 Phase 2（原子生成）完成程式碼實作，且通過 Lint 驗證之後。必須執行此指令，驗證生成的程式碼是否違反了架構不變量邊界（例如 `deny_imports` 限制）。若檢查失敗，你必須根據錯誤修正代碼，不可直接提交。

### 7. 🧪 執行代碼實現校驗 (Verification)
* **指令**：`python .agents/skills/adad-workflow/scripts/verify_implementation.py <node_name> [file_path]`
* **時機**：在完成代碼實作後。必須執行此指令，檢查代碼是否符合架構設計所要求的 Verification 驗證條件（例如 `must_have_assertions` 斷言檢測）。

### 8. 📊 重新讀取進度與思路重啟 (Resume)
* **指令**：`python .agents/skills/adad-workflow/scripts/resume_analysis.py`
* **時機**：當 Agent 啟動或中途接手任務時、或人類需要了解目前專案進度、TODO 項目與未完成 Checkpoint 時。此報告現包含 **Draft Debt Ledger** 區塊，顯示所有 draft/pending_review 模組及其風險等級。

### 9. 📋 Draft Debt Ledger 偵測 (Draft Debt)
* **說明**：Draft Debt 偵測已整合於 `compile_map.py` 編譯流程中，無須獨立呼叫。每次編譯時系統自動計算 fan-in 變化，若 draft 模組的 fan-in 從 0 → ≥2，自動升級為 `pending_review` 並提示需要補做 Checkpoint（含 ADR）。
* **查看方式**：執行 `resume_analysis.py` 即可在報告末尾看到 Draft Debt Ledger 表格。

### 10. 🔒 Pre-Commit Hook 手動觸發
* **指令**：`python .agents/skills/adad-workflow/scripts/adad_pre_commit.py`
* **時機**：在 `git commit` 之前手動檢查，或用於 CI/CD 流水線中。此腳本會執行 5 項檢查（Staleness、狀態門禁、原子範圍、Invariants、Verification），阻斷不合規的提交。
* **自動安裝**：執行 `python install.py init` 時會自動將此腳本安裝為 `.git/hooks/pre-commit`。

---

## 🚧 錯誤處理機制

若執行上述任何腳本返回錯誤（Exit Code != 0），你必須立即停止當前操作，將錯誤訊息輸出並呈報給人類，不可自行忽略或嘗試繞過。
