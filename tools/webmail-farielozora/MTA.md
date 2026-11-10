# MTA — email internet untuk farielozora.biz.id

Stack: **Postfix 3.10** (SMTP) + **OpenDKIM** (tanda tangan) + **pipe transport**
ke maildir webmail. Tidak pakai Dovecot: webmail membaca maildir langsung.

```
internet ──:25──▶ Postfix ──pipe──▶ /var/lib/webmail-farielozora/mail/<user>/INBOX/new/*.eml
webmail  ──:25(127.0.0.1)──▶ Postfix ──▶ DKIM sign ──▶ MX tujuan
```

## Status sekarang

| Komponen | Status |
|---|---|
| Apex + mail A record | OK (85.9.196.242) |
| MX 10 mail.farielozora.biz.id | OK |
| SPF `v=spf1 mx -all` | OK |
| DMARC `p=quarantine` | OK |
| DKIM `default._domainkey` (2048-bit) | OK, TXT cocok dengan private key |
| Postfix listen :25 + STARTTLS | OK (sertifikat Let's Encrypt s/d Feb 2027) |
| OpenDKIM milter (unix socket) | OK, semua mail keluar ditandatangani |
| Delivery ke maildir | OK, teruji end-to-end |
| Relay dibatasi (bukan open relay) | OK, klien luar ditolak 554 |
| **Port 25 keluar** | **DIBLOKIR UpCloud** |
| **Port 25 masuk** | **DIBLOKIR UpCloud** |
| **PTR / reverse DNS** | **masih `...upcloud.host`** |

Sampai tiga baris terakhir beres, email ke/dari Gmail dkk **belum** bisa. Semua
komponen di sisi server sudah siap dan akan langsung jalan begitu port dibuka.

## Yang harus dilakukan di panel UpCloud

1. **Buka tiket support** minta unblock port 25 (inbound + outbound) untuk
   `85.9.196.242`. Ini prosedur normal; mereka biasanya minta penjelasan singkat.
   Contoh isi tiket:

   > Please unblock TCP port 25 outbound and inbound for 85.9.196.242
   > (hostname 1tb-us-nyc1). We run a legitimate mail server for
   > farielozora.biz.id: Postfix with DKIM signing, valid SPF/DMARC, and no
   > open relay (relay is restricted to the local webmail only). We will also
   > set reverse DNS to mail.farielozora.biz.id.

2. **Set reverse DNS / PTR** `85.9.196.242` → `mail.farielozora.biz.id`
   (UpCloud: Server → Network → Reverse DNS). Tanpa PTR yang cocok, Gmail dan
   Outlook hampir pasti menolak atau menandai spam.

3. Setelah keduanya aktif, jalankan:

   ```bash
   cd /root/syns4033-jb/tools/webmail-farielozora
   ./check_mta.sh
   ```

   Semua baris harus `[OK]`. Lalu tes kirim dari webmail ke Gmail.

## Kalau port 25 tetap diblokir (alternatif)

Kalau UpCloud menolak unblock, dua opsi:

- **Relay keluar lewat smarthost**: isi `relayhost` Postfix dengan SMTP relay
  pihak ketiga (butuh akun + kredensial). Port 465/587 juga diblokir provider
  ini, jadi relay harus lewat port yang diizinkan — cek dulu.
- **Inbound**: pakai domain lain yang punya mail server, lalu tarik pesan ke
  sini pakai fetchmail/IMAP poll. Ini hanya menambal, bukan solusi asli.

## Ops harian

```bash
mailq                                  # antrean
postqueue -f                           # paksa kirim ulang
postsuper -d ALL                       # hapus semua antrean (hati-hati)
journalctl -u postfix -f               # log realtime
journalctl -u opendkim -f              # log DKIM
./check_mta.sh                         # status lengkap
```

Sertifikat TLS Postfix disalin dari Caddy oleh
`postfix-tls-sync.timer` (tiap 6 jam). Kalau cert Caddy diperbarui, Postfix
otomatis ikut.

## Pengaturan penting

| Setting | Nilai | Alasan |
|---|---|---|
| `mynetworks` | `127.0.0.0/8` | hanya webmail lokal yang boleh relay |
| `virtual_mailbox_domains` | farielozora.biz.id | domain yang dilayani |
| `virtual_mailbox_maps` | `texthash:/etc/postfix/vmailbox` | recipient tak ada ditolak saat SMTP (550), bukan bounce |
| `virtual_transport` | `webmail-deliver` | kirim ke maildir via script |
| `smtpd_relay_restrictions` | permit_mynetworks, reject_unauth_destination | anti open relay |
| `smtpd_milters` | `unix:/run/opendkim/opendkim.sock` | DKIM sign |
| `WEBMAIL_RELAY` | `127.0.0.1:25` | webmail submit ke Postfix |
| `WEBMAIL_SEND_LIMIT` | `200` | kuota kirim per user per hari |

`vmailbox` digenerate dari `users.json`. Setiap user baru (registrasi web)
harus memicu regenerate — jalankan `python3 sync_vmailbox.py` setelahnya.

Catatan: port 8888-8900 di VPS ini dipakai proses lain (`/tmp/floppyx.py`),
karena itu milter OpenDKIM memakai unix socket, bukan TCP.
