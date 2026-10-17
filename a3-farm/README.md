A3 — Gemini Free-Tier Key Farm
==============================

Tujuan: kumpulkan BANYAK Gemini API key dari free tier (yang gak butuh nomor Jio,
gak butuh payment, gak butuh email kampus), lalu satukan throughput-nya jadi satu
pool ber-load-balancer + proxy OpenAI-compatible.

Kenapa banyak KEY, bukan banyak akun Google trial:
  - Free tier Gemini API dihitung PER PROJECT, bukan per key.
  - AI Studio: max 10 project per akun sekaligus, display max 100 keys / 50 project.
  - Sejak 28 Mei 2026 semua key baru = "auth keys"; key standard `unrestricted`
    DITOLAK API. Jadi key WAJIB dibuat lewat AI Studio.

Arsitektur
----------
  core/config.py      konstanta, path, endpoint, model
  core/db.py          SQLite: accounts / projects / api_keys / usage + stats
  core/apikey.py      verifikasi key (list-models) + generate probe + klasifikasi error
  core/balancer.py    KeyPool: round-robin, cooldown 429, failover antar-key & antar-model
  core/server.py      proxy HTTP OpenAI-compatible di atas pool
  core/google_login.py  login akun Google (manual/vault), simpan storage_state per akun
  core/aistudio_ui.py   Playwright: bikin project + auth key via UI AI Studio, harvest
  core/farm.py        orchestrator bulk: banyak akun × banyak key, paralel
  cli.py              entrypoint semua subcommand
  tests/              mock_gemini.py + test_balancer.py + run_tests.sh

Quickstart
----------
  source /root/osint/venv/bin/activate
  cd /root/syns4033-jb/a3-farm

  # 1. masukin key yang udah ada
  python cli.py import-key AIza... AIza...
  python cli.py import-keys keys.txt

  # 2. verifikasi (list-models murah, gak makan token)
  python cli.py verify                 # semua key di pool
  python cli.py verify --gen           # sekalian generate beneran
  python cli.py test-key AIza... --gen

  # 3. pakai pool
  python cli.py ask "jelasin X singkat"
  python cli.py bench 50 --concurrency 8   # ukur throughput efektif
  python cli.py health
  python cli.py stats
  python cli.py export keys_inventory.jsonl

  # 4. proxy OpenAI-compatible (drop-in buat client apa pun)
  python cli.py serve --host 127.0.0.1 --port 8787
  # GET  /v1/models
  # POST /v1/chat/completions  {"model":"auto","messages":[...]}
  # GET  /health

Bikin key via browser (butuh akun Google udah login)
----------------------------------------------------
  python cli.py login-google akun@gmail.com            # buka browser, login manual + 2FA sekali
  python cli.py make-keys --email akun@gmail.com --n 10
  # bulk:
  # data/accounts.jsonl  ->  {"email":"a@gmail.com"} per baris
  python cli.py farm --accounts data/accounts.jsonl --n 1 --workers 2

  Catatan browser flow: markup AI Studio berubah; extractor nyoba banyak strategi
  DOM + sniffer network response dan nangkap tiap token AIza.../auth-key yang muncul.
  Hasil per akun dicatat ke data/claim_results.jsonl.

Tests
-----
  bash tests/run_tests.sh
  # 1) unit db  2) mock endpoint -> rotasi/429/failover  3) proxy end-to-end

Batas teknis (jujur, 1 baris)
-----------------------------
  - Farm INI butuh akun Google valid (yang bisa login) + nomor biasa buat verifikasi
    akun Google Cloud saat pertama; TIDAK butuh nomor Jio, TIDAK butuh kartu.
  - Free tier tetap ada RPM/RPD per project; kapasitas riil = jumlah project × limit model.
  - Bikin ratusan AKUN Google otomatis (registrasi + verifikasi nomor) itu jalur
    terpisah dan bergantung kualitas nomor+proxy — bukan bagian dari modul ini.
