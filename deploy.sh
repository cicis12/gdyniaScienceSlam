#!/usr/bin/env bash
# Gdynia Science Slam: readable, interactive Docker Compose deployment.
# Run this in the HOST terminal, from a complete copy of the project.
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
export GSS_DEPLOY_DIR="${GSS_DEPLOY_DIR:-$PROJECT_DIR/.deploy}"
COMPOSE_PROJECT="${GSS_COMPOSE_PROJECT:-gdynia-science-slam}"
ACTION="${1:-deploy}"

usage() {
    cat <<'HELP'
Usage: ./deploy.sh [command]

  (no command)       Configure, build, migrate, and start the website
  --configure-only   Collect credentials and settings without starting containers
  --check            Validate saved settings and Compose configuration
  status             Show running services
  logs               Follow service logs
  stop               Stop the stack without deleting its data
  start              Start an already initialized stack
  backup             Save database, uploads, certificates, and configuration
  --help             Show this help

Configuration is stored in .deploy/ and reused on subsequent runs.
Run from your host terminal. Docker Engine + Compose and Python 3 are required.
HELP
}

compose() {
    env -u SITE_DOMAIN -u ACME_EMAIL -u APP_WORKERS -u BIND_ADDRESS \
        docker compose --project-name "$COMPOSE_PROJECT" \
        --env-file "$GSS_DEPLOY_DIR/site.env" -f "$PROJECT_DIR/compose.yaml" "$@"
}

pause_for_input() {
    if [[ ! -t 0 ]]; then
        echo "Interactive input is required. Run ./deploy.sh in a terminal." >&2
        exit 1
    fi
    read -r -p "$1 Press Enter when ready, or Ctrl+C to stop. "
}

require_docker() {
    if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
        echo "Install Docker Engine and the Docker Compose plugin for your OS:"
        echo "https://docs.docker.com/engine/install/"
        pause_for_input "Docker installation needs your host administrator access."
    fi
    docker compose version >/dev/null
    if ! docker info >/dev/null 2>&1; then
        echo "Docker is installed, but this terminal cannot reach its daemon."
        pause_for_input "Start Docker or fix your Docker access permissions."
        docker info >/dev/null
    fi
}

require_configuration() {
    python3 scripts/deploy_support.py check --directory "$GSS_DEPLOY_DIR"
}

trap 'echo "Step failed. Existing data has not been automatically deleted. Check the error above and use ./deploy.sh logs." >&2' ERR

[[ "$ACTION" == "--help" ]] && { usage; exit 0; }
if ! command -v python3 >/dev/null; then
    echo "Install Python 3 using your host package manager."
    pause_for_input "The configuration helper needs Python 3."
    command -v python3 >/dev/null
fi

case "$ACTION" in
    --configure-only)
        python3 scripts/deploy_support.py configure --directory "$GSS_DEPLOY_DIR"
        exit 0
        ;;
    --check)
        require_configuration
        docker compose version >/dev/null
        compose config --quiet
        echo "Deployment configuration is valid. No services were started."
        exit 0
        ;;
    status|logs|stop|start)
        require_docker
        require_configuration
        case "$ACTION" in
            status) compose ps ;;
            logs) compose logs --follow --tail 100 ;;
            stop) compose stop ;;
            start) compose up -d --wait app proxy ;;
        esac
        exit 0
        ;;
    backup)
        require_docker
        require_configuration
        # Pause writes so the DB dump and uploaded files describe the same state.
        mkdir -p "$PROJECT_DIR/backups"
        chmod 700 "$PROJECT_DIR/backups"
        BACKUP_DIR="$(mktemp -d "$PROJECT_DIR/backups/$(date -u +%Y%m%d-%H%M%S)-UTC-XXXXXX")"
        compose stop app
        trap 'compose start app >/dev/null || true' EXIT
        compose exec -T db pg_dump -U postgres -d gdynia_science_slam -Fc > "$BACKUP_DIR/database.dump"
        compose run --rm --no-deps -T --entrypoint python app scripts/deploy_support.py archive-uploads > "$BACKUP_DIR/uploads.tar.gz"
        compose exec -T proxy tar -czf - -C /data . > "$BACKUP_DIR/caddy-data.tar.gz"
        tar -czf "$BACKUP_DIR/configuration.tar.gz" -C "$GSS_DEPLOY_DIR" .
        compose up -d --wait app
        trap - EXIT
        echo "Backup saved to $BACKUP_DIR (contains credentials; store it privately)."
        exit 0
        ;;
    deploy) ;;
    *) usage; exit 1 ;;
esac

# 1. Collect settings. Existing secrets and account passwords are preserved.
require_docker
python3 scripts/deploy_support.py configure --directory "$GSS_DEPLOY_DIR"
require_configuration
compose config --quiet

# File-backed Docker secrets need a shared container-readable SELinux type on enforcing hosts.
if [[ "$(docker info --format '{{json .SecurityOptions}}')" == *selinux* ]]; then
    if ! chcon -R -t container_file_t "$GSS_DEPLOY_DIR/secrets"; then
        pause_for_input "Label the deployment secrets container_file_t on this SELinux host."
        chcon -R -t container_file_t "$GSS_DEPLOY_DIR/secrets"
    fi
fi

# 2. DNS and firewall configuration depend on your domain provider and host.
DOMAIN="$(python3 scripts/deploy_support.py domain --directory "$GSS_DEPLOY_DIR")"
if [[ "$DOMAIN" != "localhost" ]] && [[ ! -f "$GSS_DEPLOY_DIR/deployed-domain" || "$(cat "$GSS_DEPLOY_DIR/deployed-domain")" != "$DOMAIN" ]]; then
    echo "Point the A DNS record for $DOMAIN to this server IPv4 address."
    echo "Only add AAAA after configuring an IPv6 proxy binding; the default binding is IPv4."
    echo "Allow inbound TCP ports 80 and 443 in the host and provider firewalls."
    pause_for_input "These external settings cannot be changed by this script."
fi

# 3. Build code and dependencies into an image. Persistent data stays in volumes.
echo "Building the application image..."
compose build app

# 4. Start PostgreSQL and Redis and wait until they are ready.
echo "Starting database and shared rate-limit storage..."
compose up -d --wait --wait-timeout 180 db redis

# 5. Set up database roles/schema/permissions and the first superadmin.
echo "Applying database setup and migrations..."
compose run --rm --no-deps -T bootstrap
python3 scripts/deploy_support.py clear-bootstrap-password --directory "$GSS_DEPLOY_DIR"

# 6. Start the application and HTTPS proxy; login health checks verify readiness.
echo "Starting the website and HTTPS proxy..."
compose up -d --wait --wait-timeout 180 --force-recreate app proxy
printf '%s\n' "$DOMAIN" > "$GSS_DEPLOY_DIR/deployed-domain"
compose ps

echo "Open https://$DOMAIN/admin"
if [[ "$DOMAIN" == "localhost" ]]; then
    echo "Local HTTPS uses Caddy's own CA. See README.md for trusting its certificate."
else
    echo "Caddy will obtain and renew the public HTTPS certificate automatically."
fi
echo "Run ./deploy.sh backup regularly; keep backups off this machine too."
