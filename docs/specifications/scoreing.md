---
title: スコア計算仕様書
document_id: SPEC-SCORE-001
version: 0.3.0
status: Reviewed
project: Project Atlas
author: Takatori Tatsuo
created: 2026-07-26
updated: 2026-11-20
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
- **弱気・リスク要因の減点・除外判定**: 下落転換パターン（`R002: DoubleTop`）、過度な当日ボラティリティスパイク（`tr_today / avg_atr >= 2.0` または `R001 <= 10.0`）、SMA75 からの過熱上方乖離（`+25%` 超）、および大幅ギャップアップ過熱（`+7%` 超）のペナルティ反映。
- **戦略別スコアの算出**:
  - **押し目買い戦略スコア (`PullbackStrategyScore`)**: 上昇トレンド × 押し目位置・反発確認 (`P001`) × 押し目帯 RSI ベル型評価 (`40〜60`)・`RSI5` 短期反転トリガー (`O001`) × 売り枯れ→反発出来高増 (`V001`) × VCP収縮・低リスク安定度 (`R001`) × 底打ち・反発パターン (`R001: DoubleBottom`, `Hammer`) × 財務補助点。
  - **ブレイクアウト戦略スコア (`BreakoutStrategyScore`)**: 上昇トレンド × 高値接近・突破・CLV (`P002`) × 出来高急増・蓄積 (`V001`) × ブレイク帯 RSI ベル型評価 (`55〜75`) (`O001`) × 財務補助点（大幅ギャップアップ・RSI80超過熱時は減点）。
- **ユニバース横断市場コンテキスト (`MarketContext`) の統合**:
  - 親プロセス側で基準日 `d` 以前のデータのみから構築した読み取り専用 `MarketContextModel` を受け取り、**対 TOPIX（`1306.T`）相対力（RSパーセンタイル順位、押し目買い戦略では正のRS過熱ブーストを `pullback_rs_positive_factor` で抑制）**、**33業種モメンタム**、**業種内相対バリュエーション（`PER`/`PBR`/`ROE` の Z スコア）** に基づく補正点（合計上限 `total_adjustment_cap`）を戦略別スコア（キャップ適用前）へ加算する。
  - **地合いレジーム判定（Market Breadth & TOPIX トレンド）**: ユニバースの `close > SMA25` 比率とベンチマーク位置（および極端 Breadth `< 35%` 二極化ガード）により `bearish` と判定された場合、ブレイクアウト戦略のみ要求エントリースコアを引き上げ（`breakout_threshold_delta`）およびブレイクアウト減点（`breakout_score_penalty`）を適用する。
- **代表スコアと推奨戦略タイプの決定**: 両戦略スコアのうち高い方をその銘柄の `total_score`（代表スコア）および `strategy_type`（`pullback` / `breakout` / `watch`）として決定。
- **後段AI連携用の価格水準・判断根拠メタデータの集約**: 各特徴量・指標が算出した現在値、移動平均線価格（SMA5/25/75）、直近20日高値・安値、ボラティリティ、市場コンテキスト詳細の集約と推奨理由の生成。

以下は責務としない。

- 個別Featureの算出および個別Patternの検出
- 並列ワーカープロセス内での複数銘柄横断集計（`MarketContext` 構築は親プロセス側の責務とする）
- 最終的な指値・逆指値注文の執行

---

## 4. 入力

- Feature Engineが出力した特徴量セット（`FeatureSetModel`）
- Pattern Detectorが検出したパターンセット（`PatternSetModel`）
- （任意）基準日断面のユニバース横断市場コンテキスト（`MarketContextModel`、`frozen=True`）
- スコアリング設定（各戦略の重み付け・閾値パラメータ・`MarketContextConfig`）

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
  - `rs_score` / `sector_momentum_score` / `relative_valuation_score` / `market_context_adjustment`: `MarketContext` 適用時のみ付与される相対力・業種モメンタム・業種内相対バリュエーション・適用補正点
- **AI連携用メタデータ・価格水準 (`metadata`)**:
  - `key_levels`: 現在終値 (`close`)、`sma5`, `sma25`, `sma75`、直近最高値 (`highest_high`)、直近最安値 (`lowest_low`)
  - `risk_metrics`: ボラティリティ比率、出来高倍率
  - `market_regime` / `market_breadth_ratio` / `breakout_threshold_delta` / `market_context`: `MarketContext` 適用時の地合いレジーム・補正内訳詳細
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
   - **補助**: ファンダメンタルズスコア（`F001〜F006`）、ボラティリティ安定度（`R001: VolatilityScore`）
2. **ブレイクアウト戦略スコア (`BreakoutStrategyScore`)**
   - **主軸**: `P002: BreakoutScore`（直近高値への接近〜上抜け初動）
   - **需給・勢い裏付け**: `V001: VolumeScore`（出来高急増）、`O001: MomentumScore`
   - **環境**: `M001: MAAlignmentScore`, `T001: TrendStrengthScore`
   - **補助**: ファンダメンタルズスコア（`F001〜F006`）、ボラティリティ評価（`R001: VolatilityScore`）

### 6.3 第3関門・MarketContext による相対軸補正と地合いレジーム制御
- **対 TOPIX 相対力（RS）**: 20日/60日/120日超過リターンの合成順位（`0〜100` パーセンタイル、欠損期間は利用可能期間で正規化）。押し目買い戦略では高β急騰株の短期反落を抑えるため正の RS 補正のみ `pullback_rs_positive_factor`（既定 `0.3`）で抑制し、負の RS 減点は全額維持する。
- **33業種モメンタム＆業種内相対バリュエーション**: `sector_33` 内の銘柄数が `min_sector_size`（既定 `5`）以上の場合のみ、業種平均20日リターン・`SMA25` 上回り率から業種モメンタムを評価し、同一業種内の対数 `PER`・対数 `PBR`・`ROE` の Z スコア平均（`[-2.5, +2.5]` クリップ）を加算する。`F003_ValuationScore` の絶対評価は変更せず補助補正として加算する。
- **地合いレジーム（Market Breadth）制御**: ユニバースの `close > SMA25` 比率が `breadth_bearish_threshold`（既定 `0.40`）未満かつベンチマーク `< SMA25`、または `breadth_severe_bearish_threshold`（既定 `0.35`）未満のとき `bearish` と判定し、`StrategyScoreCalculator`（ブレイクアウト減点＋要求スコア引き上げ）と `Screener`（ブレイクアウト抽出閾値引き上げ、二重加算なし）を一貫連動させる。

---

## 7. 例外処理

- 必須となるテクニカル特徴量（`M001`, `T001`, `P001`, `P002`）が欠損している日付・銘柄は評価不能としてスキップまたは0点とする。
- 財務データ欠損時はファンダメンタルズ補助スコアを中立（50点相当）として扱い、テクニカル評価のみで算出を継続できるようにする。
- Pattern未検出時は加点・減点ともに0として扱う。
- `MarketContext` 未指定時・`is_active=False` 時（最小ユニバース数 `min_universe_size` 未達など）・特徴量日付とコンテキスト基準日/バー日付の不一致時は、誤適用・先読みを防ぐため完全に無補正として計算する。また `min_sector_size` 未満の業種やベンチマーク `1306.T` 取得失敗時はそれぞれ中立（`0.0` 点）またはユニバース中央値リターンへ安全にフォールバックする。
- ランキング生成時（`RankingGenerator`）の基準日照合は原則当日厳密一致（`strict_date_match: true`）とし、過去日や別日の特徴量・パターンへの暗黙フォールバックを禁止する。

---

## 8. テスト観点

- スクリーニング全通過銘柄に対する特徴量別分位評価（上位20% vs 下位20%の +5 / +20 / +60 営業日勝率・平均リターン・MFE・MAE・スプレッド、および `MC_RS_Rank` / `MC_SectorMomentum` / `MC_RelativeValuation`）を `--mode evaluate` / `--mode backtest` で検証できること。
- `MarketContext` が基準日 `as_of_date` 厳密分離（未来バー改ざん不変）・少銘柄/少業種中立フォールバック・ベンチマーク欠損代替・`bearish` 地合い時のブレイクアウト戦略限定抑止・並列/逐次完全一致を満たすこと。

- 上昇トレンド中の押し目銘柄において、`PullbackStrategyScore` が高く算出され、推奨戦略が `"pullback"` となること。
- 高値接近・上抜けかつ出来高増加銘柄において、`BreakoutStrategyScore` が高く算出され、推奨戦略が `"breakout"` となること。
- 下降トレンド銘柄や `DoubleTop` 成立銘柄において、単一指標が良くても総合スコアが低く抑えられる（足切りされる）こと。
- 後段AI連携用の価格水準（`close`, `sma25`, `sma75`, `highest_high` 等）および推奨理由が結果に含まれること。
- 同一入力に対して常に同一スコアが算出されること。
