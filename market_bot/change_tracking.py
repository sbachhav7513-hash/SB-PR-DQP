import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GitIdentity:
    sha: str
    dirty: bool


def get_git_identity(repo_path: str | Path = REPOSITORY_ROOT) -> GitIdentity:
    repository = Path(repo_path).resolve()
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return GitIdentity(sha=commit, dirty=bool(status.strip()))


def is_config_hash_changelogged(
    config_hash: str,
    changelog_path: str | Path = REPOSITORY_ROOT / "config_changelog.md",
) -> bool:
    text = Path(changelog_path).read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(?<![0-9a-f]){re.escape(config_hash)}(?![0-9a-f])",
        re.IGNORECASE,
    )
    return pattern.search(text) is not None


def log_startup_identity(
    config_hash: str,
    changelog_path: str | Path = REPOSITORY_ROOT / "config_changelog.md",
    repo_path: str | Path = REPOSITORY_ROOT,
) -> GitIdentity:
    identity = get_git_identity(repo_path)
    logger.info(
        "Runtime identity: config_hash=%s git_sha=%s git_dirty=%s",
        config_hash,
        identity.sha,
        identity.dirty,
    )
    if not is_config_hash_changelogged(config_hash, changelog_path):
        logger.warning(
            "Config hash %s is not listed in %s",
            config_hash,
            changelog_path,
        )
    return identity
