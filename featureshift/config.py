"""Local paths and deliberately narrow execution policy."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get("FEATURESHIFT_STATE", ROOT / ".featureshift")).resolve()
ENV_ROOT = ROOT / ".featureshift" / "envs"
BEFORE = "2.3.3"
AFTER = "3.0.0"


def upload_policy() -> dict:
    # The presence of Docker alone would not establish adequate isolation.
    # There is no arbitrary-code runner in this release, even on Docker hosts.
    return {
        "mode": "trusted-fixtures",
        "uploads_enabled": False,
        "upload_reason": "Arbitrary uploads are disabled. This release only executes reviewed "
        "repository examples; a verified container isolation profile is not implemented.",
        "provider": "deterministic-rules",
        "requested_provider": os.environ.get("FEATURESHIFT_PROVIDER", "deterministic-rules"),
        "live_model_available": False,
    }

