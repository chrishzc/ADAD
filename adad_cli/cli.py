# -*- coding: utf-8 -*-
"""
ADAD CLI 入口點。

安裝後（pip install . 或 pipx install .）會在 PATH 上得到一個 `adad` 指令，
可在任何目錄下呼叫，行為等同於原本的 `python install.py <cmd>`，
但不再要求你必須待在 clone 下來的 repo 目錄裡才能執行。
"""
import click

from adad_cli import __version__, core


@click.group()
@click.version_option(__version__, prog_name="adad")
def main():
    """ADAD (Architecture-Driven Agentic Development) 命令列工具。"""


@main.command("init")
def cmd_init():
    """在目前專案目錄初始化 ADAD (checkpoints、system_map.md、venv、pre-commit hook 等)。"""
    core.init_project()


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
    """
    core.upgrade_project(force_agents_md=force_agents_md)


@main.group("global")
def cmd_global():
    """管理 Antigravity 2.0 / IDE 的全域 ADAD Skills 與規則。"""


@cmd_global.command("install")
def cmd_global_install():
    """將 ADAD 部署至 Antigravity 全域設定，供所有專案共用。"""
    core.install_global()


@cmd_global.command("uninstall")
def cmd_global_uninstall():
    """自 Antigravity 全域設定移除 ADAD 客製化與規則。"""
    core.uninstall_global()


@main.command("pack")
def cmd_pack():
    """打包目前目錄下的 .agents 客製化目錄為 zip，便於上傳 GitHub 發布。"""
    core.pack_dist()


if __name__ == "__main__":
    main()
