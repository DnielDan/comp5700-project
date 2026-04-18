# COMP 5700 Project: Security Requirements Diff + Kubescape

## Team

- Daniel Choi — dhc0018@auburn.edu

## LLM

Task-1 uses **Google Gemma-3-1B** (model ID: `google/gemma-3-1b-it`)
via HuggingFace Transformers.

## Continuous Integration

All test cases from Tasks 1, 2, and 3 run automatically on every push and
pull request via GitHub Actions. See the latest run here:

https://github.com/DnielDan/comp5700-project/actions/runs/24593915818

## Install

    pip install -r requirements.txt

## Run one input pair

    python main.py inputs/cis-r1.pdf inputs/cis-r1.pdf

Flags:

--prompt-type {zero_shot,few_shot,chain_of_thought}    # default: few_shot
--scan-target project-yamls.zip                        # default
--output-dir  outputs                                  # default
--skip-kubescape                                       # skip Task 3 scan

## Running the tests

    pytest -q

## Run all 9 combinations

On Windows PowerShell:

    .\run_all.ps1

On Linux/Mac:

    chmod +x run_all.sh
    ./run_all.sh

Each run writes artifacts under `outputs/<stem1>__<stem2>/`.

## Running the binary (PyInstaller)

From an activated venv:

    pip install pyinstaller
    pyinstaller --onefile --name comp5700-pipeline main.py `
        --collect-all transformers `
        --collect-all tokenizers `
        --collect-all torch `
        --collect-data pypdf `
        --hidden-import sentencepiece

Produces `dist/comp5700-pipeline.exe` (Windows) or `dist/comp5700-pipeline`
(Linux/Mac). Run it the same way as `python main.py`:

    .\dist\comp5700-pipeline.exe inputs\cis-r1.pdf inputs\cis-r2.pdf

Or via the wrapper script with the `-UseBinary` flag:

    .\run_all.ps1 -UseBinary

## Runtime expectations

Total runtime depends on your hardware. Per pair, the pipeline makes up
to 150 LLM calls (25 chunks × 2 docs × 3 prompt styles) plus one
Kubescape scan.

| Hardware                          | Per pair        | All 9 combos   |
|-----------------------------------|-----------------|----------------|
| NVIDIA GPU (tested on RTX 3060 Ti)| ~20–30 minutes  | ~3–4.5 hours   |
| CPU only                          | ~60 minutes     | ~9 hours       |

The first run also downloads the Gemma-3-1B weights (~2 GB) from
HuggingFace.