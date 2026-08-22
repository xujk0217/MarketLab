# STATUS.md — 開發進度與交接文件

> **給下一個開發者／AI Agent**：本檔記錄 MarketLab 的即時開發狀態。
> **規則：每次完成工作後必須更新此檔並一併 commit。**
> 需求來源：[docs/SPEC.md](docs/SPEC.md)（v0.2 規格，唯一真相）。
> 階段定義與勾選：[docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 快照（最後更新：2026-08-22）

| 項目 | 狀態 |
| --- | --- |
| 目前階段 | **Phase 0 Foundation ✅ 完成** |
| 下一步 | Phase 1 BTC Market Explorer（WebSocket + 歷史下載）→ Phase 2 三層資料 |
| 測試 | `41 passed`（pytest, 0.6s） |
| Lint | `ruff check` All checks passed |
| 實網驗證 | OKX 公開 API 端到端已通（ticker + 300 根 5m K 線 + Regime 判定） |
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
.venv\Scripts\python -m pytest        # 全部測試（期望：41 passed）
.venv\Scripts\python -m ruff check .  # lint（期望：All checks passed!）
.venv\Scripts\python -m marketlab     # CLI 煙霧測試（印出版本）
```

---

## 已完成：Phase 0 模組地圖

| 檔案 | 內容 | 規格出處 |
| --- | --- | --- |
| `src/marketlab/core/market_state.py` | `MarketState` 凍結 dataclass — Digital Twin 統一狀態向量，optional 欄位留給後續 phase 填充 | SPEC §18 |
| `src/marketlab/core/regime.py` | `RuleBasedRegimeDetector`：EVENT_SHOCK→BREAKOUT→TREND→VOLATILITY→RANGE 階梯式分類，輸出 `RegimeResult(regime, confidence)` | SPEC §3–4 |
| `src/marketlab/core/events.py` | `NewsEvent`(pydantic v2)、`EventType/Direction/Horizon/SourceTier` enum、`NEWS_EVENT_JSON_SCHEMA`（LLM 固定合約）、`effective_impact = impact×confidence×tier_weight` | SPEC §9–12 |
| `src/marketlab/data/okx/client.py` | `OKXPublicClient`：ticker / candles / trades（僅公開端點），`transport=` 注入供 MockTransport 離線測試；business code ≠ "0" 時 raise `OKXError` | Phase 1 |
| `src/marketlab/strategies/` | `Strategy` ABC + BuyAndHold / SmaCross(fast,slow) / Momentum(lookback,deadband) / MeanReversion(window,entry_z)；訊號 ∈ {−1,0,+1} | Phase 3 |
| `src/marketlab/backtest/engine.py` | `run_backtest(prices, signals, config)`：下一根 K 執行、turnover 收 fee+slippage、產出 total/annualized return、Sharpe、max_drawdown、trades、exposure、total_cost | Phase 4 |
| `tests/` | 41 個測試：regime 合成資料校準、schema 驗證、backtest 已知值、防 lookahead 回歸測試、OKX MockTransport | — |
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

* **OKX candles 回傳 newest-first**，client 已排序成 ascending——別在別處再排一次。
* `/api/v5/market/candles` 單次上限 **300** 根；更久歷史要用 `/api/v5/market/history-candles`
  配 `after`/`before` 分頁（Phase 1 待辦）。
* 年化報酬在「短視窗 × 極端報酬」會指數爆表：engine 已在 log 空間計算並 guard overflow（>709 → `inf`）。
* Windows git 會印 `LF will be replaced by CRLF` 警告——已有 `.gitattributes` 正規化，可忽略。
* Regime 合成測試（`tests/test_regime.py`）以固定 seed 校準閾值；
  改 detector 參數前先讀該檔的工程設計註記，避免誤判「測試壞了」。
* **Git 身份已設定**（repo-local：`xujunkai / 128728119+xujk0217@users.noreply.github.com`，
  noreply 格式會自動關聯 GitHub 帳號 xujk0217）。若在新機器 clone，請重新設定：
  ```powershell
  git config user.name "xujunkai"; git config user.email "128728119+xujk0217@users.noreply.github.com"
  ```

---

## 下一步待辦（照 ROADMAP 順序）

### Phase 1 — BTC Market Explorer
- [ ] OKX WebSocket 公開頻道訂閱（`tickers` / `trades` / `candle5m`），斷線自動重連
- [ ] 歷史 K 線下載腳本：`history-candles` 分頁 → `data/raw/*.parquet`（immutable）
- [ ] Dashboard v1（先簡單：Streamlit 或 CLI 報表皆可，討論後再選）

### Phase 2 — Historical Data 三層
- [ ] Raw 層落盤格式與命名慣例（UTC、instId、interval）
- [ ] Normalized 層：統一 schema + 缺口檢查
- [ ] Feature 層：returns / realized vol / volume features（pandas 向量實作）

### 再之後
Phase 3–4 已有基礎版（四策略＋回測引擎），接著補 CLI 入口與參數化；
然後 Phase 5 Experiment Lab（run metadata + metrics 比較）。

---

## 給 Agent 的交接流程

1. 讀 `docs/SPEC.md`（需求）→ 本檔（現況）→ `docs/ROADMAP.md`（勾進度）
2. 改程式 → 跑驗證 SOP → 全綠才 commit
3. 完成的項目：勾 ROADMAP checkbox、更新本檔「快照」區塊與待辦清單
4. 新增依賴、新增目錄、或違反上方「不可違反的決策」之前——先停下來說明理由
