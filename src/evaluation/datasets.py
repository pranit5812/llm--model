"""Benchmark datasets loader and validator for ICMR STW model evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_BENCHMARK_PATH = Path("data/evaluation/model_benchmark_queries.json")


class BenchmarkDataset:
    """Loads and validates clinical benchmark evaluation datasets."""

    def __init__(self, dataset_path: Optional[Path] = None) -> None:
        self.path = dataset_path or DEFAULT_BENCHMARK_PATH
        self._queries: List[Dict[str, Any]] = []
        self._metadata: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"Benchmark dataset not found at {self.path.resolve()}")
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._metadata = {
            "description": data.get("description", ""),
            "corpus": data.get("corpus", ""),
        }
        self._queries = data.get("queries", [])

    @property
    def queries(self) -> List[Dict[str, Any]]:
        return self._queries

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    def get_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [q for q in self._queries if q.get("category") == category]

    def get_in_scope_queries(self) -> List[Dict[str, Any]]:
        return [q for q in self._queries if not q.get("should_abstain", False)]

    def get_abstention_queries(self) -> List[Dict[str, Any]]:
        return [q for q in self._queries if q.get("should_abstain", False)]

    def summary(self) -> Dict[str, Any]:
        categories: Dict[str, int] = {}
        for q in self._queries:
            cat = q.get("category", "uncategorized")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_queries": len(self._queries),
            "in_scope_queries": len(self.get_in_scope_queries()),
            "abstention_queries": len(self.get_abstention_queries()),
            "categories": categories,
        }
