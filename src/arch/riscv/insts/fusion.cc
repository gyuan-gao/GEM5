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
        return nullptr; // cannot fuse
    }

    return new ChainFusionInst(name, vec[1]->opClass(), vec[0], vec[1]);
}

const std::unordered_map<std::type_index, std::type_index> deCompressMap = {
    {typeid(RiscvISAInst::C_slli), typeid(RiscvISAInst::Slli)},
    {typeid(RiscvISAInst::C_srli), typeid(RiscvISAInst::Srli)},
    {typeid(RiscvISAInst::C_addi), typeid(RiscvISAInst::Addi)},
    {typeid(RiscvISAInst::C_addiw), typeid(RiscvISAInst::Addiw)},
    {typeid(RiscvISAInst::C_add), typeid(RiscvISAInst::Add)},
    {typeid(RiscvISAInst::C_addw), typeid(RiscvISAInst::Addw)},
    {typeid(RiscvISAInst::C_and), typeid(RiscvISAInst::And)},
    {typeid(RiscvISAInst::C_andi), typeid(RiscvISAInst::Andi)},
    {typeid(RiscvISAInst::C_zext_h), typeid(RiscvISAInst::Zext_h)},
    {typeid(RiscvISAInst::C_sext_h), typeid(RiscvISAInst::Sext_h)},
};


#define FuseKey(t, n, i) FusionKey(typeid(RiscvISAInst::t), n, i)
#define ChainCreator(n, ...) [](const std::vector<o3::DynInstPtr>& vec) { return chainFuseInsts(n, std::move(vec), [](const std::vector<o3::DynInstPtr>& vec) { return __VA_ARGS__ ;}); }

#define FirstDest0EqualSecond(a, b) (a->destRegIdx(0) == b->destRegIdx(0))
#define Dest0EqualSrc0(x) (x->destRegIdx(0) == x->srcRegIdx(0))

const FusionTag fusionMap = {
    {FuseKey(Slli, 1, 32), new FusionTag{
        {FuseKey(Srli, 1, 32), ChainCreator("low32", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {FuseKey(Srli, 1, 31), ChainCreator("sll1zext", FirstDest0EqualSecond(vec[0], vec[1]) && vec[0]->srcRegIdx(0) == vec[1]->srcRegIdx(0) )},
        {FuseKey(Srli, 1, 30), ChainCreator("sll2zext", FirstDest0EqualSecond(vec[0], vec[1]) && vec[0]->srcRegIdx(0) == vec[1]->srcRegIdx(0) )},
        {FuseKey(Srli, 1, 29), ChainCreator("sll3zext", FirstDest0EqualSecond(vec[0], vec[1]) && vec[0]->srcRegIdx(0) == vec[1]->srcRegIdx(0) )},
    }},
    {FuseKey(Slli, 1, 48), new FusionTag{
        {FuseKey(Srli, 1, 48), ChainCreator("low16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Slliw, 1, 16), new FusionTag{
        {FuseKey(Srliw, 1, 16), ChainCreator("low16w", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {FuseKey(Sraiw, 1, 16), ChainCreator("sext16w", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Slli, 1, 1), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("sll1add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Slli, 1, 2), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("sll2add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Slli, 1, 3), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("sll3add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Slli, 1, 4), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("sll4add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Srli, 1, 29), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("srl29add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Srli, 1, 30), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("srl30add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Srli, 1, 31), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("srl31add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Srli, 1, 32), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("srl32add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Srli, 1, 8), new FusionTag{
        {FuseKey(Andi, 1, 255), ChainCreator("getsecondbyte", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Andi, 1, 1), new FusionTag{
        {FuseKey(Add, 2, 0), ChainCreator("add1ifodd", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {FuseKey(Addw, 2, 0), ChainCreator("add1ifoddw", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {FuseKey(Addw, 2, 0), new FusionTag{
        {FuseKey(Andi, 1, 255), ChainCreator("addwbyte", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {FuseKey(Andi, 1, 1), ChainCreator("addwbit", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {FuseKey(Zext_h, 1, 0), ChainCreator("addwzexth", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {FuseKey(Sext_h, 1, 0), ChainCreator("addwsexth", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    // TODO: logic operation and extract its LSB
    // TODO: logic operation and extract its lower 16 bits
    // TODO: OR(Cat(src1(63, 8), 0.U(8.W)), src2)
    // TODO: mul 7-bit data with 32-bit data
};





}
}
