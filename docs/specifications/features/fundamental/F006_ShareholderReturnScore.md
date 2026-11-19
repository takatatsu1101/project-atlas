---
title: ShareholderReturnScore
document_id: SPEC-FEATURE-F006
version: 0.1.0
status: Implemented
project: Project Atlas
feature_id: F006
category: Fundamental
created: 2026-11-19
updated: 2026-11-19
related:
  - specifications/feature_list.md
  - specifications/scoreing.md
---

# ShareholderReturnScore

## 1. 概要
- Feature ID：`F006_ShareholderReturnScore`
- Feature名：ShareholderReturnScore
- 日本語名：株主還元スコア
- カテゴリ：Fundamental
- バージョン：0.1.0
- ステータス：Implemented
- 優先度：P2

## 2. 目的
- 企業の株主還元姿勢を「連続増配・非減配モメンタム」「総還元性向／配当性向バランス」「自社株買いの実績・継続性」「純資産配当率（DOE）」の 4 軸から定量評価し、持続的な株主価値還元企業を高く評価するとともに、無理なタコ足配当や赤字配当を減点する。

## 3. 入力
- 入力データ（`FinancialModel`）:
  - 単期配当指標：`dividend_per_share`, `total_dividends`, `share_buyback`, `payout_ratio`, `total_payout_ratio`, `doe`, `net_profit`
  - 複数年モメンタム：`consecutive_dividend_increase_years`, `consecutive_non_decrease_years`, `buyback_count_3y`

## 4. 出力
- `score`: `0.0〜100.0`（正規化スコア）
- `metadata`: `dividend_per_share`, `share_buyback`, `payout_ratio`, `total_payout_ratio`, `doe`, `consecutive_dividend_increase_years`, `consecutive_non_decrease_years`, `buyback_count_3y`, `available_weight`

## 5. アルゴリズム・配点バランス
取得可能な項目のウェイト合計で再配分する（`(weighted_sum / weight_sum) * 100.0`）。

1. **連続増配・非減配モメンタム（ウェイト 35.0）**
   - 連続増配年数 `>= 1` のとき `0〜5年` を `15.0〜35.0` で連続評価（株式分割に伴う 1 株配当の見かけ上の減少は `total_dividends` 比較で事前補正済み）。
   - 連続増配 `0` 年時は連続非減配年数を `5.0〜18.0` で評価。
   - 複数年履歴が無い場合は当期配当有無（`17.5` / `3.0`）で評価。
2. **総還元性向・配当性向バランス（ウェイト 30.0）**
   - `total_payout_ratio`（欠損時は `payout_ratio`）を使用。
   - 適正帯 `30%〜60%` を満点（`30.0`）、`60%〜75%` を `25.0〜30.0`、`0%〜30%` を `3.0〜30.0` とし、`> 100%`（タコ足配当リスク）および `< 0%`（赤字配当）は大きく減点（`< 0%` は `0.0`）。
3. **自社株買い実績・継続性（ウェイト 20.0）**
   - 当期 `share_buyback > 0` の場合、基本 `10.0`＋対純利益還元比率（最大 `5.0`）＋直近 3 期実施回数 `buyback_count_3y`（最大 `5.0`）。
   - 当期未実施でも直近 3 期内に実施実績があれば継続性に応じて `4.0〜12.0`、完全未実施は `4.0`。
4. **純資産配当率 DOE（ウェイト 15.0）**
   - `0%〜5%` を `0.0〜15.0`、`5%〜8%` を満点（`15.0`）とし、`> 8%`（過剰還元）および `< 0%` は段階減点。

## 6. 例外処理・フォールバック
- `financial_data is None`、または株主還元関連 9 フィールドがすべて `None`（非有限値含む）の場合は中立 `50.0` を返す。
- 非有限値（`NaN` / `inf`）は欠損（`None`）として安全に除外する。
