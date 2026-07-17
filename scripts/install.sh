#!/usr/bin/env bash
set -Eeuo pipefail

readonly RELEASE_VERSION="${REMOTECRAFT_VERSION:-0.2.1}"
readonly PACKAGE_SOURCE="${REMOTECRAFT_PACKAGE_SOURCE:-https://github.com/zaydzaari/RemoteCraft/archive/refs/tags/v${RELEASE_VERSION}.tar.gz}"
readonly INSTALL_ROOT="${REMOTECRAFT_INSTALL_ROOT:-${HOME}/.local/share/remotecraft}"
readonly CONFIG_ROOT="${XDG_CONFIG_HOME:-${HOME}/.config}/remotecraft"
readonly VENV_DIR="${INSTALL_ROOT}/venv"
readonly DATA_DIR="${INSTALL_ROOT}/data"
readonly ENV_FILE="${CONFIG_ROOT}/.env"
readonly SERVICE_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
readonly SERVICE_FILE="${SERVICE_DIR}/remotecraft.service"

info() {
  printf '\033[1;32mRemoteCraft\033[0m %s\n' "$*"
}

warn() {
  printf '\033[1;33mWarning:\033[0m %s\n' "$*" >&2
}

die() {
  printf '\033[1;31mError:\033[0m %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

write_env_var() {
  local name="$1"
  local value="$2"

  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] \
    || die "Configuration values cannot contain newlines"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s="%s"\n' "$name" "$value"
}

prompt() {
  local variable_name="$1"
  local label="$2"
  local default_value="${3:-}"
  local current_value="${!variable_name:-}"
  local response

  if [[ -n "$current_value" ]]; then
    return
  fi
  [[ -r /dev/tty ]] || die "Set ${variable_name} when running without a terminal"
  if [[ -n "$default_value" ]]; then
    read -r -p "${label} [${default_value}]: " response </dev/tty
    printf -v "$variable_name" '%s' "${response:-$default_value}"
  else
    read -r -p "${label}: " response </dev/tty
    printf -v "$variable_name" '%s' "$response"
  fi
}

confirm_fingerprint() {
  local response
  [[ -r /dev/tty ]] || die "Host-key confirmation requires an interactive terminal"
  printf '\nVerify this fingerprint in your VPS provider console.\n'
  ssh-keygen -lf "$1"
  read -r -p "Type YES only when the fingerprint matches: " response </dev/tty
  [[ "$response" == "YES" ]] || die "SSH host key was not trusted"
}

[[ "$(uname -s)" == "Linux" ]] || die "The guided installer currently supports Linux"
for command_name in python3 curl ssh ssh-keyscan ssh-keygen; do
  require_command "$command_name"
done

python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' \
  || die "Python 3.11 or newer is required"
python3 -m venv --help >/dev/null 2>&1 \
  || die "The Python venv module is required (Ubuntu: sudo apt install python3-venv)"

printf '\nRemoteCraft guided installer %s\n\n' "$RELEASE_VERSION"

prompt REMOTECRAFT_SSH_HOST "Minecraft host or IP"
prompt REMOTECRAFT_SSH_PORT "SSH port" "22"
prompt REMOTECRAFT_SSH_USER "SSH user" "minecraft"
prompt REMOTECRAFT_SSH_KEY_PATH "Private key path (SSH agent fallback)" "${HOME}/.ssh/id_ed25519"
prompt REMOTECRAFT_SERVERS_ROOT "Remote server root" "/srv/minecraft"
prompt REMOTECRAFT_MAX_RAM_GB "Maximum RAM per server in GB" "16"

[[ "$REMOTECRAFT_SSH_HOST" =~ ^[A-Za-z0-9._:-]+$ ]] \
  || die "The SSH host contains unsupported characters"
[[ "$REMOTECRAFT_SSH_PORT" =~ ^[0-9]+$ ]] \
  && ((REMOTECRAFT_SSH_PORT >= 1 && REMOTECRAFT_SSH_PORT <= 65535)) \
  || die "The SSH port must be between 1 and 65535"
[[ "$REMOTECRAFT_SSH_USER" =~ ^[A-Za-z_][A-Za-z0-9_-]{0,31}$ ]] \
  || die "The SSH user contains unsupported characters"
[[ "$REMOTECRAFT_SERVERS_ROOT" =~ ^/[A-Za-z0-9._/-]+$ ]] \
  && [[ "$REMOTECRAFT_SERVERS_ROOT" != *".."* ]] \
  || die "The server root must be a safe absolute Linux path"
[[ "$REMOTECRAFT_MAX_RAM_GB" =~ ^[0-9]+$ ]] \
  && ((REMOTECRAFT_MAX_RAM_GB >= 1 && REMOTECRAFT_MAX_RAM_GB <= 64)) \
  || die "Maximum RAM must be between 1 and 64 GB"

if [[ "$REMOTECRAFT_SSH_KEY_PATH" == "~"* ]]; then
  REMOTECRAFT_SSH_KEY_PATH="${HOME}${REMOTECRAFT_SSH_KEY_PATH:1}"
fi
if [[ -n "$REMOTECRAFT_SSH_KEY_PATH" && ! -f "$REMOTECRAFT_SSH_KEY_PATH" ]]; then
  warn "Key not found at ${REMOTECRAFT_SSH_KEY_PATH}; the SSH agent will be used instead."
  REMOTECRAFT_SSH_KEY_PATH=""
fi

readonly KNOWN_HOSTS_PATH="${HOME}/.ssh/known_hosts"
install -d -m 0700 "$(dirname "$KNOWN_HOSTS_PATH")"
touch "$KNOWN_HOSTS_PATH"
chmod 0600 "$KNOWN_HOSTS_PATH"

host_lookup="$REMOTECRAFT_SSH_HOST"
if [[ "$REMOTECRAFT_SSH_PORT" != "22" ]]; then
  host_lookup="[${REMOTECRAFT_SSH_HOST}]:${REMOTECRAFT_SSH_PORT}"
fi

if ! ssh-keygen -F "$host_lookup" -f "$KNOWN_HOSTS_PATH" >/dev/null; then
  scan_file="$(mktemp)"
  trap 'rm -f "${scan_file:-}"' EXIT
  info "Fetching the SSH host key for fingerprint verification..."
  ssh-keyscan -T 10 -p "$REMOTECRAFT_SSH_PORT" "$REMOTECRAFT_SSH_HOST" \
    >"$scan_file" 2>/dev/null || die "Could not fetch the SSH host key"
  [[ -s "$scan_file" ]] || die "The SSH host did not return a host key"
  confirm_fingerprint "$scan_file"
  cat "$scan_file" >>"$KNOWN_HOSTS_PATH"
  rm -f "$scan_file"
  trap - EXIT
fi

ssh_args=(
  -p "$REMOTECRAFT_SSH_PORT"
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=${KNOWN_HOSTS_PATH}"
)
if [[ -n "$REMOTECRAFT_SSH_KEY_PATH" ]]; then
  ssh_args+=(-i "$REMOTECRAFT_SSH_KEY_PATH")
fi

quoted_root="$(printf '%q' "$REMOTECRAFT_SERVERS_ROOT")"
info "Checking SSH access and remote requirements..."
ssh "${ssh_args[@]}" "${REMOTECRAFT_SSH_USER}@${REMOTECRAFT_SSH_HOST}" \
  "for tool in java screen curl sha1sum; do command -v \"\$tool\" >/dev/null || { echo \"Missing: \$tool\" >&2; exit 1; }; done; test -d ${quoted_root} && test -w ${quoted_root}" \
  || die "SSH failed, a required remote tool is missing, or ${REMOTECRAFT_SERVERS_ROOT} is not writable"

info "Installing RemoteCraft into ${INSTALL_ROOT}..."
install -d -m 0700 "$INSTALL_ROOT" "$DATA_DIR" "$CONFIG_ROOT"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install --upgrade "$PACKAGE_SOURCE"

api_token="$($VENV_DIR/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
umask 077
{
  write_env_var REMOTECRAFT_API_TOKEN "$api_token"
  write_env_var REMOTECRAFT_SSH_HOST "$REMOTECRAFT_SSH_HOST"
  write_env_var REMOTECRAFT_SSH_PORT "$REMOTECRAFT_SSH_PORT"
  write_env_var REMOTECRAFT_SSH_USER "$REMOTECRAFT_SSH_USER"
  write_env_var REMOTECRAFT_SSH_KEY_PATH "$REMOTECRAFT_SSH_KEY_PATH"
  write_env_var REMOTECRAFT_SSH_USE_AGENT true
  write_env_var REMOTECRAFT_KNOWN_HOSTS_PATH "$KNOWN_HOSTS_PATH"
  write_env_var REMOTECRAFT_SERVERS_ROOT "$REMOTECRAFT_SERVERS_ROOT"
  write_env_var REMOTECRAFT_DATA_DIR "$DATA_DIR"
  write_env_var REMOTECRAFT_MAX_RAM_GB "$REMOTECRAFT_MAX_RAM_GB"
  write_env_var REMOTECRAFT_BIND_HOST 127.0.0.1
  write_env_var REMOTECRAFT_PORT 8000
} >"$ENV_FILE"
chmod 0600 "$ENV_FILE"

service_started=false
if [[ -z "$REMOTECRAFT_SSH_KEY_PATH" ]]; then
  warn "Skipping the user service because an interactive SSH agent may not survive logout."
  warn "Set a private key path in ${ENV_FILE}, then install the service manually."
elif command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  install -d -m 0700 "$SERVICE_DIR"
  cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=RemoteCraft Minecraft control plane
After=network-online.target

[Service]
Type=simple
WorkingDirectory="${CONFIG_ROOT}"
EnvironmentFile="${ENV_FILE}"
ExecStart="${VENV_DIR}/bin/remotecraft"
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths="${DATA_DIR}"

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  if systemctl --user enable --now remotecraft.service; then
    service_started=true
    if command -v loginctl >/dev/null 2>&1 \
      && [[ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || true)" != "yes" ]]; then
      warn "User lingering is disabled; the service may stop after logout or not start at boot."
      warn "Enable it with: sudo loginctl enable-linger $(id -un)"
    fi
  else
    warn "The user service could not start; use the manual command printed below."
  fi
else
  warn "A user-level systemd session is unavailable; use the manual command below."
fi

if [[ "$service_started" == true ]]; then
  healthy=false
  for _attempt in {1..20}; do
    if curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null; then
      healthy=true
      break
    fi
    sleep 1
  done
  [[ "$healthy" == true ]] || warn "Service started but did not become healthy; run: journalctl --user -u remotecraft"
fi

printf '\nInstallation complete.\n'
printf 'Dashboard: http://127.0.0.1:8000\n'
printf 'API token: %s\n' "$api_token"
printf 'Config: %s\n' "$ENV_FILE"
if [[ "$service_started" == true ]]; then
  printf 'Service: systemctl --user status remotecraft\n'
else
  printf 'Manual start: cd %q && %q\n' "$CONFIG_ROOT" "$VENV_DIR/bin/remotecraft"
fi
printf '\nKeep the token private. For remote access, use an SSH tunnel:\n'
printf 'ssh -L 8000:127.0.0.1:8000 user@control-plane.example.com\n'
