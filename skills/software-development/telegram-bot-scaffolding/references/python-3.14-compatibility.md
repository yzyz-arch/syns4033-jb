# Python 3.14 Compatibility Issues

## urllib3 / requests Retry API Change

**Problem**: `TypeError: Retry.__init__() got an unexpected keyword argument 'method_whitelist'`

**Root cause**: urllib3 2.x deprecated `method_whitelist` in favor of `allowed_methods`. Python 3.14 ships with urllib3 2.x by default.

**Fix**:

```python
# OLD - breaks on Python 3.14+
from urllib3.util.retry import Retry
retry_strategy = Retry(
    total=3,
    method_whitelist=["GET", "POST", "HEAD"]  # ❌ Deprecated
)

# NEW - Python 3.14 compatible
retry_strategy = Retry(
    total=3,
    allowed_methods=["GET", "POST", "HEAD"]  # ✅ Works
)
```

**Backward compatibility** (if supporting Python 3.11-3.14):

```python
import sys
from urllib3.util.retry import Retry

# Detect parameter name based on urllib3 version
if sys.version_info >= (3, 14):
    retry_kwargs = {"allowed_methods": ["GET", "POST"]}
else:
    retry_kwargs = {"method_whitelist": ["GET", "POST"]}

retry_strategy = Retry(total=3, **retry_kwargs)
```

**Related APIs affected**:
- `requests.adapters.HTTPAdapter` with retry strategy
- `urllib3.util.retry.Retry` constructor
- Any custom retry logic using urllib3

**Migration checklist**:
- Search codebase for `method_whitelist`
- Replace with `allowed_methods`
- Test with Python 3.14 virtual environment
- Update requirements.txt if pinning urllib3 version
