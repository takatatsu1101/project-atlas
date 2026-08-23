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

- [ ] **M001: MAAlignmentScore (移動平均線の並び評価)**
    - 完了条件:
        - `src/feature_engine/features/moving_average/ma_alignment_score.py` を新規作成し、`IFeature` インターフェースを実装する。
        - 移動平均線の並び（例: 短期 > 中期 > 長期）に基づいてスコアを算出するロジックを実装する。
        - `src/feature_engine/registry.py` に登録する。
        - `tests/unit/feature_engine/test_ma_alignment_score.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [ ] **P001: PullbackScore (押し目の理想度)**
    - 完了条件:
        - `src/feature_engine/features/price_action/pullback_score.py` を新規作成し、`IFeature` インターフェースを実装する。
        - 押し目の理想度を評価するロジックを実装する。
        - `src/feature_engine/registry.py` に登録する。
        - `tests/unit/feature_engine/test_pullback_score.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [ ] **P002: BreakoutScore (ブレイクアウトの強さ)**
    - 完了条件:
        - `src/feature_engine/features/price_action/breakout_score.py` を新規作成し、`IFeature` インターフェースを実装する。
        - ブレイクアウトの強さを評価するロジックを実装する。
        - `src/feature_engine/registry.py` に登録する。
        - `tests/unit/feature_engine/test_breakout_score.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

### 3.2. パターン (`Pattern`) の追加
`docs/specifications/patterns/pattern_list.md` より、以下のP1優先度のパターンを実装します。

- [ ] **R001: DoubleBottom (ダブルボトム)**
    - 完了条件:
        - `src/pattern_detector/patterns/reversal/double_bottom.py` を新規作成し、`IPattern` インターフェースを実装する。
        - ダブルボトムパターンを検出するロジックを実装する。
        - `src/pattern_detector/registry.py` に登録する。
        - `tests/unit/pattern_detector/test_double_bottom.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

- [ ] **R002: DoubleTop (ダブルトップ)**
    - 完了条件:
        - `src/pattern_detector/patterns/reversal/double_top.py` を新規作成し、`IPattern` インターフェースを実装する。
        - ダブルトップパターンを検出するロジックを実装する。
        - `src/pattern_detector/registry.py` に登録する。
        - `tests/unit/pattern_detector/test_double_top.py` を新規作成し、単体テストを実装・実行し、成功することを確認する。
        - `docs/_plan.md` と本計画書を更新する。

## 4. 実行ログ
- (ここに作業の進捗を追記します)

## 5. 改善点・課題 (work/reflection.mdに詳細を記載)
- (ここに実装中に見つかった改善点や課題の概要を記載します。詳細は `work/reflection.md` を参照してください)
