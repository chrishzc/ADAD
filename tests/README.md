# ADAD 測試套件

對應「規格總覽.md」代辦事項 **#5**：`adad_cli/resources/.../scripts/` 底下的
CLI 腳本原本完全沒有自動化測試覆蓋，只有 `adad_core.py` 內建一份用 `assert`
手刻的自我測試（`run_self_test()`）。這裡補上一套 pytest 測試，覆蓋每支獨立
CLI 腳本的輸入/輸出契約與主要錯誤路徑。

## 安裝與執行

```bash
pip install -e ".[dev]"   # 安裝 pytest（開發用相依）
pytest                    # 在 repo 根目錄執行整套測試
pytest tests/test_compile_map.py   # 只跑單一檔案
pytest -k invariants               # 只跑名稱含 invariants 的測試
```

`pyproject.toml` 已加入 `[tool.pytest.ini_options] testpaths = ["tests"]`，
在 repo 根目錄直接執行 `pytest` 就會自動找到這個目錄，不需要額外參數。

## 設計原則

- **黑箱測試，不是白箱**：每支腳本都是這個專案刻意設計成「不依賴任何特定
  平台呼叫方式」的獨立 CLI（見「規格總覽.md」1-3）。所以測試策略是用
  `subprocess` 實際呼叫腳本、餵真實參數／stdin，檢查 stdout（多半是 JSON）
  與 exit code，而不是 `import` 內部函式繞過 CLI 邊界。這樣測試驗證的是
  「使用者或 agent 真正呼叫時會發生什麼事」，跟平台整合時的行為一致。
- **每個測試在乾淨的 `tmp_path` 假專案裡跑**：透過 `project_dir` fixture
  把 cwd 切到一個臨時目錄，不會動到真正的 `system_map.md` / `system_map.yaml`，
  測試之間也不會互相污染。
- **`adad_core.py` 的細節分支交給它自己內建的 `run_self_test()`**：那份自我
  測試已經覆蓋 DAG 級聯、Rule of Two 相似度、Task 生命週期、Draft Debt
  Ledger、include 分區地圖等很細的邏輯分支。`test_adad_core_selftest.py`
  只是把它接進 pytest 可以自動發現、CI 可以自動執行的範圍（用子行程呼叫
  `python adad_core.py --test`），不重新刻一遍同樣的案例。
- **`adad_pre_commit.py` 用真的 git repo 測**：這支腳本的核心邏輯是讀
  `git diff --cached` / `git show :0:<path>`（staged/index 內容，不是工作
  目錄），沒辦法脫離 git 測試出真正有意義的行為，所以 `test_adad_pre_commit.py`
  的 `git_repo` fixture 會在 `tmp_path` 裡真的 `git init`。

## 涵蓋範圍

| 測試檔案 | 對應腳本 |
|---|---|
| `test_read_context.py` | `read_context.py` |
| `test_check_normalization.py` | `check_normalization.py` |
| `test_analyze_cascade.py` | `analyze_cascade.py` |
| `test_transit_state.py` | `transit_state.py` |
| `test_generate_task.py` | `generate_task.py` |
| `test_check_invariants.py` | `check_invariants.py` |
| `test_verify_implementation.py` | `verify_implementation.py` |
| `test_adad_task.py` | `adad_task.py`（submit / approve / reject） |
| `test_check_domain_boundary.py` | `check_domain_boundary.py` |
| `test_validate_schema.py` | `validate_schema.py` |
| `test_compile_map.py` | `compile_map.py` |
| `test_resolve_target_file.py` | `resolve_target_file.py` |
| `test_resume_analysis.py` | `resume_analysis.py` |
| `test_adad_pretooluse_gate.py` | `adad_pretooluse_gate.py` |
| `test_adad_pre_commit.py` | `adad_pre_commit.py`（RULE-01~05、Invariants、Verification、懸空依賴） |
| `test_adad_core_selftest.py` | `adad_core.py`（接上既有的 `run_self_test()`） |

`adad_task.py` 的 approve/reject 在測試環境下透過 `subprocess` 呼叫，stdin
天生不是互動終端機，這正好拿來驗證「非 tty 一律拒絕、防止 Agent 自我核准」
這個關鍵行為——不需要另外模擬 tty。

## 已知限制 / 尚未覆蓋

- 沒有覆蓋 Windows 路徑分隔符（`\\`）相關的正規化邏輯分支，目前只在
  Linux/macOS 風格路徑下測試。
- `check_module_placement`（RULE-05，模組落點校驗）與 include 分區地圖
  （`<!-- include ... -->` 巢狀展開）沒有另外寫黑箱測試，這兩塊的分支邏輯
  已被 `adad_core.py` 內建的 `run_self_test()` 覆蓋（見上方 `test_adad_core_selftest.py`
  的說明），這裡不重複。
- 尚未接上 CI（「規格總覽.md」#6，屬於下一項待辦，這裡先不動）。
- 本次執行環境無法連網安裝 `pytest`，所有測試都已經過人工核對腳本原始碼
  與手動模擬執行驗證邏輯正確，但尚未實際跑過 `pytest` 本體；請在有網路的
  環境安裝後執行一次確認（正常預期應該全數通過）。
