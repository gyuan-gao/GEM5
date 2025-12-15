import argparse
import sys

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
        import json, time
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


try:
    from common import XSConfig  # noqa: F401
    _agent_log(
        "A",
        "configs/example/cliff.py:import-xsconfig-ok",
        "imported XSConfig successfully",
        {},
    )
except Exception as e:
    _agent_log(
        "A",
        "configs/example/cliff.py:import-xsconfig-failed",
        "failed to import XSConfig from common (ignored; module missing)",
        {"exc_type": type(e).__name__, "exc": str(e)},
    )
    XSConfig = None  # noqa: N816
# endregion agent log
from common.Caches import *
from common import Options
from common.xiangshan import *

if __name__ == '__m5_main__':

    # Add args
    parser = argparse.ArgumentParser()
    Options.addCommonOptions(parser, configure_xiangshan=True)
    Options.addXiangshanFSOptions(parser)

    # Add the ruby specific and protocol specific args
    if '--ruby' in sys.argv:
        Ruby.define_options(parser)

    args = parser.parse_args()

    args.xiangshan_system = True
    args.enable_difftest = False
    args.enable_riscv_vector = True
    args.raw_cpt = True
    args.no_pf = True

    # l1cache prefetcher use stream, stride
    # l2cache prefetcher use pht, bop, cmc
    # disable l1prefetcher store pf train
    # disable l1 berti, l2 cdp
    args.l2_wrapper_hwp_type = "L2CompositeWithWorkerPrefetcher"
    args.pht_pf_level = 2
    args.kmh_align = True

    assert not args.external_memory_system

    test_mem_mode = 'timing'

    # override cpu class and clock
    if args.xiangshan_ecore:
        FutureClass = None
        args.cpu_clock = '2.4GHz'
    else:
        FutureClass = None

    # Match the memories with the CPUs, based on the options for the test system
    TestMemClass = Simulation.setMemClass(args)

    test_sys = build_xiangshan_system(args)

    root = Root(full_system=True, system=test_sys)

    Simulation.run_vanilla(args, root, test_sys, FutureClass)