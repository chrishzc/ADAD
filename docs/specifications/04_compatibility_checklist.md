## 4. 導入新 Kernel/平台時的相容性 Checklist

每次要把 ADAD 套件接到一個新的 agent 平台上（不管是自建還是換一家現成平台），跑一次
這張表，誠實記錄每一項是「機械強制」還是「降級為指示性建議」，寫進專案的風險登記：

- [ ] 平台是否支援自訂 MCP tool？ → 決定 1-4（blocked 回報）能不能做到強制
- [ ] 平台是否支援 PostToolUse 等級的 hook？ → 決定 1-3（Harness）是即時擋還是只能 pre-commit/CI 事後擋
- [ ] 平台是否支援檔案級/MCP 工具白名單？ → 決定 1-2（讀取邊界）是可設定還是純指示
- [ ] 平台是否有結構化輸出保證（如 Antigravity 的 Artifacts）？ → 決定 1-7 格式驗證要不要額外加重試邏輯
- [ ] 是否所有「迴圈外」項目（1-1、1-5、1-6）都能在 spawn agent session 之前/之後正常呼叫本地腳本？ → 這幾項理論上任何平台都該打勾，打不了勾代表這平台連當 Kernel 的基本資格都不夠
- [ ] 平台執行本地 Python 時是否能用 argv 陣列、UTF-8 strict 與明確 cwd，而非 shell command 字串？ → 否則 Windows quoting／CP950 與 POSIX shell 行為可能分歧
- [ ] hook command 是否固定使用目標專案 `.venv`，並分別採 Windows CreateProcess 與 POSIX shell 的安全引用規則？ → 禁止退回全域 `python`／`python3`／目前程序的 `sys.executable`
- [ ] 平台是否能嚴格讀寫 UTF-8，並以同目錄暫存檔原子替換設定？ → 解析失敗時必須保留原檔，不能用空設定覆寫
- [ ] 版本庫是否有 `.gitattributes` 明定 LF／CRLF 與二進位檔政策？ → 避免 checkout 換行差異造成架構過期、資產同步或 hash 誤判
- [ ] Windows、macOS、Linux 是否都測過 POSIX absolute、Windows drive-relative／drive-qualified、UNC 與 `..` 路徑逃逸？ → 路徑安全判斷不得只依賴目前宿主 OS

**沒打勾的項目，不要在文件裡寫「保證」兩個字**，要如實寫「本平台上此項為建議性質，
需要人類 review 補位」——這樣 CP-2 Review 的人才知道哪些地方要多看一眼，而不是被
文件的機械強制措辭誤導成以為已經有保障。

---
