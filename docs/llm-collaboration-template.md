# LLM 協作規範（模板）

> 目的：讓任何 LLM 在本專案內接任務時，遵守同一套可驗證的輸入輸出規格，降低「猜測」與格式/編碼異常風險。

## 1) 可直接貼到 LLM 的 System Prompt 模板

```text
你現在只負責在本專案 ADAD 中進行程式/文件協作，請遵守以下硬性規範：

1) 唯一事實來源
- 只依據 root/system_map.yaml 與目前 task 規格與 checkpoints 進行操作。
- 不新增、修改、推測未在 system_map.yaml 中定義的介面、欄位、路由、參數、行為。

2) 原子範圍
- 每次只修改單一節點（單一函式/API/元件範圍）。
- 不跨模組大規模重構，不順手整理無關代碼。

3) 介面與狀態門禁
- 只可變更 system_map.yaml 中允許狀態的節點，否則停止並回報阻塞。
- 發現需求與現有規格不一致，直接回報「Schema Update Request」，停止繼續修改。

4) 文字/編碼規格
- 所有新建或更新的文字檔案皆採 UTF-8（建議無 BOM）。
- 讀檔時使用 strict UTF-8；不可使用 errors=ignore 或 errors=replace 隱藏問題。
- 涉及中文、註解、錯誤訊息時，保留完整字符，不做亂碼修補。

5) 寫檔規格
- 所有檔案寫入時明確指定 encoding="utf-8"。
- Python 輸出需使用 pathlib.open / open(..., encoding="utf-8")。

6) 回報格式
- 回覆要可追蹤：列出「修改檔案、修改原因、影響範圍、風險」。
- 如改動超過 1 個檔案，先確認是否仍屬同一節點；否則先停止等待人類指示。

7) 錯誤處理原則
- 若 pre-commit / 驗證會議失敗，先修正錯誤，不繞過檢查，不回退到規格外方式。
```

## 2) Pre-commit 檢查條款（可直接加到 hook 流程）

### A. 字元與編碼
1) 嚴格 UTF-8 檔案掃描
- 針對 staged 的文本檔（`*.py`、`*.md`、`*.yaml`/`*.yml`、`*.toml`、`*.json`、`*.cfg` 等）逐檔 decode(`utf-8`)。
- 發生 `UnicodeDecodeError` 時直接 fail，輸出檔名與位元序位置資訊（`hex byte`）供修正。

2) 斷言關鍵檔不得混入壞字元
- 禁止在 `AGENTS.md`、`system_map.yaml/md`、`*.py` 中出現非 UTF-8 bytes。
- 發現壞字元時要求落盤修復再 retry commit。

### B. 規格與狀態（ADAD）
3) SSOT 與版本新鮮度
- `system_map.yaml` 必須為最新版本來源，若有 `system_map.md` 更新但 yaml 舊版則阻斷。

4) 狀態門禁
- 目標節點未授權狀態一律阻斷（aligned with RULE-02）。

5) 原子化範圍警示
- 跨節點變更出現時輸出 warning；必要跨節點時需人工批准。

6) Invariants / Verification
- 必要 assertions 規範與 import 邊界不符時阻斷。

### C. 其他質控
7) 不允許的工具行為
- 禁止隱式編碼容錯（`errors=ignore`、`encoding` 未指定等）出現在新增/修改程式碼裡。
- 檢查 commit 中是否有「明顯壞格式」或可疑自動改寫痕跡（如亂碼片段）。

## 3) 風險處理流程（失敗時）
- 若 pre-commit 報編碼錯誤：先修正檔案 encoding，不允許先提交再補資料。
- 若規格衝突：提交「Schema Update Request」並停止實作，待 Checkpoint 批示。

## 4) 推薦落地
- 在任務交接時要求 LLM 回覆先貼上「System Prompt 逐條遵守情形」。
- 於 `AGENTS.md`/技能文件加上上述條款參考，與 pre-commit 形成「流程 + 機械」雙重守門。
- 於 `.github`/CI 及 local pre-commit 中複用同一套條款，避免只在本地通過、CI 違規。
