"""Validators specific to accounts in the chart."""
from __future__ import annotations

from core.codes import UNKNOWN, class_of, is_valid_code
from core.errors import format_error
from validation.rules import first_problem, max_length, require_nonempty

MAX_ACCOUNT_NAME = 60


def validate_code(code: str) -> str:
    if not is_valid_code(code):
        return format_error("E201", "account code " + code + " is malformed")
    if class_of(code) == UNKNOWN:
        return format_error("E202", "account code " + code + " has no known class")
    return ""


def validate_name(name: str) -> str:
    return first_problem(
        require_nonempty(name, "account name"),
        max_length(name, "account name", MAX_ACCOUNT_NAME),
    )


def validate_account(code: str, name: str) -> str:
    return first_problem(validate_code(code), validate_name(name))


def can_post_to(code: str, is_group: bool) -> bool:
    """Group accounts are headings; postings belong on their leaves."""
    if is_group:
        return False
    return validate_code(code) == ""


def posting_problem(code: str, is_group: bool) -> str:
    problem = validate_code(code)
    if problem:
        return problem
    if is_group:
        return format_error("E203", "account " + code + " is a group heading")
    return ""
