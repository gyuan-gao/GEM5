#ifndef __ARCH_RISCV_FUSION_INST_HH__
#define __ARCH_RISCV_FUSION_INST_HH__

#include <string>
#include <typeindex>
#include <variant>

#include "arch/riscv/insts/static_inst.hh"
#include "arch/riscv/regs/misc.hh"
#include "cpu/exec_context.hh"
#include "cpu/static_inst.hh"

namespace gem5
{

namespace RiscvISA
{

class FusionInst : public RiscvStaticInst
{
  protected:
    o3::DynInst* fused = nullptr;// do not use DynInstPtr here, as it will cause a circular dependency
  public:
    FusionInst(const char *name, OpClass op)
        : RiscvStaticInst(name, 0, op)
    {
    }

    void setFusedInst(o3::DynInstPtr& inst) {
        flags[IsFusion] = true;
        fused = inst.get();
    }
};

// A x1, x2, x3 + B x1, x1, x4
// => A fuseTmp, x2, x3 + B x1, fuseTmp, x4
// => C x1, (x2, x3), (fuseTmp, x4)
class ChainFusionInst : public FusionInst
{
    // only have one dst
    RegId destRegIdxArr[1];
    RegId srcRegIdxArr[4]; // max 4 src

    o3::DynInstPtr first, second;
    int firstNumSrcs = 0;
  public:
    ChainFusionInst(const char *name, OpClass op, o3::DynInstPtr first, o3::DynInstPtr second);

    Fault execute(ExecContext *xc, Trace::InstRecord *traceData) const override;

    std::string generateDisassembly(Addr pc, const loader::SymbolTable *symtab) const override { return mnemonic; }
};

struct FusionKey
{
    std::type_index type;
    bool ignore_imm;
    int imm;
    FusionKey() : type(typeid(void)), ignore_imm(true), imm(0) {}
    FusionKey(std::type_index t) : type(t), ignore_imm(true), imm(0) {}
    FusionKey(std::type_index t, int i) : type(t), ignore_imm(false), imm(i) {}

    // hash
    std::size_t operator()(const FusionKey& t) const {
        return (std::size_t)t.type.name();
    }

    bool operator==(const FusionKey& other) const {
        // other is the key in map
        return type == other.type && (imm == other.imm || other.ignore_imm);
    }
};

class FusionTag;

typedef StaticInstPtr (*FuseCreator)(const std::vector<o3::DynInstPtr> &subInsts);

using FusionVal = std::variant<FuseCreator, FusionTag*>;
class FusionTag: public std::unordered_map<FusionKey, FusionVal, FusionKey>
{
public:
    FusionTag(std::initializer_list<std::pair<const FusionKey, FusionVal>> init)
        : std::unordered_map<FusionKey, FusionVal, FusionKey>(init) {}
};

extern const std::unordered_map<std::type_index, std::type_index> deCompressMap;
extern const FusionTag fusionMap;

}

}

#endif
