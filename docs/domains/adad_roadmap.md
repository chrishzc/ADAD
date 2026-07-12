### Domain: ADAD_Roadmap
- Description: 規格總覽中已完成能力與後續演進工作的可施工架構地圖。
- Allowed Dependencies: [ADAD_Workflow]

#### Subsystem: Completed_Baseline
- Description: 已落地能力的驗證基線。

##### Module: architecture_inventory
- Type: documentation
- Observability: not_required
- Description: 已完成既有 workflow 腳本的架構登記與 Domain/Subsystem 分層（規格總覽 #4）。
- Source: system_map.md
- Preferred Pattern: ssot_document
- Decisions: [以 system_map.md 與 system_map.yaml 作為架構盤點證據]
- Invariants: []
- Verification: []
- Dependencies: []
- Input: {}
- Output:
  - inventory: system_map.yaml
- TODO:
  - [x] 規格總覽 #4：既有 workflow 腳本已登記
- Checkpoint:
  - [x] CP-1-019 (validated)
  - [x] CP-2-019 (deployed)

##### Module: automated_test_suite
- Type: test_suite
- Observability: not_required
- Description: 已建立 pytest 黑箱測試與 dev extra，涵蓋既有 workflow 工具（規格總覽 #5）。
- Source: pyproject.toml
- Preferred Pattern: black_box_test
- Decisions: [測試依賴透過 .venv 的 dev extra 安裝]
- Invariants: []
- Verification: []
- Dependencies: []
- Input: {}
- Output:
  - test_result: report
- TODO:
  - [x] 規格總覽 #5：pytest 測試套件已建立
- Checkpoint:
  - [x] CP-1-020 (validated)
  - [x] CP-2-020 (deployed)

#### Subsystem: Contract_Evolution
- Description: Schema、Task 與執行契約缺口的可獨立施工節點。

##### Module: environment_contract
- Type: schema
- Observability: not_required
- Description: 將 environment 宣告納入 Markdown parser、IR schema 與編譯 gate（#3）。
- Source: adad_cli/workflow/environment_contract.py
- Preferred Pattern: schema_first
- Decisions: [純 CLI 專案必須明確宣告 not_required]
- Invariants: []
- Verification: []
- Dependencies: [compile_map, validate_schema]
- Input:
  - environment: object
- Output:
  - validated_environment: object
- TODO:
  - [ ] 規格總覽 #3：環境宣告機械化
- Checkpoint:
  - [ ] CP-1-021 (planned)

##### Module: module_contract_schema
- Type: schema
- Observability: not_required
- Description: 補強模組的 Pattern、Complexity/Algorithm、Invariants、Verification、生命週期與觀測契約（#9-16）。
- Source: adad_cli/workflow/module_contract_schema.py
- Preferred Pattern: schema_first
- Decisions: [高複雜度模組必須有 Algorithm；觀測契約不與 description 混用]
- Invariants: []
- Verification: []
- Dependencies: [compile_map, validate_schema]
- Input:
  - module_contract: object
- Output:
  - normalized_module_contract: object
- TODO:
  - [ ] 規格總覽 #9-16：補齊模組契約欄位與驗證
- Checkpoint:
  - [ ] CP-1-022 (planned)

##### Module: rollback_and_concurrency_contract
- Type: schema
- Observability: not_required
- Description: 宣告 Task 重試失敗後的 rollback 策略與平行修改衝突處理（#17-18）。
- Source: adad_cli/workflow/execution_policy.py
- Preferred Pattern: explicit_contract
- Decisions: [先宣告 rollback 與鎖定邊界，再導入執行期機制]
- Invariants: []
- Verification: []
- Dependencies: [adad_task]
- Input:
  - execution_policy: object
- Output:
  - guarded_execution_policy: object
- TODO:
  - [ ] 規格總覽 #17-18：失敗清理與併發衝突契約
- Checkpoint:
  - [ ] CP-1-023 (planned)

##### Module: task_contract_schema
- Type: schema
- Observability: not_required
- Description: 聚合 #19～#23 的原子契約驗證結果，產生完整的 per-task contract 快照。
- Source: adad_cli/workflow/task_contract_schema.py::validate_task_contract
- Preferred Pattern: thin_orchestrator
- Complexity: low
- Decisions: [Preconditions/Postconditions 擴充 Verification case，不建立重複欄位]
- Invariants: []
- Verification: []
- Dependencies: [generate_task, task_semantic_contract, task_non_goals_contract, task_verification_conditions, task_assumptions_contract, task_input_json_schema, task_output_json_schema]
- Input:
  - task_contract: object
- Output:
  - validated_task_contract: object
- TODO:
  - [ ] 規格總覽 #19-23：Task 規格化
- Checkpoint:
  - [x] CP-1-024 (validated)

##### Module: task_semantic_contract
- Type: schema
- Observability: not_required
- Description: 將 Task 的自然語言 description 升級為可驗證的結構化 Semantic Contract（#19）。
- Source: adad_cli/workflow/task_contract_schema.py::validate_semantic_contract
- Preferred Pattern: schema_first
- Complexity: low
- Decisions: [Semantic Contract 必須保留人類可讀摘要，並提供機器可驗證的目標與完成條件]
- Invariants: []
- Verification: []
- Dependencies: [validate_schema]
- Input:
  - description: string
- Output:
  - semantic_contract: object
- TODO:
  - [ ] 規格總覽 #19：結構化 Semantic Contract
- Checkpoint:
  - [x] CP-1-024-A (validated)

##### Module: task_non_goals_contract
- Type: schema
- Observability: not_required
- Description: 為 Task 增加明確的 Non-goal 清單，限制 Agent 不得自行擴張的工作範圍（#20）。
- Source: adad_cli/workflow/task_contract_schema.py::validate_non_goals
- Preferred Pattern: explicit_contract
- Complexity: low
- Decisions: [空陣列代表已明確確認沒有額外 Non-goal，不得以缺少欄位代替]
- Invariants: []
- Verification: []
- Dependencies: [validate_schema]
- Input:
  - non_goals: array
- Output:
  - validated_non_goals: array
- TODO:
  - [ ] 規格總覽 #20：Non-goal 契約
- Checkpoint:
  - [x] CP-1-024-B (validated)

##### Module: task_verification_conditions
- Type: schema
- Observability: not_required
- Description: 以既有 Verification case 的 input、expect 與 expect_exception 表達 Preconditions/Postconditions，不新增重複欄位（#21）。
- Source: adad_cli/workflow/task_contract_schema.py::validate_verification_conditions
- Preferred Pattern: extend_existing_contract
- Complexity: low
- Decisions: [Preconditions 由 case input 與前置狀態表達；Postconditions 由 expect 或 expect_exception 表達]
- Invariants: []
- Verification: []
- Dependencies: [verify_implementation]
- Input:
  - verification_cases: array
- Output:
  - validated_verification_cases: array
- TODO:
  - [ ] 規格總覽 #21：以前後條件強化 Verification case
- Checkpoint:
  - [x] CP-1-024-C (validated)

##### Module: task_assumptions_contract
- Type: schema
- Observability: not_required
- Description: 為 Task 增加可快照、可審核的 Assumptions 清單（#22）。
- Source: adad_cli/workflow/task_contract_schema.py::validate_assumptions
- Preferred Pattern: explicit_contract
- Complexity: low
- Decisions: [Assumption 只描述 Task 成立所依賴的外部事實，不得重複 Preconditions 或 Non-goal]
- Invariants: []
- Verification: []
- Dependencies: [validate_schema]
- Input:
  - assumptions: array
- Output:
  - validated_assumptions: array
- TODO:
  - [ ] 規格總覽 #22：Assumptions 契約
- Checkpoint:
  - [x] CP-1-024-D (validated)

##### Module: task_input_json_schema
- Type: schema
- Observability: not_required
- Description: 將既有通用 schema 驗證能力套用至 per-task Input JSON Schema（#23）。
- Source: adad_cli/workflow/task_contract_schema.py::validate_task_input_schema
- Preferred Pattern: schema_first
- Complexity: low
- Decisions: [沿用 validate_schema 的支援子集與錯誤格式，不建立第二套 JSON Schema 引擎]
- Invariants: []
- Verification: []
- Dependencies: [validate_schema]
- Input:
  - input_schema: object
- Output:
  - validated_input_schema: object
- TODO:
  - [ ] 規格總覽 #23-A：per-task Input JSON Schema
- Checkpoint:
  - [x] CP-1-024-E (validated)

##### Module: task_output_json_schema
- Type: schema
- Observability: not_required
- Description: 將既有通用 schema 驗證能力套用至 per-task Output JSON Schema（#23）。
- Source: adad_cli/workflow/task_contract_schema.py::validate_task_output_schema
- Preferred Pattern: schema_first
- Complexity: low
- Decisions: [沿用 validate_schema 的支援子集與錯誤格式，不建立第二套 JSON Schema 引擎]
- Invariants: []
- Verification: []
- Dependencies: [validate_schema]
- Input:
  - output_schema: object
- Output:
  - validated_output_schema: object
- TODO:
  - [ ] 規格總覽 #23-B：per-task Output JSON Schema
- Checkpoint:
  - [x] CP-1-024-F (validated)

##### Module: execution_contracts
- Type: schema
- Observability: not_required
- Description: 宣告並逐步驗證 side effect、determinism、idempotency、state change、purity、resource 與 concurrency 契約（#24-32）。
- Source: adad_cli/workflow/execution_contracts.py
- Preferred Pattern: executable_contract
- Decisions: [Exception verification 併入 case；purity 以 Pattern 的 machine-readable flag 表示]
- Invariants: []
- Verification: []
- Dependencies: [check_invariants, verify_implementation]
- Input:
  - execution_contract: object
- Output:
  - execution_verdict: object
- TODO:
  - [ ] 規格總覽 #24-32：執行、例外與資源契約
- Checkpoint:
  - [ ] CP-1-025 (planned)

##### Module: dependency_and_retry_contract
- Type: schema
- Observability: not_required
- Description: 宣告相依模組的契約摘要與逐 Task retry budget，並控制 Task 快照的 context 膨脹（#33-35）。
- Source: adad_cli/workflow/dependency_contract.py
- Preferred Pattern: bounded_context
- Decisions: [Dependency version 暫不導入，待確認實際需求]
- Invariants: []
- Verification: []
- Dependencies: [generate_task, adad_task]
- Input:
  - dependency_contract: object
- Output:
  - bounded_dependency_context: object
- TODO:
  - [ ] 規格總覽 #33-35：相依契約與重試預算
- Checkpoint:
  - [ ] CP-1-026 (planned)

##### Module: verification_strategy
- Type: verifier
- Observability: not_required
- Description: 擴充 case 的 boundary、invalid input、exception、fixture、determinism 與 golden/property 驗證策略（#36-39）。
- Source: adad_cli/workflow/verification_strategy.py
- Preferred Pattern: executable_specification
- Decisions: [Coverage gate 列為 P2，先強化 case 覆蓋規則]
- Invariants: []
- Verification: []
- Dependencies: [verify_implementation]
- Input:
  - verification_plan: object
- Output:
  - verification_report: object
- TODO:
  - [ ] 規格總覽 #36-39：驗證策略演進
- Checkpoint:
  - [ ] CP-1-027 (planned)

##### Module: task_readiness_and_audit
- Type: gate
- Observability: not_required
- Description: 將 required field/readiness score、模型可執行的複雜度預算、Task 分解門禁與可追溯審批留痕納入核發及 CP-2 流程（#40-42、#49）。
- Source: adad_cli/workflow/task_readiness.py
- Preferred Pattern: fail_fast_gate
- Complexity: medium
- Decisions:
  - Algorithm gate 已由 compile_map 實作；本節點補齊 readiness、complexity budget 與 audit 欄位規格。
  - low 可直接核發；medium 必須有完整 Algorithm、邊界與 Verification；high 預設阻斷並要求拆分。
  - high 只有在人類指定高能力模型、記錄不可再拆原因並核准 override 時才能例外核發。
- Invariants: []
- Verification: []
- Dependencies: [generate_task, adad_task, compile_map, task_complexity_policy]
- Input:
  - task_snapshot: object
- Output:
  - readiness_result: object
  - audit_record: object
- TODO:
  - [ ] 規格總覽 #40、#42：Readiness 與 audit 契約
  - [x] 規格總覽 #41：high complexity 缺 Algorithm 已阻斷編譯
  - [x] 規格總覽 #49：Task 核發門禁已套用 complexity policy；high 必須拆分，人工 override 待後續契約。
- Checkpoint:
  - [ ] CP-1-028 (planned)

##### Module: task_complexity_policy
- Type: function
- Observability: not_required
- Description: 以純函式判定施工 Task 應直接核發、補齊規格或拆分；已接線 generate_task，high complexity 一律要求拆分，人工 override 待後續契約實作（#49）。
- Source: adad_source/agents/skills/adad-workflow/scripts/task_complexity.py::evaluate_task_complexity
- Preferred Pattern: pure_function
- Complexity: medium
- Algorithm:
  - 將 complexity 與 model_capability 正規化為小寫，僅接受 complexity=[low, medium, high] 與 model_capability=[low, standard, high]；非法值拋出 ValueError。
  - complexity=low 時回傳 `issue`。
  - complexity=medium 時，只有 has_algorithm、has_boundaries、has_verification 全為 true 才回傳 `issue`，否則回傳 `complete_spec`。
  - complexity=high 時，只有 model_capability=high、override_approved=true 且 override_reason 去除空白後非空，才回傳 `issue_override`。
  - 其餘 high 情況一律回傳 `split`；不得讀寫檔案、環境變數、全域狀態或呼叫外部服務。
- Decisions:
  - 此 Task 不修改 generate_task、adad_core、system_map、文件、測試或其他節點。
  - `high` 的人工例外必須同時具備高能力模型、核准旗標與不可再拆原因，缺一不可。
- Invariants:
  - deny_imports: [yaml, subprocess, os]
- Verification:
  - case: {"input": {"complexity": "low", "has_algorithm": false, "has_boundaries": false, "has_verification": false, "model_capability": "low", "override_approved": false, "override_reason": ""}, "expect": "issue"}
  - case: {"input": {"complexity": "medium", "has_algorithm": true, "has_boundaries": true, "has_verification": true, "model_capability": "standard", "override_approved": false, "override_reason": ""}, "expect": "issue"}
  - case: {"input": {"complexity": "medium", "has_algorithm": true, "has_boundaries": true, "has_verification": false, "model_capability": "standard", "override_approved": false, "override_reason": ""}, "expect": "complete_spec"}
  - case: {"input": {"complexity": "high", "has_algorithm": true, "has_boundaries": true, "has_verification": true, "model_capability": "high", "override_approved": false, "override_reason": ""}, "expect": "split"}
  - case: {"input": {"complexity": "high", "has_algorithm": true, "has_boundaries": true, "has_verification": true, "model_capability": "high", "override_approved": true, "override_reason": "atomic external transaction"}, "expect": "issue_override"}
  - case: {"input": {"complexity": "high", "has_algorithm": true, "has_boundaries": true, "has_verification": true, "model_capability": "standard", "override_approved": true, "override_reason": "atomic external transaction"}, "expect": "split"}
- Dependencies: []
- Input:
  - target_file: adad_source/agents/skills/adad-workflow/scripts/task_complexity.py
  - legacy_file: adad_cli/task_complexity.py
  - allowed_symbols: [evaluate_task_complexity]
  - forbidden_files: [adad_cli/core.py, adad_cli/sync_assets.py, system_map.md, tests, README.md]
  - complexity: string
  - has_algorithm: boolean
  - has_boundaries: boolean
  - has_verification: boolean
  - model_capability: string
  - override_approved: boolean
  - override_reason: string
- Output:
  - decision: string
- TODO:
  - [ ] 規格總覽 #49 第一階段：實作純函式複雜度決策矩陣
- Checkpoint:
  - [x] CP-1-037 (validated)

##### Module: context_policy
- Type: policy
- Observability: not_required
- Description: 宣告 required/forbidden context、priority 與來源，並讓 Task 快照遵循裁剪策略（#43-47）。
- Source: adad_cli/workflow/context_policy.py
- Preferred Pattern: least_context
- Decisions: [Context budget 屬 Kernel 整合追蹤項，不與 ADAD schema 強耦合]
- Invariants: []
- Verification: []
- Dependencies: [generate_task, read_context]
- Input:
  - context_policy: object
- Output:
  - curated_context: object
- TODO:
  - [ ] 規格總覽 #43-47：Context 契約
- Checkpoint:
  - [ ] CP-1-029 (planned)

#### Subsystem: Product_Delivery
- Description: 文件、發佈、CI 與專案環境的一致性交付。

##### Module: documentation_alignment
- Type: documentation
- Observability: not_required
- Description: 對齊 README 的 CLI 工具表與 Phase/Checkpoint 文件，使其反映 Task 快照工作流（#1-2）。
- Source: README.md
- Preferred Pattern: documentation_as_contract
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: [generate_task, adad_task, check_domain_boundary]
- Input: {}
- Output:
  - user_documentation: markdown
- TODO:
  - [ ] 規格總覽 #1-2：README 對齊
- Checkpoint:
  - [ ] CP-1-030 (planned)

##### Module: continuous_integration
- Type: pipeline
- Observability: not_required
- Description: 在 push 與 pull request 執行架構編譯、資產同步檢查、ADAD gate 與 pytest（#6）。
- Source: .github/workflows/verify.yml
- Preferred Pattern: continuous_verification
- Decisions: [CI 必須先驗證 generated assets 與 adad_source 一致]
- Invariants: []
- Verification: []
- Dependencies: [sync_adad_assets, adad_pre_commit]
- Input:
  - git_revision: string
- Output:
  - check_results: report
- TODO:
  - [ ] 規格總覽 #6：CI/CD
- Checkpoint:
  - [ ] CP-1-031 (planned)

##### Module: release_changelog
- Type: documentation
- Observability: not_required
- Description: 以 CHANGELOG 維護版本化改善紀錄，取代 README 尾端長篇變更文字（#7）。
- Source: CHANGELOG.md
- Preferred Pattern: keep_a_changelog
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - release_changes: array
- Output:
  - changelog_entry: markdown
- TODO:
  - [ ] 規格總覽 #7：版本化變更紀錄
- Checkpoint:
  - [ ] CP-1-032 (planned)

##### Module: project_venv_python
- Type: function
- Observability: not_required
- Description: 依專案根目錄與作業系統決定唯一受管理的 `.venv` Python 直譯器路徑（#48）。
- Source: adad_cli/core.py::_project_venv_python
- Preferred Pattern: pure_function
- Complexity: low
- Decisions: [不讀取 shell PATH；`.venv` 是唯一受管理的環境名稱]
- Invariants:
  - deny_imports: [virtualenv]
- Verification: []
- Dependencies: []
- Input:
  - project_root: path
- Output:
  - python_path: path
- TODO:
  - [ ] 規格總覽 #48-1：解析專案 `.venv` 直譯器路徑
- Checkpoint:
  - [x] CP-1-033-A (validated)

##### Module: init_project_virtual_environment
- Type: lifecycle
- Observability: not_required
- Description: `adad init` 編排已拆分的 `.venv` 建立與 pre-commit hook 寫入節點（#48）。
- Source: adad_cli/core.py::init_project
- Preferred Pattern: thin_orchestrator
- Complexity: low
- Decisions: [本 repo 已手動完成單一 .venv 整理；本節點只修正 CLI 的未來 init 行為, 舊 venv 可能含使用者資料，遷移採提示優先]
- Invariants:
  - deny_imports: [virtualenv]
- Verification: []
- Dependencies: [ensure_project_virtual_environment, write_project_pre_commit_hook]
- Input:
  - project_root: path
  - agents: array
- Output:
  - environment_status: object
- TODO:
  - [ ] 規格總覽 #48-2：初始化唯一 `.venv` 與 hook
- Checkpoint:
  - [x] CP-1-033-B (validated)
  - [x] CP-3-048-F (validated)

##### Module: ensure_project_virtual_environment
- Type: function
- Observability: not_required
- Description: 建立或保留專案唯一受管理的 `.venv`，舊 `venv` 僅提示而不搬移或刪除（#48）。
- Source: adad_cli/core.py::_ensure_project_virtual_environment
- Preferred Pattern: idempotent_resource
- Complexity: low
- Decisions: [舊 venv 可能含使用者資料，遷移採提示優先]
- Invariants:
  - deny_imports: [virtualenv]
- Verification: []
- Dependencies: []
- Input:
  - project_root: path
- Output:
  - environment_status: object
- TODO:
  - [ ] 規格總覽 #48-2A：建立或保留唯一 `.venv`
- Checkpoint:
  - [x] CP-3-048-E (validated)

##### Module: write_project_pre_commit_hook
- Type: function
- Observability: not_required
- Description: 使用專案 `.venv` 直譯器寫入 pre-commit hook，供 init 與 upgrade 共用（#48）。
- Source: adad_cli/core.py::_write_project_pre_commit_hook
- Preferred Pattern: shared_resource_writer
- Complexity: low
- Decisions: [Rule of Two 要求 init 與 upgrade 共用相同 hook 寫入邏輯]
- Invariants:
  - deny_imports: [virtualenv]
- Verification: []
- Dependencies: [project_venv_python]
- Input:
  - project_root: path
  - hook_src: path
- Output:
  - hook_status: object
- TODO:
  - [ ] 規格總覽 #48-2B：以專案 `.venv` 寫入 hook
- Checkpoint:
  - [x] CP-3-048-A (validated)

##### Module: upgrade_project_virtual_environment
- Type: lifecycle
- Observability: not_required
- Description: `adad upgrade` 僅在 `.venv` 存在時委派共享節點更新 pre-commit hook（#48）。
- Source: adad_cli/core.py::upgrade_project
- Preferred Pattern: thin_orchestrator
- Complexity: low
- Decisions: [upgrade 不得以隱含方式建立虛擬環境]
- Invariants:
  - deny_imports: [virtualenv]
- Verification: []
- Dependencies: [write_project_pre_commit_hook]
- Input:
  - project_root: path
  - agents: array
- Output:
  - environment_status: object
- TODO:
  - [ ] 規格總覽 #48-3：升級時重寫既有 `.venv` hook
- Checkpoint:
  - [x] CP-1-033-C (validated)
  - [x] CP-3-048-B (validated)

##### Module: remove_project_virtual_environment
- Type: function
- Observability: not_required
- Description: 只移除專案受管理的 `.venv`；舊 `venv` 保留並提示人工處理（#48）。
- Source: adad_cli/core.py::_remove_project_virtual_environment
- Preferred Pattern: safe_cleanup
- Complexity: low
- Decisions: [舊 venv 可能含使用者資料，因此禁止破壞性自動清理]
- Invariants:
  - deny_imports: [virtualenv]
- Verification: []
- Dependencies: []
- Input:
  - project_root: path
- Output:
  - environment_status: object
- TODO:
  - [ ] 規格總覽 #48-4A：安全移除唯一 `.venv`
- Checkpoint:
  - [x] CP-3-048-C (validated)

##### Module: clean_project_virtual_environment
- Type: lifecycle
- Observability: not_required
- Description: `adad remove` 委派安全清理節點處理 `.venv`，並保留其他既有清理職責（#48）。
- Source: adad_cli/core.py::clean_project
- Preferred Pattern: thin_orchestrator
- Complexity: low
- Decisions: [舊 venv 可能含使用者資料，因此禁止破壞性自動清理]
- Invariants:
  - deny_imports: [virtualenv]
- Verification: []
- Dependencies: [remove_project_virtual_environment]
- Input:
  - project_root: path
  - purge_docs: boolean
- Output:
  - environment_status: object
- TODO:
  - [ ] 規格總覽 #48-4：安全清理唯一 `.venv`
- Checkpoint:
  - [x] CP-1-033-D (validated)
  - [x] CP-3-048-D (validated)

#### Subsystem: Platform_Integration
- Description: 將跨平台指示與平台能力降級情況變成可追蹤的產品資產。

##### Module: blocked_task_reporting
- Type: integration
- Observability: not_required
- Description: 提供 task_block 到 blocked 報告的結構化 MCP 與文字備援流程（規格能力 1-4）。
- Source: adad_cli/integrations/blocked_reporting.py
- Preferred Pattern: structured_failure
- Decisions: [不支援自訂工具的平台使用 schema 加文字擷取作為降級方案]
- Invariants: []
- Verification: []
- Dependencies: [adad_task]
- Input:
  - blocked_reason: object
- Output:
  - blocked_task: object
- TODO:
  - [ ] 規格能力 1-4：結構化 blocked 回報
- Checkpoint:
  - [ ] CP-1-034 (planned)

##### Module: platform_instruction_renderer
- Type: generator
- Observability: not_required
- Description: 從單一 instruction source 產生 Claude、Antigravity 與 Codex 的平台格式指示檔（規格第 2 節）。
- Source: adad_cli/platform_instructions.py
- Preferred Pattern: generate_from_ssot
- Decisions: [平台格式不同，但讀取邊界、blocked 格式與 harness 時機必須語意一致]
- Invariants: []
- Verification: []
- Dependencies: [sync_adad_assets]
- Input:
  - platform_instruction_source: object
- Output:
  - rendered_instructions: array
- TODO:
  - [ ] 規格第 2 節：平台 instruction SSOT 與 renderer
- Checkpoint:
  - [ ] CP-1-035 (planned)

##### Module: platform_compatibility_assessment
- Type: checklist
- Observability: not_required
- Description: 對新 Kernel/平台記錄 MCP、hooks、ACL、structured output 與本地 CLI 可用性，避免宣稱不存在的強制保證（規格第 4 節）。
- Source: docs/platform_compatibility.md
- Preferred Pattern: explicit_capability_matrix
- Decisions: [未通過的能力必須標記為指示性與人工 review 風險]
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - platform_capabilities: object
- Output:
  - compatibility_report: object
- TODO:
  - [ ] 規格第 4 節：平台相容性 Checklist
- Checkpoint:
  - [ ] CP-1-036 (planned)
