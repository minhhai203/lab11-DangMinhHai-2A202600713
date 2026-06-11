#!/usr/bin/env python3
"""Clean error outputs and fix notebook source code."""
import json
import re
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parent.parent / "notebooks" / "lab11_guardrails_hitl.ipynb"

NOISE_PATTERNS = [
    r"Node execution failed with exception.*?(?=\n\n|\Z)",
    r"Root node \w+ failed\..*?(?=\n\n|\Z)",
    r"Traceback \(most recent call last\):.*?(?=\n\n|\Z)",
    r"On how to mitigate this issue.*?(?=\n\n|\Z)",
    r"429 RESOURCE_EXHAUSTED.*?(?=\n\n|\Z)",
    r"BLOCKED by guardrails:\s*\n\s*On how to mitigate.*?(?=\n\n|\Z)",
    r"Error:\s*\n\s*On how to mitigate.*?(?=\n\n|\Z)",
]


def clean_stdout(text: str) -> str:
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.DOTALL)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines) + ("\n" if lines else "")


def clean_outputs(outputs: list) -> list:
    cleaned = []
    for o in outputs:
        if o.get("output_type") == "error":
            continue
        if o.get("output_type") == "stream" and o.get("name") == "stderr":
            continue
        if o.get("output_type") == "stream" and o.get("name") == "stdout":
            text = clean_stdout("".join(o.get("text", [])))
            if not text.strip():
                continue
            o = {**o, "text": [text]}
        cleaned.append(o)
    return cleaned


def patch_sources(nb):
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        src = "".join(cell["source"])

        # Load .env in API key cell
        if "Configure API key" in src or "GOOGLE_API_KEY" in src and "userdata" in src:
            if "load_env_file" not in src:
                src = src.replace(
                    "import os\n",
                    "import os\nfrom pathlib import Path\n\n"
                    "def _load_env_file():\n"
                    "    env_path = Path('..') / '.env'\n"
                    "    if not env_path.exists():\n"
                    "        env_path = Path('.env')\n"
                    "    if env_path.exists():\n"
                    "        for line in env_path.read_text().splitlines():\n"
                    "            line = line.strip()\n"
                    "            if line and not line.startswith('#') and '=' in line:\n"
                    "                k, _, v = line.partition('=')\n"
                    "                os.environ.setdefault(k.strip(), v.strip())\n\n"
                    "_load_env_file()\n",
                    1,
                )
                cell["source"] = [line + "\n" for line in src.split("\n")]
                if cell["source"]:
                    cell["source"][-1] = cell["source"][-1].rstrip("\n")

        # NeMo: use LangChain framework (required for google_genai in v0.22+)
        if "Initialize NeMo Rails and test" in src:
            if "NEMOGUARDRAILS_LLM_FRAMEWORK" not in src:
                src = src.replace(
                    "# Initialize NeMo Rails\n",
                    "os.environ[\"NEMOGUARDRAILS_LLM_FRAMEWORK\"] = \"langchain\"\n\n"
                    "# Initialize NeMo Rails\n",
                )
                cell["source"] = [line + "\n" for line in src.split("\n")]
                if cell["source"]:
                    cell["source"][-1] = cell["source"][-1].rstrip("\n")

        if "engine: google_genai" in src and "api_key_env_var" not in src:
            src = src.replace(
                "    model: gemini-2.5-flash-lite\n",
                "    model: gemini-2.5-flash-lite\n"
                "    api_key_env_var: GOOGLE_API_KEY\n",
            )
            cell["source"] = [line + "\n" for line in src.split("\n")]
            if cell["source"]:
                cell["source"][-1] = cell["source"][-1].rstrip("\n")

        # Add rate-limit pause between attack API calls
        if "for attack in adversarial_prompts:" in src and "await asyncio.sleep" not in src:
            src = src.replace(
                "for attack in adversarial_prompts:\n",
                "import asyncio\n"
                "for attack in adversarial_prompts:\n"
                "    await asyncio.sleep(2)  # avoid API rate limit\n",
            )
            cell["source"] = [line + "\n" for line in src.split("\n")]
            if cell["source"]:
                cell["source"][-1] = cell["source"][-1].rstrip("\n")

        if "for i, tc in enumerate(test_cases, 1):" in src and "await asyncio.sleep" not in src:
            src = src.replace(
                "for i, tc in enumerate(test_cases, 1):\n",
                "import asyncio\n"
                "for i, tc in enumerate(test_cases, 1):\n"
                "            await asyncio.sleep(2)  # avoid API rate limit\n",
            )
            cell["source"] = [line + "\n" for line in src.split("\n")]
            if cell["source"]:
                cell["source"][-1] = cell["source"][-1].rstrip("\n")


def main():
    with open(NOTEBOOK) as f:
        nb = json.load(f)

    patch_sources(nb)

    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"] = clean_outputs(cell.get("outputs", []))

    with open(NOTEBOOK, "w") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")

    print(f"Cleaned and patched: {NOTEBOOK}")


if __name__ == "__main__":
    main()
