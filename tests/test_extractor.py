import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extractor import extractor as ex  
from extractor import (  
    build_zero_shot_prompt,
    build_few_shot_prompt,
    build_chain_of_thought_prompt,
    load_documents,
    extract_kdes,
    dump_llm_outputs,
)


def _make_pdf(tmpdir: Path, name: str, body: str) -> str:
    """Create a minimal real PDF file on disk and return its path."""
    pytest.importorskip("pypdf")
    from reportlab.pdfgen import canvas
    path = tmpdir / name
    c = canvas.Canvas(str(path))
    for i, line in enumerate(body.splitlines() or [body]):
        c.drawString(72, 800 - i * 14, line)
    c.showPage()
    c.save()
    return str(path)


# 1) load_documents
def test_load_documents_reads_both_pdfs(tmp_path):
    pytest.importorskip("reportlab")
    p1 = _make_pdf(tmp_path, "a.pdf", "Alpha requirement one.\nAlpha requirement two.")
    p2 = _make_pdf(tmp_path, "b.pdf", "Beta says hello.")

    out = load_documents(p1, p2)
    assert set(out.keys()) == {p1, p2}
    assert "Alpha" in out[p1]
    assert "Beta" in out[p2]


def test_load_documents_rejects_missing_file(tmp_path):
    real = _make_pdf(tmp_path, "ok.pdf", "ok")
    with pytest.raises(FileNotFoundError):
        load_documents(real, str(tmp_path / "nope.pdf"))


# 2) build_zero_shot_prompt
def test_build_zero_shot_prompt_contains_document_and_format():
    doc = "The API server must enable audit logging."
    prompt = build_zero_shot_prompt(doc)
    assert isinstance(prompt, str)
    assert doc in prompt
    assert "Key Data Element" in prompt
    assert "JSON" in prompt
    assert "Example 1 text" not in prompt
    assert "Step 1" not in prompt


# 3) build_few_shot_prompt
def test_build_few_shot_prompt_contains_examples_and_document():
    doc = "kubelet must authenticate requests."
    prompt = build_few_shot_prompt(doc)
    assert doc in prompt
    assert "Example 1 text" in prompt
    assert "Example 2 text" in prompt
    assert "Example 3 text" in prompt
    assert "API server" in prompt


# 4) build_chain_of_thought_prompt
def test_build_chain_of_thought_prompt_contains_steps():
    doc = "etcd must use TLS."
    prompt = build_chain_of_thought_prompt(doc)
    assert doc in prompt
    for step in ("Step 1", "Step 2", "Step 3", "Step 4", "Step 5"):
        assert step in prompt
    assert "step-by-step" in prompt.lower()


# 5) extract_kdes
def test_extract_kdes_merges_across_chunks(monkeypatch, tmp_path):
    """
    Feed a long document that produces multiple chunks. Return different
    KDEs per chunk from the mocked LLM, and verify the YAML has the merged
    result (dedup by name, unioned requirements).
    """
    doc_text = ("API server must enable audit logging. " * 200)

    docs = {str(tmp_path / "cis-r1.pdf"): doc_text}

    chunk_outputs = iter([
        '{"elements": [{"name": "API server", '
        '"requirements": ["Enable audit logging"]}]}',
        '{"elements": [{"name": "api server", '
        '"requirements": ["Restrict anonymous auth"]}]}',
        '{"elements": [{"name": "etcd", '
        '"requirements": ["Encrypt at rest"]}]}',
    ])

    def fake_llm(prompt, max_new_tokens=512):
        try:
            return next(chunk_outputs)
        except StopIteration:
            return '{"elements": []}'

    monkeypatch.setattr(ex, "_run_llm", fake_llm)

    out_dir = tmp_path / "out"
    results = extract_kdes(
        docs, output_dir=str(out_dir), prompt_type="few_shot"
    )

    info = results[str(tmp_path / "cis-r1.pdf")]
    assert os.path.isfile(info["yaml_path"])
    with open(info["yaml_path"], "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    names = {v["name"].lower() for v in data.values()}
    assert names == {"api server", "etcd"}

    api = next(v for v in data.values() if v["name"].lower() == "api server")
    assert "Enable audit logging" in api["requirements"]
    assert "Restrict anonymous auth" in api["requirements"]

    assert len(info["prompts"]) >= 3
    assert len(info["llm_outputs"]) == len(info["prompts"])


# 6) dump_llm_outputs
def test_dump_llm_outputs_format(tmp_path):
    runs = [
        {
            "llm_name": "google/gemma-3-1b-it",
            "prompt": "PROMPT_TEXT_1",
            "prompt_type": "zero_shot",
            "llm_output": "LLM_OUTPUT_1",
        },
        {
            "llm_name": "google/gemma-3-1b-it",
            "prompt": "PROMPT_TEXT_2",
            "prompt_type": "few_shot",
            "llm_output": "LLM_OUTPUT_2",
        },
    ]
    out = tmp_path / "log.txt"
    dump_llm_outputs(runs, output_path=str(out))
    content = out.read_text(encoding="utf-8")
    for header in ("*LLM Name*", "*Prompt Used*", "*Prompt Type*", "*LLM Output*"):
        assert header in content
    assert "PROMPT_TEXT_1" in content
    assert "LLM_OUTPUT_2" in content
    assert "zero_shot" in content and "few_shot" in content
    assert content.count("*LLM Name*") == 2


# Extra: chunking and parsing helpers
def test_chunk_text_respects_size_and_cap():
    text = "A" * 10000
    chunks = ex._chunk_text(text, chunk_size=2000, overlap=0, max_chunks=50)
    assert len(chunks) == 5
    assert all(len(c) == 2000 for c in chunks)

    text_big = "A" * 1_000_000
    chunks_big = ex._chunk_text(text_big, chunk_size=2000, max_chunks=50)
    assert len(chunks_big) == 50


def test_parse_chunk_output_discards_garbage():
    good = '{"elements":[{"name":"etcd","requirements":["Use TLS"]}]}'
    assert ex._parse_chunk_output(good) == [
        {"name": "etcd", "requirements": ["Use TLS"]}
    ]

    fenced = '```json\n{"elements": [{"name":"etcd","requirements":["Use TLS"]}]}\n```'
    assert ex._parse_chunk_output(fenced) == [
        {"name": "etcd", "requirements": ["Use TLS"]}
    ]

    placeholder = '{"elements":[{"name":"etcd","requirements":["..."]}]}'
    assert ex._parse_chunk_output(placeholder) == []

    assert ex._parse_chunk_output("I don't know") == []
    assert ex._parse_chunk_output("") == []