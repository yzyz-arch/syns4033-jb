# apipwn

Harness API pentest, stdlib-only (Python 3.9+), turunan langsung dari playbook
Hacktricks **Web API Pentesting**. Tiap modul = satu bagian metodologi, jadi
hasilnya bisa langsung dipetakan ke laporan.

```
tools/apipwn/
  apipwn.py     # harness (recon / probe / trpc / cxf / all)
  selftest.py   # mock API rentan + assertion deteksi (8/8)
```

## Kenapa

Metodologi API biasanya dijalankan manual dan outputnya berserakan. `apipwn`
menyatukan enam pemeriksaan yang paling sering berbuah di engagement nyata jadi
satu run + satu file JSON, dengan baseline anonim vs terautentikasi supaya delta
(authz gap) kelihatan eksplisit.

## Modul

| Modul | Yang dikerjakan | Sinyal Hacktricks |
|---|---|---|
| `recon` | discovery `openapi.json`/`swagger.json`/`v2/api-docs`/`v3/api-docs`, `?wsdl`, GraphQL introspection; fallback wordlist endpoint | "Understanding API Types", OpenAPI/Swagger/WSDL |
| `probe` | method tampering (GET 401 vs PUT/PATCH/DELETE 2xx), CORS origin reflection + credentials, content-type switch ke XML (XXE candidate), version downgrade (`/v1` -> `/v2`, `beta`, `internal`, unversioned), HPP, TRACE/XST | "Effective Tricks for API Pentesting" |
| `trpc` | enumerasi `<router>.<procedure>` (`POST /api/trpc/x.y`, body `{"input":{}}`), flag procedure privileged yang jawab tanpa sesi | tRPC/Zod `protectedProcedure` pitfall (CVE-2025-59305 case) |
| `cxf` | MTOM/XOP `xop:Include` di body `multipart/related` + `application/xop+xml`, uji `file:///etc/passwd` dan `http://` collaborator | Apache CXF CVE-2022-46364 |

`all` menjalankan recon -> probe -> trpc -> (cxf kalau `--soap-op` diisi).

## Pakai

```bash
# full pass, laporan JSON
./apipwn.py all --target https://TARGET --out findings.json

# pakai spec hasil tarikan manual (biar tidak enumerasi ulang)
./apipwn.py probe --target https://TARGET --spec openapi.json

# tRPC BOLA, router spesifik
./apipwn.py trpc --target https://TARGET \
  --routers backgroundMigrations,admin,billing

# CXF MTOM: op/param diambil dari WSDL target
./apipwn.py cxf --target https://TARGET/soap --op getFile --param arg0 \
  --collab https://xxxx.oast.pro
```

Auth dan OPSEC:

```bash
--header 'Authorization: Bearer <TOKEN>'      # repeatable
--header 'X-API-Key: <KEY>'
--cookie 'session=<SID>'
--proxy http://user:pass@host:8080            # atau env APIPWN_PROXY
--rate 0.3                                    # jeda antar request (detik)
```

`--rate` wajib dipakai di target produksi; default 0 = secepat mungkin, hanya
untuk lab/mock.

## Output

JSON: `{meta, counts, findings[{module, kind, severity, title, url, method,
status, evidence, detail}]}`, sudah diurut severity. Kind yang dipakai:

```
spec_exposed  wsdl_exposed  graphql_introspection  endpoint_enum
method_authz_gap  cors_reflection  cors_wildcard  version_downgrade
xml_parser_reachable  xxe_confirmed  param_pollution_diff  trace_enabled
trpc_anonymous  trpc_anonymous_privileged
cxf_lfi  cxf_xop_probe
```

Severity: `cxf_lfi` / `xxe_confirmed` = critical, authz/version/CORS-credentialed
= high, parser reachable & tRPC non-privileged = medium, discovery = low/info.

## Verifikasi

```bash
python3 selftest.py       # mock rentan -> harus PASS 8/8
```

Mock mereproduksi: spec terbuka, GET 401 vs PUT 200, CORS reflect+credentials,
`/api/v2` tanpa auth, tRPC `admin.wipe` anonim, MTOM `xop:Include` yang
expand `/etc/passwd`, GraphQL introspection, TRACE aktif.

## Batasan yang disengaja

- Tidak ada dependency eksternal, tidak ada telemetry, tidak menyentuh file
  selain `--out`.
- `probe` hanya menandai, tidak mengeksploitasi. Eskalasi (mis. dump lewat XXE
  atau replay tRPC privileged dengan side effect) dikerjakan manual supaya tidak
  ada aksi destruktif otomatis.
- `cxf` mengirim dua request per endpoint (baseline + XOP). Untuk blind SSRF
  pakai `--collab`; harness tidak menunggu callback.

## Next hop setelah `cxf_lfi`

`/etc/systemd/system/*.service` dan `/lib/systemd/system/*.service`
(`ExecStart=`, `EnvironmentFile=`), `/proc/<pid>/cmdline`,
`/proc/<pid>/environ` — env biasanya berisi kredensial DB/API yang langsung
memperluas scope ke service lain.