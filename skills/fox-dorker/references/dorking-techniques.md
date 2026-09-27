# Fox-Dorker: Dorking Techniques Reference

## Overview
Dorking is the art of using search engine advanced operators to find vulnerable web applications, exposed files, misconfigured servers, and juicy targets. Combines techniques from ClownSearcher (SexyClown), psqli-pro dorking engine, and OG Google hacking.

## Engine Comparison

| Feature          | Google | Bing | Yahoo | Ask.com |
|-----------------|--------|------|-------|---------|
| Result quality  | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐    |
| Rate limiting   | High   | Medium | Low  | Low     |
| Proxy needed?   | Often | Sometimes | Rarely | Rarely |
| Operators       | Full  | Most | Most  | Basic   |
| Stealth level   | Low   | Medium | High | High    |

**Strategy**: Use Google first → if blocked, fallback to Bing → Yahoo → Ask.com.

## Operators (Google-style)

### Target enumeration
```
inurl:php?id=5
inurl:product.php?id=
inurl:item.php?num=
inurl:page?ID=
inurl:index.php?id=
inurl:news.php?id=
inurl:readnews.php?id=
inurl:article.php?id=
inurl:detail.php?id=
inurl:view.php?id=
inurl:main.php?id=
inurl:show.php?id=
inurl:cat.php?id=
inurl:rub.php?id=
inurl:chapter.php?id=
inurl:books.php?id=
inurl:jump.php?id=
```

### Admin panels
```
inurl:admin
inurl:admin.php
inurl:admin/login.php
inurl:admin/index.php
inurl:admin/home.php
inurl:admin/control.php
inurl:admin/panel.php
inurl:administrator
inurl:adm/index.php
intitle:"admin login"
intitle:"admin panel"
intitle:"control panel"
intitle:"administration"
inurl:login.php
inurl:user/login
```

### File upload
```
inurl:upload.php
inurl:file-upload
inurl:filemanager
inurl:file_upload
inurl:uploader
inurl:uploadify
inurl:plupload
inurl:dropzone
inurl:plupload
```

### LFI / RFI
```
inurl:index.php?page=
inurl:main.php?file=
inurl:include.php?template=
inurl:page=php://input
inurl:file=
inurl:page=
inurl:document=
inurl:folder=
inurl:root=
inurl:load=
inurl:read=
inurl:dir=
inurl:show=
inurl:include=
inurl:path=
inurl:inc=
```

### SQL Error disclosure
```
intext:"mysql_num_rows()"
intext:"mysql_fetch_array()"
intext:"You have an error in your SQL syntax"
intext:"supplied argument is not a valid MySQL"
intext:"Warning: mysql_connect()"
intext:"Warning: pg_connect()"
intext:"ODBC drivers" "SQL Server"
```

### Config files / exposed data
```
filetype:env "DB_PASSWORD"
filetype:sql "INSERT INTO" "password"
filetype:xml "wp-config"
filetype:ini "mysql"
filetype:log "password"
filetype:cfg "datasource"
filetype:config "connectionString"
filetype:inc "mysql_connect"
filetype:conf "root" "password"
filetype:dat "password"
```

### API endpoints
```
inurl:api inurl:swagger
inurl:api inurl:docs
inurl:graphql
inurl:/api/v1
inurl:rest/api
inurl:wp-json
inurl:api.php
inurl:api/index.php
```

### Directory listing
```
intitle:"index of" "backup"
intitle:"index of" "admin"
intitle:"index of" "config"
intitle:"index of" "database"
intitle:"index of" "sql"
intitle:"index of" "dump"
intitle:"index of" "private"
intitle:"index of" "secret"
intitle:"index of" ".git"
intitle:"index of" ".env"
```

## Advanced Google-fu

### Combining operators
```
inurl:php?id= intitle:"error" | SQLi blind targets with error pages
inurl:admin inurl:login intitle:admin | Admin login panels
filetype:php inurl:id= intext:warning | PHP + ID param + warning text
```

### Site-specific
```
site:target.com inurl:php?id=
site:target.com intitle:"index of"
site:target.com filetype:pdf
-site:www.target.com site:target.com
```

### Filetype dorks
```
filetype:pdf "confidential"
filetype:xls "email" "password"
filetype:doc "username" "password"
filetype:sql "INSERT INTO"
filetype:csv "email" "password"
filetype:json "api_key"
filetype:env "DB_PASSWORD"
```

### Time-based (find recent targets)
```
inurl:php?id= & "2025"
inurl:php?id= & "2026"
inurl:product.php?id= & "new"
```

## Dork List Format (for batch mode)
One dork per line:
```
inurl:php?id=
inurl:product.php?id=
inurl:page.php?category=
inurl:item.php?id=
# This is a comment and will be ignored
inurl:admin intitle:login
```

## Workflow Integration

### Phase 1: Dork → Collect targets
```
fox-dorker -l sqli_dorks.txt -e all -o sqli_targets.txt
```

### Phase 2: Verify targets live
```
httpx -l sqli_targets.txt -o live_targets.txt
```

### Phase 3: Test for SQLi
```
fox-sqli "http://target.com/page.php?id=1"
```

### Full pipeline (one-liner)
```powershell
fox-dorker -d "inurl:php?id=" -e all -o urls.txt
httpx -l urls.txt -o live.txt
fox-sqli -l live.txt
```

## Anti-Detection

### Google detection signs
- CAPTCHA page returned
- "Our systems have detected unusual traffic"
- HTTP 503
- Empty results

### Bypass techniques
1. **Proxy rotation** — `--proxy proxies.txt`
2. **Timing** — default 2s delay, randomized
3. **UA rotation** — 5 modern browsers, auto-rotated
4. **Engine fallback** — Google blocked? → Bing → Yahoo → Ask
5. **Intermittent dorking** — avoid hammering any single engine

### Good proxy sources
- Free proxy lists (hideMyName, SSLProxies)
- Residential proxy services (BrightData, Oxylabs, Smartproxy)
- SOCKS5 proxies for better anonymity

## Tools Comparison

| Tool | Engine Support | Mode | Proxy | Author |
|------|---------------|------|-------|--------|
| ClownSearcher | Google only | Single/List | No | SexyClown |
| psqli-pro dork | Google/Bing/Yahoo/Ask | Dork function | No | Kedjaw3n |
| **Fox-Dorker** | Google/Bing/Yahoo/Ask + all | Single/List/Interactive | Yes | Fox |

## References
- SexyClown/ClownSearcher — https://github.com/SexyClown/ClownSearcher
- Google Hacking Database (GHDB) — https://www.exploit-db.com/google-hacking-database
- psqli-pro dorking engine — https://github.com/Agressiv1njector/psqli-pro
