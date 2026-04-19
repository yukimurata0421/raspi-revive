# Notify Queue 設計

この文書は、`raspi-revive` に追加した「復旧アクションを有効化しない通知専用拡張」をまとめたものです。

## 目的

- restart/reboot アクションを無効のまま維持する。
- reboot 候補状態の継続を検知する。
- キュー方式で耐障害性のある通知配信を行う。

## 発火条件

次の両方を満たしたときに通知イベントを enqueue します。

1. `classified_state` が以下のいずれか:
   - `HOST_DEGRADED`
   - `FREEZE_SUSPECTED`
2. 同一 incident が `candidate_hold_seconds`（既定300秒）以上継続

## 配信先

キューイベントは以下の両方を試行します。

1. SSH 経由で Pi 5 側 JSONL へ append（`notify.remote_jsonl_path`）
2. Discord webhook POST

有効な配信先がすべて成功したときのみ、イベントをキューから削除します。

## リトライ方針

- 基本リトライ間隔: `queue_retry_interval_seconds`（既定60秒）
- 連続失敗時間が `backoff_after_seconds`（既定300秒）に達したら指数バックオフへ遷移:
  - `delay = base * backoff_multiplier^n`
  - `backoff_max_seconds` で上限

## Runtime ファイル

- Queue: `notify-queue.json`
- Stats: `notify-stats.json`
- Events: `notify-events.jsonl`

これらは controller 側 runtime artifact であり、リポジトリへコミットしません。

## セキュリティと秘密情報

- Webhook URL は環境変数（`notify.discord_webhook_url_env`）から読み込む。
- webhook をリポジトリ内へ直書きしない。
- 公開レイヤーではプレースホルダ/サニタイズ済みパスのみ扱う。

## 実装対応箇所

- Dispatcher: `src/raspi_revive/notifier.py`
- 設定モデル/ローダ: `src/raspi_revive/config.py`
- controller 連携: `src/raspi_revive/controller.py`
- 単体テスト: `tests/test_notifier.py`

## 検証

実装は次で検証済みです。

- `ruff check .`
- `pytest -q`
- `python3 -m py_compile ...`
- scenario replay CLI の回帰実行
