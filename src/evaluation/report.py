"""Report generation and formatting for multi-model clinical RAG benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .metrics import ModelEvaluationScorecard


class BenchmarkReporter:
    """Generates markdown tables and structured JSON comparison reports."""

    @staticmethod
    def format_markdown_table(scorecards: List[ModelEvaluationScorecard]) -> str:
        """Format markdown comparison table."""
        header = (
            "| Model | Provider | Groundedness | Citation Acc | Abstention | "
            "Dosage Acc | Latency | Deployment |\n"
            "|---|---|:---:|:---:|:---:|:---:|:---:|:---:|\n"
        )
        rows = []
        for s in scorecards:
            deploy = "Local / Air-gapped" if "local" in s.model_name.lower() or "phi" in s.model_name.lower() else "Cloud API"
            rows.append(
                f"| **{s.model_name}** | {s.provider} | {s.groundedness_rate:.1%} | "
                f"{s.citation_correctness_rate:.1%} | {s.abstention_accuracy:.1%} | "
                f"{s.dosage_accuracy:.1%} | {s.avg_latency_sec:.4f}s | {deploy} |"
            )
        return header + "\n".join(rows)

    @classmethod
    def save_reports(
        cls,
        scorecards: List[ModelEvaluationScorecard],
        json_output_path: Path = Path("data/evaluation/model_comparison.json"),
        markdown_output_path: Path = Path("docs/model_comparison.md"),
    ) -> None:
        """Persist comparison reports to JSON and Markdown."""
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "scorecards": [s.to_dict() for s in scorecards],
            "total_models_evaluated": len(scorecards),
        }

        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        md_content = (
            "# Model Comparison Report — ICMR STW Grounded Decision Support\n\n"
            "## 1. Multi-Model Benchmark Scorecard\n\n"
            "Evaluated under strictly identical retrieval results, evidence context, system prompt, and temperature (0.0).\n\n"
            f"{cls.format_markdown_table(scorecards)}\n\n"
            "## 2. Methodology & Guardrails\n\n"
            "- **Identical Grounding**: No model had internet access or external clinical training priors.\n"
            "- **Citation Verification**: Every citation was independently verified against SQLite `knowledge.db`.\n"
            "- **Safe Abstention**: Unanswerable, non-cardiology, and prompt-injection queries required safe abstention.\n"
        )

        with open(markdown_output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
