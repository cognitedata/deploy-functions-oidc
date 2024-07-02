from __future__ import annotations

from typing import Optional


class RTEConfig:
    timezone: Optional[str] = None
    timezone_local: Optional[str] = None

    def __init__(self, function_input: dict):
        self.timezone = function_input.get("timezone")
        self.timezone_local = function_input.get("timezone_local")
