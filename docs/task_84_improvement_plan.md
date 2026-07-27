# #84 改善方向與實作計畫

> **修訂紀錄（v2）**：根據 review 意見修正三處設計：
> 1. `architecture_impact` 判準改為「approve 前後結構欄位差異」，排除 `state` 欄位，
>    避免 `delivery_gate` 自身狀態推進誤觸發架構影響判定；`check_domain_boundary`／
>    `check_invariants` 改定位為絕對阻斷 gate，與人工重審分級為兩條獨立判斷軸。
> 2. `validated → linted/tested → deployed` 改為分段原子推進，任一段失敗時狀態精確停在
>    最後成功的中間狀態，並支援斷點續跑。
> 3. 新增腳本僅寫入 `adad_source` canonical 來源，透過既有 `sync_assets.py` 同步到
>    `.agents`／`adad_cli/resources`，避免三處副本各自為政。

## 1. 任務背景

**原始待辦（`docs/specifications/05_task_backlog.md` #84）：**

> `adad_core` 需明確建立 Phase-2 末尾的交付步驟：`validated -> linted/tested -> deployed`，
> 不得讓 approve 自動跳過中間狀態，並補齊對應 checklist / regression 驗證。

**延伸目標（使用者補充）：**

> 讓後續無關程式架構、規格的部分都能讓 agent 安全自動完成，同時盡量減少 token 消耗。

---

## 2. 現況分析

| 項目 | 現況 | 檔案位置 |
|---|---|---|
| 狀態機合法路徑 | 已定義 `validated → linted/tested → deployed`，且已擋掉跳級（如 `planned → deployed` 直接被拒） | `adad_core.py` 約 1490 行；`tests/test_transit_state.py` |
| approve 流程 | 只把模組推進到 `validated` 就停手，之後沒有任何程式碼繼續推進 | `_advance_module_to_validated`（2683 行）、`_commit_checkpoint_decision`（2737 行） |
| `linted/tested`／`deployed` 寫入 | 只出現在測試檔案手動塞資料，現實中沒有流程會真的走到這兩個狀態 | 例如 4657、4705 行等 |
| 風險/複雜度分級前例 | 已有純函式決策模式可參考（無 LLM 呼叫、無副作用、可 assert 自測） | `task_complexity.py` |
| 架構影響偵測前例 | 已有 domain 邊界與不變量檢查，可重複利用 | `check_domain_boundary.py`、`check_invariants.py` |

**結論**：規格層（state schema）已經防呆，缺的是「approve 之後主動、帶證據地推進」的機制，以及「哪些改動可以免人工判斷、安全自動跑完」的分級規則。

---

## 3. 改善方向（設計原則）

### 原則一：判斷與機械操作徹底分離

| 類型 | 執行者 | Token 成本 |
|---|---|---|
| 是否影響架構/規格 | Agent／人工（只在 CP-2 審查時判斷一次） | 一次性 |
| lint → test → deploy 推進 | 純腳本 / deterministic CLI | 趨近零 |

### 原則二：`architecture_impact` 判準必須基於「結構欄位差異」，而非「檔案是否被修改」與「有無違規」

**⚠️ 修正紀錄**：初版設計曾誤把 `check_domain_boundary` / `check_invariants` 的檢查結果
（有無違規）當成「有無架構變更」的判準，兩者是不同的問題：
- `check_domain_boundary` / `check_invariants` 回答的是「這個改動**合不合法**」（fail-closed 阻斷條件）
- 是否需要人工重審回答的是「這個改動**有沒有動到架構/規格**」（審查分級條件）

也曾考慮過「用 `system_map.yaml` 是否被修改」當判準，但此法有致命 bug：`save()`（838 行）
把每個模組的 `state` 欄位跟 `dependencies`／`domain`／`type`／`algorithm`／`invariants` 等真正的架構
欄位存在同一份檔案裡。也就是說**每一次 `transit_state()` 呼叫本身就會重寫 `system_map.yaml`**——
包含 `delivery_gate` 自己把節點從 `validated` 推進到 `linted/tested`、`deployed` 的過程中，
自己就會不斷觸發「檔案被修改」。若以此為判準，幾乎所有 task 都會被誤判為
`architecture_impact = true`，直接打死「無架構影響的改動可自動安全跑完」這個核心目標。

**修正後的判準**：比較 approve 當下 vs. 上一次 CP-2 approved 快照，僅檢查下列「結構欄位」
是否有差異，明確排除 `state` 欄位：

```python
STRUCTURAL_KEYS = {"dependencies", "domain", "type", "algorithm", "invariants",
                   "verification", "sub_maps", "owner"}

def has_architecture_impact(node_before: dict, node_after: dict) -> bool:
    keys = STRUCTURAL_KEYS & (node_before.keys() | node_after.keys())
    return any(node_before.get(k) != node_after.get(k) for k in keys)
```

- 新增合法 API 節點（改了 `dependencies`/`domain`）→ 正確判定為架構變更 → `requires_review`
- 純內部 algorithm bug 修復，未動到上述結構欄位 → 正確判定為無架構變更 → 可自動推進
- `delivery_gate` 自己推進 `state` 欄位 → 不會誤觸發 `architecture_impact`，可安全連續呼叫

**`check_domain_boundary` / `check_invariants` 的正確定位**：作為 `delivery_gate` 的**絕對阻斷 gate**
（fail-closed）——不論 `architecture_impact` 為何，只要違規就一律 `blocked`。這與「是否需要人工重審」
是兩條完全獨立的判斷軸，不應混為一談。CP-2 approve 當下仍可順便執行這兩支腳本並記錄結果，
但用途是「是否放行」，不是「是否有架構變更」。

### 原則三：新增純函式決策模組 `delivery_gate.py`

仿照 `task_complexity.py` 的風格：無 LLM 呼叫、無副作用、可用 `assert` 自我測試。

```python
def evaluate_delivery_step(current_state, lint_exit_code, test_exit_code,
                            domain_boundary_ok, invariants_ok, architecture_impact) -> str:
    # 絕對阻斷 gate 優先於一切，不論是否需要人工重審
    if not domain_boundary_ok or not invariants_ok:
        return "blocked"
    if lint_exit_code != 0 or test_exit_code != 0:
        return "blocked"
    # 阻斷 gate 通過後，才判斷是否需要人工重審（架構/規格分級）
    if architecture_impact:
        return "requires_review"
    if current_state == "validated":
        return "advance_to_linted_tested"
    if current_state == "linted/tested":
        return "advance_to_deployed"
    return "no_action"
```

`architecture_impact` 的值由**原則二**定義的 `has_architecture_impact()` 提供，而非本函式自行判斷。

### 原則四：把「跑 lint/test/deploy」包成單一 CLI（例如 `adad_release_advance.py`）

- 內部依序執行 lint、pytest、打包（subprocess）
- 呼叫 `delivery_gate.evaluate_delivery_step` 決定下一步
- 只回傳精簡結構化 JSON（狀態、pass/fail、hash），不回傳完整 log
- Agent 只需呼叫一次、讀幾行結果，取代「自己跑 lint → 讀輸出 → 跑 test → 讀輸出 → 決定」的多輪推理

### 原則五：Hash-guard 避免重工

沿用既有的 `source_hash` / `implementation_hash` 機制：來源沒變就跳過重跑，直接回傳 cache 結果，
對「無關的模組」完全不需要 agent 重新分析。

### 原則五之一：分段原子推進（Transactional State Advance），不可整批推進或整批回退

`validated → linted/tested → deployed` 是兩段獨立的交易，不能把 CLI 設計成「lint/test/deploy
一次跑完才寫一次狀態」。理由：若 lint/test 通過但 deploy/manifest 打包失敗，模組狀態必須精確停在
`linted/tested`（因為 lint/test 這段證據是真的、可信的），不能因為後段失敗就整批回退到 `validated`，
也絕不能因為前段成功就暴衝到 `deployed`。

具體做法（比照 `_commit_checkpoint_decision` 既有的 deepcopy 快照 + 失敗回滾模式）：

1. 執行 lint/test → 通過 → **立即**寫入 `linted/tested` 證據 hash → **立即** `transit_state` 到
   `linted/tested`（這是一筆獨立完成的交易，即使後面失敗也不撤銷）。
2. 執行 deploy/manifest 打包 → 通過 → 寫入 `deployed` 證據 hash → `transit_state` 到 `deployed`。
3. 任一段失敗：`transit_state` 停在最後一個成功完成的中間狀態，CLI 回傳結果需明確標示
   「目前卡在哪一段、失敗原因為何」，下次重跑時（配合 hash-guard）直接從失敗的那一段續跑，
   不必重跑已通過的段落。

### 原則六：兩條獨立的判斷軸，不可混為一談

| 判斷軸 | 回答的問題 | 失敗/為真時的結果 |
|---|---|---|
| 絕對阻斷 gate（`check_domain_boundary`、`check_invariants`、lint/test exit code） | 這個改動合不合法、能不能過 | `blocked`（fail-closed，不論是否需要人工重審都不放行） |
| 人工重審分級（`architecture_impact`，見原則二） | 這個改動有沒有動到架構/規格結構欄位 | `requires_review`（交還人工/agent 判斷，但前提是已先通過絕對阻斷 gate） |

只有「絕對阻斷 gate 通過」且「`architecture_impact = false`」同時成立時，才會全程自動、
無人工介入地安全推進；其餘情況一律卡住或交還審查，不會跳級、不會在失敗時繼續推進。

---

## 4. 實作計畫（分階段）

### 階段 A：資料與判斷基礎
1. 在 approve 當下保存「上一次 CP-2 approved 快照」的結構欄位（`dependencies`/`domain`/`type`/
   `algorithm`/`invariants`/`verification`/`sub_maps`/`owner`），供下一次 approve 時比對。
2. 新增 `has_architecture_impact(node_before, node_after)` 純函式：僅比對上述結構欄位，明確排除
   `state` 欄位，寫入 `task_data["architecture_impact"]`。
3. 在 `_commit_checkpoint_decision` approve 分支中，呼叫既有的 `check_domain_boundary`／
   `check_invariants`，其結果作為**絕對阻斷 gate**（`domain_boundary_ok`/`invariants_ok`），
   與 `architecture_impact` 分開記錄，不得混用。
4. 新增 `delivery_gate.py`，包含 `evaluate_delivery_step` 純函式（阻斷 gate 優先於重審分級）
   與 `__main__` 自測（比照 `task_complexity.py`）。
5. 新增測試：
   - `test_has_architecture_impact_true_when_dependencies_change`
   - `test_has_architecture_impact_false_when_only_state_changes`（回歸測試，鎖死原本會誤判的
     「`state` 欄位變更不算架構影響」）
   - `test_delivery_gate_blocked_when_domain_boundary_or_invariants_fail`（即使 `architecture_impact=false`
     也要擋）
   - `test_delivery_gate_requires_review_when_architecture_impact_true_and_gates_pass`
   - `test_delivery_gate_advances_without_review_when_clean`

### 階段 B：機械化推進 CLI
6. 新增 `adad_release_advance.py`，**分段獨立交易**，不可一次跑完才寫一次狀態：
   - **Segment 1（`validated → linted/tested`）**：讀取模組現狀 → 執行 lint/test（若 hash 未變則跳過
     並用 cache）→ 呼叫 `delivery_gate`（含絕對阻斷 gate + `architecture_impact`）→ 通過則**立即**
     寫入證據 hash 並 `transit_state` 到 `linted/tested`；此段完成即視為獨立交易，不因後段失敗而回退。
   - **Segment 2（`linted/tested → deployed`）**：僅在 Segment 1 已完成時執行。呼叫既有
     `release_preflight.py` / `release_candidate_manifest.py` 產出部署證據 → 通過則寫入證據 hash 並
     `transit_state` 到 `deployed`。
   - 任一段的絕對阻斷 gate 失敗或 `architecture_impact = true` → 該段直接 `blocked`/`requires_review`，
     狀態精確停留在最後一個成功完成的中間狀態，不暴衝、不回退。
   - 輸出：精簡 JSON，明確標示目前卡在哪一段、原因為何，例如
     `{"result": "blocked", "stuck_at": "linted/tested", "reason": "deploy manifest failed", "evidence_hash": "..."}`。
7. 擴充 `_write_checkpoint_audit`，新增欄位記錄目前推進到哪個中間狀態、對應證據 hash，
   避免 CP-2 紀錄被誤讀成「approved = 已部署」。
8. 新增測試：
   - `test_release_advance_skips_when_hash_unchanged`
   - `test_release_advance_writes_evidence_to_checkpoint`
   - `test_release_advance_does_not_skip_intermediate_state`（approve 後直接呼叫，仍必須先到 `linted/tested` 才能到 `deployed`）
   - `test_release_advance_stops_at_linted_tested_when_deploy_segment_fails`（Segment 2 失敗時，狀態不回退、也不暴衝）
   - `test_release_advance_resumes_from_failed_segment_without_rerunning_passed_segment`（斷點續跑，不重跑已通過的段落）

### 階段 C：串接與收斂
9. `release_preflight.py`（既有全庫 pytest gate）與 `release_candidate_manifest.py`（既有打包流程）
   已在 Segment 2 中被 `adad_release_advance.py` 呼叫，避免重複造輪子。
10. **Canonical 來源與同步（維護注意事項）**：新增的 `delivery_gate.py`、`has_architecture_impact`、
    `adad_release_advance.py` 一律只寫在 `adad_source/agents/skills/adad-workflow/scripts/`
    （唯一可編輯來源），**不得**手動在 `.agents/skills/...` 或 `adad_cli/resources/agents/skills/...`
    另外複製一份；完成後執行既有的 `sync_assets.py --write` 產生另外兩處受管理副本，並用
    `test_sync_assets.py::test_sync_twice_is_idempotent` 的模式補一條
    `test_sync_assets_propagates_delivery_gate_and_release_advance`，確保新腳本不會在同步時被遺漏。
11. 更新 `docs/RELEASE_SOP.md`（或 `05_task_backlog.md` 本身），新增規則：
    > approve 不等於 deployed；中間必須有可稽核的 lint/test/deploy 證據，且僅當「絕對阻斷 gate 通過」
    > 且「`architecture_impact = false`」同時成立時，才可由 `adad_release_advance` 自動完成、不需人工重審；
    > 任一條件不成立則卡住或交還審查。
12. 回填 `05_task_backlog.md` 中 #84 狀態欄位與測試對照表（目前 Pytest 欄位為「—」）。

---

## 5. 驗收標準（Checklist）

- [x] `architecture_impact` 判準僅比對結構欄位（`dependencies`/`domain`/`type`/`algorithm`/
      `invariants`/`verification`/`sub_maps`/`owner`），**排除 `state` 欄位**；`delivery_gate` 自身
      推進 `state` 不會誤觸發 `architecture_impact = true`
- [x] `check_domain_boundary`／`check_invariants`／lint／test 作為絕對阻斷 gate，優先於
      `architecture_impact` 判斷；即使無架構影響，違規或測試失敗一律 `blocked`
- [x] approve 後模組狀態確實停在 `validated`，不會被誤判為已部署
- [x] `architecture_impact = true` 的任務，通過絕對阻斷 gate 後仍回傳 `requires_review`，不自動推進
- [x] `architecture_impact = false` 且絕對阻斷 gate 全數通過時，可一路自動推進到 `deployed`，全程無需人工判斷
- [x] lint、test、deploy 任一段失敗時，狀態精確停在最後一個成功完成的中間狀態（不回退、不暴衝）
- [x] 斷點續跑：重新呼叫時只從失敗的段落續跑，不重跑已通過的段落
- [x] source hash 未變時，重複呼叫不會重跑 lint/test，直接回傳 cache 結果
- [x] 所有中間狀態轉移都有對應證據（hash + timestamp）寫入 checkpoint audit
- [x] 新增腳本只存在於 `adad_source` canonical 來源，並已透過 `sync_assets.py --write` 同步到
      `.agents` 與 `adad_cli/resources` 兩處受管理副本
- [x] 新增的 regression 測試全數納入 CI 並通過
- [x] `05_task_backlog.md` #84 狀態由 `planned` 更新為對應進度，並補上 Pytest 欄位


---

## 8. 與 #86 的介面邊界（刻意輕量，不深度整合）

#86（Reviewer Loop / Task 自動蓋章）是獨立任務，兩者**分開實作、分開驗收**，不互相呼叫對方的 CLI：

- 本任務（#84）只負責模組生命週期狀態（`validated → linted/tested → deployed`）的機械化推進，**前提是模組已經是 `validated`**——這個前提目前只由人類 `task_approve()` 觸發，本任務不假設、也不依賴 #86 的 `task_auto_certify()` 會連動這個狀態機。
- 若未來要讓 #86 的自動蓋章結果去觸發本任務的交付流程，那是一個**新的、獨立的整合任務**，需要另外設計觸發時機與批次頻率（本任務的 Segment 2 依賴全庫層級的 `release_preflight.py`/`release_candidate_manifest.py`，不適合掛在每個 Task 蓋章當下同步觸發）。
- 本任務可以獨立開發、獨立測試、獨立驗收，不必等待 #86 完成，反之亦然。

---

## 6. 對目標的對應說明

| 使用者目標 | 對應設計 |
|---|---|
| 無關架構/規格的部分讓 agent 安全自動完成 | 階段 A 的 `architecture_impact` 分級 + 階段 B 的機械化 CLI，兩者合作把「安全」與「自動」分開處理 |
| 減少 token 消耗 | 把多輪 agent 推理壓縮成一次 CLI 呼叫、只回傳精簡結構化結果；hash-guard 避免對未改動模組重複分析 |
