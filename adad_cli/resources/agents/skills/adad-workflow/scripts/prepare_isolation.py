# -*- coding: utf-8 -*-
"""Create an owned, rebuildable isolation workspace for one issued Task.

The workspace is deliberately treated as untrusted until its owner marker and
``lstat`` identity agree.  This keeps an old ``isolate`` invocation from
turning a malformed node name, junction, or unrelated directory into a
recursive-delete target.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid


ISOLATION_POLICY = {
    "coding": {
        "context_dump": "context.json",
    }
}
_NODE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_OWNER_MARKER = ".adad-isolation-owner.json"
_ALLOWED_TASK_STATUSES = {"assigned", "in_progress"}


def _is_reparse_point(path, metadata=None):
    try:
        metadata = metadata or os.lstat(path)
    except OSError:
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return os.path.islink(path) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _identity(path):
    """Return a stable directory identity, or ``None`` for unsafe paths."""
    try:
        metadata = os.lstat(path)
    except OSError:
        return None

    if not stat.S_ISDIR(metadata.st_mode) or _is_reparse_point(path, metadata):
        return None
    return {
        "st_dev": metadata.st_dev,
        "st_ino": metadata.st_ino,
        "type": "directory",
        "st_reparse_tag": getattr(metadata, "st_reparse_tag", 0),
    }


def _safe_regular_file(path):
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and not _is_reparse_point(path, metadata)
    )


def _inside(path, parent):
    """Check both lexical and resolved containment without accepting a drive hop."""
    try:
        absolute_path = os.path.abspath(path)
        absolute_parent = os.path.abspath(parent)
        resolved_path = os.path.realpath(absolute_path)
        resolved_parent = os.path.realpath(absolute_parent)
        return (
            os.path.commonpath([absolute_path, absolute_parent]) == absolute_parent
            and os.path.commonpath([resolved_path, resolved_parent]) == resolved_parent
        )
    except (TypeError, ValueError):
        return False


def _direct_child(path, parent, name=None):
    absolute_path = os.path.abspath(path)
    if os.path.dirname(absolute_path) != os.path.abspath(parent):
        return False
    if name is not None and os.path.basename(absolute_path) != name:
        return False
    return _inside(absolute_path, parent)


def _failure(error, *, workspace=None, cleanup_status="not_started",
             manual_action_required=False, receipt=None):
    return {
        "success": False,
        "error": error,
        "workspace": workspace,
        "copied_files": [],
        "cleanup_status": cleanup_status,
        "manual_action_required": manual_action_required,
        "receipt": receipt or {},
    }


def _read_owned_marker(workspace, node_name, expected_identity=None):
    marker_path = os.path.join(workspace, _OWNER_MARKER)
    if not _safe_regular_file(marker_path):
        return False
    try:
        with open(marker_path, "r", encoding="utf-8") as marker_file:
            marker = json.load(marker_file)
    except (OSError, json.JSONDecodeError):
        return False

    identity = _identity(workspace)
    if identity is None or marker.get("node_name") != node_name:
        return False
    if marker.get("identity") != identity:
        return False
    return expected_identity is None or identity == expected_identity


def _safe_project_file(project_root, relative_path):
    """Resolve an existing, regular project file without following reparse points."""
    if not isinstance(relative_path, str) or not relative_path:
        return None
    source_path = relative_path.split("::", 1)[0]
    if os.path.isabs(source_path):
        return None
    absolute_path = os.path.abspath(os.path.join(project_root, source_path))
    if not _inside(absolute_path, project_root) or not _safe_regular_file(absolute_path):
        return None
    return absolute_path


def _copy_project_file(project_root, staging_dir, relative_path):
    source_path = _safe_project_file(project_root, relative_path)
    if source_path is None:
        raise ValueError(f"白名單檔案不安全或不存在: {relative_path}")

    destination_path = os.path.abspath(
        os.path.join(staging_dir, os.path.relpath(source_path, project_root))
    )
    if not _inside(destination_path, staging_dir):
        raise ValueError(f"白名單目的地不在 staging: {relative_path}")
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return os.path.relpath(source_path, project_root)


def _receipt(node_name, staging_dir=None, quarantine_dir=None):
    return {
        "node_name": node_name,
        "staging": staging_dir,
        "quarantine": quarantine_dir,
    }


def _safe_tree_for_removal(root):
    """Reject any nested reparse point before cleanup can reach it."""
    pending = [root]
    while pending:
        current = pending.pop()
        if _identity(current) is None:
            return False
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if _is_reparse_point(entry.path):
                        return False
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
        except OSError:
            return False
    return True


def _publish_staging(workspace_dir, staging_dir, node_name):
    """Publish staging without recursively removing an unowned workspace."""
    if not os.path.exists(workspace_dir):
        try:
            os.rename(staging_dir, workspace_dir)
        except OSError as exc:
            return _failure(
                f"無法發布 staging workspace: {exc}",
                workspace=staging_dir,
                cleanup_status="staging_preserved",
                receipt=_receipt(node_name, staging_dir),
            )
        if not _read_owned_marker(workspace_dir, node_name):
            return _failure(
                "發布後 workspace owner marker 驗證失敗",
                workspace=workspace_dir,
                cleanup_status="published_unverified",
                manual_action_required=True,
                receipt=_receipt(node_name, staging_dir),
            )
        return None

    existing_identity = _identity(workspace_dir)
    if (
        existing_identity is None
        or not _read_owned_marker(workspace_dir, node_name, existing_identity)
    ):
        return _failure(
            "既有 workspace 未通過 owner marker 或 identity 驗證，已保留",
            workspace=staging_dir,
            cleanup_status="preserved_unowned",
            manual_action_required=True,
            receipt=_receipt(node_name, staging_dir),
        )

    workspace_root = os.path.dirname(workspace_dir)
    quarantine_dir = os.path.join(
        workspace_root, f".{node_name}.quarantine-{uuid.uuid4().hex}"
    )
    if not _direct_child(quarantine_dir, workspace_root):
        return _failure(
            "quarantine 路徑驗證失敗",
            workspace=staging_dir,
            cleanup_status="staging_preserved",
            receipt=_receipt(node_name, staging_dir),
        )

    try:
        os.rename(workspace_dir, quarantine_dir)
    except OSError as exc:
        return _failure(
            f"無法隔離既有 workspace: {exc}",
            workspace=staging_dir,
            cleanup_status="staging_preserved",
            receipt=_receipt(node_name, staging_dir, quarantine_dir),
        )

    try:
        os.rename(staging_dir, workspace_dir)
    except OSError as exc:
        restored = False
        try:
            os.rename(quarantine_dir, workspace_dir)
            restored = True
        except OSError:
            pass
        return _failure(
            f"無法交換 staging workspace: {exc}",
            workspace=staging_dir if os.path.exists(staging_dir) else None,
            cleanup_status="restore_succeeded" if restored else "restore_required",
            manual_action_required=not restored,
            receipt=_receipt(node_name, staging_dir, quarantine_dir),
        )

    if not _read_owned_marker(workspace_dir, node_name):
        return _failure(
            "交換後 workspace owner marker 驗證失敗",
            workspace=workspace_dir,
            cleanup_status="quarantine_retained",
            manual_action_required=True,
            receipt=_receipt(node_name, staging_dir, quarantine_dir),
        )

    if (
        not _direct_child(quarantine_dir, workspace_root)
        or _identity(quarantine_dir) != existing_identity
        or not _read_owned_marker(quarantine_dir, node_name, existing_identity)
        or not _safe_tree_for_removal(quarantine_dir)
    ):
        return _failure(
            "quarantine owner marker 或 identity 驗證失敗，已保留",
            workspace=workspace_dir,
            cleanup_status="quarantine_retained",
            manual_action_required=True,
            receipt=_receipt(node_name, staging_dir, quarantine_dir),
        )

    try:
        shutil.rmtree(quarantine_dir)
    except OSError as exc:
        return _failure(
            f"quarantine 清理失敗，已保留供人工處理: {exc}",
            workspace=workspace_dir,
            cleanup_status="quarantine_retained",
            manual_action_required=True,
            receipt=_receipt(node_name, staging_dir, quarantine_dir),
        )
    return None


def prepare_isolation(node_name, artifact_type="coding"):
    """Prepare one Task-owned workspace, preserving anything not provably owned."""
    if not isinstance(node_name, str) or not _NODE_NAME_RE.fullmatch(node_name):
        return _failure("node_name 不合法，僅接受英文字母開頭的英數底線名稱")
    if artifact_type not in ISOLATION_POLICY:
        return _failure(f"未知的 artifact 類型: {artifact_type}")

    project_root = os.path.abspath(os.getcwd())
    agents_dir = os.path.join(project_root, ".agents")
    tasks_dir = os.path.join(agents_dir, "tasks")
    if _identity(agents_dir) is None or _identity(tasks_dir) is None:
        return _failure(".agents 或 .agents/tasks 不是安全目錄")

    task_path = os.path.join(tasks_dir, f"{node_name}.task.json")
    if not _direct_child(task_path, tasks_dir, f"{node_name}.task.json") or not _safe_regular_file(task_path):
        return _failure(f"任務快照不存在或不安全: {task_path}，請先確認任務已核發")
    try:
        with open(task_path, "r", encoding="utf-8") as task_file:
            task_data = json.load(task_file)
    except (OSError, json.JSONDecodeError) as exc:
        return _failure(f"任務快照無法解析: {exc}")
    if (
        not isinstance(task_data, dict)
        or task_data.get("node_name") != node_name
        or task_data.get("status") not in _ALLOWED_TASK_STATUSES
    ):
        return _failure("任務快照 node_name 或 status 未通過 isolate gate")

    task_source = task_data.get("source_lock", {}).get("source_path")
    if _safe_project_file(project_root, task_source) is None:
        return _failure("任務快照未提供安全的 Source Lock source_path")

    workspace_root = os.path.join(agents_dir, "workspaces")
    if not os.path.exists(workspace_root):
        try:
            os.makedirs(workspace_root, exist_ok=False)
        except OSError as exc:
            return _failure(f"無法建立 workspace root: {exc}")
    if not _direct_child(workspace_root, agents_dir, "workspaces") or _identity(workspace_root) is None:
        return _failure("workspace root 不是安全目錄")

    workspace_dir = os.path.join(workspace_root, node_name)
    if not _direct_child(workspace_dir, workspace_root, node_name):
        return _failure("workspace 路徑驗證失敗")

    try:
        staging_dir = tempfile.mkdtemp(prefix=f".{node_name}.staging-", dir=workspace_root)
    except OSError as exc:
        return _failure(f"無法建立 staging workspace: {exc}")
    staging_identity = _identity(staging_dir)
    if staging_identity is None or not _direct_child(staging_dir, workspace_root):
        return _failure(
            "staging workspace 路徑驗證失敗",
            workspace=staging_dir,
            cleanup_status="staging_preserved",
            receipt=_receipt(node_name, staging_dir),
        )

    script_dir = os.path.dirname(os.path.abspath(__file__))
    read_context_script = os.path.join(script_dir, "read_context.py")
    result = subprocess.run(
        [sys.executable, read_context_script, node_name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=project_root,
    )
    if result.returncode != 0:
        return _failure(
            f"無法取得上下文: {result.stderr}",
            workspace=staging_dir,
            cleanup_status="staging_preserved",
            receipt=_receipt(node_name, staging_dir),
        )
    try:
        context_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _failure(
            "解析上下文失敗",
            workspace=staging_dir,
            cleanup_status="staging_preserved",
            receipt=_receipt(node_name, staging_dir),
        )

    context_source = context_data.get("target_node", {}).get("source") if isinstance(context_data, dict) else None
    if not isinstance(context_source, str) or context_source.split("::", 1)[0] != task_source.split("::", 1)[0]:
        return _failure(
            "上下文 source 與 Task Source Lock 不一致",
            workspace=staging_dir,
            cleanup_status="staging_preserved",
            receipt=_receipt(node_name, staging_dir),
        )

    try:
        context_path = os.path.join(staging_dir, ISOLATION_POLICY[artifact_type]["context_dump"])
        with open(context_path, "w", encoding="utf-8") as context_file:
            json.dump(context_data, context_file, ensure_ascii=False, indent=2)

        copied_files = [
            _copy_project_file(project_root, staging_dir, task_source),
            _copy_project_file(project_root, staging_dir, os.path.relpath(task_path, project_root)),
        ]
        marker_path = os.path.join(staging_dir, _OWNER_MARKER)
        with open(marker_path, "w", encoding="utf-8") as marker_file:
            json.dump(
                {"version": 1, "node_name": node_name, "identity": staging_identity},
                marker_file,
                ensure_ascii=False,
                indent=2,
            )
    except (OSError, ValueError) as exc:
        return _failure(
            f"建立 staging 內容失敗: {exc}",
            workspace=staging_dir,
            cleanup_status="staging_preserved",
            receipt=_receipt(node_name, staging_dir),
        )

    publish_error = _publish_staging(workspace_dir, staging_dir, node_name)
    if publish_error is not None:
        return publish_error

    return {
        "success": True,
        "workspace": workspace_dir,
        "copied_files": copied_files,
        "context_dump": ISOLATION_POLICY[artifact_type]["context_dump"],
        "cleanup_status": "cleaned",
        "manual_action_required": False,
        "receipt": _receipt(node_name, staging_dir),
    }


def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print(json.dumps({"success": False, "error": "用法: python prepare_isolation.py <node_name> [artifact_type]"}, ensure_ascii=False))
        sys.exit(1)

    node_name = sys.argv[1]
    artifact_type = sys.argv[2] if len(sys.argv) == 3 else "coding"
    result = prepare_isolation(node_name, artifact_type)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
