---
title: ディレクトリ構造設計書
document_id: DESIGN-DIRSTRUCT-001
version: 0.1.0
status: Draft
project: Project Atlas
author: Takatori Tatsuo
created: 2026-07-26
updated: 2026-07-26
related:
  - design/readme.md
  - design/architecture.md
---

# ディレクトリ構造設計書

## 1. 概要
本設計書は、Project Atlas のソースコードおよびドキュメントのディレクトリ構造を定義する。これにより、プロジェクトの構成を明確にし、開発効率と保守性を向上させる。

## 2. 目的
- プロジェクト内のファイルとディレクトリの配置に関する一貫性を提供する。
- 開発者が特定の機能や情報を見つけやすくする。
- 新しいメンバーがプロジェクトの構造を迅速に理解できるようにする。
- 各コンポーネントの責務をディレクトリレベルで明確にする。

## 3. 設計原則
- **機能別・層別構造:** 関連する機能や同じ層に属するコンポーネントは、まとまったディレクトリに配置する。
- **明瞭な命名規則:** ディレクトリ名とファイル名は、内容を明確に表すものとする。
- **拡張性:** 新しい機能やモジュールが追加された際に、既存の構造を大きく変更することなく対応できる柔軟性を持つ。
- **独立性:** 各ディレクトリは可能な限り独立性を保ち、他ディレクトリへの依存関係を最小限にする。

## 4. ディレクトリ構造
```
. # プロジェクトルート
├── .git/
├── .vscode/                 # VS Code 設定ファイル
├── docs/                    # ドキュメント
│   ├── _plan.md             # 全体計画書
│   ├── README.md            # プロジェクト概要
│   ├── design/              # 設計書
│   │   ├── README.md
│   │   ├── architecture.md
│   │   ├── data_model.md
│   │   ├── directory_structure.md # 本ファイル
│   │   ├── feature_engine.md
│   │   ├── indicator.md
│   │   ├── pattern_detector.md
│   │   └── score_engine.md
│   ├── requirements/        # 要件定義書
│   │   └── requirements.md
│   └── specifications/      # 仕様書
│       ├── features/        # 特徴量仕様書
│       │   ├── fundamental/
│       │   ├── moving_average/
│       │   ├── oscillator/
│       │   ├── price_action/
│       │   ├── risc/
│       │   ├── trend/
│       │   └── volume/
│       ├── patterns/        # パターン仕様書
│       │   ├── candlestick/
│       │   ├── continuation/
│       │   ├── reversal/
│       │   ├── support_resistance/
│       │   └── trend/
│       ├── feature_list.md
│       ├── indicators.md
│       ├── pattern_list.md
│       └── scoreing.md
├── src/                     # ソースコードルート
│   ├── __init__.py          # Pythonパッケージとして認識させるためのファイル
│   ├── main.py              # メインアプリケーションのエントリポイント
│   ├── config/              # 設定関連
│   │   └── settings.py
│   ├── data_collector/      # データ収集モジュール
│   │   ├── __init__.py
│   │   ├── collector.py
│   │   └── models.py        # データモデル定義（DBスキーマ等）
│   ├── indicator_calculator/ # テクニカル指標計算モジュール
│   │   ├── __init__.py
│   │   └── calculator.py
│   ├── feature_engine/      # 特徴量算出モジュール
│   │   ├── __init__.py
│   │   ├── manager.py       # FeatureManager
│   │   ├── registry.py      # FeatureRegistry
│   │   ├── interfaces.py    # IFeatureインターフェース
│   │   ├── features/        # 各特徴量の実装
│   │   │   ├── __init__.py
│   │   │   ├── trend/
│   │   │   └── fundamental/
│   │   └── models.py        # FeatureResultモデル
│   ├── pattern_detector/    # パターン検出モジュール
│   │   ├── __init__.py
│   │   ├── manager.py       # PatternManager
│   │   ├── registry.py      # PatternRegistry
│   │   ├── interfaces.py    # IPatternインターフェース
│   │   ├── patterns/        # 各パターン検出の実装
│   │   │   ├── __init__.py
│   │   │   └── candlestick/
│   │   └── models.py        # PatternResultモデル
│   ├── score_engine/        # スコアリングモジュール
│   │   ├── __init__.py
│   │   ├── manager.py       # ScoreManager
│   │   ├── registry.py      # ScoreRegistry
│   │   ├── interfaces.py    # IScoreCalculatorインターフェース
│   │   ├── scores/          # 各スコア計算の実装
│   │   │   ├── __init__.py
│   │   │   └── overall/
│   │   └── models.py        # ScoreResultモデル
│   ├── utils/               # 汎用ユーティリティ
│   │   └── helper.py
│   └── visualization/       # データ可視化モジュール（GUI化の際に拡充）
│       └── plotter.py
├── tests/                   # テストコード
│   ├── __init__.py
│   ├── unit/                # 単体テスト
│   │   ├── data_collector/
│   │   ├── indicator_calculator/
│   │   ├── feature_engine/
│   │   ├── pattern_detector/
│   │   └── score_engine/
│   └── integration/         # 結合テスト
├── venv/                    # Python仮想環境
├── .gitignore
├── pyproject.toml           # プロジェクト設定（Poetryなど）
└── README.md
```

## 5. 各ディレクトリの責務
- **`.git/`**: Gitリポジトリのメタデータを格納する。
- **`.vscode/`**: Visual Studio Code のワークスペース設定や推奨拡張機能を格納する。
- **`docs/`**: プロジェクトに関するすべてのドキュメントを格納する。
    - **`_plan.md`**: プロジェクトの全体計画、進捗、タスクリストを記述する。
    - **`README.md`**: プロジェクトの目的、セットアップ方法、基本的な使用方法などを記述する。
    - **`design/`**: システム設計に関するドキュメントを格納する。
        - **`architecture.md`**: システム全体のアーキテクチャ概要を記述する。
        - **`data_model.md`**: データモデルの定義を記述する。
        - **`directory_structure.md`**: 本ドキュメント。ディレクトリ構造を定義する。
        - **`feature_engine.md`**: Feature Engine の詳細設計を記述する。
        - **`indicator.md`**: Indicator Calculator の詳細設計を記述する。
        - **`pattern_detector.md`**: Pattern Detector の詳細設計を記述する。
        - **`score_engine.md`**: Score Engine の詳細設計を記述する。
    - **`requirements/`**: ユーザー要件やシステム要件を記述する。
    - **`specifications/`**: 各コンポーネントや機能の詳細仕様を記述する。
        - **`features/`**: 各特徴量の具体的な計算方法やデータ形式を記述する。
        - **`patterns/`**: 各パターンの具体的な検出ロジックやデータ形式を記述する。
        - **`feature_list.md`**: 定義されている特徴量の一覧を記述する。
        - **`indicators.md`**: テクニカル指標の定義と計算方法を記述する。
        - **`pattern_list.md`**: 定義されているパターンの一覧を記述する。
        - **`scoreing.md`**: スコアリングロジックの定義と計算方法を記述する。
- **`src/`**: アプリケーションのソースコードを格納する。
    - **`main.py`**: アプリケーションのエントリポイント。CLIの起動や主要な処理フローを制御する。
    - **`config/`**: 環境設定やアプリケーション設定を格納する。
    - **`data_collector/`**: 外部データソースからデータを収集・保存する機能を提供する。
    - **`indicator_calculator/`**: ローデータからテクニカル指標を計算する機能を提供する。
    - **`feature_engine/`**: テクニカル指標や生データから特徴量を算出する機能を提供する。
        - **`manager.py`**: 特徴量のオーケストレーションを管理する。
        - **`registry.py`**: 特徴量クラスの登録・取得を行う。
        - **`interfaces.py`**: `IFeature` インターフェースを定義する。
        - **`features/`**: 個々の特徴量計算ロジックを実装する。
        - **`models.py`**: `FeatureResult` データモデルを定義する。
    - **`pattern_detector/`**: 特徴量や生データから価格パターンを検出する機能を提供する。
        - **`manager.py`**: パターン検出のオーケストレーションを管理する。
        - **`registry.py`**: パターンクラスの登録・取得を行う。
        - **`interfaces.py`**: `IPattern` インターフェースを定義する。
        - **`patterns/`**: 個々のパターン検出ロジックを実装する。
        - **`models.py`**: `PatternResult` データモデルを定義する。
    - **`score_engine/`**: 特徴量や検出パターンから総合スコアを算出する機能を提供する。
        - **`manager.py`**: スコア計算のオーケストレーションを管理する。
        - **`registry.py`**: スコア計算クラスの登録・取得を行う。
        - **`interfaces.py`**: `IScoreCalculator` インターフェースを定義する。
        - **`scores/`**: 個々のスコア計算ロジックを実装する。
        - **`models.py`**: `ScoreResult` データモデルを定義する。
    - **`utils/`**: 汎用的なユーティリティ関数やクラスを格納する。
    - **`visualization/`**: データ可視化に関する機能を提供する（将来的なGUI化を見据える）。
- **`tests/`**: プロジェクトのテストコードを格納する。
    - **`unit/`**: 各モジュールの単体テストを格納する。
    - **`integration/`**: モジュール間の結合テストを格納する。
- **`venv/`**: Pythonの仮想環境を格納する（`.gitignore` で除外）。
- **`.gitignore`**: Gitが追跡しないファイルやディレクトリを指定する。
- **`pyproject.toml`**: PoetryなどのPythonプロジェクト管理ツールの設定ファイル。
- **`README.md`**: プロジェクトルート直下のプロジェクト概要。

## 6. クラス設計（概要）
各コンポーネント内で以下の主要なクラスを想定する。

### Data Collector
- `DataCollector`: データを収集し、データベースに保存する。
- `DataProvider`: データベースからデータを取得するインターフェース。
- `SQLiteDataProvider`: `DataProvider` のSQLite実装。

### Indicator Calculator
- `IndicatorCalculator`: 生データからテクニカル指標を計算する。
- `MovingAverage`: 移動平均線を計算するクラス。
- `RSI`: RSIを計算するクラス。

### Feature Engine
- `FeatureManager`: 特徴量の計算を管理する。
- `FeatureRegistry`: `IFeature` を実装する特徴量クラスを登録・提供する。
- `IFeature`: 特徴量クラスのインターフェース。
- `TrendStrengthFeature`: トレンド強度特徴量を計算するクラス。
- `PullbackScoreFeature`: 押し目評価特徴量を計算するクラス。
- `FeatureResult`: 計算された特徴量の結果を保持するデータクラス。

### Pattern Detector
- `PatternManager`: パターン検出を管理する。
- `PatternRegistry`: `IPattern` を実装するパターンクラスを登録・提供する。
- `IPattern`: パターンクラスのインターフェース。
- `DoubleBottomDetector`: ダブルボトムパターンを検出するクラス。
- `HeadAndShouldersDetector`: ヘッドアンドショルダーズパターンを検出するクラス。
- `PatternResult`: 検出されたパターンの結果を保持するデータクラス。

### Score Engine
- `ScoreManager`: スコア計算を管理する。
- `ScoreRegistry`: `IScoreCalculator` を実装するスコア計算クラスを登録・提供する。
- `IScoreCalculator`: スコア計算クラスのインターフェース。
- `OverallScoreCalculator`: 総合スコアを計算するクラス。
- `TrendFollowingScoreCalculator`: トレンドフォロー戦略に基づくスコアを計算するクラス。
- `ScoreResult`: 計算されたスコアの結果を保持するデータクラス。

## 7. API・モジュール設計（概要）
各モジュールは、明確なAPI（公開メソッドとクラス）を提供し、疎結合を保つように設計する。

- **`data_collector.collector`**: `collect_data(symbol, start_date, end_date)` などのメソッドを提供。
- **`indicator_calculator.calculator`**: `calculate_ma(data, period)` などのメソッドを提供。
- **`feature_engine.manager`**: `calculate_features(symbol, start_date, end_date, feature_ids)` などのメソッドを提供。
- **`pattern_detector.manager`**: `detect_patterns(symbol, start_date, end_date, pattern_ids)` などのメソッドを提供。
- **`score_engine.manager`**: `calculate_scores(symbol, start_date, end_date, score_ids)` などのメソッドを提供。

## 8. データ設計（概要）
各モジュールの入出力データは、Pydanticなどのライブラリを用いてデータクラスとして定義し、型ヒントを積極的に活用する。

- **生データ**: OHLCV（Open, High, Low, Close, Volume）データ、出来高、売買代金など。
- **テクニカル指標**: 移動平均線、RSI、MACDなどの計算結果。
- **特徴量**: Feature Engine で算出される0〜100に正規化された数値データ。
- **パターン**: Pattern Detector で検出されるパターン（開始日、終了日、信頼度など）。
- **スコア**: Score Engine で算出される総合スコア（0〜100）、サブスコア、各特徴量やパターンの寄与度など。

## 9. レビュープロセス
- 設計書は定期的にレビューし、変更点や改善点を議論する。
- 実装前に主要な設計箇所はレビューを必須とする。
- レビューアは、設計原則、要件との整合性、拡張性、テスト容易性、パフォーマンスなどを評価する。