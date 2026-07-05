# -*- coding: utf-8 -*-
"""
[Deprecated] 舊版進入點，僅為向下相容保留。

請改用安裝後的 `adad` CLI 指令（例如 `adad init`、`adad global install`）。
本檔案只是把舊的 `python install.py <cmd>` 轉呼叫到新的 adad_cli 套件，
讓還沒重新安裝套件的人暫時不會直接壞掉。
"""
import sys

from adad_cli.cli import main as _adad_main

_LEGACY_TO_NEW = {
    "init": ["init"],
    "clean": ["remove"],
    "global": ["global", "install"],
    "uninstall": ["global", "uninstall"],
    "pack": ["pack"],
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in _LEGACY_TO_NEW:
        print("[ADAD] install.py 已棄用，請改用 `adad` 指令，例如：")
        print("  adad init")
        print("  adad remove")
        print("  adad global install")
        print("  adad global uninstall")
        print("  adad pack")
        sys.exit(1)

    print(f"[ADAD] 偵測到舊版呼叫方式，自動轉發為: adad {' '.join(_LEGACY_TO_NEW[sys.argv[1]])}")
    sys.argv = ["adad"] + _LEGACY_TO_NEW[sys.argv[1]]
    _adad_main()
