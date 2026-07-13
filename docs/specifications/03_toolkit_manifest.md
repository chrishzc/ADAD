## 3. ADAD 套件清單（最終交付物）

把以上收斂成一張清單，這是「不管 Kernel 是誰都要帶著走」的東西：

```
adad-toolkit/
├── core/
│   ├── generate_task.py          # 1-1，Kernel-agnostic
│   ├── task_schema.json          # 1-1
│   ├── checkpoint.py             # 1-5，Kernel-agnostic（approve 原子操作）
│   ├── adad_task.py               # 1-6，前置 Permission 檢查 wrapper
│   └── validate_schema.py        # 1-7，Architecture Proposal 格式驗證
├── harness/
│   ├── check_invariants.py       # 1-3，獨立可執行
│   ├── verify_implementation.py  # 1-3，獨立可執行
│   └── check_normalization.py    # 1-7，可包成 MCP tool 或 CLI
├── blocked_report/
│   ├── blocked_report.schema.json # 1-4 備援格式
│   ├── report_blocked_mcp/        # 1-4，最小 MCP server 實作
│   └── extract_blocked_from_text.py # 1-4 備援 parser
├── platform_instructions/
│   ├── source.yaml                # 單一事實來源：讀取邊界規則+blocked格式+何時跑harness
│   ├── render_claude_md.py        # 轉譯成 CLAUDE.md
│   ├── render_antigravity_skill.py
│   └── render_codex_instructions.py
└── compat_checklist.md            # 見第 4 節
```

---
