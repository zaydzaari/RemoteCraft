#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TEST_ROOT="$(mktemp -d)"
readonly HOST_UNAME="$(uname -s)"
trap 'rm -rf "$TEST_ROOT"' EXIT

mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/home/.ssh" "$TEST_ROOT/config" "$TEST_ROOT/install"
touch "$TEST_ROOT/home/.ssh/id_ed25519" "$TEST_ROOT/home/.ssh/known_hosts"

cat >"$TEST_ROOT/bin/uname" <<'EOF'
#!/usr/bin/env bash
printf 'Linux\n'
EOF

cat >"$TEST_ROOT/bin/python3" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${1:-}" == "-c" ]]; then
  exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" && "${3:-}" == "--help" ]]; then
  exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
  mkdir -p "$3/bin"
  cp "$MOCK_VENV_PYTHON" "$3/bin/python"
  chmod +x "$3/bin/python"
  exit 0
fi
exit 1
EOF

cat >"$TEST_ROOT/venv-python" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${1:-}" == "-m" && "${2:-}" == "pip" ]]; then
  exit 0
fi
if [[ "${1:-}" == "-c" ]]; then
  printf 'installer-smoke-token-that-is-longer-than-32-characters\n'
  exit 0
fi
exit 1
EOF

cat >"$TEST_ROOT/bin/ssh-keygen" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == "-F" ]]
EOF

for command_name in curl ssh ssh-keyscan; do
  cat >"$TEST_ROOT/bin/$command_name" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
done

cat >"$TEST_ROOT/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF

cat >"$TEST_ROOT/bin/install" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
while (($#)); do
  case "$1" in
    -d)
      shift
      ;;
    -m)
      shift 2
      ;;
    *)
      mkdir -p "$1"
      shift
      ;;
  esac
done
EOF

chmod +x "$TEST_ROOT/bin/"* "$TEST_ROOT/venv-python"

export HOME="$TEST_ROOT/home"
export XDG_CONFIG_HOME="$TEST_ROOT/config"
export PATH="$TEST_ROOT/bin:/usr/bin:/bin"
export MOCK_VENV_PYTHON="$TEST_ROOT/venv-python"
export REMOTECRAFT_INSTALL_ROOT="$TEST_ROOT/install"
export REMOTECRAFT_PACKAGE_SOURCE="$PROJECT_ROOT"
export REMOTECRAFT_SSH_HOST="minecraft.example.test"
export REMOTECRAFT_SSH_PORT="22"
export REMOTECRAFT_SSH_USER="minecraft"
export REMOTECRAFT_SSH_KEY_PATH="$TEST_ROOT/home/.ssh/id_ed25519"
export REMOTECRAFT_SERVERS_ROOT="/srv/minecraft"
export REMOTECRAFT_MAX_RAM_GB="8"

output="$(bash "$PROJECT_ROOT/scripts/install.sh")"
env_file="$TEST_ROOT/config/remotecraft/.env"

[[ -f "$env_file" ]]
if [[ "$HOST_UNAME" == "Linux" ]]; then
  [[ "$(stat -c '%a' "$env_file")" == "600" ]]
fi
grep -q '^REMOTECRAFT_API_TOKEN="installer-smoke-token' "$env_file"
grep -q '^REMOTECRAFT_SSH_HOST="minecraft.example.test"$' "$env_file"
grep -q '^REMOTECRAFT_MAX_RAM_GB="8"$' "$env_file"
grep -q 'Installation complete.' <<<"$output"
grep -q 'Manual start:' <<<"$output"

printf 'installer smoke test: ok\n'
