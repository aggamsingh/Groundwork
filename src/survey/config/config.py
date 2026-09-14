"""Run configuration — one object, serialised with every run.

CLAUDE.md requires that every retrieval hop be explainable and that ablations be
attributable. Both depend on this: a run is reproducible only if the exact
settings that produced it were recorded, and Phase 3 compares eight techniques by
diffing configs rather than by remembering what was set at the time.

**Every default here is unjustified** (C-006). They exist so the pipeline runs,
not because they were measured. `justified` records which ones have since been
backed by an eval run, and `describe_unjustified()` prints the rest — so a report
can never quietly present a guessed default as a finding.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChunkingConfig(BaseModel):
    strategy: Literal["flat", "section", "paragraph"] = "flat"
    chunk_tokens: int = 512
    overlap_tokens: int = 0
    # Phase 3 item 2: prepend paper/section context before embedding.
    contextual_prefix: bool = False


class RetrievalConfig(BaseModel):
    mode: Literal["dense", "bm25", "hybrid"] = "dense"
    top_k: int = 5
    # Reciprocal rank fusion constant. 60 is the value from the original RRF
    # paper, carried over unexamined -- it has not been tuned on this corpus.
    rrf_k: int = 60
    dense_weight: float = 0.5
    bm25_weight: float = 0.5
    rerank: bool = False
    rerank_top_n: int = 50


class EmbeddingConfig(BaseModel):
    # Not chosen: the spec requires benchmarking two alternatives in Phase 3, and
    # D-020 constrains the field to what fits in 4 GB VRAM.
    model_name: str = "unset"
    dimensions: int = 0
    normalize: bool = True
    batch_size: int = 32


class GenerationConfig(BaseModel):
    # Config-swappable, never hardcoded (spec section 4). Unset until Q-B3 is
    # answered; a run with generation enabled and no model must fail loudly
    # rather than silently pick one.
    provider: str = "unset"
    model: str = "unset"
    temperature: float = 0.0
    max_tokens: int = 1024
    require_citations: bool = True


class VerificationConfig(BaseModel):
    """Phase 4. Thresholds are placeholders and are marked as such."""

    nli_model: str = "unset"
    entailment_threshold: float = 0.5
    # Drop the whole answer when this share of sentences fails entailment.
    max_unentailed_ratio: float = 0.34
    sufficiency_threshold: float = 0.5


class RunConfig(BaseModel):
    """The complete description of one pipeline run."""

    corpus: str = "semcom"
    phase: int = 2
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)

    # Settings whose value has been backed by a recorded eval run. Anything not
    # listed here is still a guess, however long it has been in the file.
    justified: list[str] = Field(default_factory=list)

    # Provenance, so a stored result can be tied back to the code that made it.
    code_version: str = "unset"
    embedding_model_version: str = "unset"
    notes: str = ""

    def fingerprint(self) -> str:
        """Stable hash of the settings that affect results.

        Excludes `notes` and `justified`, which are commentary: two runs with the
        same settings must share a fingerprint even if one has been annotated
        since.
        """
        payload = self.model_dump(exclude={"notes", "justified"})
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def flatten(self) -> dict[str, Any]:
        """Dotted key/value pairs, for experiment-tracker parameter logging."""
        out: dict[str, Any] = {}

        def walk(prefix: str, value: Any) -> None:
            if isinstance(value, dict):
                for key, sub in value.items():
                    walk(f"{prefix}.{key}" if prefix else key, sub)
            elif isinstance(value, list):
                out[prefix] = ",".join(str(v) for v in value)
            else:
                out[prefix] = value

        walk("", self.model_dump())
        return out

    def unjustified(self) -> list[str]:
        """Settings not yet backed by an eval run.

        Deliberately computed from `justified` rather than maintained by hand: a
        list of known-good settings is easy to keep honest, while a list of
        known-guesses rots the moment someone forgets to add to it.
        """
        tuneable = [
            key
            for key in self.flatten()
            if key.startswith(
                ("chunking.", "embedding.", "retrieval.", "verification.")
            )
        ]
        return sorted(set(tuneable) - set(self.justified))

    def describe_unjustified(self) -> str:
        pending = self.unjustified()
        if not pending:
            return "All tuneable settings have been justified by an eval run."
        lines = [
            f"{len(pending)} setting(s) are defaults, NOT results "
            "(C-006). Do not report these as findings:"
        ]
        flat = self.flatten()
        lines.extend(f"  {key} = {flat[key]!r}" for key in pending)
        return "\n".join(lines)


def default_config() -> RunConfig:
    """The Phase 2 naive baseline shape from spec section 5.

    Fixed 512-token flat chunks, dense-only, top-k=5, no reranking, no citation
    enforcement. This is the thing everything else is measured against, so its
    values come from the spec rather than from judgement.
    """
    return RunConfig(
        phase=2,
        chunking=ChunkingConfig(strategy="flat", chunk_tokens=512, overlap_tokens=0),
        retrieval=RetrievalConfig(mode="dense", top_k=5, rerank=False),
        generation=GenerationConfig(require_citations=False),
        notes="Phase 2 naive baseline (spec section 5). Not tuned.",
    )
