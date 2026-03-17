#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
SERVICE_NAME="postgres"
BACKUP_DIR="${REPO_ROOT}/backups/postgres"

usage() {
    cat <<'EOF'
Usage: scripts/backup_postgres.sh [-f COMPOSE_FILE]

Create a PostgreSQL backup from the docker compose postgres service.

Options:
  -f, --compose-file PATH  Override the default compose file
  -h, --help               Show this help message
EOF
}

error() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

require_command() {
    local command_name=$1

    if ! command -v "${command_name}" >/dev/null 2>&1; then
        error "missing required command: ${command_name}"
    fi
}

resolve_path_from_repo_root() {
    local path_value=$1

    if [[ "${path_value}" = /* ]]; then
        printf '%s\n' "${path_value}"
        return
    fi

    printf '%s\n' "${REPO_ROOT}/${path_value}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--compose-file)
            [[ $# -ge 2 ]] || error "missing value for $1"
            COMPOSE_FILE=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            error "unknown argument: $1"
            ;;
    esac
done

require_command docker
require_command gzip

COMPOSE_FILE=$(resolve_path_from_repo_root "${COMPOSE_FILE}")
[[ -f "${COMPOSE_FILE}" ]] || error "compose file not found: ${COMPOSE_FILE}"

COMPOSE_CMD=(docker compose -f "${COMPOSE_FILE}")

if ! "${COMPOSE_CMD[@]}" config --services | grep -Fxq "${SERVICE_NAME}"; then
    error "service '${SERVICE_NAME}' not found in ${COMPOSE_FILE}"
fi

if ! "${COMPOSE_CMD[@]}" ps --status running --services | grep -Fxq "${SERVICE_NAME}"; then
    error "service '${SERVICE_NAME}' is not running"
fi

mkdir -p "${BACKUP_DIR}"

DATABASE_NAME=$("${COMPOSE_CMD[@]}" exec -T "${SERVICE_NAME}" sh -lc 'printf "%s" "$POSTGRES_DB"')
[[ -n "${DATABASE_NAME}" ]] || error "POSTGRES_DB is empty inside service '${SERVICE_NAME}'"

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="${BACKUP_DIR}/${DATABASE_NAME}_${TIMESTAMP}.sql.gz"
TMP_FILE="${BACKUP_FILE}.tmp"

cleanup_tmp_file() {
    if [[ -n "${TMP_FILE:-}" && -f "${TMP_FILE}" ]]; then
        rm -f "${TMP_FILE}"
    fi
}

trap cleanup_tmp_file EXIT

"${COMPOSE_CMD[@]}" exec -T "${SERVICE_NAME}" sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -c > "${TMP_FILE}"

mv "${TMP_FILE}" "${BACKUP_FILE}"
trap - EXIT

printf 'Backup created: %s\n' "${BACKUP_FILE}"
