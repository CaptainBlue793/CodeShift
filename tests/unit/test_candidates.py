"""Best-attempt tracking — the guard against a run that improves then regresses.

Modelled on the observed `1 -> 0 -> 1` type-error sequence, where the final
attempt shipped despite attempt 2 being clean.
"""
from codeshift.candidates import adopt_best, record_candidate, score


def _unit(code="x", type_errors=None, divergences=None, attempts=1, best=None):
    return {
        "translated_code": code,
        "target_path": "models.ts",
        "type_errors": list(type_errors or []),
        "divergences": list(divergences or []),
        "attempts": attempts,
        "best": best,
    }


def _div(function="f", detail="mismatch"):
    return {"function": function, "args": [1], "category": "value_mismatch", "detail": detail}


def test_score_counts_errors_and_distinct_failure_modes():
    unit = _unit(type_errors=[{"code": "TS1"}], divergences=[_div(), _div(), _div()])
    assert score(unit) == (1, 1)          # 3 records, one failure mode


def test_type_errors_outrank_divergences():
    compiles_but_wrong = _unit(divergences=[_div(detail=f"d{i}") for i in range(9)])
    does_not_compile = _unit(type_errors=[{"code": "TS1"}])
    assert score(compiles_but_wrong) < score(does_not_compile)


def test_record_candidate_keeps_the_better_attempt():
    unit = _unit(code="attempt-1", type_errors=[{"code": "TS1"}], attempts=1)
    record_candidate(unit)

    unit.update(translated_code="attempt-2", type_errors=[], attempts=2)
    record_candidate(unit)

    # A regression on attempt 3 must not displace the clean attempt 2.
    unit.update(translated_code="attempt-3", type_errors=[{"code": "TS1"}], attempts=3)
    record_candidate(unit)

    assert unit["best"]["code"] == "attempt-2"
    assert unit["best"]["attempt"] == 2


def test_record_candidate_ignores_units_without_code():
    unit = _unit(code=None)
    assert record_candidate(unit) is None
    assert unit["best"] is None


def test_adopt_best_restores_the_winner_and_its_diagnostics():
    unit = _unit(code="attempt-1", attempts=1)
    record_candidate(unit)
    unit.update(translated_code="attempt-2", type_errors=[{"code": "TS1"}], attempts=2)

    adopted = adopt_best(unit)

    assert adopted is not None
    assert unit["translated_code"] == "attempt-1"
    assert unit["type_errors"] == []       # diagnostics travel with the code


def test_adopt_best_is_a_noop_when_last_attempt_is_the_best():
    unit = _unit(code="only", attempts=1)
    record_candidate(unit)
    assert adopt_best(unit) is None
