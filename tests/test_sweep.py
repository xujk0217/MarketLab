"""Tests for parameter grid sweeps."""


import numpy as np
import pandas as pd
import pytest

from marketlab.backtest.engine import BacktestConfig
from marketlab.experiments import ExperimentLab
from marketlab.experiments.sweep import (
    coerce_scalar,
    expand_grid,
    run_sweep,
    sweep_table,
    validate_params,
)
from marketlab.strategies import MeanReversion, Momentum, SmaCross


def candles(n=150):
    idx = pd.date_range("2026-08-20", periods=n, freq="min", tz="UTC")
    rng = np.random.default_rng(5)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.002, n))
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


class TestCoerceScalar:
    def test_types(self):
        assert coerce_scalar("20") == 20 and isinstance(coerce_scalar("20"), int)
        assert coerce_scalar("2.0") == pytest.approx(2.0)
        assert coerce_scalar("true") is True
        assert coerce_scalar("False") is False
        assert coerce_scalar("BTC-USDT") == "BTC-USDT"


class TestExpandGrid:
    def test_cartesian_product(self):
        combos = list(expand_grid({"a": [1, 2], "b": ["x", "y", "z"]}))
        assert len(combos) == 6
        assert {"a": 2, "b": "z"} in combos

    def test_single_value_axis(self):
        combos = list(expand_grid({"a": [5], "b": [1, 2]}))
        assert len(combos) == 2

    def test_empty_spec_yields_one_empty_combo(self):
        assert list(expand_grid({})) == [{}]


class TestValidateParams:
    def test_unknown_param_rejected_before_running(self):
        with pytest.raises(ValueError, match="does not accept"):
            validate_params(Momentum, {"window": 10})
        validate_params(Momentum, {"lookback": 30, "deadband": 0.001})  # ok

    def test_sweep_fails_fast_on_typo(self):
        with pytest.raises(ValueError):
            run_sweep(
                candles(),
                MeanReversion,
                {"windo": [20]},  # typo
                inst_id="BTC-USDT",
                bar="1m",
                group="g",
            )


class TestRunSweep:
    def test_one_record_per_combination_same_group_and_fingerprint(self, tmp_path):
        lab = ExperimentLab(root=tmp_path)
        entries = run_sweep(
            candles(),
            SmaCross,
            {"fast": [3, 5], "slow": [10]},
            inst_id="BTC-USDT",
            bar="1m",
            config=BacktestConfig(fee_rate=0.0),
            lab=lab,
            group="sweep-1",
        )
        assert len(entries) == 2
        records = lab.load_all()
        assert len(records) == 2
        assert {r.group for r in records} == {"sweep-1"}
        fingerprints = {r.dataset.fingerprint for r in records}
        assert len(fingerprints) == 1  # identical dataset across the sweep
        assert {e.label for e in entries} == {"fast=3,slow=10", "fast=5,slow=10"}

    def test_labels_are_deterministic_and_distinct(self, tmp_path):
        lab = ExperimentLab(root=tmp_path)
        entries = run_sweep(
            candles(),
            MeanReversion,
            {"window": [10], "entry_z": [1.0, 2.0]},
            inst_id="BTC-USDT",
            bar="1m",
            lab=lab,
            group="sweep-2",
        )
        labels = sorted(e.label for e in entries)
        assert labels == ["entry_z=1.0,window=10", "entry_z=2.0,window=10"]

    def test_sweep_table_sorted_by_sharpe(self, tmp_path):
        lab = ExperimentLab(root=tmp_path)
        entries = run_sweep(
            candles(),
            Momentum,
            {"lookback": [5, 60]},
            inst_id="BTC-USDT",
            bar="1m",
            lab=lab,
            group="sweep-3",
        )
        table = sweep_table(entries)
        assert list(table["sharpe"]) == sorted(table["sharpe"], reverse=True)
