<p align="center">
  <img src="docs/assets/robot.png" alt="ADAD — Architecture is the only truth." width="100%">
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-2DD4BF">
  <img alt="Version" src="https://img.shields.io/badge/version-1.0.0-38BDF8">
  <img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-3776AB">
  <img alt="Built for" src="https://img.shields.io/badge/built%20for-Antigravity-F5A623">
  <img alt="PRs" src="https://img.shields.io/badge/PRs-welcome-brightgreen">
</p>

# 📋 ADAD (Architecture-Driven Agentic Development) 開發規範與工具鏈

本專案是一個專為 **Antigravity AI Agent** 設計的 Workspace Customization 擴充套件，旨在實行 **ADAD (架構驅動型智能體開發)** 開發模式。

ADAD 的核心理念是：**將「系統設計（架構）」與「程式碼實作（邏輯）」徹底解耦**。由人類把持高價值的架構與驗收 Checkpoint，並指派 Agent 在最小 Context 的約束下進行高精度的原子程式碼生成，以防範 AI 開發中的架構失控與 Context 膨脹問題。

## 🧭 為什麼你會需要 ADAD

**模型能力不是決定輸出品質的唯一因素。** 就算換上更強的模型，只要沒有機制約束「架構認知」，AI agent 在多輪修改之後還是會開始亂猜、亂改介面、偷改別人依賴的模組——問題不是模型不夠聰明，是它從頭到尾都沒有一份雙方都要遵守的唯一事實來源可以對照。ADAD 把架構寫成人類與 Agent 共同遵守的合約，用機械化的 pre-commit hook 擋下不合規的變更，而不是寄望 AI 每次都自律。

**架構維持清晰，你不用每次都重新解釋一遍給 Agent 聽。** `system_map.md` 是唯一事實來源，Agent 只讀編譯過的乾淨版本；改一次，全專案的架構認知就同步，不必在每個 prompt 裡重新貼一次背景脈絡。

**大型專案不容易長出結構性 bug。** Draft Debt Ledger 會在某個「先求有再求好」的暫時模組被越來越多地方依賴時，自動要求補齊審查；Domain 邊界檢查用 AST 靜態擋下違規的跨模組 import。架構不會腐化，因為它是被系統結構性擋下來的，不是靠人力盯出來的。

---

## 📐 三層事實流架構 (Three-Layer Facts Flow)

為了將架構演進的「靈活性」與 Agent 生成的「高精準度」完美結合，本專案採用三層事實流設計：

```
    Human Intent
         ↓
  system_map.md          (Architecture Source) ➔ 人類與 Agent 共同設計，支援逐步展開、TODO、決策記錄等
         ↓
      Compile            (compile_map.py)      ➔ 自動進行格式驗證、生命週期狀態繼承與 dirty 判定
         ↓
  system_map.yaml        (Architecture IR)     ➔ 僅供 Agent 讀取上下文與執行工具，禁止人工編輯
         ↓
  Code Generation        (Implementation)      ➔ 依據 YAML (IR) 產生高質量的原子代碼
```

*   **system_map.md (Architecture Source)**：專為人類與 Agent 協同設計的 Markdown 文件。支援 TODO、Checkpoint、Design Decision、Alternative 等內容。允許暫存、未完成與逐步擴充。
*   **system_map.yaml (Architecture IR)**：完全由編譯器（Compiler）從 Markdown 產生的中間表示檔。用途只有 Context 載入、DAG 依賴分析、Rule of Two 正規化檢查與狀態機執行，**嚴禁人工直接編輯**。
*   **過期自動阻斷**：如果 `system_map.md` 的修改時間晚於 `system_map.yaml`，核心引擎將自動阻斷所有查詢指令（如 `read_context.py`）並要求重新編譯，以確保事實一致性。

---

## 📂 專案目錄結構

> 👉 下方的 `pyproject.toml` 就是 **`pip install .` 指令要認的那個檔案**。
> 只要你所在的資料夾能看到這個檔案，代表這裡就是本 repo 根目錄，
> 也就是應該執行 `pip install .` 的位置。

```
ADAD/                # ← repo 根目錄，pip install . 要在這裡執行
├── adad_cli/                      # `adad` CLI 套件原始碼（pip install . 實際安裝的內容）
│   ├── cli.py                     # 指令定義 (adad init / remove / global / pack)
│   ├── core.py                    # 對應每個指令的實際邏輯
│   ├── resources.py               # 定位套件內建範本檔（不依賴使用者執行指令當下的 cwd）
│   └── resources/                 # 內建範本：agents/（.agents 內容）與 templates/（各種預設檔）
├── pyproject.toml                 # 套件設定：定義了 `adad` 這個可執行指令 (project.scripts)
├── install.py                     # [已棄用] 舊版進入點，轉發呼叫到 adad_cli，保留相容性
├── .agents/                       # 本 repo 自身開發時使用的 Workspace Customizations
│   ├── AGENTS.md                  # Antigravity Rules (定義四大全局規則與 CP 決策限制)
│   └── skills/
│       └── adad-workflow/         # ADAD 輔助工具技能（與 adad_cli/resources/agents 內容一致）
│           ├── SKILL.md           # Skill 定義與 Antigravity 調用引導
│           └── scripts/           # Antigravity 藉由 run_command 執行的輔助 Python 腳本
│               ├── adad_core.py   # 核心引擎 (Markdown 解析、IR 讀寫、DAG 分析、過期阻斷)
│               ├── compile_map.py # Architecture Compiler (Markdown ➔ YAML 狀態合併 + Draft Debt 偵測)
│               ├── resume_analysis.py # Resume 分析器 (進度統計、智能下一步建議、Draft Debt Ledger)
│               ├── adad_pre_commit.py # Pre-Commit Hook (機械強制 RULE-01/02/03 + Invariants + Verification)
│               ├── read_context.py
│               ├── check_normalization.py
│               ├── analyze_cascade.py
│               ├── transit_state.py
│               ├── verify_implementation.py # 實作校驗器 (驗證 Verification 條件如斷言)
│               └── check_invariants.py # Invariants 校驗器 (驗證靜態 AST 導入約束)
├── checkpoints/                   # Checkpoint 決策歷史存檔目錄 (CP-X-XXX.yaml)
├── system_map.md                  # 專案架構唯一事實來源 (SSOT - Architecture Source)
├── system_map.yaml                # 專案架構中間表示檔 (SSOT - Architecture IR)
└── README.md                      # 本說明文件
```

> 💡 `.agents/` 是這個 repo「自己開發自己」時用的 ADAD 專案結構（dogfooding）；
> `adad_cli/resources/agents/` 則是**打包進 `adad` 套件、會被複製到其他專案**的版本。
> 兩者內容一致，只是用途不同——一個是「本 repo 自舉」，一個是「發佈給別人用」。

---
## 🚀 快速上手

### 步驟 0：安裝 `adad` 命令列工具（只需做一次）

> ⚠️ **`pip install .` 一定要在「這個 repo 的根目錄」（也就是 `pyproject.toml` 所在的那一層）
> 執行，`.` 才會正確代表「目前這個資料夾」。**
> 如果在別的地方（例如你自己的專案目錄、或 repo 外層）執行 `pip install .`，
> pip 會去讀「你當下所在資料夾」的 `pyproject.toml`，通常會直接報錯找不到檔案，
> 或裝到完全不相干的東西。

```bash
git clone <repo-url>
cd ADAD                  # 進入本 repo 根目錄——這裡要能看到 pyproject.toml
ls pyproject.toml         # (可省略) 確認自己站對位置，能看到檔案就代表位置正確
pip install .             # 只在這裡執行一次；或用 pipx install . 取得獨立、不污染全域 site-packages 的安裝
```

`pip install .` 中的 `.` 代表「安裝目前這個目錄底下的套件」，pip 會依照這裡的
`pyproject.toml` 把 `adad_cli/` 打包安裝，並在你的 Python 環境（或 venv）的
`bin/`（Windows 為 `Scripts/`）目錄下產生一個 `adad` 可執行檔。

安裝完成後，PATH 上就有了這個真正的 `adad` 指令，**之後可以離開這個 repo，
在任何其他專案目錄下**直接使用 `adad <子指令>`（例如 `adad init`），不需要再記得
`install.py` 放在哪裡、也不需要 `cd` 回這個 repo。

若想確認安裝與 PATH 是否正確，可以執行：
```bash
adad --version
```
如果出現 `command not found: adad`，通常代表 pip 安裝套件的 `bin/`（例如
`~/.local/bin` 或你目前啟用的 venv 的 `bin/`）不在 PATH 裡，需要自行加入，
或改用 `pipx install .`（pipx 會自動處理 PATH 設定）。

若之後修改了 `adad_cli/` 原始碼想立即生效，可改用可編輯模式安裝：
```bash
pip install -e .
```
差別在於 `-e`（editable）安裝後，指令會直接讀取 repo 裡的原始碼，
改完程式碼不用重新 `pip install` 就能測到最新行為，適合開發這個工具本身時使用。

### 步驟 1（必要）：在每個目標專案執行 `adad init`

> ⚠️ **這一步不是「選項之一」，是啟用 ADAD 安全機制的唯一入口。**
> `pip install .`／`pipx install .` 只是把 `adad` 這個指令裝進你的電腦，
> **並不會**對任何專案做任何事。真正把 pre-commit hook 寫進
> `.git/hooks/pre-commit`、建立 `checkpoints/`、`system_map.md` 等安全防線的，
> 是 `adad init`。**沒有對某個專案執行過 `adad init`，那個專案就完全沒有
> ADAD 的機械強制保護**——即使你已經執行過 `adad global install` 也一樣，
> 因為全域安裝影響的是「Antigravity IDE 認不認得這個 skill」，跟「這個
> 專案有沒有裝上 pre-commit hook」是兩件互不相關的事。

1. `cd` 到**任何**想套用 ADAD 架構的專案根目錄（必須已經是 `git init` 過的 repo，
   pre-commit hook 才裝得上去），執行：
   ```bash
   adad init
   ```
   這會建立 `checkpoints/`、`docs/adr`、`docs/patterns`、`system_map.md`（並自動編譯出
   `system_map.yaml`）、`venv/`、`.git/hooks/pre-commit`，**並把 `adad-workflow` skill 的腳本
   複製一份到該專案的 `.agents/skills/adad-workflow/`**，讓這個專案完全自我完備，不必依賴
   全域安裝也能運作。
2. 安裝 Python 依賴：
   ```bash
   venv/bin/pip install -r requirements.txt   # Windows: venv\Scripts\pip install -r requirements.txt
   ```
3. 完成後即可呼叫 ADAD 底層腳本，例如：
   ```bash
   venv/bin/python .agents/skills/adad-workflow/scripts/read_context.py <node_name>
   ```
4. 不再需要 ADAD 時，於該專案目錄執行 `adad remove` 即可還原（移除 venv、pre-commit hook、
   本地 skill 副本）。**`system_map.md`／`system_map.yaml`／`checkpoints/` 這些是你自己的
   架構文件與決策紀錄，預設會保留、不會被刪除**；如果確定要連同這些也一起清掉重來，
   改執行 `adad remove --purge-docs`。

### 步驟 2（可選加碼）：全域安裝至 Antigravity

`adad init` 每個專案都要各自執行一次，這件事不會因為做了下面這步而改變。
這步純粹是**額外的便利功能**：讓 Antigravity IDE 在任何專案裡都能直接看到
ADAD 的 skill 說明與規則，不用等到 `adad init` 之後才看得到。

```bash
adad global install
```

會將 `adad-workflow` Skills 複製到所有已知 Antigravity 全域路徑，並將 ADAD 規則寫入
`~/.gemini/GEMINI.md`。若要移除，執行 `adad global uninstall`。

> 💡 **不想全域安裝？** 完全沒問題，直接跳過這步即可。`adad init` 本身就會把
> skill 腳本複製一份到目標專案內（自我完備），不依賴全域安裝也能正常運作。
> 這個決定跟「要不要 clone 專案進某個地方」無關——你只需要 `pip install .` 過
> 一次（見上方步驟 0），之後在任何電腦上的任何專案都可以直接 `adad init`，
> 不需要把 ADAD 這個 repo 本身 clone 或複製進每一個目標專案裡。
>
> （如果你希望完全不影響全域 Python 環境，正確做法是在**目標專案自己的
> venv 裡**執行 `pip install /path/to/adad-cli`，而不是把 ADAD 的原始碼
> clone 進目標專案資料夾——後者會讓目標專案的 git 裡多出一個巢狀的
> `.git`，追蹤起來會很混亂，不建議這樣做。）

### 步驟 3（之後有新版套件時）：升級已經 init 過的舊專案

`pip install` 升級了套件本身（例如修了 pre-commit hook 的 bug），**不會自動反映到
之前已經 `adad init` 過的專案**——因為那些檔案在當時就已經複製進該專案裡了。
想同步最新版本，到該專案目錄執行：

```bash
adad upgrade
```

只會更新套件管理的檔案（`adad-workflow` 腳本、pre-commit hook），覆蓋前自動備份成
`.bak`；`system_map.md`、`checkpoints/`、`docs/adr`、`docs/patterns` 等你自己的資產
完全不會被觸碰，`.agents/AGENTS.md` 若偵測到你客製化過也只會提示、不會自動覆蓋
（要強制覆蓋才需要加 `--force-agents-md`）。

### 常用指令一覽

| 指令 | 說明 |
|---|---|
| `adad init` | 在目前專案初始化 ADAD（自我完備，含本地 skill 副本） |
| `adad upgrade` | 將已安裝的套件版本安全同步到已 init 過的專案（僅更新套件管理的檔案，不動使用者資產；覆蓋前自動備份成 `.bak`） |
| `adad upgrade --force-agents-md` | 同上，但連 `.agents/AGENTS.md` 也用套件最新版本強制覆蓋 |
| `adad remove` | 清理/還原目前專案的環境與工具產出（venv、pre-commit hook、本地 skill 副本）；`system_map.md/.yaml`、`checkpoints/` 等使用者資產預設保留 |
| `adad remove --purge-docs` | 同上，但連同 `system_map.md/.yaml`、`checkpoints/` 一併刪除 |
| `adad global install` | 部署到 Antigravity 全域設定，供所有專案共用 |
| `adad global uninstall` | 自 Antigravity 全域設定移除 |
| `adad pack` | 打包目前目錄的 `.agents` 為 zip，供發布用 |
| `adad --version` / `adad --help` | 查看版本 / 說明 |

> 舊版 `python install.py <cmd>` 仍保留作為相容轉發（`init`→`init`、`clean`→`remove`、
> `global`→`global install`、`uninstall`→`global uninstall`），但建議直接改用 `adad`。

## 🛡️ 核心開發憲法 (Global Rules)

不論 Agent 執行哪一個階段的任務，都必須強制遵循以下元規則（Meta-Rules）：

> *   **[RULE-01] SSOT 唯一性** 🔒 **機器強制**：你唯一的記憶與事實來源為 `system_map.yaml` (自 `system_map.md` 編譯而來)。**嚴禁自行在代碼中衍生或假設未記載於該檔案的介面、路由或規格。** Pre-commit hook 自動阻斷過期的 `system_map.yaml`。
> *   **[RULE-02] 先架構後程式 (拒絕 Code-First)** 🔒 **機器強制**：嚴禁 Code-First 開發。只有在目標節點於 `system_map.yaml` 中的狀態為 `planned`、`dirty`、`validated`、`draft` 或 `pending_review`，且已通過人類的 Checkpoint 審核時，你才被允許生成或修改該節點的商業邏輯代碼。Pre-commit hook 比對 staged 檔案與模組狀態。
> *   **[RULE-03] 原子化操作 (Atomic Scope)** ⚠️ **機器警告**：你每次的輸出（程式碼修改）**只能影響單一節點（單一函數、API 或組件）**。嚴禁進行跨模組、跨檔案的大規模 Patch 程式碼。Pre-commit hook 偵測跨模組修改時發出 WARNING。
> *   **[RULE-04] 遇錯即停 (Fail-Fast)** 📝 **Agent 行為規則**：在 Phase 2（實作期）若發現架構規格無法滿足邏輯需求（例如：發現少傳引數、需要多回傳欄位等），**你必須立即中斷程式碼生成**，改為輸出 `Schema Update Request` 格式，並等待人類審核。

---

## ⚠️ 機械強制的前提與已知限制

上面所有標示「🔒 機器強制」的規則，**實際上都是靠 `.git/hooks/pre-commit` 這支 hook 執行的**。這代表兩件事，務必知道：

1. **hook 沒裝，強制就完全不存在。** 只有執行過 `python install.py init` 才會裝上這支 hook。如果團隊裡有人是直接 `git clone` 專案就開始改東西、沒跑過 `init`，RULE-01~05、Invariants、Verification 全部都不會生效——而且**系統不會主動告訴你這件事**，一切看起來都跟正常一樣，只是完全沒人在把關。
   為了降低這個風險，`compile_map.py` 與 `resume_analysis.py` 現在會在每次執行時主動檢查：若偵測到目前是 git repo、但 `.git/hooks/pre-commit` 不存在，會印出 `[NO GUARDRAIL]` 警告，提醒你尚未安裝 hook。但這只是被動提醒，不會阻止任何操作。

2. **`git commit --no-verify` 可以完全繞過 pre-commit hook，不留任何痕跡。** 這是 git 本身的機制，ADAD 無法從 hook 層面阻止。**強烈建議在 CI/CD pipeline 中額外執行一次**：
   ```bash
   python .agents/skills/adad-workflow/scripts/adad_pre_commit.py
   ```
   把它當作本地 hook 被跳過時的最後一道防線。`adad_pre_commit.py` 本身是讀 git 的 staged/HEAD 內容執行檢查，跟本地 hook 用的是同一份邏輯，可以直接搬進任何 CI 環境使用。

3. **效能：目前不呼叫任何 LLM，純靜態分析（AST + regex + YAML），但會隨專案規模變慢，實測數字如下。**
   `adad_pre_commit.py` 完全是本機同步執行的靜態檢查，沒有網路請求、沒有呼叫任何語言模型 API——這代表它的延遲上限是「跟專案規模成正比的本機運算」，不是不可預期的網路/推論延遲。實際量測：
   - 小型專案（4 個模組）：約 0.07 秒，跟一般 Linter 感覺不出差異。
   - 中型規模（2000 個模組、單次 commit 觸及 50 個檔案）：修正前（每個 staged 檔案都重新載入一次整份 `system_map.yaml`）要 **69.5 秒**；修正後（`system_map.yaml` 只載入一次、所有檔案共用）降到 **2.3 秒**。
   若你的專案模組數持續成長、單次 commit 又常常一次觸及大量檔案，2 秒左右的等待仍然存在——這是目前架構下（YAML 反序列化 + 逐檔 AST 解析）的合理下限，不是零成本。若這個等待時間開始造成困擾，建議把非阻斷性的檢查（如孤兒地圖偵測）搬到 CI 而非本地 hook，只在本地保留真正需要即時回饋的幾條規則。

---

## 🔄 ADAD 核心 CLI 工具說明

當前專案底下的 Antigravity Agent 可以直接調用以下指令來操作架構狀態：

| 工具腳本 | 功能說明 | 調用時機 |
| :--- | :--- | :--- |
| `compile_map.py` | 編譯 `system_map.md` ➔ `system_map.yaml` + Draft Debt / 模組落點偵測 | 修改 Markdown 架構源後首要執行 |
| `resolve_target_file.py` | 查詢新模組該寫進哪個實體檔案（含子地圖落點） | Phase 1 新增模組前，先查再動筆 |
| `resume_analysis.py` | 分析架構進度、Draft Debt Ledger 與智能推薦下一步 | 開發重啟、或人類要求進度概覽時執行 |
| `read_context.py` | 讀取單一節點最小上下文 (已包含 ADR & 模式注入) | Phase 2 開始編寫代碼前，獲取目標簽章 |
| `check_normalization.py` | 執行 Rule of Two 檢查 | Phase 1 架構規劃期，檢測是否重複造輪子 |
| `analyze_cascade.py` | 執行髒點依賴分析 (DAG 走查) | Phase 3 反向同步，架構變更時級聯標記 `dirty` |
| `transit_state.py` | 推進/變更模組生命週期狀態（硬化版：非法轉移阻斷） | CP 審查通過、Lint 通過或被退回時更新狀態 |
| `verify_implementation.py` | 執行代碼實現驗證條件（如 assert）校驗 | 原子代碼生成完畢後進行自檢驗證 |
| `check_invariants.py` | 執行不變量約束（如 deny_imports）校驗 | 原子代碼生成完畢後進行靜態 AST 檢查 |
| `adad_pre_commit.py` | Pre-Commit Hook（機械強制 5 項檢查） | 每次 `git commit` 自動執行，或手動呼叫 |

---

## 🔄 ADAD 人機協作工作流 (Human-Agent Workflow)

此工作流以**人類（架構師/開發者）**為主動驅動者，**Agent** 則作為被動呼叫的原子執行單元。整體流程透過多個 **Checkpoint** 由人類進行決策與狀態推進。

```
[ Phase 1: 架構規劃與逐步展開 (Architecture Growth) ]
  1. 人類啟動規劃，依序小步展開系統架構 (Domain ➔ Subsystem ➔ Module ➔ Interface)。
  2. Agent 執行分析並呼叫 `check_normalization` 確保符合 Rule of Two。
  3. Agent 將規劃草案寫入 `system_map.md` (節點狀態標記為 planned)。
  4. 🚧 【人工 Checkpoint 1】：人類審查架構草案，確認無誤後批准。
  5. 執行 `compile_map.py` 編譯產生 `system_map.yaml`。
       │
       ▼
[ Phase 1.5: 環境與容器規劃 ]
  5.1. Agent 根據系統架構，於 `system_map.md` 的 `environment` 區塊規劃 Docker Compose 容器服務（狀態標記為 planned）。
  5.2. 🚧 【人工 Checkpoint 1.5】：人類審查多容器架構配置，確認無誤後批准，自動產生實體環境配置。
       │
       ▼
[ Phase 2: 原子生成 ]
  6. 人類指派特定節點進行開發，系統呼叫 `read_context` 為 Agent 準備最小上下文。
  7. 人類呼叫 Agent，Agent 依照上下文與規範生成單一原子代碼。
  8. 系統自動執行 Lint & Type Check 驗證代碼。
  9. Agent 呼叫 `check_invariants` 與 `verify_implementation` 進行架構與自檢約束校驗。
     ├── ❌ 失敗：系統呼叫 Agent 讀取 Error，進行自我修正迴圈 (Self-Fix Loop)。
     └──  成功：系統將節點狀態更新為 [linted/tested]。
  10. 🚧 【人工 Checkpoint 2】：人類審查產生的程式碼與實作，確認無誤後批准，推進狀態為 [deployed]。
       │
       ▼
[ Phase 3: 反向同步 ] ─── (若 Agent 在 Phase 2 實作期發現架構缺陷...)
  11. Agent 中斷程式碼生成，改為輸出 `Schema Update Request` 提案給人類。
  12. 🚧 【人工 Checkpoint 3】：人類審查此架構更新請求與影響範圍。
  13. 人類批准更新後，系統執行 Version +1，並自動呼叫 `analyze_cascade`。
  14. 系統自動將變更節點及所有受其影響的上層依賴節點狀態標記為 [dirty]。
  15. 🔄 人類引導指針重回 [Phase 2]，重新呼叫 Agent 生成所有被標記為 dirty 的節點。
       │
       ▼
[ Phase 4: 執行回饋 ]
  16. 人類部署運行系統，並收集監控工具或測試回報數據。
  17. 人類呼叫 Agent 分析運行數據，Agent 輸出 `suggest_architecture_update` 優化提案。
  18. 🚧 【人工 Checkpoint 4】：人類審估此優化提案，批准後更新 YAML，受影響節點變更為 [dirty]，人類重啟 [Phase 2] 演進。
```

---

## 🚧 Checkpoint Review Payload 標準格式

每個 Checkpoint 由三個部分組成：**系統呈現給人類的內容**、**人類的決策選項**、**決策後系統的行為**。每個 Checkpoint 無論結果如何，完整 Payload 都必須存檔於：`checkpoints/CP-{phase}-{序號}-{approved|rejected|modified}.yaml`。

### 共用信封格式（所有 Checkpoint 通用）

```yaml
checkpoint_payload:
  id: "CP-{phase}-{sequence}"        # 例如 CP-1-003
  phase: 1                            # 1~4
  timestamp: "2026-06-30T10:30:00Z"
  triggered_by: "agent"               # agent / system / runtime
  status: "pending"                   # pending / approved / rejected / modify_requested

  display:                            # 呈現給人類看的內容（各 Checkpoint 不同）
    ...

  decision:                           # 人類填寫
    action: ""                        # approve / reject / request_change
    comment: ""                       # 選填，任何文字說明
    modify_targets: []                # 僅 request_change 時填寫

  on_approve: ""                      # 系統執行動作
  on_reject: ""                       # 系統執行動作
  on_modify: ""                       # 系統執行動作
```

---

### Checkpoint 1：架構規劃審查（Phase 1 完成後）
*   **觸發時機**：Agent 完成一層或部分展開，準備編譯與進入 Phase 2 之前。

```yaml
checkpoint_payload:
  id: "CP-1-001"
  phase: 1
  triggered_by: "agent"
  status: "pending"

  display:
    title: "架構規劃審查"
    summary: "本次新增 3 個節點，修改 1 個節點"

    new_nodes:
      - name: "calculate_tax"
        input: { amount: float, country: string }
        output: { tax: float }
        dependencies: ["vat_rules"]
        state: "planned"

    modified_nodes:
      - name: "order_service"
        change: "新增對 calculate_tax 的依賴"
        before: { dependencies: [] }
        after: { dependencies: ["calculate_tax"] }

    normalization_report:
      - "validate_email 出現第 2 次，已 inline，第 3 次將強制抽 Shared Module"

    adr_required:                      # 本次設計決策，建議人類補充 why
      - node: "calculate_tax"
        question: "為何不內嵌於 order_service？"

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - node: ""                       # 要求修改的節點名稱
        instruction: ""                # 修改指示

  on_approve: "transit_module_state(all_new_nodes, validated)"
  on_reject: "清除本次所有 planned 節點，Agent 重新規劃"
  on_modify: "Agent 依照 modify_targets 修正後重新觸發 CP-1"
```

---

### Checkpoint 1.5：環境與容器部署規劃審查（Phase 1.5 完成後）
*   **觸發時機**：Phase 1 架構規劃審查 (CP-1) 通過後，準備開始 Phase 2 原子代碼生成之前。

```yaml
checkpoint_payload:
  id: "CP-1.5-001"
  phase: 1.5
  triggered_by: "agent"
  status: "pending"

  display:
    title: "環境與容器部署規劃審查"
    summary: "規劃多容器服務與環境變數以支援模組運行"

    environment_schema:
      compose_arch: true
      state: "planned"
      services:
        backend:
          type: "container"
          build: "./backend"
          ports: ["8000:8000"]
          environment: ["ENV=development"]
          depends_on: ["db"]
        db:
          type: "container"
          image: "postgres:15-alpine"
          volumes: ["db_data:/var/lib/postgresql/data"]

    generated_files:
      - "docker-compose.yml"
      - "backend/Dockerfile"

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - service: "backend"
        instruction: ""

  on_approve: "產生實體環境設定檔，並推進 environment.state 為 validated"
  on_reject: "Agent 重新調整環境與容器規劃"
  on_modify: "Agent 調整容器與環境配置後重新觸發 CP-1.5"
```

---

### Checkpoint 2：原子模組審查（Phase 2 每個模組生成後）
*   **觸發時機**：單一模組通過 Lint & Type Check 後，準備標記為 deployed 之前。

```yaml
checkpoint_payload:
  id: "CP-2-007"
  phase: 2
  triggered_by: "agent"
  status: "pending"

  display:
    title: "原子模組審查"
    node: "calculate_tax"

    spec_comparison:                   # 規格對照，方便人類確認有無介面漂移
      expected:                        # 來自 system_map.yaml
        input: { amount: float, country: string }
        output: { tax: float }
      actual:                          # Agent 實際生成的 signature
        input: { amount: float, country: string }
        output: { tax: float }
      drift_detected: false

    generated_code: |
      def calculate_tax(amount: float, country: str) -> float:
          ...

    lint_result:
      passed: true
      warnings: []

    type_check_result:
      passed: true

    self_fix_history:                  # 若有自我修正，顯示過程
      attempts: 0
      log: []

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - node: "calculate_tax"
        instruction: ""

  on_approve: "transit_module_state(calculate_tax, deployed)"
  on_reject: "transit_module_state(calculate_tax, dirty)，Agent 重新生成"
  on_modify: "Agent 依照 modify_targets 修正後重新觸發 CP-2"
```

---

### Checkpoint 3：Schema Update Request 審查（Phase 3 觸發時）
*   **觸發時機**：Agent 在實作時發現架構缺陷，發出 Schema Update Request。

```yaml
checkpoint_payload:
  id: "CP-3-002"
  phase: 3
  triggered_by: "agent"
  status: "pending"

  display:
    title: "Schema Update Request 審查"

    update_request:                    # Agent 原始輸出
      action: "update_schema"
      target: "api_login"
      add_arguments: ["user_id"]
      reason: "Login response 需要回傳 user_id 供下游 SessionService 使用，目前 schema 未定義"

    impact_analysis:                   # analyze_cascade 的結果
      dirty_nodes:
        - node: "api_login"
          reason: "直接變更"
        - node: "session_service"
          reason: "依賴 api_login output"
        - node: "auth_middleware"
          reason: "依賴 session_service"
      estimated_regeneration_cost: "3 個模組需重新生成"

    version_preview:
      from: "system_map_v3.yaml"
      to: "system_map_v4.yaml"
      diff:
        - type: "modify"
          node: "api_login"
          change: "output 新增 user_id: string"

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - node: ""
        instruction: ""

  on_approve: "Version +1，執行 analyze_cascade，所有 dirty 節點重回 Phase 2"
  on_reject: "Agent 必須在不修改 schema 的前提下重新思考實作方式，若無法解決則再次觸發 CP-3"
  on_modify: "Agent 依照 modify_targets 調整 Update Request 後重新觸發 CP-3"
```

---

### Checkpoint 4：Architecture 優化提案審查（Phase 4 觸發時）
*   **觸發時機**：Runtime 數據觸發 Agent 提出優化建議。

```yaml
checkpoint_payload:
  id: "CP-4-001"
  phase: 4
  triggered_by: "runtime"
  status: "pending"

  display:
    title: "Architecture 優化提案審查"

    evidence:                          # 觸發此提案的數據依據
      metric: "calculate_tax 呼叫頻率"
      observation: "95% 來自 JP，平均回應時間 230ms"
      threshold_exceeded: "回應時間 > 200ms SLA"

    proposal:
      action: "suggest_architecture_update"
      target: "calculate_tax"
      reason: "High frequency path，JP 稅率短期不變"
      proposal: "Introduce cache layer，TTL 24hr"

    impact_analysis:
      dirty_nodes:
        - node: "calculate_tax"
          reason: "加入 cache decorator"
        - node: "vat_rules"
          reason: "需新增 cache invalidation hook"
      new_nodes:
        - name: "tax_cache"
          type: "infrastructure"
          state: "planned"
      estimated_regeneration_cost: "2 個模組修改，1 個新模組"

    risk_assessment:
      - "cache 過期期間若 JP 稅率異動，將回傳錯誤數據"
      - "建議搭配 vat_rules 變更事件觸發 cache invalidation"

  decision:
    action: ""                         # approve / reject / request_change
    comment: ""
    modify_targets:
      - node: ""
        instruction: ""

  on_approve: "Version +1，更新 system_map，dirty 節點重回 Phase 2"
  on_reject: "提案封存，記錄於 ADR，標記為 rejected，不影響現有架構"
  on_modify: "Agent 依照 modify_targets 調整提案後重新觸發 CP-4"
```

---

## 🛡️ 跨 Checkpoint 共用規則與自修復限制

*   **Self-Fix Loop 終止條件**：
    在 Phase 2 原子模組生成時，因 Lint/Type Check 失敗所啟動的自我修正機制（Self-Fix Loop），最多嘗試 **3 次**。若 3 次皆失敗，必須立刻停止生成，將錯誤日誌填入 Checkpoint Payload 並呈報給人類審查（升級為 CP-2 審查）。
*   **on_reject 的 Agent 行為限制**：
    所有 Checkpoint 被人類拒絕（Reject）後，Agent 只能在原被拒絕的模組/節點範圍內重新思考實作或微調，**禁止自行擴大修改範圍至其他節點**。

---

## 📈 ADAD 演進與優化改善邏輯 (Improvements)

相較於 ADAD 第一版純 YAML facts 與硬性依賴校驗的設計，當前專案整合了以下幾項重大改善與升級：

### 1. 設計抉擇 (ADR) 智慧注入與 Context 裁剪
*   **改善邏輯**：為防止 Context 膨脹，架構引擎實作了 [docs/adr/](docs/adr/) 文件智慧解析器。當 Agent 調用 `read_context` 讀取節點時，引擎會提取模組關聯的 ADR 文件（如 `ADR-001`）中的**標題、狀態、以及決策要點**，智慧裁減為 2~3 行摘要後寫入 Context，為 Agent 在多種寫法中做出設計決策提供 why 的歷史引導。

### 2. 首選設計模式 (Preferred Pattern) 落地
*   **改善邏輯**：引進模式約束（例如 [pure_function.md](docs/patterns/pure_function.md) 模式）。可在架構中聲明模組首選模式，Context 會隨之注入模式規範（如 "輸入引數必須為 immutable" 等指引），直接回答 Agent「有多種寫法時應該選哪一種」的實踐方式。

### 3. 架構邊界靜態不變量 (Invariants) AST 校驗
*   **改善邏輯**：新增了基於 Python AST（抽象語法樹）的靜態檢查器 `check_invariants`。能讀取 `system_map.yaml` 中配置的 `invariants` 約束（如 `deny_imports: [pymysql]`），在代碼生成後對 Imports 與 ImportsFrom 進行靜態分析並自動阻斷違規導入，守護系統解耦意圖（如分層隔離、防腐界限）。

### 4. 代碼實現驗證限制 (Verification)
*   **改善邏輯**：新增了 `verify_implementation` 檢驗器，支援在節點上配置 `verification` 約束（例如 `must_have_assertions`），強制 Agent 在撰寫原子程式碼時必須至少包含一個 `assert` 自檢斷言，從而限制程式碼實踐的品質。

### 5. 智慧狀態繼承與編譯重置
*   **改善邏輯**：引入 Compiler (`compile_map.py`) 在從 `system_map.md` 編譯為中間表示 YAML 時，會自動進行結構比對。
    *   **無變動繼承**：如果模組的 input, output, dependencies 未改變，自動繼承舊的狀態（如 deployed）。
    *   **變動重置**：如果模組發生了結構性改變，狀態會智慧重置為 `dirty`。

### 6. 思路重啟 (Resume) 與下一步智能推薦
*   **改善邏輯**：為解決 Agent 中途接手難以恢復設計思路的痛點，實作了 `resume_analysis.py`。能輸出詳細 TODO 與 Checkpoints 進度報告。更基於 DAG 拓撲分析，篩選出**依賴項均已 deployed 但自身尚未 deployed 的模組**，智能推薦最合理的下一步開發重點。

### 7. Draft Debt Ledger（草稿債務追蹤）
*   **改善邏輯**：新增 `draft` 與 `pending_review` 兩個生命週期狀態，專為 Leaf 模式（demo 期、快速原型）設計。
    *   **draft 狀態**：Leaf 模式下生成的模組標記為 `draft`，進入 `resume_analysis.py` 的待補清單。
    *   **自動升級**：當 draft 模組的 **fan-in**（被依賴次數）從 0 變為 ≥2 時，系統自動將其及所有新依賴它的節點標記為 `pending_review`，強制觸發一次補做 Checkpoint（含 ADR）。
    *   **結構訊號驅動**：觸發條件是結構性的（依賴關係變化），不依賴人類記憶。這比「定期手動回顧 demo 期代碼」可靠得多。

### 8. 軟規則硬化（Pre-Commit Hook 機械強制）
*   **改善邏輯**：將原本只存在於 `AGENTS.md` 文字中的軟規則，轉為 `git pre-commit hook` 機械執行：

    | 檢查項目 | 對應規則 | 失敗行為 |
    |---------|---------|----------|
    | Staleness 阻斷 | RULE-01 SSOT | ❌ 阻斷 commit |
    | 狀態門禁（含刪除檔案） | RULE-02 先架構後程式 | ❌ 阻斷 commit |
    | 原子範圍 | RULE-03 原子化操作 | ⚠️ 警告（不阻斷） |
    | Invariants (deny_imports) | 架構邊界 | ❌ 阻斷 commit |
    | Verification (must_have_assertions) | 實作品質 | ❌ 阻斷 commit |
    | 跨 Domain 依賴邊界 | 架構邊界 | ❌ 阻斷 commit |

    核心保證由機器全程強制，分級只影響「需不需要人類額外審查文件」，不影響「會不會真的改A壞B」這個底線。

    **2026-07 安全強化**：所有檢查項目已改為讀取 `git show :0:<path>`（暫存區 staged blob）而非磁碟工作目錄，防止「先 git add 違規版本 → 改乾淨但忘記重新 add」的繞過攻擊向量。額外修正：
    - 相對 import（`from . import x`）漏檢問題（`deny_imports` 現可攔截所有 import 形式）
    - `check_invariants` / `verify_implementation` 未讀取節點 `source` 欄位路徑的問題
    - git 執行失敗時靜默放行的問題（現改為阻斷 commit）
    - 刪除（D）檔案不受 RULE-02 狀態門禁管轄的問題

### 9. 狀態轉移硬化
*   **改善邏輯**：`transit_state()` 從原本的 WARNING（允許非法轉移）改為 ERROR + 阻斷。非法的狀態轉移會直接返回錯誤，不再允許執行，確保狀態機的完整性。

---

## 🙏 致謝與開發方式說明

本專案的架構設計、開發規範與所有 Checkpoint 決策由專案作者主導，開發過程中使用 **Claude** 進行 AI 協作開發（由人類把持架構與審核，Agent 負責原子程式碼生成，詳見上方 ADAD 工作流）。

部分模組在實作與除錯階段，另外搭配了 **[ponytail](https://github.com/DietrichGebert/ponytail)** 這個 skill 協助控制程式碼精簡度、避免過度工程化（YAGNI 導向）。程式碼中部分 `ponytail:` / `ponytail-fix:` 開頭的註解，即為此工具留下的痕跡，特此註明並感謝原作者 [DietrichGebert](https://github.com/DietrichGebert) 的開源分享。
