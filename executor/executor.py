"""
Task-3: Executor
Reads the two diff text files produced by the Comparator, determines which
Kubescape controls should be run, runs Kubescape, and writes the
results to a CSV file.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd


VALID_CONTROLS = {
    "C-0001", "C-0002", "C-0004", "C-0005", "C-0007", "C-0009", "C-0012",
    "C-0013", "C-0014", "C-0015", "C-0016", "C-0017", "C-0018", "C-0020",
    "C-0021", "C-0026", "C-0030", "C-0031", "C-0034", "C-0035", "C-0036",
    "C-0037", "C-0038", "C-0039", "C-0041", "C-0042", "C-0044", "C-0045",
    "C-0046", "C-0048", "C-0049", "C-0050", "C-0052", "C-0053", "C-0054",
    "C-0055", "C-0056", "C-0057", "C-0058", "C-0059", "C-0061", "C-0062",
    "C-0063", "C-0065", "C-0066", "C-0067", "C-0068", "C-0069", "C-0070",
    "C-0073", "C-0074", "C-0075", "C-0076", "C-0077", "C-0078", "C-0079",
    "C-0081", "C-0083", "C-0084", "C-0085", "C-0087", "C-0088", "C-0089",
    "C-0090", "C-0091", "C-0186", "C-0187", "C-0188", "C-0189", "C-0190",
    "C-0191", "C-0192", "C-0193", "C-0197", "C-0198", "C-0199", "C-0200",
    "C-0207", "C-0209", "C-0211", "C-0212", "C-0236", "C-0237", "C-0253",
    "C-0255", "C-0256", "C-0257", "C-0258", "C-0259", "C-0260", "C-0261",
    "C-0262", "C-0263", "C-0264", "C-0265", "C-0266", "C-0267", "C-0268",
    "C-0269", "C-0270", "C-0271", "C-0272", "C-0273", "C-0274", "C-0292",
}


# ---------------------------------------------------------------------------
# KDE -> Kubescape control mapping.
# Every control ID below has been verified against this Kubescape version's
# `kubescape list controls` output, so Kubescape will never reject them.
# Matching against KDE names is case-insensitive substring matching.
# ---------------------------------------------------------------------------
KDE_TO_CONTROLS = {
    # --- API server / Kubernetes control plane -----------------------------
    # C-0005 API server insecure port
    # C-0035 Administrative Roles
    # C-0067 Audit logs enabled
    "api server":         ["C-0005", "C-0035", "C-0067"],
    "apiserver":          ["C-0005", "C-0035", "C-0067"],
    "kube-apiserver":     ["C-0005", "C-0035", "C-0067"],
    "kubernetes api":     ["C-0005", "C-0035", "C-0067"],

    # --- etcd --------------------------------------------------------------
    # C-0066 Secret/etcd encryption enabled
    "etcd":               ["C-0066"],

    # --- kubelet -----------------------------------------------------------
    # C-0069 Disable anonymous access to Kubelet
    # C-0070 Enforce Kubelet client TLS authentication
    "kubelet":            ["C-0069", "C-0070"],

    # --- RBAC / authorization ----------------------------------------------
    # C-0035 Administrative Roles
    # C-0015 List Kubernetes secrets
    # C-0007 Roles with delete capabilities
    # C-0088 RBAC enabled
    # C-0186 Minimize access to secrets
    # C-0187 Minimize wildcard use in Roles
    # C-0188 Minimize access to create pods
    # C-0272 Workload with administrative roles
    "rbac":                     ["C-0035", "C-0088", "C-0187", "C-0188"],
    "role based access control":["C-0035", "C-0088", "C-0187", "C-0188"],
    "cluster role":             ["C-0035", "C-0186", "C-0187", "C-0272"],
    "roles":                    ["C-0035", "C-0186", "C-0187"],
    "service account":          ["C-0034", "C-0053", "C-0189", "C-0190"],
    "service accounts":         ["C-0034", "C-0053", "C-0189", "C-0190"],
    "authorization":            ["C-0035", "C-0088"],

    # --- Network policy / ingress / egress ---------------------------------
    # C-0030 Ingress and Egress blocked
    # C-0041 HostNetwork access
    # C-0260 Missing network policy
    # C-0263 Ingress uses TLS
    "network policy":     ["C-0030", "C-0260"],
    "network policies":   ["C-0030", "C-0260"],
    "ingress":            ["C-0030", "C-0263"],
    "egress":             ["C-0030"],
    "networking":         ["C-0030", "C-0054", "C-0260"],

    # --- Pod security ------------------------------------------------------
    # C-0013 Non-root containers
    # C-0016 Allow privilege escalation
    # C-0017 Immutable container filesystem
    # C-0038 Host PID/IPC privileges
    # C-0044 Container hostPort
    # C-0045 Writable hostPath mount
    # C-0046 Insecure capabilities
    # C-0055 Linux hardening
    # C-0057 Privileged container
    # C-0068 PSP enabled
    # C-0211 Apply Security Context
    "pod security policy":  ["C-0013", "C-0038", "C-0044", "C-0045", "C-0046", "C-0057", "C-0068"],
    "pod security standard":["C-0013", "C-0038", "C-0044", "C-0045", "C-0057", "C-0211"],
    "pod security":         ["C-0013", "C-0016", "C-0017", "C-0038", "C-0057", "C-0068", "C-0211"],
    "pod":                  ["C-0013", "C-0016", "C-0017", "C-0038", "C-0057", "C-0061"],
    "pods":                 ["C-0013", "C-0016", "C-0017", "C-0038", "C-0057", "C-0061"],
    "privileged container": ["C-0013", "C-0016", "C-0038", "C-0057", "C-0193"],
    "container":            ["C-0013", "C-0016", "C-0017", "C-0055", "C-0057"],
    "containers":           ["C-0013", "C-0016", "C-0017", "C-0055", "C-0057"],
    "workload":             ["C-0255", "C-0257", "C-0258", "C-0267", "C-0270", "C-0271", "C-0272"],
    "workloads":            ["C-0255", "C-0257", "C-0258", "C-0267", "C-0270", "C-0271", "C-0272"],

    # --- Secrets -----------------------------------------------------------
    # C-0012 Applications credentials in configuration files
    # C-0015 List Kubernetes secrets
    # C-0186 Minimize access to secrets
    # C-0190 Service Account Tokens mounted
    # C-0207 Prefer secrets as files over env vars
    # C-0255 Workload with secret access
    "secret":              ["C-0012", "C-0015", "C-0186", "C-0207"],
    "secrets":             ["C-0012", "C-0015", "C-0186", "C-0207", "C-0255"],
    "credential":          ["C-0012", "C-0259"],
    "credentials":         ["C-0012", "C-0259"],

    # --- Images / registries -----------------------------------------------
    # C-0001 Forbidden Container Registries
    # C-0075 Image pull policy on latest tag
    # C-0078 Images from allowed registry
    # C-0236 Verify image signature
    # C-0237 Check if signature exists
    "image":               ["C-0075", "C-0078", "C-0236", "C-0237"],
    "container image":     ["C-0075", "C-0078", "C-0236"],
    "images":              ["C-0075", "C-0078", "C-0236"],
    "registry":            ["C-0001", "C-0078"],
    "registries":          ["C-0001", "C-0078"],

    # --- Logging / auditing ------------------------------------------------
    # C-0067 Audit logs enabled
    # C-0068 PSP enabled (kept from audit context)
    "audit":               ["C-0067"],
    "audit log":           ["C-0067"],
    "audit logs":          ["C-0067"],
    "audit logging":       ["C-0067"],
    "logging":             ["C-0067"],

    # --- Namespaces --------------------------------------------------------
    # C-0061 Pods in default namespace
    # C-0209 Create administrative boundaries using namespaces
    # C-0212 The default namespace should not be used
    "namespace":           ["C-0061", "C-0209", "C-0212"],
    "namespaces":          ["C-0061", "C-0209", "C-0212"],

    # --- TLS / certificates ------------------------------------------------
    # C-0070 Enforce Kubelet client TLS authentication
    # C-0263 Ingress uses TLS
    "tls":                 ["C-0070", "C-0263"],
    "certificate":         ["C-0070"],
    "certificates":        ["C-0070"],

    # --- Resource limits ---------------------------------------------------
    # C-0004 Memory limit and request
    # C-0009 Resource limits
    # C-0050 CPU limit and request
    # C-0268 Ensure CPU requests set
    # C-0269 Ensure memory requests set
    # C-0270 Ensure CPU limits set
    # C-0271 Ensure memory limits set
    "resource limit":      ["C-0004", "C-0009", "C-0050", "C-0270", "C-0271"],
    "resource limits":     ["C-0004", "C-0009", "C-0050", "C-0270", "C-0271"],
    "resource quota":      ["C-0004", "C-0050"],
    "memory limit":        ["C-0004", "C-0269", "C-0271"],
    "cpu limit":           ["C-0050", "C-0268", "C-0270"],
    "limit range":         ["C-0004", "C-0050"],

    # --- Volumes / storage -------------------------------------------------
    # C-0045 Writable hostPath mount
    # C-0048 HostPath mount
    # C-0257 Workload with PVC access
    # C-0264 PersistentVolume without encryption
    "volume":              ["C-0045", "C-0048", "C-0264"],
    "volumes":             ["C-0045", "C-0048", "C-0264"],
    "persistent volume":   ["C-0257", "C-0264"],
    "hostpath":            ["C-0045", "C-0048"],
}


# Function 1: Load both text files from Task-2
def load_diff_files(name_diff_path: str, full_diff_path: str) -> dict:
    """Load the two TEXT files produced by Task-2."""
    results = {}
    for p in (name_diff_path, full_diff_path):
        if not isinstance(p, str) or not p.strip():
            raise ValueError(f"Invalid path: {p!r}")
        if not os.path.isfile(p):
            raise FileNotFoundError(f"Diff file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            results[p] = f.read()
    return {
        "name_diff_path": name_diff_path,
        "name_diff_text": results[name_diff_path],
        "full_diff_path": full_diff_path,
        "full_diff_text": results[full_diff_path],
    }


# Function 2: Decide which controls to run
def determine_controls(
    name_diff_path: str,
    full_diff_path: str,
    output_path: str = "outputs/controls_to_run.txt",
) -> str:
    """
    If neither diff file reports any differences, write 'NO DIFFERENCES FOUND'.
    Otherwise, map the differing KDE names to Kubescape controls and write
    them to the output file (one control per line).
    """
    diffs = load_diff_files(name_diff_path, full_diff_path)
    name_text = diffs["name_diff_text"].strip()
    full_text = diffs["full_diff_text"].strip()

    no_name_diff = name_text.startswith("NO DIFFERENCES IN REGARDS TO ELEMENT NAMES")
    no_full_diff = full_text.startswith("NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS")

    Path(os.path.dirname(output_path) or ".").mkdir(parents=True, exist_ok=True)

    if no_name_diff and no_full_diff:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("NO DIFFERENCES FOUND\n")
        return output_path

    kde_names = set()
    for line in name_text.splitlines():
        line = line.strip()
        if not line or line.startswith("NO DIFFERENCES"):
            continue
        m = re.match(r"(.+?)\s*\(only in", line)
        if m:
            kde_names.add(m.group(1).strip())
        else:
            kde_names.add(line)

    for line in full_text.splitlines():
        line = line.strip()
        if not line or line.startswith("NO DIFFERENCES"):
            continue
        parts = line.split(",", 3)
        if parts:
            kde_names.add(parts[0].strip())

    controls = set()
    for name in kde_names:
        lname = name.lower()
        for key, ctrls in KDE_TO_CONTROLS.items():
            if key in lname:
                controls.update(ctrls)

    controls = {c for c in controls if c in VALID_CONTROLS}

    with open(output_path, "w", encoding="utf-8") as f:
        if not controls:
            f.write("NO DIFFERENCES FOUND\n")
        else:
            for c in sorted(controls):
                f.write(f"{c}\n")
    return output_path


# Function 3: Run Kubescape and return a DataFrame
def _find_kubescape() -> str:
    """Locate the kubescape executable."""
    exe = shutil.which("kubescape")
    if exe:
        return exe
    # Windows convenience
    for candidate in ("kubescape.exe",
                      r"C:\Program Files\kubescape\kubescape.exe"):
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        "kubescape executable not found on PATH. "
        "Install from https://github.com/kubescape/kubescape"
    )


def _scan_target_from_zip(zip_path: str, work_dir: str) -> str:
    """Unzip project-yamls.zip into work_dir and return the extracted path."""
    import zipfile
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(work_dir)
    return work_dir


def run_kubescape(
    controls_txt_path: str,
    scan_target: str,
    output_json: str = "outputs/kubescape_result.json",
) -> pd.DataFrame:
    """
    Run Kubescape based on controls_txt_path.

    `scan_target` can be a directory of YAMLs OR a path to project-yamls.zip.
    If it's a zip, it is extracted first.

    Returns a pandas DataFrame of per-control results.
    """
    if not os.path.isfile(controls_txt_path):
        raise FileNotFoundError(f"Controls file not found: {controls_txt_path}")

    with open(controls_txt_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # Prepare the scan target
    if scan_target.lower().endswith(".zip"):
        target_dir = os.path.join(
            os.path.dirname(output_json) or ".", "_scan_target"
        )
        scan_path = _scan_target_from_zip(scan_target, target_dir)
    else:
        scan_path = scan_target

    Path(os.path.dirname(output_json) or ".").mkdir(parents=True, exist_ok=True)
    kubescape = _find_kubescape()

    def _build_framework_cmd() -> list:
        return [
            kubescape, "scan", "framework", "allcontrols",
            scan_path,
            "--format", "json",
            "--output", output_json,
        ]

    def _build_controls_cmd(controls: list) -> list:
        return [
            kubescape, "scan", "control", ",".join(controls),
            scan_path,
            "--format", "json",
            "--output", output_json,
        ]

    if content == "NO DIFFERENCES FOUND" or not content:
        cmd = _build_framework_cmd()
        fallback_cmd = None
    else:
        controls = [line.strip() for line in content.splitlines() if line.strip()]
        cmd = _build_controls_cmd(controls)
        fallback_cmd = _build_framework_cmd()

    try:
        if os.path.isfile(output_json):
            os.remove(output_json)
    except OSError:
        pass

    result = subprocess.run(cmd, check=False)

    targeted_failed = (
        not os.path.isfile(output_json)
        or os.path.getsize(output_json) == 0
    )

    if targeted_failed and fallback_cmd is not None:
        print(
            "[Task 3] Targeted Kubescape scan failed "
            f"(return code {result.returncode}); "
            "falling back to 'allcontrols' framework.",
            flush=True,
        )
        try:
            if os.path.isfile(output_json):
                os.remove(output_json)
        except OSError:
            pass
        subprocess.run(fallback_cmd, check=False)

    if not os.path.isfile(output_json) or os.path.getsize(output_json) == 0:
        raise RuntimeError(
            f"Kubescape did not produce any output at {output_json}. "
            "Check that kubescape can scan the target and that at least "
            "one control/framework is valid."
        )

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = _flatten_kubescape_json(data)
    return pd.DataFrame(rows)


def _flatten_kubescape_json(data) -> list:
    """
    Flatten a Kubescape JSON report into per-(resource, control) rows.

    Produces rows with keys:
        FilePath, Severity, Control name, Failed resources, All Resources,
        Compliance score
    """
    summary = (data or {}).get("summaryDetails") or {}
    summary_controls = summary.get("controls") or {}

    ctrl_meta = {}
    if isinstance(summary_controls, dict):
        for cid, meta in summary_controls.items():
            ctrl_meta[cid] = meta or {}
    elif isinstance(summary_controls, list):
        for meta in summary_controls:
            cid = (meta or {}).get("controlID") or (meta or {}).get("id")
            if cid:
                ctrl_meta[cid] = meta

    results = (data or {}).get("results") or []
    resources = {
        r.get("resourceID"): r
        for r in ((data or {}).get("resources") or [])
        if isinstance(r, dict)
    }

    rows = []
    for item in results:
        res_id = item.get("resourceID", "")
        res_obj = resources.get(res_id, {}) or {}
        file_path = (res_obj.get("source") or {}).get("path") or res_id

        controls_on_resource = item.get("controls") or []
        for c in controls_on_resource:
            cid = c.get("controlID") or c.get("controlId") or ""
            meta = ctrl_meta.get(cid, {}) or {}

            control_name = (
                c.get("name")
                or meta.get("name")
                or cid
            )
            severity = (
                meta.get("severity")
                or (meta.get("scoreFactor") and "N/A")
                or c.get("severity")
                or "N/A"
            )

            resource_counts = meta.get("ResourceCounters") or meta.get("resourceCounters") or {}
            failed = resource_counts.get("failedResources",
                                         resource_counts.get("failed", 0))
            passed = resource_counts.get("passedResources",
                                         resource_counts.get("passed", 0))
            skipped = resource_counts.get("skippedResources",
                                          resource_counts.get("skipped", 0))
            all_res = (failed or 0) + (passed or 0) + (skipped or 0)

            compliance = meta.get("complianceScore")
            if compliance is None:
                compliance = meta.get("score")

            rows.append({
                "FilePath": file_path,
                "Severity": severity,
                "Control name": control_name,
                "Failed resources": failed or 0,
                "All Resources": all_res or 0,
                "Compliance score": compliance if compliance is not None else "N/A",
            })

    if not rows and ctrl_meta:
        for cid, meta in ctrl_meta.items():
            rc = meta.get("ResourceCounters") or meta.get("resourceCounters") or {}
            failed = rc.get("failedResources", rc.get("failed", 0)) or 0
            passed = rc.get("passedResources", rc.get("passed", 0)) or 0
            skipped = rc.get("skippedResources", rc.get("skipped", 0)) or 0
            rows.append({
                "FilePath": "N/A",
                "Severity": meta.get("severity", "N/A"),
                "Control name": meta.get("name", cid),
                "Failed resources": failed,
                "All Resources": failed + passed + skipped,
                "Compliance score":
                    meta.get("complianceScore",
                             meta.get("score", "N/A")),
            })
    return rows


# Function 4: Write the CSV
def write_csv(df: pd.DataFrame, csv_path: str = "outputs/kubescape_results.csv") -> str:
    """Write the scan DataFrame to CSV with the required headers."""
    required = [
        "FilePath", "Severity", "Control name",
        "Failed resources", "All Resources", "Compliance score",
    ]
    for col in required:
        if col not in df.columns:
            df[col] = "N/A"
    df = df[required]

    Path(os.path.dirname(csv_path) or ".").mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    return csv_path