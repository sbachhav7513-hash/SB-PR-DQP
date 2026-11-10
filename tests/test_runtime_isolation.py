import os
import subprocess
import sys
from pathlib import Path

import pytest

from market_bot.kite_main import _log_runtime_flags
from market_bot.runtime_safety import require_temporary_path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ARTIFACTS = (
    "kite_bot.log",
    "trades.jsonl",
    "decision_log.jsonl",
    "commands.jsonl",
    "paper_trading_data",
    "sim",
)


def _artifact_snapshot():
    snapshot = {}
    for name in RUNTIME_ARTIFACTS:
        path = ROOT / name
        paths = [path]
        if path.is_dir():
            paths.extend(sorted(path.rglob("*")))
        for item in paths:
            if item.exists():
                stat = item.stat()
                snapshot[str(item.relative_to(ROOT))] = (
                    stat.st_mtime_ns,
                    stat.st_size,
                    item.is_dir(),
                )
    return snapshot


def _subprocess_env(tmp_path):
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["BOT_SIM_MODE"] = "false"
    env.pop("BOT_SIM_DIR", None)
    env["TMP"] = str(tmp_path)
    env["TEMP"] = str(tmp_path)
    return env


def test_importing_kite_main_has_no_runtime_file_side_effects(tmp_path):
    before = _artifact_snapshot()
    script = (
        "import pathlib; "
        "import market_bot.kite_main; "
        "names=('kite_bot.log','trades.jsonl','decision_log.jsonl',"
        "'commands.jsonl','paper_trading_data'); "
        "assert not any(pathlib.Path(name).exists() for name in names)"
    )
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=_subprocess_env(tmp_path),
        check=True,
        capture_output=True,
        text=True,
    )
    assert _artifact_snapshot() == before


@pytest.mark.parametrize("sim_mode", [False, True])
def test_run_kite_bot_configures_a_file_handler_in_isolated_directory(
    tmp_path, sim_mode
):
    sim_dir = tmp_path / "isolated-simulation"
    env = _subprocess_env(tmp_path)
    env["BOT_SIM_MODE"] = str(sim_mode).lower()
    env["BOT_SIM_DIR"] = str(sim_dir)
    script = (
        "import logging; "
        "from run_kite_bot import configure_file_logging; "
        "path=configure_file_logging(); "
        "assert any(isinstance(handler, logging.FileHandler) "
        "for handler in logging.getLogger().handlers); "
        "logging.getLogger('isolation-test').warning('file-handler-ready'); "
        "[handler.flush() for handler in logging.getLogger().handlers]; "
        "print(path)"
    )
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    log_path = sim_dir / "kite_bot.log" if sim_mode else tmp_path / "kite_bot.log"
    assert "file-handler-ready" in log_path.read_text(encoding="utf-8")
    if sim_mode:
        assert not (tmp_path / "kite_bot.log").exists()
    else:
        assert not (sim_dir / "kite_bot.log").exists()


def test_write_targets_must_be_inside_the_system_temp_directory(tmp_path):
    assert require_temporary_path(tmp_path / "report.md", purpose="test").parent == (
        tmp_path.resolve()
    )
    with pytest.raises(ValueError, match="system temporary directory"):
        require_temporary_path(ROOT / "paper_trading_data" / "should-not-write", purpose="test")


def test_startup_logs_all_requested_runtime_flags(caplog):
    flags = {
        "partial_profit_v2": True,
        "entry_feature_logging_v2": False,
        "stop_quote_validation_v2": True,
        "runner_gap_v2": False,
        "profit_lock_v2": True,
        "trail_close_confirm_v2": False,
        "stock_take_profit_v2": True,
        "option_quote_validated_stops_enabled": True,
    }

    with caplog.at_level("INFO", logger="market_bot.kite_main"):
        _log_runtime_flags(flags, "PAPER")

    assert "mode=PAPER" in caplog.text
    for name, value in flags.items():
        assert f"{name}={value}" in caplog.text


def test_scenario_tool_rejects_non_temporary_output(monkeypatch):
    import sim_scenarios

    output = ROOT / "sim" / "phase-e-isolation-probe"
    assert not output.exists()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sim_scenarios.py",
            "--sim-dir",
            str(output),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        sim_scenarios.main()

    assert exc_info.value.code == 2
    assert not output.exists()
