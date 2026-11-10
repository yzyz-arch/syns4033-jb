#!/usr/bin/env bash
# E2E smoke test for webmail-farielozora
#
# Cover dua muka:
#   1-13  UI lama  (/login, /inbox, /view, /compose, /send, /logout)
#   14-25 JSON API untuk SPA Cloud-Mail (/api/*)
#
# Password TIDAK disimpan di repo. Pakai env:
#   WEBMAIL_TEST_PASS='password-kamu' ./smoke_test.sh
# atau argumen pertama:
#   ./smoke_test.sh 'password-kamu'
set -u
BASE=${WEBMAIL_BASE:-http://127.0.0.1:8080}
JAR=/tmp/wm.jar
JAR2=/tmp/wm-api.jar
rm -f "$JAR" "$JAR2"
U=${WEBMAIL_TEST_USER:-farielozora@farielozora.biz.id}
P=${WEBMAIL_TEST_PASS:-${1:-}}
if [ -z "$P" ]; then
  echo "usage: WEBMAIL_TEST_PASS='...' $0   (atau: $0 '...')" >&2
  exit 2
fi

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
api()  { curl -s -H 'Content-Type: application/json' -b "$JAR2" "$@"; }

echo "== UI lama =="
echo "1) login page            : $(code "$BASE/login")"
echo "2) inbox unauth (expect 302): $(code "$BASE/inbox")"
echo "3) wrong password        : $(code -d "email=$U&password=salah" "$BASE/login")"
echo "4) login correct         : $(curl -s -c "$JAR" -o /dev/null -w '%{http_code} -> %{redirect_url}' -d "email=$U&password=$P" "$BASE/login")"
echo "5) inbox as user         :"
curl -s -b "$JAR" "$BASE/inbox" | grep -oE 'Selamat datang[^<]*|[0-9]+ pesan terbaru' | head -3
UIDF=$(curl -s -b "$JAR" "$BASE/inbox" | grep -oE 'uid=[^&"'"'"']+\.eml' | head -1 | sed 's/^uid=//')
echo "6) open message ($UIDF):"
curl -s -b "$JAR" "$BASE/view?folder=INBOX&uid=$UIDF" | grep -oE 'Mailbox [a-z.]+ sudah aktif' | head -2
CSRF=$(curl -s -b "$JAR" "$BASE/compose" | grep -oE 'name="csrf" value="[0-9a-f]+"' | head -1 | sed 's/.*value="//;s/"//')
echo "7) compose csrf          : ${CSRF:0:12}..."
echo "8) send to self          :"
curl -s -b "$JAR" -d "csrf=$CSRF&to=$U&subject=Test kirim dari webmail&body=Kalau pesan ini masuk INBOX, send jalan." "$BASE/send" | grep -oE 'Pesan terkirim|Gagal mengirim[^<]*' | head -2
echo "9) maildir INBOX count   : $(ls /var/lib/webmail-farielozora/mail/*/INBOX/cur /var/lib/webmail-farielozora/mail/*/INBOX/new 2>/dev/null | grep -c eml)"
echo "10) Sent folder count    : $(ls /var/lib/webmail-farielozora/mail/*/Sent/cur /var/lib/webmail-farielozora/mail/*/Sent/new 2>/dev/null | grep -c eml)"
echo "11) non-csrf send (expect 403): $(code -b "$JAR" -d "to=$U&subject=x&body=y" "$BASE/send")"
echo "12) logout               : $(code -b "$JAR" "$BASE/logout")"
echo "13) inbox after logout   : $(code -b "$JAR" "$BASE/inbox")"

echo
echo "== JSON API (SPA) =="
echo "14) SPA shell (expect 200): $(code "$BASE/")"
echo "15) /api/me unauth (expect 401): $(code "$BASE/api/me")"
echo "16) /api/login bad (expect 401): $(code -X POST -H 'Content-Type: application/json' \
  -d "{\"email\":\"$U\",\"password\":\"salah\"}" "$BASE/api/login")"
TOK=$(curl -s -c "$JAR2" -X POST -H 'Content-Type: application/json' \
  -d "{\"email\":\"$U\",\"password\":\"$P\"}" "$BASE/api/login" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("user",{}).get("email",""))')
echo "17) /api/login ok        : ${TOK:-GAGAL}"
echo "18) /api/me              : $(api "$BASE/api/me" | head -c 80)"
echo "19) /api/folders         : $(api "$BASE/api/folders" | head -c 120)"
echo "20) /api/emails INBOX    : $(api "$BASE/api/emails?folder=INBOX&size=2" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("total",d["total"],"| first:",(d["list"][0]["subject"] if d["list"] else "-")[:40])')"
APUID=$(api "$BASE/api/emails?folder=INBOX&size=1" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["list"][0]["uid"] if d["list"] else "")')
echo "21) /api/email detail    : $(api "$BASE/api/email?folder=INBOX&uid=$APUID" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("subject:",d.get("subject","-")[:40],"| from:",d.get("name","-")[:30])')"
echo "22) /api/star on         : $(api -X POST -d "{\"folder\":\"INBOX\",\"uid\":\"$APUID\",\"star\":1}" "$BASE/api/star")"
echo "23) /api/star off        : $(api -X POST -d "{\"folder\":\"INBOX\",\"uid\":\"$APUID\",\"star\":0}" "$BASE/api/star")"
echo "24) /api/search          : $(api "$BASE/api/search?q=Test&type=subject&folder=INBOX" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("hits",d["total"])')"
echo "25) /api/send            : $(api -X POST \
  -d "{\"to\":\"$U\",\"subject\":\"API smoke\",\"body\":\"dari smoke test\"}" "$BASE/api/send" | head -c 140)"
echo "26) /api/logout          : $(api -X POST -d '{}' "$BASE/api/logout")"
echo "27) /api/me after logout (expect 401): $(code -b "$JAR2" "$BASE/api/me")"
