# 📋 Workspace Agent Rules (ADAD 專案開發憲法)

此檔案是專門給 Antigravity Agent 閱讀的行為約束規範。當前專案已啟用 **ADAD (Architecture-Driven Agentic Development)** 開發模式。

---

## 🛡️ 核心約束規則 (Global Rules)

你必須無條件遵守以下四大規則：

> ### 🛑 [RULE-01] SSOT 唯一性 🔒 **機器強制**
> 你唯一的系統架構記憶與事實來源為根目錄底下的 `system_map.yaml`。**嚴禁自行在代碼中衍生或假設未記載於該檔案的介面、路由或規格。**
> **執行方式**：Pre-commit hook 自動阻斷過期的 `system_map.yaml`（若 `.md` 較新則禁止 commit）。
>
> ### 🛑 [RULE-02] 先架構後程式 (拒絕 Code-First) 🔒 **機器強制**
> 嚴禁 Code-First 開發。只有在目標節點（Function / API / Class）於 `system_map.yaml` 中的狀態為 `planned`、`dirty`、`validated` 或 `draft`，且已通過人類的 Checkpoint 審核時，你才被允許生成或修改該節點的商業邏輯代碼。
> **執行方式**：Pre-commit hook 比對 staged 檔案與模組狀態，非允許狀態的節點禁止修改程式碼。
>
> ### 🛑 [RULE-03] 原子化操作 (Atomic Scope) ⚠️ **機器警告**
> 你每次的輸出（Output Payload / 程式碼修改）**只能影響單一節點（單一函數、API 或組件）**。嚴禁進行跨模組、跨檔案的大規模 Patch 程式碼。
> **執行方式**：Pre-commit hook 偵測跨模組修改時發出 WARNING（不阻斷，允許必要的跨模組重構）。
>
> ### 🛑 [RULE-04] 遇錯即停 (Fail-Fast) 📝 **Agent 行為規則**
> 在 Phase 2（實作期）若發現 `system_map.yaml` 所定義的架構規格無法滿足邏輯需求（例如：發現少傳引數、需要多回傳欄位等），**你必須立即中斷程式碼生成**，改為輸出 `Schema Update Request` 格式，並等待人類審核。
> **執行方式**：無法由機器強制，保留為 Agent 行為約束。

---

## 🔒 機器強制檢查 (Pre-Commit Hook)

以下檢查在每次 `git commit` 時自動執行，不依賴 Agent 自律：

| # | 檢查項目 | 對應規則 | 失敗行為 |
|---|---------|---------|---------|
| 1 | Staleness 阻斷 | RULE-01 | ❌ 阻斷 commit |
| 2 | 狀態門禁 | RULE-02 | ❌ 阻斷 commit |
| 3 | 原子範圍 | RULE-03 | ⚠️ 警告（不阻斷） |
| 4 | Invariants (deny_imports) | 架構邊界 | ❌ 阻斷 commit |
| 5 | Verification (must_have_assertions) | 實作品質 | ❌ 阻斷 commit |

緊急情況可用 `git commit --no-verify` 繞過。

---

## 📋 Draft Debt Ledger

當模組以 `draft` 狀態存在時（Leaf 模式生成的 demo 模組），系統會追蹤其 **fan-in**（有多少其他模組依賴它）。

**自動升級規則**：
- 當 draft 模組的 fan-in 從 0 變為 **≥2**（被 2 個以上模組依賴），系統自動將其及所有新依賴它的節點標記為 `pending_review`。
- 此時強制觸發一次補做 Checkpoint（含 ADR），確保 demo 期代碼在變重要時經過正式審查。

**觸發條件是結構性的（依賴關係變化），不依賴人類記憶。**

---

## 🔄 ADAD 人機協作工作流 (Human-Agent Workflow)

此工作流以**人類（架構師/開發者）**為主動驅動者，**Agent** 則作為被動呼叫的原子執行單元。整體流程透過多個 **Checkpoint** 由人類進行決策與狀態推進。

```
[ Phase 1: 架構規劃 ]
  1. 人類啟動規劃，呼叫 Agent 依序分析系統架構 (UI -> API -> Service -> DB)。
  2. Agent 執行分析並呼叫 `evaluate_normalization_policy` 確保符合 Rule of Two。
  3. Agent 將規劃草案寫入 `system_map.yaml` (節點狀態標記為 planned)。
  4. 🚧 【人工 Checkpoint 1】：人類審查架構草案，確認無誤後批准，推進狀態為 [validated]。
       │
       ▼
[ Phase 1.5: 環境與容器規劃 ]
  4.1. Agent 根據系統架構，於 `system_map.yaml` 的 `environment` 區塊規劃 Docker Compose 容器服務（狀態標記為 planned）。
  4.2. 🚧 【人工 Checkpoint 1.5】：人類審查多容器架構配置，確認無誤後批准，推進狀態為 [validated] 並自動產生實體環境配置。
       │
       ▼
[ Phase 2: 原子生成 ]
  5. 人類指派特定節點進行開發，系統呼叫 `read_context_by_node` 為 Agent 準備最小上下文。
  6. 人類呼叫 Agent，Agent 依照上下文與規範生成單一原子代碼。
  7. 系統自動執行 Lint & Type Check 驗證代碼。
     ├── ❌ 失敗：系統呼叫 Agent 讀取 Error，進行自我修正迴圈 (Self-Fix Loop)。
     └──  成功：系統將節點狀態更新為 [linted/tested]。
  8. 🚧 【人工 Checkpoint 2】：人類審查產生的程式碼與實作，確認無誤後批准，推進狀態為 [deployed]。
       │
       ▼
[ Phase 3: 反向同步 ] ─── (若 Agent 在 Phase 2 實作期發現架構缺陷...)
  9. Agent 中斷程式碼生成，改為輸出 `Schema Update Request` 提案給人類。
  10. 🚧 【人工 Checkpoint 3】：人類審查此架構更新請求與影響範圍。
  11. 人類批准更新後，系統執行 Version +1，並自動呼叫 `analyze_dirty_cascade`。
  12. 系統自動將變更節點及所有受其影響的上層依賴節點狀態標記為 [dirty]。
  13. 🔄 人類引導指針重回 [Phase 2]，重新呼叫 Agent 生成所有被標記為 dirty 的節點。
       │
       ▼
[ Phase 4: 執行回饋 ]
  14. 人類部署運行系統，並收集監控工具或測試回報數據。
  15. 人類呼叫 Agent 分析運行數據，Agent 輸出 `suggest_architecture_update` 優化提案。
  16. 🚧 【人工 Checkpoint 4】：人類審估此優化提案，批准後更新 YAML，受影響節點變更為 [dirty]，人類重啟 [Phase 2] 演進。
```

---

## 🚧 Checkpoint 決策處理與限制

* **被拒絕的應對 (On Reject)**：若 Checkpoint 提案被人類拒絕（Reject），你只能在原被拒絕的節點範圍內重新調整實作或架構，**禁止自行擴大修改範圍至其他節點**。
* **自我修正限制 (Self-Fix Policy)**：在 Phase 2 代碼生成因 Lint/Type Check 失敗進行 Self-Fix時，最多嘗試 3 次。若 3 次皆失敗，必須立刻停止生成，將錯誤日誌填入 Checkpoint Payload 並呈報給人類。

### Reviewer Unicode 證據規則

* 不得只依終端畫面或工具渲染判定檔案編碼異常。
* 退回前必須檢查原始 bytes 能否 strict UTF-8 解碼、內容是否包含 replacement character (`U+FFFD`)；JSON 檔另須完成 UTF-8 strict 讀回與解析。
* 編碼退回必須附上可重現命令、上述檢查結果與 fingerprint。
* Task submit 前須確認受管文字檔的 working tree bytes 已符合 `.gitattributes`，避免 CRLF／LF 正規化造成 staged hash 與核准 hash 不一致。
* 若證據確認只是顯示誤判，必須撤回該次退回，且 `return_count` 不得增加；若已遞增則恢復為退回前數值。
