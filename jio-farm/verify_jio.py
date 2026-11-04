import csv, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from jio_farm import is_jio_number, jio_session, NUMBERS_CSV, NUMBERS_JSON

rows = list(csv.DictReader(NUMBERS_CSV.open(encoding="utf-8")))
print("total", len(rows))

def check(r):
    s = jio_session()
    r["is_jio"] = bool(is_jio_number(s, r["mobile_number"]))
    return r

out = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(check, r): r for r in rows}
    done = 0
    for fut in as_completed(futs):
        out.append(fut.result())
        done += 1
        if done % 25 == 0:
            print(f"checked {done}/{len(rows)}")

# preserve original order
order = {r["mobile_number"]: i for i, r in enumerate(rows)}
out.sort(key=lambda r: order.get(r["mobile_number"], 9999))

with NUMBERS_CSV.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["mobile_number","is_jio","device_id","panel_url","harvested_at"])
    w.writeheader()
    for r in out:
        w.writerow(r)
with NUMBERS_JSON.open("w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

jio = [r for r in out if str(r["is_jio"]).lower()=="true"]
print("Jio verified:", len(jio), "/", len(out))
