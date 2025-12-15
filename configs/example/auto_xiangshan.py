import argparse
import sys
import os
import json
import time

import m5
from m5.defines import buildEnv
from m5.objects import *
from m5.util import addToPath, fatal, warn
from m5.util.fdthelper import *

addToPath('../')

from ruby import Ruby

from common.FSConfig import *
from common.SysPaths import *
from common.Benchmarks import *
from common import Simulation
from common import CacheConfig
from common import CpuConfig
from common import MemConfig
from common import ObjectList
# region agent log
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
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


_common_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "common"))
try:
    _common_files = sorted(os.listdir(_common_dir))
except Exception as e:
    _common_files = [f"<os.listdir failed: {type(e).__name__}: {e}>"]

_agent_log(
    "A",
    "configs/example/auto_xiangshan.py:pre-import-xsconfig",
    "about to import XSConfig from common",
    {
        "argv0": sys.argv[0] if sys.argv else None,
        "common_dir": _common_dir,
        "has_XSConfig_py": os.path.exists(os.path.join(_common_dir, "XSConfig.py")),
        "common_files_head": _common_files[:50],
        "sys_path_head": sys.path[:20],
    },
)
# endregion agent log

try:
    from common import XSConfig  # noqa: F401
    # region agent log
    _agent_log(
        "A",
        "configs/example/auto_xiangshan.py:import-xsconfig-ok",
        "imported XSConfig successfully",
        {"XSConfig_type": str(type(XSConfig)), "XSConfig_repr": repr(XSConfig)[:200]},
    )
    # endregion agent log
except Exception as e:
    # region agent log
    _agent_log(
        "A",
        "configs/example/auto_xiangshan.py:import-xsconfig-failed",
        "failed to import XSConfig from common (ignored; module missing)",
        {"exc_type": type(e).__name__, "exc": str(e)},
    )
    # endregion agent log
    XSConfig = None  # noqa: N816
from common.Caches import *
from common import Options
from common.xiangshan import *

def autoCalibrateParams(args, system):
    for cpu in system.cpu:
        cpu.fetchWidth=8
        cpu.fetchQueueSize=64
        cpu.decodeWidth=6
        cpu.renameWidth=6
        cpu.commitWidth=8
        cpu.LQEntries=72
        cpu.SQEntries=56
        cpu.SbufferEntries=16
        cpu.SbufferEvictThreshold=7
        cpu.RARQEntries=72
        cpu.RAWQEntries=32
        cpu.numROBEntries=160
        cpu.numPhysIntRegs=224
        cpu.numPhysFloatRegs=192
        cpu.numPhysVecRegs=128







if __name__ == '__m5_main__':
    args = xiangshan_system_init()

    args.enable_difftest = False
    args.raw_cpt = True
    args.no_pf = True

    # l1cache prefetcher use stream, stride
    # l2cache prefetcher use pht, bop, cmc
    # disable l1prefetcher store pf train
    # disable l1 berti, l2 cdp
    args.l2_hwp_type = "L2CompositeWithWorkerPrefetcher"
    #args.pht_pf_level = 2
    #args.kmh_align = True

    assert not args.external_memory_system

    test_mem_mode = 'timing'

    # override cpu class and clock
    if args.xiangshan_ecore:
        FutureClass = None
        args.cpu_clock = '2.4GHz'
    else:
        FutureClass = None

    test_sys = build_xiangshan_system(args)
    autoCalibrateParams(args, test_sys)

    root = Root(full_system=True, system=test_sys)

    Simulation.run_vanilla(args, root, test_sys, FutureClass)