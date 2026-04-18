# COMP 5700 Project: Security Requirements Diff + Kubescape

End-to-end pipeline:

```
 PDF1 + PDF2 ──► Task 1: Extractor (Gemma-3-1B, chunked map-reduce)
                  │ writes:
                  │   outputs/<pair>/<doc>-kdes.yaml
                  │   outputs/<pair>/llm_outputs.txt
                  ▼
                Task 2: Comparator
                  │ writes:
                  │   outputs/<pair>/name_diff.txt
                  │   outputs/<pair>/full_diff.txt
                  ▼
                Task 3: Executor
                  │ writes:
                  │   outputs/<pair>/controls_to_run.txt
                  │   outputs/<pair>/kubescape_results.csv
```

## How extraction works

Gemma-3-1B has a 32K context window, but the CIS Kubernetes Benchmark PDFs
are far too long to pass whole. The extractor therefore runs a
**map-reduce** pipeline:

1. **Map** — the PDF text is split into ~2000-character chunks (no overlap,
   max 50 chunks per document). The LLM is called once per chunk per
   prompt style, asking for a JSON `{"elements": [...]}` object.
2. **Parse** — each chunk response is JSON-parsed; invalid or empty
   responses are discarded.
3. **Reduce** — chunk results are merged: KDEs deduplicated by
   case-insensitive name, requirements unioned case-insensitively.
4. **Write** — the merged list is converted to the assignment's
   `element1/element2/...` YAML schema and written to
   `<doc>-kdes.yaml`.

Chunking knobs live at the top of `extractor/extractor.py`:
`CHUNK_SIZE`, `CHUNK_OVERLAP`, `MAX_CHUNKS`.

## Layout

```
project/
├── main.py                      # single CLI entry point
├── PROMPT.md                    # the three prompts used
├── requirements.txt
├── extractor/
│   ├── __init__.py
│   └── extractor.py             # Task 1 (6 functions)
├── comparator/
│   ├── __init__.py
│   └── comparator.py            # Task 2 (3 functions)
├── executor/
│   ├── __init__.py
│   └── executor.py              # Task 3 (4 functions)
├── tests/
│   ├── test_extractor.py
│   ├── test_comparator.py
│   └── test_executor.py
├── inputs/                      # put cis-r1.pdf .. cis-r4.pdf here
├── project-yamls.zip            # Kubescape scan target
└── outputs/                     # generated files
```

## Install

```
pip install -r requirements.txt
```

Plus the Kubescape CLI on PATH: <https://github.com/kubescape/kubescape>

## Run one input pair

```
python main.py inputs/cis-r1.pdf inputs/cis-r2.pdf
```

Flags:

```
--prompt-type {zero_shot,few_shot,chain_of_thought}   # default: few_shot
--scan-target project-yamls.zip                        # default
--output-dir  outputs                                  # default
--skip-kubescape                                       # skip Task 3 scan
--only-selected-prompt   # run only --prompt-type instead of all three (~3x faster)
```

## Run all 9 combinations

```
python main.py inputs/cis-r1.pdf inputs/cis-r1.pdf
python main.py inputs/cis-r1.pdf inputs/cis-r2.pdf
python main.py inputs/cis-r1.pdf inputs/cis-r3.pdf
python main.py inputs/cis-r1.pdf inputs/cis-r4.pdf
python main.py inputs/cis-r2.pdf inputs/cis-r2.pdf
python main.py inputs/cis-r2.pdf inputs/cis-r3.pdf
python main.py inputs/cis-r2.pdf inputs/cis-r4.pdf
python main.py inputs/cis-r3.pdf inputs/cis-r3.pdf
python main.py inputs/cis-r3.pdf inputs/cis-r4.pdf
```

Each run writes its artifacts under `outputs/<stem1>__<stem2>/`, so
combinations never overwrite each other.

## Runtime expectations

On CPU, each chunk takes Gemma-3-1B roughly 5–15 seconds. With the fast
profile (≤50 chunks per document × 2 documents × 3 prompt styles) that's
up to 300 LLM calls per pair → **30–90 minutes per pair**. Add
`--only-selected-prompt` to cut that to ~1/3.

On a CUDA-enabled GPU, divide by ~10×.

## Tests

```
pytest -q
```

The extractor tests monkey-patch the LLM call, so they run in seconds
without downloading Gemma weights.

## Notes on the KDE → Kubescape control mapping

`executor/executor.py` contains a curated dict `KDE_TO_CONTROLS` that maps
common CIS-Kubernetes KDEs (API server, etcd, kubelet, RBAC, Pod security
policy, etc.) to Kubescape control IDs. Matching is case-insensitive
substring matching against the KDE name. Extend the dict if Gemma emits
names you want to catch.

When both diff files report no differences, the executor runs Kubescape
against the `allcontrols` framework, as the assignment requires.
