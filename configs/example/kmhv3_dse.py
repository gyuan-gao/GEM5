from dataclasses import dataclass
import enum
import json
import random
import os
import subprocess
import sys

import m5
from m5.objects import *
from m5.util import addToPath

addToPath('../')

from typing import Any, Dict, List, Optional, Tuple

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


def _as_int(x: Any, *, name: str) -> int:
    try:
        return int(x)
    except Exception as e:
        raise ValueError(f"{name} must be int-like, got {x!r}") from e


def _solve_widths(
    *,
    allowed: Dict[str, List[Any]],
    fixed: Dict[str, Any],
    rng: random.Random,
) -> Dict[str, int]:
    fw_dom = sorted({_as_int(v, name="FetchWidth") for v in allowed.get("FetchWidth", [])})
    dw_dom = sorted({_as_int(v, name="DecodeWidth") for v in allowed.get("DecodeWidth", [])})
    rw_dom = sorted({_as_int(v, name="RenameWidth") for v in allowed.get("RenameWidth", [])})
    if not fw_dom or not dw_dom or not rw_dom:
        return {}

    fw_fix = fixed.get("FetchWidth")
    dw_fix = fixed.get("DecodeWidth")
    rw_fix = fixed.get("RenameWidth")

    feasible: List[Tuple[int, int, int]] = []
    for fw in fw_dom:
        if fw_fix is not None and fw != _as_int(fw_fix, name="FetchWidth"):
            continue
        for dw in dw_dom:
            if dw_fix is not None and dw != _as_int(dw_fix, name="DecodeWidth"):
                continue
            if fw < dw:
                continue
            for rw in rw_dom:
                if rw_fix is not None and rw != _as_int(rw_fix, name="RenameWidth"):
                    continue
                if dw < rw:
                    continue
                feasible.append((fw, dw, rw))

    if not feasible:
        raise ValueError("No feasible (FetchWidth, DecodeWidth, RenameWidth) satisfying FetchWidth >= DecodeWidth >= RenameWidth")

    fw, dw, rw = rng.choice(feasible)
    return {"FetchWidth": fw, "DecodeWidth": dw, "RenameWidth": rw}


def _solve_icache_assoc_even(
    *,
    allowed: Dict[str, List[Any]],
    fixed: Dict[str, Any],
    rng: random.Random,
) -> Dict[str, int]:
    if "ICacheAssociativity" not in allowed:
        return {}

    if fixed.get("ICacheAssociativity") is not None:
        assoc = _as_int(fixed["ICacheAssociativity"], name="ICacheAssociativity")
        if assoc % 2 != 0:
            raise ValueError(f"ICacheAssociativity must be multiple of 2, got {assoc}")
        return {"ICacheAssociativity": assoc}

    dom = sorted({_as_int(v, name="ICacheAssociativity") for v in allowed["ICacheAssociativity"]})
    dom = [v for v in dom if v % 2 == 0]
    if not dom:
        raise ValueError("No feasible ICacheAssociativity values satisfying multiple-of-2 constraint")
    return {"ICacheAssociativity": rng.choice(dom)}


def _check_iq_binding_spec(spec: Dict[str, Any], *, enforce_deq_match: bool, fixed_deq: Dict[str, Optional[int]]) -> None:
    m_fu = {"SX": 4, "VX": 5, "MX": 2}
    allowed_k = {"SX": {2, 3}, "VX": {1, 2}, "MX": {2, 3}}

    for cls in ("SX", "VX", "MX"):
        if cls not in spec or not isinstance(spec[cls], dict):
            raise ValueError(f"IQBindingSpec missing class {cls}")
        queues = spec[cls].get("queues")
        if not isinstance(queues, list) or len(queues) == 0:
            raise ValueError(f"IQBindingSpec[{cls}].queues must be a non-empty list")

        mask_all = (1 << m_fu[cls]) - 1
        class_union = 0

        for q in queues:
            if not isinstance(q, dict):
                raise ValueError(f"IQBindingSpec[{cls}].queues contains non-dict entry")
            deq_size = _as_int(q.get("deq_size"), name=f"IQBindingSpec[{cls}].queue.deq_size")
            if deq_size not in allowed_k[cls]:
                raise ValueError(f"IQBindingSpec[{cls}] deq_size {deq_size} not in {sorted(allowed_k[cls])}")
            masks = q.get("port_fu_masks")
            if not isinstance(masks, list):
                raise ValueError(f"IQBindingSpec[{cls}].queue.port_fu_masks must be a list")
            if len(masks) != deq_size:
                raise ValueError(
                    f"IQBindingSpec[{cls}] deq_size={deq_size} but port_fu_masks has {len(masks)} entries"
                )

            seen = 0
            for mv in masks:
                m = _as_int(mv, name=f"IQBindingSpec[{cls}].queue.port_fu_masks[]")
                if m < 1 or m > mask_all:
                    raise ValueError(f"IQBindingSpec[{cls}] mask {m} out of range [1..{mask_all}]")
                if seen & m:
                    raise ValueError(f"IQBindingSpec[{cls}] queue has overlapping FU mask bits: {m}")
                seen |= m
                class_union |= m

            if enforce_deq_match:
                fixed = fixed_deq.get(cls)
                if fixed is not None and deq_size != int(fixed):
                    raise ValueError(f"IQBindingSpec[{cls}] deq_size={deq_size} does not match fixed {fixed}")

        if class_union != mask_all:
            raise ValueError(f"IQBindingSpec[{cls}] does not cover all FU bits (union=0x{class_union:x})")


def checker(
    space: KmhV3DesignSpace,
    config: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    *,
    allow_unknown: bool = False,
) -> None:
    if not isinstance(config, dict):
        raise ValueError(f"config must be dict, got {type(config).__name__}")

    allowed: Dict[str, List[Any]] = {p.name: list(p.values) for p in space.params}
    known = set(allowed.keys()) | {"SXQDeqSize", "VXQDeqSize", "MXQDeqSize", "IQBindingSpec"}

    unknown = [k for k in config.keys() if k not in known]
    if unknown and not allow_unknown:
        raise ValueError(f"Unknown config keys: {sorted(unknown)}")

    for k, v in config.items():
        if k in allowed:
            if v not in allowed[k]:
                raise ValueError(f"{k}={v!r} not in allowed values: {allowed[k]}")

    if "ICacheAssociativity" in config and config["ICacheAssociativity"] is not None:
        assoc = _as_int(config["ICacheAssociativity"], name="ICacheAssociativity")
        if assoc % 2 != 0:
            raise ValueError(f"ICacheAssociativity must be multiple of 2, got {assoc}")

    if "FetchWidth" in config and "DecodeWidth" in config:
        fw = _as_int(config["FetchWidth"], name="FetchWidth")
        dw = _as_int(config["DecodeWidth"], name="DecodeWidth")
        if not (fw >= dw):
            raise ValueError(f"FetchWidth must be >= DecodeWidth, got {fw} and {dw}")

    if "DecodeWidth" in config and "RenameWidth" in config:
        dw = _as_int(config["DecodeWidth"], name="DecodeWidth")
        rw = _as_int(config["RenameWidth"], name="RenameWidth")
        if not (dw >= rw):
            raise ValueError(f"DecodeWidth must be >= RenameWidth, got {dw} and {rw}")

    spec_json = None
    enforce_deq_match = False
    fixed_deq = {"SX": None, "VX": None, "MX": None}
    if params is not None:
        if params.get("EnforceDeqMatch") is not None:
            enforce_deq_match = bool(params.get("EnforceDeqMatch"))
        spec_json = params.get("IQBindingSpec")
        fixed_deq = {
            "SX": params.get("SXQDeqSize"),
            "VX": params.get("VXQDeqSize"),
            "MX": params.get("MXQDeqSize"),
        }
    if spec_json is None:
        spec_json = config.get("IQBindingSpec")
    if spec_json is not None:
        if not isinstance(spec_json, str):
            raise ValueError(f"IQBindingSpec must be JSON string, got {type(spec_json).__name__}")
        try:
            spec = json.loads(spec_json)
        except Exception as e:
            raise ValueError("IQBindingSpec is not valid JSON") from e
        if not isinstance(spec, dict):
            raise ValueError("IQBindingSpec JSON must be an object")
        _check_iq_binding_spec(spec, enforce_deq_match=enforce_deq_match, fixed_deq=fixed_deq)

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
                values=sorted(set([x for x in range(160, 641, 20)])),
                default=240,
            ),
            ParameterRange(
                name="FloatPregsNumber",
                values=sorted(set([x for x in range(96, 321, 20)])),
                default=96,
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


def gen_random(
    space: KmhV3DesignSpace,
    *,
    seed: Optional[int] = None,
    base_config: Optional[Dict[str, Any]] = None,
    randomize_unconstrained: bool = True,
    respect_base_config: bool = True,
    use_solver_deq: bool = True,
    enforce_deq_match: bool = False,
    time_limit_s: float = 5.0,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    rng = random.Random(seed)

    allowed: Dict[str, List[Any]] = {p.name: list(p.values) for p in space.params}
    fixed_keys = set(base_config.keys()) if (base_config is not None and respect_base_config) else set()
    constrained_keys = {"FetchWidth", "DecodeWidth", "RenameWidth", "ICacheAssociativity"}

    if base_config is None:
        config: Dict[str, Any] = space.default_config()
    else:
        config = dict(base_config)

    if randomize_unconstrained:
        for p in space.params:
            if p.name in constrained_keys:
                continue
            if p.name in fixed_keys:
                continue
            config[p.name] = rng.choice(p.values)

        fixed_view = dict(config) if not fixed_keys else {k: config.get(k) for k in fixed_keys}
        config.update(_solve_widths(allowed=allowed, fixed=fixed_view, rng=rng))
        config.update(_solve_icache_assoc_even(allowed=allowed, fixed=fixed_view, rng=rng))

    params: Dict[str, Any] = {}

    params["SXQSize"] = config.get("SXQSize", 18)
    params["SXQEnqSize"] = config.get("SXQEnqSize", 3)
    params["SXQDeqSize"] = config.get("SXQDeqSize", 3)

    params["VXQSize"] = config.get("VXQSize", 18)
    params["VXQEnqSize"] = config.get("VXQEnqSize", 3)
    params["VXQDeqSize"] = config.get("VXQDeqSize", 1)

    params["MXQSize"] = config.get("MXQSize", 18)
    params["MXQEnqSize"] = config.get("MXQEnqSize", 3)
    params["MXQDeqSize"] = config.get("MXQDeqSize", 3)

    params["UseSolverDeq"] = bool(use_solver_deq)
    params["EnforceDeqMatch"] = bool(enforce_deq_match)

    solver_seed = rng.randint(0, (1 << 31) - 1) if seed is not None else None
    if params["UseSolverDeq"]:
        spec_json = solve_iq_binding_spec_external(
            use_solver_deq_sx=True,
            use_solver_deq_vx=True,
            use_solver_deq_mx=True,
            random_seed=solver_seed,
            time_limit_s=time_limit_s,
        )
    else:
        spec_json = solve_iq_binding_spec_external(
            use_solver_deq_sx=False,
            fixed_sx_deq=int(params["SXQDeqSize"]),
            use_solver_deq_vx=False,
            fixed_vx_deq=int(params["VXQDeqSize"]),
            use_solver_deq_mx=False,
            fixed_mx_deq=int(params["MXQDeqSize"]),
            random_seed=solver_seed,
            time_limit_s=time_limit_s,
        )

    params["IQBindingSpec"] = spec_json
    return config, params


def bind_gem5(system: Any, config: Dict[str, Any], params: Dict[str, Any]) -> None:


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
            cpu.icache.assoc = int(config["ICacheAssociativity"])

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
            cpu.dcache.assoc = int(config["DCacheAssociativity"])

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

    config, params = gen_random(
        space,
        seed=3454,
        base_config=space.default_config(),
        randomize_unconstrained=False,
        use_solver_deq=True,
        enforce_deq_match=False,
        time_limit_s=5.0,
    )
    checker(space, config, params)
    bind_gem5(system=test_sys, config=config, params=params)

    root = Root(full_system=True, system=test_sys)

    Simulation.run_vanilla(args, root, test_sys, FutureClass)