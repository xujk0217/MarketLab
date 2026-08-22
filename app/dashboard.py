"""MarketLab Dashboard v1 (Streamlit).

Run from the repo root:
    .venv\\Scripts\\streamlit run app/dashboard.py

Reads the Normalized layer produced by:
    python -m marketlab download --inst BTC-USDT --bar 1m --days 3
    python -m marketlab normalize --inst BTC-USDT --bar 1m
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Allow `streamlit run app/dashboard.py` from repo root without installing src changes.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from marketlab.core.regime import RuleBasedRegimeDetector  # noqa: E402
from marketlab.data.store import NORMALIZED_ROOT, load_normalized, normalize  # noqa: E402
from marketlab.features import FeatureConfig, build_features  # noqa: E402

st.set_page_config(page_title="MarketLab", page_icon="📊", layout="wide")

REGIME_WINDOW = 500
REGIME_STEP = 50


@st.cache_data(ttl=60, show_spinner=False)
def discover_instruments() -> list[tuple[str, str]]:
    """(inst_id, bar) pairs found in the normalized store."""
    pairs: list[tuple[str, str]] = []
    if NORMALIZED_ROOT.exists():
        for path in sorted(NORMALIZED_ROOT.glob("okx/*/*.parquet")):
            pairs.append((path.parent.name, path.stem))
    return pairs


@st.cache_data(ttl=60, show_spinner="Loading market data...")
def load_candles(inst_id: str, bar: str) -> pd.DataFrame | None:
    try:
        return load_normalized(inst_id, bar)
    except FileNotFoundError:
        return None


def regime_timeline(candles: pd.DataFrame) -> pd.DataFrame:
    """Rolling regime classification over the recent history."""
    detector = RuleBasedRegimeDetector()
    tail = candles.tail(REGIME_WINDOW * 4).reset_index(drop=True)
    records = []
    for end in range(REGIME_WINDOW, len(tail) + 1, REGIME_STEP):
        result = detector.detect(tail.iloc[end - REGIME_WINDOW : end])
        records.append(
            {
                "timestamp": tail["timestamp"].iloc[end - 1],
                "regime": result.regime.value,
                "confidence": result.confidence,
            }
        )
    return pd.DataFrame(records)


def price_figure(candles: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25])
    fig.add_trace(
        go.Candlestick(
            x=candles["timestamp"],
            open=candles["open"],
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            name="BTC-USDT",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=candles["timestamp"],
            y=candles["volume"],
            name="volume",
            marker_color="rgba(100,120,160,0.5)",
        ),
        row=2,
        col=1,
    )
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False)
    fig.update_yaxes(title_text="price (USDT)", row=1)
    fig.update_yaxes(title_text="volume", row=2)
    return fig


def main() -> None:
    st.title("MarketLab · BTC Market Explorer")
    st.caption("Phase 1 dashboard — normalized OKX data + rule-based regime")

    pairs = discover_instruments()
    if not pairs:
        st.warning(
            "No normalized data yet. From the repo root run:\n\n"
            "```bash\npython -m marketlab download --inst BTC-USDT --bar 1m --days 3\n"
            "python -m marketlab normalize --inst BTC-USDT --bar 1m\n```"
        )
        return

    left, right = st.columns([1, 3])
    with left:
        inst_options = sorted({p[0] for p in pairs})
        inst_id = st.selectbox("Instrument", inst_options)
        bars = [b for i, b in pairs if i == inst_id]
        bar = st.selectbox("Bar", bars)

    candles = load_candles(inst_id, bar)
    if candles is None or candles.empty:
        st.error("Normalized file exists but could not be read.")
        return

    _, gap_report = normalize(candles.tail(5000), bar)
    features = build_features(candles, FeatureConfig())
    view = candles.tail(REGIME_WINDOW * 3)

    regime = RuleBasedRegimeDetector().detect(view)
    vol_col = next(c for c in features.columns if c.startswith("realized_vol_"))

    m_price, m_change, m_regime, m_conf, m_gaps = st.columns(5)
    m_price.metric("Last close", f"{view['close'].iloc[-1]:,.1f}")
    change = view["close"].iloc[-1] / view["close"].iloc[0] - 1
    m_change.metric("Window Δ", f"{change:+.2%}")
    m_regime.metric("Regime", regime.regime.value.replace("_", " ").title())
    m_conf.metric("Confidence", f"{regime.confidence:.0%}")
    m_gaps.metric("Missing bars (5k)", gap_report.missing_bars)

    tab_price, tab_regime, tab_features = st.tabs(["📈 Price", "🧭 Regime", "🚦 Features"])

    with tab_price:
        st.plotly_chart(price_figure(view), use_container_width=True)

    with tab_regime:
        col_a, col_b = st.columns([1, 2])
        col_a.markdown(f"### {regime.regime.value}\nconfidence **{regime.confidence:.0%}**\n\nwindow: {REGIME_WINDOW} bars")
        timeline = regime_timeline(candles)
        if not timeline.empty:
            fig = go.Figure(
                go.Scatter(
                    x=timeline["timestamp"],
                    y=timeline["regime"],
                    mode="markers",
                    marker=dict(size=9, color=timeline["confidence"], colorscale="Viridis"),
                )
            )
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="regime")
            col_b.plotly_chart(fig, use_container_width=True)

    with tab_features:
        f_view = features.tail(REGIME_WINDOW * 3)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
        fig.add_trace(go.Scatter(x=f_view["timestamp"], y=f_view[vol_col], name=vol_col), row=1, col=1)
        vr_col = next(c for c in features.columns if c.startswith("volume_ratio_"))
        fig.add_trace(go.Scatter(x=f_view["timestamp"], y=f_view[vr_col], name=vr_col), row=2, col=1)
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
