"""
Task-2: Comparator
Compares two KDE YAML files produced by the Extractor.
"""

import os
from pathlib import Path
import yaml


# Function 1: Load both YAML files
def load_yaml_files(yaml_path_1: str, yaml_path_2: str) -> tuple:
    """
    Load two YAML files produced by the Extractor.

    Returns a tuple: ((path1, data1), (path2, data2)) where each data is the
    nested dict with element keys.
    """
    results = []
    for p in (yaml_path_1, yaml_path_2):
        if not isinstance(p, str) or not p.strip():
            raise ValueError(f"Invalid YAML path: {p!r}")
        if not os.path.isfile(p):
            raise FileNotFoundError(f"YAML file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected YAML structure in {p}")
        results.append((p, data))
    return tuple(results)


def _extract_names(data: dict) -> set:
    names = set()
    for _, v in (data or {}).items():
        if isinstance(v, dict) and "name" in v:
            names.add(str(v["name"]).strip())
    return names


def _extract_name_to_reqs(data: dict) -> dict:
    mapping = {}
    for _, v in (data or {}).items():
        if isinstance(v, dict) and "name" in v:
            name = str(v["name"]).strip()
            reqs = v.get("requirements") or []
            if not isinstance(reqs, list):
                reqs = [reqs]
            mapping[name] = {str(r).strip() for r in reqs if r}
    return mapping


# Function 2: Diff by KDE name only
def diff_names(
    yaml_path_1: str,
    yaml_path_2: str,
    output_path: str = "outputs/name_diff.txt",
) -> str:
    """
    Write a text file listing KDE names that differ between the two YAMLs.
    If none differ, write 'NO DIFFERENCES IN REGARDS TO ELEMENT NAMES'.
    """
    (_, data1), (_, data2) = load_yaml_files(yaml_path_1, yaml_path_2)
    names1 = _extract_names(data1)
    names2 = _extract_names(data2)

    only_in_1 = sorted(names1 - names2)
    only_in_2 = sorted(names2 - names1)

    Path(os.path.dirname(output_path) or ".").mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        if not only_in_1 and not only_in_2:
            f.write("NO DIFFERENCES IN REGARDS TO ELEMENT NAMES\n")
        else:
            fn1 = os.path.basename(yaml_path_1)
            fn2 = os.path.basename(yaml_path_2)
            for n in only_in_1:
                f.write(f"{n} (only in {fn1})\n")
            for n in only_in_2:
                f.write(f"{n} (only in {fn2})\n")
    return output_path


# Function 3: Diff by KDE name AND requirements
def diff_names_and_requirements(
    yaml_path_1: str,
    yaml_path_2: str,
    output_path: str = "outputs/full_diff.txt",
) -> str:
    """
    Write a text file with tuples describing name/requirement differences.

    Tuple format:
        NAME,ABSENT-IN-<FILENAME>,PRESENT-IN-<FILENAME>,NA       # KDE missing in one file
        NAME,ABSENT-IN-<FILENAME>,PRESENT-IN-<FILENAME>,REQ      # requirement missing in one file
    """
    (_, data1), (_, data2) = load_yaml_files(yaml_path_1, yaml_path_2)
    map1 = _extract_name_to_reqs(data1)
    map2 = _extract_name_to_reqs(data2)

    fn1 = os.path.basename(yaml_path_1)
    fn2 = os.path.basename(yaml_path_2)

    lines = []
    all_names = set(map1.keys()) | set(map2.keys())

    for name in sorted(all_names):
        in1 = name in map1
        in2 = name in map2

        if in1 and not in2:
            lines.append(f"{name},ABSENT-IN-{fn2},PRESENT-IN-{fn1},NA")
        elif in2 and not in1:
            lines.append(f"{name},ABSENT-IN-{fn1},PRESENT-IN-{fn2},NA")
        else:
            reqs1 = map1[name]
            reqs2 = map2[name]
            for req in sorted(reqs1 - reqs2):
                lines.append(
                    f"{name},ABSENT-IN-{fn2},PRESENT-IN-{fn1},{req}"
                )
            for req in sorted(reqs2 - reqs1):
                lines.append(
                    f"{name},ABSENT-IN-{fn1},PRESENT-IN-{fn2},{req}"
                )

    Path(os.path.dirname(output_path) or ".").mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        if not lines:
            f.write("NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS\n")
        else:
            f.write("\n".join(lines) + "\n")
    return output_path
