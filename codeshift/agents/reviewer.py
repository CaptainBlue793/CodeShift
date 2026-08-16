"""Reviewer/summarizer agent — produces the migration report.

Runs once at the end. Summarizes per-module status, drift caught and resolved,
unresolved risks, and coverage, then writes a Markdown report into the state.
"""
from __future__ import annotations

from codeshift.report.builder import build_report
from codeshift.state import MigrationState
from codeshift.utils.logging import get_logger

log = get_logger(__name__)


def run(state: MigrationState) -> dict:
    log.info("reviewer: building migration report")
    # TODO(reviewer): enrich with an LLM narrative (prompts/reviewer.md).
    return {"report": build_report(state)}
