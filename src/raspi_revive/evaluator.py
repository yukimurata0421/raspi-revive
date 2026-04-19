from __future__ import annotations

from dataclasses import dataclass

from .models import ControllerState, Evidence, Observation


@dataclass(slots=True)
class Classification:
    state: ControllerState
    evidence: Evidence
    reason: str


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
    # NOTE: host_heartbeat_progressing is captured in Evidence but not yet used in
    # classification gates. For future hardening, consider treating sustained
    # "fresh-but-not-progressing" heartbeat as degradation signal.

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
    if ev.gpio_fresh and ev.host_heartbeat_fresh and ev.ssh_ok and sentinel_stale:
        return Classification(
            state=ControllerState.SENTINEL_ONLY_FAILURE,
            evidence=ev,
            reason="sentinel facts stale while host/gpio/ssh indicate OS alive",
        )

    host_degraded_rebootable = (
        ((not ev.gpio_fresh) and (not ev.host_heartbeat_fresh))
        or ((not ev.host_heartbeat_fresh) and (not ev.sentinel_fresh))
    )
    if host_degraded_rebootable and ev.ssh_ok:
        return Classification(
            state=ControllerState.HOST_DEGRADED,
            evidence=ev,
            reason="multi-evidence degradation with ssh reachable",
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
