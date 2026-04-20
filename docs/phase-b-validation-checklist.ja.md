# Phase B Validation Checklist

## 1. 前提確認

- リポジトリ方針が observation-first のままであること
- 配備設定が `controller.phase-b.toml` であること
- remote/gpio/power action が無効のままであること

## 2. config 切替

```bash
sudo install -m 0644 \
  <deployment-root>/targets/raspi-zero-controller/config/phases/controller.phase-b.toml \
  /etc/raspi-revive/controller.toml
sudo systemctl restart raspi-revive-controller.service
```

## 3. サービス状態確認

```bash
systemctl status raspi-revive-controller.service --no-pager
journalctl -u raspi-revive-controller.service -n 200 --no-pager
```

## 4. ログ確認

```bash
tail -n 200 /var/log/raspi-revive/observations.jsonl
tail -n 200 /var/log/raspi-revive/decisions.jsonl
tail -n 200 /var/log/raspi-revive/actions.jsonl
tail -n 200 /var/log/raspi-revive/events.jsonl
```

`events.jsonl` は lifecycle / transition の節目のみが出ることを確認します。

## 5. sentinel-only fault injection

gpio + host heartbeat + ping + ssh は健全に保ち、sentinel のみ stale 化させます。

期待結果:

- state: `SENTINEL_ONLY_FAILURE`
- action: `RESTART_SENTINEL`
- forbidden: `REMOTE_REBOOT`, `GPIO_REBOOT`, `POWER_BUTTON_PULSE`

## 6. verification 期待値

確認項目:

- `actions.jsonl` に restart command 実行結果が記録される
- `actions.jsonl` に sentinel freshness verification が記録される
- `events.jsonl` に `sentinel_restart_scheduled/completed/verified`（失敗時は `failed`）が記録される

## 7. ロールバック条件

次の場合は Phase A に戻します。

- sentinel 以外の incident で restart が発火する
- Phase B ログに remote/gpio/power action が出る
- sentinel restart verification が反復失敗する

## 8. ロールバック手順

```bash
sudo install -m 0644 \
  <deployment-root>/targets/raspi-zero-controller/config/phases/controller.phase-a.toml \
  /etc/raspi-revive/controller.toml
sudo systemctl restart raspi-revive-controller.service
```
