#!/bin/bash
# ==============================================================================
# Edukom Enterprise LMS - PostgreSQL Point-In-Time Disaster Recovery Restore Script
# Features:
# - Integrity validation via SHA-256 checksum
# - Decryption of AES-256-CBC archives
# - Clean pre-flight connection drops & pg_restore
# ==============================================================================

set -eo pipefail

BACKUP_FILE="$1"

if [ -z "${BACKUP_FILE}" ]; then
    echo "Usage: $0 <path_to_backup_file> [encryption_key]"
    exit 1
fi

CHECKSUM_FILE="${BACKUP_FILE%.enc}.sha256"
CHECKSUM_FILE="${CHECKSUM_FILE%.dump}.sha256"

# 1. Verify Checksum if present
if [ -f "${CHECKSUM_FILE}" ]; then
    echo "[$(date -u)] Verifying archive integrity via SHA-256..."
    sha256sum -c "${CHECKSUM_FILE}"
    echo "[$(date -u)] SHA-256 checksum verified."
fi

WORK_FILE="${BACKUP_FILE}"

# 2. Decrypt if file ends with .enc
if [[ "${BACKUP_FILE}" == *.enc ]]; then
    KEY="${2:-$BACKUP_ENCRYPTION_KEY}"
    if [ -z "${KEY}" ]; then
        echo "Error: Backup file is encrypted, but no encryption key provided."
        exit 1
    fi
    echo "[$(date -u)] Decrypting AES-256-CBC archive..."
    DECRYPTED_TMP="/tmp/restore_$(date +%s).dump"
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
        -in "${BACKUP_FILE}" \
        -out "${DECRYPTED_TMP}" \
        -k "${KEY}"
    WORK_FILE="${DECRYPTED_TMP}"
fi

# 3. Terminate active database connections before restore
echo "[$(date -u)] Terminating active connections to database ${POSTGRES_DB}..."
PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    -h "${POSTGRES_HOST:-localhost}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER:-edukom_admin}" \
    -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" || true

# 4. Execute pg_restore with clean overwrite
echo "[$(date -u)] Restoring database from archive ${WORK_FILE}..."
PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
    -h "${POSTGRES_HOST:-localhost}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER:-edukom_admin}" \
    -d "${POSTGRES_DB:-edukom_production}" \
    --clean \
    --if-exists \
    -v \
    "${WORK_FILE}"

# Clean up decrypted temporary file
if [ "${WORK_FILE}" != "${BACKUP_FILE}" ]; then
    rm -f "${WORK_FILE}"
fi

echo "[$(date -u)] Database restore completed successfully."
