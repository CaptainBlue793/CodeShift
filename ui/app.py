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
from ui import theme  # noqa: E402
from ui.diffview import (  # noqa: E402
    STYLE, align, changed_rows, pane, plain_html, to_html, whitespace_only,
)
from ui.history import counts, record_history  # noqa: E402
from ui.runner import RunHandle, start_run  # noqa: E402

REFRESH_SECONDS = 0.5
LOGO = theme.LOGO

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

#: Sidebar presets. Typing a fixture path by hand is the most common way to
#: start a run that fails before the mapper even sees it.
CUSTOM = "Custom path"
PRESETS: dict[str, str] = {
    "sample_app": "4 modules, plain functions",
    "class_app": "classes, methods, object state",
    "cyclic_app": "circular imports",
    CUSTOM: "point it anywhere",
}
FIXTURE_PATHS = {name: f"./tests/fixtures/{name}" for name in PRESETS if name != CUSTOM}


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

    # A cycle changes what this table means: one module in it was translated
    # before its dependencies existed. Same reasoning as the report's notice.
    for cycle in snapshot.get("cycles") or []:
        st.warning(
            f"Circular imports: {' → '.join(cycle)} → back to {cycle[0]}. Broken at "
            f"**{cycle[0]}**, which was translated before its own dependencies existed.",
            icon="🔁",
        )

    rows = [theme.HEADER_ROW]
    for module in order:
        unit = files.get(module) or {}
        per_module = history.get(module, {})
        status = unit.get("status", "pending")
        judged = status in _JUDGED

        notes = []
        skipped = unverified_names(unit)
        if skipped:
            notes.append(f"not checked: {', '.join(skipped)}")
        if unit.get("rejected"):
            notes.append(f"⚠ output rejected: {unit['rejected']}")

        # Pre-verdict the pipeline status is the only thing to say; after it,
        # the verdict is, and it is not interchangeable with the status.
        rows.append(
            theme.module_row(
                module=module,
                icon=_icon(unit),
                verdict_label=LABEL[verdict(unit)] if judged else status,
                verdict_slug=verdict(unit) if judged else "empty",
                attempts=unit.get("attempts", 0),
                type_errors=counts(per_module, "type_errors"),
                divergences=counts(per_module, "divergences"),
                notes=notes,
                is_current=module == current,
            )
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


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

    drifted = len([u for u in units if u.get("status") in _JUDGED and verdict(u) == "drift"])
    started = st.session_state.started_at
    elapsed = f"{int(time.time() - started)}s" if started else "—"

    st.markdown(
        theme.tiles([
            ("Modules", len(order) or "—", None),
            ("Verified", verified, theme.CYAN if verified else None),
            ("Drift", drifted, theme.LAVENDER if drifted else None),
            ("Not verified", unverified, theme.AMBER if unverified else None),
            ("Current", snapshot.get("current") or "—", None),
            ("Elapsed", elapsed, None),
        ]),
        unsafe_allow_html=True,
    )

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
    on_disk = unit.get("translated_code")
    # What the model emitted, before the formatter rewrote the file. Absent for
    # modules that have not reached the idiom step, and for snapshots predating
    # the field — fall back to the final code, which renders as "no changes".
    emitted = unit.get("pre_format_code") or on_disk

    src_lang = snapshot.get("source_lang", "python")
    tgt_lang = snapshot.get("target_lang", "typescript")

    st.markdown(STYLE, unsafe_allow_html=True)
    src_col, model_col, disk_col = st.columns(3)
    with src_col:
        st.markdown(
            pane(
                "① source",
                unit.get("path", ""),
                plain_html(unit.get("source_code") or "", src_lang),
                theme.LAVENDER,
            ),
            unsafe_allow_html=True,
        )

    if not on_disk:
        with model_col:
            st.info("Not translated yet.")
        return

    rows = align(emitted, on_disk)
    with model_col:
        st.markdown(
            pane(
                "② as the model wrote it",
                "",
                to_html(rows, "left", tgt_lang),
                theme.CYAN,
            ),
            unsafe_allow_html=True,
        )
    with disk_col:
        st.markdown(
            pane(
                "③ on disk",
                unit.get("target_path") or "not emitted",
                to_html(rows, "right", tgt_lang),
                theme.CYAN,
            ),
            unsafe_allow_html=True,
        )

    # Say what the highlighting means, so an unchanged module is not read as a
    # broken comparison.
    changed = changed_rows(rows)
    if not changed:
        st.caption("✓ The file on disk is byte-for-byte what the model emitted.")
    elif whitespace_only(emitted, on_disk):
        st.caption(
            f"✓ The {changed} highlighted line(s) are the formatter's work only — "
            "whitespace, no code changed."
        )
    else:
        st.caption(
            f"{changed} line(s) differ between ② and ③ — red is what the model emitted, "
            "green is what ended up on disk."
        )

    # The retry loop's effect is no longer a column, so it is stated instead —
    # it is the project's core diagnostic and should not vanish from this tab.
    attempts = unit.get("attempts", 0)
    first = unit.get("first_code")
    if attempts > 1 and first:
        retry_changed = changed_rows(align(first, on_disk))
        st.caption(
            f"↻ Shipped after {attempts} attempts — {retry_changed} line(s) differ from "
            "the model's first attempt."
        )
    elif attempts == 1:
        st.caption("↻ First attempt shipped — no retries.")

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
    # The mark doubles as the favicon, so a pinned tab is identifiable.
    icon = str(LOGO) if LOGO.exists() else "🔀"
    st.set_page_config(page_title="CodeShift", page_icon=icon, layout="wide")
    if LOGO.exists():
        st.logo(str(LOGO))          # app chrome, above the sidebar
    _init_state()

    handle: RunHandle | None = st.session_state.handle
    if handle:
        _drain(handle)

    st.markdown(theme.CSS, unsafe_allow_html=True)

    st.markdown(theme.header_html(), unsafe_allow_html=True)
    st.markdown(
        '<div class="cs-sub">Translate a codebase, then prove the behavior survived '
        f"&nbsp;·&nbsp; model <code>{settings.model}</code> &nbsp;·&nbsp; tsc oracle "
        f"{'on' if settings.use_tsc_oracle else 'off'} &nbsp;·&nbsp; mypy oracle "
        f"{'on' if settings.use_mypy_oracle else 'off'} &nbsp;·&nbsp; "
        f"max retries {settings.max_retries}</div>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.subheader("Run")
        # `st.radio` is typed as optional (it returns None only when the option
        # list is empty), so pin it back to a real key for the lookups below.
        preset = st.radio("Source", list(PRESETS), captions=list(PRESETS.values())) or "sample_app"
        if preset == CUSTOM:
            source = st.text_input("Source codebase", "./tests/fixtures/sample_app")
        else:
            source = FIXTURE_PATHS[preset]
            st.caption(f"`{source}`")
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
