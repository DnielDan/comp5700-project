# COMP 5700 Project: Security Requirements Diff + Kubescape

## Team

- Daniel Choi — dhc0018@auburn.edu

## LLM

Task-1 uses **Google Gemma-3-1B** (model ID: `google/gemma-3-1b-it`)
via HuggingFace Transformers.

## Install

pip install -r requirements.txt

## Run one input pair

python main.py inputs/cis-r1.pdf inputs/cis-r1.pdf

Flags:

--prompt-type {zero_shot,few_shot,chain_of_thought}    # default: few_shot
--scan-target project-yamls.zip                        # default
--output-dir  outputs                                  # default
--skip-kubescape                                       # skip Task 3 scan

## Run all 9 combinations

python main.py inputs/cis-r1.pdf inputs/cis-r1.pdf
python main.py inputs/cis-r1.pdf inputs/cis-r2.pdf
python main.py inputs/cis-r1.pdf inputs/cis-r3.pdf
python main.py inputs/cis-r1.pdf inputs/cis-r4.pdf
python main.py inputs/cis-r2.pdf inputs/cis-r2.pdf
python main.py inputs/cis-r2.pdf inputs/cis-r3.pdf
python main.py inputs/cis-r2.pdf inputs/cis-r4.pdf
python main.py inputs/cis-r3.pdf inputs/cis-r3.pdf
python main.py inputs/cis-r3.pdf inputs/cis-r4.pdf

## Running the tests

pytest -q

## Running the binary
