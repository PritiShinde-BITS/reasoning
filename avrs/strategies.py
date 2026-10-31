"""Three independent, data-generating reasoning strategies. No gold labels are read."""
import json
import ast
from .expr import run_program, UnsupportedExpression

DIRECT_SYSTEM = """You are an accurate problem solver. Return only a JSON object with
keys `answer` (short final answer as a string) and `explanation` (brief, checkable
justification). For multiple choice return the 1-based option number as a string
(e.g., '1'), not its text. Do not invent facts or pretend to execute code."""

PROGRAM_SYSTEM = """PROGRAM_SOLVER. Solve the problem using a small, executable
EXPRESSION PROGRAM; return ONLY JSON with:
{"steps": [{"name":"x", "expr":"2 + 3"}], "answer_expr":"x", "explanation":"..."}
Each step assigns a variable to an expression, and answer_expr evaluates to the
final answer. Available expressions: literals, variables, + - * / // % **,
comparisons, and/or/not, indexing, if-else expressions, list/tuple/dict literals,
functions abs/min/max/sum/len/round/all/any/sorted/int/float/bool/str,
range (max 2000 elements), gcd/lcm/sqrt/factorial/comb/Fraction.
NO imports, loops, function definitions, methods, print, attributes, lambdas or
comprehensions. Do not give a precomputed answer in place of a calculation.
For multiple-choice, output the 1-based option number as the computed answer.
If the problem requires unsupported operations or cannot be formalized faithfully,
return {"steps":[], "answer_expr":"", "unsupported_reason":"..."}.
Do not claim a program ran: it will be checked outside the LLM."""

PLANNER_SYSTEM = """JOINT_PLAN. Produce exactly 3 meaningfully complementary
reasoning PLANS for the problem. JSON only:
{"plans":[{"id":"A","tactic":"direct","instructions":"..."},
{"id":"B","tactic":"program","instructions":"..."},
{"id":"C","tactic":"direct","instructions":"..."}]}
Allowed tactic values: direct or program. Distinguish assumptions, interpretations,
or solution routes rather than paraphrasing one approach. A program tactic must
be executable in the limited expression DSL; avoid it for inexpressible problems.
No final answers in plans; no access to hidden labels.
The task may be a hybrid multiple-choice problem.

Generate three complementary reasoning plans.

For each plan:
- Identify all answer choices.
- Determine which facts and calculations are needed
  to assess each relevant choice.
- Distinguish intermediate numeric results from
  the final multiple-choice answer.
- Do not assume an answer is correct in advance.
- Do not include the final answer in the plan."""

AGGREGATOR_SYSTEM = """AGGREGATOR. Select the most credible candidate using
its provided answer, explanation, and any genuinely executed computation trace.
Do not assume a majority is correct. A successful program execution is not proof
of semantic correctness. Return JSON only: {"selected_id":"A", "reason":"..."}.
You MUST choose one of the candidate ids; there is no reference answer.
Evaluate the candidate solutions against the
ORIGINAL question.

A successful program execution does not prove
that the program solves the original problem.

For multiple-choice problems:
- Select the answer supported by the evidence.
- The final answer must be a valid option number.
- Never return an intermediate calculation
  as the final answer.
- Do not invent evidence or assume that a
  candidate is correct."""


def _total_usage(responses):
    return {
        name: sum(r.usage.get(name, 0) for r in responses)
        for name in ("input_tokens", "output_tokens", "total_tokens")
    }


def _program_candidate(backend, question, guidance=""):
    user = f"Problem:\n{question}\n"
    if guidance:
        user += f"\nFollow this reasoning plan:\n{guidance}\n"
    response = backend.ask(PROGRAM_SYSTEM, user)
    payload = response.data
    try:
        executed = run_program(payload)
        answer = executed["answer"]
        status = "ok"
        trace = executed["trace"]
        failure = None
    except (UnsupportedExpression, SyntaxError) as exc:
        answer, status, trace = None, "unsupported_or_invalid", []
        failure = str(exc)[:500]
    # Diagnostic proxy only: a successful expression is NOT a proof that the
    # program models the question, or that it avoids hardcoded answers.
    substantive = False
    for step in payload.get("steps", []):
        try:
            parsed = ast.parse(step.get("expr", ""), mode="eval")
            if any(isinstance(n, (ast.BinOp, ast.Compare, ast.BoolOp, ast.Call, ast.IfExp))
                   for n in ast.walk(parsed)):
                substantive = True
        except (SyntaxError, TypeError, AttributeError):
            continue
    return {
        "answer": answer,
        "program_nontriviality_proxy": "has_operations" if substantive else "possibly_trivial",
        "execution_status": status,
        "execution_error": failure,
        "program": payload,
        "execution_trace": trace,
        "explanation": str(payload.get("explanation", "")),
    }, [response]


def _direct_candidate(backend, question, guidance=""):
    user = f"Problem:\n{question}\n"
    if guidance:
        user += f"\nUse this plan but determine the answer independently:\n{guidance}"
    response = backend.ask(DIRECT_SYSTEM, user)
    answer = response.data.get("answer")
    return {
        "answer": str(answer).strip() if answer is not None else None,
        "explanation": str(response.data.get("explanation", "")),
        "execution_status": "not_applicable",
        "program": None,
        "execution_trace": [],
        "execution_error": None,
    }, [response]


def generate_strategy(backend, question, strategy):
    if strategy == "direct":
        candidate, calls = _direct_candidate(backend, question)
        return {"answer": candidate["answer"], "candidates": [candidate],
                "selection": "single", "usage": _total_usage(calls), "model_calls": len(calls)}
    if strategy == "program":
        candidate, calls = _program_candidate(backend, question)
        return {"answer": candidate["answer"], "candidates": [candidate],
                "selection": "single", "usage": _total_usage(calls), "model_calls": len(calls)}
    if strategy != "multi_path":
        raise ValueError(f"Unknown strategy: {strategy}")

    plan_response = backend.ask(PLANNER_SYSTEM, f"Problem:\n{question}")
    calls = [plan_response]
    plans = plan_response.data.get("plans")
    if not isinstance(plans, list) or len(plans) != 3:
        raise ValueError("Planner must return exactly three plans")
    candidates = []
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict): raise ValueError("Invalid plan")
        tactic = plan.get("tactic")
        if tactic not in ("direct", "program"):
            raise ValueError(f"Unsupported plan tactic: {tactic}")
        # IDs are assigned by code to prevent duplicate or untrusted identifiers.
        plan_id = ("A", "B", "C")[index]
        guidance = str(plan.get("instructions", ""))[:2000]
        if tactic == "program":
            candidate, new_calls = _program_candidate(backend, question, guidance)
        else:
            candidate, new_calls = _direct_candidate(backend, question, guidance)
        calls.extend(new_calls)
        candidate.update({"id": plan_id, "tactic": tactic, "plan": guidance})
        candidates.append(candidate)

    # No reference labels are shown to the selector; record evidence for each path.
    selector_input = {
        "question": question,
        "candidates": [
            {"id": c["id"], "answer": c["answer"],
             "explanation": c["explanation"],
             "execution_status": c["execution_status"],
             "execution_trace": c["execution_trace"]}
            for c in candidates
        ],
    }
    chosen = backend.ask(AGGREGATOR_SYSTEM, json.dumps(selector_input, ensure_ascii=False))
    calls.append(chosen)
    selected_id = chosen.data.get("selected_id")
    if selected_id not in ("A", "B", "C"):
        raise ValueError("Aggregator selected an unknown candidate")
    selected = next(c for c in candidates if c["id"] == selected_id)
    return {
        "answer": selected["answer"],
        "candidates": candidates,
        "plans": plans,
        "selection": {"id": selected_id, "reason": chosen.data.get("reason", "")},
        "usage": _total_usage(calls),
        "model_calls": len(calls),
    }
