# 特徴量とパターンの追加計画

## 1. 概要
この計画書は、`docs/_plan.md` の「フェーズ2: 機能拡張と改善」における「特徴量とパターンの追加」タスクを実行するための詳細な作業計画です。`docs/specifications/feature_list.md` と `docs/specifications/patterns/pattern_list.md` に基づき、優先度の高い特徴量とパターンから順次実装を進めます。

## 2. 完了条件
- `docs/specifications/feature_list.md` に記載されている全てのP1優先度の特徴量が実装され、対応する単体テストが成功すること。
- `docs/specifications/patterns/pattern_list.md` に記載されている全てのP1優先度のパターンが実装され、対応する単体テストが成功すること。
- 追加された特徴量とパターンが `src/feature_engine/registry.py` および `src/pattern_detector/registry.py` に適切に登録されていること。
- `docs/_plan.md` の「フェーズ2: 機能拡張と改善」の該当項目が完了済みに更新されること。
- `work/reflection.md` に、実装中に発見された改善点や課題が記録されていること。

## 3. 実装計画

### 3.1. 特徴量 (`Feature`) の追加
`docs/specifications/feature_list.md` より、以下のP1優先度の特徴量を実装します。

- [x] **M001: MAAlignmentScore (移動平均線の並び評価)**
    - 完了条件:
        - `src/feature_engine/features/moving_average/ma_alignment_score.py` を新規作成し、`IFeature` インターフェースを実装する。
        - 移動平均線の並び（例: 短期 > 中期 > 長期）に基づいてスコアを算出するロジックを実装する。
        - `src/feature_engine/registry.py` に登録する。
        - `tests/unit/feature_engine/test_ma_alignment_score.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **P001: PullbackScore (押し目の理想度)**
    - 完了条件:
        - `src/feature_engine/features/price_action/pullback_score.py` を新規作成し、`IFeature` インターフェースを実装する。
        - 押し目の理想度を評価するロジックを実装する。
        - `src/feature_engine/registry.py` に登録する。
        - `tests/unit/feature_engine/price_action/test_pullback_score.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **P002: BreakoutScore (ブレイクアウトの強さ)**
    - 完了条件:
        - `src/feature_engine/features/price_action/breakout_score.py` を新規作成し、`IFeature` インターフェースを実装する。
        - ブレイクアウトの強さを評価するロジックを実装する。
        - `src/feature_engine/registry.py` に登録する。
        - `tests/unit/feature_engine/price_action/test_breakout_score.py` を新規作成し、単体テストを実装・実行し、成功することを確認する.
        - `docs/_plan.md` と本計画書を更新する。

- [x] **T001: TrendStrengthScore (トレンド強度)**
    - 完了条件:
        - `src/feature_engine/features/trend.py` に `TrendStrengthScore` を実装する。
        - 移動平均線の並び、傾き、株価位置、高値・安値を総合的にスコア化する。
        - `tests/unit/feature_engine/trend/test_trend_strength_score.py` に単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **V001: VolumeScore (出来高評価)**
    - 完了条件:
        - `src/feature_engine/features/volume/volume_score.py` を新規作成し、`IFeature` インターフェースを実装する。
        - 出来高の急増、出来高移動平均の短期トレンド、株価方向との整合性をスコア化する。
        - `tests/unit/feature_engine/volume/test_volume_score.py` に単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **O001: MomentumScore (モメンタム評価)**
    - 完了条件:
        - `src/feature_engine/features/oscillator/momentum_score.py` を新規作成し、`IFeature` インターフェースを実装する。
        - RSIとMACDの挙動を組み合わせて売買エネルギーや勢いをスコア化する。
        - `tests/unit/feature_engine/oscillator/test_momentum_score.py` に単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **R001: VolatilityScore (ボラティリティ評価)**
    - 完了条件:
        - `src/feature_engine/features/risc/volatility_score.py` を新規作成し,`IFeature` インターフェースを実装する。
        - 過去の平均値動き(ATR)に対する現在の値動き(True Range)の比率をスコア化する。
        - `tests/unit/feature_engine/risc/test_volatility_score.py` に単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **F001: ProfitabilityScore (収益性評価)**
    - 完了条件:
        - `src/feature_engine/features/fundamental/profitability_score.py` を新規作成し、`IFeature` を実装。
        - ROE, ROA, 営業利益率をスコア化する。
        - `tests/unit/feature_engine/fundamental/test_profitability_score.py` にて単体テストを実行・成功を確認。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **F002: GrowthScore (成長性評価)**
    - 完了条件:
        - `src/feature_engine/features/fundamental/growth_score.py` を新規作成し、`IFeature` を実装。
        - 3年/5年平均売上高・純利益成長率をスコア化する。
        - `tests/unit/feature_engine/fundamental/test_growth_score.py` にて単体テストを実行・成功を確認。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **F003: ValuationScore (割安性評価)**
    - 完了条件:
        - `src/feature_engine/features/fundamental/valuation_score.py` を新規作成し、`IFeature` を実装。
        - PER, PBRをスコア化する。
        - `tests/unit/feature_engine/fundamental/test_valuation_score.py` にて単体テストを実行・成功を確認。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **F004: FinancialHealthScore (財務健全性評価)**
    - 完了条件:
        - `src/feature_engine/features/fundamental/financial_health_score.py` を新規作成し、`IFeature` を実装。
        - BPS/EPSおよび営業利益・純利益の安定性をスコア化する。
        - `tests/unit/feature_engine/fundamental/test_financial_health_score.py` にて単体テストを実行・成功を確認。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **F005: EarningsQualityScore (利益の質評価)**
    - 完了条件:
        - `src/feature_engine/features/fundamental/earnings_quality_score.py` を新規作成し、`IFeature` を実装。
        - 営業利益と純利益の整合性およびレバレッジの健全性をスコア化する。
        - `tests/unit/feature_engine/fundamental/test_earnings_quality_score.py` にて単体テストを実行・成功を確認。
        - `docs/_plan.md` と本計画書を更新する。

### 3.2. パターン (`Pattern`) の追加
`docs/specifications/patterns/pattern_list.md` より、以下のP1優先度のパターンを実装します。

- [x] **R001: DoubleBottom (ダブルボトム)**
    - 完了条件:
        - `src/pattern_detector/patterns/reversal/double_bottom.py` を新規作成し、`IPattern` インターフェースを実装する。
        - ダブルボトムパターンを検出するロジックを実装する。
        - `src/pattern_detector/registry.py` に登録する。
        - `tests/unit/pattern_detector/test_double_bottom.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [x] **R002: DoubleTop (ダブルトップ)**
    - 完了条件:
        - `src/pattern_detector/patterns/reversal/double_top.py` を新規作成し、`IPattern` インターフェースを実装する。
        - ダブルトップパターンを検出するロジックを実装する。
        - `src/pattern_detector/registry.py` に登録する。
        - `tests/unit/pattern_detector/test_double_top.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

## 4. 実行ログ
- 2026/08/23: `M001: MAAlignmentScore` の実装と対応する単体テストの調整・作成が完了しました。
- 2026/08/23: `P001: PullbackScore` の実装、および対応する単体テストの作成が完了しました。すべてのテストケースがパスすることを確認。
- 2026/08/23: 新規ブランチ `feat/P002-breakout-score` にて `P002: BreakoutScore` の実装、および対応する単体テスト of 作成が完了しました。すべてのテストケースがパスすることを確認。
- 2026/08/23: まとめブランチ `feat/technical-features-pack` にて `T001: TrendStrengthScore` の実装、および対応する単体テストの作成が完了しました。
- 2026/08/23: まとめブランチ `feat/technical-features-pack` にて `V001: VolumeScore` の実装、および対応する単体テスト of 作成が完了しました。
- 2026/08/23: まとめブランチ `feat/technical-features-pack` にて `O001: MomentumScore` の実装、および対応する単体テスト of 作成が完了しました.
- 2026/08/23: まとめブランチ `feat/technical-features-pack` にて `R001: VolatilityScore` の実装、および対応する単体テスト of 作成が完了しました。これでテクニカル特徴量一括パックの実装がすべて完了。
- 2026/08/23: まとめブランチ `feat/fundamental-features-pack` にて、F001（収益性）、F002（成長性）、F003（割安性）、F004（財務健全性）、F005（利益の質）の5つのファンダメンタルズ特徴量と対応する単体テストをすべて実装完了しました。
- 2026/08/23: まとめブランチ `feat/reversal-patterns-pack` にて、R001（ダブルボトム）、R002（ダブルトップ）の2つの転換チャートパターン検出モジュールと、対応する単体テストをすべて実装完了しました。

## 5. 改善点・課題 (work/reflection.mdに詳細を記載)
- (ここに実装中に見つかった改善点や課題の概要を記載します。詳細は `work/reflection.md` を参照してください)
