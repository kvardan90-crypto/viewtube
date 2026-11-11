#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

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
    "${admin[@]}" systemctl start docker
    docker_cmd=("${admin[@]}" docker)
fi

if [[ ! -e .env ]]; then
    umask 077
    env_file=$(mktemp .env.XXXXXX)
    trap 'rm -f -- "$env_file"' EXIT
    for key in POSTGRES_PASSWORD STORAGE_PASSWORD ADMIN_PASSWORD MODERATOR_PASSWORD DEMO_PASSWORD; do
        value=$(od -An -v -tx1 -N24 /dev/urandom | tr -d ' \n')
        printf '%s=%s\n' "$key" "$value" >>"$env_file"
    done
    mv -n -- "$env_file" .env
fi

"${docker_cmd[@]}" compose up -d --build --wait --wait-timeout 360
"${docker_cmd[@]}" compose port api 8000
echo 'Demo viewer: demo_viewer / DEMO_PASSWORD (from .env)'
echo 'Moderator: demo_mod / MODERATOR_PASSWORD (from .env)'
echo 'Administrator: admin / ADMIN_PASSWORD (from .env)'
