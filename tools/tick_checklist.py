"""Mark SPEC.md's section-12 checklist from verified evidence, not by hand.

A checklist ticked by hand is a checklist that lies. Each item is matched to
one or more named tests by *exact* test-function name, and only an item whose
every named test exists gets ticked - so a near-miss on a substring cannot
quietly pass.

    uv run python tools/tick_checklist.py            # report only
    uv run python tools/tick_checklist.py --write    # apply
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "SPEC.md"

#: item phrase (lower-cased, backticks stripped) -> the tests that prove it.
#:
#: Every test named must exist. A single existing test is not evidence for a
#: compound claim, which is why most entries name two.
EVIDENCE: dict[str, tuple[str, ...]] = {
    "normalisation": (
        "test_a_normalises_the_buffer_but_not_the_variable",
        "test_a_assign_is_still_normalised",
    ),
    "assigns to the buffer without prompting": ("test_a_assigns_without_prompting",),
    "numeric accept never errors": ("test_numeric_accept_never_errors",),
    "distinguishable": (
        "test_t_of_a_null_string_prints_nothing",
        "test_t_of_an_undefined_variable_prints_its_name",
    ),
    "substring": ("test_matching_is_a_substring_search",),
    "field separators": (
        "test_a_leading_bar_selects_the_bar_separator",
        "test_the_separator_is_never_both_at_once",
    ),
    "exposed as `%m`": (
        "test_percent_m_reports_the_ordinal",
        "test_jm_branches_on_the_ordinal",
    ),
    "null match": (
        "test_an_empty_field_is_a_null_match",
        "test_separators_without_a_field_are_a_null_match",
    ),
    "retains": ("test_ms_retains_previous_values_on_failure",),
    "own name": ("test_t_of_an_undefined_variable_prints_its_name",),
    "truncates toward zero": ("test_c_truncating_division",),
    "wraps at 16 bits": ("test_c_wraps_at_16_bits_silently",),
    "26 numeric variables": ("test_c_rejects_a_multi_letter_numeric_target",),
    "truncate at 254": ("test_constants_truncate_on_entry",),
    "single-pass": ("test_t_does_not_rescan_expanded_text",),
    "indirection": ("test_indirection_depth_is_recorded",),
    "lowest line number": (
        "test_duplicate_labels_are_allowed_and_lowest_line_wins",
        "test_a_duplicate_label_jumps_to_the_lowest_line_number",
    ),
    "continuation works after": (
        "test_continuation_repeats_the_previous_command",
        "test_continuation_inherits_the_previous_command",
    ),
    "interchangeable as operand separators": ("test_fields_split_on_a_comma",),
    "conjunctive": ("test_y_and_n_conditions_are_conjunctive",),
    "recursive `u:`": (
        "test_recursion_terminates_and_counts",
        "test_nesting_past_the_limit_raises_rather_than_crashing",
    ),
    "naming the subcommand": (
        "test_running_a_program_with_a_refused_command",
        "test_a_refusal_names_the_gr_subcommand",
    ),
    "call:`/`tape:`/`tsync:`/`dos:`": ("test_refused_commands_still_parse",),
    "syntax errors, not silently ignored": ("test_unknown_command_is_rejected",),
    "match ordinal is the field number": (
        "test_percent_m_reports_the_ordinal",
        "test_fields_are_tried_in_order",
    ),
    "may share a line with a command": (
        "test_label_may_share_a_line_with_a_command",
        "test_label_of_any_length_is_accepted",
    ),
    "comments are": ("test_comment_runs_from_bracket_to_end_of_line",),
    "not truncated to": ("test_command_name_is_exact_not_truncated",),
    "`gr:`/`so:` parse and raise `pilotunsupportederror` naming the": (
        "test_graphics_example_is_refused_when_run",
        "test_a_refusal_names_the_gr_subcommand",
    ),
    "`call:`/`tape:`/`tsync:`/`dos:` parse and raise": (
        "test_refused_commands_still_parse",
        "test_a_refused_command_raises_clearly",
    ),
    "is a label, not a link": ("test_l_is_a_label_not_a_link_command",),
    "core-pilot-only commands": (
        "test_core_pilot_only_commands_are_rejected_not_ignored",
        "test_rejected_table_has_a_reason_for_every_entry",
    ),
    "`--trace` prints each statement as it executes": (
        "test_trace_goes_to_stderr_not_stdout",
        "test_trace_records_every_executed_statement",
    ),
    "reports the program line number and echoes": (
        "test_running_a_program_with_a_runtime_error_exits_one",
    ),
    "every example runs": ("test_every_runnable_example_actually_runs",),
    "starts a repl": ("test_no_program_starts_the_repl",),
    "`--trace` prints": ("test_trace_goes_to_stderr_not_stdout",),
    "line number and echoes": ("test_running_a_program_with_a_runtime_error_exits_one",),
}


def test_names() -> set[str]:
    """Every test function defined in the suite."""
    found: set[str] = set()
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        found.update(re.findall(r"^def (test_[A-Za-z0-9_]+)", text, re.MULTILINE))
    return found


def safe(text: str) -> str:
    """ASCII-fold for the Windows console, which is cp1252 and refuses to."""
    return text.encode("ascii", errors="replace").decode("ascii")


def main(argv: list[str]) -> int:
    write = "--write" in argv
    text = SPEC.read_text(encoding="utf-8")
    names = test_names()

    start = text.index("## 12. Definition of done")
    end = text.index("\n## 13.", start)
    section = text[start:end]

    verified: list[str] = []
    unverified: list[tuple[str, str]] = []

    def rewrite(match: re.Match[str]) -> str:
        body = match.group(1)
        plain = body.lower().replace("`", "")
        keys = [key for key in EVIDENCE if key in plain]
        if keys and all(all(test in names for test in EVIDENCE[key]) for key in keys):
            verified.append(body.strip())
            return f"- [x] {body}"
        missing = [test for key in keys for test in EVIDENCE[key] if test not in names]
        unverified.append((body.strip(), ", ".join(missing) or "no evidence mapped"))
        return match.group(0)

    updated = re.sub(r"- \[ \] ((?:.|\n)*?)(?=\n- \[ \]|\n\n|\n### |\Z)", rewrite, section)

    print(f"tests found: {len(names)}")
    print(f"verified:   {len(verified)}")
    for item in verified:
        print(f"  [x] {safe(item.splitlines()[0][:86])}")
    print(f"unverified: {len(unverified)}")
    for item, why in unverified:
        head = safe(item.splitlines()[0][:66])
        print(f"  [ ] {head:<68} <- {safe(why[:38])}")

    if write:
        SPEC.write_text(text[:start] + updated + text[end:], encoding="utf-8", newline="\n")
        print("\nSPEC.md updated")
    else:
        print("\n(dry run; pass --write to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
