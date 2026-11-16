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

Project Atlas は、スイングトレード（数週間〜3ヶ月保有）向けの**1次スクリーニング＆テクニカル定量評価システム**です。東京証券取引所に上場する銘柄を対象に、事前条件（市場区分・財務・流動性）と中長期の上昇トレンドを満たす銘柄を絞り込み、**「押し目買い型」**または**「ブレイクアウト型（保ち合い上抜け）」**のセットアップにある有望銘柄を定量抽出します。

抽出された推奨銘柄および構造化データ（具体的なサポレジ価格水準、リスク指標、判定根拠）を後段のAI（またはトレーダー自身）へ引き渡し、具体的な買値（指値・逆指値）やエントリータイミングの意思決定を支援することを目的としています。

### 主要コンポーネント
- **Data Collector**: 東証銘柄マスタ、市場データ（OHLCV）、財務データ（IR BANK JSON）の取得・キャッシュ・永続化を担当。
- **Pre-Screener (Universe Filter)**: 市場区分・財務数値・売買代金（流動性）に基づく分析対象ユニバースの事前絞り込みを担当。
- **Indicator Calculator**: テクニカル指標（SMA, RSI, MACD, ボラティリティ等）の計算を担当。
- **Feature Engine**: 指標や財務データを基にした市場・企業の特性（特徴量：0〜100）の定量化を担当。
- **Pattern Detector**: チャートパターン（ダブルボトム、ダブルトップ、ローソク足等）の検出を担当。
- **Score Engine**: 第1関門（上昇トレンド前提）を踏まえ、「押し目買い戦略スコア」と「ブレイクアウト戦略スコア」を算出し、代表スコア・推奨戦略タイプ・AI連携用の具体的価格水準を集約。
- **Screener / Ranking**: 戦略スコアとトレンド条件に基づく推奨候補の抽出と順位付けを担当。
- **Evaluator (Forward Return Validator)**: 過去基準日（`as_of_date`）指定時のフォワードリターン（N営業日後の騰落率・勝率・最大上昇/下落幅）の答え合わせ検証を担当。
- **Presentation**: 分析結果のCLI表示、および後段AI連携用の構造化レポート（JSON / Markdown）出力を担当。

### 中核トレード戦略・評価方針（v0.2.0 決定事項）
- **システムの役割**: 最終的な指値決定・自動売買ではなく、後段のAIが買値や損切りラインを判断するための**高精度な1次スクリーニングと定量根拠の構造化出力**に特化する。
- **対象銘柄と売買方向**: 東証プライム・スタンダード市場を中心とした**中〜大型・黒字・高流動性銘柄**の**「現物・買いエントリー」**に特化する（空売り候補や保有株の売り判定は対象外）。
- **3段階ゲート＋戦略別スコア方式**:
  1. **事前スクリーニング**: 銘柄マスタ（プライム・スタンダード）× ローカル財務データ（規模・黒字・ROE・自己資本比率）× 流動性（売買代金）で対象ユニバースを抽出。
  2. **第1関門（環境認識）**: 勝率・資金効率を高めるため、**中長期が上昇トレンドにある銘柄**に限定（`DoubleTop` 等の弱気シグナルは減点・除外）。
  3. **第2・第3関門（2大セットアップ戦略別評価）**: 全指標の単純平均を廃止し、**「押し目買い戦略スコア」**と**「ブレイクアウト戦略スコア」**をそれぞれ重み付け算出し、高い方を銘柄の代表スコアおよび推奨タイプとして採用する。
- **後段AI連携出力と過去検証**: スコアだけでなく具体的な価格水準（現在値、SMA5/25/75価格、直近20日高安、ボラティリティ、出来高倍率）を JSON / Markdown で出力し、過去基準日指定で「抽出銘柄がN営業日後に実際プラスになったか」を検証可能にする。

ドキュメントは、目的別に以下の3つのカテゴリに分かれています。

- **要件定義 (Requirements)**: プロジェクトの背景、目的、およびシステムが実現すべき機能を定義しています。
    - [要件定義書](requirements/requirements.md)
- **仕様 (Specifications)**: 「何を」評価・検出するかという具体的なロジックや対象を定義しています。
    - [特徴量一覧](specifications/features/feature_list.md)
    - [パターン一覧](specifications/patterns/pattern_list.md)
    - [指標仕様](specifications/indicators.md)
    - [スコアリング仕様](specifications/scoreing.md)
- **設計 (Design)**: 「どのように」システムを構築し、各モジュールを実装するかを定義しています。
    - [設計の全体概要](design/README.md)
    - [開発環境・実行ガイド](development_guide.md)
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
- [x] コア機能の基本実装と単体テスト
    - Data Collector, Indicator Calculator, Feature Engine, Pattern Detector, Score Engine, Screener, Ranking, Presentation (CLI) の初期実装

### 3.2. フェーズ2: 特徴量・パターン・データ永続化基盤の構築 (完了)
- [x] **特徴量とパターンの追加**
    - [x] `docs/specifications/features/feature_list.md` に記載された全ての特徴量を実装（旧 `R002`, `S001` はv0.2.0要件見直しによりScore/出力層の具体的価格水準・リスク情報へ統合）
        - [x] M001: MAAlignmentScore
        - [x] P001: PullbackScore
        - [x] P002: BreakoutScore
        - [x] T001: TrendStrengthScore
        - [x] V001: VolumeScore
        - [x] O001: MomentumScore
        - [x] R001: VolatilityScore
        - [x] F001〜F005: Fundamental Features (Profitability, Growth, Valuation, FinancialHealth, EarningsQuality)
    - [x] `docs/specifications/patterns/pattern_list.md` に記載された全てのパターンを実装
        - [x] R001: DoubleBottom
        - [x] R002: DoubleTop
    - [x] 各特徴量/パターンに対応する単体テストおよび統合テストを作成・実行
- [x] **データ永続化・キャッシュ機構の実装**
    - [x] ストレージユーティリティ (`src/common/storage.py`) の設計・実装
    - [x] OHLCV（株価・出来高データ）の Parquet 永続化・差分更新の実装
    - [x] IR BANK 財務データの読込・CAGR成長率計算の実装
    - [x] インジケータ・特徴量の計算結果キャッシュ機構の整備
- [x] **エラーハンドリング・ロギング基盤とパイプライン結合検証**
    - [x] 共通例外クラス (`src/common/exceptions.py`) と共通ロギング (`src/common/logger.py`) の実装
    - [x] メイン実行フロー (`src/main.py`) におけるステップ1〜6の全パイプライン結合検証完了

### 3.3. フェーズ3: v0.2.0 新要件に基づく1次スクリーニング＆AI連携・検証機能の実装 (完了・1要件1PR構成)

- [x] **PR #1: 要件定義・仕様書・開発計画の見直し (`docs/revise-requirements-and-plan`)**
    - [x] `docs/requirements/requirements.md` を v0.2.0（1次スクリーニング特化、3段階ゲート＋2大買い戦略スコア、AI連携出力、フォワードリターン検証、非機能・データ要件完備）へ改訂
    - [x] `docs/specifications/scoreing.md` および `docs/specifications/features/feature_list.md` の更新
    - [x] `docs/_plan.md` のフェーズ・PR計画の再編成

- [x] **PR #2: 銘柄マスタ管理と事前スクリーニング（Universe Pre-Screener）の実装 (`feat/pre-screener-and-master`)**
    - [x] `DataCollector` の財務データ参照パス修正（`data/financial/` を優先参照）および基準日（`as_of_date`）指定によるデータ切り出し対応（先読みバイアス防止）
    - [x] 東証銘柄マスタ（銘柄コード、銘柄名、市場区分、業種、規模区分）の保持・ロード機構の実装
    - [x] 事前スクリーニング（`PreScreener`）：①市場区分（プライム・スタンダード）× ②財務・規模条件（黒字・ROE・自己資本比率等）で対象コードを高速抽出し、③OHLCV取得後に売買代金（流動性）で絞り込む機能の実装と単体テスト

- [x] **PR #3: 3段階ゲート＆戦略別スコアリング（押し目買い型／ブレイクアウト型）の実装 (`feat/strategy-score-engine`)**
    - [x] `ScoreResultModel` / `AnalysisResultModel` のデータモデル拡張（推奨戦略タイプ `strategy_type`、戦略別サブスコア、判定根拠リスト `reasons`、AI連携用の具体的価格水準 `key_levels`［現在値、SMA5/25/75、直近20日高安、ボラティリティ、出来高倍率］）
    - [x] 第1関門（中長期上昇トレンド条件、`DoubleTop` 等の弱気シグナル減点・除外）の実装
    - [x] 「押し目買い戦略スコア (`PullbackStrategyScore`)」と「ブレイクアウト戦略スコア (`BreakoutStrategyScore`)」の重み付け算出および代表スコア決定ロジックの実装と単体テスト

- [x] **PR #4: 本スクリーニング・ランキングおよび後段AI連携レポート出力（JSON / Markdown）の実装 (`feat/ai-report-and-screener`)**
    - [x] 設定ファイル（YAML等）による事前フィルタ条件・戦略スコア重み・抽出閾値の外部化
    - [x] `Screener`（トレンド条件＋戦略スコア閾値による買い候補抽出）および `RankingGenerator`（銘柄名・業種・価格水準・推奨理由の完全引き継ぎ、総合/戦略別ランキング）の改修
    - [x] `Presenter` による CLI 表示の改善と、`output/` ディレクトリへの後段AI連携用レポート（JSON形式・Markdown形式）出力機能の実装と単体・結合テスト

- [x] **PR #5: 過去基準日指定およびスクリーニング精度検証（フォワードリターン評価）機能の実装 (`feat/forward-return-evaluator`)**
    - [x] 任意の過去基準日（`as_of_date`）を指定したスクリーニング実行と、基準日以降のN営業日後（例：5日・20日・60日後）の騰落率・勝率・最大上昇率（MFE）/最大下落率（MAE）を算出・集計する `Evaluator` モジュールの実装
    - [x] `src/main.py` への CLI 引数（`--as-of-date`, `--mode [screen|evaluate]` 等）の追加と、検証レポート出力のテスト

## 4. 今後のマイルストーン
- [x] 2026/08/31: フェーズ2の「特徴量・パターン追加およびパイプライン結合」完了
- [x] 2026/11/15: 要件見直し（v0.2.0）および1要件1PR計画の策定完了（PR #1）
- [x] 2026/11/16: フェーズ3 PR #2〜#5 の順次実装・検証完了

## 5. 実行ログ (最新の作業のみ記載)
- 2026/11/16: `feat/tune-screening-thresholds` を実施。代表32銘柄×16基準日（2025年4月〜2026年7月）のフォワードリターン検証に基づき `config/screening.yaml` をチューニング（過熱ボラ減点 `10.0→20.0`、ダブルトップ減点係数 `0.35→0.45` / 除外上限 `70.0→60.0`、ブレイクアウト出来高重み `0.25→0.35`、最低総合スコア `60.0→65.0`）。全体 +60営業日勝率が `64.8%→69.5%`、平均リターン `+14.29%→+16.36%`（ブレイクアウト型は `60.6%→69.6%`）へ改善し、全テスト205件パスを確認。
- 2026/11/16: `feat/optimize-data-collector-and-master` を実施。`DataCollector` に IR BANK JSON のインメモリキャッシュ・ダウンロード失敗/破損JSONのネガティブキャッシュ・`timeout=15`・`allow_download` 制御・`as_of_date=None` 時フォールバック統一を実装し、`MasterManager` に JPX 東証上場銘柄一覧（`data_j.xlsx`）の標準ライブラリのみによる自動取得・解析・更新機能（更新日時優先解決、ふりがな `<rPh>` 除外、タイトル行/複数シート動的探索含む）を追加。`src/main.py` に `--update-master` / `--no-irbank-download` を統合し、全テスト205件パスおよび2段階レビュー（1次 `atlas-reviewer`・2次 `gemini-4-argon-high` Approve）を完了。
- 2026/11/16: PR #5（`feat/forward-return-evaluator`）を実施。`IndicatorCalculator` / `FeatureManager` のキャッシュ分離（`cache_key_suffix` / `use_cache`）と全日付・財務署名一致検証による先読みバイアス・汚染防止強化、フォワードリターン評価モデル（`HorizonMetricsModel` 等）と `EvaluationConfig`（`config/screening.yaml`）の追加、`ForwardReturnEvaluator`（`Evaluator`：N営業日後リターン・勝率・MFE/MAE・全体/戦略別集計・休場日7日ルックバック）の実装、`Presenter` の CLI/JSON/Markdown 検証レポート対応（`evaluation_report_*`）、および `src/main.py` への CLI パーサ（`--mode`, `--as-of-date`, `--horizons`, `--no-cache` 等）統合を実装し、全テスト191件のパスおよび2段階レビュー（1次 `atlas-reviewer`・2次 `gemini-4-argon-high` 双方 Approve）を完了。
- 2026/11/15: PR #4（`feat/ai-report-and-screener`）を実施。`config/screening.yaml` による設定外部化（`src/config/screening_config.py`）と `ScoreManager`/`ScoreRegistry` への設定注入、`src/pattern_detector` の自動登録修正、`Screener`（3段階ゲート・戦略別閾値対応）・`RankingGenerator`（全フィールド引き継ぎ・総合/戦略別ランキング）・`Presenter`（CLI改善・`output/` への JSON/Markdown 出力）の改修、および `src/main.py` への全パイプライン統合を実装し、全テスト170件のパスおよび2段階レビュー（1次 `atlas-reviewer`・2次 `gemini-4-argon-high` 双方 Approve）を完了。
- 2026/11/15: PR #3（`feat/strategy-score-engine`）を実施。`ScoreResultModel`/`AnalysisResultModel` の拡張、`IndicatorCalculator` への20日高安・ATR14・出来高倍率の追加、3段階ゲート＆戦略別スコアリング（`S002_StrategyScore`：`Pullback` / `Breakout` / `Watch` 判定、`DoubleTop`・過熱ボラ減点、`key_levels`/`risk_metrics`/`reasons` 生成）を実装し、全テスト150件のパスおよび2段階レビュー（Argon Approve）を完了。
- 2026/11/15: PR #2（`feat/pre-screener-and-master`）を実施。`DataCollector` の `data/financial/` 優先参照・`as_of_date` 対応・`load_financial_snapshot` 実装、東証銘柄マスタ管理（`MasterManager`）、事前スクリーニング（`PreScreener`）を実装し、単体テスト32件が全パスすることを確認。
- 2026/11/15: 要件見直しを実施し、`docs/requirements/requirements.md` (v0.2.0)、`docs/specifications/scoreing.md`、`docs/specifications/features/feature_list.md`、`docs/_plan.md` を改訂。後段AI連携を見据えた1次スクリーニング特化、3段階ゲート＋戦略別スコア（押し目買い型／ブレイクアウト型）、構造化レポート出力（JSON/Markdown）、フォワードリターン検証機能を定義し、以降の実装を PR #1〜#5 の「1要件1PR」構成に整理。
- 2026/08/31: ステップ5（パターン検出・スコアリングの結合）およびステップ6（ランキング・プレゼンテーション出力までの全パイプライン結合テスト）を完了。全10銘柄を用いた一連の分析パイプライン（OHLCV・財務データ取得、指標計算、特徴量計算、パターン検出、スコアリング、ランキング順位付け、CLI出力）を正常に実行・検証。`docs/_plan.md` を更新。
- 2026/08/31: 全13種類の特徴量（テクニカル系・ファンダメンタルズ系すべて）を `main.py` のパイプラインに一括統合し、全10銘柄での計算およびキャッシュ保存が正常に完了することを確認（ステップ4完了）。`docs/_plan.md` を更新。
- 2026/08/31: ステップ4のサブタスク 4-1・4-2 として、特徴量単体テストの全パス確認および代表的な `M001_MAAlignmentScore` を全10銘柄で `main.py` に結合・検証完了。また不要なJSON読み込みINFOログをDEBUGに修正。`docs/_plan.md` を更新。
- 2026/08/31: `src/main.py` に `Indicator Calculator` を結合し、テクニカル指標（SMA, RSI, MACD等）の計算・キャッシュ読み込みが正常に行われることを検証（ステップ3完了）。`docs/_plan.md` を更新。
- 2026/08/23: エラーハンドリングとロギングの強化として、共通例外クラス (`src/common/exceptions.py`) および共通ロギングモジュール (`src/common/logger.py`) を実装。対応する単体テスト (`tests/unit/common/test_common.py`) を追加し、正常にパスすることを確認。`docs/_plan.md` を更新。
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
