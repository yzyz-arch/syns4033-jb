#!/usr/bin/env bash
# E2E smoke test for webmail-farielozora
set -u
BASE=http://127.0.0.1:8080
JAR=/tmp/wm.jar
rm -f "$JAR"
P='cGNJOLjMQFm0KB'
U='farielozora@farielozora.biz.id'

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "1) login page            : $(code "$BASE/")"
echo "2) inbox unauth (expect 302): $(curl -s -o /dev/null -w '%{http_code}' "$BASE/inbox")"
echo "3) wrong password        : $(code -d "email=$U&password=salah" "$BASE/login")"
echo "4) login correct         : $(curl -s -c "$JAR" -o /dev/null -w '%{http_code} -> %{redirect_url}' -d "email=$U&password=$P" "$BASE/login")"
echo "5) inbox as user         :"
curl -s -b "$JAR" "$BASE/inbox" | grep -oE 'Selamat datang[^<]*|[0-9]+ pesan terbaru' | head -3
UIDF=$(find /var/lib/webmail-farielozora/mail/*/INBOX -name '*.eml' | head -1 | xargs -r basename)
echo "6) open message ($UIDF):"
curl -s -b "$JAR" "$BASE/view?folder=INBOX&uid=$UIDF" | grep -oE 'Mailbox [a-z.]+ sudah aktif' | head -2
CSRF=$(curl -s -b "$JAR" "$BASE/compose" | grep -oE 'name="csrf" value="[0-9a-f]+"' | head -1 | sed 's/.*value="//;s/"//')
echo "7) compose csrf          : ${CSRF:0:12}..."
echo "8) send to self          :"
curl -s -b "$JAR" -d "csrf=$CSRF&to=$U&subject=Test kirim dari webmail&body=Kalau pesan ini masuk INBOX, SMTP/send jalan." "$BASE/send" | grep -oE 'Pesan terkirim|Gagal mengirim[^<]*' | head -2
echo "9) maildir INBOX count   : $(ls /var/lib/webmail-farielozora/mail/*/INBOX/new /var/lib/webmail-farielozora/mail/*/INBOX/cur 2>/dev/null | wc -l)"
echo "10) Sent folder count    : $(ls /var/lib/webmail-farielozora/mail/*/Sent/new /var/lib/webmail-farielozora/mail/*/Sent/cur 2>/dev/null | wc -l)"
echo "11) non-csrf send (expect 403): $(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -d "to=$U&subject=x&body=y" "$BASE/send")"
echo "12) logout               : $(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "$BASE/logout")"
echo "13) inbox after logout   : $(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "$BASE/inbox")"
