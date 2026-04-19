# Ops Notes（公開テンプレート）

この文書は、公開リポジトリに残す情報と、非公開 runbook に分離すべき情報の境界を定義します。

## 公開に残す

- トポロジーと役割境界
- state/action 方針と safety gate
- phased rollout 方針
- プレースホルダ化された設定例
- 個人識別情報を含まない運用チェックリスト

## 非公開に分離する

- 実ユーザー名、実アカウント名
- 実ホスト名、プライベート IP、トンネル終端
- 実 home path、実 SSH 鍵パス
- 実 known_hosts 配置
- 実 deployment path、実サービス配置の詳細
- 日付付きの個別運用ログ、インシデント痕跡

## プレースホルダ規約

公開ドキュメント/設定例では次の形式を使う。

- SSH target: `<agent-user>@<agent-host>`
- Ping target: `<agent-host-or-ip>`
- Controller SSH 鍵パス: `<controller-user-home>/.ssh/id_ed25519`
- Controller known_hosts パス: `<controller-user-home>/.ssh/known_hosts`
- Deployment root: `<deployment-root>`
- Local facts mirror root: `<local-facts-mirror-root>/remote/`
- Agent export root: `<agent-export-root>`

## 公開前チェック

1. docs/examples に実ユーザー名・実 IP・実ホスト名がないか確認する。
2. host 固有の home/deploy path をプレースホルダへ置換する。
3. 設計理由（why）と方針（what）は維持する。
4. 日付依存の運用履歴は private runbook へ移す。

## Private Runbook テンプレート

`docs/private-runbook.template.ja.md` を private runbook の雛形として使う。
実値を入れた runbook は公開されない場所で管理する。
