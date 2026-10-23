#!/usr/bin/env python
"""Start the ICMR STW Knowledge Retrieval API server.

Usage:
    python scripts/serve_api.py
    python scripts/serve_api.py --host 0.0.0.0 --port 8080 --reload

The API serves:
    POST /api/v1/retrieve       — Hybrid clinical evidence retrieval
    GET  /api/v1/documents      — List indexed STW documents
    GET  /api/v1/documents/{id} — Document metadata
    GET  /api/v1/review/items   — Review queue
    GET  /api/v1/health         — Health check
    GET  /api/docs              — OpenAPI interactive docs
    GET  /api/redoc             — ReDoc documentation

Requires:
    Run 'python scripts/build_index.py' first to build the knowledge index.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from src.api.routes import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="ICMR STW Retrieval API server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload for development")
    parser.add_argument(
        "--structured-dir",
        default="data/processed/structured",
        help="Directory containing canonical STW JSON files",
    )
    parser.add_argument(
        "--knowledge-dir",
        default="data/knowledge",
        help="Directory containing built knowledge indexes",
    )
    args = parser.parse_args()

    knowledge_dir = Path(args.knowledge_dir)
    if not (knowledge_dir / "knowledge.db").exists():
        print(
            f"[ERROR] Knowledge index not found at {knowledge_dir}.\n"
            "Run 'python scripts/build_index.py' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    app = create_app(
        structured_dir=Path(args.structured_dir),
        knowledge_dir=knowledge_dir,
    )

    print(f"Starting ICMR STW Retrieval API on http://{args.host}:{args.port}")
    print(f"  Docs: http://{args.host}:{args.port}/api/docs")
    print(f"  Health: http://{args.host}:{args.port}/api/v1/health")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
