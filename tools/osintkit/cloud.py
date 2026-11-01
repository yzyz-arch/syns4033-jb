"""Cloud storage enumeration: S3 / GCS / Azure Blob / DigitalOcean Spaces.

Derives candidate bucket names from the domain and classifies each as
public-list (critical), exists-private (informational), or free. Read-only GETs.
"""
from __future__ import annotations

import concurrent.futures as cf
import re

from .http import session

REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]


def candidates(domain: str, extra: list[str] | None = None) -> list[str]:
    base = domain.lower()
    stem = base.split(".")[0]
    nodots = re.sub(r"[^a-z0-9]", "", base)
    hyph = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    prefixes = ["", "www-", "dev-", "prod-", "staging-", "stage-", "test-", "qa-",
                "backup-", "backups-", "assets-", "static-", "cdn-", "media-",
                "files-", "uploads-", "data-", "logs-", "archive-", "images-",
                "img-", "public-", "private-", "internal-", "s3-", "bucket-"]
    names = {nodots, hyph, stem}
    for p in prefixes:
        names.add(f"{p}{hyph}" if p else hyph)
        names.add(f"{p}{nodots}" if p else nodots)
        if stem != hyph:
            names.add(f"{p}{stem}" if p else stem)
    names.add(f"{hyph}-{REGIONS[0]}")
    if extra:
        names.update(x.lower() for x in extra)
    clean = {n for n in names if 3 <= len(n) <= 63 and re.fullmatch(r"[a-z0-9.\-]+", n)}
    return sorted(clean)


def check_s3(bucket: str) -> dict:
    s = session()
    for host in (f"{bucket}.s3.amazonaws.com", f"https://{bucket}.s3.amazonaws.com"):
        pass
    url = f"https://{bucket}.s3.amazonaws.com/"
    try:
        r = s.get(url, timeout=10)
        body = r.text[:4000]
        if r.status_code == 200 and "ListBucketResult" in body:
            keys = re.findall(r"<Key>([^<]+)</Key>", body)[:10]
            return {"bucket": bucket, "provider": "s3", "status": "public-list",
                    "url": url, "sample_keys": keys,
                    "key_count_returned": len(re.findall(r"<Key>", body))}
        if r.status_code in (301, 400) and ("PermanentRedirect" in body or "AuthorizationHeaderMalformed" in body):
            return {"bucket": bucket, "provider": "s3", "status": "exists-private",
                    "url": url, "detail": "redirect/auth error -> bucket exists in another region"}
        if r.status_code == 403 and "AccessDenied" in body:
            return {"bucket": bucket, "provider": "s3", "status": "exists-private", "url": url}
        if "NoSuchBucket" in body or r.status_code == 404:
            return {"bucket": bucket, "provider": "s3", "status": "free", "url": url}
        return {"bucket": bucket, "provider": "s3", "status": f"http-{r.status_code}", "url": url}
    except Exception as e:
        return {"bucket": bucket, "provider": "s3", "status": "error", "detail": str(e)[:100]}


def check_gcs(bucket: str) -> dict:
    s = session()
    url = f"https://storage.googleapis.com/{bucket}"
    try:
        r = s.get(url, timeout=10)
        body = r.text[:4000]
        # a generic 200 (branding/error page) is NOT a bucket; require the listing root
        if r.status_code == 200 and "ListBucketResult" in body:
            return {"bucket": bucket, "provider": "gcs", "status": "public-list", "url": url,
                    "sample_keys": re.findall(r"<Key>([^<]+)</Key>", body)[:10]}
        if r.status_code in (401, 403):
            return {"bucket": bucket, "provider": "gcs", "status": "exists-private", "url": url}
        if r.status_code == 404 or "NoSuchBucket" in body:
            return {"bucket": bucket, "provider": "gcs", "status": "free", "url": url}
        return {"bucket": bucket, "provider": "gcs", "status": f"http-{r.status_code}", "url": url}
    except Exception as e:
        return {"bucket": bucket, "provider": "gcs", "status": "error", "detail": str(e)[:100]}


def check_azure(account: str) -> dict:
    s = session()
    url = f"https://{account}.blob.core.windows.net/?comp=list"
    try:
        r = s.get(url, timeout=10)
        body = r.text[:2000]
        if r.status_code == 200 and "EnumerationResults" in body:
            return {"bucket": account, "provider": "azure", "status": "public-list", "url": url,
                    "sample_keys": re.findall(r"<Name>([^<]+)</Name>", body)[:10]}
        if r.status_code in (403, 400) and ("AuthenticationFailed" in body or "InvalidQueryParameterValue" in body
                                            or "AuthorizationFailure" in body):
            return {"bucket": account, "provider": "azure", "status": "exists-private", "url": url}
        if r.status_code == 404:
            return {"bucket": account, "provider": "azure", "status": "free", "url": url}
        return {"bucket": account, "provider": "azure", "status": f"http-{r.status_code}", "url": url}
    except Exception as e:
        return {"bucket": account, "provider": "azure", "status": "error", "detail": str(e)[:100]}


def check_spaces(bucket: str, region: str = "nyc3") -> dict:
    s = session()
    url = f"https://{bucket}.{region}.digitaloceanspaces.com/"
    try:
        r = s.get(url, timeout=10)
        body = r.text[:2000]
        if r.status_code == 200 and "ListBucketResult" in body:
            return {"bucket": bucket, "provider": "spaces", "status": "public-list", "url": url,
                    "sample_keys": re.findall(r"<Key>([^<]+)</Key>", body)[:10]}
        if r.status_code == 403:
            return {"bucket": bucket, "provider": "spaces", "status": "exists-private", "url": url}
        if r.status_code == 404:
            return {"bucket": bucket, "provider": "spaces", "status": "free", "url": url}
        return {"bucket": bucket, "provider": "spaces", "status": f"http-{r.status_code}", "url": url}
    except Exception as e:
        return {"bucket": bucket, "provider": "spaces", "status": "error", "detail": str(e)[:100]}


def enumerate_all(domain: str, providers: tuple[str, ...] = ("s3", "gcs", "azure"),
                  limit: int = 40, workers: int = 20) -> dict:
    names = candidates(domain)[:limit]
    jobs = []
    for n in names:
        if "s3" in providers:
            jobs.append(("s3", n))
        if "gcs" in providers:
            jobs.append(("gcs", n))
        if "azure" in providers:
            jobs.append(("azure", n.replace(".", "")))
    fn = {"s3": check_s3, "gcs": check_gcs, "azure": check_azure, "spaces": check_spaces}
    results = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn[p], n): (p, n) for p, n in jobs}
        for f in cf.as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                p, n = futs[f]
                results.append({"bucket": n, "provider": p, "status": "error", "detail": str(e)[:100]})
    order = {"public-list": 0, "exists-private": 1}
    results.sort(key=lambda r: (order.get(r["status"], 5), r["provider"], r["bucket"]))
    return {
        "domain": domain,
        "checked": len(results),
        "public": [r for r in results if r["status"] == "public-list"],
        "private": [r for r in results if r["status"] == "exists-private"],
        "results": results,
        "note": ("bucket names are guesses derived from the domain; a hit proves the "
                 "bucket name exists and is readable, not that the target owns it"),
    }
