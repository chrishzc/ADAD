# -*- coding: utf-8 -*-
"""
ADAD Core Engine (ADAD 核心處理引擎)
ponytail: 自動檢測並於需要時安裝 pyyaml，核心邏輯以標準 DAG 演算法與最簡特徵相似度實作。
"""
import os
import sys
import json

# 自動安裝 PyYAML 依賴以確保跨裝置開箱即用
try:
    import yaml
except ImportError:
    import subprocess
    print("[ADAD] 偵測到未安裝 PyYAML，正在自動安裝...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "--quiet"])
        import yaml
        print("[ADAD] PyYAML 安裝成功。")
    except Exception as e:
        print(f"[ADAD ERROR] 無法自動安裝 PyYAML: {e}。請手動安裝: pip install pyyaml")
        sys.exit(1)

MAP_FILE = "system_map.yaml"

class ADADCore:
    def __init__(self, map_path=MAP_FILE):
        self.map_path = map_path
        self.data = self._load_map()

    def _load_map(self):
        if not os.path.exists(self.map_path):
            return {"version": 1, "modules": {}}
        with open(self.map_path, "r", encoding="utf-8") as f:
            try:
                content = yaml.safe_load(f)
                return content if content else {"version": 1, "modules": {}}
            except Exception as e:
                print(f"[ADAD ERROR] 解析 {self.map_path} 失敗: {e}")
                sys.exit(1)

    def save(self):
        with open(self.map_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.data, f, allow_unicode=True, sort_keys=False)

    def get_node(self, node_name):
        return self.data.get("modules", {}).get(node_name)

    def read_context(self, node_name):
        """讀取單一節點最小上下文 (該節點與其相依節點的 Interface)"""
        node = self.get_node(node_name)
        if not node:
            return {"error": f"找不到節點: {node_name}"}

        context = {
            "target_node": {
                "name": node_name,
                "type": node.get("type"),
                "state": node.get("state"),
                "input": node.get("input", {}),
                "output": node.get("output", {}),
                "dependencies": node.get("dependencies", []),
                "description": node.get("description", "")
            },
            "dependency_interfaces": {}
        }

        # 獲取相依節點的 Interface 資訊
        for dep in node.get("dependencies", []):
            dep_node = self.get_node(dep)
            if dep_node:
                context["dependency_interfaces"][dep] = {
                    "input": dep_node.get("input", {}),
                    "output": dep_node.get("output", {})
                }
            else:
                context["dependency_interfaces"][dep] = "未定義"

        return context

    def evaluate_normalization(self, proposed_name, proposed_input, proposed_output):
        """執行 Rule of Two 檢查，檢測是否有相似功能已重複出現 2 次以上"""
        modules = self.data.get("modules", {})
        
        # 簡單的關鍵字相似度判定與介面完全判定
        matches = []
        
        for name, info in modules.items():
            if name == proposed_name:
                continue
            
            # 1. 介面 input/output 完全一致判定
            if info.get("input") == proposed_input and info.get("output") == proposed_output:
                matches.append((name, "介面簽章完全一致"))
                continue
                
            # 2. 關鍵字模糊匹配 (比如 'tax', 'email', 'sms')
            keywords = ["tax", "email", "sms", "auth", "login", "validate", "cache", "format"]
            for kw in keywords:
                if kw in name.lower() and kw in proposed_name.lower():
                    matches.append((name, f"包含相同特徵關鍵字 '{kw}'"))
                    break
        
        if len(matches) >= 2:
            return {
                "passed": False,
                "reason": f"觸發 Rule of Two：功能特徵與現有模組高度重複，相似模組已出現 {len(matches)} 次。",
                "duplicates": [f"{name} ({reason})" for name, reason in matches]
            }
            
        return {"passed": True, "duplicates": []}

    def analyze_dirty_cascade(self, target_node):
        """智慧髒點依賴分析 (DAG 逆向遞迴追蹤)"""
        modules = self.data.get("modules", {})
        if target_node not in modules:
            return []

        # 建立反向依賴圖 (誰依賴了我)
        # adj[u] 包含所有依賴 u 的節點
        adj = {name: [] for name in modules}
        for name, info in modules.items():
            for dep in info.get("dependencies", []):
                if dep in adj:
                    adj[dep].append(name)

        # BFS 走查所有受波及的上游節點
        visited = set()
        queue = [target_node]
        dirty_list = []

        while queue:
            curr = queue.pop(0)
            for neighbor in adj.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    modules[neighbor]["state"] = "dirty"
                    dirty_list.append(neighbor)
                    queue.append(neighbor)
                
        # 自身變更也轉為 dirty (若原本是 deployed 狀態)
        modules[target_node]["state"] = "dirty"
        dirty_list.insert(0, target_node)

        return dirty_list

    def transit_state(self, node_name, next_state):
        """模組生命週期狀態轉移與校驗"""
        node = self.get_node(node_name)
        if not node:
            return {"success": False, "error": f"找不到節點: {node_name}"}

        curr_state = node.get("state", "planned")
        valid_transitions = {
            "planned": ["validated"],
            "validated": ["dirty", "linted/tested"],
            "dirty": ["validated", "linted/tested"],
            "linted/tested": ["deployed", "dirty"],
            "deployed": ["dirty"]
        }

        # 開放人類強制變更為任何狀態，但提示非典型轉換
        if next_state not in valid_transitions.get(curr_state, []):
            print(f"[ADAD WARNING] 節點 {node_name} 進行非典型狀態轉換: {curr_state} ➔ {next_state}")

        node["state"] = next_state
        return {"success": True, "from": curr_state, "to": next_state}


# ================= 自我單元測試 =================
def run_self_test():
    print("[ADAD Test] 啟動 ADAD 核心引擎自我測試...")
    test_file = "test_system_map.yaml"
    
    # 建立測試資料
    test_data = {
        "version": 1,
        "modules": {
            "db_connector": {
                "type": "infrastructure",
                "state": "deployed",
                "dependencies": [],
                "input": {},
                "output": {"connected": "bool"}
            },
            "user_service": {
                "type": "service",
                "state": "deployed",
                "dependencies": ["db_connector"],
                "input": {"user_id": "int"},
                "output": {"name": "str"}
            },
            "calculate_jp_tax": {
                "type": "function",
                "state": "deployed",
                "dependencies": [],
                "input": {"amount": "float"},
                "output": {"tax": "float"}
            },
            "calculate_us_tax": {
                "type": "function",
                "state": "deployed",
                "dependencies": [],
                "input": {"amount": "float"},
                "output": {"tax": "float"}
            }
        }
    }
    
    with open(test_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(test_data, f)
        
    try:
        core = ADADCore(test_file)
        
        # 1. 測試讀取上下文
        ctx = core.read_context("user_service")
        assert "db_connector" in ctx["dependency_interfaces"]
        print("  - 測試 1: 讀取上下文成功")

        # 2. 測試 Rule of Two
        # 同樣有 calculate_jp_tax 和 calculate_us_tax，若想新增 calculate_uk_tax，應觸發警告
        res = core.evaluate_normalization("calculate_uk_tax", {"amount": "float"}, {"tax": "float"})
        assert res["passed"] is False, "應該觸發 Rule of Two 警告"
        print("  - 測試 2: Rule of Two 阻斷判定成功")

        # 3. 測試 DAG 級聯分析
        # db_connector 變更，應該讓 user_service 變為 dirty
        dirty = core.analyze_dirty_cascade("db_connector")
        assert "user_service" in dirty
        assert core.get_node("user_service")["state"] == "dirty"
        print("  - 測試 3: DAG 髒點依賴級聯分析成功")

        # 4. 測試狀態轉換
        core.transit_state("db_connector", "validated")
        assert core.get_node("db_connector")["state"] == "validated"
        print("  - 測試 4: 狀態機轉換成功")
        
        print("[ADAD Test] 所有測試順利通過！")
        
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_self_test()
