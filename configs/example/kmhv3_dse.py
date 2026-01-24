from dataclasses import dataclass
import enum
import math
import re
import os
import subprocess
import sys

import m5
from m5.objects import *
from m5.util import addToPath

addToPath('../')

from typing import Any, Dict, List

from ruby import Ruby
from common.FSConfig import *
from common.SysPaths import *
from common.Benchmarks import *
from common import Simulation
from common.Caches import *
from common.xiangshan import *
from common.FUScheduler import KMHV3DSEScheduler

# NOTE:
# - Do NOT import OR-Tools (and its protobuf deps) in the gem5 process.
#   gem5 already links against libprotobuf, and mixing another protobuf user
#   (e.g., OR-Tools Python wheel) can segfault in google::protobuf::internal::AddDescriptors.
# - We instead run the solver in a separate Python process and only pass JSON back.


def _default_solver_python() -> str:
    """
    Pick a Python interpreter for running the external IQ binding solver.

    In gem5 embedded Python, sys.executable is the gem5 binary, so we try:
    - $IQ_SOLVER_PYTHON if provided
    - <sys.prefix>/bin/python3 or <sys.prefix>/bin/python
    - fallback to 'python3'
    """
    env_py = os.environ.get("IQ_SOLVER_PYTHON")
    if env_py:
        return env_py

    # In conda-based builds, sys.prefix is typically the env root (e.g. /opt/miniconda3/envs/py38)
    cand = [
        os.path.join(sys.prefix, "bin", "python3"),
        os.path.join(sys.prefix, "bin", "python"),
    ]
    for p in cand:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p

    return "python3"


def solve_iq_binding_spec_external(
    *,
    use_solver_deq_sx: bool,
    use_solver_deq_vx: bool,
    use_solver_deq_mx: bool,
    fixed_sx_deq: int = None,
    fixed_vx_deq: int = None,
    fixed_mx_deq: int = None,
    random_seed: int = None,
    time_limit_s: float = 5.0,
) -> str:
    """
    Run configs/example/iq_binding_solver.py in a separate process and return spec_json (string).
    """
    solver_py = _default_solver_python()
    solver_script = os.path.join(os.path.dirname(__file__), "iq_binding_solver.py")
    if not os.path.exists(solver_script):
        raise FileNotFoundError(f"iq_binding_solver.py not found at {solver_script}")

    cmd = [
        solver_py,
        solver_script,
        "--use-solver-deq-sx",
        "1" if use_solver_deq_sx else "0",
        "--use-solver-deq-vx",
        "1" if use_solver_deq_vx else "0",
        "--use-solver-deq-mx",
        "1" if use_solver_deq_mx else "0",
        "--time-limit-s",
        str(float(time_limit_s)),
    ]
    if random_seed is not None:
        cmd += ["--random-seed", str(int(random_seed))]
    if not use_solver_deq_sx:
        cmd += ["--fixed-sx-deq", str(int(fixed_sx_deq))]
    if not use_solver_deq_vx:
        cmd += ["--fixed-vx-deq", str(int(fixed_vx_deq))]
    if not use_solver_deq_mx:
        cmd += ["--fixed-mx-deq", str(int(fixed_mx_deq))]

    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "External IQ binding solver failed.\n"
            f"cmd: {' '.join(cmd)}\n"
            f"exit: {e.returncode}\n"
            f"output:\n{e.output}"
        ) from e

    spec_json = out.strip()
    if not spec_json:
        raise RuntimeError("External IQ binding solver returned empty output.")
    return spec_json


def _is_power_of_two(x: int) -> bool:
    x = int(x)
    return x > 0 and (x & (x - 1)) == 0


def _next_power_of_two(x: int) -> int:
    x = int(x)
    if x <= 1:
        return 1
    return 1 << (x - 1).bit_length()


class ParamType(enum.Enum):
    CPU = "CPU"
    BPred = "BPred"
    ICache = "ICache"
    DCache = "DCache"


@dataclass(frozen=True)
class ParameterRange:
    name: str
    values: List[Any]
    default: Any
    ptype: ParamType = ParamType.BPred
    desc: str = ""


@dataclass(frozen=True)
class KmhV3DesignSpace:
    params: List[ParameterRange]

    def default_config(self) -> Dict[str, Any]:
        return {p.name: p.default for p in self.params}

def build_design_space() -> KmhV3DesignSpace:
    return KmhV3DesignSpace(
        params=[
            ParameterRange(
                name="fetchQueueSize",
                values=[16, 32, 48, 64, 80, 96],
                default=64,
                ptype=ParamType.CPU,
            ),
            ParameterRange(
                name="TLBSize",
                values=[32,64,128,256],
                default=64,
                ptype=ParamType.CPU,
            ),
            ParameterRange(
                name="ICacheAssociativity",
                # Must be power-of-two; non-power-of-two triggers warnings in cache/prefetch structures.
                values=[4, 8],
                default=4,
                ptype=ParamType.ICache,
            ),
            ParameterRange(
                name="ICacheSize",
                values=['16kB','32kB','64kB'],
                default='16kB',
                ptype=ParamType.ICache,
            ),
            ParameterRange(
                name="uBTBSize",
                values=[512, 1024, 2048],
                default=1024,
                ptype=ParamType.BPred,
            ),
            ParameterRange(
                name="L1BTBSize",
                values=[2048, 4096, 8192],
                default=4096,
                ptype=ParamType.BPred,
            ),
            ParameterRange(
                name="L2BTBSize",
                values=[4096, 8192, 16384, 32768],
                default=8192,
                ptype=ParamType.BPred,
            ),
            # ParameterRange(
            #     name="GHB",
            #     values=[512, 1024, 2048],
            #     default=1024,
            #     ptype=ParamType.BPred,
            # ),
            # ParameterRange(
            #     name="BIM",
            #     values=[512, 1024, 2048, 4096, 8192],
            #     default=8192,
            #     ptype=ParamType.BPred,
            # ),
            # ParameterRange(
            #     name="LHB",
            #     values=[512, 1024, 2048],
            #     default=1024,
            #     ptype=ParamType.BPred,
            # ),
            ParameterRange(
                name="RASSize",
                values=[16,32,64],
                default=32,
            ),
            ParameterRange(
                name="FetchWidth",
                values=[8,16],
                default=16,
            ),
            # OEX Part:
            ParameterRange(
                name="SXQSize",
                values=[12,18,24,30,36],
                default=18,
            ),
            ParameterRange(
                name="VXQSize",
                values=[12,18,24,30,36],
                default=18,
            ),
            ParameterRange(
                name="MXQSize",
                values=[12,18,24,30,36],
                default=18,
            ),
            ParameterRange(
                name="LSQSize",
                values=[12,18,24,30,36],
                default=18,
            ),
            ParameterRange(
                name="SXQEnqSize",
                values=[1,2,3],
                default=3,
            ),
            ParameterRange(
                name="VXQEnqSize",
                values=[1,2,3],
                default=3,
            ),
            ParameterRange(
                name="MXQEnqSize",
                values=[1,2,3],
                default=3,
            ),
            ParameterRange(
                name="LSQEnqSize",
                values=[1,2,3],
                default=3,
            ),
                # PREGs,value range need tuning
            ParameterRange(
                name="IntPregsNumber",
                values=[x for x in range(160, 641, 40)],
                default=224,
            ),
            ParameterRange(
                name="FloatPregsNumber",
                values=[x for x in range(96, 321, 40)],
                default=256,
            ),
            ParameterRange(
                name="VectorPregsNumber",
                values=[x for x in range(32, 97, 8)],
                default=64,
            ),
            ParameterRange(
                name="PredicateVectorPregsNumber",
                values=[x for x in range(96, 384, 16)],
                default=128,
            ),
                # Something
            ParameterRange(
                name="DecodeWidth",
                values=[4,6,8,10,12],
                default=6,
            ),
            ParameterRange(
                name="RenameWidth",
                values=[4,6,8,10,12],
                default=6,
            ),
            # ParameterRange(
            #     name="phyregReleaseWidth",
            #     values=[4,6,8,10,12,16],
            #     default=8,
            # ), # overall limitation, p_all >= p_int + p_fp + f_vec as a loose constrain
            ParameterRange(
                name="phyregReleaseWidthInt",
                values=[1,2,4,6,8],
                default=1,
            ),
            ParameterRange(
                name="phyregReleaseWidthFp",
                values=[1,2,4,6,8],
                default=1,
            ),
            ParameterRange(
                name="phyregReleaseWidthVec",
                values=[1,2,4],
                default=1,
            ),
            # LSU
            ParameterRange(
                name="LoadRequestQueueSize",
                values=[16,32,64],
                default=32,
            ),
            ParameterRange(
                name="TempStoreQueueSize",
                values=[16,32,64],
                default=32,
            ),
            ParameterRange(
                name="StoreMergeBuffer",
                values=[8,16,32],
                default=16,
            ),
            ParameterRange(
                name="MSHRSize",
                values=[8,16,32],
                default=16,
            ),
            ParameterRange(
                name="L1DcacheSize",
                values=['16kB','32kB','64kB'],
                default='64kB',
            ),
            ParameterRange(
                name="DCacheAssociativity",
                # Must be power-of-two; TreePLRU num_leaves = assoc.
                values=[4, 8],
                default=4,
            ),
            # ParameterRange(
            #     name="CommitedStoreBufferSize(RSC)",
            #     value=[8,16,32],
            #     default=16,
            # ),
                # way prediction unit
            ParameterRange(
                name="WPUPolicy",
                values=['IndexMRU','MRU','MMRU','UTag','Null'],
                default='IndexMRU',
            ),
            ParameterRange(
                name="cacheLoadPorts",
                values=[1,2,3,4,5,6,7,8],
                default=1,
            ),
            ParameterRange(
                name="cacheStorePorts",
                values=[1,2,3,4,5,6,7,8],
                default=1,
            ),
            ParameterRange(
                name="RARQSize",
                values=[24,32,40,48,56,64,72,80,88,96,104,112,120,128],
                default=24,
            ),
            ParameterRange(
                name="RAWQSize",
                values=[24,32,40,48,56,64,72,80,88,96],
                default=24,
            ),
            ParameterRange(
                name="LFSTSize",
                values=[8,16,32],
                default=8,
            ),
            ParameterRange(
                name="LFSTEntrySize",
                values=[1,2,3,4],
                default=1,
            ),
            ParameterRange(
                name="SSITSize",
                values=[8,16,32],
                default=8,
            ),
            ParameterRange(
                name="l1d_replacement_policy",
                values=['TreePLRURP','DRRIPRP','LRURP'],
                default='TreePLRURP',
            ),
            ParameterRange(
                name="ROBSize",
                values=[x for x in range(160, 641, 40)],
                default=160,
            ),
        ]
    )


def bind_gem5(system: Any, config: Dict[str, Any], *, strict: bool = False) -> None:

    # Parent-space parameters (you can replace with argparse/yaml)
    params: Dict[str, Any] = {}

    # SXQ parameters
    if "SXQSize" in config:
        params["SXQSize"] = config["SXQSize"]
    else:
        params["SXQSize"] = 18
    if "SXQEnqSize" in config:
        params["SXQEnqSize"] = config["SXQEnqSize"]
    else:
        params["SXQEnqSize"] = 3
    if "SXQDeqSize" in config:
        params["SXQDeqSize"] = config["SXQDeqSize"]
    else:
        params["SXQDeqSize"] = 3

    # VXQ parameters
    if "VXQSize" in config:
        params["VXQSize"] = config["VXQSize"]
    else:
        params["VXQSize"] = 18
    if "VXQEnqSize" in config:
        params["VXQEnqSize"] = config["VXQEnqSize"]
    else:
        params["VXQEnqSize"] = 3
    if "VXQDeqSize" in config:
        params["VXQDeqSize"] = config["VXQDeqSize"]
    else:
        params["VXQDeqSize"] = 1

    # MXQ parameters
    if "MXQSize" in config:
        params["MXQSize"] = config["MXQSize"]
    else:
        params["MXQSize"] = 18
    if "MXQEnqSize" in config:
        params["MXQEnqSize"] = config["MXQEnqSize"]
    else:
        params["MXQEnqSize"] = 3
    if "MXQDeqSize" in config:
        params["MXQDeqSize"] = config["MXQDeqSize"]
    else:
        params["MXQDeqSize"] = 3

    params["UseSolverDeq"] = True          # True: deq sizes come from spec; False: fixed by SXQDeqSize etc.
    params["EnforceDeqMatch"] = False      # if UseSolverDeq=True, set True to require spec matches parent sizes

    # Solve subspace and embed spec into params
    # IMPORTANT: run OR-Tools solver in a separate process to avoid protobuf conflicts in gem5.
    if params["UseSolverDeq"]:
        spec_json = solve_iq_binding_spec_external(
            use_solver_deq_sx=True,
            use_solver_deq_vx=True,
            use_solver_deq_mx=True,
            random_seed=123,
            time_limit_s=5.0,
        )
    else:
        spec_json = solve_iq_binding_spec_external(
            use_solver_deq_sx=False,
            fixed_sx_deq=params["SXQDeqSize"],
            use_solver_deq_vx=False,
            fixed_vx_deq=params["VXQDeqSize"],
            use_solver_deq_mx=False,
            fixed_mx_deq=params["MXQDeqSize"],
            random_seed=123,
            time_limit_s=5.0,
        )

    # Pass JSON; scheduler supports JSON string.
    params["IQBindingSpec"] = spec_json


    for cpu in getattr(system, "cpu", []):
        # The IFU Part
        if "fetchQueueSize" in config:
            cpu.fetchQueueSize = config["fetchQueueSize"]

        # TLB (unified knob: apply to both ITLB & DTLB)
        # Reference: configs/example/kmhv3.py uses cpu.mmu.itb.size
        if "TLBSize" in config:
            cpu.mmu.itb.size = config["TLBSize"]
            cpu.mmu.dtb.size = config["TLBSize"]

        if "ICacheAssociativity" in config:
            assoc = int(config["ICacheAssociativity"])
            if not _is_power_of_two(assoc):
                fixed = _next_power_of_two(assoc)
                msg = f"ICacheAssociativity={assoc} is not power-of-two; using {fixed} to avoid gem5 warnings."
                if strict:
                    raise ValueError(msg)
                print("warn:", msg)
                assoc = fixed
            cpu.icache.assoc = assoc

        if "ICacheSize" in config:
            cpu.icache.size = config["ICacheSize"]

        # Branch predictor settings - only for DecoupledBPUWithBTB
        # Check if branch predictor has these attributes before accessing
        if "uBTBSize" in config:
            if hasattr(cpu.branchPred, 'ubtb'):
                cpu.branchPred.ubtb.numEntries = config["uBTBSize"]

        # Currently treat abtb as L1BTB, mbtb as L2BTB
        # L1BTB: 4bank, 4way(fixed)
        if "L1BTBSize" in config:
            if hasattr(cpu.branchPred, 'abtb'):
                cpu.branchPred.abtb.numEntries = config["L1BTBSize"]
        # L2BTB: 2bank, 6way(fixed)
        if "L2BTBSize" in config:
            if hasattr(cpu.branchPred, 'mbtb'):
                cpu.branchPred.mbtb.numEntries = config["L2BTBSize"]

        # # !GHB param obviously wrong
        # if "GHB" in config:
        #     ok = _try_set(cpu, "branchPred.tage.histBufferSize", config["GHB"])
        #     if strict and not ok:
        #         raise AttributeError("Failed to set branchPred.tage.histBufferSize")

        # if "BIM" in config:
        #     entries = int(config["BIM"])
        #     if entries <= 0 or (entries & (entries - 1)) != 0:
        #         raise ValueError(f"BIM must be a power of two: {entries}")
        #     log2_entries = int(math.log2(entries))
        #     ok = _try_set(cpu, "branchPred.tage.logTagTableSizes[0]", log2_entries)
        #     if strict and not ok:
        #         raise AttributeError("Failed to set branchPred.tage.logTagTableSizes[0]")

        # if "LHB" in config:
        #     ok = _try_set(cpu, "branchPred.localHistoryTableSize", config["LHB"])
        #     if strict and not ok:
        #         raise AttributeError("Failed to set branchPred.localHistoryTableSize")

        if "RASSize" in config:
            cpu.branchPred.ras.enabled = True
            cpu.branchPred.ras.numEntries = config["RASSize"]
            
        # fetch width 
        if "FetchWidth" in config:
            cpu.fetchWidth = config["FetchWidth"]

        # decode width
        if "DecodeWidth" in config:
            cpu.decodeWidth = config["DecodeWidth"]
        # rename width
        if "RenameWidth" in config:
            cpu.renameWidth = config["RenameWidth"]
        # physical register release width
        if "phyregReleaseWidth" in config:
            cpu.phyregReleaseWidth = config["phyregReleaseWidth"]
        if "phyregReleaseWidthInt" in config:
            cpu.phyregReleaseWidthInt = config["phyregReleaseWidthInt"]
        if "phyregReleaseWidthFp" in config:
            cpu.phyregReleaseWidthFp = config["phyregReleaseWidthFp"]
        if "phyregReleaseWidthVec" in config:
            cpu.phyregReleaseWidthVec = config["phyregReleaseWidthVec"]
        
        # The LSU Part
        if "LoadRequestQueueSize" in config:
            cpu.LQEntries = config["LoadRequestQueueSize"]

        # Preg
        if "IntPregsNumber" in config:
            cpu.numPhysIntRegs = config["IntPregsNumber"]
        if "FloatPregsNumber" in config:
            cpu.numPhysFloatRegs = config["FloatPregsNumber"]
        if "VectorPregsNumber" in config:
            cpu.numPhysVecRegs = config["VectorPregsNumber"]
        if "PredicateVectorPregsNumber" in config:
            cpu.numPhysVecPredRegs = config["PredicateVectorPregsNumber"]
        # ROB
        if "ROBSize" in config:
            cpu.numROBEntries = config["ROBSize"]

        if "LoadRequestQueueSize" in config:
            cpu.LQEntries = config["LoadRequestQueueSize"]
        if "TempStoreQueueSize" in config:
            cpu.SQEntries = config["TempStoreQueueSize"]

        if "StoreMergeBuffer" in config:
            cpu.SbufferEntries = config["StoreMergeBuffer"]

        if "MSHRSize" in config:
            cpu.dcache.mshrs = config["MSHRSize"]
        if "L1DcacheSize" in config:
            cpu.dcache.size = config["L1DcacheSize"]
        if "DCacheAssociativity" in config:
            assoc = int(config["DCacheAssociativity"])
            if not _is_power_of_two(assoc):
                fixed = _next_power_of_two(assoc)
                msg = f"DCacheAssociativity={assoc} is not power-of-two; using {fixed} to avoid gem5 warnings."
                if strict:
                    raise ValueError(msg)
                print("warn:", msg)
                assoc = fixed
            cpu.dcache.assoc = assoc

        if "CommitedStoreBufferSize(RSC)" in config:
            raise NotImplementedError("CommitedStoreBufferSize(RSC) is not implemented")

        if "WPUPolicy" in config:
            wpu_policy = config["WPUPolicy"]
            if wpu_policy == 'MRU':
                cpu.dcache.wpu = MRUWpu()
            elif wpu_policy == 'MMRU':
                cpu.dcache.wpu = MMRUWpu()
            elif wpu_policy == 'UTag':
                cpu.dcache.wpu = UTagWpu()
            elif wpu_policy == 'Null':
                cpu.dcache.wpu = NULL
            elif wpu_policy == 'IndexMRU':
                cpu.dcache.wpu = IndexMRUWpu()
            else:
                raise ValueError(f"Invalid WPUPolicy: {wpu_policy}")

        if "cacheLoadPorts" in config:
            cpu.cacheLoadPorts = config["cacheLoadPorts"]
        if "cacheStorePorts" in config:
            cpu.cacheStorePorts = config["cacheStorePorts"]

        if "RARQSize" in config:
            cpu.RARQEntries = config["RARQSize"]
        if "RAWQSize" in config:
            cpu.RAWQEntries = config["RAWQSize"]

        if "LFSTSize" in config:
            cpu.LFSTSize = config["LFSTSize"]
        if "LFSTEntrySize" in config:
            cpu.LFSTEntrySize = config["LFSTEntrySize"]
        if "SSITSize" in config:
            cpu.SSITSize = config["SSITSize"]

        if "l1d_replacement_policy" in config:
            policy = config["l1d_replacement_policy"]
            if policy == 'TreePLRURP':
                cpu.dcache.replacement_policy = TreePLRURP()
            # Backward-compatible aliases for DRRIPRP
            elif policy in ('DrripRP', 'DRRIPRP'):
                cpu.dcache.replacement_policy = DRRIPRP()
            elif policy == 'LRURP':
                cpu.dcache.replacement_policy = LRURP()
            else:
                raise ValueError(f"Invalid l1d_replacement_policy: {policy}")
        # The OEX Part
        cpu.scheduler = KMHV3DSEScheduler(params)


if __name__ == "__m5_main__":
    FutureClass = None
    args = xiangshan_system_init()
    args.enable_difftest = False
    args.raw_cpt = True
    args.no_pf = False # enable prefetcher
    assert not args.external_memory_system

    # Set default bp_type to DecoupledBPUWithBTB to match kmhv3.py
    # This ensures branch predictor has ubtb, abtb, mbtb attributes
    args.bp_type = 'DecoupledBPUWithBTB'

    space = build_design_space()
    
    # Match the memories with the CPUs, based on the options for the test system
    TestMemClass = Simulation.setMemClass(args)

    test_sys = build_xiangshan_system(args)

    bind_gem5(system=test_sys, config=space.default_config())

    root = Root(full_system=True, system=test_sys)

    Simulation.run_vanilla(args, root, test_sys, FutureClass)