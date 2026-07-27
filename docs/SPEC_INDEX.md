# ADAD 套件規格書：與 Agent Kernel 的介面契約（修正合併版）

> 這份檔案原名 `#規格總覽.md`，放在 repo 根目錄。因為檔名開頭是 `#` 又混雜中文，
> 在部分工具鏈（例如解壓縮、markdown 連結）容易出現編碼問題，改名為純 ASCII
> 的 `docs/SPEC_INDEX.md`，內容未變。

本檔合併了兩份性質不同的文件，**這次修正把先前合併時遺失的第 1 節補回來**：

- **第 1 節**回答「ADAD 需要 Kernel 提供哪些能力、這些能力在自建 Kernel vs
  現成平台上分別怎麼達成」——這是**介面契約**，決定套件裡要放什麼檔案。
- **第 5 節**是根據前面所有討論盤點出來的**具體代辦事項清單**（目前編號至 #54）——這是
  **執行清單**，決定「現在要動手做哪一項」。

兩者關係：第 5 節每一項代辦事項，做完之後應該要能對應回第 1 節某個能力從
「指示性建議」升級成「機械強制」，或是讓 ADAD schema 補齊某個原本沒有的欄位。
之前那份「規格總覽.md」把第 1 節誤植換成第 5 節的內容，導致第 3、4 節裡對
`1-1`~`1-7` 的引用全部懸空，這份修正版已經對齊。

---

## 目錄

- [01 Kernel Interface](specifications/01_kernel_interface.md)
- [02 Platform Instructions](specifications/02_platform_instructions.md)
- [03 Toolkit Manifest](specifications/03_toolkit_manifest.md)
- [04 Compatibility Checklist](specifications/04_compatibility_checklist.md)
- [05 Task Backlog](specifications/05_task_backlog.md)
- [06 Multi Module Collaboration](specifications/06_multi_module_collaboration.md)
- [07 Checkpoint Payload Format](specifications/07_checkpoint_payload_format.md)
