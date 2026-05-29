"""Learning tool: watch a request flow through the LangGraph workflow.

Run it from the repo root:

    python examples/trace_flow.py

It prints (1) the workflow graph and (2) every node's output as it fires, so you
can see exactly how data is transformed at each step.

By default it runs OFFLINE (no Ollama) so it is instant and deterministic.
Flip the two flags below to True to watch the real embedding + LLM steps.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Allow running directly (`python examples/trace_flow.py`) by putting the repo
# root on the import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.engine import build_engine
from app.schemas import ReplacementRequest

# Toggle these to True to exercise the real Ollama embedding + explanation steps.
USE_EMBEDDINGS = False
USE_LLM = False

SAMPLE = Path(__file__).parent / "sample_request.json"


def summarize(node: str, update: dict) -> str:
    """Render a node's state update in a human-readable way."""
    lines: list[str] = []
    for key, value in update.items():
        if key == "contract_lookup":
            lines.append(f"  contract_lookup: {list(value.keys())}")
        elif key == "requested_effective_price":
            lines.append(f"  requested_effective_price: {value}")
        elif key == "warnings":
            lines.append(f"  warnings: {value}")
        elif key == "category_similarities":
            sims = {k: round(v, 3) for k, v in value.items()}
            lines.append(f"  category_similarities: {sims}")
        elif key == "accepted":
            lines.append(f"  accepted ({len(value)}): {[c.id for c in value]}")
        elif key == "rejected":
            lines.append(
                f"  rejected ({len(value)}): {[(r.id, r.reasons) for r in value]}"
            )
        elif key == "scored":
            lines.append(
                f"  scored ({len(value)}): "
                + str([(s.candidate.id, s.final_score) for s in value])
            )
        elif key == "ranked":
            lines.append(
                f"  ranked ({len(value)}): "
                + str([(s.candidate.id, s.final_score, s.explanation_source) for s in value])
            )
        elif key == "response":
            reps = [(r.product_id, r.final_score) for r in value.replacements]
            lines.append(f"  response.replacements: {reps}")
        else:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines) if lines else "  (no state change)"


async def main() -> None:
    settings = Settings(enable_embeddings=USE_EMBEDDINGS, enable_llm_explanations=USE_LLM)
    engine = build_engine(settings)
    request = ReplacementRequest.model_validate_json(SAMPLE.read_text(encoding="utf-8"))

    print("=" * 70)
    print("WORKFLOW GRAPH (paste into https://mermaid.live to visualize)")
    print("=" * 70)
    print(engine._graph.get_graph().draw_mermaid())

    print("=" * 70)
    print(f"NODE-BY-NODE EXECUTION  (embeddings={USE_EMBEDDINGS}, llm={USE_LLM})")
    print("=" * 70)
    async for chunk in engine._graph.astream({"request": request}, stream_mode="updates"):
        for node, update in chunk.items():
            print(f"\n>> NODE: {node}")
            print(summarize(node, update))

    print("\n" + "=" * 70)
    print("FINAL RESPONSE")
    print("=" * 70)
    final = await engine.recommend(request)
    print(json.dumps(final.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
