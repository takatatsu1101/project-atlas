# Project Atlas ドキュメント

Project Atlas は、スイングトレード向けの株式分析支援システムです。東京証券取引所に上場する銘柄を対象に、テクニカル指標、チャートパターン、およびファンダメンタルズを統合的に評価し、有望な銘柄をスコアリングして抽出することを目的としています。

## 1. プロジェクトの全体像

本システムは、データの取得から分析、スコアリング、結果表示までを、責務ごとに分離したモジュール構造（モジュラー・モノリス）で構築されています。

### 主要コンポーネント
- **Data Collector**: 市場データ（OHLCV）や財務データの取得・保存を担当。
- **Indicator Calculator**: テクニカル指標（MA, RSI等）の計算を担当。
- **Feature Engine**: 指標や生データを基にした市場・企業の特性（特徴量）の定量化を担当。
- **Pattern Detector**: チャートパターン（ダブルボトム等）の検出を担当。
- **Score Engine**: 特徴量とパターン検出結果を統合し、最終的なスコアを算出。
- **Screener / Ranking**: スコアに基づいた銘柄の絞り込みと順位付け。
- **Presentation**: 分析結果をユーザーに提示（CLI/将来的なGUI）。

## 2. ドキュメントの歩き方

ドキュメントは、目的別に以下の3つのカテゴリに分かれています。

### ① 要件定義（Requirements）
プロジェクトの背景、目的、およびシステムが実現すべき機能を定義しています。
- [要件定義書](requirements/requirements.md)

### ② 仕様（Specifications）
「何を」評価・検出するかという具体的なロジックや対象を定義しています。
- [特徴量一覧](specifications/features/feature_list.md)
- [パターン一覧](specifications/patterns/pattern_list.md)
- [指標仕様](specifications/indicators.md)
- [スコアリング仕様](specifications/scoreing.md)

### ③ 設計（Design）
「どのように」システムを構築し、各モジュールを実装するかを定義しています。
- [設計の全体概要](design/README.md)
- [アーキテクチャ設計](design/architecture.md)
- [データモデル設計](design/data_model.md)
- [特徴量エンジン設計](design/feature_engine.md)
- [インジケーター設計](design/indicator.md)
- [パターン検出器設計](design/pattern_detector.md)
- [スコアエンジン設計](design/score_engine.md)

### ④ 開発計画（Plan）
開発ロードマップ、タスク管理、進捗状況などを記載しています。
- [開発計画](_plan.md)