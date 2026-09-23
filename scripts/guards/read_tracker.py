from __future__ import annotations

from guards import GuardOutcome
from lib.rules import required_set_from_rules


def handle(
    event,
    *,
    rules,
    state_root,
    adapter,
) -> GuardOutcome:
    from lib.state import is_rule_doc_path, write_read_state

    required_set = required_set_from_rules(rules)
    if is_rule_doc_path(event.path, required_set):
        if adapter.is_full_read(event.tool_input):
            write_read_state(event.session_id, event.path, state_root)

    return GuardOutcome(0, adapter.render_allow())
