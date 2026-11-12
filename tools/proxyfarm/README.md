# proxyfarm — residential proxy harvester + rotating client

Harvest publik → verifikasi egress nyata → klasifikasi ASN/ISP (residential vs datacenter) → rank → dipakai.

## Files
| file | fungsi |
|---|---|
| `farm.py` | harvester + validator + classifier + ranker |
| `proxy_rotate.py` | client pool: rotasi, quarantine, self-heal, reload |
| `verify.py` | re-check NOW: pisahkan https_anon / http_anon / leak / dead |
| `scrape.py` | contoh scraper pakai pool (JSONL output, resume, concurrency) |
| `state/` | `candidates.tsv` (cache kandidat), `live.jsonl` (hasil probe), `dead.txt` (resume) |
| `out/` | `residential.json`, `residential.txt` (anon), `transparent.txt`, `stats.json` |

## Jalanin
```bash
python3 farm.py -j 900 -t 7 -n 25000        # batch pertama
python3 farm.py -j 900 -t 7 -n 25000        # lanjut (resume otomatis, dead di-skip)
python3 farm.py --reclassify --min-score 4  # ranking ulang dari live.jsonl tanpa probing
python3 proxy_rotate.py                     # sanity test pool
python3 verify.py -p out/residential.txt -o out/active   # cek ulang kapabilitas
python3 scrape.py https://target.com/path -o data.jsonl --pages 20
```

## Cek ulang kapabilitas (`verify.py`)
`farm.py` menandai "residential" dari metadata ASN — itu TIDAK membuktikan proxy masih hidup,
apalagi bahwa dia menyembunyikan IP kamu di protokol yang kamu butuh. `verify.py` menguji tiap
entri sekarang dan memisahkan:

| verdict | arti |
|---|---|
| `https_anon` | HTTPS CONNECT jalan DAN egress IP != IP kita → aman dipakai di mana-mana |
| `http_anon` | cuma HTTP polos yang jalan, egress != IP kita → buat target `http://` |
| `https_leak` / `http_leak` | jalan tapi egress = IP kita (transparent) → tidak menyamarkan |
| `dead` | tidak ada respons |

Output: `out/active_https.txt` (pool terbaik), `out/active_http.txt` (fallback),
`out/active_stats.json`. Terima format farm (`exit@ip:port`) atau list telanjang `ip:port`
lewat `--input`. Latensi di laporan = waktu ke echo `api.ipify.org`/`icanhazip.com` lewat proxy.

## Cara verifikasi (kenapa hasilnya gak zonk)
1. Proxy harus balikin IP egress != IP server sendiri (transparent proxy dibuang ke `transparent.txt`, bukan dianggap anon).
2. CONNECT/TLS probe terpisah — proxy yang cuma bisa plain HTTP ditandai `tls=0`, bukan dibuang (tetap valid buat target http).
3. ip-api.com/batch → `hosting`, `mobile`, ASN, ISP. Skor: non-hosting +3, mobile +2, hint residential/ISP +3, hint datacenter −2, TLS +2, transparent −2, latency bonus.
4. Default `--min-score 3` = hosting/DC nyaris mustahil lolos.

## Sumber
15 feed publik (geonode API dengan metadata latency/lastChecked diprioritaskan, openproxylist, proxyscrape, monosans, TheSpeedX, roosterkid, iplocate, proxifly, hookzof). `candidates.tsv` di-cache — hapus kalau mau harvest ulang bersih (`--no-resume`).

## Batas realistis
Proxy publik gratis itu volatile: live-rate ~0.5–1.5%, umur jam-an. Yang disimpan = egress unik (1 entry per exit IP), jadi pool tidak dipenuhi duplikat. Untuk stok gede/awet: jalankan farm tiap 30–60 menit via cron, pakai `proxy_rotate` (quarantine otomatis saat 403/429/timeout).

## Cron (tiap 30 menit)
```
*/30 * * * * cd /root/syns4033-jb/tools/proxyfarm && python3 farm.py -j 900 -n 20000 >> cron.log 2>&1
```
