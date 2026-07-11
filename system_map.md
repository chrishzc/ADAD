# ADAD Architecture Source

## Metadata
- Version: 1
- Status: planning

## Domains

### Domain: ADAD_Workflow
- Description: ADAD (Architecture-Driven Agentic Development) 的架構與工作流核心管理工具集。

#### Subsystem: Core_Engine
- Description: 負責架構地圖讀寫、狀態推進、DAG 依賴分析與 Invariants 校驗的核心模組。

##### Module: read_context
- Type: tool
- Description: 讀取單一節點最小上下文的輔助工具
- Source: .agents/skills/adad-workflow/scripts/read_context.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - node_name: string
- Output:
  - context: object
- TODO:
  - [ ] 補齊與其他 UI 工具串接的 context 回傳欄位
- Checkpoint:
  - [x] CP-1-001 (validated)
  - [x] CP-2-001 (deployed)

##### Module: check_normalization
- Type: tool
- Description: 執行 Rule of Two 邊界檢查，防範重複設計的工具
- Source: .agents/skills/adad-workflow/scripts/check_normalization.py
- Preferred Pattern: pure_function
- Decisions: []
- Invariants:
  - deny_imports: [pymysql]
- Verification:
  - must_have_assertions
- Dependencies: []
- Input:
  - proposed_function: string
- Output:
  - result: object
- TODO:
  - [ ] 支持更加複雜的模糊關鍵字權重分析比對
- Checkpoint:
  - [x] CP-1-002 (validated)
  - [x] CP-2-002 (deployed)

##### Module: analyze_cascade
- Type: tool
- Description: 執行髒點級聯依賴分析的 DAG 走查工具
- Source: .agents/skills/adad-workflow/scripts/analyze_cascade.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - changed_node_name: string
- Output:
  - dirty_nodes: array
- TODO:
  - [ ] 優化多重循環依賴的死循環防範機制
- Checkpoint:
  - [x] CP-1-003 (validated)
  - [x] CP-2-003 (deployed)

##### Module: transit_state
- Type: tool
- Description: 推進或變更模組生命週期狀態的狀態機工具
- Source: .agents/skills/adad-workflow/scripts/transit_state.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - node_name: string
  - next_state: string
- Output:
  - result: object
- TODO:
  - [ ] 結合 Git Hook 自動觸發狀態轉移
- Checkpoint:
  - [x] CP-1-004 (validated)
  - [x] CP-2-004 (deployed)

##### Module: adad_core
- Type: library
- Description: 核心引擎，提供 system_map 讀寫、DAG 依賴分析、狀態推進、Invariants/Domain 邊界檢查等共用邏輯，被本檔案登記的其餘所有工具 import 使用；本身不是獨立執行的 CLI 工具，沒有對外的輸入輸出介面。
- Source: .agents/skills/adad-workflow/scripts/adad_core.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input: {}
- Output: {}
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
  - [ ] 依賴此檔案的腳本改動共用邏輯時，目前沒有自動化的跨檔案影響分析
- Checkpoint:
  - [ ] CP-1-005 (planned)

##### Module: compile_map
- Type: tool
- Description: 將 system_map.md（含 include 分區地圖）編譯為機讀 IR system_map.yaml，並執行智慧狀態合併（結構未變沿用舊狀態、結構有變標記 dirty）與 Draft Debt Ledger 偵測。
- Source: .agents/skills/adad-workflow/scripts/compile_map.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - cwd_system_map_md: file（無 CLI 參數，讀取當前目錄的 system_map.md）
- Output:
  - result: object
  - system_map.yaml: file（編譯副作用，非回傳值）
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-006 (planned)

##### Module: generate_task
- Type: tool
- Description: 從 system_map.yaml 匯出一份含 source_hash 的 Task 快照給 coding 端讀取；Task 與 Module 分離，可偵測架構是否在執行期間被更動過。
- Source: .agents/skills/adad-workflow/scripts/generate_task.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - node_name: string
  - --force: flag（選填，作廢並重新核發既有任務）
- Output:
  - result: object
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-007 (planned)

##### Module: resolve_target_file
- Type: tool
- Description: Phase 1 新增模組前，查表回答「這個 Domain/Subsystem 目前該寫進哪個實體子地圖檔案」，取代 Agent 憑印象追蹤 include 鏈猜落點。
- Source: .agents/skills/adad-workflow/scripts/resolve_target_file.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - domain: string
  - subsystem: string（選填）
- Output:
  - target_file: string
  - domain_exists: boolean
  - subsystem_exists: boolean
  - hint: string
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-008 (planned)

##### Module: resume_analysis
- Type: tool
- Description: 比對 system_map.md 與 system_map.yaml，產出模組完成度進度報告（completed / dirty / planned 分類統計），供人類快速掌握目前施工進度。
- Source: .agents/skills/adad-workflow/scripts/resume_analysis.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - cwd_system_map_md: file（無 CLI 參數，讀取當前目錄檔案）
- Output:
  - report: text（stdout 輸出）
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-009 (planned)

##### Module: validate_schema
- Type: tool
- Description: 獨立於 parse_markdown/compile_map.py 之外的第二層防線，用標準 JSON Schema（system_map.schema.json）驗證 system_map.yaml 的結構正確性；未安裝 jsonschema 套件時退回純標準庫的最小驗證器。
- Source: .agents/skills/adad-workflow/scripts/validate_schema.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - cwd_system_map_yaml: file（預設驗證 system_map.yaml 對照 system_map.schema.json）
- Output:
  - result: object
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-010 (planned)

#### Subsystem: Enforcement_Gates
- Description: 機械強制執行層——commit 階段與 agent 工具呼叫前後的閘門、驗證與 Task 生命週期控管，把 AGENTS.md 的軟性規則轉成硬規則。

##### Module: adad_pre_commit
- Type: tool
- Description: Git pre-commit hook，將 AGENTS.md 的軟規則轉為 commit 階段的機械硬閘門：Staleness 阻斷、狀態門禁、原子範圍警告、Invariants/Verification 校驗、跨 Domain 依賴邊界、未登記函式掃描、懸空依賴、模組落點校驗。
- Source: .agents/skills/adad-workflow/scripts/adad_pre_commit.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - git_staged_files: file（讀取 git staged diff，無 CLI 參數）
- Output:
  - errors: array
  - warnings: array
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-011 (planned)

##### Module: adad_pretooluse_gate
- Type: tool
- Description: 掛在 Claude Code 的 PreToolUse hook 上，在 Edit/Write/MultiEdit 工具呼叫「執行前」攔截：目標檔案對應的 Task 快照狀態不允許編輯時直接 exit 2 擋下，避免 agent 白花 token 寫出會被丟棄的程式碼；無法判斷的情況一律放行，不取代 pre-commit/CI 的完整檢查。
- Source: .agents/skills/adad-workflow/scripts/adad_pretooluse_gate.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - stdin: object（Claude Code hook payload，含 tool_input.file_path）
- Output:
  - exit_code: string（0=放行；2=阻擋，原因寫在 stderr）
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-012 (planned)

##### Module: adad_task
- Type: tool
- Description: Task 快照生命週期操作：submit（coding 端自行呼叫，就地重跑 check_invariants + verify_implementation 都過才允許轉 submitted）、approve/reject（僅限人類在真正互動終端機執行，非 tty 一律拒絕，防止 Agent 透過工具呼叫自我核准）。
- Source: .agents/skills/adad-workflow/scripts/adad_task.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - command: string（submit｜approve｜reject）
  - node_name: string
  - extra: string（依 command 而定：submit 選填 file_path；approve 為 task_id 後6碼；reject 為駁回原因）
- Output:
  - result: object
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-013 (planned)

##### Module: check_domain_boundary
- Type: tool
- Description: 檢查模組是否只依賴同一 Domain 內的模組，除非該 Domain 已用 Allowed Dependencies 明確宣告允許跨 Domain 依賴。
- Source: .agents/skills/adad-workflow/scripts/check_domain_boundary.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - cwd_system_map_yaml: file（無 CLI 參數，掃描整份 system_map.yaml）
- Output:
  - passed: boolean
  - violations: array
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-014 (planned)

##### Module: check_invariants
- Type: tool
- Description: 校驗指定節點的實作是否違反其宣告的 Invariants（例如 deny_imports）。
- Source: .agents/skills/adad-workflow/scripts/check_invariants.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - node_name: string
  - file_path: string（選填）
- Output:
  - success: boolean
  - result: object
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-015 (planned)

##### Module: verify_implementation
- Type: tool
- Description: 校驗指定節點的實作是否符合其宣告的 Verification 條件（例如 must_have_assertions、結構化 case）。
- Source: .agents/skills/adad-workflow/scripts/verify_implementation.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [adad_core]
- Input:
  - node_name: string
  - file_path: string（選填）
- Output:
  - success: boolean
  - result: object
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-016 (planned)
 
