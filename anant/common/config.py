from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def config_dir() -> Path:
    env = os.environ.get("ANANT_CONFIG_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[2] / "config"


def load_yaml(name: str) -> Dict[str, Any]:
    with open(config_dir() / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_system() -> Dict[str, Any]:
    return load_yaml("system.yaml")


def load_joints() -> Dict[str, Any]:
    cfg = load_yaml("joints.yaml")
    for j in cfg["joints"]:
        j.setdefault("sign", 1)
    return cfg


def load_expressions() -> Dict[str, Any]:
    """Returns {'by_name': {name: {id, joints}}, 'by_id': {id: name}}."""
    cfg = load_yaml("expressions.yaml")
    by_name = {e["name"]: e for e in cfg["expressions"]}
    return {"by_name": by_name, "by_id": {e["id"]: e["name"] for e in cfg["expressions"]}}


def load_zones() -> Dict[str, Any]:
    cfg = load_yaml("touch_zones.yaml")
    return {"zones": cfg["zones"], "by_id": {z["id"]: z["name"] for z in cfg["zones"]},
            "by_name": {z["name"]: z["id"] for z in cfg["zones"]}}
