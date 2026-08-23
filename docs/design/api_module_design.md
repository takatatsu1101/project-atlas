---
title: API・モジュール設計書
document_id: DESIGN-APIMOD-001
version: 0.1.0
status: Draft
project: Project Atlas
author: Takatori Tatsuo
created: 2026-07-26
updated: 2026-07-26
related:
  - design/readme.md
  - design/architecture.md
  - design/data_model.md
  - design/class_design.md
---

# API・モジュール設計書

## 1. 概要
本設計書は、Project Atlas における各モジュールが提供する主要なAPI（外部公開インターフェース）および、モジュール間の連携方法について定義する。これにより、各モジュールの独立性を保ちつつ、システム全体としての一貫性と連携の効率性を確保する。

## 2. 目的
- 各モジュールが外部に提供する機能とインターフェースを明確にする。
- モジュール間のデータフローと制御フローを定義する。
- 疎結合なシステム設計を促進し、各モジュールの並行開発とテストを容易にする。
- 将来的な拡張や変更に強い柔軟なシステム基盤を構築する。

## 3. 設計原則
- **明確なインターフェース:** 各モジュールは、その責務を果たすために必要最小限かつ明確なAPIを提供する。
- **疎結合:** モジュール間の直接的な依存関係を避け、抽象化されたインターフェース（データモデル、抽象クラス）を介して連携する。
- **データ中心:** モジュール間のデータの受け渡しは、`data_model.md` で定義された共通データモデルを使用する。
- **エラーハンドリング:** APIは、予期せぬ入力やシステムエラーに対して堅牢なエラーハンドリング機構を提供する。
- **統一されたAPIスタイル:** APIの命名規則、引数、戻り値の形式などに一貫性を持たせる。

## 4. モジュール間の連携と主要API

### 4.1. アプリケーションのエントリポイント (`src/main.py`)
アプリケーションの起動、設定の読み込み、主要な処理フローのオーケストレーションを担当する。

- **主要API:**
    - `run_analysis(symbol: str, start_date: str, end_date: str, config: Dict = None) -> AnalysisResultModel`
        - 指定された銘柄と期間で分析を実行し、最終結果を返す。
    - `generate_report(analysis_result: AnalysisResultModel, output_format: str) -> None`
        - 分析結果に基づいてレポートを生成し、指定された形式で出力する。

### 4.2. `config` モジュール (`src/config/settings.py`)
アプリケーション全体の設定情報を提供する。

- **主要API:**
    - `load_settings(env: str = "development") -> Settings`
        - 環境に応じた設定（APIキー、DBパスなど）をロードする。

### 4.3. `data_collector` モジュール (`src/data_collector/`)
市場データを収集し、永続化する機能を提供する。

- **主要API:**
    - `collect_ohlcv_data(symbol: str, start_date: date, end_date: date) -> List[OhlcvModel]`
        - 指定期間のOHLCVデータを収集し、保存後、データを返す。
    - `collect_financial_data(symbol: str, fiscal_year: int) -> FinancialModel`
        - 指定年度の財務データを収集し、保存後、データを返す。

### 4.4. `indicator_calculator` モジュール (`src/indicator_calculator/`)
OHLCVデータからテクニカル指標を計算する機能を提供する。

- **主要API:**
    - `calculate_indicators(ohlcv_data: List[OhlcvModel]) -> List[IndicatorSetModel]`
        - OHLCVデータリストからテクニカル指標のセットを計算して返す。

### 4.5. `feature_engine` モジュール (`src/feature_engine/`)
テクニカル指標と財務データから特徴量を算出する機能を提供する。

- **主要API:**
    - `calculate_features(ohlcv_data: List[OhlcvModel], indicator_data: List[IndicatorSetModel], financial_data: Optional[FinancialModel] = None, feature_ids: Optional[List[str]] = None) -> List[FeatureSetModel]`
        - 指定された入力データに基づいて特徴量を計算し、結果のリストを返す。

### 4.6. `pattern_detector` モジュール (`src/pattern_detector/`)
OHLCVデータとテクニカル指標からチャートパターンを検出する機能を提供する。

- **主要API:**
    - `detect_patterns(ohlcv_data: List[OhlcvModel], indicator_data: List[IndicatorSetModel], pattern_ids: Optional[List[str]] = None) -> List[PatternSetModel]`
        - 指定された入力データに基づいてチャートパターンを検出し、結果のリストを返す。

### 4.7. `score_engine` モジュール (`src/score_engine/`)
特徴量と検出パターンを統合して評価スコアを算出する機能を提供する。

- **主要API:**
    - `calculate_scores(feature_sets: List[FeatureSetModel], pattern_sets: List[PatternSetModel]) -> List[ScoreResultModel]`
        - 特徴量セットとパターンセットから評価スコアを計算し、結果のリストを返す。

### 4.8. `screener` モジュール (`src/screener/`)
評価スコアやその他の条件に基づいて銘柄をスクリーニングする機能を提供する。

- **主要API:**
    - `apply_screener(score_results: List[ScoreResultModel], criteria: Dict) -> List[ScoreResultModel]`
        - 指定された条件でスコア結果をフィルタリングし、合致する銘柄のリストを返す。

### 4.9. `ranking` モジュール (`src/ranking/`)
スクリーニングされた銘柄をスコアに基づいてランキングする機能を提供する。

- **主要API:**
    - `generate_ranking(filtered_score_results: List[ScoreResultModel]) -> List[AnalysisResultModel]`
        - フィルタリングされたスコア結果からランキングを生成し、最終分析結果のリストを返す。

### 4.10. `presentation` モジュール (`src/presentation/`)
分析結果をユーザーに表示する機能を提供する。

- **主要API:**
    - `display_results(analysis_results: List[AnalysisResultModel], output_type: str = "cli") -> None`
        - 分析結果をCLIまたは将来的なGUIで表示する。

### 4.11. `utils` モジュール (`src/utils/`)
汎用的なユーティリティ関数やヘルパークラスを提供する。

- **主要API:**
    - `date_to_str(date_obj: date) -> str`
    - `str_to_date(date_str: str) -> date`
    - `calculate_sma(data: List[float], period: int) -> List[float]`