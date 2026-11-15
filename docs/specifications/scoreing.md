---
title: スコア計算仕様書
document_id: SPEC-SCORE-001
version: 0.2.0
status: Reviewed
project: Project Atlas
author: Takatori Tatsuo
created: 2026-07-26
updated: 2026-11-15
related:
  - requirements/requirements.md
  - design/score_engine.md
  - specifications/features/feature_list.md
  - specifications/patterns/pattern_list.md
---

# スコア計算仕様書

## 1. 概要

Score Engineは、Feature Engineで算出した特徴量とPattern Detectorで検出したチャートパターンを統合し、スイングトレード（現物・買いエントリー）における**戦略別評価スコア（「押し目買い戦略スコア」および「ブレイクアウト戦略スコア」）**と**銘柄の代表スコア**を算出するモジュールである。

本仕様書では、3段階ゲート方式に基づく評価方針、戦略別スコアの責務、および出力仕様を定義する。

---

## 2. 目的

- 全特徴量の単純平均による「高値圏の伸び切り銘柄」と「エントリー適時銘柄」の混在を防ぎ、実際にプラスになりやすい買い候補銘柄を抽出する。
- 中長期の上昇トレンドを前提（第1関門）とした上で、「押し目買い型（Pullback）」と「ブレイクアウト型（Breakout）」の2大セットアップごとに最適な重み付け評価を行う。
- 後段のAI（またはトレーダー）が具体的な買値・損切りラインを判断できるよう、推奨戦略タイプ、判断根拠、および具体的なサポレジ価格水準・リスク指標を構造化して出力する。

---

## 3. 責務

Score Engineは以下を担当する。

- **第1関門（環境認識）の評価**: 中長期の上昇トレンド要件（`M001: MAAlignmentScore`, `T001: TrendStrengthScore`）およびファンダメンタルズ基礎点の評価。
- **弱気・リスク要因の減点・除外判定**: 下落転換パターン（`R002: DoubleTop`）や過度なボラティリティ（`R001: VolatilityScore` 低スコア時）のペナルティ反映。
- **戦略別スコアの算出**:
  - **押し目買い戦略スコア (`PullbackStrategyScore`)**: 上昇トレンド × 押し目位置 (`P001`) × モメンタム反転 (`O001`) × 底打ち・反発パターン (`R001: DoubleBottom`, `Hammer`) × 財務補助点。
  - **ブレイクアウト戦略スコア (`BreakoutStrategyScore`)**: 上昇トレンド × 高値接近・突破 (`P002`) × 出来高急増 (`V001`) × モメンタム (`O001`) × 財務補助点。
- **代表スコアと推奨戦略タイプの決定**: 両戦略スコアのうち高い方をその銘柄の `total_score`（代表スコア）および `strategy_type`（`pullback` / `breakout` / `watch`）として決定。
- **後段AI連携用の価格水準・判断根拠メタデータの集約**: 各特徴量・指標が算出した現在値、移動平均線価格（SMA5/25/75）、直近20日高値・安値、ボラティリティ等の集約と推奨理由の生成。

以下は責務としない。

- 個別Featureの算出および個別Patternの検出
- 最終的な指値・逆指値注文の執行

---

## 4. 入力

- Feature Engineが出力した特徴量セット（`FeatureSetModel`）
- Pattern Detectorが検出したパターンセット（`PatternSetModel`）
- スコアリング設定（各戦略の重み付け・閾値パラメータ）

---

## 5. 出力

`ScoreResultModel`（および後続の `AnalysisResultModel`）を通じて以下を出力する。

- **代表スコア (`total_score`)**: 0〜100（押し目買い戦略スコアとブレイクアウト戦略スコアの高い方）
- **推奨戦略タイプ (`strategy_type`)**: `"pullback"`（押し目買い型） / `"breakout"`（ブレイクアウト型） / `"watch"`（監視・条件未達）
- **サブスコア (`sub_scores`)**:
  - `pullback_strategy_score`: 押し目買い戦略スコア (0〜100)
  - `breakout_strategy_score`: ブレイクアウト戦略スコア (0〜100)
  - `trend_env_score`: トレンド環境サブスコア (0〜100)
  - `fundamental_score`: ファンダメンタルズ補助サブスコア (0〜100)
  - `penalty_score`: 弱気パターン・リスクによる減点幅
- **AI連携用メタデータ・価格水準 (`metadata`)**:
  - `key_levels`: 現在終値 (`close`)、`sma5`, `sma25`, `sma75`、直近最高値 (`highest_high`)、直近最安値 (`lowest_low`)
  - `risk_metrics`: ボラティリティ比率、出来高倍率
  - `reasons`: スコアに貢献した主な根拠リスト（例：`["中長期上昇トレンド(MA整列)", "25日線付近への理想的な押し目(+1.2%)", "ROE 15.2%と高収益"]`）

---

## 6. 評価方針（3段階ゲート＋戦略別スコア）

### 6.1 第1関門：トレンド環境認識（前提条件）
- スイングトレードの勝率・再現性を確保するため、`M001: MAAlignmentScore` と `T001: TrendStrengthScore` から算出されるトレンド環境スコアが基準閾値に満たない銘柄（下降トレンドや長期線割れ）は、戦略スコアに上限キャップ（または減衰係数）を適用し、推奨候補から除外できるようにする。
- `R002: DoubleTop` が高い信頼度で検出されている場合は、買いエントリーの危険シグナルとして減点または除外対象とする。

### 6.2 第2・第3関門：2つの買い戦略別スコアの算出
1つの銘柄が同時に「押し目」かつ「高値ブレイク」になることはないため、以下の2つの戦略スコアを独立に算出し、`max(PullbackStrategyScore, BreakoutStrategyScore)` を代表スコアとする。

1. **押し目買い戦略スコア (`PullbackStrategyScore`)**
   - **主軸**: `P001: PullbackScore`（中期MA付近への調整度合い）
   - **環境**: `M001: MAAlignmentScore`, `T001: TrendStrengthScore`
   - **タイミング・反発裏付け**: `O001: MomentumScore`（売られすぎからの反転）、`R001: DoubleBottom` / `Hammer`（下値サポート確認）
   - **補助**: ファンダメンタルズスコア（`F001〜F005`）、ボラティリティ安定度（`R001: VolatilityScore`）
2. **ブレイクアウト戦略スコア (`BreakoutStrategyScore`)**
   - **主軸**: `P002: BreakoutScore`（直近高値への接近〜上抜け初動）
   - **需給・勢い裏付け**: `V001: VolumeScore`（出来高急増）、`O001: MomentumScore`
   - **環境**: `M001: MAAlignmentScore`, `T001: TrendStrengthScore`
   - **補助**: ファンダメンタルズスコア（`F001〜F005`）、ボラティリティ評価（`R001: VolatilityScore`）

---

## 7. 例外処理

- 必須となるテクニカル特徴量（`M001`, `T001`, `P001`, `P002`）が欠損している日付・銘柄は評価不能としてスキップまたは0点とする。
- 財務データ欠損時はファンダメンタルズ補助スコアを中立（50点相当）として扱い、テクニカル評価のみで算出を継続できるようにする。
- Pattern未検出時は加点・減点ともに0として扱う。

---

## 8. テスト観点

- 上昇トレンド中の押し目銘柄において、`PullbackStrategyScore` が高く算出され、推奨戦略が `"pullback"` となること。
- 高値接近・上抜けかつ出来高増加銘柄において、`BreakoutStrategyScore` が高く算出され、推奨戦略が `"breakout"` となること。
- 下降トレンド銘柄や `DoubleTop` 成立銘柄において、単一指標が良くても総合スコアが低く抑えられる（足切りされる）こと。
- 後段AI連携用の価格水準（`close`, `sma25`, `sma75`, `highest_high` 等）および推奨理由が結果に含まれること。
- 同一入力に対して常に同一スコアが算出されること。
