"""YAML schema validation for stages.yaml configuration.

Validates the structure of stages.yaml at load time to catch common
configuration errors early. Uses a lightweight embedded validator
(no external dependency beyond stdlib).
"""

from __future__ import annotations

from typing import List, Tuple


def validate_stages_config(config: dict) -> Tuple[bool, List[str]]:
    """Validate the structure of a loaded stages YAML config.
    Returns (valid, errors).
    """
    errors = []

    if not isinstance(config, dict):
        return False, ["Config must be a dict"]

    stages = config.get("stages", [])
    transitions = config.get("transitions", [])
    groups = config.get("groups", [])

    if not isinstance(stages, list):
        errors.append("'stages' must be a list")
    else:
        stage_names = set()
        for i, stage in enumerate(stages):
            if not isinstance(stage, dict):
                errors.append(f"stages[{i}]: must be a dict")
                continue
            name = stage.get("name")
            if not name or not isinstance(name, str):
                errors.append(f"stages[{i}]: missing or invalid 'name'")
            elif name in stage_names:
                errors.append(f"stages[{i}]: duplicate stage name '{name}'")
            else:
                stage_names.add(name)
            tools = stage.get("tools", [])
            if not isinstance(tools, list):
                errors.append(f"stages[{i}] ('{name}'): 'tools' must be a list")

    if not isinstance(transitions, list):
        errors.append("'transitions' must be a list")
    else:
        seen_transitions = set()
        for i, trans in enumerate(transitions):
            if not isinstance(trans, dict):
                errors.append(f"transitions[{i}]: must be a dict")
                continue
            from_s = trans.get("from")
            to_s = trans.get("to")
            if not from_s or not isinstance(from_s, str):
                errors.append(f"transitions[{i}]: missing or invalid 'from'")
            if not to_s or not isinstance(to_s, str):
                errors.append(f"transitions[{i}]: missing or invalid 'to'")
            key = (from_s, to_s)
            if key in seen_transitions:
                errors.append(f"transitions[{i}]: duplicate transition {from_s} -> {to_s}")
            seen_transitions.add(key)
            conditions = trans.get("conditions", [])
            if not isinstance(conditions, list):
                errors.append(f"transitions[{i}]: 'conditions' must be a list")
            on_fail = trans.get("on_fail")
            if on_fail is not None and not isinstance(on_fail, str):
                errors.append(f"transitions[{i}]: 'on_fail' must be a string")

    if not isinstance(groups, list):
        errors.append("'groups' must be a list")

    return len(errors) == 0, errors
