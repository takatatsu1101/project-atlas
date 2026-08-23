# Project Atlas 開発計画

## 1. 概要
このドキュメントは、Project Atlas の開発計画を管理します。各タスクのステータス、実施内容、および改善点を記録します。開発は以下のワークフローに従います。

**開発ワークフロー:**
- 完了条件の設定
- 実装
- テスト
- レビュー
- 資料修正
- 計画書更新
- 改善点がないか検討

## 2. プロジェクトの全体像とドキュメント構造

Project Atlas は、スイングトレード向けの株式分析支援システムです。東京証券取引所に上場する銘柄を対象に、テクニカル指標、チャートパターン、およびファンダメンタルズを統合的に評価し、有望な銘柄をスコアリングして抽出することを目的としています。

本システムは、データの取得から分析、スコアリング、結果表示までを、責務ごとに分離したモジュール構造（モジュラー・モノリス）で構築されています。

### 主要コンポーネント
- **Data Collector**: 市場データ（OHLCV）や財務データの取得・保存を担当。
- **Indicator Calculator**: テクニカル指標（MA, RSI等）の計算を担当。
- **Feature Engine**: 指標や生データを基にした市場・企業の特性（特徴量）の定量化を担当。
- **Pattern Detector**: チャートパターン（ダブルボトム等）の検出を担当。
- **Score Engine**: 特徴量とパターン検出結果を統合し、最終的なスコアを算出。
- **Screener / Ranking**: スコアに基づいた銘柄の絞り込みと順位付け。
- **Presentation**: 分析結果をユーザーに提示（CLI/将来的なGUI）。

ドキュメントは、目的別に以下の3つのカテゴリに分かれています。

- **要件定義 (Requirements)**: プロジェクトの背景、目的、およびシステムが実現すべき機能を定義しています。
    - [要件定義書](requirements/requirements.md)
- **仕様 (Specifications)**: 「何を」評価・検出するかという具体的なロジックや対象を定義しています。
    - [特徴量一覧](specifications/feature_list.md)
    - [パターン一覧](specifications/pattern_list.md)
    - [指標仕様](specifications/indicators.md)
    - [スコアリング仕様](specifications/scoreing.md)
- **設計 (Design)**: 「どのように」システムを構築し、各モジュールを実装するかを定義しています。
    - [設計の全体概要](design/README.md)
    - [アーキテクチャ設計](design/architecture.md)
    - [データモデル設計](design/data_model.md)
    - [特徴量エンジン設計](design/feature_engine.md)
    - [インジケーター設計](design/indicator.md)
    - [パターン検出器設計](design/pattern_detector.md)
    - [スコアエンジン設計](design/score_engine.md)
    - [ディレクトリ構造設計](design/directory_structure.md)
    - [クラス設計](design/class_design.md)
    - [API・モジュール連携設計](design/api_module_design.md)

## 3. 開発フェーズごとの計画

### 3.1. フェーズ1: コア機能の確立 (完了)
- [x] プロジェクト名とコンセプトの決定
    - プロジェクト名: Project Atlas
    - 開発目的: スイングトレード向け株式分析支援システム
    - ターゲットユーザー: 自分
    - 売買スタイル: 週〜月のスイングトレード、チャート分析主、ファンダメンタルズ分析補助
- [x] システム全体構成の定義
    - システム構成図の作成 (`docs/design/architecture.md`)
    - データ取得フロー、分析フロー、スコアリングフロー、出力フローの概要定義
- [x] 主要設計書の作成とレビュー
    - 要件定義書 (`docs/requirements/requirements.md`)
    - 各種仕様書 (`docs/specifications/`)
    - システム設計書 (`docs/design/` 配下の各ファイル)
        - アーキテクチャ設計 (`docs/design/architecture.md`)
        - データモデル設計 (`docs/design/data_model.md`)
        - ディレクトリ構造設計 (`docs/design/directory_structure.md`)
        - クラス設計 (`docs/design/class_design.md`)
        - API・モジュール連携設計 (`docs/design/api_module_design.md`)
- [x] コア機能の基本実装と単体テスト
    - Data Collector の実装とテスト
    - Indicator Calculator の実装とテスト
    - Feature Engine の実装とテスト (最低1つの特徴量)
    - Pattern Detector の実装とテスト (最低1つのパターン)
    - Score Engine の実装とテスト (総合スコア)
    - Screener と Ranking の基本実装
    - Presentation (CLI) の実装

### 3.2. フェーズ2: 機能拡張と改善 (進行中)
- [ ] **特徴量とパターンの追加**
    - [ ] `docs/specifications/feature_list.md` に記載された全ての特徴量を追加実装する
        - [x] M001: MAAlignmentScore
        - [x] P001: PullbackScore
        - [x] P002: BreakoutScore
        - [x] T001: TrendStrengthScore
        - [x] V001: VolumeScore
        - [x] O001: MomentumScore
        - [x] R001: VolatilityScore
        - R002: RiskScore
        - S001: SupportResistanceScore
        - [x] F001: ProfitabilityScore
        - [x] F002: GrowthScore
        - [x] F003: ValuationScore
        - [x] F004: FinancialHealthScore
        - [x] F005: EarningsQualityScore
    - [ ] `docs/specifications/pattern_list.md` に記載された全てのパターンを追加実装する
        - [x] R001: DoubleBottom
        - [x] R002: DoubleTop
    - [ ] 各特徴量/パターンに対応する単体テストを作成・実行する
- [ ] **データ永続化の実装**
    - [x] OHLCVデータ、財務データ、計算済み指標、特徴量、パターンの永続化ロジックを実装する (SQLite/Parquet)
    - [x] キャッシュ機構を強化する
- [ ] **高機能なスクリーニングとランキング**
    - [ ] 複数の条件を組み合わせたスクリーニング機能の実装
    - [ ] ランキング表示のカスタマイズ機能
- [ ] **エラーハンドリングとロギングの強化**
    - [ ] 例外処理の一元化と詳細なロギング機能の実装
    - [ ] 警告・エラーメッセージの改善
- [ ] **パフォーマンス最適化**
    - [ ] 大量データ処理におけるボトルネックの特定と改善
    - [ ] 並列処理、高速化ライブラリの導入検討

### 3.3. フェーズ3: バックテストとUI/UX (未着手)
- [ ] **バックテスト機能の実装**
    - [ ] 過去データを用いた売買戦略の検証機能
    - [ ] パフォーマンス指標の算出と表示
- [ ] **GUIの開発 (検討)**
    - [ ] Streamlit, Dash, PyQtなどを用いたGUI化の検討とプロトタイプ開発
- [ ] **アラート機能**
    - [ ] 特定の条件が満たされた場合に通知する機能

## 4. 今後のマイルストーン (現時点での暫定版)
- [ ] 2026/08/31: フェーズ2の「特徴量とパターンの追加」完了
- [ ] 2026/09/30: フェーズ2の「データ永続化の実装」完了
- [ ] 2026/10/31: フェーズ2の全項目完了
- [ ] 2026/12/31: フェーズ3の「バックテスト機能の実装」完了

## 5. 実行ログ (最新の作業のみ記載)
- 2026/08/23: データコレクターに、以前取得されたIR BANKの財務データJSONキャッシュ読み込み機能、およびOHLCV株価データのCSVキャッシュ機構を実装完了。Pydantic設定クラスの環境変数無視設定追加。101件すべてのユニットテストに合格。
- 2026/08/23: チャートパターン転換一括パック（`R001: DoubleBottom`、`R002: DoubleTop`）の実装、および対応するすべての単体テスト（計10件）の作成を実施。すべてのテストが正常にパスすることを確認。
- 2026/08/23: ファンダメンタルズ評価一括パック（`F001`〜`F005`）の実装、および対応するすべての単体テスト（計21件）の作成を実施。すべてのテストが正常にパスすることを確認。
- 2026/08/23: ボラティリティ評価 (`R001_VolatilityScore`) の実装、および対応する単体テストの作成を実施。全てのテストが正常にパスすることを確認。
- 2026/08/23: モメンタム評価 (`O001_MomentumScore`) の実装、および対応する単体テストの作成を実施。全てのテストが正常にパスすることを確認。
- 2026/08/23: 出来高評価 (`V001_VolumeScore`) の実装、および対応する単体テストの作成を実施。全てのテストが正常にパスすることを確認。
- 2026/08/23: トレンド強度評価 (`T001_TrendStrengthScore`) の実装、および対応する単体テストの作成を実施。全てのテストが正常にパスすることを確認。
- 2026/08/23: ブレイクアウト評価 (`P002_BreakoutScore`) の実装、および対応する単体テストの作成を実施。全てのテストが正常にパスすることを確認.
- 2026/08/23: 押し目評価 (`P001_PullbackScore`) の実装、および対応する単体テストの作成を実施。全てのテストが正常にパスすることを確認。
- 2026/08/23: 移動平均線配列スコア (`M001_MAAlignmentScore`) の実装、および対応する単体テストの作成・調整を実施。全てのテストが正常にパスすることを確認。
- 2026/08/02: `docs/_plan.md` にフェーズ2の「特徴量とパターンの追加」に関する詳細なタスクと完了条件を追記。
- 2026/07/26: ディレクトリ構造の作成と、`src/main.py` の基本実装、主要なモデル、設定、各モジュールのインターフェースと初期クラス（データ収集、指標計算、特徴量計算、パターン検出、スコアリング、スクリーニング、ランキング、結果表示）を実装。対応する単体テストも作成・修正し、全テストケースが合格することを確認。`work/plan.md` を `work/initial_setup_plan.md` にリネームし、`docs/_plan.md` をプロジェクト全体の開発計画書として更新。

## 6. テスト計画 (詳細は各モジュールのテストファイルを参照)

### 6.1. Data Collector
- **テストファイル:** `tests/unit/data_collector/test_collector.py`
- **主要テストケース:** OHLCVデータ取得成功・空データ処理、財務データ取得、モジュールレベル関数テスト

### 6.2. Indicator Calculator
- **テストファイル:** `tests/unit/indicator_calculator/test_calculator.py`
- **主要テストケース:** SMA/RSI/MACD計算、統合計算、空データ処理

### 6.3. Feature Engine
- **テストファイル:** `tests/unit/feature_engine/test_features.py`
- **主要テストケース:** 特徴量プロパティ、各種トレンド状況でのスコア計算、空データ処理、スコア正規化

### 6.4. Pattern Detector
- **テストファイル:** `tests/unit/pattern_detector/test_patterns.py`
- **主要テストケース:** パターンプロパティ、有効/無効なハンマー検出、空データ処理、信頼度計算

### 6.5. Score Engine
- **テストファイル:** `tests/unit/score_engine/test_scores.py`
- **主要テストケース:** スコアプロパティ、総合スコア計算、空データ処理、スコア正規化

### 6.6. Feature Engine (Moving Average)
- **テストファイル:** `tests/unit/feature_engine/moving_average/test_ma_alignment_score.py`
- **主要テストケース:** 特徴量プロパティ、各種並び状態（強い上昇、上昇、中立、下降、強い下降）でのスコア計算、データ不足時のハンドリング、スコア正規化

### 6.7. Feature Engine (Price Action)
- **テストファイル:** `tests/unit/feature_engine/price_action/test_pullback_score.py`
- **主要テストケース:** 特徴量プロパティ、各種調整状態（理想的な押し目、浅い押し目、長期線でのサポート押し目、下降トレンド/サポート割れ、データ不足）でのスコア計算、スコア正規化

### 6.8. Feature Engine (Breakout)
- **テストファイル:** `tests/unit/feature_engine/price_action/test_breakout_score.py`
- **主要テストケース:** 特徴量プロパティ、各種ブレイクアウト状況（健全なブレイク初動、少し買い遅れのブレイク、過熱したブレイク、ブレイク目前、射程圏内、まだ遠いレンジ相場、データ不足）でのスコア計算、スコア正規化

### 6.9. Feature Engine (Trend)
- **テストファイル:** `tests/unit/feature_engine/trend/test_trend_strength_score.py`
- **主要テストケース:** 特徴量プロパティ、上昇・下降トレンド等での総合強度（並び、傾き、株価位置、高安切り上げ）のスコア計算、データ不足時のハンドリング、スコア正規化

### 6.10. Feature Engine (Volume)
- **テストファイル:** `tests/unit/feature_engine/volume/test_volume_score.py`
- **主要テストケース:** 特徴量プロパティ、急増水準（平均に対する比率）、短期トレンド、株価方向との整合性を加味したスコア計算、データ不足時のハンドリング、スコア正規化

### 6.11. Feature Engine (Oscillator)
- **テストファイル:** `tests/unit/feature_engine/oscillator/test_momentum_score.py`
- **主要テストケース:** 特徴量プロパティ、上昇モメンタム、下降モメンタム、MACDデータ欠損時やデータ不足時のハンドリング、スコア正規化

### 6.12. Feature Engine (Volatility)
- **テストファイル:** `tests/unit/feature_engine/risc/test_volatility_score.py`
- **主要テストケース:** 特徴量プロパティ、高ボラティリティ（平均の2倍以上）、低ボラティリティ、データ不足時のハンドリング、スコア正規化

### 6.13. Pattern Detector (Reversal - DoubleBottom)
- **テストファイル:** `tests/unit/pattern_detector/reversal/test_double_bottom.py`
- **主要テストケース:** パターンプロパティ、有効なダブルボトム（ネック上抜け）、形成途中のダブルボトム、不成立（サポート割れ）の検出、データ不足時のハンドリング

### 6.14. Pattern Detector (Reversal - DoubleTop)
- **テストファイル:** `tests/unit/pattern_detector/reversal/test_double_top.py`
- **主要テストケース:** パターンプロパティ、有効なダブルトップ（ネック下抜け）、形成途中のダブルトップ、不成立（高値ブレイク）の検出、データ不足時のハンドリング

### 6.13. Feature Engine (Fundamental - Profitability)
- **テストファイル:** `tests/unit/feature_engine/fundamental/test_profitability_score.py`
- **主要テストケース:** 特徴量プロパティ、高収益ケース（ROE/ROA/営業利益率高）、赤字ケース、データ欠損時のハンドリング、スコア正規化

### 6.14. Feature Engine (Fundamental - Growth)
- **テストファイル:** `tests/unit/feature_engine/fundamental/test_growth_score.py`
- **主要テストケース:** 特徴量プロパティ、5年平均成長ケース（売上高・純利益）、3年平均ケース、減収減益ケース、データ欠損時のハンドリング、スコア正規化

### 6.15. Feature Engine (Fundamental - Valuation)
- **テストファイル:** `tests/unit/feature_engine/fundamental/test_valuation_score.py`
- **主要テストケース:** 特徴量プロパティ、非常に割安なケース（PER/PBR低）、割高ケース、データ欠損時のハンドリング、スコア正規化

### 6.16. Feature Engine (Fundamental - Financial Health)
- **テストファイル:** `tests/unit/feature_engine/fundamental/test_financial_health_score.py`
- **主要テストケース:** 特徴量プロパティ、健全な自己資本蓄積と黒字安定ケース（BPS>EPS & 営業/純利益黒字）、脆弱ケース、データ欠損時のハンドリング、スコア正規化

### 6.17. Feature Engine (Fundamental - Earnings Quality)
- **テストファイル:** `tests/unit/feature_engine/fundamental/test_earnings_quality_score.py`
- **主要テストケース:** 特徴量プロパティ、本業と最終利益の整合、健全な財務レバレッジ（ROE/ROA比）、一時利益依存ケース、データ欠損時のハンドリング、スコア正規化
