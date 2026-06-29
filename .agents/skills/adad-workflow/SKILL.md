---
name: adad-workflow
description: 用於執行 ADAD (Architecture-Driven Agentic Development) 的架構與工作流管理工具。當人類或流程要求進行「架構規劃」、「Checkpoint 狀態轉換」、「相依髒點級聯分析」或「讀取節點上下文」時觸發。
---

# 🛠️ ADAD (Architecture-Driven Agentic Development) Workflow Skills

此 Skill 賦予 Antigravity Agent 操作架構 SSOT (`system_map.yaml`) 與流程狀態推演的能力。
當觸發此技能時，你應優先透過執行 `.agents/skills/adad-workflow/scripts/` 目錄下的輔助 Python 腳本來完成操作。

---

## 🛠️ 核心指令對照與調用指引

你必須透過 `run_command` 呼叫以下 CLI 指令來執行對應的架構操作，禁止手動用正則表達式或直接文字覆寫去修改 `system_map.yaml` 中的狀態或依賴結構。

### 1. 🎯 讀取單一節點上下文
* **指令**：`python .agents/skills/adad-workflow/scripts/read_context.py <node_name>`
* **時機**：在 Phase 2（原子生成）開始編寫特定節點的程式碼前，必須先執行此指令獲取該節點的 Input、Output、以及相依 Interface 定義。

### 2. 🛡️ 執行 Rule of Two 邊界檢查
* **指令**：`python .agents/skills/adad-workflow/scripts/check_normalization.py "<proposed_function_json_or_yaml_string>"`
* **時機**：在 Phase 1（架構規劃）想建立新功能/函數時，必須執行此指令判定該功能的特徵是否已在 `system_map.yaml` 重複出現過 2 次以上。若觸發規則，你必須改為使用已存在的 Shared Module。

### 3. 🔍 執行髒點級聯依賴分析 (DAG 走查)
* **指令**：`python .agents/skills/adad-workflow/scripts/analyze_cascade.py <changed_node_name>`
* **時機**：在 Phase 3（反向同步）人類批准 Schema 變更後，或任何節點規格變更時，必須執行此指令來更新 DAG 依賴，自動將所有受影響的上層節點標記為 `dirty`。

### 4. 🔄 推進模組生命週期狀態
* **指令**：`python .agents/skills/adad-workflow/scripts/transit_state.py <node_name> <next_state>`
* **時機**：當 Checkpoint 通過，或者 Lint/Test 通過時，呼叫此指令來安全推進 `system_map.yaml` 中節點的生命週期狀態。
* **合法狀態轉換**：
  * `planned` ➔ `validated` (CP1 審查通過)
  * `validated` ➔ `dirty` (因依賴變更被級聯污染)
  * `validated` ➔ `linted/tested` (Phase 2 代碼通過 Lint)
  * `linted/tested` ➔ `deployed` (CP2 審查通過)
  * `deployed` ➔ `dirty` (因依賴變更被級聯污染)

---

## 🚧 錯誤處理機制

若執行上述任何腳本返回錯誤（Exit Code != 0），你必須立即停止當前操作，將錯誤訊息輸出並呈報給人類，不可自行忽略或嘗試繞過。
