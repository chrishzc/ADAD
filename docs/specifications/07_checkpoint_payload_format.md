## 7. Checkpoint Review Payload 標準格式

> 本文件從 README.md 拆出，屬於 [規格總覽](../SPEC_INDEX.md) 系列的第 7 份。README 只保留摘要與連結，完整的 Checkpoint payload schema、四種 Checkpoint 各自的 YAML 範例、以及跨 Checkpoint 共用規則都在這裡。

每個 Checkpoint 由三個部分組成：**系統呈現給人類的內容**、**人類的決策選項**、**決策後系統的行為**。每個 Checkpoint 無論結果如何，完整 Payload 都必須存檔於：`checkpoints/CP-{phase}-{序號}-{approved|rejected|modified}.yaml`。

CP-2 的 `adad_task.py approve/reject` 會自動建立此留痕；人類必須在互動終端機提供 `--reviewer "姓名"`。紀錄會固定保存 reviewer、時間、Task ID、架構版本、source hash、結果與註解，audit 寫入失敗時會回復 Task 與模組狀態。

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

  on_approve: "adad_task.py approve（解開 source 鎖，寫入 audit 紀錄，推進狀態為 deployed）"
  on_reject: "adad_task.py reject（保留修改，留待後續修正），Agent 重新生成"
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

### 跨 Checkpoint 共用規則與自修復限制

*   **Self-Fix Loop 終止條件**：
    在 Phase 2 原子模組生成時，因 Lint/Type Check 失敗所啟動的自我修正機制（Self-Fix Loop），最多嘗試 **3 次**。若 3 次皆失敗，必須立刻停止生成，將錯誤日誌填入 Checkpoint Payload 並呈報給人類審查（升級為 CP-2 審查）。
*   **on_reject 的 Agent 行為限制**：
    所有 Checkpoint 被人類拒絕（Reject）後，Agent 只能在原被拒絕的模組/節點範圍內重新思考實作或微調，**禁止自行擴大修改範圍至其他節點**。

---

