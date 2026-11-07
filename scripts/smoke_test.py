"""Live connectivity check for Hindsight and Groq.

It deliberately fails if Hindsight is unreachable; there is no local store.

Run locally:
    export HINDSIGHT_BASE_URL=https://your-cloud-url
    export HINDSIGHT_API_KEY=...
    export GROQ_API_KEY=...          # optional; skipped if absent
    python smoke_test.py

Exit codes: 0 = passed, 1 = failed.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

try:
    from src.core.memory import MemoryStore
except ImportError:
    from memory import MemoryStore

load_dotenv()


def main() -> int:
    base_url = os.getenv("HINDSIGHT_BASE_URL") or "http://localhost:8888"
    bank_id = os.getenv("SMOKE_BANK_ID") or (os.getenv("HINDSIGHT_BANK_ID") or "incident-response-agent") + "-smoke"

    print(f"Hindsight URL: {base_url}")
    print(f"Smoke bank:    {bank_id}")

    store = MemoryStore(base_url=base_url, bank_id=bank_id)
    backend = store.connect()
    if backend != "hindsight":
        print(f"FAIL: Hindsight did not connect. Fallback reason: {store.error}", file=sys.stderr)
        store.close()
        return 1
    print("PASS: Hindsight connected (probe recall succeeded)")

    token = f"SMOKE-{uuid.uuid4().hex[:10].upper()}"
    document = (
        f"Incident ID: INC-999999\n"
        f"Date: {datetime.now(timezone.utc).isoformat()}\n"
        f"Service: smoke-test\n"
        f"Title: Live smoke test {token}\n"
        f"Root cause: this document verifies retain and recall.\n"
        f"Resolution:\n1. Find the token {token} in a recall result.\n"
        f"What failed (made it worse):\n- None; this is a synthetic smoke test.\n"
        f"TTR: 1 minutes\n"
        f"Responder: smoke-test"
    )
    try:
        store.retain(document, context=f"live smoke test {token}")
    except Exception as exc:
        print(f"FAIL: retain() raised {type(exc).__name__}: {exc}", file=sys.stderr)
        store.close()
        return 1
    print("PASS: retain() accepted a document")

    try:
        memories = store.recall(token, limit=5)
    except Exception as exc:
        print(f"FAIL: recall() raised {type(exc).__name__}: {exc}", file=sys.stderr)
        store.close()
        return 1
    if not any(token in memory.text for memory in memories):
        print(f"FAIL: recall() did not return the retained token. Results: {len(memories)}", file=sys.stderr)
        for memory in memories:
            print(f"  - {memory.text[:120]}", file=sys.stderr)
        store.close()
        return 1
    print(f"PASS: recall() returned the token ({len(memories)} results)")

    try:
        answer = store.reflect("What did the live smoke test retain?")
    except Exception as exc:
        print(f"FAIL: reflect() raised {type(exc).__name__}: {exc}", file=sys.stderr)
        store.close()
        return 1
    if not answer.strip():
        print("FAIL: reflect() returned an empty answer", file=sys.stderr)
        store.close()
        return 1
    print(f"PASS: reflect() returned {len(answer)} characters")

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        print("SKIP: GROQ_API_KEY not set; LLM call not tested")
        store.close()
        return 0

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=groq_key,
            base_url=os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL") or "openai/gpt-oss-120b",
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            temperature=0,
            max_tokens=100,
        )
        content = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"FAIL: Groq call raised {type(exc).__name__}: {exc}", file=sys.stderr)
        store.close()
        return 1
    store.close()
    if "OK" not in content.upper():
        print(f"FAIL: unexpected Groq response: {content!r}", file=sys.stderr)
        return 1
    print(f"PASS: Groq model {os.getenv('LLM_MODEL') or 'openai/gpt-oss-120b'} replied {content!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
