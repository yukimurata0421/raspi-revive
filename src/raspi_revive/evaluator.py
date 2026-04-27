from __future__ import annotations

from dataclasses import dataclass

from .models import ControllerState, Evidence, Observation


@dataclass(slots=True)
class Classification:
    state: ControllerState
    evidence: Evidence
    reason: str
    failure_reason_code: str | None = None


TELEMETRY_SOURCE_FAILURE = "TELEMETRY_SOURCE_FAILURE"
TELEMETRY_EXPORT_FAILURE = "TELEMETRY_EXPORT_FAILURE"
TELEMETRY_PULL_FAILURE = "TELEMETRY_PULL_FAILURE"


def _telemetry_failure_classification(obs: Observation) -> tuple[str, str]:
    if not obs.export_meta_fresh:
        return (
            TELEMETRY_PULL_FAILURE,
            "telemetry stale and exporter meta is stale/missing on controller side",
        )

    source_host_stale = obs.export_source_host_heartbeat_fresh is False
    source_sentinel_stale = (
        (obs.export_source_sentinel_stats_fresh is False)
        or (obs.export_source_sentinel_state_fresh is False)
    )
    if source_host_stale or source_sentinel_stale:
        return (
            TELEMETRY_SOURCE_FAILURE,
            "telemetry stale and exporter reports source-side heartbeat/sentinel staleness",
        )

    if obs.export_last_error:
        return (
            TELEMETRY_EXPORT_FAILURE,
            f"telemetry stale and exporter reported copy errors: {obs.export_last_error}",
        )

    return (
        TELEMETRY_EXPORT_FAILURE,
        "telemetry stale despite fresh exporter meta and source mtimes",
    )


def build_evidence(obs: Observation) -> Evidence:
    return Evidence(
        out_of_band_gpio_fresh=obs.gpio_heartbeat_fresh,
        network_dependent_host_heartbeat_fresh=obs.host_heartbeat_fresh,
        network_dependent_host_heartbeat_progressing=obs.host_heartbeat_progressing,
        network_dependent_sentinel_stats_fresh=obs.sentinel_stats_fresh,
        network_dependent_sentinel_state_fresh=obs.sentinel_state_fresh,
        network_dependent_ping_ok=obs.ping_ok,
        network_dependent_ssh_ok=obs.ssh_ok,
    )


def classify(obs: Observation) -> Classification:
    ev = build_evidence(obs)

    if ev.gpio_fresh and ev.host_heartbeat_fresh and ev.ping_ok and (not ev.ssh_ok):
        return Classification(
            state=ControllerState.MANAGEMENT_PLANE_DEGRADED,
            evidence=ev,
            reason="host appears alive but ssh management path is degraded",
        )

    if ev.gpio_fresh and ((not ev.ping_ok) or (not ev.ssh_ok)):
        return Classification(
            state=ControllerState.NETWORK_ONLY_ISSUE,
            evidence=ev,
            reason="network-dependent probes failing while out-of-band gpio remains fresh",
        )

    sentinel_stale = not ev.sentinel_fresh
    if (
        ev.gpio_fresh
        and ev.host_heartbeat_fresh
        and (not ev.host_heartbeat_progressing)
        and ev.ssh_ok
        and sentinel_stale
    ):
        failure_code, reason = _telemetry_failure_classification(obs)
        return Classification(
            state=ControllerState.TELEMETRY_PIPELINE_FAILURE,
            evidence=ev,
            reason=reason,
            failure_reason_code=failure_code,
        )

    if ev.gpio_fresh and ev.host_heartbeat_fresh and ev.ssh_ok and sentinel_stale:
        return Classification(
            state=ControllerState.SENTINEL_ONLY_FAILURE,
            evidence=ev,
            reason="sentinel facts stale while host/gpio/ssh indicate OS alive",
        )

    telemetry_pipeline_failure = (not ev.host_heartbeat_fresh) and (not ev.sentinel_fresh)
    if telemetry_pipeline_failure and ev.gpio_fresh and ev.ssh_ok:
        failure_code, reason = _telemetry_failure_classification(obs)
        return Classification(
            state=ControllerState.TELEMETRY_PIPELINE_FAILURE,
            evidence=ev,
            reason=reason,
            failure_reason_code=failure_code,
        )

    host_degraded_rebootable = (not ev.gpio_fresh) and (not ev.host_heartbeat_fresh)
    if host_degraded_rebootable and ev.ssh_ok:
        return Classification(
            state=ControllerState.HOST_DEGRADED,
            evidence=ev,
            reason="out-of-band and host-heartbeat evidence indicate host degradation with ssh reachable",
        )

    if (not ev.gpio_fresh) and (not ev.ssh_ok) and (not ev.host_heartbeat_fresh):
        return Classification(
            state=ControllerState.FREEZE_SUSPECTED,
            evidence=ev,
            reason="out-of-band gpio stale and network-path probes indicate deep host failure",
        )

    return Classification(
        state=ControllerState.HEALTHY,
        evidence=ev,
        reason="no recovery gate matched",
    )
