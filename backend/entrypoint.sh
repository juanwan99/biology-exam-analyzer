#!/bin/sh
set -e

HASH_FILE="/tmp/.requirements_hash"
CURRENT_HASH=$(sha256sum /app/requirements.txt | cut -d" " -f1)
STORED_HASH=""
[ -f "$HASH_FILE" ] && STORED_HASH=$(cat "$HASH_FILE")

if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
    echo "[entrypoint] requirements.txt changed, installing dependencies..."
    pip install --no-cache-dir -r /app/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q
    echo "$CURRENT_HASH" > "$HASH_FILE"
    echo "[entrypoint] dependencies updated."
else
    echo "[entrypoint] requirements.txt unchanged, skipping pip install."
fi

exec "$@"
