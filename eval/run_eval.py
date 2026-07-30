import argparse
import asyncio
import time
from collections import defaultdict

from app.adapters.memory_sender import InMemoryEmailSender
from app.agent.agent import RoutingResult, build_agent, route_message
from app.agent.departments import Department
from app.agent.prompt import SYSTEM_PROMPT
from app.config import settings
from eval.dataset import CASES, Case


async def run_eval(model_name: str | None) -> None:
    eval_agent = build_agent(SYSTEM_PROMPT, model_name)
    effective_model = model_name or settings.ollama_model

    run_results: list[tuple[Case, RoutingResult, float]] = []

    t_start = time.monotonic()
    for i, case in enumerate(CASES, 1):
        t0 = time.monotonic()
        email_sender = InMemoryEmailSender()
        result = await route_message(
            case.message, "eval@example.com", email_sender, routing_agent=eval_agent
        )
        elapsed = time.monotonic() - t0
        run_results.append((case, result, elapsed))
        ok = result.department == case.expected
        print(
            f"  [{i:02d}/{len(CASES)}] {'OK  ' if ok else 'FAIL'}"
            f"  {case.expected.value:<15} → {result.department.value}"
        )

    total_time = time.monotonic() - t_start
    total = len(run_results)
    correct = sum(1 for c, r, _ in run_results if r.department == c.expected)
    agent_count = sum(1 for _, r, _ in run_results if r.routed_by == "agent")

    dept_correct: dict[Department, int] = defaultdict(int)
    dept_total: dict[Department, int] = defaultdict(int)
    for case, result, _ in run_results:
        dept_total[case.expected] += 1
        if result.department == case.expected:
            dept_correct[case.expected] += 1

    confusion: dict[tuple[Department, Department], int] = defaultdict(int)
    for case, result, _ in run_results:
        confusion[(case.expected, result.department)] += 1

    all_depts = list(Department)
    errors = [(c, r) for c, r, _ in run_results if r.department != c.expected]

    lines: list[str] = []
    lines.append(f"## Eval — model: `{effective_model}`\n")
    lines.append(
        f"**Zbiór:** {total} wiadomości &nbsp;|&nbsp; "
        f"**Accuracy:** {correct}/{total} = {correct / total:.0%} &nbsp;|&nbsp; "
        f"**Czas łączny:** {total_time:.1f}s &nbsp;|&nbsp; "
        f"**Średni:** {total_time / total:.1f}s/msg &nbsp;|&nbsp; "
        f"**Agent:** {agent_count} &nbsp;|&nbsp; **Fallback:** {total - agent_count}\n"
    )

    lines.append("### Accuracy per dział\n")
    lines.append("| Dział | Poprawne | Łącznie | Accuracy |")
    lines.append("|---|---:|---:|---:|")
    for dept in all_depts:
        n = dept_total[dept]
        if n == 0:
            continue
        acc = dept_correct[dept] / n
        lines.append(f"| `{dept.value}` | {dept_correct[dept]} | {n} | {acc:.0%} |")

    lines.append("\n### Macierz pomyłek\n")
    lines.append("Wiersze = oczekiwany, kolumny = otrzymany.\n")
    header = "| |" + "".join(f" `{d.value}` |" for d in all_depts)
    sep = "|---|" + "---:|" * len(all_depts)
    lines.append(header)
    lines.append(sep)
    for expected in all_depts:
        if dept_total[expected] == 0:
            continue
        row = f"| **`{expected.value}`** |"
        for received in all_depts:
            count = confusion[(expected, received)]
            if count == 0:
                row += " — |"
            elif expected == received:
                row += f" {count} |"
            else:
                row += f" **{count}** |"
        lines.append(row)

    if errors:
        lines.append(f"\n### Pomyłki ({len(errors)}) — materiał do strojenia promptu\n")
        for i, (case, result) in enumerate(errors, 1):
            snippet = case.message[:150].replace("\n", " ")
            if len(case.message) > 150:
                snippet += "…"
            lines.append(
                f"**{i}.** `{case.expected.value}` → `{result.department.value}`"
                f" ({result.routed_by})"
            )
            lines.append(f"> {snippet}\n")
    else:
        lines.append("\n_Brak pomyłek._\n")

    print("\n" + "\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval routera wiadomości")
    parser.add_argument(
        "--model",
        default=None,
        help="Nazwa modelu Ollama (domyślnie: settings.ollama_model)",
    )
    args = parser.parse_args()
    asyncio.run(run_eval(args.model))


if __name__ == "__main__":
    main()
