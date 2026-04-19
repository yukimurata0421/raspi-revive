# Wiring

## 現在の観測配線（Phase A）

- Pi 5 physical pin 11（`BCM17`）-> Pi Zero 2 W physical pin 11（`BCM17`）
- GND -> GND
- ボード間で 5V 同士を接続しない
- ボード間で 3.3V 同士を接続しない
- この phase では外部介入線（GPIO reboot / power-button pulse）は未接続のままにする

## GPIO 抽象

controller は抽象インターフェースを使い、ボード依存を直接埋め込みません。

- `HeartbeatInput`: host 側 GPIO heartbeat edge の freshness を読む
- `ExternalResetOutput`: 外部 reset pulse を実行
- `PowerButtonPulseOutput`: power-button 相当の pulse を実行

## Safety Notes

- この phase は観測専用。controller の action gate はすべて無効のままにする
- Pi Zero 側 observer は pull-down 入力を前提とし、heartbeat が来ないときは Low 安定にする
- レベル変換、絶縁、pull-up/down の最終設計は配備依存でソフト対象外
