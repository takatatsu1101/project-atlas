# 開発計画

## 1. 概要
このドキュメントは、Project Atlas の開発計画を管理します。各タスクのステータス、実施内容、および改善点を記録します。

## 2. 実装計画

### 2.1. Data Collector (完了)
- [x] データの取得戦略を決定する
- [x] データの保存方法を設計する
- [x] 初期データの取得と保存を実装する

### 2.2. Indicator Calculator (完了)
- [x] 主要なテクニカル指標の計算ロジックを設計する
- [x] 指標計算モジュールを実装する
- [x] 計算結果のキャッシュメカニズムを実装する

### 2.3. Feature Engine (完了)
- [x] 特徴量抽出のインターフェースを設計する
- [x] いくつかの基本的な特徴量を実装する
- [x] Feature Engine の実行フローを実装する

### 2.4. Pattern Detector (完了)
- [x] チャートパターン検出のインターフェースを設計する
- [x] いくつかの基本的なチャートパターンを実装する
- [x] Pattern Detector の実行フローを実装する

### 2.5. Score Engine (完了)
- [x] スコア算出ロジックを設計する
- [x] Feature と Pattern を統合したスコアリングを実装する
- [x] ランキング生成モジュールを実装する

### 2.6. Screener / Ranking (完了)
- [x] スクリーニング条件の定義と実装
- [x] ランキング表示の実装

### 2.7. Presentation (完了)
- [x] CLI出力機能の実装
- [ ] (将来) GUIの検討

## 3. Reflection (別のファイルに記録)

## 4. 実行ログ
- 2026/07/26: ディレクトリ構造の作成と、`src/main.py` の基本実装、`src/model/data_models.py`、`src/config/settings.py`、`src/data_collector/collector.py`、`src/indicator_calculator/calculator.py`、`src/feature_engine/interfaces.py`、`src/feature_engine/registry.py`、`src/feature_engine/features/trend.py`、`src/feature_engine/manager.py`、`src/pattern_detector/interfaces.py`、`src/pattern_detector/registry.py`、`src/pattern_detector/patterns/candlestick.py`、`src/pattern_detector/manager.py`、`src/score_engine/interfaces.py`、`src/score_engine/registry.py`、`src/score_engine/scores/overall.py`、`src/score_engine/manager.py`、`src/screener/screener.py`、`src/ranking/generator.py`、`src/presentation/presenter.py` を実装した。