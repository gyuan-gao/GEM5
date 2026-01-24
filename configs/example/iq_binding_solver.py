# ============================================================
# (1) iq_binding_solver.py
#     - Self-contained constraint toolset (OR-Tools CP-SAT)
#     - Returns a pure-data IQBindingSpec dict + JSON
# ============================================================

from __future__ import annotations

import json
import argparse
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model


def add_queue_constraints(
    model: cp_model.CpModel,
    name: str,
    m_fu: int,
    k_choices: List[int],
) -> dict:
    """
    Queue variables:
      - k in k_choices
      - up to k_max ports
      - active[i] <-> i < k
      - mask[i] in [1..(2^m)-1] if active else 0
      - IMPORTANT: ports within the same queue must NOT partially overlap in opClass.
        gem5's issue_queue.cc enforces that outports' opClass masks are either identical
        or disjoint; partial overlap panics. We enforce a stronger condition here:
        within one queue, each FU bit can be used by at most one active port (bitwise disjoint).
    """
    if not k_choices:
        raise ValueError("k_choices must be non-empty")
    k_choices = sorted(set(int(x) for x in k_choices))
    if any(k <= 0 for k in k_choices):
        raise ValueError(f"Invalid k_choices={k_choices}: must be positive integers")

    k_min, k_max = k_choices[0], k_choices[-1]
    mask_all = (1 << m_fu) - 1
    if mask_all <= 0:
        raise ValueError(f"m_fu must be >= 1, got {m_fu}")

    k = model.NewIntVar(k_min, k_max, f"{name}_k")
    model.AddAllowedAssignments([k], [[v] for v in k_choices])

    active: List[cp_model.IntVar] = []
    masks: List[cp_model.IntVar] = []
    for i in range(k_max):
        a = model.NewBoolVar(f"{name}_active_{i}")
        active.append(a)

        mi = model.NewIntVar(0, mask_all, f"{name}_mask_{i}")
        masks.append(mi)

        # active <-> (i < k)
        model.Add(k >= i + 1).OnlyEnforceIf(a)
        model.Add(k <= i).OnlyEnforceIf(a.Not())

        # domain gating
        model.Add(mi >= 1).OnlyEnforceIf(a)
        model.Add(mi <= mask_all).OnlyEnforceIf(a)
        model.Add(mi == 0).OnlyEnforceIf(a.Not())

    # Enforce: for each FU bit, at most one active port in this queue can have it.
    # Implemented via (mask -> has_bit) boolean mapping and sum <= 1.
    mask_all = (1 << m_fu) - 1
    allowed_per_bit = []
    for b in range(m_fu):
        bit = 1 << b
        allowed = [[mv, 1 if (mv & bit) else 0] for mv in range(0, mask_all + 1)]
        allowed_per_bit.append(allowed)

    for b in range(m_fu):
        has_list: List[cp_model.IntVar] = []
        for i in range(k_max):
            has_bit = model.NewBoolVar(f"{name}_hasbit{b}_p{i}")
            model.AddAllowedAssignments([masks[i], has_bit], allowed_per_bit[b])
            has_list.append(has_bit)
        model.Add(sum(has_list) <= 1)

    return {
        "name": name,
        "m_fu": m_fu,
        "k": k,
        "k_max": k_max,
        "mask": masks,
        "active": active,
        "mask_all": mask_all,
        "k_choices": k_choices,
    }


def add_class_cover_constraint(
    model: cp_model.CpModel,
    class_name: str,
    queues: List[dict],
    m_fu: int,
) -> None:
    """
    Constraint 1: class-level full coverage (union covers all FU types).
    Implement per-bit: for each bit b, exists active port with (mask has bit b).
    """
    mask_all = (1 << m_fu) - 1

    for b in range(m_fu):
        bit = 1 << b
        hits: List[cp_model.IntVar] = []

        allowed = []
        for mv in range(0, mask_all + 1):
            allowed.append([mv, 1 if (mv & bit) else 0])

        for q in queues:
            for i in range(q["k_max"]):
                has_bit = model.NewBoolVar(f"{class_name}_{q['name']}_hasbit{b}_p{i}")
                model.AddAllowedAssignments([q["mask"][i], has_bit], allowed)

                z = model.NewBoolVar(f"{class_name}_{q['name']}_hitbit{b}_p{i}")
                model.Add(z <= q["active"][i])
                model.Add(z <= has_bit)
                model.Add(z >= q["active"][i] + has_bit - 1)
                hits.append(z)

        model.Add(sum(hits) >= 1)


def _dump_queue_solution(solver: cp_model.CpSolver, q: dict, out_name: str) -> Dict:
    k = int(solver.Value(q["k"]))
    masks = [
        int(solver.Value(q["mask"][i]))
        for i in range(q["k_max"])
        if int(solver.Value(q["active"][i])) == 1
    ]
    if len(masks) != k:
        raise RuntimeError(f"{out_name}: k={k} but got {len(masks)} active masks")
    return {
        "name": out_name,
        "deq_size": k,
        "port_fu_masks": masks,
    }


def solve_iq_binding_spec(
    *,
    # Topology fixed to match your current scheduler: SXQ0..2, VXQ0..1, MXQ0
    num_sx: int = 3,
    num_vx: int = 2,
    num_mx: int = 1,

    # Allowed deq sizes
    sx_k_choices: Tuple[int, ...] = (2, 3),
    vx_k_choices: Tuple[int, ...] = (1, 2),
    mx_k_choices: Tuple[int, ...] = (2, 3),

    # Switch: solver decides deq_size, or user pins it
    use_solver_deq_sx: bool = True,
    use_solver_deq_vx: bool = True,
    use_solver_deq_mx: bool = True,

    fixed_sx_deq: Optional[int] = None,
    fixed_vx_deq: Optional[int] = None,
    fixed_mx_deq: Optional[int] = None,

    # solver knobs
    time_limit_s: float = 5.0,
    random_seed: Optional[int] = None,
) -> Tuple[Dict, str]:
    """
    Return:
      spec_dict: IQBindingSpec (pure data dict)
      spec_json: JSON string
    """

    # FU pool sizes (bit positions assumed fixed across solver and scheduler)
    SX_m, MX_m, VX_m = 4, 2, 5

    def domain(choices: Tuple[int, ...], use_solver: bool, fixed: Optional[int], cls: str) -> List[int]:
        if use_solver:
            dom = sorted(set(int(x) for x in choices))
            if not dom:
                raise ValueError(f"{cls}: empty choices")
            return dom
        if fixed is None:
            raise ValueError(f"{cls}: pinned deq requested but fixed_{cls.lower()}_deq is None")
        return [int(fixed)]

    model = cp_model.CpModel()

    sx_dom = domain(sx_k_choices, use_solver_deq_sx, fixed_sx_deq, "SX")
    vx_dom = domain(vx_k_choices, use_solver_deq_vx, fixed_vx_deq, "VX")
    mx_dom = domain(mx_k_choices, use_solver_deq_mx, fixed_mx_deq, "MX")

    sx_qs = [add_queue_constraints(model, f"SXQ{i}", SX_m, sx_dom) for i in range(num_sx)]
    mx_qs = [add_queue_constraints(model, f"MXQ{i}", MX_m, mx_dom) for i in range(num_mx)]
    vx_qs = [add_queue_constraints(model, f"VXQ{i}", VX_m, vx_dom) for i in range(num_vx)]

    add_class_cover_constraint(model, "SX", sx_qs, SX_m)
    add_class_cover_constraint(model, "MX", mx_qs, MX_m)
    add_class_cover_constraint(model, "VX", vx_qs, VX_m)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    if random_seed is not None:
        solver.parameters.random_seed = int(random_seed)
        solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("No feasible IQ binding solution found.")

    sx_queues = [_dump_queue_solution(solver, sx_qs[i], f"SXQ{i}") for i in range(num_sx)]
    vx_queues = [_dump_queue_solution(solver, vx_qs[i], f"VXQ{i}") for i in range(num_vx)]
    mx_queues = [_dump_queue_solution(solver, mx_qs[i], f"MXQ{i}") for i in range(num_mx)]

    # Pure-data spec (no objects)
    spec: Dict = {
        "SX": {
            "rp_policy": {"rd_start": 0, "wr_start": 0, "rd_per_port": 2, "wr_per_port": 1},
            "queues": sx_queues,
        },
        "VX": {
            "rp_policy": {
                "fp_rd_start": 0,
                "fp_rd_per_port": 0,
                # store symbolic plan, scheduler instantiates objects
                "special_rp_plan": {
                    "VXQ0": {
                        "0": [("FpRD", 0, 0), ("FpRD", 1, 0), ("FpRD", 2, 0)]
                    }
                }
            },
            "queues": vx_queues,
        },
        "MX": {
            "rp_policy": {"rd_start": 0, "wr_start": 0, "rd_per_port": 2, "wr_per_port": 1},
            "queues": mx_queues,
        },
        "meta": {
            "use_solver_deq_sx": bool(use_solver_deq_sx),
            "use_solver_deq_vx": bool(use_solver_deq_vx),
            "use_solver_deq_mx": bool(use_solver_deq_mx),
            "time_limit_s": float(time_limit_s),
            "random_seed": None if random_seed is None else int(random_seed),
        }
    }

    spec_json = json.dumps(spec, sort_keys=True)
    return spec, spec_json


def _parse_bool01(s: str) -> bool:
    s = str(s).strip()
    if s in ("1", "true", "True", "yes", "y", "on"):
        return True
    if s in ("0", "false", "False", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"Expected 0/1 or true/false, got: {s}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Solve IQ binding spec and print JSON to stdout.")
    p.add_argument("--use-solver-deq-sx", type=_parse_bool01, required=True)
    p.add_argument("--use-solver-deq-vx", type=_parse_bool01, required=True)
    p.add_argument("--use-solver-deq-mx", type=_parse_bool01, required=True)
    p.add_argument("--fixed-sx-deq", type=int, default=None)
    p.add_argument("--fixed-vx-deq", type=int, default=None)
    p.add_argument("--fixed-mx-deq", type=int, default=None)
    p.add_argument("--random-seed", type=int, default=None)
    p.add_argument("--time-limit-s", type=float, default=5.0)

    args = p.parse_args(argv)

    _, spec_json = solve_iq_binding_spec(
        use_solver_deq_sx=bool(args.use_solver_deq_sx),
        use_solver_deq_vx=bool(args.use_solver_deq_vx),
        use_solver_deq_mx=bool(args.use_solver_deq_mx),
        fixed_sx_deq=args.fixed_sx_deq,
        fixed_vx_deq=args.fixed_vx_deq,
        fixed_mx_deq=args.fixed_mx_deq,
        random_seed=args.random_seed,
        time_limit_s=args.time_limit_s,
    )
    print(spec_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
