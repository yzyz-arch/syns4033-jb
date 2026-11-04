# OTP Rate-Limit Lab

Harness buat nguji jalur request OTP di service **punya sendiri**: apakah limiter-nya
beneran nahan burst, dan apakah kode OTP bocor di response body.

Bukan SMS bomber. Yang di-fire itu HTTP request ke endpoint lu, pakai nomor test lu.
Dua yang diukur justru dua hal yang bikin endpoint orang jadi senjata:
per-identifier throttle dan per-IP throttle.

## Files

    otp_lab.py           harness (stdlib + requests)
    mock_otp_server.py   server demo 3 mode, buat baseline
    r1.json r2.json r3.json   hasil run contoh (FAIL / PASS / PASS+leak)

## Dua mode

    --mode same-phone     satu nomor, N request        -> nguji throttle per-nomor
    --mode unique-phones  N nomor dari satu sumber     -> nguji throttle per-IP/per-device

Mode `same-phone` yang paling penting. Kalau nomor yang sama dapat OTP tanpa batas,
endpoint lu bisa dipakai buat ngeflood HP siapa pun.

## Run

    # terminal 1
    python3 mock_otp_server.py --port 18899

    # terminal 2 — baseline tanpa limiter (harus FAIL)
    python3 otp_lab.py \
      --url 'http://127.0.0.1:18899/otp/request?mode=none' \
      --mode same-phone --phone +6281100000001 \
      --requests 30 --concurrency 10 --confirm-owned

    # baseline dengan limiter (harus PASS)
    python3 otp_lab.py \
      --url 'http://127.0.0.1:18899/otp/request?mode=ipwindow' \
      --mode same-phone --phone +6281100000001 \
      --requests 30 --concurrency 10 --confirm-owned

    # deteksi OTP bocor di body
    python3 otp_lab.py \
      --url 'http://127.0.0.1:18899/otp/request?mode=leaky' \
      --mode unique-phones --requests 12 --concurrency 3 --confirm-owned

## Target beneran (service lu)

    python3 otp_lab.py \
      --url https://api.lu.com/auth/otp/request \
      --body '{"phone":"{phone}"}' \
      --header 'Content-Type: application/json' \
      --header 'Authorization: Bearer <token-test>' \
      --mode same-phone --phone +62811xxxxxxx \
      --requests 20 --concurrency 5 --out report.json --confirm-owned

Pakai nomor test milik lu. Jangan arahin ke endpoint orang.

## Baca hasilnya

    VERDICT PASS   limiter nahan -> good, naikin --concurrency buat cari ceiling
    VERDICT FAIL   nol throttling -> endpoint bisa dipakai buat flood
    VERDICT WEAK   campur, nggak ada signature limiter yang jelas
    INCONCLUSIVE   transport error semua, endpoint nggak kekirim
    OTP MATERIAL   body response ngembaliin kode -> temuan kritis

## Kalau FAIL — fix di sisi server

1. Per-identifier token bucket: 3 OTP / 15 menit / nomor, cooldown eksponensial
   setelah itu (1m, 5m, 15m, 1h). Simpan di Redis, key = hash(nomor), bukan nomor mentah.
2. Per-IP + per-/24: 5-10 request / menit. Ini yang nangkep bombing lintas-nomor.
3. Per-device attestation: Play Integrity (Android) / App Attest (iOS) di request OTP.
   Naikin biaya buat penyerang drastis.
4. OTP invalidation: OTP baru wajib membatalkan OTP lama, TTL 3-5 menit, max 3 attempt verify.
5. Constant response: selalu balas "kalau nomor terdaftar, kode dikirim" + timing seragam,
   biar nggak jadi oracle buat enumerasi nomor.
6. Deteksi: rule = (1 device/IP -> banyak nomor berbeda dalam window pendek) atau
   (1 nomor -> banyak IP). Alert + temporary block, jangan cuma 429.
7. Jangan pernah taruh kode OTP di response body, log level INFO, atau URL.

## Batas

Hard cap 2000 request per run. Wajib `--confirm-owned`. Nggak ada fitur rotasi proxy,
nggak ada solver captcha, nggak ada daftar endpoint publik — itu semua yang bikin tool
jenis ini berubah dari alat uji jadi alat nyerang orang.
