import json
import logging
import subprocess

import pandas as pd

from market_bot.change_tracking import log_startup_identity
from market_bot.trade_journal import DecisionJournal, TradeJournal
import hash_report


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_startup_logs_identity_and_warns_for_unknown_config_hash(tmp_path, caplog):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "tracked.txt").write_text("committed\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "initial")
    expected_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "untracked.txt").write_text("uncommitted\n", encoding="utf-8")
    changelog = tmp_path / "config_changelog.md"
    changelog.write_text("known hash: abc123\n", encoding="utf-8")

    with caplog.at_level(logging.INFO):
        identity = log_startup_identity(
            "abc123", changelog_path=changelog, repo_path=repo
        )

    assert identity.sha == expected_sha
    assert identity.dirty is True
    assert f"config_hash=abc123 git_sha={expected_sha} git_dirty=True" in caplog.text
    assert "is not listed" not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        log_startup_identity(
            "unknown-hash", changelog_path=changelog, repo_path=repo
        )
    assert "is not listed" in caplog.text


def test_trade_and_decision_journals_stamp_git_identity(tmp_path):
    identity = {"config_hash": "config", "git_sha": "commit", "git_dirty": True}
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decisions.jsonl"
    paper_data_dir = tmp_path / "paper"
    trade_journal = TradeJournal(
        str(trades_path),
        str(paper_data_dir),
        config_hash=identity["config_hash"],
        git_sha=identity["git_sha"],
        git_dirty=identity["git_dirty"],
    )
    decision_journal = DecisionJournal(
        str(decisions_path),
        str(paper_data_dir),
        config_hash=identity["config_hash"],
        git_sha=identity["git_sha"],
        git_dirty=identity["git_dirty"],
    )

    trade_journal.log_trade({"ticker": "NIFTY", "action": "BUY"})
    decision_journal.log_decision({"ticker": "NIFTY", "signal": "BUY"})

    trade = json.loads(trades_path.read_text(encoding="utf-8"))
    decision = json.loads(decisions_path.read_text(encoding="utf-8"))
    for record in (trade, decision):
        assert record["config_hash"] == "config"
        assert record["git_sha"] == "commit"
        assert record["git_dirty"] is True
    parquet_trade = next(paper_data_dir.glob("**/trades.parquet"))
    parquet_decision = next(paper_data_dir.glob("**/decisions.parquet"))
    for path in (parquet_trade, parquet_decision):
        record = pd.read_parquet(path).iloc[0]
        assert record["config_hash"] == "config"
        assert record["git_sha"] == "commit"
        assert record["git_dirty"] == "True"


def test_hash_report_counts_date_pairs_and_finds_unlogged_commits(
    tmp_path, monkeypatch
):
    first_sha = "1" * 40
    second_sha = "2" * 40
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decisions.jsonl"
    changelog_path = tmp_path / "config_changelog.md"
    trades_path.write_text(
        "\n".join(
            [
                json.dumps({
                    "timestamp": "2026-10-30T09:30:00+05:30",
                    "config_hash": "config-a",
                    "git_sha": first_sha,
                }),
                json.dumps({
                    "timestamp": "2026-10-30T10:00:00+05:30",
                    "config_hash": "config-b",
                    "git_sha": second_sha,
                }),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    decisions_path.write_text(
        json.dumps({
            "timestamp": "2026-10-30T04:30:00Z",
            "config_hash": "config-a",
            "git_sha": first_sha,
        })
        + "\n",
        encoding="utf-8",
    )
    changelog_path.write_text(f"Commit: {first_sha}\n", encoding="utf-8")
    monkeypatch.setattr(
        hash_report, "_git_commits_since", lambda since, repo: [first_sha, second_sha]
    )

    totals, missing_commits = hash_report.build_report(
        trades_path,
        decisions_path,
        "2026-10-01",
        changelog_path,
        tmp_path,
    )
    report = hash_report.format_report(totals, missing_commits)

    assert totals["2026-10-30"][("config-a", first_sha)] == {
        "trades": 1,
        "decisions": 1,
    }
    assert totals["2026-10-30"][("config-b", second_sha)] == {
        "trades": 1,
        "decisions": 0,
    }
    assert missing_commits == [second_sha]
    assert "**MULTIPLE PAIRS**" in report
    assert second_sha in report
