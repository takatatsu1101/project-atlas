---
title: 特徴量仕様書
document_id: SPEC-FEATURE-001
version: 0.1.0
status: Draft
project: Project Atlas
author: Takatori Tatsuo
created:
updated:
related:
  - requirements/requirements.md
  - design/feature_engine.md
  - specifications/pattern_spec.md
---

# 特徴量仕様書

## 1. 目的

本書は、Project Atlasで利用するチャート特徴量を定義する。

各特徴量は Feature Engine により算出され、Pattern Detector、Score Engine、および将来のバックテストや機械学習で共通利用する。

本仕様書では「何を算出するか」「どのような考え方で評価するか」を定義する。詳細なアルゴリズム、数式、クラス構成など実装に関する内容は設計書で管理する。

---

## 2. 特徴量カテゴリ

特徴量は責務ごとにカテゴリへ分類する。

| カテゴリID | カテゴリ名 | 説明 |
|------------|------------|------|
| T | Trend | トレンドに関する特徴量 |
| M | Moving Average | 移動平均線に関する特徴量 |
| V | Volume | 出来高に関する特徴量 |
| P | Price Action | 値動きに関する特徴量 |
| S | Support / Resistance | サポート・レジスタンスに関する特徴量 |
| O | Oscillator | RSI・MACD等のオシレーターを用いた価格モメンタム評価 |
| R | Risk | ボラティリティ・リスクに関する特徴量 |
| F | Fundamental | 財務・ファンダメンタルズに関する特徴量 |

## 3. 特徴量一覧

| ID | カテゴリ | 特徴量名 | 説明 | ステータス |
|----|----------|----------|------|------------|
| M001 | Moving Average | MAAlignmentScore | 移動平均線の並び・傾き（5日/20日）・スプレッドの連続評価 | 実装済 |
| P001 | Price Action | PullbackScore | 押し目の理想度（SMA25/75乖離＋陽線転換・CLV・下ヒゲ反発確認） | 実装済 |
| P002 | Price Action | BreakoutScore | ブレイクアウトの強さ（20日/60日高値突破＋CLV・上ヒゲだまし・ギャップ過熱評価） | 実装済 |
| T001 | Trend | TrendStrengthScore | トレンドの強さ（SMA75適正帯・52週高値接近度・マルチ期間ブレイク・SMA200基盤） | 実装済 |
| V001 | Volume | VolumeScore | 出来高の質（急増・短期トレンド・Up/Down Volume Ratio・押し目売り枯れ反発） | 実装済 |
| O001 | Oscillator | MomentumScore | モメンタム評価（RSI14ベル型・MACD・短期反転RSI5メタデータ出力） | 実装済 |
| R001 | Risk | VolatilityScore | リスク・VCP収縮健全性（ATR5/ATR20収縮率・定常ATR%・リスクリワード余地） | 実装済 |
| F001 | Fundamental | ProfitabilityScore | 収益性（ROE・営業利益率など） | 実装済 |
| F002 | Fundamental | GrowthScore | 成長性（EPS・売上・利益CAGRなど） | 実装済 |
| F003 | Fundamental | ValuationScore | 割安性（PER・PBR） | 実装済 |
| F004 | Fundamental | FinancialHealthScore | 財務健全性（自己資本・黒字安定性など） | 実装済 |
| F005 | Fundamental | EarningsQualityScore | 利益の質（本業利益と純利益の整合性など） | 実装済 |

> Note: 旧一覧にあった `R002: RiskScore` および `S001: SupportResistanceScore` は、v0.2.0 要件見直しにより独立した特徴量クラスからは廃止し、`P001` / `P002` / `R001` のメタデータおよび Score Engine・出力層の「後段AI連携用・具体的サポレジ価格水準＆リスク情報」へ統合。

---

## 4. 特徴量仕様

今後、各特徴量は個別仕様書として作成し、以下のテンプレートに従って定義する。

````yaml
---
title: <Feature名>
document_id: SPEC-FEATURE-<Feature ID>
version: 0.1.0
status: Draft
project: Project Atlas
feature_id: <Feature ID>
category: <カテゴリ>
author:
created:
updated:
related:
  - specifications/feature_list.md
  - design/feature_engine.md
---
````

````md
# <Feature名>

## 1. 概要
- Feature ID：
- Feature名：
- 日本語名：
- カテゴリ：
- バージョン：
- ステータス：Draft / Reviewing / Implemented / Verified
- 優先度：P1 / P2 / P3

## 2. 目的
- この特徴量を算出する目的を記載する。
- 採用理由・期待する効果を記載する。

## 3. 前提条件
- 必要なデータ期間
- 前提となる計算結果
- 利用可能条件

## 4. 入力
- 入力データ
- 使用するテクニカル指標
- パラメータ

## 5. 出力
- 型
- 値域
- 値の意味

## 6. アルゴリズム
- アルゴリズム概要（自然言語で処理の流れを記載する）
- 処理手順（自然言語で記載する）
- 算出式の概要（詳細な数式は設計書へ記載する）
- 使用するパラメータ
- 備考

## 7. 判定基準
- 高評価となる条件
- 低評価となる条件
- 正規化方法

## 8. 利用箇所
- 利用モジュール
- 利用目的

## 9. 例外処理
- データ不足時
- 異常値
- エラー時の扱い

## 10. テスト観点
- 正常系
- 境界値
- 異常系
- 期待値（代表的な入力・出力例）

## 11. 今後の拡張
- 改善案
- 将来追加予定
````


---

## 5. 命名規則

- Feature ID はカテゴリごとに採番する（例：T001、V003、P012）。
- 特徴量名は英語（PascalCase）とする。
- 仕様書内では日本語説明を併記する。
- 出力値は原則として 0〜100 に正規化する。
- 特徴量は他の特徴量へ依存しないことを原則とする。

---

## 6. Feature追加ルール

新しいFeatureを追加する場合は以下を満たすこと。

- 一意なFeature IDを採番する
- カテゴリを決定する
- 算出方法を明文化する
- 0〜100へ正規化方法を定義する
- 利用モジュールを明記する
- Score Engineで利用するか判断する
---

## 7. 更新履歴

| バージョン | 内容 |
|------------|------|
| 0.1.0 | 初版作成 |