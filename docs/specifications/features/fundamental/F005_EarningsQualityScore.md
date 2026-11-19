---
title: EarningsQualityScore
document_id: SPEC-FEATURE-F005
version: 0.2.0
status: Implemented
project: Project Atlas
feature_id: F005
category: Fundamental
updated: 2026-11-19
related:
  - specifications/feature_list.md
  - design/feature_engine.md
---

# EarningsQualityScore

## 1. 概要
- Feature ID：`F005_EarningsQualityScore`
- Feature名：EarningsQualityScore
- 日本語名：利益の質スコア
- カテゴリ：Fundamental
- バージョン：0.2.0
- ステータス：Implemented
- 優先度：P2

## 2. 目的
- 会計上の純利益に対する営業キャッシュフローの裏付け（アクルーアルズ品質）、フリーキャッシュフロー創出力、営業CFマージン、日本の実効税率水準に適合した利益整合性、およびレバレッジ健全性を多軸で評価する。

## 3. 入力
- 入力データ（`FinancialModel`）:
  - CF: `operating_cf`, `capex`, `free_cash_flow`, `operating_cf_margin`
  - BS/PL: `total_assets`, `revenue`, `operating_profit`, `ordinary_profit`, `net_profit`, `roe`, `roa`

## 4. 出力
- `score`: `0.0〜100.0`（正規化スコア）
- `metadata`: `operating_cf`, `free_cash_flow`, `operating_cf_margin`, `cf_to_net_profit`, `fcf_to_assets`, `net_profit_to_operating_profit_ratio`, `roe_to_roa_ratio`, `available_weight`

## 5. アルゴリズム・配点バランス
取得可能な項目のウェイト合計で再配分する（`(weighted_sum / weight_sum) * 100.0`）。

1. **アクルーアルズ / 営業CF裏付け（ウェイト 35.0）**
   - `net_profit > 0` のとき `cf_to_net_profit = operating_cf / net_profit` を算出：`<= 0.0` で `0.0`、`0.0〜0.8` で `5.0〜25.0`、`0.8〜1.2` で `25.0〜35.0`、`>= 1.2` で `35.0`。
   - `net_profit <= 0` のとき `operating_cf > 0` なら `15.0`、それ以外は `0.0`。
2. **フリーキャッシュフロー創出力（ウェイト 25.0）**
   - `free_cash_flow` 欠損時は `operating_cf - abs(capex)` でフォールバック（IR BANK の `capex` 負値表現に対応）。
   - `total_assets > 0` 時は `fcf / total_assets`（`-0.05〜+0.10` → `0.0〜25.0`）、無ければ `fcf / revenue`（`-0.05〜+0.15` → `0.0〜25.0`）、双方欠損時は正負二値（`20.0` / `5.0`）。
3. **営業CFマージン（ウェイト 15.0）**
   - `operating_cf_margin`（欠損時は `(operating_cf / revenue) * 100`）を `-10%〜0%`（`0.0〜3.0`）および `0%〜20%`（`3.0〜15.0`）で評価。
4. **本業利益と最終利益の整合性（ウェイト 15.0）**
   - 基準利益は `operating_profit` とし、金融業等で `operating_profit` が欠損または `<= 0` の場合は `ordinary_profit > 0` を代替利用する。
   - `profit_ratio = net_profit / base_profit` の理想帯を日本の実効税率水準に合わせた **`0.60〜0.80`（満点 15.0）** とし、特別利益過多（`> 1.00`）や特別損失過大（`< 0.45`）は段階的に減点する。
5. **レバレッジ健全性（ウェイト 10.0）**
   - `leverage = roe / roa`（`roa > 0` 時）：`1.0〜2.5` を理想（`10.0`）とし、`> 2.5` は過大レバレッジとして減点する。

## 6. 例外処理・フォールバック
- `financial_data is None` または全軸算出不能（`weight_sum == 0`）時は中立 `50.0` を返す。
- 非有限値（`NaN` / `inf`）は欠損（`None`）として安全に除外する。
