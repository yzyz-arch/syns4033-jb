#!/usr/bin/env bash
# check_mta.sh — status kesiapan MTA (Postfix + DKIM + DNS) farielozora.biz.id
#
# Jalankan kapan saja:  ./check_mta.sh
# Yang dicari: semua HIJAU -> email internet benar-benar jalan.
set -u
DOMAIN=${1:-farielozora.biz.id}
MAIL_HOST=mail.$DOMAIN
IPV4=85.9.196.242
SEL=default

ok()   { printf '  [OK]   %s\n' "$*"; }
bad()  { printf '  [X]    %s\n' "$*"; }
warn() { printf '  [!]    %s\n' "$*"; }

echo "== DNS =="
A=$(dig +short A "$DOMAIN" @1.1.1.1 | head -1)
[ "$A" = "$IPV4" ] && ok "A $DOMAIN -> $A" || bad "A $DOMAIN = '${A:-kosong}' (harus $IPV4)"
MA=$(dig +short A "$MAIL_HOST" @1.1.1.1 | head -1)
[ "$MA" = "$IPV4" ] && ok "A $MAIL_HOST -> $MA" || bad "A $MAIL_HOST = '${MA:-kosong}'"
MX=$(dig +short MX "$DOMAIN" @1.1.1.1 | head -1)
case "$MX" in *"$MAIL_HOST"*) ok "MX $MX";; *) bad "MX = '${MX:-kosong}'";; esac
dig +short TXT "$DOMAIN" @1.1.1.1 | grep -q 'v=spf1' && ok "SPF ada" || bad "SPF tidak ada"
dig +short TXT _dmarc."$DOMAIN" @1.1.1.1 | grep -q 'v=DMARC1' && ok "DMARC ada" || bad "DMARC tidak ada"
DKV=$(python3 - "$DOMAIN" "$SEL" <<'PY'
import re, subprocess, sys
d, s = sys.argv[1], sys.argv[2]
out = subprocess.run(["dig","+short","TXT",f"{s}._domainkey.{d}","@1.1.1.1"],
                     capture_output=True, text=True).stdout
val = "".join(re.findall(r'"([^"]*)"', out)).replace("\\", "")
m = re.search(r'p=([A-Za-z0-9+/=]+)', val)
print(m.group(1) if m else "")
PY
)
if [ -n "$DKV" ]; then
  LKV=$(python3 - "$DOMAIN" "$SEL" <<'PY'
import re, sys
d, s = sys.argv[1], sys.argv[2]
raw = open(f"/etc/opendkim/keys/{d}/{s}.txt").read().split("-----")[0]
val = "".join(re.findall(r'"([^"]*)"', raw))
print(re.search(r'p=([A-Za-z0-9+/=]+)', val).group(1))
PY
)
  [ "$DKV" = "$LKV" ] && ok "DKIM TXT cocok dengan private key" || bad "DKIM TXT beda dengan private key"
else
  bad "DKIM TXT $SEL._domainkey tidak ada"
fi

echo "== PTR (reverse DNS) =="
PTR=$(dig +short -x "$IPV4" @1.1.1.1)
case "$PTR" in
  "$MAIL_HOST".) ok "PTR $PTR" ;;
  *) bad "PTR '$PTR' != $MAIL_HOST (set di panel UpCloud)" ;;
esac

echo "== port 25 keluar (bisa kirim ke internet?) =="
if timeout 8 bash -c "exec 3<>/dev/tcp/gmail-smtp-in.l.google.com/25" 2>/dev/null; then
  ok "egress 25 terbuka"
else
  bad "egress 25 DIBLOKIR provider (minta unblock ke UpCloud)"
fi

echo "== port 25 masuk (bisa terima dari internet?) =="
if command -v curl >/dev/null; then
  RID=$(curl -sS -m 20 -H 'Accept: application/json' \
        "https://check-host.net/check-tcp?host=$IPV4:25&max_nodes=2" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin).get("request_id",""))' 2>/dev/null)
  if [ -n "$RID" ]; then
    sleep 14
    RES=$(curl -sS -m 20 -H 'Accept: application/json' "https://check-host.net/check-result/$RID")
    if echo "$RES" | grep -q 'timeout\|timed out\|Connection refused'; then
      bad "ingress 25 DIBLOKIR (hasil: $(echo "$RES" | grep -o 'error[^}]*' | head -1))"
    else
      ok "ingress 25 terbuka"
    fi
  else
    warn "tidak bisa query check-host.net"
  fi
fi

echo "== layanan lokal =="
for s in postfix opendkim webmail-farielozora; do
  systemctl is-active --quiet "$s" && ok "$s active" || bad "$s tidak active"
done
ss -lnt 2>/dev/null | grep -q ':25 ' && ok "postfix listen :25" || bad "postfix tidak listen :25"

echo "== TLS SMTP =="
if [ -f /etc/postfix/tls/mail.crt ]; then
  END=$(openssl x509 -in /etc/postfix/tls/mail.crt -noout -enddate 2>/dev/null | cut -d= -f2)
  ok "sertifikat s/d $END"
else
  bad "sertifikat Postfix tidak ada"
fi

echo "== antrean =="
Q=$(mailq 2>/dev/null | tail -1)
echo "  $Q"

echo
echo "Selesai. Kalau egress+ingress 25 masih [X]: email internet belum bisa,"
echo "semua komponen lain sudah siap dan akan langsung jalan setelah port dibuka."
