# Prompts Used for Key Data Element (KDE) Extraction

Target model: `google/gemma-3-1b-it` (Gemma-3-1B, instruction-tuned).

Each prompt operates on a **single chunk** of the PDF (≈2000 characters,
no overlap, max 50 chunks per document). The extractor calls the LLM once
per chunk per prompt style, then merges all chunk results by deduplicating
KDEs by name (case-insensitive) and unioning their requirements.

Each prompt asks for a JSON object of the form:

```json
{"elements": [{"name": "<KDE name>", "requirements": ["<req 1>", "<req 2>"]}]}
```

The JSON is then converted to the assignment's required YAML schema
(`element1`, `element2`, …) before being written to disk.

The `{CHUNK}` placeholder is substituted with one chunk of extracted PDF
text at runtime.

---

## Zero-shot

```
You are a security requirements analyst.
A Key Data Element (KDE) is a specific, named security-relevant artifact,
asset, configuration item, or control object that has one or more
requirements described in the text below.

TASK: Read the text and list every Key Data Element you find. For each KDE,
list the specific requirements associated with it.

OUTPUT: a single JSON object of the form:
{"elements": [{"name": "<KDE name>", "requirements": ["<req 1>", "<req 2>"]}]}
If you find no KDEs in this text, return {"elements": []}. Return ONLY the
JSON, no commentary, no markdown fences.

TEXT:
{CHUNK}
```

---

## Few-shot

```
You are a security requirements analyst.
A Key Data Element (KDE) is a specific, named security-relevant artifact,
asset, configuration item, or control object that has one or more
requirements described in the text. One KDE can map to multiple
requirements.

EXAMPLES:

Example 1 text:
'The API server must enable audit logging. The API server must restrict
anonymous authentication.'
Example 1 output:
{"elements": [{"name": "API server", "requirements": ["Enable audit logging", "Restrict anonymous authentication"]}]}

Example 2 text:
'etcd data should be encrypted at rest. etcd client communications must
use TLS.'
Example 2 output:
{"elements": [{"name": "etcd", "requirements": ["Encrypt data at rest", "Use TLS for client communications"]}]}

Example 3 text:
'Pod security policies should restrict privileged containers.'
Example 3 output:
{"elements": [{"name": "Pod security policy", "requirements": ["Restrict privileged containers"]}]}

Now produce the same JSON object for the following text. Return ONLY the
JSON, no commentary, no markdown fences. If no KDEs are present, return
{"elements": []}.

TEXT:
{CHUNK}
```

---

## Chain-of-thought

```
You are a security requirements analyst.
A Key Data Element (KDE) is a specific, named security-relevant artifact,
asset, configuration item, or control object that has one or more
requirements described in the text.

Solve the task step-by-step (think silently, do not print your reasoning):
Step 1: Read the text carefully.
Step 2: Identify every noun phrase that names a security artifact or
control target (e.g., 'API server', 'etcd', 'kubelet', 'Pod security
policy').
Step 3: For each identified artifact, find every sentence that states a
requirement or configuration obligation on it.
Step 4: Group the requirements under the artifact name. One KDE may map to
multiple requirements.
Step 5: Produce the final answer as a JSON object ONLY.

FINAL OUTPUT FORMAT:
{"elements": [{"name": "<KDE name>", "requirements": ["<req 1>", "<req 2>"]}]}
If no KDEs are present, output {"elements": []}. Do not include any
reasoning in the final output. Do not use markdown fences.

TEXT:
{CHUNK}

Final JSON:
```
