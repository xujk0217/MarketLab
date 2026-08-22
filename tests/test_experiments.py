"""Tests for the Experiment Lab (SPEC Phase 5)."""

import json

import pandas as pd
import pytest

from marketlab.backtest.engine import BacktestConfig
from marketlab.experiments import (
    ExperimentLab,
    RunRecord,
    describe_dataset,
    fingerprint,
    git_sha,
    run_backtest_experiment,
)
from marketlab.strategies import MeanReversion, Momentum, SmaCross


def candles(n=120):
    idx = pd.date_range("2026-08-20", periods=n, freq="min", tz="UTC")
    close = pd.Series(100.0 + 0.3 * pd.Series(range(n), index=idx), index=idx)
    return pd.DataFrame(
        {
            "timestamp": idx,
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 1.0,
        }
    )


class TestFingerprint:
    def test_stable_for_identical_frames(self):
        assert fingerprint(candles()) == fingerprint(candles())

    def test_changes_when_content_changes(self):
        altered = candles()
        altered.loc[altered.index[5], "close"] *= 1.01
        assert fingerprint(candles()) != fingerprint(altered)


class TestRunBacktestExperiment:
    def test_record_contains_full_provenance_and_metrics(self):
        record, result = run_backtest_experiment(
            candles(),
            SmaCross(fast=5, slow=20),
            inst_id="BTC-USDT",
            bar="1m",
            config=BacktestConfig(fee_rate=0.001),
            store=False,
        )
        assert record.strategy_name == "sma_cross"
        assert record.strategy_params == {"fast": 5, "slow": 20}
        assert record.config["fee_rate"] == 0.001
        assert record.dataset.inst_id == "BTC-USDT"
        assert record.dataset.rows == 120
        assert len(record.dataset.fingerprint) == 16
        # Metrics match what the engine produces directly.
        direct = result.metrics
        for key, value in direct.items():
            assert record.metrics[key] == pytest.approx(value)
        assert isinstance(record.git_sha, str) or record.git_sha is None

    def test_json_round_trip(self):
        record, _ = run_backtest_experiment(
            candles(), Momentum(lookback=10), inst_id="BTC-USDT", bar="1m", store=False
        )
        restored = RunRecord.from_dict(json.loads(record.to_json()))
        assert restored.run_id == record.run_id
        assert restored.dataset.fingerprint == record.dataset.fingerprint
        assert restored.strategy_params == {"lookback": 10, "deadband": 0.0}
        assert restored.metrics == record.metrics

    def test_save_and_load_all(self, tmp_path):
        lab = ExperimentLab(root=tmp_path)
        run_backtest_experiment(
            candles(), MeanReversion(window=20), inst_id="BTC-USDT", bar="1m",
            lab=lab, group="ab-test", label="A",
        )
        run_backtest_experiment(
            candles(), Momentum(lookback=15), inst_id="BTC-USDT", bar="1m",
            lab=lab, group="ab-test", label="B",
        )
        records = lab.load_all()
        assert {r.label for r in records} == {"A", "B"}

        comparison = lab.compare(group="ab-test")
        assert len(comparison) == 2
        assert set(comparison["label"]) == {"A", "B"}
        assert comparison["sharpe"].is_monotonic_decreasing  # sorted by sharpe desc

    def test_compare_empty_lab(self, tmp_path):
        assert ExperimentLab(root=tmp_path).compare().empty


def test_describe_dataset_bounds():
    info = describe_dataset(candles(60), "BTC-USDT", "1m")
    assert info.start.startswith("2026-08-20")
    assert info.end.startswith("2026-08-20")


def test_git_sha_returns_none_or_hex():
    sha = git_sha()
    assert sha is None or (len(sha) == 40 and int(sha, 16) >= 0)
