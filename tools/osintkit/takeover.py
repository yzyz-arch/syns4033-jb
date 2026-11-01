"""Subdomain takeover detection: dangling CNAME -> unclaimed provider resource.

Two-stage check per host:
  1. follow the CNAME chain and match the terminal host against provider suffixes
  2. fetch the host and match the provider's "unclaimed" response signature
A hit on both is a strong signal (vulnerable); stage 1 alone is "candidate".
"""
from __future__ import annotations

import concurrent.futures as cf

from . import net
from .http import probe

# provider -> (cname suffixes, body signatures, status hints)
FINGERPRINTS: dict[str, dict] = {
    "GitHub Pages": {"cname": ["github.io", "github.com"], "body": ["there isn't a github pages site here"], "status": [404]},
    "Heroku": {"cname": ["herokuapp.com", "herokussl.com"], "body": ["no such app", "there's nothing here, yet"], "status": [404]},
    "AWS S3": {"cname": ["s3.amazonaws.com", "s3-website", "amazonaws.com"], "body": ["nosuchbucket", "the specified bucket does not exist"], "status": [404]},
    "AWS CloudFront": {"cname": ["cloudfront.net"], "body": ["bad request", "the request could not be satisfied"], "status": [403]},
    "Azure Web App": {"cname": ["azurewebsites.net", "cloudapp.net", "azurestaticapps.net", "trafficmanager.net"], "body": ["404 web site not found", "error 404"], "status": [404]},
    "Azure Blob": {"cname": ["blob.core.windows.net"], "body": ["blobserverror", "the specified resource does not exist"], "status": [404]},
    "Netlify": {"cname": ["netlify.app", "netlify.com"], "body": ["not found - request id", "page not found"], "status": [404]},
    "Vercel": {"cname": ["vercel.app", "now.sh"], "body": ["deployment_not_found", "the deployment could not be found"], "status": [404]},
    "Render": {"cname": ["onrender.com"], "body": ["service not found", "not found"], "status": [404]},
    "Railway": {"cname": ["railway.app", "up.railway.app"], "body": ["application not found"], "status": [404]},
    "Fly.io": {"cname": ["fly.dev"], "body": ["404 not found"], "status": [404]},
    "Firebase": {"cname": ["web.app", "firebaseapp.com"], "body": ["site not found", "page not found"], "status": [404]},
    "Cloudflare Pages": {"cname": ["pages.dev"], "body": ["project not found"], "status": [404]},
    "Shopify": {"cname": ["myshopify.com"], "body": ["sorry, this shop is currently unavailable", "only one step left"], "status": [404]},
    "WordPress.com": {"cname": ["wordpress.com", "wpcomstaging.com"], "body": ["do you want to register", "doesn't exist"], "status": [404]},
    "Tumblr": {"cname": ["tumblr.com"], "body": ["there's nothing here", "whatever you were looking for doesn't currently exist"], "status": [404]},
    "Fastly": {"cname": ["fastly.net", "fastlylb.net"], "body": ["fastly error: unknown domain", "fastly error: unknown domain"], "status": [500]},
    "Pantheon": {"cname": ["pantheonsite.io", "pantheon.io"], "body": ["the gods are wise, but do not know of the site"], "status": [404]},
    "Zendesk": {"cname": ["zendesk.com"], "body": ["help center closed", "this help center no longer exists"], "status": [404]},
    "Desk.com": {"cname": ["desk.com"], "body": ["this site is no longer active"], "status": [404]},
    "Statuspage": {"cname": ["statuspage.io"], "body": ["status page pushed a little too far", "page not found"], "status": [404]},
    "Surge.sh": {"cname": ["surge.sh"], "body": ["project not found"], "status": [404]},
    "Bitbucket": {"cname": ["bitbucket.io"], "body": ["repository not found"], "status": [404]},
    "ReadTheDocs": {"cname": ["readthedocs.io", "readthedocs.org"], "body": ["unknown to read the docs"], "status": [404]},
    "Ghost": {"cname": ["ghost.io"], "body": ["hello there, this is a ghost blog", "page not found"], "status": [404]},
    "Freshdesk": {"cname": ["freshdesk.com"], "body": ["may be incorrect or the account", "there is no helpdesk here"], "status": [404]},
    "UserVoice": {"cname": ["uservoice.com"], "body": ["this uservoice subdomain is currently available"], "status": [404]},
    "Intercom": {"cname": ["intercom.help", "custom.intercom.help"], "body": ["this page is reserved for", "page not found"], "status": [404]},
    "Pingdom": {"cname": ["pingdom.com", "stats.pingdom.com"], "body": ["this public status page does not exist"], "status": [404]},
    "Tilda": {"cname": ["tilda.ws"], "body": ["please renew your subscription"], "status": [404]},
    "Unbounce": {"cname": ["unbouncepages.com"], "body": ["the requested url was not found on this server"], "status": [404]},
    "Cargo": {"cname": ["cargocollective.com"], "body": ["404 not found"], "status": [404]},
    "Launchrock": {"cname": ["launchrock.com"], "body": ["hello, welcome to launchrock"], "status": [404]},
    "Ngrok": {"cname": ["ngrok.io", "ngrok-free.app", "ngrok.app"], "body": ["tunnel", "not found"], "status": [404]},
    "BigCartel": {"cname": ["bigcartel.com"], "body": ["oops! we couldn't find that page"], "status": [404]},
    "CampaignMonitor": {"cname": ["createsend.com", "campaignmonitor.com"], "body": ["double check the url"], "status": [404]},
    "Squarespace": {"cname": ["squarespace.com"], "body": ["no such site", "if you're the owner"], "status": [404]},
    "Wix": {"cname": ["wix.com", "wixsite.com"], "body": ["this site is not available"], "status": [404]},
    "Webflow": {"cname": ["webflow.io"], "body": ["the page you are looking for doesn't exist"], "status": [404]},
    "HubSpot": {"cname": ["hubspot.net", "hubspot.com"], "body": ["this page could not be found", "does not exist"], "status": [404]},
    "Unbounce2": {"cname": ["unbounce.com"], "body": ["page not found"], "status": [404]},
    "SmugMug": {"cname": ["smugmug.com"], "body": ["this page is no longer available"], "status": [404]},
    "Teamwork": {"cname": ["teamwork.com"], "body": ["this page is missing"], "status": [404]},
    "Kanbanize": {"cname": ["kanbanize.com"], "body": ["this is a company account"], "status": [404]},
    "Helpjuice": {"cname": ["helpjuice.com"], "body": ["this help center is no longer available"], "status": [404]},
    "Acquia": {"cname": ["acquia-sites.com", "acquia.com"], "body": ["this site is currently unavailable", "not found"], "status": [404]},
    "Discourse": {"cname": ["discourse.org"], "body": ["page not found", "doesn't exist"], "status": [404]},
    "DigitalOcean Apps": {"cname": ["ondigitalocean.app"], "body": ["not found"], "status": [404]},
    "Kinsta": {"cname": ["kinsta.cloud"], "body": ["no such site", "not found"], "status": [404]},
    "Salesforce Commerce": {"cname": ["commercecloud.salesforce.com"], "body": ["storefront not found"], "status": [404]},
    "Chargify": {"cname": ["chargify.com"], "body": ["sorry, this page is no longer available"], "status": [404]},
    "Tictail": {"cname": ["tictail.com"], "body": ["sorry, that store doesn't exist"], "status": [404]},
}


def _provider_for_name(name: str) -> str | None:
    name = name.lower().rstrip(".")
    for provider, fp in FINGERPRINTS.items():
        for suf in fp["cname"]:
            if name == suf or name.endswith("." + suf):
                return provider
    return None


def _match_cname(chain: list[str]) -> str | None:
    """Match the terminal CNAME hop, or the host itself when it lives on the
    provider's own domain (e.g. a bare *.github.io / *.herokuapp.com host has no
    CNAME record of its own but is still an unclaimed provider resource)."""
    if not chain:
        return None
    provider = _provider_for_name(chain[-1])
    if provider:
        return provider
    return _provider_for_name(chain[0]) if len(chain) == 1 else None


def _match_body(provider: str, body: str, status: int | None) -> bool:
    fp = FINGERPRINTS.get(provider) or {}
    low = (body or "").lower()
    for sig in fp.get("body", []):
        if sig and sig in low:
            return True
    return False


def check_host(host: str) -> dict:
    chain = net.cname_chain(host)
    provider = _match_cname(chain)
    out = {"host": host, "cname_chain": chain, "provider": provider,
           "status": "no-cname", "evidence": []}
    if not provider:
        if len(chain) > 1:
            out["status"] = "cname-unrecognised"
        return out

    for scheme in ("https", "http"):
        status, final, headers, body = probe(f"{scheme}://{host}/", timeout=12)
        if status is None:
            continue
        out["http_status"] = status
        out["final_url"] = final
        if _match_body(provider, body, status):
            out["status"] = "VULNERABLE"
            out["evidence"].append(f"{provider} unclaimed-page signature on {scheme} ({status})")
            break
        if status in (404, 403) and provider in ("AWS S3", "AWS CloudFront", "Azure Web App"):
            out["status"] = "candidate"
            out["evidence"].append(f"{provider} edge error {status} without content")
            break
        out["status"] = "claimed"
        break
    if out["status"] == "no-cname":
        out["status"] = "candidate"
        out["evidence"].append("provider CNAME present but host did not respond")
    return out


def scan(hosts: list[str], workers: int = 25) -> dict:
    results = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(check_host, h): h for h in hosts}
        for f in cf.as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"host": futs[f], "status": "error", "error": str(e)[:120]})
    results.sort(key=lambda r: (r.get("status") != "VULNERABLE", r.get("status") != "candidate", r["host"]))
    return {
        "scanned": len(hosts),
        "vulnerable": [r for r in results if r.get("status") == "VULNERABLE"],
        "candidates": [r for r in results if r.get("status") in ("candidate", "cname-unrecognised")],
        "results": results,
    }
