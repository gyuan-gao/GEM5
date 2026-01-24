from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional
from m5.SimObject import SimObject
from m5.params import *
from m5.objects.FuncUnit import *
from m5.objects.FuncUnitConfig import *
from m5.objects.FuncScheduler import *
#  must be consistent with issue_queue.cc
maxTotalRFPorts = (1 << 6) - 1
# portid, priority
# smaller value get higher priority
def IntRD(id, p):
    # [7:6] [5:2] [1:0]
    assert id < 16
    assert p < 4
    ret = (0 << 6) | (id << 2) | (p)
    return ret

def FpRD(id, p):
    # [7:6] [5:2] [1:0]
    assert id < 16
    assert p < 4
    ret = (1 << 6) | (id << 2) | (p)
    return ret

def FpWR(id, p):
    assert id < 16
    assert p < 4
    return (1 << 8) | (1 << 6) | (id << 2) | p  # write-bit + FP typeid

def IntWR(id, p):
    # [8] [7:6] [5:2] [1:0]
    assert id < 16
    assert p < 4
    ret = (1 << 8) | (0 << 6) | (id << 2) | (p)
    return ret

class ECoreScheduler(Scheduler):
    IQs = [
        IssueQue(name='intIQ0' , inports=2, size=2*12, oports=[
            IssuePort(fu=[IntALU(), IntBJU()]),
            IssuePort(fu=[IntALU(), IntBJU()])
        ]),
        IssueQue(name='intIQ1' , inports=2, size=2*12, oports=[
            IssuePort(fu=[IntALU(), IntBJU()]),
            IssuePort(fu=[IntALU(), IntBJU()])
        ]),
        IssueQue(name='intIQ2' , inports=2, size=2*12, oports=[
            IssuePort(fu=[IntMult(), IntDiv(), IntMisc()])
        ]),
        IssueQue(name='memIQ0' , inports=2, size=2*16, oports=[
            IssuePort(fu=[ReadPort()])
        ]),
        IssueQue(name='memIQ1' , inports=2, size=2*16, oports=[
            IssuePort(fu=[RdWrPort()])
        ]),
        IssueQue(name='fpIQ0' , inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()]),
            IssuePort(fu=[FP_ALU(), FP_MAC()])
        ], scheduleToExecDelay=3),
        IssueQue(name='fpIQ1' , inports=2, size=18, oports=[
            IssuePort(fu=[FP_MISC(), FP_SLOW()])
        ], scheduleToExecDelay=3),
        IssueQue(name='vecIQ0' , inports=2, size=16, oports=[
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()])
        ], scheduleToExecDelay=3),
    ]
    xbarWakeup = True

class ECore2ReadScheduler(Scheduler):
    IQs = [
        IssueQue(name='intIQ0' , inports=2, size=2*12, oports=[
            IssuePort(fu=[IntALU(), IntBJU()]),
            IssuePort(fu=[IntALU(), IntBJU()])
        ]),
        IssueQue(name='intIQ1' , inports=2, size=2*12, oports=[
            IssuePort(fu=[IntALU(), IntBJU()]),
            IssuePort(fu=[IntALU(), IntBJU()])
        ]),
        IssueQue(name='intIQ2' , inports=2, size=2*12, oports=[
            IssuePort(fu=[IntMult(), IntDiv(), IntMisc()])
        ]),
        IssueQue(name='memIQ0' , inports=2, size=2*16, oports=[
            IssuePort(fu=[ReadPort()]),
            IssuePort(fu=[ReadPort()])
        ]),
        IssueQue(name='memIQ1' , inports=2, size=2*16, oports=[
            IssuePort(fu=[WritePort()])
        ]),
        IssueQue(name='fpIQ0' , inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()]),
            IssuePort(fu=[FP_ALU(), FP_MAC()])
        ], scheduleToExecDelay=3),
        IssueQue(name='fpIQ1' , inports=2, size=18, oports=[
            IssuePort(fu=[FP_MISC()])
        ], scheduleToExecDelay=3),
        IssueQue(name='fpIQ4' , inports=2, size=18, oports=[
            IssuePort(fu=[FP_SLOW()])
        ], scheduleToExecDelay=3),
        IssueQue(name='vecIQ0' , inports=2, size=16, oports=[
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()])
        ], scheduleToExecDelay=3),
    ]
    xbarWakeup = True


class KunminghuScheduler(Scheduler):
    __intIQs = [
        IssueQue(name='intIQ0', inports=2, size=2*12, oports=[
            IssuePort(fu=[IntALU(), IntMult()], rp=[IntRD(0, 0), IntRD(1, 0)]),
            IssuePort(fu=[IntBJU()], rp=[IntRD(6, 1), IntRD(7, 1)])
        ]),
        IssueQue(name='intIQ1', inports=2, size=2*12, oports=[
            IssuePort(fu=[IntALU(), IntMult()], rp=[IntRD(2, 0), IntRD(3, 0)]),
            IssuePort(fu=[IntBJU()], rp=[IntRD(4, 1), IntRD(5, 1)])
        ]),
        IssueQue(name='intIQ2', inports=2, size=2*12, oports=[
            IssuePort(fu=[IntALU(), IntCvt()], rp=[IntRD(4, 0), IntRD(5, 0)]),
            IssuePort(fu=[IntBJU(), IntMisc()], rp=[IntRD(2, 1), IntRD(3, 1)])
        ]),
        IssueQue(name='intIQ3', inports=2, size=2*12, oports=[
            IssuePort(fu=[IntALU()], rp=[IntRD(6, 0), IntRD(7, 0)]),
            IssuePort(fu=[IntDiv()], rp=[IntRD(0, 1), IntRD(1, 1)])
        ])
    ]
    __memIQs = [
        IssueQue(name='load0', inports=2, size=16, oports=[
            IssuePort(fu=[ReadPort()], rp=[IntRD(8, 0)])
        ]),
        IssueQue(name='load1', inports=2, size=16, oports=[
            IssuePort(fu=[ReadPort()], rp=[IntRD(9, 0)])
        ]),
        IssueQue(name='load2', inports=2, size=16, oports=[
            IssuePort(fu=[ReadPort()], rp=[IntRD(10, 0)])
        ]),
        IssueQue(name='store0', inports=2, size=16, oports=[
            IssuePort(fu=[WritePort()], rp=[IntRD(7, 2)])
        ]),
        IssueQue(name='store1', inports=2, size=16, oports=[
            IssuePort(fu=[WritePort()], rp=[IntRD(6, 2)])
        ]),
        IssueQue(name='std0', inports=2, size=16, oports=[
            IssuePort(fu=[StoreDataPort()], rp=[IntRD(5,2), FpRD(9,0)])
        ]),
        IssueQue(name='std1', inports=2, size=16, oports=[
            IssuePort(fu=[StoreDataPort()], rp=[IntRD(3,2), FpRD(10,0)])
        ])
    ]
    __fpIQs = [
        IssueQue(name='fpIQ0', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MISC(), FP_MAC()], rp=[FpRD(0,0), FpRD(1, 0), FpRD(2,0)]),
            IssuePort(fu=[FP_SLOW()], rp=[FpRD(2,1), FpRD(5,1)])
        ], scheduleToExecDelay=2),
        IssueQue(name='fpIQ1', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()], rp=[FpRD(3,0), FpRD(4,0), FpRD(5,0)]),
            IssuePort(fu=[FP_SLOW()], rp=[FpRD(8,1), FpRD(9,1)]),
        ], scheduleToExecDelay=2),
        IssueQue(name='fpIQ2', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()], rp=[FpRD(6,0), FpRD(7,0), FpRD(8,0)])
        ], scheduleToExecDelay=2),
        IssueQue(name='vecIQ0', inports=5, size=16+16+10, oports=[
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()])
        ], scheduleToExecDelay=3)
    ]
    IQs = __intIQs + __memIQs + __fpIQs

    __int_bank = [i.name for i in __intIQs]
    __mem_bank = [i.name for i in __memIQs]
    __fp_bank = [i.name for i in __fpIQs]
    specWakeupNetwork = [
        SpecWakeupChannel(srcs=__int_bank + __mem_bank, dsts=__int_bank + __mem_bank),
        SpecWakeupChannel(srcs=__fp_bank, dsts=__fp_bank)
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.disableAllRegArb()

    def disableAllRegArb(self):
        print("Disable regfile arbitration")
        for iq in self.IQs:
            for port in iq.oports:
                port.rp.clear()

class KMHV3Scheduler(Scheduler):
    __intIQs = [
        IssueQue(name='intIQ0', inports=2, size=16, oports=[
            IssuePort(fu=[IntALU()],
                      rp=[IntRD(0, 0), IntRD(1, 0), IntWR(0, 0)]),
            IssuePort(fu=[IntBJU()],
                      rp=[IntRD(1, 1), IntRD(7, 2), IntWR(0, 1)])
        ]),
        IssueQue(name='intIQ1', inports=2, size=16, oports=[
            IssuePort(fu=[IntALU()],
                      rp=[IntRD(2, 0), IntRD(3, 0), IntWR(1, 0)]),
            IssuePort(fu=[IntBRU()],
                      rp=[IntRD(3, 1), IntRD(9, 2), IntWR(1, 1)])
        ]),
        IssueQue(name='intIQ2', inports=2, size=16, oports=[
            IssuePort(fu=[IntALU(), IntCvt()],
                      rp=[IntRD(4, 0), IntRD(5, 0), IntWR(2, 0)]),
            IssuePort(fu=[IntBRU()],
                      rp=[IntRD(5, 1), IntRD(11, 2), IntWR(2, 1)])
        ]),
        IssueQue(name='intIQ3', inports=2, size=16, oports=[
            IssuePort(fu=[IntALU(), IntMult()],
                      rp=[IntRD(6, 0), IntRD(7, 1)]),
        ]),
        IssueQue(name='intIQ4', inports=2, size=16, oports=[
            IssuePort(fu=[IntALU(), IntMult()],
                      rp=[IntRD(8, 0), IntRD(9, 1)]),
        ]),
        IssueQue(name='intIQ5', inports=2, size=16, oports=[
            IssuePort(fu=[IntALU(), IntDiv(), IntMisc()],
                      rp=[IntRD(10, 0), IntRD(11, 1)])
        ]),
    ]
    __memIQs = [
        IssueQue(name='ld0', inports=2, size=16, oports=[
            IssuePort(fu=[ReadPort()],
                      rp=[IntRD(7, 0)])]),
        IssueQue(name='ld1', inports=2, size=16, oports=[
            IssuePort(fu=[ReadPort()],
                      rp=[IntRD(9, 0)])]),
        IssueQue(name='ld2', inports=2, size=16, oports=[
            IssuePort(fu=[ReadPort()],
                      rp=[IntRD(11, 0)])]),
        IssueQue(name='sta0', inports=2, size=16, oports=[
            IssuePort(fu=[WritePort()],
                      rp=[IntRD(6, 1)])]),
        IssueQue(name='sta1', inports=2, size=16, oports=[
            IssuePort(fu=[WritePort()],
                      rp=[IntRD(8, 1)])]),
        IssueQue(name='std0', inports=2, size=16, oports=[
            IssuePort(fu=[StoreDataPort()],
                      rp=[IntRD(0, 1), FpRD(12, 0)])]),
        IssueQue(name='std1', inports=2, size=16, oports=[
            IssuePort(fu=[StoreDataPort()],
                      rp=[IntRD(2, 1), FpRD(13, 0)])]),
    ]
    __fpIQs = [
        IssueQue(name='fpIQ0', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MISC(), FP_MAC()],
                    #   rp=[FpRD(0,0), FpRD(1, 0), FpRD(2,0),FpWR(0,0)]),# modified
                      rp=[FpRD(0,0), FpRD(1, 0), FpRD(2,0)]),# origin
            IssuePort(fu=[FP_SLOW()],
                      rp=[FpRD(2,1), FpRD(5,1)])
        ]),
        IssueQue(name='fpIQ1', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()],
                      rp=[FpRD(3,0), FpRD(4,0), FpRD(5,0)])
        ]),
        IssueQue(name='fpIQ2', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()],
                      rp=[FpRD(6,0), FpRD(7,0), FpRD(8,0)])
        ]),
        IssueQue(name='fpIQ3', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()],
                      rp=[FpRD(9,0), FpRD(10,0), FpRD(11,0)])
        ]),
        IssueQue(name='vecIQ0', inports=5, size=16+16+10, oports=[
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()])
        ], scheduleToExecDelay=3),
    ]

    intRegfileBanks = 2

    IQs = __intIQs + __memIQs + __fpIQs
    __int_bank = [i.name for i in __intIQs]
    __mem_bank = [i.name for i in __memIQs]
    __fp_bank = [i.name for i in __fpIQs]
    specWakeupNetwork = [
        SpecWakeupChannel(srcs=__int_bank + __mem_bank + ['fpIQ0'], dsts=__int_bank + __mem_bank),
        SpecWakeupChannel(srcs=__mem_bank, dsts=__fp_bank),
        SpecWakeupChannel(srcs=__fp_bank, dsts=__fp_bank + ['std0', 'std1'])
    ]

    enableMainRdpOpt = True  # TX dynamic read port optimization

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.disableAllRegArb()

    def disableAllRegArb(self):
        print("Disable regfile arbitration")
        for iq in self.IQs:
            for port in iq.oports:
                port.rp.clear()


class IdealScheduler(Scheduler):
    __intIQs = [
        IssueQue(name='intIQ0', inports=2, size=2*24, oports=[
            IssuePort(fu=[IntALU(), IntMult()]),
            IssuePort(fu=[IntBJU()])
        ]),
        IssueQue(name='intIQ1', inports=2, size=2*24, oports=[
            IssuePort(fu=[IntALU(), IntMult()]),
            IssuePort(fu=[IntBJU()])
        ]),
        IssueQue(name='intIQ2', inports=2, size=2*24, oports=[
            IssuePort(fu=[IntALU(), IntCvt()]),
            IssuePort(fu=[IntBJU(), IntMisc()])
        ]),
        IssueQue(name='intIQ3', inports=2, size=2*24, oports=[
            IssuePort(fu=[IntALU()]),
            IssuePort(fu=[IntDiv()])
        ])
    ]
    __memIQs = [
        IssueQue(name='load0', inports=6, size=3*32, oports=[
            IssuePort(fu=[ReadPort()]),
            IssuePort(fu=[ReadPort()]),
            IssuePort(fu=[ReadPort()])
        ]),
        IssueQue(name='store0', inports=4, size=2*32, oports=[
            IssuePort(fu=[WritePort()]),
            IssuePort(fu=[WritePort()])
        ]),
        IssueQue(name='std0', inports=4, size=2*32, oports=[
            IssuePort(fu=[StoreDataPort()]),
            IssuePort(fu=[StoreDataPort()])
        ])
    ]
    __fpIQs = [
        IssueQue(name='fpIQ0', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MISC(), FP_MAC()])
        ], scheduleToExecDelay=3),
        IssueQue(name='fpIQ1', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()])
        ], scheduleToExecDelay=3),
        IssueQue(name='fpIQ2', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()])
        ], scheduleToExecDelay=3),
        IssueQue(name='fpIQ3', inports=2, size=18, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()])
        ], scheduleToExecDelay=3),
        IssueQue(name='fpIQ4', inports=2, size=18, oports=[
            IssuePort(fu=[FP_SLOW()]),
            IssuePort(fu=[FP_SLOW()])
        ], scheduleToExecDelay=3),
        IssueQue(name='vecIQ0', inports=5, size=16+16+10, oports=[
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()]),
            IssuePort(fu=[SIMD_Unit()])
        ], scheduleToExecDelay=3),
    ]
    IQs = __intIQs + __memIQs + __fpIQs
    __int_bank = [i.name for i in __intIQs]
    __mem_bank = [i.name for i in __memIQs]
    __fp_bank = [i.name for i in __fpIQs]
    specWakeupNetwork = [
        SpecWakeupChannel(srcs=__int_bank + __mem_bank, dsts=__int_bank + __mem_bank),
        SpecWakeupChannel(srcs=__fp_bank, dsts=__fp_bank)
    ]

    useOldDisp = True


DefaultScheduler = KunminghuScheduler

# ============================================================
# (2) scheduler_from_spec.py
#     - Full scheduler implementation that takes a params dict
#     - No dependency on get_param/set_param
#     - Main program:
#         1) calls solver -> spec_json/spec_dict
#         2) puts spec into params
#         3) instantiates scheduler with params
# ============================================================




# ----------------------------
# Utility functions
# ----------------------------

def _decode_mask(mask: int, fu_pool: List[Any]) -> List[Any]:
    mask = int(mask)
    if mask <= 0:
        raise ValueError(f"Invalid FU mask {mask}: must be >= 1")
    out: List[Any] = []
    for i in range(len(fu_pool)):
        if (mask >> i) & 1:
            # IMPORTANT:
            # FuncUnit objects are SimObjects and must NOT be shared across
            # multiple IssuePorts/IssueQues (multi-parent/orphan issues).
            # Store constructors/classes in fu_pool and instantiate here.
            ctor = fu_pool[i]
            out.append(ctor() if callable(ctor) else ctor)
    return out


def _alloc_rp_linear(make_rd, make_wr,
                     rd_start: int, wr_start: int,
                     num_ports: int, rd_per_port: int, wr_per_port: int,
                     rd_prio: int = 0, wr_prio: int = 0) -> Tuple[List[List[Any]], int, int]:
    rp_lists: List[List[Any]] = []
    rd = int(rd_start)
    wr = int(wr_start)
    # IntRD/IntWR/FpRD/FpWR encode port id in 4 bits -> id must be < 16.
    # For DSE-generated schedules, total requested "logical" ports can exceed 16.
    # We must therefore reuse physical port ids by wrapping within [0..15].
    _MAX_ID = 16
    for _ in range(int(num_ports)):
        rps: List[Any] = []
        for i in range(int(rd_per_port)):
            rps.append(make_rd((rd + i) % _MAX_ID, rd_prio))
        rd += int(rd_per_port)
        for j in range(int(wr_per_port)):
            rps.append(make_wr((wr + j) % _MAX_ID, wr_prio))
        wr += int(wr_per_port)
        rp_lists.append(rps)
    return rp_lists, rd, wr


def _instantiate_rp_from_plan(plan_items: List[Tuple[str, int, int]]) -> List[Any]:
    rp: List[Any] = []
    for kind, idx, prio in plan_items:
        kind = str(kind)
        idx = int(idx)
        prio = int(prio)
        if kind == "FpRD":
            rp.append(FpRD(idx, prio))
        elif kind == "FpWR":
            rp.append(FpWR(idx, prio))
        elif kind == "IntRD":
            rp.append(IntRD(idx, prio))
        elif kind == "IntWR":
            rp.append(IntWR(idx, prio))
        else:
            raise ValueError(f"Unknown RP kind in plan: {kind}")
    return rp


def _build_sx_queues(sol_sx: Dict, enq: int, size: int, fu_pool: List[Any]) -> List[Any]:
    rp_pol = sol_sx.get("rp_policy", {})
    rd = int(rp_pol.get("rd_start", 0))
    wr = int(rp_pol.get("wr_start", 0))
    rd_per_port = int(rp_pol.get("rd_per_port", 2))
    wr_per_port = int(rp_pol.get("wr_per_port", 1))

    out: List[Any] = []
    for q in sol_sx["queues"]:
        name = q["name"]
        deq = int(q["deq_size"])
        masks = q["port_fu_masks"]
        if len(masks) != deq:
            raise ValueError(f"{name}: deq_size={deq} but got {len(masks)} masks")

        rp_lists, rd, wr = _alloc_rp_linear(IntRD, IntWR, rd, wr, deq, rd_per_port, wr_per_port, 0, 0)
        oports: List[Any] = []
        for i in range(deq):
            oports.append(IssuePort(fu=_decode_mask(masks[i], fu_pool), rp=rp_lists[i]))
        out.append(IssueQue(name=name, inports=enq, size=size, oports=oports))
    return out


def _build_mx_queues(sol_mx: Dict, enq: int, size: int, fu_pool: List[Any]) -> List[Any]:
    rp_pol = sol_mx.get("rp_policy", {})
    rd = int(rp_pol.get("rd_start", 0))
    wr = int(rp_pol.get("wr_start", 0))
    rd_per_port = int(rp_pol.get("rd_per_port", 2))
    wr_per_port = int(rp_pol.get("wr_per_port", 1))

    out: List[Any] = []
    for q in sol_mx["queues"]:
        name = q["name"]
        deq = int(q["deq_size"])
        masks = q["port_fu_masks"]
        if len(masks) != deq:
            raise ValueError(f"{name}: deq_size={deq} but got {len(masks)} masks")

        rp_lists, rd, wr = _alloc_rp_linear(IntRD, IntWR, rd, wr, deq, rd_per_port, wr_per_port, 0, 0)
        oports: List[Any] = []
        for i in range(deq):
            oports.append(IssuePort(fu=_decode_mask(masks[i], fu_pool), rp=rp_lists[i]))
        out.append(IssueQue(name=name, inports=enq, size=size, oports=oports))
    return out


def _build_vx_queues(sol_vx: Dict, enq: int, size: int, fu_pool: List[Any]) -> List[Any]:
    rp_pol = sol_vx.get("rp_policy", {})
    fp_rd_start = int(rp_pol.get("fp_rd_start", 0))
    fp_rd_per_port = int(rp_pol.get("fp_rd_per_port", 0))
    special_plan = rp_pol.get("special_rp_plan", {})

    rd = fp_rd_start
    out: List[Any] = []
    for q in sol_vx["queues"]:
        name = q["name"]
        deq = int(q["deq_size"])
        masks = q["port_fu_masks"]
        if len(masks) != deq:
            raise ValueError(f"{name}: deq_size={deq} but got {len(masks)} masks")

        oports: List[Any] = []
        for i in range(deq):
            rp: List[Any] = []
            if name in special_plan and str(i) in special_plan[name]:
                rp = _instantiate_rp_from_plan(special_plan[name][str(i)])
            elif fp_rd_per_port > 0:
                rp = [FpRD(rd + j, 0) for j in range(fp_rd_per_port)]
                rd += fp_rd_per_port
            oports.append(IssuePort(fu=_decode_mask(masks[i], fu_pool), rp=rp))
        out.append(IssueQue(name=name, inports=enq, size=size, oports=oports))
    return out


# ----------------------------
# Scheduler that consumes params dict (no get_param)
# ----------------------------

class KMHV3DSEScheduler(Scheduler):
    """
    params dict schema (minimal):
      {
        "SXQSize": 18, "SXQEnqSize": 3, "SXQDeqSize": 3,
        "VXQSize": 18, "VXQEnqSize": 3, "VXQDeqSize": 1,
        "MXQSize": 18, "MXQEnqSize": 3, "MXQDeqSize": 3,
        "UseSolverDeq": True/False,
        "EnforceDeqMatch": True/False,
        "IQBindingSpec": dict or JSON string
      }
    """

    def __init__(self, params: Dict[str, Any], **kwargs):
        # Scheduler is a SimObject; when overriding __init__, gem5 requires
        # calling the SimObject initializer first.
        super().__init__(**kwargs)

        def P(key: str, default: Any) -> Any:
            return params.get(key, default)

        SXQSize = int(P('SXQSize', 18))
        VXQSize = int(P('VXQSize', 18))
        MXQSize = int(P('MXQSize', 18))
        LSQSize = int(P('LSQSize', 18))

        SXQEnqSize = int(P('SXQEnqSize', 3))
        VXQEnqSize = int(P('VXQEnqSize', 3))
        MXQEnqSize = int(P('MXQEnqSize', 3))
        LSQEnqSize = int(P('LSQEnqSize', 3))

        SXQDeqSize = int(P('SXQDeqSize', 3))
        VXQDeqSize = int(P('VXQDeqSize', 1))
        MXQDeqSize = int(P('MXQDeqSize', 3))
        LSQDeqSize = int(P('LSQDeqSize', 4))

        use_solver_deq = bool(P("UseSolverDeq", True))
        enforce_deq_match = bool(P("EnforceDeqMatch", False))

        spec_raw = P("IQBindingSpec", None)
        if spec_raw is None:
            raise ValueError("params['IQBindingSpec'] is required.")

        if isinstance(spec_raw, str):
            spec = json.loads(spec_raw)
        elif isinstance(spec_raw, dict):
            spec = spec_raw
        else:
            raise TypeError(f"IQBindingSpec must be dict or JSON string, got {type(spec_raw)}")

        # If parent controls deq, enforce it (spec must already contain correct mask lengths)
        if not use_solver_deq:
            for q in spec["SX"]["queues"]:
                if len(q["port_fu_masks"]) != SXQDeqSize:
                    raise ValueError(f"SX {q['name']}: masks length must == SXQDeqSize")
                q["deq_size"] = SXQDeqSize
            for q in spec["VX"]["queues"]:
                if len(q["port_fu_masks"]) != VXQDeqSize:
                    raise ValueError(f"VX {q['name']}: masks length must == VXQDeqSize")
                q["deq_size"] = VXQDeqSize
            for q in spec["MX"]["queues"]:
                if len(q["port_fu_masks"]) != MXQDeqSize:
                    raise ValueError(f"MX {q['name']}: masks length must == MXQDeqSize")
                q["deq_size"] = MXQDeqSize
        else:
            # Spec controls deq; optionally require it matches parent params
            if enforce_deq_match:
                for q in spec["SX"]["queues"]:
                    if int(q["deq_size"]) != SXQDeqSize:
                        raise ValueError(f"SX {q['name']}: deq_size mismatch")
                for q in spec["VX"]["queues"]:
                    if int(q["deq_size"]) != VXQDeqSize:
                        raise ValueError(f"VX {q['name']}: deq_size mismatch")
                for q in spec["MX"]["queues"]:
                    if int(q["deq_size"]) != MXQDeqSize:
                        raise ValueError(f"MX {q['name']}: deq_size mismatch")

        # FU pools (bit order must match solver)
        # Use constructors/classes (NOT instances) so each IssuePort gets fresh SimObjects.
        sx_pool = [IntALU, IntCvt, IntBJU, IntMisc]
        mx_pool = [IntMult, IntDiv]
        vx_pool = [FP_ALU, FP_MISC, FP_MAC, FP_SLOW, SIMD_Unit]

        __SXQs = _build_sx_queues(spec["SX"], SXQEnqSize, SXQSize, sx_pool)
        __VXQs = _build_vx_queues(spec["VX"], VXQEnqSize, VXQSize, vx_pool)
        __MXQs = _build_mx_queues(spec["MX"], MXQEnqSize, MXQSize, mx_pool)

        # LSQ fixed, as in your current design
        __LSQs = [
            IssueQue(name='ld0', inports=2, size=16, oports=[
                IssuePort(fu=[ReadPort()], rp=[IntRD(7, 0)])
            ]),
            IssueQue(name='ld1', inports=2, size=16, oports=[
                IssuePort(fu=[ReadPort()], rp=[IntRD(9, 0)])
            ]),
            IssueQue(name='sta0', inports=2, size=16, oports=[
                IssuePort(fu=[WritePort()], rp=[IntRD(6, 1)])
            ]),
            IssueQue(name='std0', inports=2, size=16, oports=[
                IssuePort(fu=[StoreDataPort()], rp=[IntRD(0, 1), FpRD(12, 0)])
            ]),
        ]

        self.intRegfileBanks = 2
        self.IQs = __SXQs + __VXQs + __MXQs + __LSQs

        __SX_bank = [i.name for i in __SXQs]
        __VX_bank = [i.name for i in __VXQs]
        __MX_bank = [i.name for i in __MXQs]
        __LS_bank = [i.name for i in __LSQs]

        self.specWakeupNetwork = [
            SpecWakeupChannel(
                srcs=__SX_bank + __MX_bank + __LS_bank,
                dsts=__SX_bank + __MX_bank + __LS_bank
            ),
            SpecWakeupChannel(
                srcs=__VX_bank,
                dsts=__VX_bank
            ),
            SpecWakeupChannel(
                srcs=__LS_bank,
                dsts=__VX_bank
            )
        ]

        self.enableMainRdpOpt = True

    def disableAllRegArb(self):
        print("Disable regfile arbitration")
        for iq in self.IQs:
            for port in iq.oports:
                port.rp.clear()



