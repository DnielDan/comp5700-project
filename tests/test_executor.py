import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from executor import ( 
    load_diff_files,
    determine_controls,
    run_kubescape,
    write_csv,
)
from executor import executor as exec_mod


# 1) load_diff_files
def test_load_diff_files_reads_both(tmp_path):
    name_p = tmp_path / "name_diff.txt"
    full_p = tmp_path / "full_diff.txt"
    name_p.write_text("etcd (only in a-kdes.yaml)\n", encoding="utf-8")
    full_p.write_text(
        "etcd,ABSENT-IN-b-kdes.yaml,PRESENT-IN-a-kdes.yaml,NA\n",
        encoding="utf-8",
    )
    out = load_diff_files(str(name_p), str(full_p))
    assert "etcd" in out["name_diff_text"]
    assert "ABSENT-IN-b-kdes.yaml" in out["full_diff_text"]


# 2) determine_controls
def test_determine_controls_maps_differences(tmp_path):
    name_p = tmp_path / "name_diff.txt"
    full_p = tmp_path / "full_diff.txt"
    name_p.write_text("etcd (only in a-kdes.yaml)\n", encoding="utf-8")
    full_p.write_text(
        "API server,ABSENT-IN-b-kdes.yaml,PRESENT-IN-a-kdes.yaml,Enable audit logging\n",
        encoding="utf-8",
    )
    out = tmp_path / "controls.txt"
    determine_controls(str(name_p), str(full_p), output_path=str(out))
    content = out.read_text(encoding="utf-8")
    assert "C-0066" in content
    assert "C-0005" in content
    assert "NO DIFFERENCES FOUND" not in content


def test_determine_controls_no_diff(tmp_path):
    name_p = tmp_path / "name_diff.txt"
    full_p = tmp_path / "full_diff.txt"
    name_p.write_text("NO DIFFERENCES IN REGARDS TO ELEMENT NAMES\n", encoding="utf-8")
    full_p.write_text("NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS\n", encoding="utf-8")
    out = tmp_path / "controls.txt"
    determine_controls(str(name_p), str(full_p), output_path=str(out))
    assert out.read_text(encoding="utf-8").strip() == "NO DIFFERENCES FOUND"


# 3) run_kubescape  (subprocess + kubescape binary are mocked)
def test_run_kubescape_returns_dataframe(monkeypatch, tmp_path):
    controls_p = tmp_path / "controls.txt"
    controls_p.write_text("C-0005\nC-0042\n", encoding="utf-8")

    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    (scan_dir / "deploy.yaml").write_text("kind: Deployment\n", encoding="utf-8")

    out_json = tmp_path / "result.json"

    fake_report = {
        "summaryDetails": {
            "controls": {
                "C-0005": {
                    "name": "API server insecure port",
                    "severity": "High",
                    "ResourceCounters": {
                        "failedResources": 1,
                        "passedResources": 0,
                        "skippedResources": 0,
                    },
                    "complianceScore": 0.0,
                },
                "C-0042": {
                    "name": "etcd encryption",
                    "severity": "Medium",
                    "ResourceCounters": {
                        "failedResources": 0,
                        "passedResources": 1,
                        "skippedResources": 0,
                    },
                    "complianceScore": 100.0,
                },
            }
        },
        "resources": [
            {"resourceID": "r1", "source": {"path": "deploy.yaml"}},
        ],
        "results": [
            {
                "resourceID": "r1",
                "controls": [
                    {"controlID": "C-0005", "name": "API server insecure port"},
                    {"controlID": "C-0042", "name": "etcd encryption"},
                ],
            }
        ],
    }

    monkeypatch.setattr(exec_mod, "_find_kubescape",
                        lambda: "/fake/kubescape")

    def fake_run(cmd, check=False, **kwargs):
        if "--output" in cmd:
            idx = cmd.index("--output")
            path = cmd[idx + 1]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(fake_report, f)

        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(exec_mod.subprocess, "run", fake_run)

    df = run_kubescape(
        controls_txt_path=str(controls_p),
        scan_target=str(scan_dir),
        output_json=str(out_json),
    )
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= {
        "FilePath", "Severity", "Control name",
        "Failed resources", "All Resources", "Compliance score",
    }
    assert len(df) == 2
    assert "API server insecure port" in df["Control name"].tolist()


# 4) write_csv
def test_write_csv_has_required_headers(tmp_path):
    df = pd.DataFrame([
        {
            "FilePath": "a.yaml",
            "Severity": "High",
            "Control name": "API server",
            "Failed resources": 1,
            "All Resources": 2,
            "Compliance score": 50.0,
        }
    ])
    out = tmp_path / "result.csv"
    write_csv(df, csv_path=str(out))

    with open(out, "r", encoding="utf-8") as f:
        header = f.readline().strip()
    assert header == "FilePath,Severity,Control name,Failed resources,All Resources,Compliance score"
