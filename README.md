# MarketLab

**Open-source event-aware Market Digital Twin & AI Quant Research Platform**

> 核心市場：BTC-USDT ・ 初始交易所：OKX
> 最終方向：Historical Research → Replay → Live Shadow → Demo → Controlled Live Trading
> 最終目標：找出經真實市場驗證後仍具有正期望值的 Quant / AI Strategy

MarketLab 不是「預測 BTC 漲跌」的專案，而是一個**不會欺騙自己的市場研究環境**：
把價格、成交、Order Book、新聞、政策、Macro 全部收斂成統一的 `MarketState`，
在上面研究 Regime 偵測、事件智慧（LLM）、策略路由與嚴格驗證流程。

## 核心設計原則（鐵律）

1. **LLM 不直接交易**：`News → LLM → Event Feature → Model → Strategy → Risk → Order`
2. **防 lookahead bias**：時間 T 的策略看不到 T 之後的任何資料（含新聞）
3. **A/B 驗證一切**：每個 AI Feature 都必須可關閉；沒有 OOS 證據就刪掉，不能因為「LLM 很酷」就保留
4. **晉升階梯**：`RESEARCH → BACKTESTED → OUT_OF_SAMPLE → REPLAY → SHADOW → DEMO → LIVE_CANDIDATE → LIVE`，不可跳級

## 快速開始

```bash
# 需要 Python 3.11+
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"     # Windows
# source .venv/bin/activate && pip install -e ".[dev]"   # macOS/Linux

pytest            # 執行測試
ruff check .      # lint
```

## 專案結構

```text
src/marketlab/
├── core/
│   ├── market_state.py   # MarketState — Digital Twin 的統一狀態 (SPEC §18)
│   ├── regime.py         # Rule-based Regime Detector (SPEC §3–4)
│   └── events.py         # NewsEvent JSON Schema + Source Reliability (SPEC §9–12)
├── data/okx/             # OKX 公開行情 REST client (ticker/candles/trades)
├── strategies/           # Strategy 介面 + BuyHold/SmaCross/Momentum/MeanReversion
└── backtest/             # 引擎：Fee / Slippage / PnL / MaxDrawdown / Sharpe
docs/
├── SPEC.md               # 完整產品與技術規格書 v0.2（唯一需求來源）
└── ROADMAP.md            # Phase 0–25 路線圖與驗收條件
```

## 文件

- [規格書 v0.2](docs/SPEC.md) — 42 節完整需求
- [路線圖](docs/ROADMAP.md) — Phase 0–25 進度追蹤

## License

MIT — 見 [LICENSE](LICENSE)
