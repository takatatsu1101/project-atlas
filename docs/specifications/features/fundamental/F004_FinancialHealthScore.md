---
title: FinancialHealthScore
document_id: SPEC-FEATURE-F004
version: 0.2.0
status: Implemented
project: Project Atlas
feature_id: F004
category: Fundamental
updated: 2026-11-19
related:
  - specifications/feature_list.md
  - design/feature_engine.md
---

# FinancialHealthScore

## 1. 概要
- Feature ID：`F004_FinancialHealthScore`
- Feature名：FinancialHealthScore
- 日本語名：財務健全性スコア
- カテゴリ：Fundamental
- バージョン：0.2.0
- ステータス：Implemented
- 優先度：P2

## 2. 目的
- 企業の財務健全性を「自己資本比率」「ネットキャッシュ比率」「有利子負債／利益剰余金バランス」の多段階・連続評価で定量化し、定数化を解消して実質的な財務余力・安全性を識別する。

## 3. 入力
- 入力データ（`FinancialModel`）:
  - BS: `equity_ratio`, `total_assets`, `short_term_debt`, `long_term_debt`, `retained_earnings`, `shareholders_equity`, `net_assets`
  - CF: `cash_and_equivalents`
  - レガシーフォールバック用: `eps`, `bps`, `operating_profit`, `net_profit`

## 4. 出力
- `score`: `0.0〜100.0`（正規化スコア）
- `metadata`: `equity_ratio`, `total_assets`, `cash_and_equivalents`, `interest_bearing_debt`, `net_cash_ratio`, `retained_earnings_ratio`, `debt_to_equity`, `available_weight`

## 5. アルゴリズム・配点バランス
取得可能な項目のウェイト合計で再配分する（`(weighted_sum / weight_sum) * 100.0`）。

1. **自己資本比率（ウェイト 40.0）**
   - `equity_ratio`（%）を `10% → 0.0`、`75% → 40.0` の範囲で連続線形評価。
2. **ネットキャッシュ比率（ウェイト 40.0）**
   - `cash_and_equivalents`・`total_assets > 0` が揃い、かつ `short_term_debt` または `long_term_debt` の少なくとも一方が非 `None` 有限値の場合に限り、`interest_bearing_debt = (short_term_debt or 0.0) + (long_term_debt or 0.0)`、`net_cash_ratio = (cash_and_equivalents - interest_bearing_debt) / total_assets` を算出。
   - `-0.40 → 0.0`、`+0.40 → 40.0` の範囲で連続線形評価。
   - 短期・長期借入金が双方 `None` の銘柄（銀行・借入金明細非開示企業など）では有利子負債 `0` と見なさず欠損扱いとし、取得可能項目へウェイトを再配分する。
3. **有利子負債 / 利益剰余金健全性（ウェイト 20.0）**
   - **利益剰余金比率**: `retained_earnings / total_assets` を `-0.10 〜 +0.60` で `0.0 〜 1.0` に正規化。
   - **D/E レシオ**: `interest_bearing_debt / (shareholders_equity or net_assets)` を `2.0 〜 0.0` で `0.0 〜 1.0` に正規化（債務超過 `<= 0` は `0.0`）。
   - 算出可能なサブ指標の平均 × `20.0`。

## 6. 例外処理・フォールバック
- `financial_data is None` の場合は中立 `50.0` を返す。
- 上記 3 軸がすべて算出不能（`weight_sum == 0`）の場合のみ、レガシー 4 項目（`eps`, `bps`, `operating_profit`, `net_profit`）による簡易判定へフォールバックし、それも欠損していれば `50.0` を返す。
- 非有限値（`NaN` / `inf`）は欠損（`None`）として安全に除外する。
