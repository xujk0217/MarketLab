# MarketLab Roadmap

> 對應 [SPEC.md](./SPEC.md) §34 的 26 個階段。每個 Phase 完成後勾選，
> 並以 git tag / commit 記錄狀態。**順序不可跳過**（尤其進入 Live 相關階段前）。

## 狀態圖例

- [ ] 未開始
- [x] 完成
- （🚧 = 進行中）

---

## Phase 0 — Foundation 🚧
Repository / Python Core / Tests / Docker / CI / Docs

- [x] Git repository 初始化
- [x] `docs/SPEC.md` v0.2 規格文件
- [x] Python 套件骨架（src layout, pyproject.toml）
- [x] Core 模組：`MarketState`、Rule-based `RegimeDetector`、`NewsEvent` Schema（pydantic）
- [x] OKX 公開行情 REST client（ticker / candles / trades）
- [x] Strategy 介面 + BuyHold / SmaCross / Momentum / MeanReversion
- [x] Backtest Engine（Fee / Slippage / PnL / MaxDrawdown / Sharpe）
- [x] 單元測試全綠
- [x] Dockerfile + GitHub Actions CI

## Phase 1 — BTC Market Explorer ✅
OKX Ticker / Trade / Candlestick → 第一版 Dashboard

- [x] OKX WebSocket 即時行情訂閱（tickers/trades 走 public、candle 走 business 端點，自動重連＋心跳）
- [x] 歷史 K 線下載腳本（history-candles 分頁抓取至 parquet Raw 層）
- [x] Dashboard v1（Streamlit：K線圖、Regime 面板、Features 面板）

## Phase 2 — Historical Data ✅
Raw / Normalized / Feature 三層資料

- [x] Raw 層：交易所原始格式落盤（immutable 批次檔，拒絕覆寫）
- [x] Normalized 層：統一 schema、UTC timestamp、去重＋OHLC 驗證＋缺口報告
- [x] Feature 層：log returns / realized vol / volume ratio / hl range / momentum lags

## Phase 3 — First Quant ✅（基礎版隨 Phase 0 先行落地）

- [x] BuyHold / SMA Cross / Momentum / Mean Reversion 四策略
- [ ] 參數化設定與 CLI 入口

## Phase 4 — Backtest Engine ✅（核心版隨 Phase 0 先行落地）

- [x] Position-based 引擎：Fee / Slippage / PnL / MaxDrawdown / Sharpe
- [ ] Portfolio 多標的支援、position sizing

## Phase 5 — Experiment Lab
參考 Qlib：Dataset/Strategy 版本、參數、Metrics、Experiment Comparison

- [ ] 實驗記錄（run metadata + metrics）
- [ ] 實驗比較報表

## Phase 6 — Market Regime v1 ✅（rule-based 核心隨 Phase 0 先行落地）

- [x] TREND_UP / TREND_DOWN / RANGE / HIGH_VOLATILITY / LOW_VOLATILITY / BREAKOUT
- [ ] EVENT_SHOCK 接上新聞事件分數（依賴 Phase 8–9）
- [ ] Regime Dashboard

## Phase 7 — Strategy Arena v2
按不同 Regime 比較 Strategy（非常重要）

- [ ] Per-regime 績效矩陣（SPEC §27 表格自動產生）

## Phase 8 — Event Data Infrastructure

- [ ] News / Macro collector（只保存，不交易）
- [ ] Source metadata（publish_time / url / source tier）

## Phase 9 — LLM Event Intelligence

- [ ] LLM → NewsEvent JSON Schema（已定義於 `marketlab.core.events`）
- [ ] Classification / Entity / Sentiment / Impact / Horizon / Novelty pipeline

## Phase 10 — Event Study

- [ ] Event × 後續 1m/5m/30m/1h/24h return 分析
- [ ] Historical Event Dataset（SPEC §17 欄位）

## Phase 11 — Event Strategy

- [ ] Event Feature 進 Strategy；A/B：Price only vs Price+Event

## Phase 12 — Event Engine + Replay

- [ ] Replay 同時播放 Market + News + Macro Events（Historical Digital Twin）
- [ ] 鐵律：時間 T 的策略看不到 T 之後的事件（防 lookahead）

## Phase 13 — Live Shadow
即時資料 → Strategy，不真實下單

## Phase 14 — Machine Learning
Logistic Regression / XGBoost

## Phase 15 — Regime AI
XGBoost / HMM / Clustering 替換或比較 Rule-based

## Phase 16 — AI Ensemble
Regime Model + Price Model + Event Model → Final Signal

## Phase 17 — OKX Demo
走 Exchange Order API，Demo 帳戶

## Phase 18 — Risk Engine
Position Limit / Daily Loss / Drawdown / Rate Limit / Data Freshness / Kill Switch

## Phase 19 — Cloud（AWS）
ECS Fargate / S3 / PostgreSQL / CloudWatch / Step Functions，24/7

## Phase 20 — RL（參考 FinRL）
MarketEnvironment：State / Action / Reward

## Phase 21 — Order Book Quant
Depth / Imbalance / TradeFlow / Microprice / Liquidity

## Phase 22 — Synthetic Exchange（參考 BSE）
Order Book / Matching Engine

## Phase 23 — Multi Agent（參考 StockSim・TwinMarket）
Momentum Agent / Market Maker / RL Agent / LLM Agent / News Agent

## Phase 24 — Advanced Replay（參考 hftbacktest）
Latency / Queue / Partial Fill / L2-L3

## Phase 25 — Small Live
Backtest / Out-of-Sample / Replay / Shadow / Demo / Risk 全部完成後才啟動。
第一階段：BTC-USDT / SPOT / No Leverage（SPEC §35 晉升階梯強制）。
