#!/bin/bash
# sync-postfix-tls.sh — salin sertifikat Caddy (Let's Encrypt) ke Postfix.
# Caddy renew otomatis; timer systemd menjalankan script ini tiap 6 jam,
# lalu reload Postfix kalau sertifikat berubah.
set -eu

SRC_DIR=/var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory/mail.farielozora.biz.id
SRC_CRT=$SRC_DIR/mail.farielozora.biz.id.crt
SRC_KEY=$SRC_DIR/mail.farielozora.biz.id.key
DST_DIR=/etc/postfix/tls
DST_CRT=$DST_DIR/mail.crt
DST_KEY=$DST_DIR/mail.key

[ -f "$SRC_CRT" ] || { echo "cert tidak ada: $SRC_CRT" >&2; exit 1; }
[ -f "$SRC_KEY" ] || { echo "key tidak ada: $SRC_KEY" >&2; exit 1; }

mkdir -p "$DST_DIR"
changed=0

if ! cmp -s "$SRC_CRT" "$DST_CRT" 2>/dev/null; then
  install -m 644 -o root -g postfix "$SRC_CRT" "$DST_CRT"
  changed=1
fi
if ! cmp -s "$SRC_KEY" "$DST_KEY" 2>/dev/null; then
  install -m 640 -o root -g postfix "$SRC_KEY" "$DST_KEY"
  changed=1
fi

if [ "$changed" = "1" ]; then
  echo "sertifikat diperbarui -> reload postfix"
  systemctl reload postfix || systemctl restart postfix
else
  echo "sertifikat sama, tidak ada perubahan"
fi
