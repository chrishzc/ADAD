# -*- coding: utf-8 -*-
import json
import os
import copy
from pathlib import Path, PurePosixPath, PureWindowsPath

def resolve_verification_fixture_inputs(case: dict, project_root: str) -> dict:
    """
    ponytail: resolve verification case fixture inputs idempotently.
    """
    if not isinstance(case, dict):
        raise ValueError("case must be a dict")
    if "input" not in case or not isinstance(case["input"], dict):
        raise ValueError("case['input'] must be a dict")
        
    if "fixtures" in case:
        fixtures = case["fixtures"]
        if fixtures is None:
            raise ValueError("fixtures must not be null")
        if not isinstance(fixtures, list):
            raise ValueError("fixtures must be a list")
    else:
        fixtures = []
        
    resolved_case = copy.deepcopy(case)
    new_input = resolved_case["input"]
    
    seen_keys = set()
    for desc in fixtures:
        if not isinstance(desc, dict):
            raise ValueError("fixture descriptor must be a dict")
        if set(desc.keys()) != {"input_key", "source"}:
            raise ValueError("fixture descriptor must only contain input_key and source")
            
        input_key = desc["input_key"]
        source = desc["source"]
        
        if not isinstance(input_key, str) or not input_key:
            raise ValueError("input_key must be a non-empty string")
        if not isinstance(source, str) or not source:
            raise ValueError("source must be a non-empty string")
            
        # Reject absolute paths, Windows drive-relative/drive-qualified, and UNC paths on all platforms
        p_win = PureWindowsPath(source)
        if PurePosixPath(source).is_absolute() or p_win.is_absolute() or Path(source).is_absolute():
            raise ValueError(f"fixture source must not be an absolute path: {source}")
        if p_win.drive != "" or source.startswith(("\\\\", "//")):
            raise ValueError(f"fixture source must not be a Windows drive or UNC path: {source}")
            
        if input_key in seen_keys:
            raise ValueError(f"duplicate input_key: {input_key}")
        seen_keys.add(input_key)
        
        # Refuse existing input key conflict
        if input_key in case["input"]:
            raise ValueError(f"input_key conflict: {input_key} already exists in case input")
            
        # Resolve path and check it is within project_root
        abs_project_root = Path(project_root).resolve()
        abs_source = Path(os.path.join(str(abs_project_root), source)).resolve()
        
        try:
            abs_source.relative_to(abs_project_root)
        except ValueError:
            raise ValueError(f"fixture source is outside project root: {source}")
            
        if not abs_source.is_file():
            raise ValueError(f"fixture source file not found or not a regular file: {source}")
            
        # Read and parse strict UTF-8 JSON
        with open(abs_source, "r", encoding="utf-8") as f:
            data = json.load(f)
                
        new_input[input_key] = data
        
    return resolved_case
