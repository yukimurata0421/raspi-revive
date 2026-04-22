from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import ssl
import subprocess
from typing import Callable
import urllib.error
import urllib.request

from .config import ControllerConfig
from .io import append_jsonl_with_rotation, read_json, write_json_atomic
from .models import Decision, Observation


def _iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def compute_retry_delay_seconds(
    *,
    first_failure_ts: float,
    now_ts: float,
    retry_interval_seconds: float,
    backoff_after_seconds: float,
    backoff_multiplier: float,
    backoff_max_seconds: float,
) -> float:
    elapsed = max(0.0, now_ts - first_failure_ts)
    if elapsed < backoff_after_seconds:
        return max(1.0, retry_interval_seconds)

    exponent = int((elapsed - backoff_after_seconds) // max(1.0, retry_interval_seconds)) + 1
    delay = retry_interval_seconds * (backoff_multiplier ** exponent)
    return max(1.0, min(backoff_max_seconds, delay))


@dataclass(slots=True)
class NotifyState:
    candidate_incident_key: str | None = None
    candidate_state: str | None = None
    candidate_since_ts: float | None = None
    last_notified_incident_key: str | None = None
    last_notified_ts: float | None = None
    last_delivery_ts: float | None = None
    last_failure_ts: float | None = None

    @classmethod
    def from_json(cls, payload: dict | None) -> "NotifyState":
        if not isinstance(payload, dict):
            return cls()
        return cls(
            candidate_incident_key=payload.get("candidate_incident_key"),
            candidate_state=payload.get("candidate_state"),
            candidate_since_ts=payload.get("candidate_since_ts"),
            last_notified_incident_key=payload.get("last_notified_incident_key"),
            last_notified_ts=payload.get("last_notified_ts"),
            last_delivery_ts=payload.get("last_delivery_ts"),
            last_failure_ts=payload.get("last_failure_ts"),
        )

    def to_json(self) -> dict:
        return {
            "candidate_incident_key": self.candidate_incident_key,
            "candidate_state": self.candidate_state,
            "candidate_since_ts": self.candidate_since_ts,
            "last_notified_incident_key": self.last_notified_incident_key,
            "last_notified_ts": self.last_notified_ts,
            "last_delivery_ts": self.last_delivery_ts,
            "last_failure_ts": self.last_failure_ts,
        }


@dataclass(slots=True)
class _NotifyProvider:
    name: str
    kind: str
    deliver: Callable[[dict], tuple[bool, str | None]]


@dataclass(slots=True)
class NotifyDispatcher:
    config: ControllerConfig
    _state: NotifyState = field(init=False)
    _queue: list[dict] = field(init=False, default_factory=list)
    _providers: list[_NotifyProvider] = field(init=False, default_factory=list)
    _queue_dirty: bool = field(init=False, default=False)
    _stats_dirty: bool = field(init=False, default=False)
    _last_stats_flush_ts: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self._state = NotifyState.from_json(read_json(self.config.notify.stats_path))
        payload = read_json(self.config.notify.queue_path)
        self._queue = (
            payload["items"]
            if isinstance(payload, dict) and isinstance(payload.get("items"), list)
            else []
        )
        self._providers = self._build_providers()
        self._last_stats_flush_ts = None
        if self.config.notify.enabled:
            if not self.config.notify.queue_path.exists():
                self._queue_dirty = True
            if not self.config.notify.stats_path.exists():
                self._stats_dirty = True

    def handle_cycle(self, decision: Decision, obs: Observation) -> None:
        now_ts = obs.ts
        if not self.config.notify.enabled:
            return

        self._track_candidate(decision, now_ts)
        self._drain_queue(now_ts)
        self._flush_persistence(now_ts)

    def _track_candidate(self, decision: Decision, now_ts: float) -> None:
        state = decision.classified_state.value
        is_candidate = state in self.config.notify.candidate_states
        incident_changed = self._state.candidate_incident_key != decision.incident_key

        if not is_candidate:
            if self._state.candidate_since_ts is not None:
                self._append_event(
                    "candidate_reset",
                    now_ts,
                    {"reason": "state_not_candidate", "state": state, "incident_key": decision.incident_key},
                )
            self._state.candidate_incident_key = None
            self._state.candidate_state = None
            self._state.candidate_since_ts = None
            self._stats_dirty = True
            return

        if self._state.candidate_since_ts is None or incident_changed:
            self._state.candidate_incident_key = decision.incident_key
            self._state.candidate_state = state
            self._state.candidate_since_ts = now_ts
            self._stats_dirty = True
            self._append_event(
                "candidate_started",
                now_ts,
                {"state": state, "incident_key": decision.incident_key},
            )
            return

        duration = now_ts - self._state.candidate_since_ts
        if (
            duration >= self.config.notify.candidate_hold_seconds
            and self._state.last_notified_incident_key != decision.incident_key
        ):
            item = self._build_queue_item(decision, now_ts, duration)
            self._trim_queue_for_new_item(now_ts)
            self._queue.append(item)
            self._queue_dirty = True
            self._state.last_notified_incident_key = decision.incident_key
            self._state.last_notified_ts = now_ts
            self._stats_dirty = True
            self._append_event("enqueued", now_ts, {"event_id": item["event_id"], "incident_key": decision.incident_key})

    def _build_queue_item(self, decision: Decision, now_ts: float, duration: float) -> dict:
        payload = {
            "event_id": decision.correlation_id,
            "ts": now_ts,
            "ts_iso": _iso_utc(now_ts),
            "incident_key": decision.incident_key,
            "classified_state": decision.classified_state.value,
            "reason": decision.reason,
            "candidate_duration_sec": round(duration, 1),
            "evidence": {
                "gpio_fresh": decision.evidence.gpio_fresh,
                "host_heartbeat_fresh": decision.evidence.host_heartbeat_fresh,
                "sentinel_stats_fresh": decision.evidence.sentinel_stats_fresh,
                "sentinel_state_fresh": decision.evidence.sentinel_state_fresh,
                "ping_ok": decision.evidence.ping_ok,
                "ssh_ok": decision.evidence.ssh_ok,
            },
        }
        return {
            "event_id": decision.correlation_id,
            "payload": payload,
            "created_ts": now_ts,
            "next_retry_ts": now_ts,
            "first_failure_ts": None,
            "attempt_count": 0,
            "provider_status": {provider.name: False for provider in self._providers},
            "last_error": None,
        }

    def _drain_queue(self, now_ts: float) -> None:
        self._drop_expired_items(now_ts)
        remaining: list[dict] = []
        for item in self._queue:
            if now_ts < float(item.get("next_retry_ts", 0.0)):
                remaining.append(item)
                continue

            status = self._provider_status_from_item(item)
            last_error = None

            for provider in self._providers:
                if status.get(provider.name, False):
                    continue
                ok, provider_error = provider.deliver(item["payload"])
                if ok:
                    status[provider.name] = True
                    self._append_event(
                        "provider_ok",
                        now_ts,
                        {"event_id": item["event_id"], "provider": provider.name, "kind": provider.kind},
                    )
                elif last_error is None:
                    last_error = provider_error

            item["provider_status"] = status
            self._write_legacy_provider_flags(item, status)

            if (not status) or all(status.values()):
                self._state.last_delivery_ts = now_ts
                self._stats_dirty = True
                self._queue_dirty = True
                self._append_event("delivery_complete", now_ts, {"event_id": item["event_id"]})
                continue

            item["attempt_count"] = int(item.get("attempt_count", 0)) + 1
            if item.get("first_failure_ts") is None:
                item["first_failure_ts"] = now_ts
            item["last_error"] = last_error or "delivery_failed"
            delay = compute_retry_delay_seconds(
                first_failure_ts=float(item["first_failure_ts"]),
                now_ts=now_ts,
                retry_interval_seconds=self.config.notify.queue_retry_interval_seconds,
                backoff_after_seconds=self.config.notify.backoff_after_seconds,
                backoff_multiplier=self.config.notify.backoff_multiplier,
                backoff_max_seconds=self.config.notify.backoff_max_seconds,
            )
            item["next_retry_ts"] = now_ts + delay
            self._state.last_failure_ts = now_ts
            self._stats_dirty = True
            self._queue_dirty = True
            self._append_event(
                "delivery_failed",
                now_ts,
                {
                    "event_id": item["event_id"],
                    "attempt_count": item["attempt_count"],
                    "retry_in_seconds": round(delay, 1),
                    "error": item["last_error"],
                },
            )
            remaining.append(item)

        self._queue = remaining

    def _drop_expired_items(self, now_ts: float) -> None:
        kept: list[dict] = []
        for item in self._queue:
            created_ts = float(item.get("created_ts", now_ts))
            if (now_ts - created_ts) > self.config.notify.max_event_age_seconds:
                self._append_event(
                    "dropped_expired",
                    now_ts,
                    {"event_id": item.get("event_id"), "age_seconds": round(now_ts - created_ts, 1)},
                )
                self._queue_dirty = True
                continue
            kept.append(item)
        self._queue = kept

    def _trim_queue_for_new_item(self, now_ts: float) -> None:
        while len(self._queue) >= self.config.notify.max_queue_size:
            dropped = self._queue.pop(0)
            self._queue_dirty = True
            self._append_event(
                "dropped_overflow",
                now_ts,
                {"event_id": dropped.get("event_id"), "max_queue_size": self.config.notify.max_queue_size},
            )

    def _build_providers(self) -> list[_NotifyProvider]:
        providers: list[_NotifyProvider] = []
        provider_configs = list(self.config.notify_providers)
        if not provider_configs:
            if self.config.notify.remote_append_enabled:
                provider_configs.append(
                    type(
                        "_LegacyProviderCfg",
                        (),
                        {
                            "name": "ssh_append_default",
                            "kind": "ssh_append",
                            "enabled": True,
                            "remote_jsonl_path": self.config.notify.remote_jsonl_path,
                            "webhook_url": "",
                        },
                    )()
                )
            if self.config.notify.discord_webhook_url:
                provider_configs.append(
                    type(
                        "_LegacyProviderCfg",
                        (),
                        {
                            "name": "discord_webhook_default",
                            "kind": "discord_webhook",
                            "enabled": True,
                            "remote_jsonl_path": "",
                            "webhook_url": self.config.notify.discord_webhook_url,
                        },
                    )()
                )

        for provider_cfg in provider_configs:
            if not provider_cfg.enabled:
                continue
            if provider_cfg.kind == "ssh_append":
                providers.append(
                    _NotifyProvider(
                        name=provider_cfg.name,
                        kind=provider_cfg.kind,
                        deliver=lambda payload, remote_path=provider_cfg.remote_jsonl_path: self._append_remote_jsonl_to_path(payload, remote_path),
                    )
                )
            elif provider_cfg.kind == "discord_webhook":
                if provider_cfg.webhook_url == self.config.notify.discord_webhook_url:
                    def deliver_fn(payload: dict) -> tuple[bool, str | None]:
                        return self._send_discord(payload)
                else:
                    webhook_url = provider_cfg.webhook_url

                    def deliver_fn(payload: dict) -> tuple[bool, str | None]:
                        return self._send_discord_to_url(payload, webhook_url)
                providers.append(
                    _NotifyProvider(
                        name=provider_cfg.name,
                        kind=provider_cfg.kind,
                        deliver=deliver_fn,
                    )
                )
        return providers

    def _provider_status_from_item(self, item: dict) -> dict[str, bool]:
        status = {provider.name: False for provider in self._providers}
        existing = item.get("provider_status")
        if isinstance(existing, dict):
            for name, value in existing.items():
                if name in status:
                    status[name] = bool(value)

        # Backward compatibility for queue items persisted by old schema.
        if bool(item.get("remote_delivered", False)):
            for provider in self._providers:
                if provider.kind == "ssh_append":
                    status[provider.name] = True
                    break
        if bool(item.get("discord_delivered", False)):
            for provider in self._providers:
                if provider.kind == "discord_webhook":
                    status[provider.name] = True
                    break
        return status

    def _write_legacy_provider_flags(self, item: dict, status: dict[str, bool]) -> None:
        item["remote_delivered"] = any(
            status.get(provider.name, False)
            for provider in self._providers
            if provider.kind == "ssh_append"
        )
        item["discord_delivered"] = any(
            status.get(provider.name, False)
            for provider in self._providers
            if provider.kind == "discord_webhook"
        )

    def _append_remote_jsonl_to_path(self, payload: dict, remote_path: str) -> tuple[bool, str | None]:
        json_line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        remote_dir = str(Path(remote_path).parent)
        cmd = [
            "ssh",
            *self.config.probe.ssh_options,
            self.config.probe.ssh_target,
            (
                f"mkdir -p {shlex.quote(remote_dir)} && "
                f"printf '%s\\n' {shlex.quote(json_line)} >> {shlex.quote(remote_path)}"
            ),
        ]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        except OSError as exc:
            return False, f"remote_append_exec_error: {exc}"
        if proc.returncode != 0:
            return False, (proc.stderr.strip() or proc.stdout.strip() or f"ssh_exit={proc.returncode}")
        return True, None

    def _append_remote_jsonl(self, payload: dict) -> tuple[bool, str | None]:
        return self._append_remote_jsonl_to_path(payload, self.config.notify.remote_jsonl_path)

    def _send_discord_to_url(self, payload: dict, webhook_url: str) -> tuple[bool, str | None]:
        if not webhook_url:
            return False, "discord_url_not_configured"
        body = {
            "content": (
                "[raspi-revive] reboot candidate sustained for 5+ minutes\\n"
                f"state={payload['classified_state']} incident={payload['incident_key']} "
                f"duration={payload['candidate_duration_sec']}s"
            )
        }
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=10):
                return True, None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                return False, f"discord_tls_error(clock_skew_or_cert): {exc.reason}"
            return False, f"discord_url_error: {exc}"
        except TimeoutError as exc:
            return False, f"discord_timeout: {exc}"

    def _send_discord(self, payload: dict) -> tuple[bool, str | None]:
        return self._send_discord_to_url(payload, self.config.notify.discord_webhook_url)

    def _append_event(self, event: str, ts: float, detail: dict) -> None:
        append_jsonl_with_rotation(
            self.config.notify.events_path,
            {
                "ts": ts,
                "ts_iso": _iso_utc(ts),
                "event": event,
                "detail": detail,
            },
            max_bytes=self.config.logs.max_log_size_bytes,
            rotation_count=self.config.logs.rotation_count,
        )

    def _flush_persistence(self, now_ts: float) -> None:
        if self._queue_dirty:
            write_json_atomic(self.config.notify.queue_path, {"items": self._queue})
            self._queue_dirty = False

        flush_interval = max(0.0, self.config.notify.stats_flush_interval_seconds)
        should_flush_stats = False
        if self._stats_dirty:
            if flush_interval == 0.0:
                should_flush_stats = True
            elif self._last_stats_flush_ts is None:
                should_flush_stats = True
            elif (now_ts - self._last_stats_flush_ts) >= flush_interval:
                should_flush_stats = True

        if should_flush_stats:
            write_json_atomic(self.config.notify.stats_path, self._state.to_json())
            self._last_stats_flush_ts = now_ts
            self._stats_dirty = False
