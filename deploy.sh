#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

case "${1:-}" in
    '') verify=false ;;
    --verify) verify=true ;;
    -h|--help)
        printf 'Usage: bash deploy.sh [--verify]\n'
        printf '  --verify  run a smoke test in a temporary Compose project\n'
        exit 0
        ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac
if (( $# > 1 )); then
    echo "Usage: bash deploy.sh [--verify]" >&2
    exit 2
fi

admin=()
if (( EUID != 0 )); then
    admin=(sudo)
fi

if ! docker compose version >/dev/null 2>&1; then
    . /etc/os-release
    if [[ "${ID:-}" != ubuntu ]]; then
        echo "Automatic Docker setup requires Ubuntu." >&2
        exit 1
    fi
    "${admin[@]}" apt-get update
    "${admin[@]}" apt-get install -y ca-certificates curl
    "${admin[@]}" install -m 0755 -d /etc/apt/keyrings
    "${admin[@]}" curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    "${admin[@]}" chmod a+r /etc/apt/keyrings/docker.asc
    "${admin[@]}" tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    "${admin[@]}" apt-get update
    "${admin[@]}" apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
    docker_cmd=("${admin[@]}" docker)
    if ! "${docker_cmd[@]}" info >/dev/null 2>&1; then
        "${admin[@]}" systemctl start docker
        "${docker_cmd[@]}" info >/dev/null
    fi
fi

write_credentials() {
    local key value
    for key in POSTGRES_PASSWORD STORAGE_PASSWORD ADMIN_PASSWORD MODERATOR_PASSWORD DEMO_PASSWORD; do
        value=$(od -An -v -tx1 -N24 /dev/urandom | tr -d ' \n')
        printf '%s=%s\n' "$key" "$value"
    done
}

umask 077
if "$verify"; then
    env_file=$(mktemp .env.verify.XXXXXXXX)
    suffix=${env_file##*.}
    compose=("${docker_cmd[@]}" compose --env-file "$env_file"
        -f compose.yaml -f compose.verify.yaml -p "viewtube-verify-${suffix,,}")
    cleanup() {
        local result=$?
        if (( result != 0 )); then
            "${compose[@]}" logs --tail=60 bootstrap api worker >&2 || true
        fi
        if ! "${compose[@]}" down --volumes; then
            if (( result == 0 )); then result=1; fi
        fi
        rm -f -- "$env_file"
        exit "$result"
    }
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    write_credentials >"$env_file"
    unset POSTGRES_PASSWORD STORAGE_PASSWORD ADMIN_PASSWORD MODERATOR_PASSWORD DEMO_PASSWORD
    "${compose[@]}" up -d --build --wait --wait-timeout 900 api worker
    "${compose[@]}" run --rm --no-deps smoke
    exit 0
fi

if [[ ! -e .env ]]; then
    env_file=$(mktemp .env.XXXXXX)
    trap 'rm -f -- "$env_file"' EXIT
    write_credentials >"$env_file"
    mv -n -- "$env_file" .env
fi

"${docker_cmd[@]}" compose up -d --build --wait --wait-timeout 900
"${docker_cmd[@]}" compose port api 8000
echo 'Demo viewer: demo_viewer / DEMO_PASSWORD (from .env)'
echo 'Moderator: demo_mod / MODERATOR_PASSWORD (from .env)'
echo 'Administrator: admin / ADMIN_PASSWORD (from .env)'
