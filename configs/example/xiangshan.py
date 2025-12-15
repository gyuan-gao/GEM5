import os
import runpy
import time


def _agent_log(hypothesisId: str, location: str, message: str, data: dict):
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": "pre-fix",
            "hypothesisId": hypothesisId,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open("/root/.cursor/debug.log", "a", encoding="utf-8") as f:
            f.write(str(payload).replace("'", '"') + "\n")
    except Exception:
        # Best-effort logging only; never block gem5 execution.
        pass


# region agent log
_TARGET = os.path.join(os.path.dirname(__file__), "auto_xiangshan.py")
_agent_log(
    "A",
    "configs/example/xiangshan.py:entry",
    "compat shim executing auto_xiangshan.py via runpy",
    {
        "cwd": os.getcwd(),
        "shim": __file__,
        "target": _TARGET,
        "target_exists": os.path.exists(_TARGET),
        "target_is_file": os.path.isfile(_TARGET),
        "target_readable": os.access(_TARGET, os.R_OK),
    },
)
# endregion agent log

# This repository contains `configs/example/auto_xiangshan.py` (not `xiangshan.py`).
# Some scripts still reference `configs/example/xiangshan.py`; keep this shim for compatibility.
runpy.run_path(_TARGET, run_name="__m5_main__")

# region agent log
_agent_log(
    "A",
    "configs/example/xiangshan.py:exit",
    "compat shim finished (runpy returned)",
    {"cwd": os.getcwd(), "target": _TARGET},
)
# endregion agent log



