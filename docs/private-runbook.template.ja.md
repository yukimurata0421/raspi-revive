# Private Runbook テンプレート（非公開）

このファイルは private 運用 runbook の雛形です。
実値を入れた版は公開リポジトリにコミットしないこと。

## 1. 環境ベースライン

- 日付:
- 作業者:
- Controller host:
- Agent host:
- Deployment root:
- 実行ユーザー:

## 2. ネットワークと認証（実値）

- `ping_target =`
- `ssh_target =`
- Controller SSH 鍵パス:
- Controller known_hosts パス:

## 3. Runtime パス（実値）

- Agent export root:
- Controller local facts mirror root:
- Controller config path:
- Controller logs:
- Controller state file:

## 4. サービス構成と責任境界

- Agent host 側サービス:
- Controller host 側サービス:
- systemd unit override メモ:

## 5. Phase 投入記録

- 現在 phase:
- `dry_run`:
- 有効 action:
- 昇格条件チェック結果:
- ロールバック条件チェック結果:

## 6. Safety Gate（適用値）

- `cooldown_seconds =`
- `lockout_window_seconds =`
- `max_actions_per_window =`
- `post_action_verification_wait_seconds =`

## 7. 障害・復旧メモ

- 障害 ID:
- 発火条件:
- 証拠サマリ:
- 実行 action:
- post-action verification 結果:
- フォローアップ:

## 8. 変更履歴

| 日付 | 変更内容 | 理由 | 証拠 |
| --- | --- | --- | --- |
| YYYY-MM-DD |  |  |  |

## 9. 運用コマンド（非公開）

実パス・実サービス名を使うホスト固有コマンドを記録する。

```bash
# 例
systemctl status <controller-service> --no-pager
journalctl -u <controller-service> -n 200 --no-pager
```
