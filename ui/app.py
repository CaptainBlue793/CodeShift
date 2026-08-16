"""CodeShift live dashboard.

Run with:  streamlit run ui/app.py

Shows a migration as it happens. The interesting thing to watch is the
translate<->verify loop: a module bounces between the translator and the type
oracle, and its error count either moves or doesn't. That trace ("1 -> 0 -> 1")
is the project's core behavior and is otherwise only visible by grepping logs.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# `streamlit run ui/app.py` puts ui/ on sys.path, not the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from codeshift.config import settings  # noqa: E402
from codeshift.equivalence.diff import render_call  # noqa: E402
from codeshift.sandbox.policy import describe  # noqa: E402
from codeshift.verification import LABEL, is_trustworthy, unverified_names, verdict  # noqa: E402
from ui.diffview import STYLE, align, changed_rows, to_html, whitespace_only  # noqa: E402
from ui.history import record_history, trace, trend  # noqa: E402
from ui.runner import RunHandle, start_run  # noqa: E402

REFRESH_SECONDS = 0.5

# Before the differential run there is nothing to judge, so rows show where the
# module is in the pipeline...
STATUS_ICON = {
    "pending": "○",
    "translated": "⟳",
    "verified": "✅",
    "idiomatic": "✅",
    "failed": "❌",
}

# ...and after it they show what the run established. A module that was never
# executed must not wear the same ✅ as one that was.
VERDICT_ICON = {
    "verified": "✅",
    "partial": "⚠",
    "unverified": "⚠",
    "drift": "❌",
    "empty": "○",
}

_JUDGED = ("verified", "idiomatic", "failed")


def _icon(unit: dict) -> str:
    """Pipeline icon until the differential run has had its say, then the verdict."""
    status = unit.get("status", "pending")
    if status in _JUDGED:
        return VERDICT_ICON.get(verdict(unit), "○")
    return STATUS_ICON.get(status, "○")


# --------------------------------------------------------------- state plumbing

def _init_state() -> None:
    st.session_state.setdefault("handle", None)
    st.session_state.setdefault("snapshot", {})
    st.session_state.setdefault("history", {})
    st.session_state.setdefault("started_at", None)


def _drain(handle: RunHandle) -> None:
    for snapshot in handle.drain():
        st.session_state.snapshot = snapshot
        record_history(st.session_state.history, snapshot)


# ------------------------------------------------------------------- rendering

def _render_modules(snapshot: dict, history: dict) -> None:
    order = snapshot.get("translation_order") or []
    files = snapshot.get("files") or {}
    current = snapshot.get("current")

    if not order:
        st.info("Waiting for the dependency mapper…")
        return

    widths = [2.2, 1.4, 1, 1.6, 1.6]
    header = st.columns(widths)
    for col, label in zip(header, ("Module", "Verified", "Attempts", "Type errors", "Divergences")):
        col.caption(label)

    for module in order:
        unit = files.get(module) or {}
        per_module = history.get(module, {})
        status = unit.get("status", "pending")
        is_current = module == current

        cols = st.columns(widths)
        name = f"**{module}**" if is_current else module
        cols[0].markdown(f"{_icon(unit)} {name}")
        # Pre-verdict the pipeline status is the only thing to say; after it,
        # the verdict is, and it is not interchangeable with the status.
        judged = status in _JUDGED
        cols[1].markdown(f"`{LABEL[verdict(unit)] if judged else status}`")
        cols[2].markdown(str(unit.get("attempts", 0)))
        cols[3].markdown(trace(per_module, "type_errors") + trend(per_module, "type_errors"))
        cols[4].markdown(trace(per_module, "divergences") + trend(per_module, "divergences"))

        skipped = unverified_names(unit)
        if skipped:
            cols[0].caption(f"not checked: {', '.join(skipped)}")
        if unit.get("rejected"):
            cols[0].caption(f"⚠ output rejected: {unit['rejected']}")


def _render_summary(snapshot: dict, handle: RunHandle | None) -> None:
    files = snapshot.get("files") or {}
    order = snapshot.get("translation_order") or []
    units: list[dict] = [files.get(m) or {} for m in order]

    verified = len([u for u in units if u.get("attempts") and is_trustworthy(u)])
    # Anything that reached the differential run without earning a clean verdict.
    unverified = len([
        u for u in units
        if u.get("status") in _JUDGED and verdict(u) in ("partial", "unverified")
    ])
    done = len([u for u in units if u.get("status") in ("idiomatic", "failed")])

    cols = st.columns(5)
    cols[0].metric("Modules", len(order))
    cols[1].metric("Verified", verified)
    cols[2].metric("Not verified", unverified)
    cols[3].metric("Current", snapshot.get("current") or "—")

    started = st.session_state.started_at
    elapsed = f"{int(time.time() - started)}s" if started else "—"
    cols[4].metric("Elapsed", elapsed)

    # Progress tracks modules finished, not modules that came out clean — an
    # unverifiable module still advances the run.
    if handle and handle.running:
        st.progress(min(done / len(order), 1.0) if order else 0.0, text="Running…")

    # The "Verified" metric above means something different depending on where
    # the code ran, so the two are shown together. The report carries the same
    # line; see codeshift.verification on why these must not drift apart.
    isolation = snapshot.get("isolation")
    if isolation == "host":
        st.warning(describe("host"), icon="⚠")
    elif isolation == "unavailable":
        st.error(describe("unavailable"), icon="🚫")
    elif isolation == "docker":
        st.caption(f"🔒 {describe('docker')}")


def _render_code(snapshot: dict) -> None:
    files = snapshot.get("files") or {}
    order = [m for m in (snapshot.get("translation_order") or []) if m in files]
    if not order:
        st.info("No modules yet.")
        return

    module = st.selectbox("Module", order)
    unit = files[module]
    shipped = unit.get("translated_code")
    # `first_code` is absent for modules translated before it was recorded, and
    # for anything not yet emitted; fall back to comparing the shipped code with
    # itself, which correctly renders as "no changes".
    first = unit.get("first_code") or shipped

    src_col, first_col, final_col = st.columns(3)
    with src_col:
        st.caption(f"source · {unit.get('path', '')}")
        st.code(unit.get("source_code") or "", language=snapshot.get("source_lang", "python"))

    if not shipped:
        with first_col:
            st.info("Not translated yet.")
        return

    rows = align(first, shipped)
    attempts = unit.get("attempts", 0)
    st.markdown(STYLE, unsafe_allow_html=True)
    with first_col:
        st.caption(f"first attempt · {'1 attempt' if attempts <= 1 else f'of {attempts}'}")
        st.markdown(to_html(rows, "left"), unsafe_allow_html=True)
    with final_col:
        st.caption(f"shipped · {unit.get('target_path') or 'not emitted'}")
        st.markdown(to_html(rows, "right"), unsafe_allow_html=True)

    # Say what the highlighting means, so an unchanged module is not read as a
    # broken comparison — and so formatting churn is never mistaken for a fix.
    changed = changed_rows(rows)
    if not changed:
        st.caption("✓ Shipped exactly what the model produced first — no retries, no edits.")
    elif whitespace_only(first, shipped):
        st.caption(f"✓ No retries — the {changed} highlighted line(s) are formatting only.")
    else:
        st.caption(
            f"{changed} line(s) changed between the first attempt and what shipped "
            "— red is what the model wrote first, green is what the retry loop settled on."
        )

    if unit.get("type_errors"):
        st.error("Type errors")
        for err in unit["type_errors"]:
            st.markdown(f"- `line {err.get('line')}` **{err.get('code')}** — {err.get('message')}")

    skipped = unverified_names(unit)
    if skipped:
        st.warning(
            f"Not differential-tested: {', '.join(skipped)} — translated, but no "
            "behavioral evidence."
        )

    if unit.get("divergences"):
        st.warning(f"{len(unit['divergences'])} divergence(s) — showing first 10")
        for d in unit["divergences"][:10]:
            st.markdown(
                f"- `{render_call(d, lambda a: repr(a or []))}` "
                f"**{d.get('category')}** — {d.get('detail')}"
            )


# ------------------------------------------------------------------------ page

def main() -> None:
    st.set_page_config(page_title="CodeShift", page_icon="🔀", layout="wide")
    _init_state()

    handle: RunHandle | None = st.session_state.handle
    if handle:
        _drain(handle)

    st.title("🔀 CodeShift")
    st.caption(
        f"model `{settings.model}` · tsc oracle "
        f"{'on' if settings.use_tsc_oracle else 'off'} · mypy oracle "
        f"{'on' if settings.use_mypy_oracle else 'off'} · max retries {settings.max_retries}"
    )

    with st.sidebar:
        st.subheader("Run")
        source = st.text_input("Source codebase", "./tests/fixtures/sample_app")
        output = st.text_input("Output directory", "./data/output")
        col_a, col_b = st.columns(2)
        source_lang = col_a.text_input("From", "python")
        target_lang = col_b.text_input("To", "typescript")
        retries = st.number_input(
            "Max retries per module", min_value=1, max_value=10, value=settings.max_retries
        )

        running = bool(handle and handle.running)
        if st.button("▶ Run migration", disabled=running, type="primary", use_container_width=True):
            if not Path(source).exists():
                st.error(f"Source path not found: {source}")
            else:
                st.session_state.history = {}
                st.session_state.snapshot = {}
                st.session_state.started_at = time.time()
                st.session_state.handle = start_run(
                    source_root=source,
                    output_root=output,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    max_retries=int(retries),
                )
                st.rerun()

        if running:
            st.info("Run in progress. Leaving this page cancels nothing — the thread is a daemon "
                    "and dies with the server.")

    snapshot = st.session_state.snapshot

    if handle and handle.error:
        st.error(f"Run failed: {handle.error}")
    elif handle and handle.finished and not handle.running:
        st.success("Run complete.")

    _render_summary(snapshot, handle)
    st.divider()

    modules_tab, report_tab, code_tab = st.tabs(["Modules", "Report", "Code"])
    with modules_tab:
        _render_modules(snapshot, st.session_state.history)
    with report_tab:
        report = snapshot.get("report")
        if report:
            st.markdown(report)
        else:
            st.info("The report is written by the reviewer agent at the end of a run.")
    with code_tab:
        _render_code(snapshot)

    # Poll for new snapshots while the worker is alive.
    if handle and handle.running:
        time.sleep(REFRESH_SECONDS)
        st.rerun()


main()
