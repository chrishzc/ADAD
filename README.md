# 📋 ADAD (Architecture-Driven Agentic Development) 開發規範與工具鏈

本專案是一個專為 **Antigravity AI Agent** 設計的 Workspace Customization 擴充套件，旨在實行 **ADAD (架構驅動型智能體開發)** 開發模式。

ADAD 的核心理念是：**將「系統設計（架構）」與「程式碼實作（邏輯）」徹底解耦**。由人類把持高價值的架構與驗收 Checkpoint，並指派 Agent 在最小 Context 的約束下進行高精度的原子程式碼生成，以防範 AI 開發中的架構失控與 Context 膨脹問題。

---

## 📐 三層事實流架構 (Three-Layer Facts Flow)

為了將架構演進的「靈活性」與 Agent 生成的「高精準度」完美結合，本專案採用三層事實流設計：

```
    Human Intent
         ↓
  system_map.md          (Architecture Source) ➔ 人類與 Agent 共同設計，支援逐步展開、TODO、決策記錄等
         ↓
      Compile            (compile_map.py)      ➔ 自動進行格式驗證、生命週期狀態繼承與 dirty 判定
         ↓
  system_map.yaml        (Architecture IR)     ➔ 僅供 Agent 讀取上下文與執行工具，禁止人工編輯
         ↓
  Code Generation        (Implementation)      ➔ 依據 YAML (IR) 產生高質量的原子代碼
```

*   **system_map.md (Architecture Source)**：專為人類與 Agent 協同設計的 Markdown 文件。支援 TODO、Checkpoint、Design Decision、Alternative 等內容。允許暫存、未完成與逐步擴充。
*   **system_map.yaml (Architecture IR)**：完全由編譯器（Compiler）從 Markdown 產生的中間表示檔。用途只有 Context 載入、DAG 依賴分析、Rule of Two 正規化檢查與狀態機執行，**嚴禁人工直接編輯**。
*   **過期自動阻斷**：如果 `system_map.md` 的修改時間晚於 `system_map.yaml`，核心引擎將自動阻斷所有查詢指令（如 `read_context.py`）並要求重新編譯，以確保事實一致性。

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
│               ├── adad_core.py  # 核心引擎 (Markdown 解析、IR 讀寫、DAG 分析、過期阻斷)
│               ├── compile_map.py # Architecture Compiler (Markdown ➔ YAML 狀態合併)
│               ├── resume_analysis.py # Resume 分析器 (進度統計與智能下一步建議)
│               ├── read_context.py
│               ├── check_normalization.py
│               ├── analyze_cascade.py
│               ├── transit_state.py
│               ├── verify_implementation.py # 實作校驗器 (驗證 Verification 條件如斷言)
│               └── check_invariants.py # Invariants 校驗器 (驗證靜態 AST 導入約束)
├── checkpoints/                  # Checkpoint 決策歷史存檔目錄 (CP-X-XXX.yaml)
├── system_map.md                 # 專案架構唯一事實來源 (SSOT - Architecture Source)
├── system_map.yaml               # 專案架構中間表示檔 (SSOT - Architecture IR)
├── install.py                    # 安裝、初始化與打包指令腳本
└── README.md                     # 本說明文件
```

---

## 🛡️ 核心開發憲法 (Global Rules)

不論 Agent 執行哪一個階段的任務，都必須強制遵循以下元規則（Meta-Rules）：

> *   **[RULE-01] SSOT 唯一性**：你唯一的記憶與事實來源為 `system_map.yaml` (自 `system_map.md` 編譯而來)。**嚴禁自行在代碼中衍生或假設未記載於該檔案的介面、路由或規格。**
> *   **[RULE-02] 先架構後程式 (拒絕 Code-First)**：嚴禁 Code-First 開發。只有在目標節點於 `system_map.yaml` 中的狀態為 `planned` 或 `dirty`，且已通過人類的 Checkpoint 審核時，你才被允許生成或修改該節點的商業邏輯代碼。
> *   **[RULE-03] 原子化操作 (Atomic Scope)**：你每次的輸出（程式碼修改）**只能影響單一節點（單一函數、API 或組件）**。嚴禁進行跨模組、跨檔案的大規模 Patch 程式碼。
> *   **[RULE-04] 遇錯即停 (Fail-Fast)**：在 Phase 2（實作期）若發現架構規格無法滿足邏輯需求（例如：發現少傳引數、需要多回傳欄位等），**你必須立即中斷程式碼生成**，改為輸出 `Schema Update Request` 格式，並等待人類審核。

---

## 🔄 ADAD 核心 CLI 工具說明

當前專案底下的 Antigravity Agent 可以直接調用以下指令來操作架構狀態：

| 工具腳本 | 功能說明 | 調用時機 |
| :--- | :--- | :--- |
| `compile_map.py` | 編譯 `system_map.md` ➔ `system_map.yaml` | 修改 Markdown 架構源後首要執行 |
| `resume_analysis.py` | 分析架構 TODO 與智能推薦下一步 | 開發重啟、或人類要求進度概覽時執行 |
| `read_context.py` | 讀取單一節點最小上下文 (已包含 ADR & 模式注入) | Phase 2 開始編寫代碼前，獲取目標簽章 |
| `check_normalization.py` | 執行 Rule of Two 檢查 | Phase 1 架構規劃期，檢測是否重複造輪子 |
| `analyze_cascade.py` | 執行髒點依賴分析 (DAG 走查) | Phase 3 反向同步，架構變更時級聯標記 `dirty` |
| `transit_state.py` | 推進/變更模組生命週期狀態 | CP 審查通過、Lint 通過或被退回時更新狀態 |
| `verify_implementation.py` | 執行代碼實現驗證條件（如 assert）校驗 | 原子代碼生成完畢後進行自檢驗證 |
| `check_invariants.py` | 執行不變量約束（如 deny_imports）校驗 | 原子代碼生成完畢後進行靜態 AST 檢查 |

---

## 🔄 ADAD 人機協作工作流 (Human-Agent Workflow)

此工作流以**人類（架構師/開發者）**為主動驅動者，**Agent** 則作為被動呼叫的原子執行單元。整體流程透過多個 **Checkpoint** 由人類進行決策與狀態推進。

```
[ Phase 1: 架構規劃與逐步展開 (Architecture Growth) ]
  1. 人類啟動規劃，依序小步展開系統架構 (Domain ➔ Subsystem ➔ Module ➔ Interface)。
  2. Agent 執行分析並呼叫 `check_normalization` 確保符合 Rule of Two。
  3. Agent 將規劃草案寫入 `system_map.md` (節點狀態標記為 planned)。
  4. 🚧 【人工 Checkpoint 1】：人類審查架構草案，確認無誤後批准。
  5. 執行 `compile_map.py` 編譯產生 `system_map.yaml`。
       │
       ▼
[ Phase 1.5: 環境與容器規劃 ]
  5.1. Agent 根據系統架構，於 `system_map.md` 的 `environment` 區塊規劃 Docker Compose 容器服務（狀態標記為 planned）。
  5.2. 🚧 【人工 Checkpoint 1.5】：人類審查多容器架構配置，確認無誤後批准，自動產生實體環境配置。
       │
       ▼
[ Phase 2: 原子生成 ]
  6. 人類指派特定節點進行開發，系統呼叫 `read_context` 為 Agent 準備最小上下文。
  7. 人類呼叫 Agent，Agent 依照上下文與規範生成單一原子代碼。
  8. 系統自動執行 Lint & Type Check 驗證代碼。
  9. Agent 呼叫 `check_invariants` 與 `verify_implementation` 進行架構與自檢約束校驗。
     ├── ❌ 失敗：系統呼叫 Agent 讀取 Error，進行自我修正迴圈 (Self-Fix Loop)。
     └──  成功：系統將節點狀態更新為 [linted/tested]。
  10. 🚧 【人工 Checkpoint 2】：人類審查產生的程式碼與實作，確認無誤後批准，推進狀態為 [deployed]。
       │
       ▼
[ Phase 3: 反向同步 ] ─── (若 Agent 在 Phase 2 實作期發現架構缺陷...)
  11. Agent 中斷程式碼生成，改為輸出 `Schema Update Request` 提案給人類。
  12. 🚧 【人工 Checkpoint 3】：人類審查此架構更新請求與影響範圍。
  13. 人類批准更新後，系統執行 Version +1，並自動呼叫 `analyze_cascade`。
  14. 系統自動將變更節點及所有受其影響的上層依賴節點狀態標記為 [dirty]。
  15. 🔄 人類引導指針重回 [Phase 2]，重新呼叫 Agent 生成所有被標記為 dirty 的節點。
       │
       ▼
[ Phase 4: 執行回饋 ]
  16. 人類部署運行系統，並收集監控工具或測試回報數據。
  17. 人類呼叫 Agent 分析運行數據，Agent 輸出 `suggest_architecture_update` 優化提案。
  18. 🚧 【人工 Checkpoint 4】：人類審估此優化提案，批准後更新 YAML，受影響節點變更為 [dirty]，人類重啟 [Phase 2] 演進。
```

---

## 🚧 Checkpoint Review Payload 標準格式

每個 Checkpoint 由三個部分組成：**系統呈現給人類的內容**、**人類的決策選項**、**決策後系統的行為**。每個 Checkpoint 無論結果如何，完整 Payload 都必須存檔於：`checkpoints/CP-{phase}-{序號}-{approved|rejected|modified}.yaml`。

### 共用信封格式（所有 Checkpoint 通用）

```yaml
checkpoint_payload:
  id: "CP-{phase}-{sequence}"        # 例如 CP-1-003
  phase: 1                            # 1~4
  timestamp: "2026-06-30T10:30:00Z"
  triggered_by: "agent"               # agent / system / runtime
  status: "pending"                   # pending / approved / rejected / modify_requested

  display:                            # 呈現給人類看的內容（各 Checkpoint 不同）
    ...

  decision:                           # 人類填寫
    action: ""                        # approve / reject / request_change
    comment: ""                       # 選填，任何文字說明
    modify_targets: []                # 僅 request_change 時填寫

  on_approve: ""                      # 系統執行動作
  on_reject: ""                       # 系統執行動作
  on_modify: ""                       # 系統執行動作
```

---

### Checkpoint 1：架構規劃審查（Phase 1 完成後）
*   **觸發時機**：Agent 完成一層或部分展開，準備編譯與進入 Phase 2 之前。

```yaml
checkpoint_payload:
  id: "CP-1-001"
  phase: 1
  triggered_by: "agent"
  status: "pending"

  display:
    title: "架構規劃審查"
    summary: "本次新增 3 個節點，修改 1 個節點"

    new_nodes:
      - name: "calculate_tax"
        input: { amount: float, country: string }
        output: { tax: float }
        dependencies: ["vat_rules"]
        state: "planned"

    modified_nodes:
      - name: "order_service"
        change: "新增對 calculate_tax 的依賴"
        before: { dependencies: [] }
        after: { dependencies: ["calculate_tax"] }

    normalization_report:
      - "validate_email 出現第 2 次，已 inline，第 3 次將強制抽 Shared Module"

    adr_required:                      # 本次設計決策，建議人類補充 why
      - node: "calculate_tax"
        question: "為何不內嵌於 order_service？"

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - node: ""                       # 要求修改的節點名稱
        instruction: ""                # 修改指示

  on_approve: "transit_module_state(all_new_nodes, validated)"
  on_reject: "清除本次所有 planned 節點，Agent 重新規劃"
  on_modify: "Agent 依照 modify_targets 修正後重新觸發 CP-1"
```

---

### Checkpoint 1.5：環境與容器部署規劃審查（Phase 1.5 完成後）
*   **觸發時機**：Phase 1 架構規劃審查 (CP-1) 通過後，準備開始 Phase 2 原子代碼生成之前。

```yaml
checkpoint_payload:
  id: "CP-1.5-001"
  phase: 1.5
  triggered_by: "agent"
  status: "pending"

  display:
    title: "環境與容器部署規劃審查"
    summary: "規劃多容器服務與環境變數以支援模組運行"

    environment_schema:
      compose_arch: true
      state: "planned"
      services:
        backend:
          type: "container"
          build: "./backend"
          ports: ["8000:8000"]
          environment: ["ENV=development"]
          depends_on: ["db"]
        db:
          type: "container"
          image: "postgres:15-alpine"
          volumes: ["db_data:/var/lib/postgresql/data"]

    generated_files:
      - "docker-compose.yml"
      - "backend/Dockerfile"

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - service: "backend"
        instruction: ""

  on_approve: "產生實體環境設定檔，並推進 environment.state 為 validated"
  on_reject: "Agent 重新調整環境與容器規劃"
  on_modify: "Agent 調整容器與環境配置後重新觸發 CP-1.5"
```

---

### Checkpoint 2：原子模組審查（Phase 2 每個模組生成後）
*   **觸發時機**：單一模組通過 Lint & Type Check 後，準備標記為 deployed 之前。

```yaml
checkpoint_payload:
  id: "CP-2-007"
  phase: 2
  triggered_by: "agent"
  status: "pending"

  display:
    title: "原子模組審查"
    node: "calculate_tax"

    spec_comparison:                   # 規格對照，方便人類確認有無介面漂移
      expected:                        # 來自 system_map.yaml
        input: { amount: float, country: string }
        output: { tax: float }
      actual:                          # Agent 實際生成的 signature
        input: { amount: float, country: string }
        output: { tax: float }
      drift_detected: false

    generated_code: |
      def calculate_tax(amount: float, country: str) -> float:
          ...

    lint_result:
      passed: true
      warnings: []

    type_check_result:
      passed: true

    self_fix_history:                  # 若有自我修正，顯示過程
      attempts: 0
      log: []

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - node: "calculate_tax"
        instruction: ""

  on_approve: "transit_module_state(calculate_tax, deployed)"
  on_reject: "transit_module_state(calculate_tax, dirty)，Agent 重新生成"
  on_modify: "Agent 依照 modify_targets 修正後重新觸發 CP-2"
```

---

### Checkpoint 3：Schema Update Request 審查（Phase 3 觸發時）
*   **觸發時機**：Agent 在實作時發現架構缺陷，發出 Schema Update Request。

```yaml
checkpoint_payload:
  id: "CP-3-002"
  phase: 3
  triggered_by: "agent"
  status: "pending"

  display:
    title: "Schema Update Request 審查"

    update_request:                    # Agent 原始輸出
      action: "update_schema"
      target: "api_login"
      add_arguments: ["user_id"]
      reason: "Login response 需要回傳 user_id 供下游 SessionService 使用，目前 schema 未定義"

    impact_analysis:                   # analyze_cascade 的結果
      dirty_nodes:
        - node: "api_login"
          reason: "直接變更"
        - node: "session_service"
          reason: "依賴 api_login output"
        - node: "auth_middleware"
          reason: "依賴 session_service"
      estimated_regeneration_cost: "3 個模組需重新生成"

    version_preview:
      from: "system_map_v3.yaml"
      to: "system_map_v4.yaml"
      diff:
        - type: "modify"
          node: "api_login"
          change: "output 新增 user_id: string"

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - node: ""
        instruction: ""

  on_approve: "Version +1，執行 analyze_cascade，所有 dirty 節點重回 Phase 2"
  on_reject: "Agent 必須在不修改 schema 的前提下重新思考實作方式，若無法解決則再次觸發 CP-3"
  on_modify: "Agent 依照 modify_targets 調整 Update Request 後重新觸發 CP-3"
```

---

### Checkpoint 4：Architecture 優化提案審查（Phase 4 觸發時）
*   **觸發時機**：Runtime 數據觸發 Agent 提出優化建議。

```yaml
checkpoint_payload:
  id: "CP-4-001"
  phase: 4
  triggered_by: "runtime"
  status: "pending"

  display:
    title: "Architecture 優化提案審查"

    evidence:                          # 觸發此提案的數據依據
      metric: "calculate_tax 呼叫頻率"
      observation: "95% 來自 JP，平均回應時間 230ms"
      threshold_exceeded: "回應時間 > 200ms SLA"

    proposal:
      action: "suggest_architecture_update"
      target: "calculate_tax"
      reason: "High frequency path，JP 稅率短期不變"
      proposal: "Introduce cache layer，TTL 24hr"

    impact_analysis:
      dirty_nodes:
        - node: "calculate_tax"
          reason: "加入 cache decorator"
        - node: "vat_rules"
          reason: "需新增 cache invalidation hook"
      new_nodes:
        - name: "tax_cache"
          type: "infrastructure"
          state: "planned"
      estimated_regeneration_cost: "2 個模組修改，1 個新模組"

    risk_assessment:
      - "cache 過期期間若 JP 稅率異動，將回傳錯誤數據"
      - "建議搭配 vat_rules 變更事件觸發 cache invalidation"

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - node: ""
        instruction: ""

  on_approve: "Version +1，更新 system_map，dirty 節點重回 Phase 2"
  on_reject: "提案封存，記錄於 ADR，標記為 rejected，不影響現有架構"
  on_modify: "Agent 依照 modify_targets 調整提案後重新觸發 CP-4"
```

---

## 🛡️ 跨 Checkpoint 共用規則與自修復限制

*   **Self-Fix Loop 終止條件**：
    在 Phase 2 原子模組生成時，因 Lint/Type Check 失敗所啟動的自我修正機制（Self-Fix Loop），最多嘗試 **3 次**。若 3 次皆失敗，必須立刻停止生成，將錯誤日誌填入 Checkpoint Payload 並呈報給人類審查（升級為 CP-2 審查）。
*   **on_reject 的 Agent 行為限制**：
    所有 Checkpoint 被人類拒絕（Reject）後，Agent 只能在原被拒絕的模組/節點範圍內重新思考實作或微調，**禁止自行擴大修改範圍至其他節點**。

---

## 📈 ADAD 演進與優化改善邏輯 (Improvements)

相較於 ADAD 第一版純 YAML facts 與硬性依賴校驗的設計，當前專案整合了以下幾項重大改善與升級：

### 1. 設計抉擇 (ADR) 智慧注入與 Context 裁剪
*   **改善邏輯**：為防止 Context 膨脹，架構引擎實作了 [docs/adr/](file:///docs/adr) 文件智慧解析器。當 Agent 調用 `read_context` 讀取節點時，引擎會提取模組關聯的 ADR 文件（如 `ADR-001`）中的**標題、狀態、以及決策要點**，智慧裁減為 2~3 行摘要後寫入 Context，為 Agent 在多種寫法中做出設計決策提供 why 的歷史引導。

### 2. 首選設計模式 (Preferred Pattern) 落地
*   **改善邏輯**：引進模式約束（例如 [pure_function.md](file:///docs/patterns/pure_function.md) 模式）。可在架構中聲明模組首選模式，Context 會隨之注入模式規範（如 "輸入引數必須為 immutable" 等指引），直接回答 Agent「有多種寫法時應該選哪一種」的實踐方式。

### 3. 架構邊界靜態不變量 (Invariants) AST 校驗
*   **改善邏輯**：新增了基於 Python AST（抽象語法樹）的靜態檢查器 `check_invariants`。能讀取 `system_map.yaml` 中配置的 `invariants` 約束（如 `deny_imports: [pymysql]`），在代碼生成後對 Imports 與 ImportsFrom 進行靜態分析並自動阻斷違規導入，守護系統解耦意圖（如分層隔離、防腐界限）。

### 4. 代碼實現驗證限制 (Verification)
*   **改善邏輯**：新增了 `verify_implementation` 檢驗器，支援在節點上配置 `verification` 約束（例如 `must_have_assertions`），強制 Agent 在撰寫原子程式碼時必須至少包含一個 `assert` 自檢斷言，從而限制程式碼實踐的品質。

### 5. 智慧狀態繼承與編譯重置
*   **改善邏輯**：引入 Compiler (`compile_map.py`) 在從 `system_map.md` 編譯為中間表示 YAML 時，會自動進行結構比對。
    *   **無變動繼承**：如果模組的 input, output, dependencies 未改變，自動繼承舊的狀態（如 deployed）。
    *   **變動重置**：如果模組發生了結構性改變，狀態會智慧重置為 `dirty`。

### 6. 思路重啟 (Resume) 與下一步智能推薦
*   **改善邏輯**：為解決 Agent 中途接手難以恢復設計思路的痛點，實作了 `resume_analysis.py`。能輸出詳細 TODO 與 Checkpoints 進度報告。更基於 DAG 拓撲分析，篩選出**依賴項均已 deployed 但自身尚未 deployed 的模組**，智能推薦最合理的下一步開發重點。
