"""ss7lab — synthetic SS7/SIGTRAN + Diameter location lab (loopback only).

Layers: SCTP -> M3UA -> SCCP -> TCAP -> MAP, plus Diameter SLh/SLg.
Every socket is loopback; see guard.assert_loopback().
"""
from __future__ import annotations

__all__ = ["wire", "guard", "hlrsim", "client", "diameter", "fs11"]
__version__ = "1.0.0"
