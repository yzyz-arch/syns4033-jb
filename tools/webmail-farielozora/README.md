# webmail-farielozora

Webmail self-hosted untuk **farielozora.biz.id**. Python stdlib only — tanpa pip,
tanpa nginx, tanpa database. Mailbox disimpan sebagai file `.eml` (maildir) di
`/var/lib/webmail-farielozora/mail/<user>/<Folder>/{new,cur,tmp}`.

## Status deploy (VPS 85.9.196.242)

- Service: `webmail-farielozora.service` (systemd, enabled, restart=always)
- URL: **http://85.9.196.242:8080**
- Backend: `local` (maildir), user pertama: `farielozora@farielozora.biz.id`
- Data: `/var/lib/webmail-farielozora/` (users.json 0600 + maildir)

## Perintah harian

```bash
systemctl status webmail-farielozora      # cek status
systemctl restart webmail-farielozora     # restart
journalctl -u webmail-farielozora -f      # log

cd /root/syns4033-jb/tools/webmail-farielozora
python3 manage.py list                                   # daftar user
python3 manage.py adduser nama@farielozora.biz.id 'PASS'  # tambah user
python3 manage.py passwd  nama@farielozora.biz.id 'PASS'  # ganti password
python3 manage.py seed    nama@farielozora.biz.id         # kirim pesan selamat datang
```

`manage.py` memakai env yang sama dengan service:
`WEBMAIL_USERS=/var/lib/webmail-farielozora/users.json` dan
`WEBMAIL_MAILDIR=/var/lib/webmail-farielozora/mail`.

## DNS yang harus ditambahkan di registrar (belum ada!)

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A    | `@` (farielozora.biz.id) | `85.9.196.242` | 300 |
| CNAME| `mail` | `farielozora.biz.id` | 300 |
| MX   | `@` | `mail.farielozora.biz.id` (priority 10) | 300 |
| TXT  | `@` | `v=spf1 mx -all` | 300 |
| TXT  | `_dmarc` | `v=DMARC1; p=quarantine; rua=mailto:postmaster@farielozora.biz.id` | 300 |

Setelah A record aktif, webmail bisa diakses di `http://farielozora.biz.id:8080`,
dan TLS bisa dipasang otomatis dengan Caddy:

```bash
apt-get install -y caddy
cat >/etc/caddy/Caddyfile <<'EOF'
mail.farielozora.biz.id {
    reverse_proxy 127.0.0.1:8080
}
EOF
systemctl enable --now caddy
```

## Batasan yang perlu diketahui

- Backend `local` = pengiriman **hanya antar-mailbox lokal** di VPS ini. Untuk
  email keluar/masuk internet, perlu MTA (Postfix/Dovecot) + DNS MX + PTR +
  port 25 terbuka di provider.
- Belum ada TLS. Jangan login lewat internet sebelum domain + Caddy aktif
  (password lewat HTTP polos bisa di-sniff).
- Session disimpan di memory proses → restart service = semua sesi logout.

## Ganti backend ke IMAP/SMTP nyata

Setelah Postfix/Dovecot siap, edit unit:

```
Environment=WEBMAIL_BACKEND=imap
Environment=WEBMAIL_IMAP=mail.farielozora.biz.id
Environment=WEBMAIL_SMTP=mail.farielozora.biz.id
```

lalu `systemctl daemon-reload && systemctl restart webmail-farielozora`.

## Test

```bash
./smoke_test.sh    # login, inbox, view, send, CSRF, logout end-to-end
```
