# raspi-revive アーキテクチャ

## スコープ

`raspi-revive` は in-band の `raspi-sentinel` を補完する out-of-band 復旧システムです。

- `raspi-5-agent`: 事実のみを出力
- `raspi-zero-controller`: 判定と介入を担当

runtime 生成物はリポジトリ外に置きます。リポジトリには source / schema / example / config / test のみを保持します。

## 責務分離

### raspi-5-agent（facts producer）

- host heartbeat JSON（`boot_id`, `seq`, `monotonic_sec`, `wall_time` など）を更新
- GPIO heartbeat パルス/トグルを出力
- 収集用 facts（`host-heartbeat`, `sentinel stats/state/events`）を export
- recovery decision は持たない

### raspi-zero-controller（decision + action）

- 複数 probe から観測を収集
- 観測を evidence gate へ正規化
- 明示的 state machine で判定
- 段階的 recovery action を選択
- adapter 経由で action 実行（dry-run 対応）
- controller state（cooldown/lockout/counter/verification 待ち）を永続化
- append-only の audit JSONL を出力

## パイプライン分離

1. 観測収集
2. 観測正規化
3. evidence gate 評価
4. 状態分類
5. action 選択（policy + safety gate）
6. action 実行
7. post-action verification（reboot は `boot_id` 変化を期待）
8. audit logging

## 設計保証

- 証拠を2系統で明示:
  - `out_of_band_evidence`: GPIO heartbeat freshness
  - `network_path_evidence`: host heartbeat file, sentinel facts, ping, SSH
- network-only 障害では外部 reboot しない
- 強い action ほど強い証拠と連続性を要求
- 連続 action は cooldown/lockout で制限
- すべての判定/action を `correlation_id` で追跡可能
- maintenance mode 中は介入を止め、観測/判定/監査は継続

## 前提（MVP）

- Zero は設定パスから agent export ファイルを読める
- GPIO 監視は抽象化（`HeartbeatInput`）で扱い、既定は file-backed 実装
- controller 実行環境で SSH/ping probe が利用可能
