# main 發行分支資料架構

## 目的

`main` 是可發布的 ADAD 套件分支。它只保存套件程式碼、打包資產、測試與使用者文件；不作為 ADAD 套件自身 dogfooding 的工作區。

此邊界以 `75d913d`（`adad-cli` 1.0.0 的首次可安裝套件提交）為基準，並採用目前以 `adad_source/` 管理資產來源的結構。

## 受版控內容

| 區域 | 職責 |
| --- | --- |
| `adad_cli/` | CLI 執行程式與 wheel 內建資源。 |
| `adad_source/` | Agent 資產與初始化模板的唯一來源。 |
| `.agents/` | 由 `adad_source/agents/` 同步的發行資產副本。 |
| `adad_cli/resources/` | 由 `adad_source/` 同步、隨套件發布的資產副本。 |
| `tests/` | 套件行為、資產同步與初始化結果的測試。 |
| `docs/`、`README.md`、`CHANGELOG.md`、`LICENSE` | 使用者與發行文件。 |
| `pyproject.toml`、CI 與 Git 設定 | 打包、驗證與版本控制設定。 |

## 禁止納入 main 的 dogfood 狀態

- 根目錄 `AGENTS.md`
- 根目錄 `system_map.md`、`system_map.yaml`、`system_map.schema.json`
- `checkpoints/`
- ADAD 自身的架構 roadmap、task backlog 與其他由 dogfooding 流程產生的決策／施工紀錄
- 任何 `.agents/tasks/` 或 `.agents/workspaces/` 執行期產物

## 分支責任

- `development`：可保存 ADAD 套件自我開發所需的 maps、checkpoints、任務與改善紀錄。
- `main`：只接收可發布的套件變更；發布前必須移除上述 dogfood 狀態，並維持資產同步。

## 發布驗收

1. `adad_source/` 與 `.agents/`、`adad_cli/resources/` 的受管理資產一致。
2. 受版控樹沒有「禁止納入 main」所列路徑。
3. 套件測試不依賴根目錄 dogfood maps、checkpoint 或 task 狀態。
4. CI 在 `main` 與以 `main` 為目標的 PR 上自動檢查第 2 項；違反即拒絕發布。
