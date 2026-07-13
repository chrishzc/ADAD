# ADAD Architecture Source

## Metadata
- Version: 6
- Status: planning

## Environment
- State: not_required
- Services: []

## Domains

### Domain: ADAD_Workflow
- Description: ADAD (Architecture-Driven Agentic Development) 的架構與工作流核心管理工具集。

#### Subsystem: Core_Engine
- Description: 負責架構地圖讀寫、狀態推進、DAG 依賴分析與 Invariants 校驗的核心模組。

##### Module: sync_adad_assets
- Type: tool
- Observability: not_required
- Description: 以 adad_source 作為唯一可編輯來源，同步產生本 repo 的 .agents 與發佈給 adad init 的 resources 資產；Python 快取不是受管理資產，必須排除於複製與一致性比較之外。
- Source: adad_cli/sync_assets.py
- Preferred Pattern: pure_function
- Decisions:
  - 根目錄 system_map.md 是 ADAD 本體的架構 SSOT，不屬於可同步範本。
  - adad_source/agents 與 adad_source/templates 是 workflow 規則與新專案範本的唯一可編輯來源。
  - .agents 與 adad_cli/resources 是受管理產物，僅能透過本工具更新。
  - __pycache__/ 與 *.pyc 是執行期快取，不得複製、不得納入 --check 比較；--write 必須清除受管理輸出中的既有快取。
- Invariants:
  - deny_imports: [yaml]
- Verification:
  - must_have_assertions
- Algorithm:
  - 收集與比較檔案樹時，排除路徑任一層為 __pycache__ 的檔案及副檔名為 .pyc 的檔案。
  - --write 前先從受管理輸出樹移除上述快取，再只複製 canonical 的非快取檔案。
  - --check 只比較受管理檔案，Python 執行期產生的快取不得造成不一致。
  - 擴充測試，驗證 canonical 與輸出任一側出現 .pyc 時，資產檢查仍只評估受管理檔案且 --write 可清理輸出快取。
- Dependencies: []
- Input:
  - source_file: adad_cli/sync_assets.py
  - test_file: tests/test_sync_assets.py
  - allowed_symbols: [_tree_files, _compare_tree, _copy_tree, sync_assets]
  - forbidden_files: [system_map.md, adad_source, adad_cli/resources, .agents/AGENTS.md, README.md]
  - --write: flag（將唯一來源同步至所有產物）
  - --check: flag（驗證所有產物與唯一來源一致）
- Output:
  - result: object（同步或檢查結果；不一致時列出相對路徑）
- TODO:
  - [ ] 規格總覽 #50：排除並清理 Python 快取，避免同步一致性假失敗
- Checkpoint:
  - [x] CP-1-018 (validated)
  - [x] CP-3-002 (validated：生成資產快取排除)
- Complexity: medium

##### Module: read_context
- Type: tool
- Observability: not_required
- Description: 讀取單一節點最小上下文的輔助工具
- Source: adad_source/agents/skills/adad-workflow/scripts/read_context.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 執行 Rule of Two 邊界檢查；架構提案只能透過 UTF-8 JSON 檔案或 stdin 傳入，禁止 positional JSON，避免 Windows PowerShell 與其他 shell quoting 破壞內容。
- Source: adad_source/agents/skills/adad-workflow/scripts/check_normalization.py::main
- Preferred Pattern: pure_function
- Complexity: medium
- Algorithm:
  - 使用 argparse 定義 `--file <path>`；任何 positional 參數都視為已停用的危險輸入方式，輸出結構化錯誤並 exit 1。
  - 若提供 `--file`，以 strict UTF-8 讀取完整內容；否則從 stdin 讀取。stdin 為互動終端或內容空白時輸出結構化用法錯誤。
  - 將取得的文字交給 json.loads；解析失敗、檔案讀取失敗或根節點不是 object 時，都輸出單一 JSON error object 並 exit 1，不輸出 traceback。
  - 保留 name 必填與既有 ADADCore.evaluate_normalization 呼叫，不改 Rule of Two 判斷邏輯及成功輸出格式。
  - canonical SKILL 指令範例不得再出現 positional JSON，只能示範 `--file`；stdin 適用於能安全傳遞原始位元流的平台。
  - 僅修改 canonical source 與同一節點的 canonical 操作指示；生成副本由 sync_adad_assets 更新，不直接手改。
- Decisions: []
- Invariants:
  - deny_imports: [pymysql]
- Verification:
  - must_have_assertions
- Observability: not_required
- Dependencies: []
- Input:
  - target_file: adad_source/agents/skills/adad-workflow/scripts/check_normalization.py
  - allowed_symbols: [main]
  - forbidden_files: [system_map.md, adad_cli/core.py, adad_cli/sync_assets.py, adad_cli/resources, .agents, README.md]
  - proposal_file: path（CLI 旗標為 --file；strict UTF-8 JSON 檔案，可選，與 stdin 二擇一）
  - stdin: string（未提供 --file 時使用）
- Output:
  - result: object
- TODO:
  - [ ] 支持更加複雜的模糊關鍵字權重分析比對
- Checkpoint:
  - [x] CP-1-002 (validated)
  - [x] CP-2-002 (deployed)
  - [x] CP-3-001 (validated：改善 Windows quoting 輸入邊界)
  - [x] CP-3-040 (approved：停用 positional JSON，改以 --file 或 stdin 作為唯一正式輸入)

##### Module: analyze_cascade
- Type: tool
- Observability: not_required
- Description: 執行髒點級聯依賴分析的 DAG 走查工具
- Source: adad_source/agents/skills/adad-workflow/scripts/analyze_cascade.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 推進或變更模組生命週期狀態的狀態機工具
- Source: adad_source/agents/skills/adad-workflow/scripts/transit_state.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 核心引擎，提供 system_map 讀寫、DAG 依賴分析、狀態推進、Invariants/Domain 邊界檢查等共用邏輯，被本檔案登記的其餘所有工具 import 使用；本身不是獨立執行的 CLI 工具，沒有對外的輸入輸出介面。
- Source: adad_source/agents/skills/adad-workflow/scripts/adad_core.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 將 system_map.md（含 include 分區地圖）編譯為機讀 IR system_map.yaml，並執行智慧狀態合併（結構未變沿用舊狀態、結構有變標記 dirty）與 Draft Debt Ledger 偵測。
- Source: adad_source/agents/skills/adad-workflow/scripts/compile_map.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 從 system_map.yaml 匯出一份含 source_hash 的 Task 快照給 coding 端讀取；Task 與 Module 分離，可偵測架構是否在執行期間被更動過。
- Source: adad_source/agents/skills/adad-workflow/scripts/generate_task.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: Phase 1 新增模組前，查表回答「這個 Domain/Subsystem 目前該寫進哪個實體子地圖檔案」，取代 Agent 憑印象追蹤 include 鏈猜落點。
- Source: adad_source/agents/skills/adad-workflow/scripts/resolve_target_file.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 比對 system_map.md 與 system_map.yaml，產出模組完成度進度報告（completed / dirty / planned 分類統計），供人類快速掌握目前施工進度。
- Source: adad_source/agents/skills/adad-workflow/scripts/resume_analysis.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 獨立於 parse_markdown/compile_map.py 之外的第二層防線，用標準 JSON Schema（system_map.schema.json）驗證 system_map.yaml 的結構正確性；未安裝 jsonschema 套件時退回純標準庫的最小驗證器。
- Source: adad_source/agents/skills/adad-workflow/scripts/validate_schema.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
- Dependencies: []
- Input:
  - cwd_system_map_yaml: file（預設驗證 system_map.yaml 對照 system_map.schema.json）
- Output:
  - result: object
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-010 (planned)

##### Module: read_utf8_text_strict
- Type: function
- Observability: not_required
- Description: 以嚴格 UTF-8 解碼讀取架構、規格與 Task 文字，拒絕非法位元與 BOM，避免 errors=ignore 靜默遺失 SSOT 內容。
- Source: adad_source/agents/skills/adad-workflow/scripts/text_io.py::read_utf8_text_strict
- Preferred Pattern: boundary_adapter
- Complexity: low
- Decisions:
  - 檔案內容必須是無 BOM 的 UTF-8；UTF-8 BOM、UTF-16 BOM、非法位元與無法解碼內容一律明確失敗。
  - 不提供 errors=ignore 或 errors=replace 降級模式，避免架構文字在未被察覺時遺失。
  - 本節點只負責單一文字讀取邊界；各既有 reader 的採用由後續原子 Task 分別處理。
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - file_path: string
- Output:
  - text: string
- TODO:
  - [ ] 將架構與規格讀取統一為 strict UTF-8，移除 errors=ignore
- Checkpoint:
  - [ ] CP-1-039 (planned)

##### Module: write_utf8_text_atomic
- Type: function
- Observability: not_required
- Description: 以無 BOM UTF-8、LF 換行與同目錄暫存檔原子取代方式寫入架構、規格及 Task 文字，避免 Windows、macOS、Linux 換行差異或中斷寫入造成部分檔案與後續解析失敗。
- Source: adad_source/agents/skills/adad-workflow/scripts/text_io.py::write_utf8_text_atomic
- Preferred Pattern: atomic_file_writer
- Complexity: low
- Decisions:
  - 輸入文字若以 BOM 字元開頭必須明確失敗；其餘 CRLF 與 CR 一律正規化為 LF，再以 strict UTF-8 編碼，不得使用 errors=ignore 或 errors=replace。
  - 暫存檔必須建立在目標檔案的同一目錄，完整寫入並 flush 後再以 os.replace 原子取代；不得先截斷目標檔案。
  - 寫入或取代失敗時保留原目標內容並清理本次暫存檔，原始例外向上傳遞，不得留下可被誤認為正式 SSOT 的部分檔案。
  - 僅負責單一文字檔案邊界，不建立父目錄、不解析內容，也不批次更新多個檔案；既有 writers 的採用由後續原子 Task 分別處理。
- Invariants:
  - deny_imports: [subprocess]
  - deny_calls: [os.chdir]
- Verification: []
- Dependencies: []
- Input:
  - file_path: string
  - text: string
- Output:
  - written_path: string
- TODO:
  - [ ] 統一架構、規格與 Task 的跨平台 UTF-8 原子寫入邊界
- Checkpoint:
  - [ ] CP-1-041 (planned)

#### Subsystem: Enforcement_Gates
- Description: 機械強制執行層——commit 階段與 agent 工具呼叫前後的閘門、驗證與 Task 生命週期控管，把 AGENTS.md 的軟性規則轉成硬規則。

##### Module: adad_pre_commit
- Type: tool
- Observability: not_required
- Description: Git pre-commit／CI guardrail，將 AGENTS.md 的軟規則轉為機械硬閘門：本機讀取 staged diff；CI pull request 比對明確 base branch；CI push 在 GITHUB_BASE_REF 空白時安全回退至 HEAD~1，禁止組成無效的 origin/ revision。
- Source: adad_source/agents/skills/adad-workflow/scripts/adad_pre_commit.py
- Preferred Pattern: none
- Decisions:
  - GITHUB_BASE_REF 空字串等同未提供；push 事件使用 HEAD~1，pull request 才使用 origin/<base>。
- Invariants: []
- Verification: []
- Observability: not_required
- Dependencies: [adad_core]
- Input:
  - git_change_set: file（本機為 staged diff；CI 為 base revision 到 HEAD）
  - ci_environment: object（CI、GITHUB_BASE_REF；空白 base 必須視為未提供）
- Output:
  - errors: array
  - warnings: array
- Algorithm:
  - 非 CI 環境使用 git diff --cached。
  - CI 且 GITHUB_BASE_REF 為非空白值時，使用 origin/<base> 到 HEAD。
  - CI 且 GITHUB_BASE_REF 缺少或為空白值時，使用 HEAD~1 到 HEAD。
- TODO:
  - [ ] 補齊架構地圖登記（本次新增，尚未走完 CP-1/CP-2 審查）
- Checkpoint:
  - [ ] CP-1-011 (planned)
  - [x] CP-3-003 (validated：CI push 空 base fallback)

##### Module: adad_pretooluse_gate
- Type: tool
- Observability: not_required
- Description: 掛在 Claude Code 的 PreToolUse hook 上，在 Edit/Write/MultiEdit 工具呼叫「執行前」攔截：目標檔案對應的 Task 快照狀態不允許編輯時直接 exit 2 擋下，避免 agent 白花 token 寫出會被丟棄的程式碼；無法判斷的情況一律放行，不取代 pre-commit/CI 的完整檢查。
- Source: adad_source/agents/skills/adad-workflow/scripts/adad_pretooluse_gate.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: Task 快照生命週期操作：submit（coding 端自行呼叫，就地重跑 check_invariants + verify_implementation 都過才允許轉 submitted）、approve/reject（僅限人類在真正互動終端機執行，非 tty 一律拒絕，防止 Agent 透過工具呼叫自我核准）。
- Source: adad_source/agents/skills/adad-workflow/scripts/adad_task.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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

##### Module: check_source_binding
- Type: tool
- Observability: not_required
- Description: 檢查 Module 的 Source 綁定是否存在重複、整檔與逐函式混用、或同一函式多重歸屬等歧義；歧義會使後續 Gate 無法可靠反查模組，因此編譯與 commit 前皆須阻斷。
- Source: adad_source/agents/skills/adad-workflow/scripts/check_source_binding.py
- Preferred Pattern: pure_function
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
- Dependencies: [adad_core]
- Input:
  - cwd_system_map_yaml: file（無 CLI 參數，掃描整份 system_map.yaml）
- Output:
  - passed: boolean
  - violations: array
  - unbound: array
- TODO: []
- Checkpoint:
  - [ ] CP-1-017 (planned)

##### Module: check_domain_boundary
- Type: tool
- Observability: not_required
- Description: 檢查模組是否只依賴同一 Domain 內的模組，除非該 Domain 已用 Allowed Dependencies 明確宣告允許跨 Domain 依賴。
- Source: adad_source/agents/skills/adad-workflow/scripts/check_domain_boundary.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 校驗指定節點的實作是否違反其宣告的 Invariants（例如 deny_imports）。
- Source: adad_source/agents/skills/adad-workflow/scripts/check_invariants.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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
- Observability: not_required
- Description: 校驗指定節點的實作是否符合其宣告的 Verification 條件（例如 must_have_assertions、結構化 case）。
- Source: adad_source/agents/skills/adad-workflow/scripts/verify_implementation.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
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

<!-- include docs/domains/adad_roadmap.md -->
