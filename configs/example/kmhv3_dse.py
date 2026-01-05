from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Any, Dict, List


class ParamType(Enum):
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
                values=[64, 128],
                default=64,
                ptype=ParamType.CPU,
            ),
            ParameterRange(
                name="ICacheAssociativity",
                values=[4, 6],
                default=4,
                ptype=ParamType.ICache,
            ),
            ParameterRange(
                name="ICacheEntriesNumber",
                values=[128, 256, 512],
                default=256,
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
                name="RASSize"
                value=[16,32,64],
                default=32,
            ),
            ParameterRange(
                name="FetchWidth",
                value=[8,16],
                default=16,
            ),
            # LSU Part:
            ParameterRange(
                name="LoadRequestQueueSize",
                value=[16,32,64],
                default=32,
            ),
            # OEX Part:
            ParameterRange(
                name="SXQSize",
                value=[12,18,24,30,36],
                default=18,
            ),
            ParameterRange(
                name="VXQSize",
                value=[12,18,24,30,36],
                default=18,
            ),
            ParameterRange(
                name="MXQSize",
                value=[12,18,24,30,36],
                default=18,
            ),
            ParameterRange(
                name="LSQSize",
                value=[12,18,24,30,36],
                default=18,
            ),
            ParameterRange(
                name="SXQEnqSize",
                value=[1,2,3],
                default=3,
            ),
            ParameterRange(
                name="VXQEnqSize",
                value=[1,2,3],
                default=3,
            ),
            ParameterRange(
                name="MXQEnqSize",
                value=[1,2,3],
                default=3,
                name="SXQDeqSize",
                value=[2,3],
                default=2,
            )
            ParameterRange(
                name="VXQDeqSize",
                value=[1,2],
                default=1,
            )
            ParameterRange(
                name="MXQDeqSize",
                value=[2,3],
                default=2,
            )
            ParameterRange(
                name="LSQDeqSize",
                value=[2,3,4],
                default=4,
            ),
            ParameterRange(
                name="SXQ00_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="SXQ01_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="SXQ02_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="SXQ10_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="SXQ11_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="SXQ12_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="SXQ20_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="SXQ21_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="SXQ22_FUs",
                value=['A','AB','AC','ABC']
            ),
            ParameterRange(
                name="VXQ00_FUs",
                value=['FM','FMA','ALU','SHUF','SPEC','V']
            ),
            ParameterRange(
                name="VXQ01_FUs",
                value=['FM','FMA','ALU','SHUF','SPEC','V']
            ),
            ParameterRange(
                name="VXQ10_FUs",
                value=['FM','FMA','ALU','SHUF','SPEC','V']
            ),
            ParameterRange(
                name="VXQ11_FUs",
                value=['FM','FMA','ALU','SHUF','SPEC','V']
            ),

                # PREGs,value range need tuning
            ParameterRange(
                name="IntPregsNumber",
                value=[x for x in range(160, 641, 40)]
            ),
            ParameterRange(
                name="FloatPregsNumber",
                value=[x for x in range(96, 321, 40)]
            ),
            ParameterRange(
                name="VectorPregsNumber",
                value=[x for x in range(32, 96, 8)]
            ),
            ParameterRange(
                name="PredicateVectorPregsNumber",
                value=[x for x in range(96, 384, 16)]
            ),
                # Something
            ParameterRange(
                name="DecodeWidth",
                value=[4,6,8,10,12],
                default=6,
            ),
            ParameterRange(
                name="RenameWidth",
                value=[4,6,8,10,12],
                default=6,
            ),
            ParameterRange(
                name="numPregsRecycle",
                value=[4,6,8,10,12],
                default=6,
            ),
            # LSU
            ParameterRange(
                name="LoadRequestQueueSize",
                value=[16,32,64],
                default=32,
            ),
            ParameterRange(
                name="TempStoreQueueSize",
                value=[16,32,64],
                default=32,
            ),
            ParameterRange(
                name="StoreMergeBuffer",
                value=[8,16,32],
                default=16,
            ),
            ParameterRange(
                name="MSHRSize",
                value=[8,16,32],
                default=16,
            ),
            ParameterRange(
                name="L1DcacheSize",
                value=['64kB','128kB','256kB'],
                default='64kB'
            ),
            ParameterRange(
                name="DCacheAssociativity",
                values=[4, 6],
                default=4,
            ),
            
        ]
    )


def bind_gem5(system: Any, config: Dict[str, Any], *, strict: bool = False) -> None:
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
            cpu.icache.assoc = config["ICacheAssociativity"])

        # need varify
        if "ICacheEntriesNumber" in config:
            entries = int(config["ICacheEntriesNumber"])
            cpu.icache.cache_line_size=64
            size_bytes = entries * cpu.icache.cache_line_size
            cpu.icache.size = f"{size_bytes}B"

        if "uBTBSize" in config:
            cpu.branchPred.ubtb.numEntries = config["uBTBSize"]


        # Currently treat abtb as L1BTB, mbtb as L2BTB
        # L1BTB: 4bank, 4way(fixed)
        if "L1BTBSize" in config:
            cpu.branchPred.abtb.numEntries = config["L1BTBSize"]
        # L2BTB: 2bank, 6way(fixed)
        if "L2BTBSize" in config:
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
            cpu.branchPred.ras.size = config["RASSize"]
            
        # fetch width 
        if "FetchWidth" in config:
            cpu.fetchWidth = config["FetchWidth"]

        # decode width
        if "DecodeWidth" in config:
            cpu.decodeWidth = config["DecodeWidth"]
        # rename width
        if "RenameWidth" in config:
            cpu.renameWidth = config["RenameWidth"]
        # num pregs recycle
        if "numPregsRecycle" in config:
            cpu.numPregsRecycle = config["numPregsRecycle"]
        
        # The OEX Part
        # scheduler
        cpu.scheduler = KMHV3DSEScheduler(
            SXQSize=config["SXQSize"],
            VXQSize=config["VXQSize"],
            MXQSize=config["MXQSize"],
            LSQSize=config["LSQSize"],
            SXQEnqSize=config["SXQEnqSize"],
            VXQEnqSize=config["VXQEnqSize"],
            MXQEnqSize=config["MXQEnqSize"],
            LSQEnqSize=config["LSQEnqSize"],
            SXQDeqSize=config["SXQDeqSize"],
            VXQDeqSize=config["VXQDeqSize"],
            MXQDeqSize=config["MXQDeqSize"],
            LSQDeqSize=config["LSQDeqSize"],
        )        

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
            cpu.SQEntries = config["StoreRequestQueueSize"]

        if "StoreMergeBuffer" in config:
            cpu.SbufferEntries = config["StoreMergeBuffer"]

        if "MSHRSize" in config:
            cpu.dcache.mshrs = config["MSHRSize"]
        if "L1DcacheSize" in config:
            cpu.dcache.size = config["L1DcacheSize"]
        if "DCacheAssociativity" in config:
            cpu.dcache.assoc = config["DCacheAssociativity"]
if __name__ == "__m5_main__":
    FutureClass = None
    args = xiangshan_system_init()
    args.enable_difftest = False
    args.raw_cpt = True
    args.no_pf = False # enable prefetcher
    assert not args.external_memory_system

    space = build_design_space()
    
    # Match the memories with the CPUs, based on the options for the test system
    TestMemClass = Simulation.setMemClass(args)

    test_sys = build_xiangshan_system(args)

    bind_gem5(system=test_sys, config=space.default_config())

    root = Root(full_system=True, system=test_sys)

    Simulation.run_vanilla(args, root, test_sys, FutureClass)