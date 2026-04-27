from __future__ import annotations

from dataclasses import dataclass
import time

from .config import ControllerConfig
from .gpio import FileHeartbeatInput
from .io import parse_iso8601
from .models import Observation
from .probes import file_age_seconds, ping_probe, read_host_heartbeat, ssh_probe


@dataclass(slots=True)
class ObservationCollector:
    config: ControllerConfig

    def collect(self, prev_host_seq: int | None) -> Observation:
        now_ts = time.time()

        gpio_age = FileHeartbeatInput(self.config.paths.gpio_heartbeat_path).edge_age_seconds(now_ts)
        gpio_fresh = gpio_age is not None and gpio_age <= self.config.threshold.gpio_heartbeat_stale_sec

        host_hb = read_host_heartbeat(self.config.paths.host_heartbeat_path)
        host_age = file_age_seconds(self.config.paths.host_heartbeat_path, now_ts)
        host_fresh = host_age is not None and host_age <= self.config.threshold.host_heartbeat_stale_sec

        host_boot_id = None
        host_seq = None
        host_monotonic = None
        host_wall = None
        if host_hb is not None:
            host_boot_id = host_hb.get("boot_id") if isinstance(host_hb.get("boot_id"), str) else None
            seq_raw = host_hb.get("seq")
            if isinstance(seq_raw, int):
                host_seq = seq_raw
            mono_raw = host_hb.get("monotonic_sec")
            if isinstance(mono_raw, (int, float)):
                host_monotonic = float(mono_raw)
            wall_raw = host_hb.get("wall_time")
            if isinstance(wall_raw, str) and parse_iso8601(wall_raw) is not None:
                host_wall = wall_raw

        progressing = False
        if host_seq is not None and prev_host_seq is not None:
            progressing = host_seq > prev_host_seq

        sentinel_stats_age = file_age_seconds(self.config.paths.sentinel_stats_path, now_ts)
        sentinel_stats_fresh = (
            sentinel_stats_age is not None
            and sentinel_stats_age <= self.config.threshold.sentinel_stats_stale_sec
        )
        sentinel_state_age = file_age_seconds(self.config.paths.sentinel_state_path, now_ts)
        sentinel_state_fresh = (
            sentinel_state_age is not None
            and sentinel_state_age <= self.config.threshold.sentinel_state_stale_sec
        )

        ping_ok = ping_probe(
            target=self.config.probe.ping_target,
            timeout_sec=self.config.probe.ping_timeout_sec,
            retries=self.config.probe.ping_retries,
        )
        ssh_ok = ssh_probe(
            target=self.config.probe.ssh_target,
            timeout_sec=self.config.probe.ssh_timeout_sec,
            retries=self.config.probe.ssh_retries,
            options=self.config.probe.ssh_options,
        )

        return Observation(
            ts=now_ts,
            host_boot_id=host_boot_id,
            host_seq=host_seq,
            host_monotonic_sec=host_monotonic,
            host_wall_time=host_wall,
            host_heartbeat_age_sec=host_age,
            host_heartbeat_fresh=host_fresh,
            host_heartbeat_progressing=progressing,
            gpio_heartbeat_age_sec=gpio_age,
            gpio_heartbeat_fresh=gpio_fresh,
            sentinel_stats_age_sec=sentinel_stats_age,
            sentinel_stats_fresh=sentinel_stats_fresh,
            sentinel_state_age_sec=sentinel_state_age,
            sentinel_state_fresh=sentinel_state_fresh,
            ping_ok=ping_ok,
            ssh_ok=ssh_ok,
        )
