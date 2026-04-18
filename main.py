import argparse
import os
import sys
from pathlib import Path

from extractor import (
    load_documents,
    extract_kdes,
    dump_llm_outputs,
)
from comparator import diff_names, diff_names_and_requirements
from executor import determine_controls, run_kubescape, write_csv


def _pair_tag(path1: str, path2: str) -> str:
    """Create a short identifier for the input pair, e.g. 'cis-r1__cis-r2'."""
    return f"{Path(path1).stem}__{Path(path2).stem}"


def main():
    parser = argparse.ArgumentParser(
        description="Run the full extractor->comparator->executor pipeline."
    )
    parser.add_argument("pdf1", help="Path to first PDF")
    parser.add_argument("pdf2", help="Path to second PDF")
    parser.add_argument(
        "--prompt-type",
        choices=["zero_shot", "few_shot", "chain_of_thought"],
        default="few_shot",
        help="Which prompt style to use for the YAML KDE files that feed "
             "Task-2 (default: few_shot).",
    )
    parser.add_argument(
        "--scan-target",
        default="project-yamls.zip",
        help="Path to project-yamls.zip (or a directory of YAMLs) "
             "to scan with Kubescape.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory for all generated artifacts.",
    )
    parser.add_argument(
        "--skip-kubescape",
        action="store_true",
        help="Skip the Task-3 Kubescape scan (useful when only testing "
             "extraction/comparison).",
    )
    parser.add_argument(
        "--only-selected-prompt",
        action="store_true",
        help="Only run the selected --prompt-type (skip the other two). "
             "Speeds things up roughly 3x, but the llm_outputs.txt "
             "transcript will only cover one prompt style.",
    )
    args = parser.parse_args()

    pair = _pair_tag(args.pdf1, args.pdf2)
    out_dir = os.path.join(args.output_dir, pair)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # TASK 1: Extraction
    print(f"[Task 1] Loading documents: {args.pdf1}  and  {args.pdf2}")
    docs = load_documents(args.pdf1, args.pdf2)

    styles = (
        [args.prompt_type]
        if args.only_selected_prompt
        else ["zero_shot", "few_shot", "chain_of_thought"]
    )

    from extractor.extractor import _chunk_text
    per_doc_chunks = {p: len(_chunk_text(t)) for p, t in docs.items()}
    chunks_per_style = sum(per_doc_chunks.values())
    total_calls = chunks_per_style * len(styles)
    print(
        f"[Task 1] Chunks per document: "
        + ", ".join(f"{Path(p).name}={n}" for p, n in per_doc_chunks.items())
    )
    print(
        f"[Task 1] Total LLM calls planned: {total_calls}  "
        f"({chunks_per_style} chunks per style x {len(styles)} styles)"
    )

    all_runs = []
    selected_yaml_paths = {}
    completed_calls = [0]

    def _progress(doc_path, prompt_type, chunk_idx, total_chunks,
                  doc_num, total_docs, elapsed_sec, **_):
        completed_calls[0] += 1
        pct = completed_calls[0] / total_calls * 100 if total_calls else 100.0
        end = "\n" if (completed_calls[0] == total_calls
                       or (chunk_idx == total_chunks and doc_num == total_docs)) else "\r"
        print(
            f"  [{prompt_type:>17}] doc {doc_num}/{total_docs} "
            f"({Path(doc_path).name}): chunk {chunk_idx}/{total_chunks}  "
            f"|  overall {completed_calls[0]}/{total_calls} ({pct:5.1f}%)  "
            f"|  last call {elapsed_sec:5.1f}s",
            end=end,
            flush=True,
        )

    for style in styles:
        print(f"[Task 1] Extracting KDEs with prompt style: {style}")
        if style == args.prompt_type:
            style_out_dir = out_dir
        else:
            style_out_dir = os.path.join(out_dir, f"_{style}_yaml")
            Path(style_out_dir).mkdir(parents=True, exist_ok=True)

        results = extract_kdes(
            docs,
            output_dir=style_out_dir,
            prompt_type=style,
            progress_cb=_progress,
        )

        for path, info in results.items():
            for prompt, output in zip(info["prompts"], info["llm_outputs"]):
                all_runs.append({
                    "llm_name": "google/gemma-3-1b-it",
                    "prompt": prompt,
                    "prompt_type": style,
                    "llm_output": output,
                })
            if style == args.prompt_type:
                selected_yaml_paths[path] = info["yaml_path"]
                print(f"[Task 1] Wrote YAML ({style}): {info['yaml_path']}")

    llm_log = os.path.join(out_dir, "llm_outputs.txt")
    dump_llm_outputs(all_runs, output_path=llm_log)
    print(f"[Task 1] LLM transcript ({len(all_runs)} entries): {llm_log}")

    yaml1 = selected_yaml_paths.get(args.pdf1) or \
        os.path.join(out_dir, f"{Path(args.pdf1).stem}-kdes.yaml")
    yaml2 = selected_yaml_paths.get(args.pdf2) or \
        os.path.join(out_dir, f"{Path(args.pdf2).stem}-kdes.yaml")

    if not os.path.isfile(yaml1):
        print(f"[ERROR] Expected YAML missing: {yaml1}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(yaml2):
        yaml2 = yaml1

    # TASK 2: Comparison
    print("[Task 2] Comparing YAML files")
    name_diff_path = os.path.join(out_dir, "name_diff.txt")
    full_diff_path = os.path.join(out_dir, "full_diff.txt")
    diff_names(yaml1, yaml2, output_path=name_diff_path)
    diff_names_and_requirements(yaml1, yaml2, output_path=full_diff_path)
    print(f"[Task 2] Name diff:             {name_diff_path}")
    print(f"[Task 2] Name+requirement diff: {full_diff_path}")

    # TASK 3: Kubescape execution
    controls_path = os.path.join(out_dir, "controls_to_run.txt")
    determine_controls(name_diff_path, full_diff_path, output_path=controls_path)
    print(f"[Task 3] Controls decision:     {controls_path}")

    if args.skip_kubescape:
        print("[Task 3] Skipping Kubescape scan (per --skip-kubescape).")
        return

    if not os.path.exists(args.scan_target):
        print(f"[Task 3] Scan target not found: {args.scan_target}. "
              f"Skipping Kubescape scan.")
        return

    print(f"[Task 3] Running Kubescape against {args.scan_target}")
    df = run_kubescape(
        controls_txt_path=controls_path,
        scan_target=args.scan_target,
        output_json=os.path.join(out_dir, "kubescape_result.json"),
    )
    csv_path = os.path.join(out_dir, "kubescape_results.csv")
    write_csv(df, csv_path=csv_path)
    print(f"[Task 3] CSV written to:        {csv_path}")


if __name__ == "__main__":
    main()