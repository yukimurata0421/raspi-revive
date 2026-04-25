# Controller デプロイ手順（アトミック切替）

この文書は、controller 配備時の partial reflection を構造的に防ぐための運用契約です。

## 目的

- runtime Python source の部分反映を防ぐ
- 次リリースを再起動前に検証する
- rollback と配備後検証を決定論的にする

## リリース配置

- deployment root: `/opt/raspi-revive`
- 不変リリースディレクトリ: `/opt/raspi-revive/releases/<release-id>/`
- 稼働 symlink: `/opt/raspi-revive/current -> /opt/raspi-revive/releases/<release-id>`

controller service は `/opt/raspi-revive/current/...` を参照するため、release 有効化は symlink のアトミック切替だけで完了します。

## デプロイコマンド

controller host 上で、このリポジトリの checkout から実行します。

```bash
./scripts/deploy_controller_release.sh
```

## スクリプトが強制する内容

1. `src/` と `targets/` を新しい release directory へコピー（まだ非アクティブ）。
2. 新 release に対して staged preflight を実行。
   - import chain
   - config load
   - controller constructor
3. `mv -T` で `/opt/raspi-revive/current` をアトミック切替。
4. systemd reload + `raspi-revive-controller.service` restart。
5. 配備後 sanity check を実施。
   - service active
   - `controller_state_path` の鮮度閾値以内
   - 直近 `controller_state_write_failed` が無い
6. 古い release を世代管理で削除（最新 N 世代を保持）。

## 主なオプション

- `--release-id <id>`
- `--config <path>`
- `--service <name>`
- `--deploy-root <path>`
- `--keep-releases <n>`
- `--verify-wait-sec <sec>`
- `--state-max-age-sec <sec>`
- `--skip-install-unit`

## ロールバック

ロールバックは symlink 切替 + restart のみです。

```bash
sudo ln -sfn /opt/raspi-revive/releases/<previous-release-id> /opt/raspi-revive/current.new
sudo mv -Tf /opt/raspi-revive/current.new /opt/raspi-revive/current
sudo systemctl daemon-reload
sudo systemctl restart raspi-revive-controller.service
```

## 運用ルール

`/opt/raspi-revive/current/src/raspi_revive` または `/opt/raspi-revive/src/raspi_revive` へ直接上書き配備しないこと。
必ず release snapshot 全体を作成し、`current` をアトミックに切り替えること。
