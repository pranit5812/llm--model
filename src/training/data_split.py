"""Dataset splitting and integrity verification with document-aware leakage prevention."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple


class DatasetSplitter:
    """Partitions generated instruction datasets into train, validation, and test splits."""

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def split_dataset(
        cls,
        examples: List[Dict[str, Any]],
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Document-aware stratified split preventing cross-partition leakage."""
        rng = random.Random(seed)

        # Separate into in-scope clinical examples and abstention examples
        clinical_examples = [e for e in examples if e["category"] != "safe_abstention"]
        abstention_examples = [e for e in examples if e["category"] == "safe_abstention"]

        # Group clinical examples by (document_id, condition, source_section)
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for e in clinical_examples:
            key = f"{e['document_id']}::{e['condition']}::{e['source_section']}"
            groups.setdefault(key, []).append(e)

        group_keys = list(groups.keys())
        rng.shuffle(group_keys)

        train_groups: List[str] = []
        val_groups: List[str] = []
        test_groups: List[str] = []

        total_examples = len(clinical_examples)
        target_train = int(total_examples * train_ratio)
        target_val = int(total_examples * val_ratio)

        curr_train = 0
        curr_val = 0

        for k in group_keys:
            cnt = len(groups[k])
            if curr_train + cnt <= target_train:
                train_groups.append(k)
                curr_train += cnt
            elif curr_val + cnt <= target_val:
                val_groups.append(k)
                curr_val += cnt
            else:
                test_groups.append(k)

        train_data: List[Dict[str, Any]] = []
        val_data: List[Dict[str, Any]] = []
        test_data: List[Dict[str, Any]] = []

        for k in train_groups:
            train_data.extend(groups[k])
        for k in val_groups:
            val_data.extend(groups[k])
        for k in test_groups:
            test_data.extend(groups[k])

        # Distribute negative abstention examples proportionally
        rng.shuffle(abstention_examples)
        n_abs = len(abstention_examples)
        n_abs_train = max(1, int(n_abs * train_ratio))
        n_abs_val = max(1, int(n_abs * val_ratio))

        train_data.extend(abstention_examples[:n_abs_train])
        val_data.extend(abstention_examples[n_abs_train:n_abs_train + n_abs_val])
        test_data.extend(abstention_examples[n_abs_train + n_abs_val:])

        # Final deterministic shuffle per split
        rng.shuffle(train_data)
        rng.shuffle(val_data)
        rng.shuffle(test_data)

        return train_data, val_data, test_data

    @classmethod
    def save_splits(
        cls,
        train_data: List[Dict[str, Any]],
        val_data: List[Dict[str, Any]],
        test_data: List[Dict[str, Any]],
        output_dir: Path = Path("data/evaluation"),
    ) -> Dict[str, Any]:
        """Persist splits and generate integrity hashes."""
        output_dir.mkdir(parents=True, exist_ok=True)

        train_path = output_dir / "train.json"
        val_path = output_dir / "validation.json"
        test_path = output_dir / "test.json"

        with open(train_path, "w", encoding="utf-8") as f:
            json.dump(train_data, f, indent=2)
        with open(val_path, "w", encoding="utf-8") as f:
            json.dump(val_data, f, indent=2)
        with open(test_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f, indent=2)

        summary = {
            "train_count": len(train_data),
            "validation_count": len(val_data),
            "test_count": len(test_data),
            "total_count": len(train_data) + len(val_data) + len(test_data),
            "hashes": {
                "train_sha256": cls.compute_sha256(train_path),
                "validation_sha256": cls.compute_sha256(val_path),
                "test_sha256": cls.compute_sha256(test_path),
            },
        }

        # Check for data leakage: no training example ID in test set
        train_ids = set(e["training_example_id"] for e in train_data)
        test_ids = set(e["training_example_id"] for e in test_data)
        overlap = train_ids & test_ids
        if overlap:
            raise ValueError(f"Data leakage detected! Overlapping IDs: {overlap}")

        return summary
