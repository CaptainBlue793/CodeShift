"""Background execution of the migration graph for the Streamlit UI.

Streamlit reruns its script top-to-bottom on every interaction, so calling
`graph.invoke()` on the page thread would freeze it for the whole run (~20
minutes) and show nothing until the end. The graph runs on a worker thread
instead, publishing a **full state snapshot after every node** via
`stream_mode="values"`; the page drains those snapshots on each rerun.

Nothing in here touches `st.*`. Worker threads have no Streamlit script context,
so the queue is the only supported channel back to the page.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from codeshift.config import settings
from codeshift.graph import build_graph
from codeshift.state import new_state


@dataclass
class RunHandle:
    """Live handle on a background migration run."""

    events: "queue.Queue[tuple[str, Any]]" = field(default_factory=queue.Queue)
    thread: Optional[threading.Thread] = None
    finished: bool = False
    error: Optional[str] = None

    @property
    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def drain(self) -> list[dict]:
        """Pop every event published since the last call; return the snapshots.

        Errors and completion are recorded on the handle rather than returned,
        so the caller only has to deal with state.
        """
        snapshots: list[dict] = []
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                snapshots.append(payload)
            elif kind == "error":
                self.error = payload
            elif kind == "done":
                self.finished = True
        return snapshots


def _worker(
    events: "queue.Queue[tuple[str, Any]]",
    state: dict,
    output_root: str,
) -> None:
    final: dict[str, Any] = {}
    try:
        graph = build_graph()
        for snapshot in graph.stream(
            state,
            config={"recursion_limit": settings.recursion_limit},
            stream_mode="values",
        ):
            final = snapshot
            events.put(("state", snapshot))

        # Match the CLI: the report is part of the deliverable, not just the view.
        report = final.get("report")
        if report:
            path = Path(output_root) / "REPORT.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
    except Exception as exc:  # surfaced on the page; the console may not be visible
        events.put(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        events.put(("done", None))


def start_run(
    *,
    source_root: str,
    output_root: str,
    source_lang: str,
    target_lang: str,
    max_retries: int,
) -> RunHandle:
    """Kick off a migration on a daemon thread and return its handle."""
    handle = RunHandle()
    state = new_state(
        source_root=source_root,
        output_root=output_root,
        source_lang=source_lang,
        target_lang=target_lang,
        max_retries=max_retries,
    )
    handle.thread = threading.Thread(
        target=_worker,
        args=(handle.events, dict(state), output_root),
        daemon=True,
    )
    handle.thread.start()
    return handle
