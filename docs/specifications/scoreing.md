---
title: スコア計算仕様書
document_id: SPEC-SCORE-001
version: 0.1.0
status: Draft
project: Project Atlas
author: Takatori Tatsuo
created:
updated:
related:
  - requirements/requirements.md
  - design/score_engine.md
  - specifications/feature_list.md
  - specifications/pattern_list.md
---

# スコア計算仕様書

## 1. 概要

Score Engineは、Feature Engineで算出した特徴量とPattern Detectorで検出したチャートパターンを統合し、銘柄の総合評価スコアを算出するモジュールである。

本仕様書では、スコアリングの目的、責務、および評価方針を定義する。実際の計算式、重み付け、アルゴリズムの詳細は設計書で管理する。

---

## 2. 目的

- FeatureとPatternを統合して総合評価を行う。
- 売買判断に利用できるランキングスコアを算出する。
- 評価ロジックをScore Engineへ集約し、FeatureおよびPatternとの責務を明確に分離する。

---

## 3. 責務

Score Engineは以下を担当する。

- Featureの評価
- Patternの評価
- Feature同士の組み合わせ評価
- Pattern同士の組み合わせ評価
- FeatureとPatternを組み合わせた評価
- 評価カテゴリごとのサブスコアの算出
- 総合スコアの算出
- ランキング用スコアの出力

以下は責務としない。

- Featureの算出
- Patternの検出
- 売買注文の実行

---

## 4. 入力

- Feature Engineが出力した特徴量
- Pattern Detectorが検出したパターン
- スコアリング設定

---

## 5. 出力

- 総合スコア
- 評価カテゴリごとのサブスコア
- ランキング用スコア

サブスコアは評価カテゴリごとの評価結果を表す。

例：

Feature例

- TrendStrengthScore
- MAAlignmentScore
- PullbackScore
- BreakoutScore
- VolumeScore
- MomentumScore
- SupportResistanceScore
- VolatilityScore
- Fundamental Features

サブスコアの構成、計算方法、重み付け、および評価カテゴリの詳細は設計書で管理する。

---

## 6. 評価方針

Score Engineは単一の特徴量ではなく、複数のFeatureおよびPatternを総合的に評価する。

FeatureおよびPatternは評価カテゴリごとに集約され、各カテゴリのサブスコアを算出する。

算出されたサブスコアを統合し、最終的な総合スコアを算出する。

例：

- TrendStrengthが高い
- ダブルボトムを形成している
- 移動平均線付近まで調整している
- 出来高が適切である

これらを総合的に評価し、「押し目買いに適した銘柄である」と判断する。

投資判断はScore Engineが担当し、FeatureおよびPatternは判断材料を提供する役割とする。

サブスコアおよび総合スコアの詳細な計算式、重み付け、正規化方法は設計書で定義する。

---

## 7. スコアリング対象

- トレンド
- 押し目
- ブレイクアウト
- 反転
- 出来高
- モメンタム
- ボラティリティ
- リスク

詳細な評価項目は別途設計書で管理する。

---

## 8. 例外処理

- Feature不足時は評価不能とする項目を定義する。
- Pattern未検出時は該当評価を行わない。
- 必須データ不足時はスコアを算出しない。

---

## 9. テスト観点

- Featureのみで評価できること
- Patternのみで評価できること
- FeatureとPatternを組み合わせて評価できること
- 各評価項目が期待どおりに反映されること
- 同一入力で同一スコアが算出されること

---

## 10. 今後の拡張

- 相場環境に応じた重み付けの切り替え
- 投資スタイル別スコアリング
- AIによるパラメータ最適化
- バックテスト結果を反映した重みの改善