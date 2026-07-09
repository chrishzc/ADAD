# -*- coding: utf-8 -*-
"""
資源定位工具 (Resource Locator)

ponytail: 這是解決原本 install.py 「假設 cwd 就是 repo 根目錄」問題的核心。
不論使用者是在哪個目錄執行 `adad` 指令、也不論套件是被 `pip install`、
`pip install -e .` 或 `pipx install` 到哪個 site-packages 路徑，
importlib.resources 都能正確定位到「隨套件一起安裝」的範本檔案，
而不是依賴呼叫當下的工作目錄。
"""
from __future__ import annotations

import importlib.resources as importlib_resources
from contextlib import ExitStack
from pathlib import Path

_exit_stack = ExitStack()


def get_resource_dir(*parts: str) -> Path:
    """回傳套件內建 resources/ 目錄下指定子路徑的實際檔案系統路徑。

    使用 importlib.resources.as_file 確保即使套件是以 zip/wheel 形式安裝
    （檔案並非直接攤開在磁碟上）也能取得一個可用的實體路徑。
    """
    traversable = importlib_resources.files("adad_cli").joinpath("resources", *parts)
    path = _exit_stack.enter_context(importlib_resources.as_file(traversable))
    return Path(path)


def agents_dir() -> Path:
    """回傳內建的 .agents 範本目錄（含 AGENTS.md 與 adad-workflow skill）。"""
    return get_resource_dir("agents")


def templates_dir() -> Path:
    """回傳內建的專案初始化範本目錄（gitignore、Dockerfile、ADR 範本等）。"""
    return get_resource_dir("templates")
