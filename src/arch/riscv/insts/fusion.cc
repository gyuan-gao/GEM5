#include "fusion.hh"

namespace gem5::RiscvISAInst
{
    using namespace RiscvISA;
}

#include <fenv.h>

#include "arch/riscv/generated/decoder.hh"
#include "cpu/o3/dyn_inst.hh"

namespace gem5
{

namespace RiscvISA
{

ChainFusionInst::ChainFusionInst(const char *name, OpClass op, o3::DynInstPtr first, o3::DynInstPtr second)
    : FusionInst(name, op), first(first), second(second)
{
    panic_if(first->destRegIdx(0) != second->destRegIdx(0), "ChainFusionInst: first and second insts must have the same destination register");
    setRegIdxArrays(reinterpret_cast<RegIdArrayPtr>(&std::remove_pointer_t<decltype(this)>::srcRegIdxArr),
            reinterpret_cast<RegIdArrayPtr>(&std::remove_pointer_t<decltype(this)>::destRegIdxArr));
    setDestRegIdx(_numDestRegs++, first->destRegIdx(0));
    for (int i = 0; i < first->numSrcRegs(); ++i) {
        setSrcRegIdx(_numSrcRegs++, first->srcRegIdx(i));
    }
    firstNumSrcs = first->numSrcRegs();

    for (int i = 0; i < second->numSrcRegs(); ++i) {
        if (second->srcRegIdx(i) == first->destRegIdx(0)) {
            // if the second inst's src is the first inst's dst, we use a temporary reg
            setSrcRegIdx(_numSrcRegs++, FuseTmpReg);
        }
        else {
            // otherwise, just use the second inst's src reg
            setSrcRegIdx(_numSrcRegs++, second->srcRegIdx(i));
        }
    }

}

Fault
ChainFusionInst::execute(ExecContext *xc, Trace::InstRecord *traceData) const
{
    assert(fused);

    PhysRegIdPtr fuseTmp = nullptr;
    for (int i = 0; i < fused->numSrcRegs(); ++i) {
        if (fused->srcRegIdx(i) == FuseTmpReg) {
            fuseTmp = fused->renamedSrcIdx(i);
            break;
        }
    }
    if (fuseTmp) {
        first->renameDestReg(0, o3::VirtRegId(fuseTmp), o3::VirtRegId());
    } else {
        first->renameDestReg(0, fused->extRenamedDestIdx(0), o3::VirtRegId());
    }

    second->renameDestReg(0, fused->extRenamedDestIdx(0), o3::VirtRegId());

    // rename
    for (int i = 0; i < numSrcRegs(); i++) {
        if (i < firstNumSrcs) {
            // first inst's src
            first->renameSrcReg(i, fused->extRenamedSrcIdx(i));
        } else {
            // second inst's src
            second->renameSrcReg(i - firstNumSrcs, fused->extRenamedSrcIdx(i));
        }
    }

    // execute
    Fault fault = first->execute();
    if (fault != NoFault) return fault;
    fault = second->execute();
    return fault;
}

StaticInstPtr chainFuseInsts(const char* name, const std::vector<o3::DynInstPtr> &vec, std::function<bool(const std::vector<o3::DynInstPtr>&)> checker)
{
    if (!checker(vec)) {
        panic("");
        return nullptr; // cannot fuse
    }

    return new ChainFusionInst(name, vec[1]->opClass(), vec[0], vec[1]);
}

#define FuseKey(t, n, i) FusionKey(typeid(RiscvISAInst::t), n, i)
#define ChainCreator(n, ...) [](const std::vector<o3::DynInstPtr>& vec) { return chainFuseInsts(n, std::move(vec), [](const std::vector<o3::DynInstPtr>& vec) { return __VA_ARGS__ ;}); }

const FusionTag fusionMap = {
    // template
    // {FuseKey(Add, 2, 0), new FusionTag{
    //     {FuseKey(Add, 2, 0), ChainCreator("add4", vec[0]->destRegIdx(0) == vec[1]->destRegIdx(0))},
    // }},
};
}
}
