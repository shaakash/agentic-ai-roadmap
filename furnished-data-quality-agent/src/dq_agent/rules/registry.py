"""Load the rule catalog (rules.yaml) into typed `Rule` objects."""

from __future__ import annotations

from pathlib import Path

import yaml

from dq_agent.config import get_settings
from dq_agent.schemas.rule import Rule, RuleCategory, RuleStatus


def load_rules(path: str | Path | None = None) -> list[Rule]:
    """Parse the YAML catalog into `Rule` objects (all rules, any status)."""
    rules_path = Path(path or get_settings().rules_path)
    raw = yaml.safe_load(rules_path.read_text())
    rules: list[Rule] = []
    for item in raw.get("rules", []):
        rules.append(
            Rule(
                rule_id=item["rule_id"],
                name=item["name"],
                category=RuleCategory(item["category"]),
                description=item.get("description", "").strip(),
                severity=item["severity"],
                status=RuleStatus(item.get("status", "active")),
                version=str(item.get("version", raw.get("version", "1.0.0"))),
                author=item.get("author", "system"),
                check_ref=item.get("check_ref"),
                generated_code=item.get("generated_code"),
            )
        )
    return rules


def active_rules(path: str | Path | None = None) -> list[Rule]:
    """Only the rules the engine should run."""
    return [r for r in load_rules(path) if r.status == RuleStatus.ACTIVE and r.enabled]
