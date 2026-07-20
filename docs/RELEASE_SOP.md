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

以 `<VERSION>` 取代實際版本，例如 `1.6.0`；以 `<DEV_COMMIT>` 取代剛推送的 development commit。先解析 commit、更新 `origin/main`，再判斷 main 是否為 development snapshot 的祖先：

```powershell
$release = "C:\tmp\ADAD-main-release-<VERSION>"
$devCommit = (git rev-parse --verify "<DEV_COMMIT>^{commit}").Trim()
if ($LASTEXITCODE -ne 0) { throw "DEV_COMMIT 無法解析" }

git fetch origin main
git merge-base --is-ancestor origin/main $devCommit
$ancestorExit = $LASTEXITCODE
if ($ancestorExit -ne 0 -and $ancestorExit -ne 1) {
    throw "無法判斷 origin/main 與 DEV_COMMIT 的 ancestry"
}

if ($ancestorExit -eq 0) {
    # main 是祖先：直接以完整 development snapshot 建立 release branch。
    git worktree add -b "codex/main-release-<VERSION>" $release $devCommit
    $snapshotNeedsCommit = $false
} else {
    # main/development 已分歧：從乾淨 main 建立完整 tracked-tree snapshot。
    git worktree add -b "codex/main-release-<VERSION>" $release origin/main
    if (git -C $release status --porcelain) { throw "release worktree 不乾淨" }
    git -C $release read-tree --reset -u $devCommit
    $snapshotNeedsCommit = $true
}

git -C $release diff --cached --quiet $devCommit --
if ($LASTEXITCODE -ne 0) { throw "release index 不等於 DEV_COMMIT tracked tree" }
```

目前 `main` 與 `development` 已分歧，因此只有 ancestry 檢查成功時才能直接 fast-forward；分歧時禁止 force push，必須在已確認乾淨的 main worktree 以 `read-tree` 建立 snapshot，之後產生一個以 main 為 parent、tree 完全等於 `$devCommit` 的 release commit。

這是完整 tracked-tree snapshot，不是 merge，也不是只取最後一個 commit。它涵蓋 development 累積的新增、修改與刪除，避免漏掉 `tests/conftest.py` 等較早 commit。驗證必須針對完整 cumulative diff 與 snapshot tree，不得使用 `git diff-tree -r <DEV_COMMIT>` 推導發布清單。

先檢查範圍：

```powershell
git -C $release status --short
git -C $release diff --cached --check
```

若 `--check` 有 whitespace 錯誤，先在 development 修正並重建 release worktree；不要在 release 分支單獨修出與 development 不一致的版本。第 3 節的 `git commit` 只在 `$snapshotNeedsCommit` 為 `$true` 時執行；若為 `$false`，驗證後直接將 `$devCommit` fast-forward 推送至 main，此時 main tree 必須等於 development snapshot。

## 3. 在 release worktree 驗證與提交

release worktree 預設沒有 `.venv`，但 Git hook 會使用相對 `.venv\Scripts\python.exe`。建立只供驗證使用的 Junction，指向已驗證的 development 環境：

```powershell
$adadRepo = 'C:\path\to\ADAD'
New-Item -ItemType Junction -Path "$release\.venv" -Target "$adadRepo\.venv"
```

linked worktree 的 commit hook 可能把 `GIT_INDEX_FILE`、`GIT_DIR`、`GIT_WORK_TREE` 等 repo-scoped `GIT_*` 傳給 Verification 子程序。Verification runner 必須清除這些變數，讓子程序依自己的 `cwd` 找 Git repo；不可直接繼承 release index。

巢狀 pytest 建立臨時 Git repo 時，也不得預設繼承外層 job 的 `CI`、`GITHUB_ACTIONS`、`GITHUB_BASE_REF`、`GITHUB_HEAD_REF`、`GITHUB_EVENT_NAME`、`GITHUB_EVENT_PATH`、`GITHUB_REF`、`GITHUB_REF_NAME`、`GITHUB_SHA`。測試 harness 應保留一般環境，但預設移除上述 event context；只有測試明確傳入 override 時才能 opt-in。否則臨時 repo 可能誤走 CI diff，並在沒有 parent commit 時把 `HEAD~1` 當成有效 revision。

最小重現與驗收：在外層設定 `CI=true`、空的 `GITHUB_BASE_REF`，於只有初始 commit 的臨時 repo 執行 pre-commit 測試；預設隔離必須成功，明確 opt-in 測試則必須看得到指定的 CI context。完成本機 pytest 後仍須確認同一 release commit 的 GitHub Actions 成功；本機通過不能取代 Actions 驗收。

執行完整驗證與正常提交：

```powershell
$adadRepo = 'C:\path\to\ADAD'
Push-Location $release
& "$adadRepo\.venv\Scripts\python.exe" -m pytest -q --basetemp .pytest-tmp-release
& "$adadRepo\.venv\Scripts\python.exe" .agents\skills\adad-workflow\scripts\adad_pre_commit.py
if ($snapshotNeedsCommit) {
    git commit -m "Release ADAD <VERSION>"
}
Pop-Location
```

測試前後都檢查 index，禁止出現 `sample_tool.py`、`second_tool.py` 或其他 fixture 假檔：

```powershell
git -C $release diff --cached --name-only
```

若發現污染，只移除已確認的假路徑，再從完整 development snapshot 重建 index 與 worktree：

```powershell
git -C $release rm --cached --ignore-unmatch -- sample_tool.py second_tool.py
git -C $release read-tree --reset -u $devCommit
git -C $release diff --cached --quiet $devCommit --
if ($LASTEXITCODE -ne 0) { throw "污染恢復後 index 不等於 DEV_COMMIT tracked tree" }
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

$releaseCommit = (git -C $release rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "無法解析 release commit" }

$runId = gh run list --branch main --commit $releaseCommit --limit 1 --json databaseId --jq '.[0].databaseId'
if ($LASTEXITCODE -ne 0 -or -not $runId) { throw "找不到 release commit 對應的 Actions run" }
gh run view $runId --exit-status
```

`gh run view --exit-status` 成功後才能安裝本機套件及執行外部專案 upgrade；不得用尚未通過 Actions 的 build 覆蓋本機工具。Actions 失敗時保留 release worktree 與日誌，建立修正 Task，不得宣告完成。

## 6. 安裝本機版本與外部專案 upgrade 驗收

先安裝已通過 Actions 的 release commit：

```powershell
$adadRepo = 'C:\path\to\ADAD'
Push-Location $release
& "$adadRepo\.venv\Scripts\python.exe" -m pip install --upgrade .
& "$adadRepo\.venv\Scripts\adad.exe" --version
Pop-Location
```

同一個步驟也必須更新「使用者層級」的 `adad` 命令；它是外部專案未安裝
`adad-cli` 時實際解析到的 CLI。不要使用外部專案的 `.venv\Scripts\python.exe`，
否則只會更新單一專案而非全域命令。以下命令會透過 Windows Python Launcher
選取使用者 Python、從已驗證的 release worktree 安裝，並直接驗證該使用者
Scripts 目錄內的 `adad.exe`：

```powershell
Push-Location $release
$globalPython = (py -3 -c "import sys; print(sys.executable)").Trim()
if (-not $globalPython) { throw "找不到使用者 Python；無法更新全域 adad CLI" }
$userScripts = (& $globalPython -c "import sysconfig; print(sysconfig.get_path('scripts', scheme='nt_user'))").Trim()
if (-not $userScripts) { throw "無法解析使用者 Python Scripts 目錄" }

& $globalPython -m pip install --user --upgrade .
if ($LASTEXITCODE -ne 0) { throw "全域 adad-cli 升級失敗" }

$globalAdad = Join-Path $userScripts 'adad.exe'
if (-not (Test-Path -LiteralPath $globalAdad)) { throw "找不到更新後的全域 adad.exe: $globalAdad" }
& $globalAdad --version
if ($LASTEXITCODE -ne 0) { throw "全域 adad CLI 版本驗證失敗" }
Pop-Location
```

外部專案不應在自身 `pyproject.toml` 宣告 `adad-cli`。若專案已有
`.venv\Scripts\adad.exe`，它會在啟用 venv 後優先於上述全域 CLI；必須一併
升級該 venv 的套件，或移除過時的專案層安裝後再驗證 `Get-Command adad`。

不得直接拿使用者正在開發的專案試升級。從含 `sub_maps` 的外部專案建立乾淨副本 `<UPGRADE_COPY>`，確認 `git status --short` 為空：

```powershell
$externalRepo = 'C:\path\to\external-project'
$upgradeCopy = 'C:\tmp\external-project-upgrade-copy'
git clone --local $externalRepo $upgradeCopy
git -C $upgradeCopy status --short
```

再記錄升級前資料：

- root `system_map.yaml` 的 `modules` 數量。
- 每個 child YAML 的 `modules` 數量與 root 的 `sub_maps` mapping。
- `FinanceImport` 只存在於預期 child，不存在於 root `modules`。

在乾淨副本執行：

```powershell
$adadRepo = 'C:\path\to\ADAD'
$upgradeCopy = 'C:\tmp\external-project-upgrade-copy'
Push-Location $upgradeCopy
& "$adadRepo\.venv\Scripts\adad.exe" upgrade
& "$adadRepo\.venv\Scripts\python.exe" .agents\skills\adad-workflow\scripts\read_context.py FinanceImport
& "$adadRepo\.venv\Scripts\python.exe" .agents\skills\adad-workflow\scripts\compile_map.py
& "$adadRepo\.venv\Scripts\python.exe" .agents\skills\adad-workflow\scripts\compile_map.py
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
