# -*- coding: utf-8 -*-
"""
ADAD CLI 入口點。

安裝後（pip install . 或 pipx install .）會在 PATH 上得到一個 `adad` 指令，
可在任何目錄下呼叫，行為等同於原本的 `python install.py <cmd>`，
但不再要求你必須待在 clone 下來的 repo 目錄裡才能執行。

multi-agent 支援 (2026 新增):
`adad init` / `adad global install` 現在支援選擇要對哪些 agent
（antigravity / claude）設定 ADAD。不加 --agents 參數時會跳出互動選單
詢問；加了就直接照參數指定的清單執行，不會再問（方便在 CI / 腳本裡
非互動呼叫）。選擇結果會存進 .agents/.adad-agents.json，之後
`adad upgrade` 會自動讀這份設定，不需要每次都重新詢問一次。

互動詢問刻意只用 click 內建的 click.confirm()，不引入 questionary 之類
的第三方套件，避免讓使用者 `pip install .` 之外還要多裝東西。
"""
import sys

import click

from adad_cli import __version__, core


def _prompt_agent_selection() -> list:
    """跳出互動選單，逐一詢問要不要為每個已知 agent 設定 ADAD。"""
    click.echo("要為哪些 Agent 設定 ADAD？（可複選，Enter 採用預設值 y）")
    selected = []
    for key, label in core.AGENT_CHOICES.items():
        if click.confirm(f"  安裝到 {label}？", default=True):
            selected.append(key)
    if not selected:
        click.echo("[ADAD ERROR] 未選擇任何 Agent，已取消。")
        sys.exit(1)
    return selected


def _resolve_agents(agents_opt) -> list:
    """把 --agents 選項字串解析成清單；沒帶這個選項就跳互動選單問。"""
    if agents_opt:
        chosen = [a.strip() for a in agents_opt.split(",") if a.strip()]
        invalid = [a for a in chosen if a not in core.AGENT_CHOICES]
        if invalid:
            click.echo(
                f"[ADAD ERROR] 不認得的 agent: {', '.join(invalid)}"
                f"（可選: {', '.join(core.AGENT_CHOICES)}）"
            )
            sys.exit(1)
        return chosen
    return _prompt_agent_selection()


@click.group()
@click.version_option(__version__, prog_name="adad")
def main():
    """ADAD (Architecture-Driven Agentic Development) 命令列工具。"""


@main.command("init")
@click.option(
    "--agents",
    default=None,
    help="逗號分隔要設定的 agent，如 antigravity,claude；省略則跳出互動選單詢問。",
)
def cmd_init(agents):
    """在目前專案目錄初始化 ADAD (checkpoints、system_map.md、venv、pre-commit hook 等)。"""
    selected = _resolve_agents(agents)
    core.init_project(agents=selected)


@main.command("remove")
@click.option(
    "--purge-docs",
    is_flag=True,
    default=False,
    help="連同 system_map.md/.yaml、checkpoints/ 等使用者架構文件與決策紀錄一併刪除（預設保留）。",
)
def cmd_remove(purge_docs):
    """還原/清理目前專案中的 ADAD 相關產出與環境（等同舊版 clean）。

    預設只清理環境/工具產出（venv、pre-commit hook、本地 skill 副本），
    system_map.md/.yaml、checkpoints/ 等使用者資產預設保留，
    需要加 --purge-docs 才會一併刪除。
    """
    core.clean_project(purge_docs=purge_docs)


@main.command("upgrade")
@click.option(
    "--force-agents-md",
    is_flag=True,
    default=False,
    help="連 .agents/AGENTS.md 也用套件內建版本強制覆蓋（覆蓋前會先備份成 .bak）。",
)
def cmd_upgrade(force_agents_md):
    """將目前已安裝的 ADAD 套件版本，安全同步到「已經 init 過」的專案。

    只更新套件管理的檔案（adad-workflow 腳本、pre-commit hook），
    system_map.md / checkpoints / docs 等使用者資產完全不會被觸碰。

    要同步哪些 agent 直接讀 `adad init` 當初存的設定（.agents/.adad-agents.json），
    不會再問一次；只有這個設定檔不存在（例如專案是這個功能加入前建立的）
    才會跳出互動選單詢問一次，並把結果補存起來。
    """
    agents = core.load_project_agents()
    if agents is None:
        click.echo("[ADAD] 這個專案還沒有記錄過要同步哪些 Agent，先詢問一次（之後就會自動記住，不會再問）：")
        agents = _prompt_agent_selection()
        core.save_project_agents(agents)
    core.upgrade_project(agents=agents, force_agents_md=force_agents_md)


@main.group("global")
def cmd_global():
    """管理各 Agent（Antigravity 2.0 / Claude Code 等）的全域 ADAD Skills 與規則。"""


@cmd_global.command("install")
@click.option(
    "--agents",
    default=None,
    help="逗號分隔要安裝的 agent，如 antigravity,claude；省略則跳出互動選單詢問。",
)
def cmd_global_install(agents):
    """將 ADAD 部署至全域設定，供所有專案共用。"""
    selected = _resolve_agents(agents)
    core.install_global(agents=selected)


@cmd_global.command("uninstall")
@click.option(
    "--agents",
    default=None,
    help="逗號分隔要卸載的 agent，如 antigravity,claude；省略則卸載全部已知 agent。",
)
def cmd_global_uninstall(agents):
    """自全域設定移除 ADAD 客製化與規則。"""
    selected = [a.strip() for a in agents.split(",") if a.strip()] if agents else None
    core.uninstall_global(agents=selected)


@main.command("pack")
def cmd_pack():
    """打包目前目錄下的 .agents（與 .claude，若存在）客製化目錄為 zip，便於上傳 GitHub 發布。"""
    core.pack_dist()


if __name__ == "__main__":
    main()
