# Wiring

## Current Observation Wiring (Phase A)

- Pi 5 physical pin 11 (`BCM17`) -> Pi Zero 2 W physical pin 11 (`BCM17`)
- GND -> GND
- Do not connect 5V rails between boards.
- Do not connect 3.3V rails between boards.
- External intervention lines (GPIO reboot / power-button pulse) stay disconnected in this phase.

## GPIO Abstractions

Controller code uses abstractions and does not hard-code board details.

- `HeartbeatInput`: reads freshness of host GPIO heartbeat edges.
- `ExternalResetOutput`: executes external reset pulse.
- `PowerButtonPulseOutput`: executes power-button equivalent pulse.

## Safety Notes

- This phase is observation-only. Keep action gates disabled in controller config.
- Pi Zero observer uses input pull-down so an idle/disconnected heartbeat remains stable at Low.
- Electrical design (level shift, isolation, pull-up/down) is deployment-specific and out of software scope.
