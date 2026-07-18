## 0. 分兩層看待每一個 Kernel 能力

對流程圖裡出現過的每一個 Kernel 節點,先問兩個問題：

1. **這件事發生在 agent 迴圈之外嗎？**（呼叫前 / 呼叫後的本地腳本）
   → 若是,答案跟 Kernel 是誰完全無關,ADAD 套件自己實作、自己保證。
2. **這件事必須發生在 agent 迴圈之內嗎？**（context 怎麼組、要不要呼叫工具、
   怎麼推論）
   → 若是,ADAD 套件做不到機械保證,只能透過該平台開放的掛勾點（MCP tool、
   hook、permission、skill/instruction 檔）去「引導」,強制程度隨平台而降級。

下面第 1 節的規格表,每一列都先回答這兩題,再給出「自建 Kernel」「現成平台」兩個
方向各自怎麼落地,最後一欄才是這份文件真正要交付的東西：**ADAD 套件裡對應要放
什麼檔案**。

---

## 1. 逐能力規格表

### 1-1｜Task 規格供給（Generate Task → Task 快照）

| | 內容 |
|---|---|
| 迴圈內 / 外 | **迴圈外**。純本地腳本,不需要 LLM 推論。 |
| ADAD 需求（契約） | 給定 `node_name`,回傳一份包含 `spec + task_id + source_hash` 的 Task 快照 JSON。 |
| 自建 Kernel 做法 | `generate_task.py` 內建在 Workflow Engine 的一個 Tool Runtime 呼叫裡。 |
| 現成平台做法 | 完全不受影響——這支腳本可以直接被任何平台當一般 CLI 呼叫（Claude Code 的 Bash tool、Antigravity 的 terminal 存取、Codex 的 shell 執行都能跑）。 |
| 強制程度 | **機械強制**,跟 Kernel 選型無關。 |
| ADAD 套件必須包含 | `generate_task.py`、`task_schema.json`（快照格式定義） |

### 1-2｜讀取邊界（Context Builder 只讀 Task 快照,不讀 system_map.yaml）

| | 內容 |
|---|---|
| 迴圈內 / 外 | **迴圈內**。這是 agent 決定「這次任務要看哪些檔案」的行為。 |
| ADAD 需求（契約） | 執行 Coding Task 時,agent 的上下文只能包含 Task 快照 + 被指定要改的檔案,不該主動去讀 `system_map.yaml` 或其他模組定義。 |
| 自建 Kernel 做法 | Context Builder 用程式碼組裝要送給 LLM 的內容,直接不把 `system_map.yaml` 放進去——**物理上不存在**,自然讀不到。 |
| 現成平台做法 | Claude Code / Antigravity / Codex 的 agent 都會主動探索檔案系統（這是它們「agentic」的賣點）,**無法物理隔絕**。只能：① 用專案層級權限把 `system_map.yaml` 設成該 agent 角色不可讀（如果平台支援檔案級 ACL 或 MCP 工具白名單）；② 在 instruction/skill 檔裡明文要求「執行 coding task 時只讀 task 快照,不要主動讀 system_map.yaml」。 |
| 強制程度 | 自建 = 機械強制；現成平台 = **指示性,無法保證**（除非平台剛好有檔案級權限機制,那退化成「可設定但需自行維護白名單」）。 |
| ADAD 套件必須包含 | 一份**平台專屬 instruction/skill 包**（見第 2 節）;以及一份「讀取邊界檢查腳本」——在 Coding Task 完成後,比對 git diff / 這次 session 實際讀取的檔案清單（如果平台有 log）,回溯檢查有沒有踩線,踩線就在 Harness 那關擋下來當違規,而不是事前阻止。 |

### 1-3｜驗證掛勾（Harness：check_invariants / verify_implementation）

| | 內容 |
|---|---|
| 迴圈內 / 外 | **迴圈外可以**,只要「寫完檔案之後」有個確定會被觸發的掛點。 |
| ADAD 需求（契約） | 每次 Coding Task 寫完程式碼,必須跑一次不變量檢查與實作驗證,失敗要能被抓到並回饋給 agent 重試。 |
| 自建 Kernel 做法 | 內建在 Workflow Engine 的固定步驟,寫檔案後自動觸發,失敗直接把結果塞回 context 讓 LLM 重試。 |
| 現成平台做法 | Claude Code 有 `PostToolUse` hook,可以在檔案寫入後自動跑指定腳本；Antigravity CLI 文件明確列出可自訂 `hooks`/`plugins`；Codex 則多半要靠 sandbox/approval 模式後接 shell 腳本,或退而求其次掛在 git pre-commit / CI。**只要平台支援 hook,強制力跟自建 Kernel 幾乎等價**——差別只在觸發時機是「工具呼叫後」還是「session 結束/commit 前」。 |
| 強制程度 | 若平台支援 hook：**接近機械強制**。若不支援：退化成 pre-commit/CI,只能擋在「進 repo 之前」,擋不住 agent 在單一 session 內反覆寫壞又自己覺得過了。 |
| ADAD 套件必須包含 | `harness/check_invariants.py`、`harness/verify_implementation.py`——**設計成獨立可執行的 CLI**,輸入 diff 或檔案路徑,輸出結構化 pass/fail JSON,不依賴任何特定平台的呼叫方式；再加每個平台的掛法說明（hook 設定範例 / pre-commit 設定範例）。 |

### 1-4｜卡住結構化回報（task_block → blocked 報告）

| | 內容 |
|---|---|
| 迴圈內 / 外 | **迴圈內**。「LLM 自陳缺規格」這個判斷只能在推論當下發生。 |
| ADAD 需求（契約） | Harness 通過後,若 agent 判斷自己缺少完成任務所需的介面/規格,要能產出一份「缺什麼」的結構化清單,而不是含糊帶過或自己亂猜實作。 |
| 自建 Kernel 做法 | 自訂 `task_block` 工具,格式自己定義,狀態機直接把 Task 凍結成 `blocked`。 |
| 現成平台做法 | 若平台支援自訂 MCP tool（Claude Code、Antigravity、多數支援 MCP 的 CLI 都可以）,可以掛一個名叫 `report_blocked` 的 MCP tool,格式跟自建版本一致,**強制力可以做到接近同等**——因為只要工具存在,agent 呼叫它就是走固定 schema,不是自由文字。這其實是本表裡少數「現成平台不會太吃虧」的項目。 |
| 強制程度 | 若肯花力氣包一個 MCP tool：**接近機械強制**。偷懶只用文字約定（要求 agent 輸出固定格式的 markdown 區塊）：**指示性,格式可能跑掉**。 |
| ADAD 套件必須包含 | 一支 `report_blocked` MCP server（最小實作,只做一件事：接收結構化理由,寫入 `.agents/tasks/<node>.task.json` 的 status 欄位）；以及備援方案 `blocked_report.schema.json` + 一支「從最終輸出文字裡萃取 blocked 區塊」的 parser 腳本,給不支援自訂工具的平台當退路。 |

### 1-5｜原子化 Checkpoint 核准

| | 內容 |
|---|---|
| 迴圈內 / 外 | **迴圈外**。四個步驟（bump_version → analyze_cascade → 標記 dirty → 寫檔）全是確定性操作,不需要模型判斷。 |
| ADAD 需求（契約） | 人類按下 CP-3 Approve 後,四步驟要嘛全部成功、要嘛全部不生效,不能卡在中間狀態。 |
| 自建 / 現成平台 | **完全無差別**——這支腳本從頭到尾不需要任何 agent 平台介入,是 ADAD 自己的 CLI 工具,人類或任何自動化都能觸發。 |
| 強制程度 | 機械強制,Kernel 選型無關。 |
| ADAD 套件必須包含 | `checkpoint.py approve`（已存在,沿用）。 |

### 1-6｜粗粒度 Permission Check

| | 內容 |
|---|---|
| 迴圈內 / 外 | 邊界模糊：判斷本身可以在迴圈外做（事前檢查 Task.status）,但「擋下工具呼叫」這個動作要嘛迴圈內攔截、要嘛乾脆不給權限。 |
| ADAD 需求（契約） | 只有 `status = assigned` 的 Task 能觸發 coding 執行；模組狀態不允許時不能核發新任務。 |
| 自建 Kernel 做法 | 狀態機在派工前查一次,查不過直接不進入下一步。 |
| 現成平台做法 | 用平台的專案級/MCP 工具白名單做「能不能碰某些資源」的權限（例如 Antigravity 的 project MCP 設定、Claude Code 的 tool allow/deny list）,但「Task.status 是否為 assigned」這種業務邏輯狀態,平台不知道,得靠 ADAD 自己的 wrapper 在呼叫 agent *之前* 先查一次、查不過就根本不啟動這次 session。 |
| 強制程度 | **機械強制,但強制點被移到「呼叫 agent 之前」**,不是迴圈內部,效果一樣,只是責任方換人。 |
| ADAD 套件必須包含 | 一支輕量 wrapper（`adad_task.py submit` 前置檢查）,在真正 spawn 任何 agent session 之前先查 Task 狀態機,查不過直接拒絕,不把請求送進 Kernel。 |

### 1-7｜Architecture Proposal 生成（Planning 呼叫,含 check_normalization）

| | 內容 |
|---|---|
| 迴圈內 / 外 | **迴圈內**,需要 LLM 推論 + 中途一次工具呼叫。 |
| ADAD 需求（契約） | 給 Requirement,產出通過重複度檢查、格式合規的 Architecture Proposal JSON。 |
| 自建 / 現成平台 | 兩者都可行,差別在「重複度檢查」這個工具呼叫要不要靠自訂 MCP tool（`check_normalization`）。現成平台一樣可以掛這支當 MCP server。格式合規則交給後置的 `validate_schema.py` 做外部驗證,不管 LLM 輸出多自由,最後都用同一支 schema validator 卡一次。 |
| 強制程度 | 輸出格式：機械強制（外部 validator）。中途要不要真的呼叫 `check_normalization`：指示性,LLM 可能跳過,只能靠事後 validator 發現漏檢查再要求補做。 |
| ADAD 套件必須包含 | `validate_schema.py`（沿用既有）；`check_normalization` 包成一支可被任何平台當 MCP tool 或 CLI 呼叫的獨立腳本。 |

---
