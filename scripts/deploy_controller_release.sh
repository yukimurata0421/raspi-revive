#!/usr/bin/env bash
set -euo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/raspi-revive}"
RELEASES_DIR="${RELEASES_DIR:-${DEPLOY_ROOT}/releases}"
CURRENT_LINK="${CURRENT_LINK:-${DEPLOY_ROOT}/current}"
CONFIG_PATH="${CONFIG_PATH:-/etc/raspi-revive/controller.toml}"
SERVICE_NAME="${SERVICE_NAME:-raspi-revive-controller.service}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"
VERIFY_WAIT_SEC="${VERIFY_WAIT_SEC:-30}"
STATE_MAX_AGE_SEC="${STATE_MAX_AGE_SEC:-60}"
INSTALL_UNIT_TEMPLATE="${INSTALL_UNIT_TEMPLATE:-1}"
UNIT_TEMPLATE="${UNIT_TEMPLATE:-targets/raspi-zero-controller/systemd/raspi-revive-controller.service}"
UNIT_DEST="${UNIT_DEST:-/etc/systemd/system/raspi-revive-controller.service}"
LEGACY_PREFLIGHT_DROPIN="${LEGACY_PREFLIGHT_DROPIN:-/etc/systemd/system/raspi-revive-controller.service.d/30-preflight.conf}"

usage() {
  cat <<'EOF'
Usage: scripts/deploy_controller_release.sh [options]

Options:
  --release-id <id>          Override release id (default: git short SHA or timestamp)
  --config <path>            Controller config path (default: /etc/raspi-revive/controller.toml)
  --service <name>           Systemd service name (default: raspi-revive-controller.service)
  --deploy-root <path>       Deployment root (default: /opt/raspi-revive)
  --keep-releases <n>        Keep newest N releases (default: 5)
  --verify-wait-sec <sec>    Wait before sanity check (default: 30)
  --state-max-age-sec <sec>  Max state file age after deploy (default: 60)
  --skip-install-unit        Do not install unit template
  --help                     Show this message
EOF
}

RELEASE_ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-id)
      RELEASE_ID="$2"
      shift 2
      ;;
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    --service)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --deploy-root)
      DEPLOY_ROOT="$2"
      RELEASES_DIR="${DEPLOY_ROOT}/releases"
      CURRENT_LINK="${DEPLOY_ROOT}/current"
      shift 2
      ;;
    --keep-releases)
      KEEP_RELEASES="$2"
      shift 2
      ;;
    --verify-wait-sec)
      VERIFY_WAIT_SEC="$2"
      shift 2
      ;;
    --state-max-age-sec)
      STATE_MAX_AGE_SEC="$2"
      shift 2
      ;;
    --skip-install-unit)
      INSTALL_UNIT_TEMPLATE="0"
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${RELEASE_ID}" ]]; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    RELEASE_ID="$(git rev-parse --short HEAD)"
  else
    RELEASE_ID="$(date +%Y%m%d%H%M%S)"
  fi
fi

RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
if sudo test -e "${RELEASE_DIR}"; then
  RELEASE_ID="${RELEASE_ID}-$(date +%Y%m%d%H%M%S)"
  RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
fi

echo "[deploy] release_id=${RELEASE_ID}"
echo "[deploy] release_dir=${RELEASE_DIR}"

sudo mkdir -p "${RELEASE_DIR}"
sudo rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  src/ "${RELEASE_DIR}/src/"
sudo rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  targets/ "${RELEASE_DIR}/targets/"

echo "[deploy] running staged preflight"
sudo /usr/bin/python3 \
  "${RELEASE_DIR}/targets/raspi-zero-controller/scripts/preflight_runtime_imports.py" \
  --src-dir "${RELEASE_DIR}/src" \
  --config "${CONFIG_PATH}" \
  --instantiate-controller

if [[ "${INSTALL_UNIT_TEMPLATE}" == "1" ]]; then
  echo "[deploy] installing unit template"
  sudo install -m 0644 "${UNIT_TEMPLATE}" "${UNIT_DEST}"
  if sudo test -f "${LEGACY_PREFLIGHT_DROPIN}"; then
    echo "[deploy] removing legacy preflight drop-in ${LEGACY_PREFLIGHT_DROPIN}"
    sudo rm -f "${LEGACY_PREFLIGHT_DROPIN}"
  fi
fi

echo "[deploy] switching current symlink atomically"
sudo ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}.new"
sudo mv -Tf "${CURRENT_LINK}.new" "${CURRENT_LINK}"

echo "[deploy] restarting ${SERVICE_NAME}"
sudo systemctl daemon-reload
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl is-active --quiet "${SERVICE_NAME}"

echo "[deploy] waiting ${VERIFY_WAIT_SEC}s before sanity checks"
sleep "${VERIFY_WAIT_SEC}"

readarray -t _RUNTIME_PATHS < <(
  sudo /usr/bin/python3 - <<PY
import tomllib
with open("${CONFIG_PATH}", "rb") as f:
    data = tomllib.load(f)
print(data["paths"]["controller_state_path"])
print(data["paths"]["events_log_path"])
PY
)
STATE_PATH="${_RUNTIME_PATHS[0]}"
EVENTS_PATH="${_RUNTIME_PATHS[1]}"

NOW_EPOCH="$(date +%s)"
STATE_MTIME="$(sudo stat -c %Y "${STATE_PATH}")"
STATE_AGE="$((NOW_EPOCH - STATE_MTIME))"
echo "[deploy] state_path=${STATE_PATH} age_sec=${STATE_AGE}"
if (( STATE_AGE > STATE_MAX_AGE_SEC )); then
  echo "[deploy] ERROR: state file age ${STATE_AGE}s exceeds ${STATE_MAX_AGE_SEC}s" >&2
  exit 1
fi

if sudo test -f "${EVENTS_PATH}"; then
  if sudo tail -n 200 "${EVENTS_PATH}" | grep -q 'controller_state_write_failed'; then
    echo "[deploy] ERROR: detected controller_state_write_failed in recent events" >&2
    exit 1
  fi
fi

echo "[deploy] pruning old releases (keep ${KEEP_RELEASES})"
mapfile -t _OLD_RELEASES < <(sudo find "${RELEASES_DIR}" -mindepth 1 -maxdepth 1 -type d | sudo sort -r)
if (( ${#_OLD_RELEASES[@]} > KEEP_RELEASES )); then
  for old_release in "${_OLD_RELEASES[@]:KEEP_RELEASES}"; do
    sudo rm -rf "${old_release}"
  done
fi

echo "[deploy] success release_id=${RELEASE_ID}"
