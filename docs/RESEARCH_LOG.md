# MarketLab 研究發現日誌

> 每一條都必須有資料指紋/指令可重現。這是「不欺騙自己」的紀錄簿——
> 結論隨時可能被新資料推翻，推翻時請新增條目而不是修改舊條目。

---

## 2026-08-22 · 交易成本在低時間框架具有支配性

- **資料**：BTC-USDT OKX spot，2 天 × 1m（2881 bars，指紋 `2965bcb15f8cc2f7`）
- **方法**：`marketlab backtest` 四策略同一資料、fee 0.1% + slippage 5bps
- **發現**：
  - BuyHold +10.4%（1 筆交易）；Momentum(30) 毛報酬約 +26% 但 274 筆交易被成本吃掉 82% 資本 → 淨 −56%
  - MeanRev(30, 2σ) 同樣死於成本（281 筆，−42%）
- **含義**：1m 級別的訊號必須極度稀疏，或需要 order book 微觀結構降低執行成本（Phase 21）。
  對應 SPEC §2 問題 E 的「成本門檻」是真實存在的第一道篩。

## 2026-08-22 · Momentum 只在 BREAKOUT/TREND 有正貢獻（初步）

- **資料**：
  - 90 天 × 1H（2160 bars）：BREAKOUT×2、RANGE×27、LOW_VOL×5、TREND_DOWN×1 段
  - 30 天 × 5m（8640 bars）：全五種 regime 出現
- **方法**：`marketlab arena --metric total_return`（分段標記無 lookahead；同 regime 複合＝只在該 regime 交易）
- **發現**（1H）：
  - Momentum：BREAKOUT **+12.2%**、TREND_DOWN +5.3%（做空側），但 RANGE **−42.4%**
  - SMA cross 在 TREND_DOWN 完全沒進場（0.0%）→ 長倉策略對空頭 regime 的暴露=0
  - BuyHold 的 +18.9% 幾乎全部來自 RANGE 段落的複合漂移，不是趨勢捕捉
- **含義**：§27 的假說「momentum 贏在突破、死在盤整」在 90 天資料上成立。
  Strategy Router（SPEC §5）的第一版規則呼之欲出：RANGE 時關閉動能類策略。
- **注意**：單一 90 天窗口、段數少（BREAKOUT 只有 2 段），統計力不足，
  僅作為方向性觀察；累積更多歷史後需重新驗證。

## 2026-08-22 · MeanRev「盤整反虧」疑點判定：不是參數問題

- **資料**：90 天 × 1H（2160 bars，同 `sweep-meanrev-1h` 群組 16 筆紀錄）
- **方法**：`marketlab sweep --strategy mean_reversion --param window=20,40,80,120 --param entry_z=1.5,2.0,2.5,3.0`
- **發現**：
  - **16/16 全數虧損**（−8.5% ~ −45.5%），無任何參數救援
  - 虧損與交易次數單調相關：392 筆 → −45.5%（成本 58.8%）；30 筆 → −8.5%（成本 4.5%）
    → 成本假說**部分成立**
  - 但最佳配置（window=120, entry_z=3.0）毛報酬仍約 −4% → 此窗口的 BTC 1H
    **均值回歸本身不成立**，不是參調問題
  - Arena 對比：最佳配置把 RANGE 段傷害從 −27.1%（預設參數）縮到 −4.1%，但沒有任何 regime 轉正
- **含義**：
  - §32 鐵律啟動——MeanRev 目前「沒有顯示比較好」，不得因理論漂亮而保留權重
  - 後續若再驗：換訊號構造（Bollinger %B / RSI）、maker-only 執行（Phase 21）、
    或等更長歷史確認是否為窗口特異性

