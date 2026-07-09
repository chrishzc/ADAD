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
1. **新增模組前，先查表、不要用猜的**：準備新增一個模組（Module）之前，**必須先執行**
   `python .agents/skills/adad-workflow/scripts/resolve_target_file.py <domain> [subsystem]`，
   它會直接告訴你這個 Domain/Subsystem 目前落腳在哪個實體檔案（`target_file`），你要把新模組寫進**那個檔案**，
   不可以自己讀 `system_map.md` 用肉眼追 include 鏈猜測。若該 Domain/Subsystem 尚不存在，這支腳本也會給出
   是否該一開始就拆成獨立子地圖檔案的建議。
2. **修改既有模組**：若是修改既有模組，直接執行 `read_context.py <node_name>`，回傳的 `map_file` 欄位就是
   這個模組實際所在的實體檔案，去該檔案編輯，而非根目錄檔案。
3. **完成編輯後編譯**：不論你修改了主地圖或是任何一個子地圖，**都必須立刻執行編譯指令**：`python .agents/skills/adad-workflow/scripts/compile_map.py`，將其彙整編譯為中間表示 `system_map.yaml` 以更新狀態。
   編譯時若出現 `[MISPLACED MODULE]` 警告，代表有模組被寫進了跟其 Domain/Subsystem 不一致的檔案，**必須立刻搬移到警告中指出的正確檔案**。
   RULE-05 依模組生命週期狀態分級：`planned` / `draft`（尚未通過任何 Checkpoint 審查）階段只會警告、不阻斷 commit，方便規劃期邊寫邊調整；
   一旦推進到 `pending_review` 以上（至少通過一次 Checkpoint 審查、甚至已有其他模組依賴它），`adad_pre_commit.py` 會直接阻斷 commit，不能再拖到之後才搬。

---

## 🔗 Source 欄位規範（模組 ↔ 實作檔案綁定，**機械強制的前提條件**）

每個 `##### Module:` 節點都應該填寫 `- Source:` 欄位，指向該模組實際實作程式碼的**相對路徑**（相對於專案根目錄）：

```
##### Module: calculate_tax
- Type: function
- Description: 計算各國稅金的最簡原子函數
- Source: src/tax/calculate_tax.py
- Preferred Pattern: pure_function
- Complexity: low
...
```

若函式邏輯較複雜（多分支、多步驟、有演算法），額外標記 `Complexity: high` 並補上 `Algorithm` 步驟大綱——這是為了解決「Input/Output/Invariants 只描述對外契約，卻沒描述內部該怎麼做」的缺口：能力較弱的模型光靠契約常常一次生成邏輯就出錯，或反覆撞 Verification 失敗卻收斂不了。有了步驟大綱，Phase 2 只需要把每一小段「翻譯」成程式碼，而不必自己重新「設計」：

```
##### Module: reconcile_ledger
- Type: function
- Description: 依多幣別交易記錄核銷應收帳款，處理跨幣別匯損分攤
- Source: src/billing/reconcile_ledger.py
- Preferred Pattern: none
- Complexity: high
- Algorithm:
  - 依交易時間排序後，先分離出已核銷與未核銷兩組
  - 未核銷組依幣別分組，各自換算為本位幣
  - 若同一應收單有多筆部分核銷，依 FIFO 順序依序沖抵
  - 沖抵後有餘額則按當期匯率計算匯損並落單獨立分錄
  - 最後彙總回傳每筆應收單的核銷狀態與匯損明細
...
```

`Complexity: low` 是預設值，可以省略不寫；只有需要拉高到 `medium`/`high` 時才需要顯式標記。合法值只有 `low`/`medium`/`high`，寫錯字（例如打成 `hgih`）在編譯時會被靜默正規化回 `low`，不會讓編譯失敗，但也代表這個分級形同沒生效，請確認拼字正確。`Complexity: high` 卻沒填 `Algorithm` 時，`compile_map.py` 會印出 `[MISSING ALGORITHM]` 警告（不阻斷編譯），提醒在進入 Phase 2 原子生成前先補上步驟大綱。

**這個欄位不是選填的裝飾，而是 `adad_pre_commit.py` 判斷「哪個被修改的檔案對應到哪個模組」的唯一依據**（見 `build_source_to_module_map`）。若模組沒有填 `Source`，pre-commit hook 完全無法把 staged 的 `.py` 檔案跟這個模組對上，會直接跳過該檔案：

- **[RULE-02] 狀態門禁**（未通過 Checkpoint 的節點禁止改代碼）不會生效
- **[RULE-03] 原子範圍警告**不會生效
- **Invariants（`deny_imports`）** 與 **Verification（`must_have_assertions`）** 校驗不會生效
- **跨 Domain 依賴邊界檢查**的「本次 commit 是否觸碰到模組程式碼」判斷也會失準

換句話說：**沒填 `Source`，pre-commit hook 只剩 Staleness 一項在運作，其餘機械強制形同虛設**。

作為 Agent，你必須遵守：
1. **Phase 1 規劃節點時**，只要你已經知道或已經決定該模組會實作在哪個檔案，就在 `system_map.md` 一併填上 `- Source:`。
2. **Phase 2 原子生成、真正建立該實作檔案時**，若規劃階段還沒填（或路徑後來變了），必須回頭補上/更新 `system_map.md` 對應節點的 `Source` 欄位，並重新執行 `compile_map.py`。
3. 一個 `Source` 路徑理論上只對應一個模組；若同一支檔案承載多個模組的邏輯，請至少讓「主要負責的模組」填上該路徑，避免完全沒有模組能對應到這支檔案。

---



你必須透過 `run_command` 呼叫以下 CLI 指令來執行對應的架構操作，禁止手動用正則表達式或直接文字覆寫去修改 `system_map.yaml` 中的狀態或依賴結構。

### 0. 🏗️ 編譯架構源檔案 (Markdown ➔ YAML)
* **指令**：`python .agents/skills/adad-workflow/scripts/compile_map.py`
* **時機**：任何時候當人類修改了 `system_map.md`，或是 Agent 進行了架構展開（Architecture Growth）後，**必須首要執行此編譯指令**，以更新架構中間表示 IR (`system_map.yaml`) 並自動繼承與比對生命週期狀態。
* **重要**：如果 `system_map.md` 的修改時間晚於 `system_map.yaml`，其他查詢指令（如 `read_context.py`）將被自動阻斷並要求執行此編譯。

### 0.5 🗺️ 解析子地圖落點（新模組該寫進哪個檔案）
* **指令**：`python .agents/skills/adad-workflow/scripts/resolve_target_file.py <domain> [subsystem]`
* **時機**：Phase 1（架構規劃）要新增任何模組之前，**必須先執行**，取得 `target_file` 後才動筆寫 `##### Module:` 節點。
* **輸出**：`target_file`（該寫進的實體檔案）、`domain_exists` / `subsystem_exists`、以及尚未拆檔案時是否建議拆分的 `hint`。

### 0. 🧭 編譯與靜默脫鉤偵測
* **指令**：`python .agents/skills/adad-workflow/scripts/compile_map.py`
* 编譯時若出現 `[UNTRACKED SYMBOL]` 警告：代表某個「整檔登記」（Source 沒有用 `::` 逐函式標註）的模組，其原始碼裡出現了先前編譯時沒見過的新函式/方法。這不會阻斷編譯或 commit——`planned`/`draft`/`dirty`/`validated` 狀態下本來就允許自由修改程式碼，這只是讓這個新增動作「至少有人看得到」，不是要禁止它。看到這個警告時，確認一下新函式是否真的屬於這個模組的職責；如果這個檔案的職責已經變得複雜到需要被個別追蹤，考慮改成 `Source: file.py::func1,func2` 逐函式登記，才能讓 RULE-04 對它生效。

### 1. 🎯 讀取單一節點上下文
* **指令**：`python .agents/skills/adad-workflow/scripts/read_context.py <node_name>`
* **時機**：在 Phase 2（原子生成）開始編寫特定節點的程式碼前，必須先執行此指令獲取該節點的 Input、Output、Invariants、Verification、Preferred Pattern、Complexity/Algorithm（若有）以及相依 Interface 定義。
  若 `Complexity` 為 `high`，**必須**先讀完 `Algorithm` 步驟大綱再動筆，逐步翻譯成程式碼，不要跳過步驟大綱直接自行設計邏輯。

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

### 6.5 🌐 執行跨 Domain 依賴邊界檢查
* **指令**：`python .agents/skills/adad-workflow/scripts/check_domain_boundary.py`
* **時機**：Phase 1（架構規劃）新增或修改模組依賴之後，必須執行此指令。它會檢查所有模組的 `dependencies` 是否跨越了不該跨越的 Domain 邊界——模組只能依賴同一個 Domain 內的模組，除非該 Domain 在 `system_map.md` 用 `Allowed Dependencies: [OtherDomain, ...]` 明確宣告允許依賴。此檢查也已整合進 `adad_pre_commit.py`，只要本次 commit 觸碰到任一模組的原始碼，就會對整份架構圖做一次邊界檢查。

### 7. 🧪 執行代碼實現校驗 (Verification)
* **指令**：`python .agents/skills/adad-workflow/scripts/verify_implementation.py <node_name> [file_path]`
* **時機**：在完成代碼實作後。必須執行此指令，檢查代碼是否符合架構設計所要求的 Verification 驗證條件。
* **支援兩種規則，可在同一節點混用**：
  - `must_have_assertions`：靜態 AST 掃描，檢查檔案裡至少有一個 `assert` 語句。只證明「有自檢」，不證明「自檢內容是對的」。
  - `case`（**可執行測試案例**）：真的動態 import 該節點對應的函式，用 `input` 當 kwargs 呼叫，比對回傳值是否等於 `expect`。這才是真正驗證「邏輯對不對」。語法（嚴格 JSON，雙引號、不可有多餘逗號）：
    ```
    - Verification:
      - case: {"input": {"a": 1, "b": 2}, "expect": 3}
      - case: {"input": {"a": -1, "b": 1}, "expect": 0}
    ```
    JSON 格式寫錯會在 `compile_map.py` 編譯時直接失敗並指出是哪個模組、哪一段寫錯，不會留到執行期才含糊報錯。失敗時 `verify_implementation.py` 會回傳每一組 case 的 `input`/`expect`/`actual`，讓你（或 agent 自己）能立刻看到具體哪裡算錯，而不必等人類複審。
  - **函式名稱解析慣例**：`Source: file.py::func_name` 時用 `func_name`；`Source: file.py`（整檔登記）時假設函式名稱與 Module 名稱相同。
  - **已知限制**：動態載入單一檔案執行，若該函式依賴同套件內其他檔案的相對匯入，可能無法完全解析（已盡量把檔案所在目錄加進 `sys.path`，但不保證所有情境）。遇到這類複雜依賴，建議把待驗證函式拆到匯入依賴單純的模組。

### 6.7 📐 正式 Schema 驗證 (system_map.yaml)
* **指令**：`python .agents/skills/adad-workflow/scripts/validate_schema.py [yaml_path] [schema_path]`（預設分別是 `system_map.yaml`、`system_map.schema.json`）
* **時機**：已整合進 `compile_map.py`，每次編譯後自動執行，無須獨立呼叫；如果需要對別的 yaml 檔案（例如 CI 裡的暫存檔）單獨驗證，才需要手動下指令。
* **這在驗證什麼**：`system_map.schema.json` 是一份跟 Python 實作完全脫鉤的標準 JSON Schema，明確定義 Module 的必要欄位、`state`/`complexity` 的合法 enum 值、`verification` 的 `case` 結構等。這道防線獨立於 `parse_markdown` 的產生邏輯之外——`parse_markdown` 或 `compile_map.py` 未來如果被改壞而產出不合規的 yaml，這裡有機會攔下來，而不是產生者跟檢查者用同一套邏輯、自己抓不到自己的錯。任何非 Python 工具（IDE 外掛、其他語言寫的 CI 檢查）也可以直接拿這份 `system_map.schema.json` 驗證，不需要理解 Markdown 語法。
* **驗證器**：優先使用 `jsonschema`（若環境已安裝，功能最完整）；沒裝的話自動退回純標準庫實作的子集驗證器（涵蓋 type/required/properties/enum/items/oneOf/$ref，足以擋下本專案 schema 實際會用到的錯誤類型）。
* **失敗時的行為**：`compile_map.py` 會直接印出每一項違規的路徑與原因並中止編譯（`sys.exit(1)`）——結構不合規的 yaml 不該被視為編譯成功。若專案裡沒有 `system_map.schema.json`（例如舊專案尚未升級），會印出 `[NO SCHEMA]` 警告但不阻斷，向下相容。

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
