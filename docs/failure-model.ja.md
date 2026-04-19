# Failure Model

## Evidence 群

- Out-of-band evidence: GPIO heartbeat freshness
- Network-dependent evidence: host heartbeat file, sentinel facts, ping, SSH

## A. Sentinel-only issue

Signals:

- GPIO heartbeat fresh
- host heartbeat fresh
- SSH reachable
- sentinel stats/state stale

Interpretation:

- OS は生きていて、sentinel 経路が劣化

Action:

- `raspi-sentinel` restart のみ
- 外部 reboot は禁止

## B. Host degraded

Signals:

- GPIO stale または host heartbeat stale
- SSH reachable

Interpretation:

- 応答はあるが制御/進行の劣化あり

Action:

- まず remote OS reboot（`ssh sudo reboot`）

## C. Freeze suspected

Signals:

- GPIO heartbeat stale
- host heartbeat stale
- SSH fail
- 設定された連続サイクルで継続

Interpretation:

- deep freeze / severe hang の疑い

Action:

- GPIO 外部 reboot 候補

## D. Network-only issue

Signals:

- ping/SSH fail（または不安定）
- GPIO heartbeat fresh
- host heartbeat fresh

Interpretation:

- host 生存の可能性が高く、network 経路問題

Action:

- reboot せず observe/notify のみ

## E. Management-plane degraded

Signals:

- GPIO heartbeat fresh
- host heartbeat fresh
- ping ok
- SSH fail

Interpretation:

- host は生存している可能性が高いが、管理プレーン経路のみ劣化している

Action:

- reboot せず observe/notify のみ

## F. Recovery guard states

- `RECOVERY_IN_PROGRESS`: action 実行後で verification 待ち
- `COOLDOWN`: cooldown 終了まで追加 action なし
- `LOCKOUT`: 介入予算超過。手動対応が必要
