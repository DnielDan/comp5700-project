import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comparator import ( 
    load_yaml_files,
    diff_names,
    diff_names_and_requirements,
)


def _write_yaml(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


# 1) load_yaml_files
def test_load_yaml_files_returns_tuples(tmp_path):
    a = tmp_path / "a-kdes.yaml"
    b = tmp_path / "b-kdes.yaml"
    _write_yaml(a, {"element1": {"name": "API server", "requirements": ["r1"]}})
    _write_yaml(b, {"element1": {"name": "etcd", "requirements": ["r2"]}})

    (p1, d1), (p2, d2) = load_yaml_files(str(a), str(b))
    assert p1 == str(a) and p2 == str(b)
    assert d1["element1"]["name"] == "API server"
    assert d2["element1"]["name"] == "etcd"


# 2) diff_names
def test_diff_names_reports_differing_names(tmp_path):
    a = tmp_path / "a-kdes.yaml"
    b = tmp_path / "b-kdes.yaml"
    _write_yaml(a, {
        "element1": {"name": "API server", "requirements": ["r1"]},
        "element2": {"name": "etcd",       "requirements": ["r2"]},
    })
    _write_yaml(b, {
        "element1": {"name": "API server", "requirements": ["r1"]},
        "element2": {"name": "kubelet",    "requirements": ["r3"]},
    })

    out = tmp_path / "name_diff.txt"
    diff_names(str(a), str(b), output_path=str(out))
    content = out.read_text(encoding="utf-8")
    assert "etcd" in content
    assert "kubelet" in content
    assert "API server" not in content


def test_diff_names_no_differences(tmp_path):
    a = tmp_path / "a-kdes.yaml"
    b = tmp_path / "b-kdes.yaml"
    _write_yaml(a, {"element1": {"name": "API server", "requirements": []}})
    _write_yaml(b, {"element1": {"name": "API server", "requirements": []}})

    out = tmp_path / "name_diff.txt"
    diff_names(str(a), str(b), output_path=str(out))
    content = out.read_text(encoding="utf-8")
    assert "NO DIFFERENCES IN REGARDS TO ELEMENT NAMES" in content


# 3) diff_names_and_requirements
def test_diff_names_and_requirements_produces_tuples(tmp_path):
    a = tmp_path / "a-kdes.yaml"
    b = tmp_path / "b-kdes.yaml"
    _write_yaml(a, {
        "element1": {"name": "API server", "requirements": ["Enable audit logging"]},
        "element2": {"name": "etcd",       "requirements": ["Encrypt at rest"]},
    })
    _write_yaml(b, {
        "element1": {"name": "API server", "requirements": ["Restrict anon auth"]},
    })

    out = tmp_path / "full_diff.txt"
    diff_names_and_requirements(str(a), str(b), output_path=str(out))
    content = out.read_text(encoding="utf-8")

    assert "etcd,ABSENT-IN-b-kdes.yaml,PRESENT-IN-a-kdes.yaml,NA" in content
    assert "API server,ABSENT-IN-b-kdes.yaml,PRESENT-IN-a-kdes.yaml,Enable audit logging" in content
    assert "API server,ABSENT-IN-a-kdes.yaml,PRESENT-IN-b-kdes.yaml,Restrict anon auth" in content