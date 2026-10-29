"""Report configuration and code revisions recorded in trade journals."""

import argparse
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPOSITORY_ROOT = Path(__file__).resolve().parent
IST = ZoneInfo("Asia/Kolkata")
COMMIT_PATTERN = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", re.IGNORECASE)


def _read_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    records: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {source}:{line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Expected a JSON object in {source}:{line_number}")
            records.append(record)
    return records


def _trading_date(record: dict[str, Any], source: str) -> str:
    value = record.get("timestamp")
    if not value:
        raise ValueError(f"Record in {source} has no timestamp")
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp {value!r} in {source}") from exc
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=IST)
    return timestamp.astimezone(IST).date().isoformat()


def _add_records(
    totals: dict[str, dict[tuple[str, str], dict[str, int]]],
    records: list[dict[str, Any]],
    category: str,
    source: str,
) -> None:
    for record in records:
        date = _trading_date(record, source)
        pair = (
            str(record.get("config_hash") or "<missing>"),
            str(record.get("git_sha") or "<missing>"),
        )
        totals[date].setdefault(pair, {"trades": 0, "decisions": 0})[category] += 1


def _git_commits_since(since: str, repo_path: str | Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(Path(repo_path).resolve()),
            "log",
            f"--since={since}",
            "--format=%H",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _changelog_commits(changelog_path: str | Path) -> set[str]:
    text = Path(changelog_path).read_text(encoding="utf-8")
    return {match.group(0).lower() for match in COMMIT_PATTERN.finditer(text)}


def build_report(
    trades_path: str | Path = "trades.jsonl",
    decisions_path: str | Path = "decision_log.jsonl",
    since: str = "",
    changelog_path: str | Path = REPOSITORY_ROOT / "config_changelog.md",
    repo_path: str | Path = REPOSITORY_ROOT,
) -> tuple[dict[str, dict[tuple[str, str], dict[str, int]]], list[str]]:
    totals: dict[str, dict[tuple[str, str], dict[str, int]]] = defaultdict(dict)
    _add_records(totals, _read_records(trades_path), "trades", str(trades_path))
    _add_records(
        totals,
        _read_records(decisions_path),
        "decisions",
        str(decisions_path),
    )
    changelog_commits = _changelog_commits(changelog_path)
    missing = [
        commit
        for commit in _git_commits_since(since, repo_path)
        if not any(
            commit.lower().startswith(entry) or entry.startswith(commit.lower())
            for entry in changelog_commits
        )
    ]
    return dict(totals), missing


def format_report(
    totals: dict[str, dict[tuple[str, str], dict[str, int]]],
    unlogged_commits: list[str],
) -> str:
    lines = ["Configuration/code pairs by trading date:"]
    if not totals:
        lines.append("  No trade or decision records found.")
    for date in sorted(totals):
        pairs = totals[date]
        lines.append(f"{date}{'  **MULTIPLE PAIRS**' if len(pairs) > 1 else ''}")
        for (config_hash, git_sha), counts in sorted(pairs.items()):
            lines.append(
                f"  config_hash={config_hash} git_sha={git_sha} "
                f"trades={counts['trades']} decisions={counts['decisions']}"
            )
    lines.append("Commits without a changelog entry:")
    if unlogged_commits:
        lines.extend(f"  {commit}" for commit in unlogged_commits)
    else:
        lines.append("  None")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="Include commits since this date")
    parser.add_argument("--trades", default="trades.jsonl")
    parser.add_argument("--decisions", default="decision_log.jsonl")
    parser.add_argument(
        "--changelog", default=str(REPOSITORY_ROOT / "config_changelog.md")
    )
    parser.add_argument("--repo", default=str(REPOSITORY_ROOT))
    args = parser.parse_args()
    totals, unlogged_commits = build_report(
        args.trades,
        args.decisions,
        args.since,
        args.changelog,
        args.repo,
    )
    print(format_report(totals, unlogged_commits))


if __name__ == "__main__":
    main()
