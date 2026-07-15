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

## 5. 發布 main、驗收 Actions 並更新本機

```powershell
git -C $release push origin HEAD:main
git branch -f main origin/main

gh run list --branch main --commit <RELEASE_COMMIT> --limit 5
gh run view <RUN_ID> --exit-status

Push-Location $release
<ADAD_REPO>\.venv\Scripts\python.exe -m pip install --upgrade .
<ADAD_REPO>\.venv\Scripts\adad.exe --version
Pop-Location
```

`gh run view --exit-status` 成功後才能宣告發布完成。Actions 失敗時保留 release worktree 與日誌，建立修正 Task，不得宣告完成。最後確認：GitHub `main` 指向 release commit、`adad --version` 顯示 `<VERSION>`、完整 pytest 與 Actions 均通過。

## 6. 最小故障排查

每個故障最多進行 2 次「修正＋驗證」：

1. 先記錄失敗指令、exit code、首個有效錯誤與 `git status --short`。
2. 只修正已確認的單一原因，重跑原失敗指令及必要 gate。
3. 第 2 次仍失敗即停止，保留 diff、index、worktree 與 Actions run ID，建立 Task／Checkpoint，不再試錯。

常見檢查順序：Junction 與 Python 路徑 → release index 假檔 → repo-scoped `GIT_*` 洩漏 → `GITHUB_BASE_REF` 空值與 fetch depth → Actions 日誌。

## 7. 清理

`.venv` Junction 只存在於 `C:\tmp` 的 release worktree，不能對它使用 `Remove-Item -Recurse`。完成後可保留 worktree 供稽核；若要清理，先確認它仍是 Junction，再移除 link 本身，不得遞迴刪除 target 的實體 `.venv`。
