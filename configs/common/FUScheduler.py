

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

# class KMHV3DSEScheduler(Scheduler):
#     # INT: reduce issue ports while keeping full FU coverage
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         SXQSize = kwargs.get('SXQSize', 18)
#         VXQSize = kwargs.get('VXQSize', 18)
#         MXQSize = kwargs.get('MXQSize', 18)
#         LSQSize = kwargs.get('LSQSize', 18)
        
#         SXQEnqSize = kwargs.get('SXQEnqSize', 3)
#         VXQEnqSize = kwargs.get('VXQEnqSize', 3)
#         MXQEnqSize = kwargs.get('MXQEnqSize', 3)
#         LSQEnqSize = kwargs.get('LSQEnqSize', 3)
        
#         SXQDeqSize = kwargs.get('SXQDeqSize', 3)
#         VXQDeqSize = kwargs.get('VXQDeqSize', 1)
#         MXQDeqSize = kwargs.get('MXQDeqSize', 3)
#         LSQDeqSize = kwargs.get('LSQDeqSize', 4)

#         # __SXQ_FUPool=[IntALU(), IntCvt(), IntBJU(), IntMisc()]
        
#         __SXQ_A=[IntALU()]
#         __SXQ_AC=[IntALU(), IntCvt()]
#         __SXQ_AB=[IntALU(), IntBJU()]
#         __SXQ_ABC=[IntALU(),IntBJU(),IntCvt()]

#         __SXQ_CHOICES = {
#             'A': __SXQ_A,
#             'AC': __SXQ_AC,
#             'AB': __SXQ_AB,
#             'ABC': __SXQ_ABC,
#         }

#         def __pick(choice_map, key: str, default: str):
#             sel = kwargs.get(key, default)
#             try:
#                 return choice_map[sel]
#             except KeyError:
#                 raise ValueError(f"Invalid {key}: {sel}. Allowed={list(choice_map.keys())}")

#         # (sxq_id, deq_port) -> FU list
#         __SXQ_FUs = {
#             (sxq, port): __pick(__SXQ_CHOICES, f"SXQ{sxq}{port}_FUs", "ABC")
#             for sxq in range(3)
#             for port in range(3)
#         }
        
#         # __VXQ_FUPool=[FP_ALU(),FP_MISC(),FP_MAC(),FP_SLOW(),SIMD_Unit()]
#         # VXQ merge float & vector instructions
#         __VXQ_FM=[FP_ALU(),FP_MAC()]
#         __VXQ_FMA=[FP_ALU(),FP_MAC(),SIMD_Unit()]
#         __VXQ_ALU=[FP_ALU(),FP_SIMD_Unit()]
#         __VXQ_SHUF=[SIMD_Unit(),FP_MISC()]
#         __VXQ_SPEC=[FP_MISC(), FP_SLOW()]
#         __VXQ_V=[SIMD_Unit()]
#         __VXQ_CHOICES = {
#             'FM': __VXQ_FM,
#             'FMA': __VXQ_FMA,
#             'ALU': __VXQ_ALU,
#             'SHUF': __VXQ_SHUF,
#             'SPEC': __VXQ_SPEC,
#             'V': __VXQ_V,
#         }

#         def __pick_vxq(vxq: int, port: int, default: str = 'FM'):
#             """
#             Prefer VXQ{vxq}{port}_FUs (e.g. VXQ00_FUs). For backward
#             compatibility, allow VXQ{vxq}_FUs as an alias for port 0.
#             """
#             key = f"VXQ{vxq}{port}_FUs"
#             legacy_key = f"VXQ{vxq}_FUs"
#             if port == 0 and (legacy_key in kwargs) and (key not in kwargs):
#                 key = legacy_key
#             return __pick(__VXQ_CHOICES, key, default)

#         # (vxq_id, deq_port) -> FU list
#         __VXQ_FUs = {(vxq, port): __pick_vxq(vxq, port) for vxq in range(2) for port in range(2)}

#         if SXQDeqSize == 3:
#             __SXQs = [
#                 IssueQue(name='SXQ0', inports=SXQEnqSize, size=SXQSize, oports=[
#                     IssuePort(
#                         fu=__SXQ_FUs[(0, 0)],
#                         # RD/WR(port_id, priority)
#                         # need decision about ports
#                         rp=[IntRD(0, 0), IntRD(1, 0), IntWR(0, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(0, 1)],
#                         rp=[IntRD(2, 0), IntRD(3, 0), IntWR(1, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(0, 2)],
#                         rp=[IntRD(4, 0), IntRD(5, 0), IntWR(2, 0)]
#                     ),
#                 ]),
#                 IssueQue(name='SXQ1', inports=SXQEnqSize, size=SXQSize, oports=[
#                     IssuePort(
#                         fu=__SXQ_FUs[(1, 0)],
#                         rp=[IntRD(6, 0), IntRD(7, 0), IntWR(3, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(1, 1)],
#                         rp=[IntRD(8, 0), IntRD(9, 0), IntWR(4, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(1, 2)],
#                         rp=[IntRD(10, 0), IntRD(11, 0), IntWR(5, 0)]
#                     ),
#                 ]),
#                 IssueQue(name='SXQ2', inports=SXQEnqSize, size=SXQSize, oports=[
#                     IssuePort(
#                         fu=__SXQ_FUs[(2, 0)],
#                         rp=[IntRD(12, 0), IntRD(13, 0), IntWR(6, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(2, 1)],
#                         rp=[IntRD(14, 0), IntRD(15, 0), IntWR(7, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(2, 2)],
#                         rp=[IntRD(16, 0), IntRD(17, 0), IntWR(8, 0)]
#                     ),
#                 ]),
#             ]  # enable full access to regfile readport, no interleave.
#         elif SXQDeqSize == 2:
#             __SXQs = [
#                 IssueQue(name='SXQ0', inports=SXQEnqSize, size=SXQSize, oports=[
#                     IssuePort(
#                         fu=__SXQ_FUs[(0, 0)],
#                         rp=[IntRD(0, 0), IntRD(1, 0), IntWR(0, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(0, 1)],
#                         rp=[IntRD(2, 0), IntRD(3, 0), IntWR(1, 0)]
#                     ),
#                 ]),
#                 IssueQue(name='SXQ1', inports=SXQEnqSize, size=SXQSize, oports=[
#                     IssuePort(
#                         fu=__SXQ_FUs[(1, 0)],
#                         rp=[IntRD(4, 0), IntRD(5, 0), IntWR(2, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(1, 1)],
#                         rp=[IntRD(6, 0), IntRD(7, 0), IntWR(3, 0)]
#                     ),
#                 ]),
#                 IssueQue(name='SXQ2', inports=SXQEnqSize, size=SXQSize, oports=[
#                     IssuePort(
#                         fu=__SXQ_FUs[(2, 0)],
#                         rp=[IntRD(8, 0), IntRD(9, 0), IntWR(4, 0)]
#                     ),
#                     IssuePort(
#                         fu=__SXQ_FUs[(2, 1)],
#                         rp=[IntRD(10, 0), IntRD(11, 0), IntWR(5, 0)]
#                     ),
#                 ]),
#             ]
#         else:
#             raise ValueError(f"Invalid SXQDeqSize: {SXQDeqSize}")

    
#         if VXQDeqSize == 1:
#             __VXQs = [
#                 IssueQue(name='VXQ0', inports=VXQEnqSize, size=VXQSize, oports=[
#                     IssuePort(
#                         fu=__VXQ_FUs[(0, 0)],
#                         rp=[FpRD(0, 0), FpRD(1, 0), FpRD(2, 0), FpWR(0, 0)]
#                     ),
#                 ]),
#                 IssueQue(name='VXQ1', inports=VXQEnqSize, size=VXQSize, oports=[
#                     IssuePort(fu=__VXQ_FUs[(1, 0)]),
#                 ]),
#             ]
#         elif VXQDeqSize == 2:
#             __VXQs = [
#                 IssueQue(name='VXQ0', inports=VXQEnqSize, size=VXQSize, oports=[
#                     IssuePort(fu=__VXQ_FUs[(0, 0)]),
#                     IssuePort(fu=__VXQ_FUs[(0, 1)]),
#                 ]),
#                 IssueQue(name='VXQ1', inports=VXQEnqSize, size=VXQSize, oports=[
#                     IssuePort(fu=__VXQ_FUs[(1, 0)]),
#                     IssuePort(fu=__VXQ_FUs[(1, 1)]),
#                 ]),
#             ]
#         else:
#             raise ValueError(f"Invalid VXQDeqSize: {VXQDeqSize}")

#     # __MXQ_FUPool=[IntMult(),IntDiv()]
#     # rd/wr ports need to be tuned
#     if MXQDeqSize == 3:
#         __MXQs = [
#             IssueQue(name='MXQ0', inports=MXQEnqSize, size=MXQSize, oports=[
#                 IssuePort(fu=[IntMult(),IntDiv()]
#                           rp=[IntRD(0, 0), IntRD(1, 0), IntWR(0, 0)]),
#                 IssuePort(fu=[IntMult(),IntDiv()],
#                           rp=[IntRD(2, 0), IntRD(3, 0), IntWR(1, 0)]),
#                 IssuePort(fu=[IntMult(),IntDiv()],
#                           rp=[IntRD(4, 0), IntRD(5, 0), IntWR(2, 0)]),
#             ]),
#         ]
#     elif MXQDeqSize == 2:
#         __MXQs = [
#             IssueQue(name='MXQ0', inports=MXQEnqSize, size=MXQSize, oports=[
#                 IssuePort(fu=[IntMult(),IntDiv()]
#                           rp=[IntRD(0, 0), IntRD(1, 0), IntWR(0, 0)]),
#                 IssuePort(fu=[IntMult(),IntDiv()],
#                           rp=[IntRD(2, 0), IntRD(3, 0), IntWR(1, 0)]),
#             ]),
#         ]
#     else:
#         raise ValueError(f"Invalid MXQDeqSize: {MXQDeqSize}")

#     # MEM: keep structure; retain two load queues as requested

#     if LSQDeqSize == 4:
#         pass
#     elif LSQDeqSize == 3:
#         pass
#     elif LSQDeqSize == 2:
#         pass
    
#     __LSQs = [
#         IssueQue(name='ld0', inports=2, size=16, oports=[
#             IssuePort(fu=[ReadPort()], rp=[IntRD(7, 0)])
#         ]),
#         IssueQue(name='ld1', inports=2, size=16, oports=[
#             IssuePort(fu=[ReadPort()], rp=[IntRD(9, 0)])
#         ]),
#         IssueQue(name='sta0', inports=2, size=16, oports=[
#             IssuePort(fu=[WritePort()], rp=[IntRD(6, 1)])
#         ]),
#         # Keep one store-data queue to preserve StoreDataPort coverage, including FP store-data read.
#         IssueQue(name='std0', inports=2, size=16, oports=[
#             IssuePort(fu=[StoreDataPort()], rp=[IntRD(0, 1), FpRD(12, 0)])
#         ]),
#     ]

#     intRegfileBanks = 2

#     IQs = __intIQs + __memIQs + __fpIQs

#     __int_bank = [i.name for i in __intIQs]
#     __mem_bank = [i.name for i in __memIQs]
#     __fp_bank = [i.name for i in __fpIQs]

#     # Update wakeup network lists to match the new IQ names (avoid dangling references).
#     specWakeupNetwork = [
#         SpecWakeupChannel(
#             srcs=__int_bank + __mem_bank + ['fpIQ0'],
#             dsts=__int_bank + __mem_bank
#         ),
#         SpecWakeupChannel(
#             srcs=__mem_bank,
#             dsts=__fp_bank
#         ),
#         SpecWakeupChannel(
#             srcs=__fp_bank,
#             dsts=__fp_bank + ['std0']
#         )
#     ]

#     enableMainRdpOpt = True  # TX dynamic read port optimization

#     def disableAllRegArb(self):
#         print("Disable regfile arbitration")
#         for iq in self.IQs:
#             for port in iq.oports:
#                 port.rp.clear()
