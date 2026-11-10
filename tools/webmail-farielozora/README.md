# webmail-farielozora

Webmail self-hosted untuk **farielozora.biz.id**. Python stdlib only — tanpa pip,
tanpa nginx, tanpa database. Mailbox disimpan sebagai file `.eml` (maildir) di
`/var/lib/webmail-farielozora/mail/<user>/<Folder>/{new,cur,tmp}`.

## Status deploy (VPS 85.9.196.242)

- Service: `webmail-farielozora.service` (systemd, enabled, restart=always)
- URL: **https://farielozora.biz.id** (juga `www.` dan `mail.`) — TLS Let's Encrypt via Caddy
- Fallback: `http://85.9.196.242:8080` (plaintext, jangan dipakai login)
- Backend: `local` (maildir), user pertama: `farielozora@farielozora.biz.id`
- Data: `/var/lib/webmail-farielozora/` (users.json 0600 + maildir + stars.json)

## Dua antarmuka

| Path | Isi |
|---|---|
| `/` | **SPA Cloud Mail** (`ui/`) — tampilan & fitur mengikuti mail.flame.edu.kg |
| `/api/*` | JSON API untuk SPA (`api.py`) |
| `/login`, `/inbox`, `/view`, `/compose`, `/send` | UI lama stdlib (masih jalan, dipakai smoke test) |

SPA tidak butuh build step dan tidak butuh CDN: Vue 3 dipinjam dari
`ui/vendor/vue.mjs`, ikon SVG inline, CSS ditulis sendiri dengan token warna
Cloud Mail (`--el-color-primary: #1890ff`, aside `#191A23`, dsb).

Fitur SPA: login, folder Inbox/Sent/Drafts/Trash, list virtual-friendly dengan
checkbox + star + unread dot, buka pesan (body HTML di iframe sandbox), reply,
forward, compose panel, hapus, tandai dibaca, cari (subjek/isi/pengirim) dengan
highlight, dark mode, responsif sampai 390px.

Endpoint API (cookie `webmail_session`):

```
POST /api/login   {email,password}      GET  /api/me
POST /api/logout                        GET  /api/folders
GET  /api/emails?folder=&offset=&size=  GET  /api/email?folder=&uid=
GET  /api/search?q=&type=&folder=       GET  /api/attach?folder=&uid=&idx=
POST /api/send    {to,cc,subject,body}  POST /api/star {folder,uid,star}
POST /api/read    {folder,uids[]}       POST /api/delete {folder,uids[]}
```

## Status DNS (sudah aktif)

Record dibuat via `cf_dns.py` (Cloudflare API, DNS-only / grey cloud):

| Type | Name | Content |
|---|---|---|
| A | farielozora.biz.id | 85.9.196.242 |
| A | mail.farielozora.biz.id | 85.9.196.242 |
| CNAME | www.farielozora.biz.id | farielozora.biz.id |
| MX | farielozora.biz.id (prio 10) | mail.farielozora.biz.id |
| TXT | farielozora.biz.id | `v=spf1 mx -all` |
| TXT | _dmarc.farielozora.biz.id | `v=DMARC1; p=quarantine; ...` |

Token Cloudflare disimpan di VPS: `/root/.cf_token` (0600). Jalankan ulang:

```bash
cd tools/webmail-farielozora
CF_TOKEN="$(cat /root/.cf_token)" python3 cf_dns.py      # idempotent
CF_TOKEN="$(cat /root/.cf_token)" python3 cf_dns.py --dry-run
```

## Smoke test

```bash
WEBMAIL_TEST_PASS='password-kamu' ./smoke_test.sh
```

27 cek: 13 untuk UI lama (login, inbox, view, send, CSRF, logout) + 14 untuk
API SPA (login/me/folders/emails/email/star/search/send/delete/logout).
Password tidak disimpan di repo.


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

### Cara cepat: import zone file (Cloudflare)

1. Cloudflare Dashboard -> pilih `farielozora.biz.id` -> **DNS** -> **Records**
2. Klik **Import** -> tempel isi `cloudflare-zone.txt` (atau upload file itu)
3. Pastikan semua record **Proxy status = DNS only (grey cloud)** saat pertama setup
4. Setelah sertifikat Let's Encrypt terbit (cek `journalctl -u caddy -f`), root domain
   boleh diubah ke **Proxied (orange cloud)** dengan SSL/TLS mode **Full (strict)**

### Record manual

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| A    | `@` | `85.9.196.242` | DNS only | Auto |
| A    | `mail` | `85.9.196.242` | DNS only | Auto |
| CNAME| `www` | `farielozora.biz.id` | DNS only | Auto |
| MX   | `@` | `mail.farielozora.biz.id` priority 10 | - | Auto |
| TXT  | `@` | `v=spf1 mx -all` | - | Auto |
| TXT  | `_dmarc` | `v=DMARC1; p=quarantine; rua=mailto:postmaster@farielozora.biz.id` | - | Auto |

### Catatan khusus Cloudflare

- **Email Routing**: kalau aktif, Cloudflare menaruh MX sendiri (route1.mx.cloudflare.net).
  Matikan dulu (Email -> Email Routing -> Disable) atau MX di atas tidak akan berfungsi.
- **`mail` wajib grey cloud** — Cloudflare tidak memproxy port 25/143/993, dan MX target
  yang di-proxy akan merusak email.
- **Port 8080**: Cloudflare memang mendukung proxy port 8080, tapi hanya HTTP. Karena
  Caddy sudah menangani 443, akses lewat `https://mail.farielozora.biz.id` saja.
- **CAA**: tidak perlu; Caddy memakai Let's Encrypt dan Cloudflare otomatis mengizinkannya.
- **PTR/rDNS** (untuk email keluar nanti) diatur di panel provider VPS, bukan Cloudflare.

Setelah A record aktif, Caddy (sudah terpasang dan jalan) otomatis menerbitkan
sertifikat Let's Encrypt untuk `farielozora.biz.id` dan `mail.farielozora.biz.id`:

```bash
journalctl -u caddy -f          # pantau penerbitan sertifikat
curl -I https://mail.farielozora.biz.id
```

Caddyfile aktif: `/etc/caddy/Caddyfile` (reverse_proxy 127.0.0.1:8080, redirect
HTTP->HTTPS, HSTS). Setelah HTTPS hidup, port 8080 bisa ditutup dari publik:

```bash
# batasi webmail hanya untuk Caddy
sed -i 's/^Environment=WEBMAIL_BIND=0.0.0.0/Environment=WEBMAIL_BIND=127.0.0.1/' \
  /etc/systemd/system/webmail-farielozora.service
systemctl daemon-reload && systemctl restart webmail-farielozora
```

## Batasan yang perlu diketahui

- Backend `local` = pengiriman **hanya antar-mailbox lokal** di VPS ini. Untuk
  email keluar/masuk internet, perlu MTA (Postfix/Dovecot) + DNS MX + PTR +
  port 25 terbuka di provider.
- TLS aktif: `https://farielozora.biz.id`, `https://www.farielozora.biz.id`,
  `https://mail.farielozora.biz.id` — sertifikat Let's Encrypt otomatis oleh Caddy
  (http-01). HTTP :80 di-redirect 308 ke HTTPS. `Secure` pada cookie session
  dipasang otomatis saat request lewat Caddy (`X-Forwarded-Proto: https`).
  Login lewat `http://85.9.196.242:8080` masih mungkin secara teknis, tapi
  jangan — password lewat plaintext.
- Session disimpan di memory proses → restart service = semua sesi logout.
- Belum ada rate-limit login. Kalau port/domain terekspos publik, tambahkan
  throttle per-IP sebelum dipakai luas.

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
