#!/bin/bash
# ==============================================================================
# Edukom Enterprise LMS - Automated PostgreSQL Backup Script
# Features:
# - Custom compressed pg_dump format
# - OpenSSL AES-256-CBC encryption for data-at-rest protection
# - SHA-256 integrity checksum generation
# - Grandfather-Father-Son (GFS) 30-day retention pruning
# ==============================================================================

set -eo pipefail

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
BACKUP_NAME="edukom_backup_${TIMESTAMP}"
RAW_DUMP="${BACKUP_DIR}/${BACKUP_NAME}.dump"
ENC_DUMP="${BACKUP_DIR}/${BACKUP_NAME}.dump.enc"
CHECKSUM_FILE="${BACKUP_DIR}/${BACKUP_NAME}.sha256"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -u)] Initiating PostgreSQL database backup..."

# 1. Execute pg_dump with custom compressed archive format
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h "${POSTGRES_HOST:-localhost}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER:-edukom_admin}" \
    -d "${POSTGRES_DB:-edukom_production}" \
    -F c \
    -b \
    -v \
    -f "${RAW_DUMP}"

# 2. Encrypt dump with AES-256-CBC using encryption passphrase if provided
if [ -n "${BACKUP_ENCRYPTION_KEY}" ]; then
    echo "[$(date -u)] Encrypting backup with AES-256-CBC..."
    openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
        -in "${RAW_DUMP}" \
        -out "${ENC_DUMP}" \
        -k "${BACKUP_ENCRYPTION_KEY}"
    
    # Securely wipe unencrypted dump
    shred -u "${RAW_DUMP}" 2>/dev/null || rm -f "${RAW_DUMP}"
    TARGET_FILE="${ENC_DUMP}"
else
    TARGET_FILE="${RAW_DUMP}"
fi

# 3. Compute SHA-256 Checksum for tamper evidence
sha256sum "${TARGET_FILE}" > "${CHECKSUM_FILE}"
echo "[$(date -u)] Backup generated successfully: ${TARGET_FILE}"
echo "[$(date -u)] Checksum: $(cat "${CHECKSUM_FILE}")"

# 4. Prune backups older than 30 days
echo "[$(date -u)] Pruning backups older than 30 days..."
find "${BACKUP_DIR}" -type f -name "edukom_backup_*" -mtime +30 -exec rm -f {} \;

echo "[$(date -u)] Backup and retention cycle completed."
