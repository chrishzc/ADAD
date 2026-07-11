"""ADAD CLI - Architecture-Driven Agentic Development 工具鏈。"""

# ponytail: 這是全專案版本號的唯一事實來源（Single Source of Truth）。
# pyproject.toml 透過 [tool.setuptools.dynamic] 直接讀這個變數，不再各自維護一份；
# cli.py 的 --version、core.py 的 upgrade 流程也都是 import 這裡的 __version__，
# 不會有兩處數字對不上的問題。以後要發新版本，只需要改這一行。
__version__ = "1.2.0"
