# Jio-Farm — Latest Jio Numbers from firexpanel.com

Harvests Jio mobile numbers from exposed Firebase panels (viewable via
https://firexpanel.com/) and farms Google AI (Gemini) activation links.

## Files
- `jio_farm.py` — CLI: harvest / activate / panel / firexpanel
- `panels.txt` — Firebase panel list (url|api_key)
- `output/jio_numbers.csv` / `.json` — harvested numbers
- `output/panel.html` — web dashboard
- `output/activation_results.csv`, `activation_links.txt` — activation results

## Quickstart
```
cd /root/syns4033-jb/jio-farm
python3 jio_farm.py harvest            # collect numbers
python3 jio_farm.py activate --limit 20 --otp-timeout 15
python3 jio_farm.py panel              # regenerate dashboard
python3 jio_farm.py firexpanel <firebase_url>
```

## Notes
- Jio number-verification API is CAPTCHA-gated; numbers are labeled "candidate".
- OTP delivery depends on device capturing SMS into Firebase messages.
- Panels are third-party exposed Firebase DBs; availability changes frequently.
