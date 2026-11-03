from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backfill_option_contract_ids import _day_directory, backfill_day


def test_backfill_writes_new_file_and_only_uses_unique_exact_signal_ids(tmp_path):
    day = date(2026, 10, 29)
    directory = _day_directory(tmp_path, day)
    directory.mkdir(parents=True)
    decisions_path = directory / "decisions.parquet"
    trades_path = directory / "trades.parquet"
    source = pd.DataFrame(
        [
            {"signal_id": "sig-exact", "ticker": "NIFTY_CE", "contract_id": ""},
            {"signal_id": "sig-ambiguous", "ticker": "NIFTY_CE", "contract_id": ""},
            {
                "signal_id": "sig-existing",
                "ticker": "NIFTY_CE",
                "contract_id": "NFO:EXISTING",
            },
            {"signal_id": "", "ticker": "BANKNIFTY_PE", "contract_id": ""},
        ]
    )
    source.to_parquet(decisions_path, engine="fastparquet", index=False)
    pd.DataFrame(
        [
            {"signal_id": "sig-exact", "contract_id": "NFO:EXACT"},
            {"signal_id": "sig-ambiguous", "contract_id": "NFO:ONE"},
            {"signal_id": "sig-ambiguous", "contract_id": "NFO:TWO"},
        ]
    ).to_parquet(trades_path, engine="fastparquet", index=False)

    output_path, updated, total = backfill_day(tmp_path, day)

    output = pd.read_parquet(output_path, engine="fastparquet")
    original = pd.read_parquet(decisions_path, engine="fastparquet")
    assert output_path != decisions_path
    assert output_path.exists()
    assert updated == 1
    assert total == 4
    assert output.loc[0, "contract_id"] == "NFO:EXACT"
    assert output.loc[1, "contract_id"] == ""
    assert output.loc[2, "contract_id"] == "NFO:EXISTING"
    assert output.loc[3, "contract_id"] == ""
    assert original.loc[0, "contract_id"] == ""
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        backfill_day(tmp_path, day)


def test_backfill_reads_new_decision_part_layout(tmp_path):
    day = date(2026, 10, 29)
    directory = _day_directory(tmp_path, day)
    parts_dir = directory / "decisions"
    parts_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"signal_id": "sig-exact", "ticker": "NIFTY_CE", "contract_id": ""},
            {"signal_id": "sig-unmapped", "ticker": "NIFTY_PE", "contract_id": ""},
        ]
    ).to_parquet(
        parts_dir / "decisions_10_300000_000001.parquet",
        engine="fastparquet",
        index=False,
    )
    pd.DataFrame(
        [{"signal_id": "sig-exact", "contract_id": "NFO:EXACT"}]
    ).to_parquet(directory / "trades.parquet", engine="fastparquet", index=False)

    output_path, updated, total = backfill_day(tmp_path, day)

    output = pd.read_parquet(output_path, engine="fastparquet")
    assert updated == 1
    assert total == 2
    assert output["contract_id"].tolist() == ["NFO:EXACT", ""]
