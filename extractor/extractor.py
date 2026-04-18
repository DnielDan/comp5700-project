import json
import os
import re
from pathlib import Path

import yaml

try:
    import pypdf
except ImportError:
    pypdf = None

_MODEL = None
_TOKENIZER = None
_MODEL_NAME = "google/gemma-3-1b-it"

CHUNK_SIZE = 2000      
CHUNK_OVERLAP = 0      
MAX_CHUNKS = 25        #


# Function 1: Load and validate the two PDF documents
def load_documents(path1: str, path2: str) -> dict:
    """
    Load and validate two PDF documents.

    Returns a dict: {path1: text1, path2: text2}.
    Raises a ValueError/FileNotFoundError on invalid input.
    """
    if pypdf is None:
        raise ImportError("pypdf is required. Install with: pip install pypdf")

    results = {}
    for p in (path1, path2):
        if not isinstance(p, str) or not p.strip():
            raise ValueError(f"Invalid path: {p!r}")
        if not os.path.isfile(p):
            raise FileNotFoundError(f"File does not exist: {p}")
        if not p.lower().endswith(".pdf"):
            raise ValueError(f"File is not a PDF: {p}")
        if os.path.getsize(p) == 0:
            raise ValueError(f"File is empty: {p}")

        try:
            reader = pypdf.PdfReader(p)
            text_chunks = []
            for page in reader.pages:
                text_chunks.append(page.extract_text() or "")
            full_text = "\n".join(text_chunks).strip()
        except Exception as e:
            raise ValueError(f"Unable to parse PDF {p}: {e}")

        if not full_text:
            raise ValueError(f"No extractable text found in {p}")

        results[p] = full_text
    return results


# Helper: chunk a document's text
def _chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    max_chunks: int = MAX_CHUNKS,
) -> list:
    """
    Split `text` into a list of chunks, capped at max_chunks.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        overlap = 0

    chunks = []
    step = chunk_size - overlap
    i = 0
    while i < len(text):
        chunks.append(text[i:i + chunk_size])
        i += step

    if max_chunks and len(chunks) > max_chunks:
        chunks = chunks[:max_chunks]
    return chunks


# Function 2: Zero-shot prompt builder, operates on a single chunk
def build_zero_shot_prompt(document_text: str) -> str:
    """Construct a zero-shot prompt for KDE identification."""
    return (
        "You are a security requirements analyst.\n"
        "A Key Data Element (KDE) is a specific, named security-relevant "
        "artifact, asset, configuration item, or control object that has "
        "one or more requirements described in the text below.\n\n"
        "TASK: Read the text and list every Key Data Element you find. For "
        "each KDE, list the specific requirements associated with it.\n\n"
        "OUTPUT: a single JSON object of the form:\n"
        '{"elements": [{"name": "<KDE name>", '
        '"requirements": ["<req 1>", "<req 2>"]}]}\n'
        "If you find no KDEs in this text, return "
        '{"elements": []}. Return ONLY the JSON, no commentary, no '
        "markdown fences.\n\n"
        "TEXT:\n"
        f"{document_text}\n"
    )


# Function 3: Few-shot prompt builder, operates on a single chunk
def build_few_shot_prompt(document_text: str) -> str:
    """Construct a few-shot prompt for KDE identification."""
    return (
        "You are a security requirements analyst.\n"
        "A Key Data Element (KDE) is a specific, named security-relevant "
        "artifact, asset, configuration item, or control object that has "
        "one or more requirements described in the text. One KDE can map "
        "to multiple requirements.\n\n"
        "EXAMPLES:\n\n"
        "Example 1 text:\n"
        "'The API server must enable audit logging. The API server must "
        "restrict anonymous authentication.'\n"
        "Example 1 output:\n"
        '{"elements": [{"name": "API server", "requirements": '
        '["Enable audit logging", "Restrict anonymous authentication"]}]}\n\n'
        "Example 2 text:\n"
        "'etcd data should be encrypted at rest. etcd client communications "
        "must use TLS.'\n"
        "Example 2 output:\n"
        '{"elements": [{"name": "etcd", "requirements": '
        '["Encrypt data at rest", "Use TLS for client communications"]}]}\n\n'
        "Example 3 text:\n"
        "'Pod security policies should restrict privileged containers.'\n"
        "Example 3 output:\n"
        '{"elements": [{"name": "Pod security policy", "requirements": '
        '["Restrict privileged containers"]}]}\n\n'
        "Now produce the same JSON object for the following text. Return "
        "ONLY the JSON, no commentary, no markdown fences. If no KDEs are "
        'present, return {"elements": []}.\n\n'
        "TEXT:\n"
        f"{document_text}\n"
    )


# Function 4: Chain-of-thought prompt builder, operates on a single chunk
def build_chain_of_thought_prompt(document_text: str) -> str:
    """Construct a chain-of-thought prompt for KDE identification."""
    return (
        "You are a security requirements analyst.\n"
        "A Key Data Element (KDE) is a specific, named security-relevant "
        "artifact, asset, configuration item, or control object that has "
        "one or more requirements described in the text.\n\n"
        "Solve the task step-by-step (think silently, do not print your "
        "reasoning):\n"
        "Step 1: Read the text carefully.\n"
        "Step 2: Identify every noun phrase that names a security artifact "
        "or control target (e.g., 'API server', 'etcd', 'kubelet', 'Pod "
        "security policy').\n"
        "Step 3: For each identified artifact, find every sentence that "
        "states a requirement or configuration obligation on it.\n"
        "Step 4: Group the requirements under the artifact name. One KDE "
        "may map to multiple requirements.\n"
        "Step 5: Produce the final answer as a JSON object ONLY.\n\n"
        "FINAL OUTPUT FORMAT:\n"
        '{"elements": [{"name": "<KDE name>", '
        '"requirements": ["<req 1>", "<req 2>"]}]}\n'
        'If no KDEs are present, output {"elements": []}. Do not include '
        "any reasoning in the final output. Do not use markdown fences.\n\n"
        "TEXT:\n"
        f"{document_text}\n\n"
        "Final JSON:\n"
    )


# Helper: lazy load Gemma-3-1B
def _load_model():
    global _MODEL, _TOKENIZER
    if _MODEL is not None:
        return _MODEL, _TOKENIZER
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    _TOKENIZER = AutoTokenizer.from_pretrained(_MODEL_NAME)
    _MODEL = AutoModelForCausalLM.from_pretrained(
        _MODEL_NAME,
        torch_dtype=torch.float32,
        device_map="auto" if torch.cuda.is_available() else "cpu",
    )
    return _MODEL, _TOKENIZER


def _run_llm(prompt: str, max_new_tokens: int = 512) -> str:
    """Run Gemma-3-1B on a prompt and return the generated text."""
    import torch
    model, tokenizer = _load_model()

    messages = [{"role": "user", "content": prompt}]
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    )
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
        )
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


# Helper: parse JSON output from the LLM for a single chunk
def _parse_chunk_output(llm_output: str) -> list:
    """
    Extract a list of {"name": ..., "requirements": [...]} dicts from the
    LLM's raw output. Returns [] on any failure (invalid JSON, empty
    response, placeholder 'elements': '...', etc.).
    """
    if not llm_output or not llm_output.strip():
        return []

    text = llm_output.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return []
    candidate = text[start:end + 1]

    try:
        data = json.loads(candidate)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []
    elements = data.get("elements")
    if not isinstance(elements, list):
        return []

    clean = []
    for item in elements:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        reqs = item.get("requirements") or []
        if not isinstance(reqs, list):
            reqs = [str(reqs)]
        clean_reqs = []
        for r in reqs:
            if not isinstance(r, str):
                r = str(r)
            r = r.strip()
            if not r or r in ("...", "…") or r.startswith("<"):
                continue
            clean_reqs.append(r)
        if not clean_reqs:
            continue
        clean.append({"name": name.strip(), "requirements": clean_reqs})
    return clean


# Helper: merge KDE lists from many chunks
def _merge_kde_lists(all_chunk_results: list) -> list:
    """
    Merge a list-of-lists of KDEs into a single list. KDEs are
    by case-insensitive name; requirements are unioned (case-insensitive,
    preserving first-seen casing).
    """
    by_name = {}          
    seen_reqs = {}        

    for chunk_result in all_chunk_results:
        for kde in chunk_result:
            name = kde["name"].strip()
            key = name.lower()
            if key not in by_name:
                by_name[key] = {"name": name, "requirements": []}
                seen_reqs[key] = set()
            for req in kde["requirements"]:
                rkey = req.strip().lower()
                if rkey and rkey not in seen_reqs[key]:
                    seen_reqs[key].add(rkey)
                    by_name[key]["requirements"].append(req.strip())
    return list(by_name.values())


# Function 5: Run the map-reduce pipeline; write YAML per document
def extract_kdes(
    documents: dict,
    output_dir: str = "outputs",
    prompt_type: str = "few_shot",
    progress_cb=None,
) -> dict:
    """
    For each document:
      1. chunk the text (fast profile: 2000 chars, no overlap, max 50 chunks)
      2. call Gemma-3-1B once per chunk with the selected prompt style
      3. parse each response as JSON, merge across chunks

    Writes one YAML per document using the assignment's schema:
        element1:
          name: ...
          requirements:
            - ...

    `progress_cb`, if provided, is called after each chunk with kwargs:
        doc_path, prompt_type, chunk_idx, total_chunks,
        doc_num, total_docs, elapsed_sec
    Use this to print progress in the terminal.

    Returns a dict mapping each document path to:
        {
          "yaml_path": ...,
          "nested": ...,
          "prompt_type": ...,
          "prompts":     [prompt_chunk_1, prompt_chunk_2, ...],
          "llm_outputs": [raw_output_chunk_1, raw_output_chunk_2, ...],
        }
    """
    import time

    if prompt_type not in ("zero_shot", "few_shot", "chain_of_thought"):
        raise ValueError(
            "prompt_type must be one of zero_shot, few_shot, chain_of_thought"
        )

    builder = {
        "zero_shot": build_zero_shot_prompt,
        "few_shot": build_few_shot_prompt,
        "chain_of_thought": build_chain_of_thought_prompt,
    }[prompt_type]

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    result = {}

    doc_paths = list(documents.keys())
    total_docs = len(doc_paths)

    for doc_idx, path in enumerate(doc_paths, start=1):
        text = documents[path]
        chunks = _chunk_text(text)
        total_chunks = len(chunks)
        prompts, raw_outputs, parsed_per_chunk = [], [], []

        for idx, chunk in enumerate(chunks, 1):
            t0 = time.time()
            prompt = builder(chunk)
            prompts.append(prompt)
            try:
                raw = _run_llm(prompt)
            except Exception as e:
                raw = f"[LLM_ERROR on chunk {idx}: {e}]"
            raw_outputs.append(raw)
            parsed_per_chunk.append(_parse_chunk_output(raw))

            if progress_cb is not None:
                try:
                    progress_cb(
                        doc_path=path,
                        prompt_type=prompt_type,
                        chunk_idx=idx,
                        total_chunks=total_chunks,
                        doc_num=doc_idx,
                        total_docs=total_docs,
                        elapsed_sec=time.time() - t0,
                    )
                except Exception:
                    pass

        merged = _merge_kde_lists(parsed_per_chunk)

        nested = {}
        for i, kde in enumerate(merged, start=1):
            nested[f"element{i}"] = {
                "name": kde["name"],
                "requirements": kde["requirements"],
            }

        stem = Path(path).stem
        yaml_path = os.path.join(output_dir, f"{stem}-kdes.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(nested, f, sort_keys=False, allow_unicode=True)

        result[path] = {
            "yaml_path": yaml_path,
            "nested": nested,
            "prompt_type": prompt_type,
            "prompts": prompts,
            "llm_outputs": raw_outputs,
        }
    return result


# Function 6: Dump all LLM outputs to a single TEXT file
def dump_llm_outputs(
    runs: list,
    output_path: str = "outputs/llm_outputs.txt",
) -> str:
    """
    Dump LLM runs to a single text file with the required headers.

    `runs` is a list of dicts, each with keys:
        llm_name, prompt, prompt_type, llm_output

    (Each chunk call is a separate entry.)
    """
    Path(os.path.dirname(output_path) or ".").mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for run in runs:
            f.write("*LLM Name*\n")
            f.write(f"{run.get('llm_name', _MODEL_NAME)}\n\n")
            f.write("*Prompt Used*\n")
            f.write(f"{run.get('prompt', '')}\n\n")
            f.write("*Prompt Type*\n")
            f.write(f"{run.get('prompt_type', '')}\n\n")
            f.write("*LLM Output*\n")
            f.write(f"{run.get('llm_output', '')}\n")
            f.write("\n" + ("=" * 80) + "\n\n")
    return output_path