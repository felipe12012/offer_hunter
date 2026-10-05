"""Two scans (HTTP tier and browser tier) change data/*.json at the same time: their states are merged, not rebased."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from price_history import MAX_SNAPSHOTS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import merge_state  # noqa: E402


def snap(date, price):
    return {"date": date, "price": price}


# ---- the rules ------------------------------------------------------------------------------------------

def test_seen_is_the_union_of_both_scans():
    assert merge_state.merge_seen(["a:1", "b:2"], ["b:2", "c:3"]) == ["a:1", "b:2", "c:3"]


def test_history_keeps_what_each_scan_learned():
    ours = {"falabella:1": [snap("2026-10-03", 100), snap("2026-10-04", 90)], "hites:9": [snap("2026-10-04", 5)]}
    theirs = {"falabella:1": [snap("2026-10-03", 100)], "skechers:7": [snap("2026-10-04", 70)]}
    merged = merge_state.merge_history(ours, theirs)
    assert set(merged) == {"falabella:1", "hites:9", "skechers:7"}
    assert merged["falabella:1"] == [snap("2026-10-03", 100), snap("2026-10-04", 90)]


def test_history_does_not_repeat_a_snapshot_both_scans_have():
    one = {"x:1": [snap("2026-10-03", 100), snap("2026-10-04", 80)]}
    assert merge_state.merge_history(one, one) == one


def test_history_is_ordered_by_date_and_capped():
    ours = {"x:1": [snap(f"2026-09-{d:02d}", 100 + d) for d in range(1, 30)]}
    theirs = {"x:1": [snap(f"2026-10-{d:02d}", 200 + d) for d in range(1, 10)]}
    merged = merge_state.merge_history(ours, theirs)["x:1"]
    assert len(merged) == MAX_SNAPSHOTS
    assert [s["date"] for s in merged] == sorted(s["date"] for s in merged)
    assert merged[-1] == snap("2026-10-09", 209)


def test_budget_of_the_same_day_takes_the_larger_counters():
    ours = {"date": "2026-10-05", "unverified": 10, "priority_unverified": 4}
    theirs = {"date": "2026-10-05", "unverified": 3, "priority_unverified": 160}
    assert merge_state.merge_budget(ours, theirs) == {"date": "2026-10-05", "unverified": 10, "priority_unverified": 160}


def test_budget_of_a_different_day_takes_the_later_day():
    old = {"date": "2026-10-04", "unverified": 999}
    new = {"date": "2026-10-05", "unverified": 1}
    assert merge_state.merge_budget(old, new) == new and merge_state.merge_budget(new, old) == new


def test_an_empty_side_changes_nothing():
    assert merge_state.merge_budget({}, {"date": "d", "unverified": 1}) == {"date": "d", "unverified": 1}
    assert merge_state.merge_budget({"date": "d"}, {}) == {"date": "d"}


def test_merge_files_rewrites_data_with_the_merge(tmp_path):
    ours, data = tmp_path / "ours", tmp_path / "data"
    ours.mkdir(), data.mkdir()
    (ours / "seen_items.json").write_text(json.dumps(["a:1"]))
    (data / "seen_items.json").write_text(json.dumps(["b:2"]))
    (ours / "price_history.json").write_text(json.dumps({"a:1": [snap("2026-10-05", 5)]}))
    (data / "price_history.json").write_text(json.dumps({"b:2": [snap("2026-10-05", 6)]}))
    (ours / "alert_budget.json").write_text(json.dumps({"date": "d", "unverified": 2}))
    (data / "alert_budget.json").write_text(json.dumps({"date": "d", "unverified": 7}))

    merge_state.merge_files(ours, data)

    assert json.loads((data / "seen_items.json").read_text()) == ["a:1", "b:2"]
    assert set(json.loads((data / "price_history.json").read_text())) == {"a:1", "b:2"}
    assert json.loads((data / "alert_budget.json").read_text())["unverified"] == 7


# ---- the workflows use it -----------------------------------------------------------------------------------

@pytest.mark.parametrize("workflow", ["fast.yml", "browser.yml"])
def test_both_tiers_commit_state_through_the_merging_script(workflow):
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    assert "bash scripts/commit_state.sh" in text
    assert "git pull --rebase" not in text  # the rebase that could not combine the two files
    yaml.safe_load(text)


# ---- the script, against a real repository ----------------------------------------------------------------

git = shutil.which("git")
bash = shutil.which("bash")


def run(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, **kw)


@pytest.mark.skipif(not (git and bash), reason="needs git and bash")
def test_the_script_pushes_a_state_that_conflicts_with_another_scans(tmp_path):
    origin = tmp_path / "origin.git"
    run([git, "init", "--bare", "-b", "main", str(origin)], tmp_path)

    def clone(name):
        path = tmp_path / name
        run([git, "clone", str(origin), str(path)], tmp_path)
        run([git, "config", "user.email", "t@example.com"], path)
        run([git, "config", "user.name", "t"], path)
        return path

    seed = clone("seed")
    (seed / "data").mkdir()
    (seed / "scripts").mkdir()
    for name in ("merge_state.py", "commit_state.sh"):
        shutil.copy(ROOT / "scripts" / name, seed / "scripts" / name)
    for name in ("price_history.py", "models.py"):
        shutil.copy(ROOT / name, seed / name)
    (seed / "data" / "seen_items.json").write_text(json.dumps(["base:1"]))
    (seed / "data" / "price_history.json").write_text(json.dumps({"base:1": [snap("2026-10-04", 10)]}, separators=(",", ":")))
    (seed / "data" / "alert_budget.json").write_text(json.dumps({"date": "2026-10-05", "unverified": 0}))
    run([git, "add", "-A"], seed)
    run([git, "commit", "-m", "seed"], seed)
    run([git, "push", "origin", "HEAD:main"], seed)

    http_tier, browser_tier = clone("http"), clone("browser")
    # both start from the same commit and change the same single-line file
    for repo, store, price in ((http_tier, "falabella:1", 111), (browser_tier, "skechers:2", 222)):
        history = json.loads((repo / "data" / "price_history.json").read_text())
        history[store] = [snap("2026-10-05", price)]
        (repo / "data" / "price_history.json").write_text(json.dumps(history, separators=(",", ":"), sort_keys=True))
        seen = json.loads((repo / "data" / "seen_items.json").read_text()) + [f"{store}:{price}"]
        (repo / "data" / "seen_items.json").write_text(json.dumps(sorted(seen), indent=2))

    env_python = {"PATH": str(Path(sys.executable).parent) + ":" + __import__("os").environ["PATH"]}
    full_env = {**__import__("os").environ, **env_python}
    run([bash, "scripts/commit_state.sh"], http_tier, env=full_env)      # pushes first
    run([bash, "scripts/commit_state.sh"], browser_tier, env=full_env)   # would conflict with a plain rebase

    check = clone("check")
    history = json.loads((check / "data" / "price_history.json").read_text())
    seen = json.loads((check / "data" / "seen_items.json").read_text())
    assert set(history) == {"base:1", "falabella:1", "skechers:2"}
    assert set(seen) == {"base:1", "falabella:1:111", "skechers:2:222"}
