## 6. 多模組協作目標

### 6-1｜隔離必須落在執行環境層，不能只是約定

||內容|
|---|---|
|問題|「只傳 artifact」若只是 prompt/SKILL 裡的一句約定，agent 跟前一輪其實跑在同一個有完整檔案系統存取權的 checkout / session 裡，約定隨時可能被好奇心、誤解或 prompt injection 破壞——這仍然是指示性,不是機械強制。|
|ADAD 需求（契約）|每次 agent 呼叫必須發生在**只掛載該 artifact + 明確允許碰的檔案**的獨立執行環境（獨立 container / worktree / sandbox），而不是共用一份大 repo checkout 加上口頭約定。|
|自建 Kernel 做法|Workflow Engine 在 spawn 每個 agent session 前，準備一份乾淨、範圍受限的工作目錄（例如把允許的檔案 clone/連結進去，其餘什麼都不掛），session 結束後只取回宣告好的輸出 artifact。|
|現成平台做法|用平台的 sandbox/worktree 機制盡量逼近（例如各自開一個 git worktree、限制 cwd），但多數平台的「檔案系統可見範圍」跟「MCP 工具白名單」是兩件事，很難做到完全物理隔離——同一個張力在 1-2 已經討論過。|
|強制程度|自建 = 可以做到機械強制（代價是基礎設施複雜度）；現成平台 = 盡力而為,通常只能逼近,無法保證。|
|ADAD 套件必須包含|一份「Agent 執行環境模板」規格（每種 artifact 類型對應「這次呼叫允許看到哪些檔案」的白名單定義），以及一支在 spawn 前依此白名單準備隔離工作目錄的 wrapper。|

### 6-2｜Artifact Schema 完整度是新的單點故障


||內容|
|---|---|
|問題|Context 收斂成幾份固定 artifact 後，任何「原本要靠 agent 自己探索 codebase 才會知道，但 schema 沒定義」的資訊都會被靜默漏掉——問題從「要不要信任 agent 的探索」搬到「schema 設計夠不夠完整」，而後者需要持續維護，不會一次做完就永久有效。|
|ADAD 需求（契約）|每次新增一種會被漏進 artifact 的資訊類型（例如環境變數、外部服務依賴、執行期限制），要有明確流程把它變成 schema 裡的新欄位，而不是讓某個 agent 私下用自然語言硬塞進 `description`。|
|自建 / 現成平台|無差別——這是 ADAD 自己的 schema 治理問題，跟 Kernel 選型無關。|
|強制程度|機械強制部分只到「schema 驗證通過」為止；「schema 本身有沒有涵蓋現實世界該有的欄位」仍然是人類治理責任，機器測不出「欄位還沒被發明」這件事。|
|ADAD 套件必須包含|一份「Schema 缺口回報」機制——`verify_report.json` 或 `task_block` 若偵測到 agent 在自然語言欄位裡描述了本該結構化的資訊（例如用關鍵字比對抓「環境變數」「timeout」這類字眼混在 `description` 裡），標記為 `possible_schema_gap`，交人類 CP-2 審查時順便決定要不要開新欄位。|


### 6-3｜已知代價（刻意取捨，非缺陷）

- **跨模組系統性推理變貴**：邊界切太細，天生要跨多模組才看得懂全貌的任務，會被迫在 依賴宣告（第 5 節 #33）裡塞進越來越多跨 artifact 引用，容易撞上 Context Budget（#45）。
- **round-trip 成本**：少了共享 context，agent 無法在同一 session 內邊摸索邊修正， 每次資訊不足都要走完整「產出 artifact → 驗證失敗 → 打回」循環，靠 `task_block` / `report_blocked`（1-4、#51）緩解，但無法消除。

這條原則不建議取代 1-1～1-7，而是把「讀取邊界」「Task 竄改」這兩個既有已知縫隙的 **修法**明確寫下來，供第 4 節相容性 checklist 逐平台檢查時多加兩條：是否支援每次呼叫 獨立隔離的執行環境？是否有 schema 治理流程避免資訊被自然語言欄位吃掉？

### G. Artifact-Only 邊界缺口

|#|代辦事項|歸屬|優先度|對應第 1／6 節能力|
|---|---|---|---|---|
|52|Agent 執行環境隔離模板尚未實作：需要「artifact 類型 → 允許掛載檔案白名單」定義檔，以及 spawn 前準備隔離工作目錄的 wrapper。|ADAD 定義白名單格式 + Kernel 執行隔離|高——沒有這項，6-0 的機械強制承諾等於空話|6-1|
|53|Schema 缺口回報機制尚未實作：`verify_report.json` / `task_block` 缺少「自然語言欄位疑似藏了該結構化的資訊」偵測，目前只能靠人工 review 發現 schema 該擴充哪裡。|ADAD 定義偵測規則 + Kernel 執行|中|6-2|
