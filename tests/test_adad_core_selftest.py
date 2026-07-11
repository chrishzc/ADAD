# -*- coding: utf-8 -*-
"""
adad_core.py 本身已經內建一套用 assert 寫成的自我測試（run_self_test()），
覆蓋了 DAG 級聯、Rule of Two、Task 生命週期、Draft Debt Ledger、include 分區地圖等
遠比本測試套件其他檔案更細的分支。這裡不重寫這些案例，而是把它當成黑箱，
用子行程呼叫 `python adad_core.py --test`，確認它在目前這份程式碼上仍然全數通過
——真正的重點是「把它接進 pytest 可以自動發現、CI 可以自動執行的範圍」，
不是重新發明一遍測試內容（規格總覽.md #5 的訴求就是『有 pytest 覆蓋』，
不是『每支腳本都要重新手刻一份邏輯測試』）。
"""
import subprocess
import sys

from conftest import script_path


def test_adad_core_embedded_self_test_passes(tmp_path):
    proc = subprocess.run(
        [sys.executable, script_path("adad_core.py"), "--test"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    assert "所有" in proc.stdout or "測試" in proc.stdout

    # run_self_test() 承諾會自行清理暫存檔，這裡順手驗證這個承諾沒有跳票，
    # 避免以後有人改壞清理邏輯、在使用者專案目錄留下垃圾檔案卻沒有任何測試發現。
    leftovers = list(tmp_path.glob("test_system_map.yaml")) + list(tmp_path.glob("*.tmp_adad_test*"))
    assert leftovers == [], f"self test 應該清理暫存檔，但殘留: {leftovers}"
