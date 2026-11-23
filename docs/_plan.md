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

### 3.4. フェーズ4: 銘柄評価高速化・スケーラビリティ改善 (完了・1要件1PR構成)

- [x] **PR #1: 重複I/O・逆転キャッシュの排除と計測ログ基盤 (`perf/eliminate-redundant-io-and-cache`)**
    - [x] パイプライン各フェーズ（マスタ/事前フィルタ・OHLCV・財務・指標・特徴量・パターン・スコア・ランキング・フォワード評価）の所要時間計測ログ (`time.perf_counter()`) と `run_metadata` 出力の追加
    - [x] `DataCollector.collect_financial_data()` への `latest_close` 引き渡しおよび事前読込キャッシュ活用による 2回目 OHLCV 読込・通信の廃止（後方互換維持）
    - [x] `FeatureManager` の `features_*_all.json` キャッシュのデフォルト無効化（明示オプション `--use-feature-cache` での切替維持）
    - [x] `RankingGenerator.generate_strategy_rankings()` におけるルックアップ辞書の1回生成・使い回し
    - [x] `--mode evaluate` 時における全期間 OHLCV の一括読込と `ForwardReturnEvaluator.evaluate(..., ohlcv_map=...)` への共有（先読みバイアス防止の `as_of_date` スライス境界厳守）

- [x] **PR #2: `yfinance` 取得判定の適正化とチャンク並列バッチ取得 (`perf/batch-yfinance-and-fetch-check`)**
    - [x] 東証最新完了営業日のプリチェックおよび開始日休場マージン考慮による不要な `yfinance` 再通信の抑止
    - [x] `DataCollector.prefetch_ohlcv_batch()`（`yf.download(..., actions=True, threads=True, group_by="ticker")` のチャンク単位取得＋失敗ティッカー個別リトライ）の実装と `src/main.py` への統合

- [x] **PR #3: Parquet 読込・指標ベクトル化と最新日評価モード (`perf/vectorize-and-latest-only-eval`)**
    - [x] `DataCollector.collect_ohlcv_data()` の列限定読込・`NaN` クレンジング・`iterrows()` 排除（`OhlcvModel.model_construct`）
    - [x] `IndicatorCalculator` の単一 DataFrame / NumPy ベクトル演算への統合（個別計算メソッド互換維持）
    - [x] `DoubleBottomPattern` / `DoubleTopPattern` の $O(N)$ 化、および `latest_only_per_symbol=True` 向け「全履歴配列参照・最新日（対象インデックス）のみ評価」モードの実装

- [x] **PR #4: プロセス並列化と複数基準日一括バックテストランナー (`perf/multiprocess-and-batch-backtest`)**
    - [x] `FEATURE_ENGINE_PARALLEL_PROCESSES` / `--workers` による `ProcessPoolExecutor` 並列化（少銘柄時の閾値制御・ワーカー初期化・読取専用制約）
    - [x] 複数基準日指定バックテスト用の「全期間1回読込・ベクトル指標1回算出・基準日断面厳密分離」一括評価ランナーの実装

### 3.5. フェーズ5: 特徴量充足度改善・検証基盤強化 (完了・1要件1PR構成)

`docs/reports/feature_improvement_report_2026-11-17.md` の「6. 推奨ネクストステップ」に基づき、検証の切り分けを明確にするため Step 1〜Step 4 を 1 PR ずつ段階的に実装・フォワード検証する。

- [x] **PR #1 (Step 1): データ修正・検証基盤強化 (`fix/data-integrity-and-quantile-eval`)**
    - **目的**: 評価の土台となるデータ不整合・計算バグを解消し、全通過銘柄を対象とした特徴量別分位バックテストによってベースラインを定量計測できるようにする。
    - **対象スコープ**:
        - [x] **株式分割による PER/PBR 歪みの補正**: Parquet に保存済みの `stock_splits` を用いて決算期末日（`fiscal_date`）翌日〜基準日（`as_of_date`）の累積分割比率を算出し、EPS/BPS を調整して PER/PBR を再計算（併せて異常値ガードを設定）。
        - [x] **成長率欠損の `None` 維持**: `DataCollector.collect_financial_data()` における過去 PL 欠損時の `revenue_growth` / `net_profit_growth`（単年・3年・5年）の `0.0` 初期化を廃止し、`None` のまま格納して `F002_GrowthScore` の欠損中立（25点）判定を有効化。
        - [x] **`V001_VolumeScore` の当日除外修正**: `avg_volume_25` の算出範囲から当日 `i` を除外（`t-25 〜 t-1`）し、出来高急増日の倍率圧縮バグを解消。
        - [x] **パターン検出バグ・ウィンドウ修正**: `HammerPattern` の `is_close_to_high` 条件式修正、および `DoubleBottomPattern` / `DoubleTopPattern` の谷・山探索期間ウィンドウ制限（直近営業日ウィンドウ導入）。
        - [x] **過去日パターンフォールバックの見直し**: `RankingGenerator._lookup_set()` で当日未検出時に過去日パターンへフォールバックする挙動を見直し、当日厳密一致を基本とする設定・制御を導入。
        - [x] **ダミー行クレンジング**: `data/price/1301.T.parquet` 先頭5行の `NaN` 混入ダミー行のクレンジング（および読込時除外の整合性確認）。
        - [x] **全通過銘柄＆特徴量別分位評価の追加**: `--mode evaluate` / `--mode backtest` で `overall_ranking`（上位 `top_n`）だけでなくスクリーニング全通過銘柄（`filtered_scores`）を対象に、各特徴量スコアの分位別（上位20% vs 下位20%）`+5 / +20 / +60` 営業日勝率・平均リターン・MFE・MAE を集計・出力する機能を追加。
    - **変更予定ファイル**:
        - `src/data_collector/collector.py`
        - `src/feature_engine/features/volume/volume_score.py`
        - `src/pattern_detector/patterns/candlestick.py`
        - `src/pattern_detector/patterns/reversal/_common.py`, `double_bottom.py`, `double_top.py`
        - `src/ranking/generator.py`
        - `src/evaluator/evaluator.py`, `src/model/data_models.py`, `src/presentation/presenter.py`, `src/main.py`
        - `src/config/screening_config.py`, `config/screening.yaml`
        - 関連単体テスト（`tests/unit/`）および仕様書（`docs/specifications/`）
    - **設計上の決定事項**:
        - 累積分割比率は `fiscal_date < split_date <= as_of_date` の範囲に限定して乗算し、先読みバイアス（未来の株式分割適用）を厳禁とする。
        - `DoubleBottom` / `DoubleTop` の $O(N)$ 高速パスと逐次パスでウィンドウ制限後の結果が完全一致するよう共通ロジック化する。
        - 既存の `evaluation_report_*`（`overall_ranking` 基準）との後方互換を維持しつつ、全通過銘柄サマリーおよび特徴量別分位テーブルを拡張フィールドとして出力する。
    - **推奨案と確認事項 (Open Questions)**:
        - **Q1-1（パターンウィンドウ幅）**: `DoubleBottom` / `DoubleTop` の探索ウィンドウ上限は「直近60営業日（推奨）」「直近45営業日」「直近30営業日」のいずれにするか。
        - **Q1-2（`_lookup_set` のフォールバック方針）**: 当日厳密一致のみ（フォールバック廃止・推奨）をデフォルトとし、設定で旧挙動へ戻せる互換フラグを残す必要があるか。
        - **Q1-3（分位評価の出力トリガー）**: `--mode evaluate` / `--mode backtest` 実行時はデフォルトで分位評価を出力する（推奨）か、明示フラグ（`--quantile-eval` 等）で切り替えるか。
    - **完了条件（テストおよびバックテスト検証方法）**:
        - 各バグ修正・分割調整・分位集計ロジックの単体テストを追加し、全テストがパスすること。
        - 代表銘柄群・複数基準日での `--mode backtest` を実行し、Step 2 以降の比較基準となるベースライン（+5/+20/+60日勝率、平均リターン、MFE/MAE、特徴量別上位20% vs 下位20%スプレッド）を計測・記録すること。

- [x] **PR #2 (Step 2): Phase A テクニカル特徴量・スコア改善 (`feat/phase-a-technical-features`)**
    - **目的**: テクニカル系特徴量の天井飽和・定数化・だまし・高値掴みを解消し、エントリーの「質」と上昇継続性を定量識別できるようにする。
    - **対象スコープ**:
        - [x] **長期・収縮・短期指標の追加（`IndicatorCalculator`）**: `SMA200`、`HIGHEST_HIGH_60`、`HIGHEST_HIGH_250`、`ATR5` / `ATR20`（またはレンジ収縮率）、短期反転オシレーター（`RSI5` 等）のベクトル計算を追加。
        - [x] **トレンド連続スコア＆52週高値位置（`M001`, `T001`）**: `SMA25` / `SMA75` の傾き（5日・20日変化率）の連続スコア化、`(close - SMA75) / SMA75` の適正帯評価（+3%〜+18% 高評価、+25%超過熱減点）、52週高値接近度（`close / HIGHEST_HIGH_250`）およびマルチ期間ブレイク判定の導入。
        - [x] **プライスアクションの質（`P001`, `P002`）**: CLV（`(close - low) / (high - low)`）とヒゲ比率の導入（ブレイク時は `CLV >= 0.6` 高評価＋上ヒゲだまし減点、押し目時は陽線転換・`close > SMA5`・長い下ヒゲを反発確認として加味）、ギャップアップ過熱（`gap_pct` 過大）ペナルティの導入。
        - [x] **VCP 収縮＆定常リスク（`R001`）**: ボラティリティ収縮率（`ATR5 / ATR20` 等）、定常 `ATR%`（`ATR14 / close`）による高ボラ減点、押し目時のリスクリワード余地比評価の導入。
        - [x] **出来高の質拡充（`V001`）**: 押し目調整中の売り枯れ→反発出来高増パターン評価（押し目戦略への反映含む）、Up/Down Volume Ratio（過去20〜60日）の導入。
        - [x] **オシレーター非線形化（`O001`）**: `RSI14` の単調増加評価を改め、押し目適正帯（40〜60）およびブレイク適正帯（55〜75）のベル型評価（`> 80` 減点）＋短期反転トリガーを導入。
        - [x] **スコア統合・重み調整**: `S002_StrategyScore` および `config/screening.yaml` に新指標・新ペナルティ・戦略別重みを反映。
    - **変更予定ファイル**:
        - `src/indicator_calculator/calculator.py`
        - `src/feature_engine/features/moving_average/ma_alignment_score.py`
        - `src/feature_engine/features/trend.py`（整理・統合対象）
        - `src/feature_engine/features/price_action/pullback_score.py`, `breakout_score.py`
        - `src/feature_engine/features/risc/volatility_score.py`
        - `src/feature_engine/features/volume/volume_score.py`
        - `src/feature_engine/features/oscillator/momentum_score.py`
        - `src/score_engine/scores/strategy.py`
        - `src/config/screening_config.py`, `config/screening.yaml`
        - 関連単体テストおよび仕様書（`docs/specifications/indicators.md`, `feature_list.md`, `scoreing.md`）
    - **設計上の決定事項**:
        - 新規指標は `IndicatorCalculator` の単一 DataFrame ベクトル演算パスへ統合し、`latest_only_per_symbol=True` 時の「全履歴配列参照・対象インデックスのみ評価」契約（`src/common/indexing.py`）と先読みバイアス遮断を維持する。
        - `M001` / `T001` の連続スコア化に伴い `trend_env_score` の分布が変化するため、第1関門閾値（現行 `min_trend_env_score: 50.0`）との整合を検証して必要に応じ調整する。
    - **推奨案と確認事項 (Open Questions)**:
        - **Q2-1（RSI ベル型評価の適用層）**: 押し目とブレイクで理想 RSI14 帯が異なるため、`O001_MomentumScore` は中立指標・メタデータ（`rsi14`, `short_rsi`）を出力し、戦略別のベル型スコアリングは `StrategyScoreCalculator` 側で計算する構成（推奨）でよいか。
        - **Q2-2（過熱・ギャップ閾値の初期値）**: `(close - SMA75) / SMA75` 適正帯 `+3%〜+18%`（`+25%超` 減点）、ギャップアップ過熱 `+7%超` 減点を初期値として `config/screening.yaml` で外出し設定とする形でよいか。
        - **Q2-3（レガシー `F001_TrendStrength` の扱い）**: `src/feature_engine/features/trend.py` の `F001_TrendStrength` を `T001_TrendStrengthScore` に統合・廃止する（推奨）か、互換のため残置するか。
        - **Q2-4（短期反転オシレーターの選定）**: 既存の `_compute_rsi` をそのまま流用できる `RSI5`（推奨）を採用するか、`RCI9` を新規実装するか。
    - **完了条件（テストおよびバックテスト検証方法）**:
        - 新規指標・全改修特徴量・`S002_StrategyScore` の単体テスト追加、ベクトル計算と逐次計算の一致確認、および全テストのパス。
        - Step 1 と同一条件の `--mode backtest` を実行し、+5 / +20 / +60 営業日の勝率・平均リターン・MFE・MAE の改善、および上位20銘柄で `M001` / `T001` が定数化（ユニーク数=1）しないことを定量確認する。

- [x] **PR #3 (Step 3): Phase A 財務データ拡張・`F004`/`F005` 刷新 (`feat/phase-a-fundamental-expansion`)**
    - **目的**: ローカルに保存済みのキャッシュフロー・株主還元・BS/PL 未抽出列を活用し、定数化していた `F004` と 3 値離散だった `F005` の識別力を回復する。
    - **対象スコープ**:
        - [x] **財務 JSON・未抽出列の読込拡張（`DataCollector`, `FinancialModel`）**: `0000-fy-cash-flow-statement.json`（営業CF, 投資CF, 財務CF, 設備投資, 現金同等物, 営業CFマージン）、`0015〜0025-fy-stock-dividend.json`（一株配当, 剰余金の配当, 自社株買い, 配当性向, 総還元性向, 純資産配当率）、BS 未抽出列（純資産, 株主資本, 利益剰余金, 短期借入金, 長期借入金）、PL 未抽出列（経常利益）を追加取得。
        - [x] **`F004_FinancialHealthScore` 刷新**: ネットキャッシュ比率 `((現金同等物 - 有利子負債) / 総資産)` および自己資本比率水準を連続/多段階で評価し、100点定数化を解消。
        - [x] **`F005_EarningsQualityScore` 刷新**: `営業CF / 純利益`（アクルーアルズ）、`フリーCF = 営業CF - 設備投資`、営業CFマージンを導入し、`net_profit / operating_profit` の理想帯を日本の実効税率水準に合わせて補正。
        - [x] **株主還元モメンタムのスコア化**: 連続増配傾向・自社株買い実績・総還元性向を評価軸へ追加（`F006_ShareholderReturnScore` 新設）。
    - **変更予定ファイル**:
        - `src/model/data_models.py`
        - `src/data_collector/collector.py`
        - `src/feature_engine/features/fundamental/financial_health_score.py`
        - `src/feature_engine/features/fundamental/earnings_quality_score.py`
        - （設計確定時）`src/feature_engine/features/fundamental/shareholder_return_score.py`, `src/score_engine/scores/strategy.py`
        - 関連単体テストおよび仕様書（`docs/specifications/features/feature_list.md`）
    - **設計上の決定事項**:
        - 新規 JSON 読込は既存の IR BANK キャッシュ機構（インメモリキャッシュ・ネガティブキャッシュ・`allow_download` / `read_only` 制御・`as_of_date` 開示ラグ判定）に統合し、並列ワーカーの読み取り専用制約を厳守する。
        - 金融業など CF 項目・借入金項目が欠損する銘柄では例外や 0 点固定にせず、取得可能項目での再配分または中立点フォールバックを適用する。
    - **推奨案と確認事項 (Open Questions)**:
        - **Q3-1（株主還元の特徴量構成）**: 新規特徴量 `F006_ShareholderReturnScore` として独立させ `FUNDAMENTAL_FEATURE_IDS` へ追加する（推奨：分位評価で単体寄与を計測可能）か、`F004` / `F005` 内に組み込むか。
        - **Q3-2（`F004` の配点バランス）**: 「自己資本比率（40点）＋ネットキャッシュ比率（40点）＋有利子負債/利益剰余金健全性（20点）」を推奨案としてよいか。
        - **Q3-3（`F005` の `net_profit / operating_profit` 理想帯）**: 現行 `0.8〜1.2` から実効税率水準の `0.60〜0.80`（推奨）へ引き下げてよいか。
    - **完了条件（テストおよびバックテスト検証方法）**:
        - 拡張財務データのロード（欠損・開示ラグ・`read_only` 含む）および刷新版 `F004` / `F005`（＋必要に応じ `F006`）の単体テスト追加と全テストパス。
        - `--mode backtest` で Step 2 時点からの勝率・リターン・分位スプレッド改善、および上位20銘柄における `F004` / `F005` の分散回復を確認する。

- [x] **PR #4 (Step 4): Phase B 相対力（RS）・業種モメンタム・地合いレジーム (`feat/phase-b-relative-strength-and-regime`)**
    - **目的**: 市場全体（TOPIX）および 33業種（`sector_33`）との相対力、ならびに市場地合いレジーム判定を導入し、市場βによる連れ高除外と地合い悪化局面でのブレイクアウトダマシ抑制を実現する。
    - **対象スコープ**:
        - [x] **市場ベンチマーク（`1306.T`）取得・共有**: 市場全体の 20日/60日/120日リターンおよび `SMA25` / `SMA75` 位置を取得・参照。
        - [x] **対 TOPIX 相対力（RS）**: 銘柄リターン − TOPIX リターン（20日/60日/120日）および分析ユニバース内の RS パーセンタイル順位を算出（押し目買い戦略では正の RS 補正を `pullback_rs_positive_factor` で抑制）。
        - [x] **33業種モメンタム＆業種内相対評価**: `sector_33` ごとに業種平均20日リターン・`SMA25` 上回り銘柄率を集計し、業種モメンタムおよび業種内相対バリュエーション（Zスコア/パーセンタイル）を補正点として評価。
        - [x] **地合いレジーム（Market Breadth）**: ユニバース全体の `close > SMA25` 比率と TOPIX トレンド（および極端 Breadth `< 35%` 二極化ガード）から地合いレジームを判定し、悪化時にブレイクアウト閾値を動的引き上げ＋ブレイクアウト減点を適用。
        - [x] **（Q4-4 方針確定）規模区分（`scale`）別正規化**: 検証切り分けのため本 PR には含めず、別 PR へ分離。
    - **変更予定ファイル**:
        - `src/model/data_models.py`
        - `src/data_collector/collector.py`
        - ユニバース横断コンテキスト算出モジュール（例：`src/score_engine/market_context.py` 等を新設）
        - `src/score_engine/scores/strategy.py`, `src/screener/screener.py`, `src/main.py`, `src/pipeline_worker.py`
        - `src/config/screening_config.py`, `config/screening.yaml`
        - 関連単体テストおよび仕様書
    - **設計上の決定事項**:
        - **先読みバイアス防止＆並列ワーカー整合性**: RS ランク・業種モメンタム・Market Breadth は複数銘柄横断の計算となるため、`ProcessPoolExecutor` の個別銘柄ワーカー内では算出せず、親プロセス側で基準日 `d` 以前のデータのみから事前集計した読み取り専用 `MarketContext` を構築し、スコア計算・スクリーニング段階へ注入する。
        - 少銘柄指定実行（単体テストや少数銘柄検証）時は、ユニバース統計が不安定になるのを防ぐため最小銘柄数ガードを設け、未達時は中立・無補正へ安全にフォールバックする。
    - **推奨案と確認事項 (Open Questions)**:
        - **Q4-1（ベンチマーク銘柄）**: 既存の営業日プリチェックでも使用している `1306.T`（TOPIX連動型ETF・推奨）を基準指数として統一使用してよいか。
        - **Q4-2（地合い悪化時の制御方式）**: Market Breadth 低下時（例：`close > SMA25` 比率 `< 40%` かつ TOPIX `< SMA25`）はブレイクアウトの要求スコア閾値を動的に引き上げる（推奨：例 `+5〜+10` 点）か、ブレイクアウト候補を全面停止するか。
        - **Q4-3（業種内相対バリュエーションの統合方法）**: `F003_ValuationScore` の絶対評価は維持し、業種内相対 Z スコアは `MarketContext` 経由の補正点として加算する（推奨）か、`F003` 本体を業種相対へ置き換えるか。
        - **Q4-4（`scale` 規模区分補正の扱い）**: Step 4 に同時実装するか、検証切り分けのため別 PR へ分離するか（推奨：最小限の基準補正のみ含めるか別 PR 分離）。
    - **完了条件（テストおよびバックテスト検証方法）**:
        - 基準日厳密分離された `MarketContext` 構築、RS ランク・業種モメンタム・Market Breadth・少銘柄フォールバックの単体テスト追加と全テストパス。
        - 上昇相場・調整相場を含む複数基準日での `--mode backtest` を実行し、地合い悪化局面でのブレイクアウト勝率・MAE の改善、および RS 上位群の勝率優位性を検証する。

### 3.6. フェーズ6: 後段AI（Gemini / Skill）連携基盤・高密度ブリーフ出力 (計画中・1要件1PR構成)

`docs/GeminiPrompt.md` で運用している後段 AI（iPhone Gemini アプリ / Skill 定期実行）とシームレスに連携し、1次スクリーニング結果から判断材料（レジサポ・直近15日OHLCV・33業種ローテーション・既存監視銘柄の最新状態）を過不足なく引き渡せるようにする。また、当面は手元 Mac（Google ドライブ デスクトップ同期フォルダ出力）で運用を開始し、将来的な GitHub Actions 完全無人実行（Drive API 連携）へ段階的に移行できる構成とする。

- [x] **PR #1: Gemini 連携用高密度ブリーフ出力・監視銘柄同梱・Googleドライブ同期フォルダ出力 (`feat/gemini-brief-report`)**
    - **目的**: 既存の `screening_report_*` の互換性を維持したまま、Gemini アプリへそのまま添付・同期して2次選別および既存監視銘柄の A〜D 判定を行える高密度 Markdown ブリーフ（`gemini_brief_YYYY-MM-DD.md` + `gemini_brief_latest.md`）、Google ドライブ同期フォルダへの自動コピー、および専用運用プリセット（`config/screening_gemini.yaml`）を整備する。
    - **対象スコープ**:
        - [x] **株価上限（`max_close`）フィルタの追加**: `PreScreeningCriteria` に `max_close: Optional[float] = None` を追加し、`--config config/screening_gemini.yaml`（東証プライム、20日平均売買代金 30億円以上、`max_close: 5000.0`＝1単元 50万円以下）で実運用条件を適用可能にする。
        - [x] **多層レジサポ＆価格帯別出来高 POC・MA傾き算出**: 直近 15営業日 OHLCV、SMA5/25/75/200（価格・乖離率・傾き）、20日/60日/250日高値・安値、直近スイング高安（押し安値・戻り高値）、直近60日価格帯別出来高 POC、1単元必要資金・20日平均売買代金・`+3%` ギャップ上限目安をブリーフ向けに構造化抽出する（`as_of_date` 以前のバーのみ参照し先読み厳禁）。
        - [x] **市場環境・33業種ローテーション表**: `MarketContext`（地合いレジーム・Breadth・`1306.T` 状態・33業種モメンタム上位/下位ランキング）をブリーフ冒頭へ出力する。
        - [x] **既存監視銘柄（`--watch-symbols` / 監視設定）の同梱**: スクリーニング上位外の監視銘柄についても同一フォーマットの最新判断材料（OHLCV 15日・支持線/抵抗線・MA位置・流動性・現在スコア）を別セクションへ出力する。
        - [x] **Gemini 専用ブリーフ出力＆Google ドライブ同期フォルダ連携（方式A）**: `output.formats`（例：`gemini`）および `output.gemini_brief_copy_dir` / CLI（`--gemini-brief`, `--brief-copy-dir`）で `gemini_brief_YYYY-MM-DD.md` / `gemini_brief_latest.md` を出力し、Google ドライブ同期フォルダへ自動コピーする（未マウント時は警告ログに留めローカル出力を保護）。
    - **変更予定ファイル**:
        - `src/screener/pre_screener.py`, `src/pipeline_worker.py`
        - `src/presentation/presenter.py`, `src/presentation/gemini_brief.py`（ブリーフ生成と配信・コピーを分離）
        - `src/config/screening_config.py`, `config/screening_gemini.yaml`（新規）
        - `src/main.py`
        - 関連単体テスト・結合テストおよび仕様書
    - **設計上の決定事項**:
        - 既存の `screening_report_*` や `config/screening.yaml`、および並列ワーカーの読み取り専用制約は一切破壊しない。
        - 監視銘柄データやブリーフ用OHLCV/レジサポ抽出は `as_of_date` 以前のスライスのみを使用し、先読みバイアスを完全に遮断する。
        - 将来の GitHub Actions 移行（PR #2）を見据え、ブリーフ生成処理と配信（ファイルコピー / API アップロード）の責務を分離する。
    - **完了条件（テストおよび動作確認）**:
        - `max_close` フィルタ、スイング高安/POC/MA傾き算出、監視銘柄同梱、`gemini_brief_*.md` / `latest` 出力、コピー先フォールバックの単体・結合テストを追加し全テストがパスすること。
        - 実際に `--config config/screening_gemini.yaml` 等で実行し、`gemini_brief_*.md` が `docs/GeminiPrompt.md` の判断材料要件を満たすことを確認する。

- [ ] **PR #2: GitHub Actions 定期実行＆Google Drive API 直接アップロード (`feat/github-actions-drive-sync`)**
    - **目的**: 手元 Mac がスリープ／オフラインの状態でも、平日大引け後に GitHub Actions 上で自動スクリーニングを実行し、個人 Google アカウントのマイドライブへ最新ブリーフを自動アップロードできるようにする。
    - **対象スコープ**:
        - [x] **Google Drive API 直接アップロードアダプタ（`GoogleDriveBriefDelivery`）実装**:
          - `src/presentation/gemini_brief.py` の `BriefDeliveryBackend` プロトコルを実装。
          - 追加パッケージを入れず既存の `requests` で Google Drive REST API v3（OAuth 2.0 トークン更新・フォルダ内同名検索・multipart 新規作成 `files.create` / 上書き更新 `files.update`・指数バックオフリトライ）を直接実装する。
          - `gemini_brief_latest.md` 等は指定フォルダ内で同名検索し、存在すればファイル ID を維持して上書き更新、なければ新規作成する（重複防止・外部参照維持）。
        - [x] **CLI / Presenter 連携**:
          - `src/main.py`, `src/presentation/presenter.py`, `src/config/screening_config.py` に Drive API 配信オプション（`--brief-drive-folder-id`, `--strict-brief-delivery` / 環境変数 `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, `GOOGLE_DRIVE_REFRESH_TOKEN` 等）を統合。
          - 複数バックエンド併用時のキー分離、カンマ・空白区切り `WATCH_SYMBOLS` 分割、およびコールドスタート時の IR BANK 事前ウォームアップを実装。
        - [x] **GitHub Actions ワークフロー（`.github/workflows/daily_gemini_brief.yml`）構築**:
          - 実行タイミング: 平日 JST 16:30（`cron: '30 7 * * 1-5'`）の定期実行＋`workflow_dispatch` 手動実行（`watch_symbols`, `as_of_date`, `update_master`, `skip_drive_upload`）。
          - キャッシュ引き継ぎ: `actions/cache`（`key: atlas-data-${{ github.run_id }}` / `restore-keys: atlas-data-`）により `data/price/`, `data/financial/`, `data/master/`（合計約 60MB）を引き継ぎ、初回・長期連休後の失効時は `--update-master` 自動付与等により再取得する（3.3GB の `data/cache/` は対象外）。
          - 監視銘柄の受け渡し: `workflow_dispatch` 入力 ＞ GitHub Repository Variables（`WATCH_SYMBOLS`） ＞ `config/screening_gemini.yaml` の優先順位で `--watch-symbols` を適用する。
          - 出力ファイル（`output/gemini_brief_*.md` 等）を Actions Artifacts にも保存する（Drive 配信失敗時もローカル出力・キャッシュ・Artifacts を保全）。
        - [x] **運用・セットアップ手順書整備**:
          - `docs/specifications/github_actions_drive_sync.md` に OAuth 2.0 リフレッシュトークン取得手順、GitHub Secrets / Variables 設定一覧、および「7日失効防止のため OAuth 同意画面を本番公開にする」運用注意点を記載する。
    - **変更ファイル**:
        - `.gitignore`（`.github/workflows/` のみ追跡許可）
        - `config/screening_gemini.yaml`
        - `src/presentation/gemini_brief.py`（`GoogleDriveBriefDelivery` 追加）
        - `src/presentation/presenter.py`, `src/main.py`, `src/config/screening_config.py`
        - `.github/workflows/daily_gemini_brief.yml`（新規）
        - `docs/specifications/github_actions_drive_sync.md`, `docs/_plan.md`
        - 関連単体・結合テスト（`test_gemini_brief.py`, `test_presenter.py`, `test_screening_config.py`, `test_pipeline_integration.py`）
    - **設計上の決定事項**:
        - 個人マイドライブはサービスアカウントによる新規ファイル作成が不可（Storage Quota 制約）のため、**OAuth 2.0（リフレッシュトークン）** を採用する。
        - 依存関係の肥大化・CI 速度低下を避けるため `google-api-python-client` 等は追加せず、`requests` で直接 REST API v3 を実装する。
        - 既存の `LocalCopyBriefDelivery`（方式A）およびローカル出力・並列ワーカー制約・先読みバイアス防止は一切破壊しない。
    - **完了条件（テストおよび動作確認）**:
        - [x] `GoogleDriveBriefDelivery` の単体テスト（トークン更新、同名検索ヒット時の `update`、未ヒット時の `create`、API エラー・リトライ時の挙動）および既存全テストがパスすること。
        - [x] GitHub Actions ワークフロー YAML の構文・ステップが整合していること。
        - [ ] （Secrets 登録後にユーザー環境にて実施）`workflow_dispatch` で実データ実行〜Drive アップロードまで疎通確認できること。

## 4. 今後のマイルストーン
- [x] 2026/08/31: フェーズ2の「特徴量・パターン追加およびパイプライン結合」完了
- [x] 2026/11/15: 要件見直し（v0.2.0）および1要件1PR計画の策定完了（PR #1）
- [x] 2026/11/16: フェーズ3 PR #2〜#5 の順次実装・検証完了
- [x] 2026/11/18: フェーズ4 PR #1〜#4（銘柄評価高速化・スケーラビリティ改善）の順次実装・検証完了
- [x] フェーズ5 PR #1（Step 1）: データ修正・検証基盤強化＆ベースライン計測
- [x] フェーズ5 PR #2（Step 2）: Phase A テクニカル特徴量・スコア改善
- [x] フェーズ5 PR #3（Step 3）: Phase A 財務データ拡張・`F004`/`F005` 刷新＆`F006` 新設
- [x] フェーズ5 PR #4（Step 4）: Phase B 相対力（RS）・業種モメンタム・地合いレジーム導入
- [x] フェーズ6 PR #1: 後段AI（Gemini / Skill）連携向け高密度ブリーフ出力・監視銘柄追跡・Googleドライブ同期フォルダ連携
- [ ] フェーズ6 PR #2（将来拡張）: GitHub Actions 自動定期実行＆Google Drive API 直接アップロード

## 5. 実行ログ (最新の作業のみ記載)
- 2026/11/20: フェーズ6 PR #1（`feat/gemini-brief-report`）を実施。`PreScreeningCriteria` へ `max_close` を追加し、`config/screening_gemini.yaml`（東証プライム・20日平均売買代金30億円以上・`max_close: 5000.0`・`formats: ["json", "markdown", "gemini"]`）を新設。`src/presentation/gemini_brief.py` にて先読みバイアスを遮断した多層レジサポ（SMA5/25/75/200 傾き、20/60/250日高安、確定スイング高安、60日価格帯別出来高 POC、直近15営業日 OHLCV、1単元資金、+3%上限目安）、市場環境・33業種モメンタム表、既存監視銘柄同梱、およびローカルコピー配信分離（`LocalCopyBriefDelivery`、未マウント時は警告ログに留めローカル出力保護）を実装し、`src/presentation/presenter.py` と `src/main.py`（`--gemini-brief`, `--brief-copy-dir`, `--watch-symbols`）へ統合。全テスト373件（+4サブテスト）パスを確認。
- 2026/11/20: フェーズ5完了後のスコア重み・閾値チューニング（`feat/tune-phase5-weights-and-thresholds`）を実施。全通過銘柄の特徴量別分位スプレッド分析（奇数月7日探索＋偶数月7日ホールドアウト）に基づき、`StrategyScoreConfig` へファンダメンタルズ特徴量別の相対重み（`fundamental_weight_f001〜f006`、コード既定は後方互換の均等 `1.0`、欠損時自動再配分・非正/非有限ガード付き）を追加し、`config/screening.yaml` を最適化した（ファンダ重み: `F003=0.50, F002=0.20, F006=0.15, F001/F004/F005=0.05`、押し目/ブレイクのファンダ配分 `0.10→0.22`、`breakout_weight_v001: 0.35→0.22`、`double_bottom_bonus_max: 10.0→6.0`、`MarketContext` 補正上限 `rs: 4.5, sector_momentum: 2.5, relative_valuation: 5.5, total_cap: 10.0`）。全テスト364件（+4サブテスト）パスを確認。
  - **探索セット（奇数月7基準日 `2025-07-01 〜 2026-07-01`・140件・Step 1〜4 と同一条件）**:
    - 全体: `+5日` 勝率 `62.14%`（Step 4比 +2.85%pt）/ 平均 `+0.56%` / MAE `-3.33%`、`+20日` 勝率 `62.86%`（+5.72%pt）/ 平均 `+2.20%` / MAE `-5.63%`、**`+60日` 勝率 `77.14%`（Step 4 `70.00%` 比 +7.14%pt / Step 1 `63.57%` 比 +13.57%pt）/ 平均 `+12.15%`（中央値 `+11.27%`）/ MFE `+22.03%` / MAE `-7.47%`**。
    - 戦略別（+60日）: 押し目買い型（89件）勝率 `77.53%` / 平均 `+12.30%` / MAE `-6.98%`、ブレイクアウト型（51件）勝率 `76.47%`（Step 4比 +13.97%pt）/ 平均 `+11.88%`（+7.64%pt）/ MAE `-8.32%`（+4.66%pt改善）。
  - **ホールドアウト検証セット（偶数月7基準日 `2025-08-01 〜 2026-08-03`・140件・未見期間）**:
    - 全体: `+5日` 勝率 `74.29%`（Step 4 `67.86%` 比 +6.43%pt）/ 平均 `+3.33%` / MAE `-2.28%`、`+20日` 勝率 `70.00%`（+3.57%pt）/ 平均 `+5.89%` / MAE `-4.28%`、**`+60日` 勝率 `66.43%`（Step 4 `61.43%` 比 +5.00%pt）/ 平均 `+9.76%`（中央値 `+6.69%`）/ MFE `+22.24%` / MAE `-6.87%`**（7基準日中6日で改善・低下日0日）。
- 2026/11/20: フェーズ5 PR #4（Step 4: `feat/phase-b-relative-strength-and-regime`）を実施。`src/score_engine/market_context.py`（`MarketContextConfig`, `extract_symbol_market_snapshot`, `compute_benchmark_metrics`, `build_market_context`）および読み取り専用 `MarketContextModel`（`frozen=True`）を新設し、並列ワーカー外（親プロセス側）で基準日 `d` 以前のデータのみからベンチマーク `1306.T`・対 TOPIX RS パーセンタイル順位（120日欠損フォールバック＆押し目買い戦略向け正の RS 抑制 `pullback_rs_positive_factor=0.3`）・33業種モメンタム・業種内相対バリュエーション（対数PER/対数PBR/ROE Zスコア）・Market Breadth 地合いレジーム（`breadth < 0.40` かつ TOPIX `< SMA25` または極端悪化 `breadth < 0.35` で `bearish` 判定し、ブレイクアウト要求閾値 `+8.0` 点引上げ＆ブレイクアウト減点 `6.0` 点を適用）を構築し、`StrategyScoreCalculator` と `Screener` へ注入（少銘柄/少業種/ベンチマーク欠損時安全フォールバック・`scale` 補正は Q4-4 に基づき別 PR 分離）。さらに `ForwardReturnEvaluator` / `Presenter` へ `MC_RS_Rank` / `MC_SectorMomentum` / `MC_RelativeValuation` 分位評価と地合いレジームサマリー出力を統合。全テスト363件（+4サブテスト）パスを確認。
  - **Step 4 バックテスト検証結果**（Step 1〜3 と同一条件：7基準日・1,776銘柄・`--no-irbank-download`、所要 `15.140s`）:
    - **上位抽出（140件）**: `+5日` 勝率 `59.29%` / 平均 `+0.25%`（中央値 `+0.88%`） / MFE `+3.91%` / MAE `-3.54%`、 `+20日` 勝率 **`57.14%`（Step 3比 +0.71%pt）** / 平均 `+1.20%`（中央値 `+1.25%`） / MFE `+8.11%` / MAE `-6.11%`、 **`+60日` 勝率 `70.00%`（Step 3比 +0.71%pt / Step 1比 +6.43%pt） / 平均 `+9.88%`（Step 3比 +1.68%pt、中央値 `+9.27%`） / MFE `+19.91%` / MAE `-8.01%`**。
    - **戦略別（+60日）**: **押し目買い型（116件）勝率 `71.55%`（Step 3比 +0.46%pt） / 平均 `+11.04%`（+1.89%pt） / MAE `-6.99%`**、**ブレイクアウト型（24件）勝率 `62.50%`（Step 3比 +12.50%pt） / 平均 `+4.24%`（Step 3 `-2.00%` 比 +6.24%pt） / MFE `+21.56%` / MAE `-12.98%`**。
    - **全通過銘柄プール（1,898件）における新指標分位スプレッド（+60日 上位20% vs 下位20%）**: `MC_SectorMomentum` (`unique=173`, 上位 `69.52%`/`+11.72%` vs 下位 `55.88%`/`+3.02%`, **リターン差 `+8.70%` / 勝率差 `+13.64%pt`**)、`MC_RelativeValuation` (`unique=1869`, 上位 `66.04%`/`+10.04%` vs 下位 `55.88%`/`+3.58%`, **+60日リターン差 `+6.46%` / +20日リターン差 `+2.96%` [+11.23%pt]**)、`MC_RS_Rank` (`unique=1896`, 上位 `63.32%`/`+8.19%` vs 下位 `51.45%`/`+2.03%`, **リターン差 `+6.16%` / 勝率差 `+11.87%pt`**)。
    - **地合い悪化レジーム判定（`2026-05-01`）**: ユニバース Breadth `33.3%`（`< 35%` 極端低下ガード）で `bearish`（BO閾値+8・BOスコア-6）が発動し、`+60日` 勝率 `50.00%`（平均 `+0.69%`）から `55.00%`（平均 `+1.82%`）へ改善。
- 2026/11/19: フェーズ5 PR #3（Step 3: `feat/phase-a-fundamental-expansion`）を実施。`FinancialModel`（22項目追加）と `DataCollector`（BS/PL未抽出列・CFデータ・配当履歴・連続増配/非減配/3年自社株買い回数・先読みバイアス遮断＆`capex` 負値対応・`warmup_irbank_cache` 拡張）を拡張し、`F004_FinancialHealthScore`（自己資本比率40・ネットキャッシュ比率40・有利子負債/利益剰余金20・借入金欠損時誤評価防止）、`F005_EarningsQualityScore`（営業CF裏付け35・FCF25・営業CFマージン15・実効税率理想帯`0.60〜0.80`整合性15・レバレッジ10）を刷新、さらに `F006_ShareholderReturnScore` を新設して `FUNDAMENTAL_FEATURE_IDS` へ統合（登録特徴量 `12→13`）。全テスト350件（+4サブテスト）パスを確認。
  - **Step 3 バックテスト検証結果**（Step 1/2 と同一条件：7基準日・1,776銘柄・`--no-irbank-download`、所要 `14.881s`）:
    - **上位抽出（140件）**: `+5日` 勝率 `60.00%` / 平均 `+0.98%`（Step 2比 +0.24%pt） / MFE `+4.16%` / MAE `-2.89%`、 `+20日` 勝率 `56.43%` / 平均 `+1.59%`（+0.22%pt） / MFE `+8.33%` / MAE `-5.44%`、 **`+60日` 勝率 `69.29%`（Step 2比 +0.72%pt / Step 1比 +5.72%pt） / 平均 `+8.20%`（中央値 `+9.54%` vs Step 2 `+7.86%`） / MFE `+18.30%` / MAE `-7.59%`**（押し目買い型 128件は `+60日` 勝率 `71.09%` / 平均 `+9.15%`）。
    - **全通過銘柄プール（1,780件）における対象特徴量ユニーク数・分位スプレッド（上位20% vs 下位20%）**: `F004` (`unique: 1→832`, +60日 `-4.10%`/`-6.74%`), `F005` (`unique: 5→818`, +60日 `+0.04%`/`-5.90%`), `F006` (`unique: 850`, +20日 `+0.11%`/`-0.56%`, +60日 `-0.59%`/`+1.69%`) と定数化・離散化を完全解消。
- 2026/11/19: フェーズ5 PR #2（Step 2: `feat/phase-a-technical-features`）を実施。`IndicatorCalculator` に `SMA200`/`HIGHEST_HIGH_60`/`HIGHEST_HIGH_250`/`ATR5`/`ATR20`/`RSI5` を追加、`F001_TrendStrength` を `T001` へ統合廃止し、`M001`/`T001`/`P001`/`P002`/`R001`/`V001`/`O001` の連続スコア化・質評価（CLV・ヒゲ・ギャップ過熱・VCP収縮・Up/Down出来高・売り枯れ反発・ベル型RSI）および `S002_StrategyScore`（戦略別RSIベル型、`RSI5` 短期反転、`SMA75` 乖離過熱、ギャップ過熱、設定外出し）を実装。全テスト321件（+4サブテスト）パスを確認。
  - **Step 2 バックテスト検証結果**（Step 1 と同一条件：7基準日・1,776銘柄・`--no-irbank-download`）:
    - **上位抽出（140件）**: `+5日` 勝率 `60.00%` / 平均 `+0.74%` / MFE `+3.92%` / MAE `-3.00%`、 `+20日` 勝率 `56.43%` / 平均 `+1.37%` / MFE `+8.09%` / MAE `-5.51%`、 **`+60日` 勝率 `68.57%`（Step 1比 +5.00%pt） / 平均 `+8.34%`（+1.81%pt） / MFE `+18.61%` / MAE `-7.61%`**（うち押し目買い型 129件は `+60日` 勝率 `70.54%` / 平均 `+9.36%`）。
    - **全通過銘柄プール（1,839件）における主要改善特徴量スプレッド（上位20% vs 下位20%・ユニーク数）**: `M001` (`unique: 3→1817`, +60日 `+0.27%`), `T001` (`unique: 11→1792`, +20日 `+3.00%`/`+7.08%`, +60日 `+2.35%`/`+15.53%`), `O001` (+20日 `+3.27%`/`+10.63%`, +60日 `+2.52%`), `P002` (+60日 `+3.01%`/`+13.35%`), `P001` (+60日 `+1.75%`/`+12.26%`), `R001` (+5日 `+1.92%`/`+19.35%`, +20日 `+1.60%`), `V001` (`unique: 16→1837`)。
- 2026/11/19: フェーズ5 PR #1（Step 1: `fix/data-integrity-and-quantile-eval`）を実施。`DataCollector.collect_financial_data()` の `stock_splits` 累積分割調整（`fiscal_date < split_date <= as_of_date`・異常値ガード）＆成長率欠損の `None` 維持、`V001_VolumeScore` の当日除外（`t-25 〜 t-1`）、`HammerPattern.is_close_to_high` 修正、`DoubleBottom` / `DoubleTop` の直近60営業日ウィンドウ制限、`RankingGenerator` の `strict_date_match=True` デフォルト化、`1301.T.parquet` 先頭5行ダミー除去、および `--mode evaluate` / `--mode backtest` 向け全通過銘柄＆特徴量別分位評価（上位20% vs 下位20%）を実装し、全テスト313件（+4サブテスト）パスを確認。
  - **Step 1 ベースライン計測結果**（`--mode backtest --as-of-dates 2025-07-01 2025-09-01 2025-11-04 2026-01-05 2026-03-02 2026-05-01 2026-07-01 --end-date 2026-11-18 --no-irbank-download`、対象1,776銘柄・7基準日）:
    - **上位抽出（140件）**: `+5日` 勝率 `65.71%` / 平均 `+1.15%` / MFE `+3.98%` / MAE `-2.30%`、 `+20日` 勝率 `62.86%` / 平均 `+2.46%` / MFE `+7.79%` / MAE `-4.45%`、 `+60日` 勝率 `63.57%` / 平均 `+6.53%` / MFE `+16.91%` / MAE `-6.75%`。
    - **全通過銘柄プール（2,442件）**: `+5日` 勝率 `53.85%` / 平均 `-0.57%` / MFE `+3.57%` / MAE `-4.34%`、 `+20日` 勝率 `52.38%` / 平均 `-0.07%` / MFE `+7.67%` / MAE `-6.97%`、 `+60日` 勝率 `61.71%` / 平均 `+6.26%` / MFE `+18.80%` / MAE `-9.70%`。
    - **特徴量別上位20% vs 下位20%スプレッド（+60日 リターン差 / 勝率差・ユニーク数）**: `F003_ValuationScore` (`+13.76%` / `+32.17%`, unique=12), `P002_BreakoutScore` (`+2.91%` / `+9.43%`, unique=2351), `F002_GrowthScore` (`+2.91%` / `-2.87%`, unique=13), `P001_PullbackScore` (`+1.69%` / `+17.62%` [+5日 `+3.02%`/`+20.70%`], unique=1992), `R001_VolatilityScore` (`+0.25%` / `+0.41%`, unique=2314), `T001_TrendStrengthScore` (`-0.60%` / `+2.46%`, unique=11), `F001_TrendStrength` (`-0.73%` / `+6.56%`, unique=3), `F004_FinancialHealthScore` (`-0.94%` / `+4.10%`, unique=1), `O001_MomentumScore` (`-1.07%` / `-3.07%`, unique=2438), `V001_VolumeScore` (`-1.24%` / `-7.17%`, unique=16), `M001_MAAlignmentScore` (`-1.59%` / `+4.51%`, unique=3), `F005_EarningsQualityScore` (`-2.69%` / `-1.23%`, unique=5)。
- 2026/11/18: `docs/reports/feature_improvement_report_2026-11-17.md` の「6. 推奨ネクストステップ（Step 1〜Step 4）」に基づき、フェーズ5（特徴量充足度改善・検証基盤強化）の4 PR 分割実装計画（目的・対象スコープ・変更予定ファイル・設計上の決定事項・Open Questions・完了条件）を策定し、`docs/_plan.md` を更新。
- 2026/11/18: フェーズ4 PR #4（`perf/multiprocess-and-batch-backtest`）を実施。`src/pipeline_worker.py` を新設して `ProcessPoolExecutor`（macOS `spawn` 対応の `init_pipeline_worker`・3レジストリ初期化・完全読取専用制約・決定的順序結合・1銘柄例外隔離）と少銘柄閾値制御（`DEFAULT_PARALLEL_MIN_SYMBOLS=20`・`FEATURE_ENGINE_PARALLEL_PROCESSES` / `--workers`）を `src/main.py` に統合。さらに複数基準日一括バックテストランナー `run_batch_backtest`（CLI `--mode backtest` / `--as-of-dates`）および `BatchBacktestSummaryModel` / `ForwardReturnEvaluator.aggregate_batch_summaries` / `Presenter` 横断レポート出力を実装し、「全期間1回読込・ベクトル指標1回算出・基準日断面厳密分離（未来バー完全遮断・開示ラグ財務対応）」を実現。全テスト277件のパスおよび2段階レビュー（1次 `atlas-reviewer` 指摘修正後・2次 `gemini-4-argon-high` Approve）を完了。
- 2026/11/18: フェーズ4 PR #3（`perf/vectorize-and-latest-only-eval`）を実施。`StorageManager.load_parquet(..., columns=...)` による列限定読込（不在列時のみフォールバック）と `DataCollector.collect_ohlcv_data()` の `NaN`/`inf` クレンジング・`iterrows()` 排除（`OhlcvModel.model_construct`）、`IndicatorCalculator` の単一ベクトル演算統合、`DoubleBottomPattern` / `DoubleTopPattern` の 1パス $O(N)$ 化（`src/pattern_detector/patterns/reversal/_common.py`）、および `src/common/indexing.py` を用いた全13特徴量・全3パターン・`FeatureManager` / `PatternManager`・`src/main.py` 向けの「全履歴参照・対象インデックス（`latest_only_per_symbol=True` 時は最新日）のみ評価」モードを実装。全テスト262件のパスおよび2段階レビュー（1次 `atlas-reviewer` 指摘修正後・2次 `gemini-4-argon-high` Approve）を完了。
- 2026/11/18: フェーズ4 PR #2（`perf/batch-yfinance-and-fetch-check`）を実施。標準ライブラリのみで東証営業日カレンダー（日本の祝日・振替休日・国民の休日・年末年始・JST 15:35 カットオフ判定）を提供する `src/data_collector/market_calendar.py` を新設し、`DataCollector` に開始日休場マージン考慮・`1306.T` 市場最新完了営業日プリチェック（TTL付きキャッシュ）・`yf.download(..., actions=True, threads=True, group_by="ticker")` によるチャンク単位並列取得＋欠損/失敗ティッカー個別リトライを行う `prefetch_ohlcv_batch()` を実装して `src/main.py` に統合。全テスト237件のパスおよび2段階レビュー（1次 `atlas-reviewer` 指摘修正後・2次 `gemini-4-argon-high` Approve）を完了。
- 2026/11/17: フェーズ4 PR #1（`perf/eliminate-redundant-io-and-cache` 相当）を実施。`src/main.py` にフェーズ別時間計測（`timings_sec`・`elapsed_sec`）と `use_feature_cache: bool = False`（CLI `--use-feature-cache`）および `--mode evaluate` 時の全期間 OHLCV 一括取得・`ohlcv_map` 共有（`ForwardReturnEvaluator.compute_default_fetch_end` 共通化・先読みバイアス防止スライス）を実装し、`DataCollector.collect_financial_data()` の `latest_close` 引き渡しによる2回目 OHLCV 読込・通信廃止、`RankingGenerator.generate_strategy_rankings()` のルックアップ1回構築を実施。全テスト215件のパスおよび2段階レビュー（1次 `atlas-reviewer`・2次 `gemini-4-argon-high` Approve）を完了。
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
