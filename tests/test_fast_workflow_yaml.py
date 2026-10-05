# tests/test_fast_workflow_yaml.py
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "fast.yml"
BROWSER_WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "browser.yml"


def test_workflow_yaml_is_valid_and_scheduled_every_15_minutes_off_peak():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    # PyYAML parses the bare `on:` key as the boolean True (YAML 1.1 quirk).
    triggers = parsed[True]
    assert triggers["schedule"][0]["cron"] == "7,22,37,52 * * * *"
    assert "workflow_dispatch" in triggers
    assert parsed["permissions"]["contents"] == "write"


def test_workflow_uses_required_secrets():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    for secret_name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert f"secrets.{secret_name}" in content


def test_fast_tier_runs_http_only_and_browser_tier_installs_chromium():
    fast = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "SCAN_TIER: http" in fast
    assert "playwright install" not in fast          # browsers moved out of the fast tier

    browser = BROWSER_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "SCAN_TIER: browser" in browser
    assert "playwright install" in browser
    assert "chromium" in browser


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


def test_workflow_serialises_runs_so_data_commits_do_not_collide():
    # Two overlapping runs both commit data/ and the second push is rejected,
    # failing a scan that actually succeeded. A concurrency group prevents it.
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    assert parsed["concurrency"]["group"]


def test_workflow_rebases_before_pushing_data_files():
    # Guards against the push being rejected when another run or a manual push
    # landed while this scan was in flight.
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "git pull --rebase" in content


def test_workflow_dispatch_offers_a_selftest_input():
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    inputs = parsed[True]["workflow_dispatch"]["inputs"]
    assert inputs["selftest"]["type"] == "boolean"
    run_step = next(step for step in parsed["jobs"]["run-pipeline"]["steps"] if step.get("name") == "Run pipeline")
    assert "--selftest" in run_step["run"]


def test_checkout_uses_branch_tip_so_queued_runs_never_start_from_stale_data():
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    checkout = next(
        step for step in parsed["jobs"]["run-pipeline"]["steps"] if str(step.get("uses", "")).startswith("actions/checkout")
    )
    assert "default_branch" in checkout["with"]["ref"]


def test_workflow_can_import_json_state_into_supabase_and_passes_the_secrets_to_the_scan():
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert parsed[True]["workflow_dispatch"]["inputs"]["migrate"]["type"] == "boolean"
    steps = parsed["jobs"]["run-pipeline"]["steps"]
    migrate = next(step for step in steps if "migrate_to_supabase" in (step.get("run") or ""))
    run = next(step for step in steps if step.get("name") == "Run pipeline")
    assert steps.index(migrate) < steps.index(run)          # import first, so the scan diffs against it
    for step in (migrate, run):
        assert "secrets.SUPABASE_URL" in step["env"]["SUPABASE_URL"]
        assert "secrets.SUPABASE_SERVICE_KEY" in step["env"]["SUPABASE_SERVICE_KEY"]
