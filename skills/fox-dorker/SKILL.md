---
name: fox-dorker
description: "This skill should be used when the user asks to 'run dorks', 'dorking', 'Google dork', 'search for vulnerable sites', 'find SQLi sites', 'harvest URLs', 'mass dorking', 'ClownSearcher', 'batch dork', 'list dork', 'inurl:', 'intext:', or needs to automate search engine dorking for target recon. Inspired by SexyClown/ClownSearcher and psqli-pro dorking engine."
---

# Fox-Dorker Skill

## Overview
Automated search engine dorking for target harvesting. Supports Google, Bing, Yahoo, and Ask.com engines. Single dork, list dork, interactive mode. Proxy rotation + UA randomization for stealth.

## When to use
- User wants to find vulnerable targets via dorking
- User mentions ClownSearcher or wants Google dork automation
- User asks you to search for specific patterns (inurl:, intext:, filetype:, etc.)
- User has a list of dorks and wants to run them all
- RECON phase of any web attack — find targets before exploiting

## How to use

### Installation
```
pip install requests          # for engines: google, bing, yahoo, ask
pip install google            # optional, for google lib engine
```

### Single dork
```powershell
fox-dorker -d "inurl:php?id="
fox-dorker -d "inurl:php?id=" -e bing -p 5
fox-dorker -d "inurl:admin intitle:login" -e all
```

### List dork (batch)
```powershell
fox-dorker -l dorks.txt
fox-dorker -l dorks.txt -e yahoo -p 3
```

### Proxy rotation
```powershell
fox-dorker -d "inurl:admin" --proxy proxies.txt -e google
```

### Interactive mode
```powershell
fox-dorker -i
```
Then inside:
```
dork> inurl:php?id=
!engine bing
!pages 5
!output results.txt
!proxy proxies.txt
```

### Save output
```powershell
fox-dorker -d "inurl:id=" -e all -o targets.txt
```

## Available engines
| Engine   | Description                    | Requires         |
|----------|--------------------------------|------------------|
| google   | Google via HTTP requests       | requests         |
| goolib   | Google via `google` library    | google (pip)     |
| bing     | Bing search                    | requests         |
| yahoo    | Yahoo search                   | requests         |
| ask      | Ask.com search                 | requests         |
| all      | ALL engines combined           | requests         |

## Dork examples for target hunting

### SQLi targets
```
inurl:php?id=
inurl:product.php?id=
inurl:item.php?id=
inurl:page.php?id=
inurl:news.php?id=
inurl:index.php?id=
```

### Admin panels
```
inurl:admin intitle:login
inurl:admin/login.php
intitle:"admin panel"
intitle:"control panel" "password"
```

### File upload vulns
```
inurl:upload.php
inurl:file-upload
inurl:filemanager
```

### LFI/RFI
```
inurl:index.php?page=
inurl:main.php?file=
inurl:include.php?template=
```

### API endpoints
```
inurl:api/v1
inurl:api/rest
inurl:graphql
inurl:swagger
```

## Proxy file format
One proxy per line:
```
http://user:pass@ip:port
http://ip:port
socks5://ip:port
```

## Default config
- Pages: 3 per dork (10 results each → ~30 URLs per dork per engine)
- Delay: 2s between requests (randomized ±50%)
- UA: rotated from pool of 5 modern browsers

## Tips
- Use `-e all` for max coverage, especially for rare targets
- Use `--proxy` when Google blocks you
- For mass dorking (list mode), output is auto-saved per run if `-o` not specified
- Combine with SQLi phase: dork → collect URLs → test with fox-sqli
- Combine with directory brute-force: dork to find targets, then ffuf/feroxbuster for paths
