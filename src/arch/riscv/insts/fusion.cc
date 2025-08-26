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
    {typeid(RiscvISAInst::C_or), typeid(RiscvISAInst::Or)},
    {typeid(RiscvISAInst::C_xor), typeid(RiscvISAInst::Xor)},
    {typeid(RiscvISAInst::C_zext_h), typeid(RiscvISAInst::Zext_h)},
    {typeid(RiscvISAInst::C_sext_h), typeid(RiscvISAInst::Sext_h)},
    {typeid(RiscvISAInst::C_lui), typeid(RiscvISAInst::Lui)},
};

#define ImmKey(t, i) FusionKey(typeid(RiscvISAInst::t), i)
#define AnyImmKey(t) FusionKey(typeid(RiscvISAInst::t))
#define ChainCreator(n, ...) [](const std::vector<o3::DynInstPtr>& vec) { return chainFuseInsts(n, std::move(vec), [](const std::vector<o3::DynInstPtr>& vec) { return __VA_ARGS__ ;}); }

#define FirstDest0EqualSecond(a, b) (a->destRegIdx(0) == b->destRegIdx(0))
#define Dest0EqualSrc0(x) (x->destRegIdx(0) == x->srcRegIdx(0))
#define Dest0EqualSrc0or1(x) ((x->destRegIdx(0) == x->srcRegIdx(0)) || (x->destRegIdx(0) == x->srcRegIdx(1)))
#define ImmIs(a, i) (a->staticInst->getImm() == i)

const FusionTag fusionMap = {
    // shift + alu
    {ImmKey(Slli, 32), new FusionTag{
        {ImmKey(Srli, 32), ChainCreator("low32", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {ImmKey(Srli, 31), ChainCreator("sll1zext", FirstDest0EqualSecond(vec[0], vec[1]) && vec[0]->srcRegIdx(0) == vec[1]->srcRegIdx(0) )},
        {ImmKey(Srli, 30), ChainCreator("sll2zext", FirstDest0EqualSecond(vec[0], vec[1]) && vec[0]->srcRegIdx(0) == vec[1]->srcRegIdx(0) )},
        {ImmKey(Srli, 29), ChainCreator("sll3zext", FirstDest0EqualSecond(vec[0], vec[1]) && vec[0]->srcRegIdx(0) == vec[1]->srcRegIdx(0) )},
    }},
    {ImmKey(Slli, 48), new FusionTag{
        {ImmKey(Srli, 48), ChainCreator("low16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {ImmKey(Slliw, 16), new FusionTag{
        {ImmKey(Srliw, 16), ChainCreator("low16w", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {ImmKey(Sraiw, 16), ChainCreator("sext16w", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {ImmKey(Slli, 1), new FusionTag{
        {AnyImmKey(Add), ChainCreator("sll1add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
    }},
    {ImmKey(Slli, 2), new FusionTag{
        {AnyImmKey(Add), ChainCreator("sll2add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
    }},
    {ImmKey(Slli, 3), new FusionTag{
        {AnyImmKey(Add), ChainCreator("sll3add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
    }},
    {ImmKey(Slli, 4), new FusionTag{
        {AnyImmKey(Add), ChainCreator("sll4add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
    }},
    {ImmKey(Srli, 29), new FusionTag{
        {AnyImmKey(Add), ChainCreator("srl29add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
    }},
    {ImmKey(Srli, 30), new FusionTag{
        {AnyImmKey(Add), ChainCreator("srl30add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
    }},
    {ImmKey(Srli, 31), new FusionTag{
        {AnyImmKey(Add), ChainCreator("srl31add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
    }},
    {ImmKey(Srli, 32), new FusionTag{
        {AnyImmKey(Add), ChainCreator("srl32add", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
    }},
    {ImmKey(Srli, 8), new FusionTag{
        {ImmKey(Andi, 0xff), ChainCreator("byte2", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    // logic + alu
    // put the anyimmkey ones at last, to avoid matching them first
    {AnyImmKey(Addw), new FusionTag{
        {ImmKey(Andi, 255), ChainCreator("addwbyte", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {ImmKey(Andi, 1), ChainCreator("addwbit", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Zext_h), ChainCreator("addwzexth", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Sext_h), ChainCreator("addwsexth", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {AnyImmKey(Andi), new FusionTag{
        {AnyImmKey(Add), ChainCreator("oddadd", ImmIs(vec[0], 1) && FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
        {AnyImmKey(Addw), ChainCreator("oddaddw", ImmIs(vec[0], 1) && FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
        {AnyImmKey(Or), ChainCreator("orh48", ImmIs(vec[0], -256) && FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},
        {AnyImmKey(Mulw), ChainCreator("mulw7", ImmIs(vec[0], 127) && FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0or1(vec[1]) )},

        {ImmKey(Andi, 1), ChainCreator("andi1", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Zext_h), ChainCreator("andi16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {AnyImmKey(And), new FusionTag{
        {ImmKey(Andi, 1), ChainCreator("and1", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Zext_h), ChainCreator("and16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {AnyImmKey(Ori), new FusionTag{
        {ImmKey(Andi, 1), ChainCreator("ori1", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Zext_h), ChainCreator("ori16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {AnyImmKey(Or), new FusionTag{
        {ImmKey(Andi, 1), ChainCreator("or1", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Zext_h), ChainCreator("or16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {AnyImmKey(Xori), new FusionTag{
        {ImmKey(Andi, 1), ChainCreator("xori1", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Zext_h), ChainCreator("xori16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {AnyImmKey(Xor), new FusionTag{
        {ImmKey(Andi, 1), ChainCreator("xor1", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Zext_h), ChainCreator("xor16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {AnyImmKey(Orc_b), new FusionTag{
        {ImmKey(Andi, 1), ChainCreator("orcb1", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Zext_h), ChainCreator("orcb16", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
    {AnyImmKey(Lui), new FusionTag{
        {AnyImmKey(Addi), ChainCreator("lui32", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
        {AnyImmKey(Addiw), ChainCreator("luiw32", FirstDest0EqualSecond(vec[0], vec[1]) && Dest0EqualSrc0(vec[1]) )},
    }},
};


}
}
