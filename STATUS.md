# STATUS.md — 開發進度與交接文件

> **給下一個開發者／AI Agent**：本檔記錄 MarketLab 的即時開發狀態。
> **規則：每次完成工作後必須更新此檔並一併 commit。**
> 需求來源：[docs/SPEC.md](docs/SPEC.md)（v0.2 規格，唯一真相）。
> 階段定義與勾選：[docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 快照（最後更新：2026-08-22）

| 項目 | 狀態 |
| --- | --- |
| 目前階段 | **Phase 0 ✅ Phase 1 ✅ Phase 2 ✅ 完成** |
| 下一步 | Phase 5 Experiment Lab（實驗記錄/比較）；Dashboard 接即時 WS；Phase 7 per-regime 績效矩陣 |
| 測試 | `71 passed`（pytest） |
| Lint | `ruff check` All checks passed |
| 實網驗證 | REST 分頁下載 2 天 1m K 線（2881 bars, 0 缺口）＋ WS 三頻道串流（ticker/trade/candle5m）＋ Streamlit 啟動 |
| Git | branch `main` → `github.com/xujk0217/MarketLab`（帳號：gh CLI 已登入 xujk0217） |

---

## 開發環境

* Windows 11 ＋ pwsh（PowerShell 7）。工作目錄：`C:\Users\許君愷\Developer\MarketLab`
* Python **3.12.10**（指令 `python`）；套件要求 `>=3.11`
* venv 在 `.venv/`（已 gitignore）。安裝：`.venv\Scripts\pip install -e ".[dev]"`
* 依賴刻意維持最小：`httpx / pandas / numpy / pydantic(≥2)`；dev：`pytest / ruff`
* ⚠️ PowerShell 陷阱：多行 `python -c "…"` 內含 `{}` 會被當 ScriptBlock 解析失敗。
  要跑多行腳本請寫到暫存檔再執行。

## 常用指令

```powershell
.venv\Scripts\python -m pytest        # 全部測試（期望：71 passed）
.venv\Scripts\python -m ruff check .  # lint（期望：All checks passed!）
.venv\Scripts\python -m marketlab --version   # CLI 煙霧測試

# 資料管線（真實網路）
.venv\Scripts\python -m marketlab download --inst BTC-USDT --bar 1m --days 2
.venv\Scripts\python -m marketlab normalize --inst BTC-USDT --bar 1m
.venv\Scripts\python -m marketlab report --inst BTC-USDT --bar 1m
.venv\Scripts\python -m marketlab live --seconds 10     # WS 三頻道即時串流

# Dashboard（從 repo 根目錄執行；需先有 normalized 資料）
.venv\Scripts\streamlit run app/dashboard.py
```

---

## 已完成：Phase 0 模組地圖

| 檔案 | 內容 | 規格出處 |
| --- | --- | --- |
| `src/marketlab/core/market_state.py` | `MarketState` 凍結 dataclass — Digital Twin 統一狀態向量，optional 欄位留給後續 phase 填充 | SPEC §18 |
| `src/marketlab/core/regime.py` | `RuleBasedRegimeDetector`：EVENT_SHOCK→BREAKOUT→TREND→VOLATILITY→RANGE 階梯式分類，輸出 `RegimeResult(regime, confidence)` | SPEC §3–4 |
| `src/marketlab/core/events.py` | `NewsEvent`(pydantic v2)、`EventType/Direction/Horizon/SourceTier` enum、`NEWS_EVENT_JSON_SCHEMA`（LLM 固定合約）、`effective_impact = impact×confidence×tier_weight` | SPEC §9–12 |
| `src/marketlab/data/okx/client.py` | `OKXPublicClient`：ticker / candles / **history-candles**（分頁游標）/ trades（僅公開端點），`transport=` 注入供 MockTransport 離線測試；business code ≠ "0" 時 raise `OKXError` | Phase 1 |
| `src/marketlab/data/okx/history.py` | `HistoryDownloader`：以 `after` 游標逐頁回溯抓取，停於短頁/起點；防停滯守衛 | Phase 2 |
| `src/marketlab/data/store.py` | 三層儲存：Raw 不可變批次 parquet + `normalize()`（去重/OHLC 驗證/缺口報告）+ normalized 快取讀寫 | Phase 2 |
| `src/marketlab/features/` | `build_features()`：log_return、realized_vol、volume_ratio、hl_range_pct、return_lag{N}（純 trailing window，無 lookahead） | Phase 2 |
| `src/marketlab/data/okx/ws.py` | `OKXWebSocketClient`：**雙端點並行**——tickers/trades 走 `/ws/v5/public`、candle 走 `/ws/v5/business`（預組合名稱如 `candle5m`）；指數退避重連＋20s 心跳；連線工廠可注入離線測試 | Phase 1 |
| `src/marketlab/__main__.py` | CLI 子命令：`download / normalize / report / live`（argparse） | Phase 1 |
| `app/dashboard.py` | Streamlit Dashboard v1：K線＋成交量圖、Regime 卡片與滾動時間軸、Features 線圖、資料健康摘要 | Phase 1 |
| `src/marketlab/strategies/` | `Strategy` ABC + BuyAndHold / SmaCross(fast,slow) / Momentum(lookback,deadband) / MeanReversion(window,entry_z)；訊號 ∈ {−1,0,+1} | Phase 3 |
| `src/marketlab/backtest/engine.py` | `run_backtest(prices, signals, config)`：下一根 K 執行、turnover 收 fee+slippage、產出 total/annualized return、Sharpe、max_drawdown、trades、exposure、total_cost | Phase 4 |
| `tests/` | 71 個測試：regime 合成校準、schema 驗證、backtest 已知值、防 lookahead 回歸、下載器分頁、資料層缺口、WS 重連流程 | — |
| `Dockerfile`、`.github/workflows/ci.yml` | python:3.12-slim 映像；CI＝ruff＋pytest，Python 3.11/3.12 matrix | Phase 0 |

---

## 不可違反的架構決策（改動前先讀）

1. **防 lookahead 是結構性的**：策略在 bar close 決策，引擎一律 `signals.shift(1)` 後才套用報酬。
   `tests/test_backtest.py::TestNoLookahead` 是回歸測試——動引擎必須保持它通過。
2. **LLM 不直接交易**（SPEC §8）：LLM 只能產出符合 `NEWS_EVENT_JSON_SCHEMA` 的結構化事件，
   一律經過 feature → model → strategy → risk 才可能變成訂單。
3. **Regime 閾值全是 constructor 參數**：為了 Phase 5 實驗比較，不要把魔術數字寫死在邏輯裡。
   `EVENT_SHOCK` 需要 `event_score`（目前恆 0，等 Phase 8–9 接上新聞層）。
4. **測試離線**：所有網路互動走 `httpx.MockTransport`，測試不得打真 API。
   真實 API 驗證用手動 smoke script（見下方）。
5. **Python ≥3.11 慣例**：enum 用 `StrEnum`（ruff UP042 會擋）、型別提示完整、`py.typed` 已放置。
6. **提交風格**：conventional commits（feat/fix/docs/chore/build/test），
   邏輯里程碑各自一個 commit（參考現有 log）。

---

## 驗證 SOP（每次改動後、commit 前）

```powershell
.venv\Scripts\python -m pytest && .venv\Scripts\python -m ruff check .
```

真實網路 smoke（手動、偶爾）：將以下內容存成暫存 .py 後用 `.venv\Scripts\python <file>` 執行：

```python
from marketlab.core.regime import RuleBasedRegimeDetector
from marketlab.data.okx import OKXPublicClient

with OKXPublicClient(timeout=15.0) as c:
    t = c.get_ticker("BTC-USDT")
    print(t["last"], t["timestamp"])
    k = c.get_candles("BTC-USDT", bar="5m", limit=300)
print(RuleBasedRegimeDetector().detect(k))
# 2026-08-22 實測：last=78560.9 → RANGE confidence=0.902
```

---

## 已知坑（踩過的）

* **OKX WS 雙端點**：candle 頻道在 `/ws/v5/business`（名稱預組合如 `candle5m`），
  tickers/trades 在 `/ws/v5/public`。訂錯端點會回 error 60018。客戶端已自動分流。
* **OKX REST 的 timestamp 是字串毫秒**——必須在 `_parse_candles` 統一轉 tz-aware UTC；
  下游所有程式碼都假設已是 Timestamp。
* `history-candles` 單次上限 **100** 根、`market/candles` 上限 300；分頁用 `after` 游標往過去走。
* WS 心跳：伺服器會送文字 `"ping"`，要回 `"pong"`；閒置 >30s 斷線。客戶端每 20s 主動送 ping。
* 年化報酬在「短視窗 × 極端報酬」會指數爆表：engine 已在 log 空間計算並 guard overflow（>709 → `inf`）。
* Windows git 的 LF/CRLF 警告可忽略（`.gitattributes` 已正規化）。
* Regime 合成測試（`tests/test_regime.py`）以固定 seed 校準閾值；
  改 detector 參數前先讀該檔的工程設計註記，避免誤判「測試壞了」。
* PowerShell 多行 `python -c "…"` 內含 `{}` 會解析失敗——寫暫存腳本執行。
* **Git 身份已設定**（repo-local：`xujunkai / 128728119+xujk0217@users.noreply.github.com`，
  noreply 格式會自動關聯 GitHub 帳號 xujk0217）。若在新機器 clone，請重新設定：
  ```powershell
  git config user.name "xujunkai"; git config user.email "128728119+xujk0217@users.noreply.github.com"
  ```

---

## 下一步待辦（照 ROADMAP 順序）

### Phase 3–4 補強
- [ ] `backtest` CLI 子命令（策略×參數×區間 → metrics 表）
- [ ] Portfolio / position sizing

### Phase 5 — Experiment Lab（下一個大目標）
- [ ] Run metadata 記錄（dataset 版本、strategy 版本、參數、metrics、git sha）
- [ ] 實驗比較報表（DataFrame/CSV 起步即可）

### Dashboard v2 候選
- [ ] 即時模式：dashboard 直接吃 WS tickers 更新價格卡
- [ ] Regime 時間軸與 K 線圖疊加背景色帶

### 再之後
Phase 7 Strategy Arena（per-regime 績效矩陣）→ Phase 8 Event Data Infra。

---

## 給 Agent 的交接流程

1. 讀 `docs/SPEC.md`（需求）→ 本檔（現況）→ `docs/ROADMAP.md`（勾進度）
2. 改程式 → 跑驗證 SOP → 全綠才 commit
3. 完成的項目：勾 ROADMAP checkbox、更新本檔「快照」區塊與待辦清單
4. 新增依賴、新增目錄、或違反上方「不可違反的決策」之前——先停下來說明理由
