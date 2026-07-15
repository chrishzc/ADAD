# ADAD 發布 SOP

適用於將 `development` 的 ADAD 更新整理為單一套件並發布到 `main`。發布分支不合併 `development`；一律從 `origin/main` 建立乾淨 worktree，再直接帶入本次已驗證的發布檔案。

## 1. 在 development 完成版本與驗證

1. 更新 `adad_cli/__init__.py`、`CHANGELOG.md`、README 徽章的版本號。
2. 編譯架構並檢查來源綁定：

   ```powershell
   .venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\compile_map.py
   .venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\check_source_binding.py
   ```

3. 暫存後執行 gate 與完整測試：

   ```powershell
   git add -A
   .venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\adad_pre_commit.py
   .venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp-release
   ```

   若本版涉及 `sub_maps`，另執行專項測試；必須證明 root／child 分開保存、`FinanceImport` 可由 root context 查得，且連續保存不會把 child 模組倒回 root：

   ```powershell
   .venv\Scripts\python.exe -m pytest tests\test_sub_maps.py -q
   ```

4. 若 gate 只報 `release_changelog` 或 `documentation_alignment` 的 Task 快照過期，重新核發後再跑 gate：

   ```powershell
   .venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\generate_task.py release_changelog
   .venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\generate_task.py documentation_alignment
   ```

   RULE-03 是警告；RULE-02、RULE-04、TASK GATE 錯誤必須先消除。

5. 提交並推送 development：

   ```powershell
   git commit -m "Release ADAD <VERSION>"
   git push origin development
   ```

## 2. 建立乾淨 release worktree

以 `<VERSION>` 取代實際版本，例如 `1.4.2`；以 `<DEV_COMMIT>` 取代剛推送的 development commit。

```powershell
$release = "C:\tmp\ADAD-main-release-<VERSION>"
git worktree add -b "codex/main-release-<VERSION>" $release origin/main

$files = git diff-tree --no-commit-id --name-only -r <DEV_COMMIT>
git -C $release checkout <DEV_COMMIT> -- $files
```

這一步是「直接覆蓋發布檔案」，不是 merge。先檢查範圍：

```powershell
git -C $release status --short
git -C $release diff --cached --check
```

若 `--check` 有 whitespace 錯誤，先在 development 修正並重建 release worktree；不要在 release 分支單獨修出與 development 不一致的版本。

## 3. 在 release worktree 驗證與提交

release worktree 預設沒有 `.venv`，但 Git hook 會使用相對 `.venv\Scripts\python.exe`。建立只供驗證使用的 Junction，指向已驗證的 development 環境：

```powershell
New-Item -ItemType Junction -Path "$release\.venv" -Target "<ADAD_REPO>\.venv"
```

linked worktree 的 commit hook 可能把 `GIT_INDEX_FILE`、`GIT_DIR`、`GIT_WORK_TREE` 等 repo-scoped `GIT_*` 傳給 Verification 子程序。Verification runner 必須清除這些變數，讓子程序依自己的 `cwd` 找 Git repo；不可直接繼承 release index。

巢狀 pytest 建立臨時 Git repo 時，也不得預設繼承外層 job 的 `CI`、`GITHUB_ACTIONS`、`GITHUB_BASE_REF`、`GITHUB_HEAD_REF`、`GITHUB_EVENT_NAME`、`GITHUB_EVENT_PATH`、`GITHUB_REF`、`GITHUB_REF_NAME`、`GITHUB_SHA`。測試 harness 應保留一般環境，但預設移除上述 event context；只有測試明確傳入 override 時才能 opt-in。否則臨時 repo 可能誤走 CI diff，並在沒有 parent commit 時把 `HEAD~1` 當成有效 revision。

最小重現與驗收：在外層設定 `CI=true`、空的 `GITHUB_BASE_REF`，於只有初始 commit 的臨時 repo 執行 pre-commit 測試；預設隔離必須成功，明確 opt-in 測試則必須看得到指定的 CI context。完成本機 pytest 後仍須確認同一 release commit 的 GitHub Actions 成功；本機通過不能取代 Actions 驗收。

執行完整驗證與正常提交：

```powershell
Push-Location $release
<ADAD_REPO>\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp-release
<ADAD_REPO>\.venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\adad_pre_commit.py
git commit -m "Release ADAD <VERSION>"
Pop-Location
```

測試前後都檢查 index，禁止出現 `sample_tool.py`、`second_tool.py` 或其他 fixture 假檔：

```powershell
git -C $release diff --cached --name-only
```

若發現污染，只移除已確認的假路徑，再從已驗證 commit 重建正式檔案：

```powershell
git -C $release rm --cached --ignore-unmatch -- sample_tool.py second_tool.py
$files = git diff-tree --no-commit-id --name-only -r <DEV_COMMIT>
git -C $release checkout <DEV_COMMIT> -- $files
git -C $release diff --cached --check
```

禁止使用 `git reset` 或 `--no-verify`。若 hook 不能啟動，先確認 Junction 與 `.venv\Scripts\python.exe` 存在。

## 4. GitHub Actions 前置條件

push workflow 的 `GITHUB_BASE_REF` 可能存在但為空字串；hook 必須以 `HEAD~1` fallback，不得組成無效的 `origin/`。checkout workflow 必須保留完整歷史：

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
```

## 5. 發布 main 並驗收 Actions

```powershell
git -C $release push origin HEAD:main
git branch -f main origin/main

gh run list --branch main --commit <RELEASE_COMMIT> --limit 5
gh run view <RUN_ID> --exit-status
```

`gh run view --exit-status` 成功後才能安裝本機套件及執行外部專案 upgrade；不得用尚未通過 Actions 的 build 覆蓋本機工具。Actions 失敗時保留 release worktree 與日誌，建立修正 Task，不得宣告完成。

## 6. 安裝本機版本與外部專案 upgrade 驗收

先安裝已通過 Actions 的 release commit：

```powershell
Push-Location $release
<ADAD_REPO>\.venv\Scripts\python.exe -m pip install --upgrade .
<ADAD_REPO>\.venv\Scripts\adad.exe --version
Pop-Location
```

不得直接拿使用者正在開發的專案試升級。從含 `sub_maps` 的外部專案建立乾淨副本 `<UPGRADE_COPY>`，確認 `git status --short` 為空：

```powershell
git clone --local <EXTERNAL_REPO> <UPGRADE_COPY>
git -C <UPGRADE_COPY> status --short
```

再記錄升級前資料：

- root `system_map.yaml` 的 `modules` 數量。
- 每個 child YAML 的 `modules` 數量與 root 的 `sub_maps` mapping。
- `FinanceImport` 只存在於預期 child，不存在於 root `modules`。

在乾淨副本執行：

```powershell
Push-Location <UPGRADE_COPY>
<ADAD_REPO>\.venv\Scripts\adad.exe upgrade
<ADAD_REPO>\.venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\read_context.py FinanceImport
<ADAD_REPO>\.venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\compile_map.py
<ADAD_REPO>\.venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\compile_map.py
git status --short
Pop-Location
```

兩次 compile 後逐項比對：root／各 child 的 module count 與升級前完全相同；root 的 `sub_maps` mapping 不變；`FinanceImport` context 成功且 owner／`map_file` 指向預期 child；root 不得吸收 child 模組。第二次 compile 不得產生額外 diff。任一項不符即視為發布失敗，不得在真實外部專案執行 upgrade。

最後確認：GitHub `main` 指向 release commit、`adad --version` 顯示 `<VERSION>`、完整 pytest 與 Actions 均通過，外部專案乾淨副本的 upgrade／context／重複 compile 驗收全數通過。

## 7. 最小故障排查

每個故障最多進行 2 次「修正＋驗證」：

1. 先記錄失敗指令、exit code、首個有效錯誤與 `git status --short`。
2. 只修正已確認的單一原因，重跑原失敗指令及必要 gate。
3. 第 2 次仍失敗即停止，保留 diff、index、worktree 與 Actions run ID，建立 Task／Checkpoint，不再試錯。

常見檢查順序：Junction 與 Python 路徑 → release index 假檔 → repo-scoped `GIT_*` 洩漏 → 巢狀測試繼承外層 CI event context → `GITHUB_BASE_REF` 空值與 fetch depth → sub_maps root／child count 與 owner → Actions 日誌。

## 8. 清理

`.venv` Junction 只存在於 `C:\tmp` 的 release worktree，不能對它使用 `Remove-Item -Recurse`。完成後可保留 worktree 供稽核；若要清理，先確認它仍是 Junction，再移除 link 本身，不得遞迴刪除 target 的實體 `.venv`。
