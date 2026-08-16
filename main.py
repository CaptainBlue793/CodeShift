"""CodeShift CLI entry point.

Example:
    python main.py --source ./data/inputs/myapp --from python --to typescript
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Optional, Sequence

from codeshift.config import settings
from codeshift.graph import build_graph
from codeshift.state import new_state


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="codeshift",
        description="Multi-agent, behavior-preserving code migration.",
    )
    p.add_argument("--source", required=True, help="Path to the source codebase.")
    p.add_argument("--from", dest="source_lang", default="python",
                   help="Source language (v1: python).")
    p.add_argument("--to", dest="target_lang", default="typescript",
                   help="Target language (v1: typescript).")
    p.add_argument("--output", default="data/output",
                   help="Directory for translated code + report.")
    p.add_argument("--max-retries", type=int, default=settings.max_retries,
                   help="Translate<->verify retries per file.")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    # Reports contain Unicode (generated test inputs); avoid a cp1252 console crash.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    graph = build_graph()
    state = new_state(
        source_root=args.source,
        output_root=args.output,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        max_retries=args.max_retries,
    )
    final = graph.invoke(state, config={"recursion_limit": settings.recursion_limit})

    report = final.get("report")
    if report:
        report_path = Path(args.output) / "REPORT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        print(report)
        print(f"\n[report written to {report_path}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
