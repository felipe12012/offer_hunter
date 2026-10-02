# tests/test_fast_workflow_yaml.py
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "fast.yml"


def test_workflow_yaml_is_valid_and_scheduled_every_15_minutes():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    # PyYAML parses the bare `on:` key as the boolean True (YAML 1.1 quirk).
    triggers = parsed[True]
    assert triggers["schedule"][0]["cron"] == "*/15 * * * *"
    assert "workflow_dispatch" in triggers
    assert parsed["permissions"]["contents"] == "write"


def test_workflow_uses_required_secrets():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    for secret_name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert f"secrets.{secret_name}" in content


def test_workflow_installs_playwright_chromium():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "playwright install" in content
    assert "chromium" in content


def test_workflow_commits_data_files():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "data/seen_items.json" in content
    assert "data/price_history.json" in content


def test_workflow_notifies_telegram_on_failure():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    steps = parsed["jobs"]["run-pipeline"]["steps"]
    failure_steps = [step for step in steps if step.get("if") == "failure()"]

    assert len(failure_steps) == 1
    assert "sendMessage" in failure_steps[0]["run"]
    assert steps[-1] is failure_steps[0]
