# MarketLab — Open-source Market Digital Twin & AI Quant Research Platform

## 完整產品與技術規格書 v0.2

| 項目 | 內容 |
| --- | --- |
| 核心市場 | BTC-USDT |
| 初始交易所 | OKX |
| 專案定位 | Open-source Quant / AI / Market Simulation Research Platform |
| 最終方向 | Historical Research → Replay → Live Shadow → Demo → Controlled Live Trading |
| 最終研究目標 | 找出經真實市場驗證後仍具有正期望值的 Quant / AI Strategy |

> 本文件為 MarketLab 的唯一需求來源（Single Source of Truth）。
> 原稿中少數亂碼字元（如「เงนจรง」）已依上下文還原為「真實」。

---

## 1. 專案核心願景

MarketLab 要建立一個接近真實市場狀態的「市場實驗空間」（Market Digital Twin）。

真實市場持續產生：

* Price
* Trades
* Order Book
* Volume
* Volatility
* News
* Policy
* 美國政府與監管機構發言
* ETF Flow
* Macro Data
* Cross-asset movements

MarketLab 將這些資訊轉成統一的市場狀態：

```text
Real World
   ├── Price / Trades / Order Book
   └── News / Policy / Macro / ETF Flow / Cross Asset
            │
            ▼
     Market Digital Twin
            │
            ▼
       Market State ──►  Quant Strategy / ML Model / AI Agent
                              │
                              ▼
                         Risk Engine
                              │
                              ▼
                   Backtest / Demo / Live
```

最終目標：

> **同一個 Strategy 可以在歷史市場、重播市場、即時市場與真實市場使用，而不必重新撰寫交易邏輯。**

---

## 2. MarketLab 不只是預測 BTC

系統不把問題定義成「BTC 明天會漲嗎？」，而是拆成五個問題：

### 問題 A — 現在市場是什麼狀態？（Regime）

Bull Trend / Bear Trend / Sideways / Low Volatility / High Volatility / Breakout / Event Shock

### 問題 B — 發生了什麼事件？

Fed Decision / Trump Statement / SEC Regulation / ETF Flow / Tariff Announcement /
War・Geopolitics / Exchange Failure / Crypto Regulation

### 問題 C — 市場正在如何反應？

Price ↑↓ / Volume ↑↓ / Volatility ↑↓ / Order Book buying pressure / USD flow

### 問題 D — 哪個 Strategy 適合現在？

* Trend → Momentum
* Range → Mean Reversion
* Breakout → Volatility Breakout
* Extreme Event → Reduce Risk

### 問題 E — 是否值得交易？

```text
Expected Return − Fee − Slippage − Risk = Trade / No Trade
```

---

## 3. Market Regime Engine

**Market Regime Detector**

輸入：

Return(1m) / Return(5m) / Return(1h) / Return(24h) / Volatility / Volume / Spread /
Order Book Imbalance / Funding / Cross Asset

輸出（機率分佈）：

```text
Bull Trend           61%
Sideways             14%
Volatility Breakout  18%
Bear Trend            7%
```

第一版使用 Rule-based；之後依序嘗試 Logistic Regression / XGBoost /
Hidden Markov Model / Clustering，並與 Rule-based 比較。

---

## 4. Regime 定義

第一版至少支援：

| Regime | 說明 |
| --- | --- |
| `TREND_UP` | 多頭趨勢 |
| `TREND_DOWN` | 空頭趨勢 |
| `RANGE` | 盤整 |
| `LOW_VOLATILITY` | 低波動 |
| `HIGH_VOLATILITY` | 高波動 |
| `BREAKOUT` | 突破 |
| `EVENT_SHOCK` | 事件衝擊（v0.2 新增，重要類型） |

`EVENT_SHOCK` 判定範例：重大政策公布 + 成交量快速上升 + 價格快速移動 + 新聞訊號升高。

---

## 5. Strategy Router

不再讓一個策略永久控制 Portfolio：

```text
Regime ──► Strategy Router ──► Strategy
```

預設路由：

| Regime | Strategy |
| --- | --- |
| TREND_UP | Momentum |
| RANGE | Mean Reversion |
| BREAKOUT | Volatility Breakout |
| EVENT_SHOCK | Event Strategy / Defensive |

後期可升級為 Mixture-of-Experts（Gating Network 加權 Momentum / MeanRev / EventModel）。

---

## 6. Event Intelligence Layer

新增 **Event Intelligence Engine**，負責把以下輸入統一轉換成 `MarketEvent`：

News / Government Statement / Regulation / Macro Announcement /
Social・Public Statement / ETF Flow Event / Geopolitical Event

---

## 7. 為什麼需要 LLM

傳統程式容易理解 `BTC price = 70,000`，
但難以理解「US president urges Congress to pass crypto market legislation」。

LLM 的工作：`Text → Understand Event → Structured Data`

---

## 8. LLM 不直接交易（鐵律）

第一階段禁止：`News → LLM → BUY`

正確架構：

```text
News → LLM → Event Feature → Quant Model → Strategy → Risk → Order
```

這是 MarketLab 非常重要的設計原則。

---

## 9. NewsEvent Schema

LLM 必須輸出固定 JSON Schema。範例：

```json
{
  "event_type": "CRYPTO_REGULATION",
  "entities": ["Donald Trump", "United States", "Bitcoin"],
  "topic": "Clarity Act",
  "sentiment": 0.64,
  "crypto_direction": "POSITIVE",
  "expected_horizon": "SHORT_TERM",
  "impact_score": 0.78,
  "confidence": 0.84,
  "novelty": 0.71
}
```

---

## 10. 不只做 Sentiment

不要只有 Positive / Negative——「Fed 升息」文字本身不一定帶情緒，但市場含義可能很重要。

LLM 需辨識 Event Type：

`MONETARY_POLICY / CRYPTO_REGULATION / TRADE_POLICY / ETF / GEOPOLITICS / SEC / CFTC / EXCHANGE / SECURITY_BREACH / LIQUIDITY / MACRO`

---

## 11. Event Impact

每個事件另外產生：`direction`、`magnitude`、`confidence`、`horizon`、`novelty`。

範例：Event「Trump supports crypto legislation」→ Direction: Positive,
Impact: 0.72, Confidence: 0.81, Horizon: hours/days。

---

## 12. Source Reliability

所有新聞來源需記錄：`source / publish_time / receive_time / author / url / revision_time`。

並計算 Source Reliability 分級：

Official Government > Central Bank > SEC・CFTC > Reuters（Wire Service） >
Major News > Crypto Media > Social Media > Unknown

不同來源不能全部一樣看待。

---

## 13. Duplicate News Detection

同一事件可能出現在 Reuters / Bloomberg / CoinDesk / Twitter / Reddit 等 100 個轉貼，
不能算成 100 次 Bullish Event。

方法：Embedding + Entity + Timestamp → **Event Clustering** → 形成 **Canonical Event**。

---

## 14. News Timeline

每個 Event 必須放在市場 Timeline 上。例如：

```text
10:00      BTC $68,900
10:03      Trump Crypto Statement        ← event
10:03:02   Volume ↑                      ← market reaction
10:04      BTC $69,200
10:10      BTC $70,000
```

Replay 鐵律：**10:02 的 Strategy 不可以知道 10:03 的新聞（嚴禁 lookahead bias）。**

---

## 15. Event Study Engine

新增 Research Module：分析「某類事件發生後市場通常怎麼動」。

例如 `CRYPTO_REGULATION` 事件之後，記錄 1m / 5m / 30m / 1h / 24h return 全部。

---

## 16. 讓模型自己學新聞真正的影響

不要人工寫死「Trump + Crypto = Bullish」（可能完全錯）。
應建立：

```text
Historical News Event + Actual Market Reaction → Training Label
```

例如：Trump Tariff Announcement → BTC after 1h −3.2%、after 24h −5.1%。模型自己學。

---

## 17. Event Dataset

建立 `EventDataset`，欄位：

`timestamp / event_type / entities / sentiment / impact / novelty / BTC_before /
BTC_after_1m / BTC_after_5m / BTC_after_1h / BTC_after_24h / volume_change / volatility_change`

未來可能成為 MarketLab 很有價值的一份 Dataset。

---

## 18. 新版 Market State（Market Digital Twin State）

MarketState 不再只有價格，完整欄位：

Price / Return / Volume / Volatility / Spread / OrderBook / TradeFlow / Funding /
OpenInterest / CrossAsset / Macro / NewsEvent / EventScore / MarketRegime

---

## 19. Cross-market Data

BTC 不能只看 BTC。新增：S&P 500 / Nasdaq / Gold / DXY / US Treasury Yield / ETH。

後期：ETF Flow / Stablecoin Flow / Funding / Open Interest / Liquidation。

---

## 20. Macro Event

系統需要記錄：CPI / PCE / Fed Rate Decision / Fed Speech / Employment /
Treasury Policy / Tariffs。（Crypto 越來越受 Macro Liquidity 影響）

---

## 21–25. AI Architecture：四個模型

```text
AI System = Regime Model + Price Model + Event Model + Risk Model
```

| Model | 回答的問題 |
| --- | --- |
| Regime Model | 現在是什麼市場？ |
| Price Model | 未來某時間範圍的 **return distribution** 是什麼？（不是只有 UP/DOWN） |
| Event Model | 這個新聞可能造成什麼市場影響？ |
| Risk Model | 現在適不適合承擔部位？ |

---

## 26. Ensemble

```text
Regime + Price Signal + Event Signal + Risk → Final Strategy
```

範例：Momentum Signal +0.70、News Signal +0.40、Regime=Strong Trend、Risk=Normal
→ Final: BUY 0.62

---

## 27. Strategy Arena v2

不只比較總報酬，需**按照 Regime** 比較策略表現：

| Strategy | Bull | Bear | Range | Breakout |
| -------- | ---: | ---: | ----: | -------: |
| BuyHold  |    + |   -- |     0 |        + |
| Momentum |   ++ |    + |     - |       ++ |
| MeanRev  |    - |    - |    ++ |       -- |
| XGBoost  |    + |    + |     + |        + |
| Event AI |    + |    + |     0 |       ++ |

研究問題：「哪個 Strategy 在什麼市場最有效？」

---

## 28. Market Visualization v2

首頁呈現：價格卡（BTC-USDT $78,000 +5.3%）、Market Regime（BREAKOUT, Confidence 82%）、
Market Event（US Crypto Regulation, Impact High Positive）、Volatility（High）、
各 Strategy 訊號（Momentum BUY / XGBoost BUY / MeanRev SELL / Event AI BUY）、
Final Strategy（BUY, Risk Medium）。

---

## 29. News Visualization

Event Timeline：BTC 價格曲線上疊加事件標記（如 Trump Statement、Crypto Regulation,
Impact +0.78）。

---

## 30. Strategy Decision Explainability

點擊某次 BUY 可展開決策分解：

```text
BUY BTC   Time 10:04:23
Why?
  Momentum         +0.72
  Regime BREAKOUT  (+)
  News             +0.54
  Order Book       +0.31
  Volatility Risk  −0.12
Final Score       +0.64
```

---

## 31. Counterfactual Analysis

後期功能：「如果沒有這則新聞，策略會怎麼做？」（WITH EVENT: BUY vs WITHOUT EVENT: HOLD）
用於研究 LLM News Layer 到底有沒有幫助。

---

## 32. A/B Experiment（鐵律）

每個 AI Feature 都必須可以關閉。例：Model A（Price only）vs Model B（Price + News），
比較 Return / Sharpe / Drawdown / Accuracy。

如果 Price+News 沒有比較好 → 就刪掉 News Feature。**不能因為「LLM 很酷」就保留。**

---

## 33. 新版 Research Pipeline

```text
Hypothesis → Data → Features → Market Regime → News Event → Model → Strategy
→ Backtest → Out-of-Sample → Replay → Live Shadow → Demo → Small Live → Evaluation
```

---

## 34. 階段規劃（Phase 0 – 25）

| Phase | 名稱 | 內容 |
| ----- | ---- | ---- |
| 0 | Foundation | Repository / Python Core / Tests / Docker / CI / Docs |
| 1 | BTC Market Explorer | OKX Ticker / Trade / Candlestick + 第一版 Dashboard |
| 2 | Historical Data | Raw / Normalized / Feature 三層資料 |
| 3 | First Quant | Buy Hold / Moving Average / Momentum / Mean Reversion |
| 4 | Backtest Engine | Portfolio / PnL / Fee / Slippage / Drawdown / Sharpe |
| 5 | Experiment Lab | 參考 Qlib：Dataset/Strategy 版本、參數、Metrics、比較 |
| 6 | Market Regime v1 | Rule-based 辨識 Trend/Range/Vol/Breakout + Dashboard |
| 7 | Strategy Arena v2 | 按 Regime 比較 Strategy（非常重要） |
| 8 | Event Data Infra | 收集 News/Macro/Regulation/Policy，只保存不交易 |
| 9 | LLM Event Intelligence | Classification/Entity/Sentiment/Impact/Horizon/Novelty + NewsEvent Schema |
| 10 | Event Study | 不同 Event × BTC Reaction → Historical Event Dataset |
| 11 | Event Strategy | 第一次讓 Event Feature 進 Strategy；Price only vs Price+Event |
| 12 | Event Engine + Replay | Replay 同時播放 Market/News/Macro Events → Historical Digital Twin |
| 13 | Live Shadow | 即時 OKX+News+Market→Strategy，但不真實下單 |
| 14 | Machine Learning | Logistic Regression / XGBoost |
| 15 | Regime AI | Rule-based 替換/比較 XGBoost / HMM / Clustering |
| 16 | AI Ensemble | Regime Model + Price Model + Event Model |
| 17 | OKX Demo | 走 Exchange Order API 但用 Demo 帳戶 |
| 18 | Risk Engine | Position Limit / Daily Loss / Drawdown / Rate Limit / Data Freshness / Kill Switch |
| 19 | Cloud | AWS：ECS Fargate / S3 / PostgreSQL / CloudWatch / Step Functions，24/7 |
| 20 | RL | 參考 FinRL：MarketEnvironment(State/Action/Reward) |
| 21 | Order Book Quant | Depth / Imbalance / TradeFlow / Microprice / Liquidity |
| 22 | Synthetic Exchange | 參考 BSE：Order Book / Matching Engine |
| 23 | Multi Agent | 參考 StockSim・TwinMarket：Momentum/MM/RL/LLM/News Agents |
| 24 | Advanced Replay | 參考 hftbacktest：Latency / Queue / Partial Fill / L2-L3 |
| 25 | Small Live | 全部驗證完成後：BTC-USDT SPOT No Leverage 小額實盤 |

詳細驗收條件見 [ROADMAP.md](./ROADMAP.md)。

---

## 35. Live Strategy Promotion（狀態晉升階梯）

```text
RESEARCH → BACKTESTED → OUT_OF_SAMPLE → REPLAY → SHADOW → DEMO → LIVE_CANDIDATE → LIVE
```

任何模型不能直接 TRAINED → LIVE。

---

## 36. 200 USDT Echtgeld Experiment

第一階段真實帳戶資本 200 USDT。目標**不是** 200→1000，真正 KPI：

Execution Correctness / PnL Reconciliation / Live vs Backtest Gap /
Live vs Shadow Gap / Fee / Slippage / Drawdown / System Stability

限制範例：Max Exposure 20–25%、Max Position 50 USDT、No Leverage、Daily Loss Limit。

---

## 37. 200 → 1000 Challenge

另做成 Research Challenge：Starting Capital 200 USDT、Goal 1000 USDT。
策略：BuyHold / Momentum / Regime / XGBoost / Event AI / RL。

不能只比誰最快到 1000，還需：Probability of Ruin / Maximum Drawdown / Volatility /
Risk-adjusted Return / Time to Target。

---

## 38. 開源專案定位

> **Open-source event-aware market digital twin and AI quantitative research platform.**

主要特色：Historical / Replay / Live / Synthetic 四種模式；
Price / Order Book / News / Macro / Policy / AI 全部共享相同 **MarketState**。

---

## 39. 與既有開源專案的關係

| 專案 | 我們學什麼 | MarketLab 多了什麼／更強調什麼 |
| --- | --- | --- |
| Qlib | Experiment / ML Pipeline | Live Twin / Replay / Event Intelligence |
| FinRL | Environment / Agent / RL | Unified Quant + ML + LLM |
| StockSim | Agent / Market Simulation | Research ↔ Real Market |
| TwinMarket | LLM Agents / News / Behavior | Quant Validation |
| NautilusTrader | Backtest/Live parity | — |
| hftbacktest | Realistic Replay / Latency / Queue | — |
| BSE | Exchange / Order Book / Matching | — |

---

## 40. 最終完整架構

```text
                        REAL WORLD
   Market          Macro          News / Policy
     │               │                 │
 Market Feed    Macro Feed     Event Collector
                     │                 │
                     └────► LLM Event Engine
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   │
          MARKET STATE ◄──────────────────────────┘
              │
   ┌──────────┼────────────┐
   ▼          ▼            ▼
 Regime     Price        Event
  Model      Model        Model
   └──────────┼────────────┘
              ▼
        Strategy Router
              │
   Momentum / MeanRev / AI Quant
              │
              ▼
         Risk Engine
              │
   Backtest / Demo / Live
```

---

## 41. 最核心的研究問題

1. 價格、交易行為、宏觀環境與公開事件結合後，能否建立**未見資料及即時真實市場中仍具穩定正期望值**的策略？
2. 市場狀態改變時，動態選擇 Strategy 是否優於固定 Strategy？
3. News / Policy / LLM Event Intelligence 是否真的帶來額外 Alpha？

第 3 題必須公平比較：

```text
Price Model vs Price+LLM News vs Price+Regime vs Price+Regime+LLM
```

只有當 Out-of-Sample / Replay / Live Shadow / Demo **全部**顯示 LLM Layer 有增加效果，
才可以說 News Intelligence 有實際價值。MarketLab 不能預設 LLM = 更好。

---

## 42. 最終目標

```text
Real Market → Understand Market → Understand Events → Detect Regime → Find Strategy
→ Validate → Replay Reality → Shadow Reality → Trade Safely → Measure Reality → Improve
```

系統最大的價值不是保證賺錢，而是：

> **盡可能建立一個不會因為 Backtest、AI、新聞解讀或資料洩漏而欺騙自己的市場研究環境，
> 讓真正存在的市場 edge 有機會被發現、驗證並安全部署。**
