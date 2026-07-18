## 2. 平台專屬 Instruction / Skill 包

上面表裡出現三次「只能靠 instruction/skill 檔引導」，這件事不能只寫一份泛用文字，
因為每個平台載入指示的機制跟優先權不一樣。ADAD 套件裡要對每個目標平台各維護一份，
**內容邏輯相同、格式對應平台**：

| 平台 | 對應檔案 | 放什麼 |
|---|---|---|
| Claude Code | `CLAUDE.md` / project instructions | 讀取邊界規則、blocked 回報格式、何時該呼叫 harness 腳本 |
| Antigravity | Skill 檔 + project 設定 | 同上內容,包成 Antigravity 的 skill 格式,並在 project 設定裡限制 MCP 工具白名單 |
| Codex CLI | 對應的 agent instructions 檔 | 同上內容 |

**這幾份檔案的內容要來自同一份 single source of truth**（例如一份 YAML/JSON 定義
「讀取邊界規則」「blocked 格式」），用小腳本轉譯成三種平台各自的檔案格式，避免三份
文件手動維護、將來對不齊。

---
