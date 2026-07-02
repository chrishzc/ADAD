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
 
