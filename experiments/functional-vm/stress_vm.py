#!/usr/bin/env python3
"""Deterministic stress tests for the functional VM."""

from __future__ import annotations

import argparse
import io
import random
from collections.abc import Callable

from vm import Instruction, VMError, VirtualMachine, run_source


def run_case(
    source: str,
    *,
    max_steps: int = 100_000,
) -> tuple[str, list[object], dict[str, object]]:
    output = io.StringIO()
    vm = run_source(source, stdout=output, max_steps=max_steps)
    return output.getvalue(), vm.stack, vm.variables


def assert_case(
    name: str,
    source: str,
    expected_output: str,
    *,
    expected_stack: list[object] | None = None,
    expected_vars: dict[str, object] | None = None,
    max_steps: int = 100_000,
) -> None:
    output, stack, variables = run_case(source, max_steps=max_steps)
    if output != expected_output:
        raise AssertionError(f"{name}: output {output!r} != {expected_output!r}")
    if expected_stack is not None and stack != expected_stack:
        raise AssertionError(f"{name}: stack {stack!r} != {expected_stack!r}")
    if expected_vars is not None and variables != expected_vars:
        raise AssertionError(f"{name}: variables {variables!r} != {expected_vars!r}")


def assert_error(
    name: str,
    source: str,
    expected_message: str,
    *,
    max_steps: int = 100_000,
) -> None:
    try:
        run_case(source, max_steps=max_steps)
    except VMError as exc:
        if expected_message not in str(exc):
            raise AssertionError(
                f"{name}: {exc!s} does not contain {expected_message!r}"
            ) from exc
        return

    raise AssertionError(f"{name}: expected VMError containing {expected_message!r}")


def arithmetic_case(rng: random.Random, index: int) -> None:
    left = rng.randint(-10_000, 10_000)
    right = rng.randint(-10_000, 10_000)
    op, expected = rng.choice(
        [
            ("ADD", left + right),
            ("SUB", left - right),
            ("MUL", left * right),
            ("DIV", left // (right or 1)),
            ("MOD", left % (right or 1)),
        ]
    )
    if op in {"DIV", "MOD"} and right == 0:
        right = 1

    assert_case(
        f"arithmetic-{index}",
        f"""
        PUSH {left}
        PUSH {right}
        {op}
        PRINTLN
        HALT
        """,
        f"{expected}\n",
    )


def variable_case(rng: random.Random, index: int) -> None:
    values = [rng.randint(-500, 500) for _ in range(4)]
    expected = (values[0] + values[1]) * (values[2] - values[3])

    assert_case(
        f"variable-{index}",
        f"""
        PUSH {values[0]}
        STORE a
        PUSH {values[1]}
        STORE b
        PUSH {values[2]}
        STORE c
        PUSH {values[3]}
        STORE d
        LOAD a
        LOAD b
        ADD
        LOAD c
        LOAD d
        SUB
        MUL
        PRINTLN
        HALT
        """,
        f"{expected}\n",
        expected_vars={"a": values[0], "b": values[1], "c": values[2], "d": values[3]},
    )


def branch_case(rng: random.Random, index: int) -> None:
    value = rng.randint(-1000, 1000)
    expected = "non-zero\n" if value != 0 else "zero\n"

    assert_case(
        f"branch-{index}",
        f"""
        PUSH {value}
        JNZ nonzero
        PUSH "zero"
        PRINTLN
        HALT
        nonzero:
          PUSH "non-zero"
          PRINTLN
          HALT
        """,
        expected,
    )


def loop_case(rng: random.Random, index: int) -> None:
    count = rng.randint(0, 80)
    expected = sum(range(1, count + 1))

    assert_case(
        f"loop-{index}",
        f"""
        PUSH {count}
        STORE n
        PUSH 0
        STORE total

        loop:
          LOAD n
          PUSH 0
          LE
          JNZ done

          LOAD total
          LOAD n
          ADD
          STORE total

          LOAD n
          PUSH 1
          SUB
          STORE n
          JMP loop

        done:
          LOAD total
          PRINTLN
          HALT
        """,
        f"{expected}\n",
    )


def call_case(rng: random.Random, index: int) -> None:
    value = rng.randint(-200, 200)

    assert_case(
        f"call-{index}",
        f"""
        PUSH {value}
        CALL square
        PRINTLN
        HALT

        square:
          DUP
          MUL
          RET
        """,
        f"{value * value}\n",
    )


def error_case(rng: random.Random, index: int) -> None:
    source, expected = rng.choice(
        [
            ("POP\n", "stack underflow"),
            ("PUSH 1\nPUSH 0\nDIV\n", "division by zero"),
            ("LOAD missing\n", "unknown variable"),
            ("RET\n", "RET without CALL"),
            ("JMP nowhere\n", "unknown label"),
        ]
    )

    assert_error(f"error-{index}", source, expected)


def extreme_integer_case() -> None:
    left = 10**120 + 12_345
    right = 2**512 - 1
    expected = (left * right) - right

    assert_case(
        "extreme-integers",
        f"""
        PUSH {left}
        PUSH {right}
        MUL
        PUSH {right}
        SUB
        PRINTLN
        HALT
        """,
        f"{expected}\n",
    )


def extreme_stack_case() -> None:
    size = 5_000
    pushes = "\n".join(f"PUSH {value}" for value in range(1, size + 1))
    adds = "\n".join("ADD" for _ in range(size - 1))
    expected = size * (size + 1) // 2

    assert_case(
        "extreme-stack-pressure",
        f"""
        {pushes}
        {adds}
        PRINTLN
        HALT
        """,
        f"{expected}\n",
        max_steps=20_000,
    )


def extreme_variables_case() -> None:
    size = 2_000
    stores = "\n".join(f"PUSH {value}\nSTORE v_{value}" for value in range(size))
    loads = "\n".join(f"LOAD v_{value}" for value in range(size))
    adds = "\n".join("ADD" for _ in range(size - 1))
    expected = size * (size - 1) // 2

    assert_case(
        "extreme-variable-pressure",
        f"""
        {stores}
        {loads}
        {adds}
        PRINTLN
        HALT
        """,
        f"{expected}\n",
        expected_stack=[],
        max_steps=20_000,
    )


def extreme_label_chain_case() -> None:
    size = 2_000
    jumps = "\n".join(f"label_{index}:\n  JMP label_{index + 1}" for index in range(size))

    assert_case(
        "extreme-label-chain",
        f"""
        JMP label_0
        {jumps}
        label_{size}:
          PUSH "label chain complete"
          PRINTLN
          HALT
        """,
        "label chain complete\n",
        max_steps=5_000,
    )


def extreme_deep_call_case() -> None:
    depth = 1_500
    frames = "\n".join(
        f"frame_{index}:\n  CALL frame_{index + 1}\n  RET"
        for index in range(depth)
    )

    assert_case(
        "extreme-deep-call",
        f"""
        CALL frame_0
        PRINTLN
        HALT

        {frames}
        frame_{depth}:
          PUSH 987654321
          RET
        """,
        "987654321\n",
        max_steps=5_000,
    )


def extreme_step_limit_case() -> None:
    pushes = "\n".join("PUSH 0" for _ in range(2_048))
    source = f"""
    {pushes}
    HALT
    """

    _, stack, _ = run_case(source, max_steps=2_049)
    if len(stack) != 2_048:
        raise AssertionError(f"extreme-step-limit: stack length was {len(stack)}")

    assert_error(
        "extreme-step-limit",
        source,
        "maximum step count reached",
        max_steps=2_048,
    )


def extreme_parser_case() -> None:
    assert_case(
        "extreme-parser",
        r'''
        PUSH "spaces, # hash, and \"quotes\" survive"
        PRINTLN
        HALT
        ''',
        'spaces, # hash, and "quotes" survive\n',
    )


def extreme_error_case() -> None:
    assert_error("extreme-empty-program", "", "instruction pointer out of range")
    assert_error("extreme-unknown-op", "WAT\n", "unknown instruction")
    assert_error("extreme-duplicate-label", "again:\nagain:\nHALT\n", "duplicate label")
    assert_error("extreme-invalid-label", "1bad:\nHALT\n", "invalid label")
    assert_error("extreme-unclosed-quote", 'PUSH "unterminated\n', "No closing quotation")
    assert_error("extreme-string-arithmetic", 'PUSH "x"\nPUSH 1\nADD\n', "expected integer")
    assert_error("extreme-mod-zero", "PUSH 1\nPUSH 0\nMOD\n", "modulo by zero")


def extreme_corrupt_bytecode_case() -> None:
    vm = VirtualMachine([Instruction("CALL", 99, line=1)])
    try:
        vm.run()
    except VMError as exc:
        if "jump target out of range" not in str(exc):
            raise AssertionError(
                "extreme-corrupt-bytecode: "
                f"{exc!s} does not contain 'jump target out of range'"
            ) from exc
        if vm.call_stack:
            raise AssertionError(
                f"extreme-corrupt-bytecode: call stack mutated to {vm.call_stack!r}"
            )
        return

    raise AssertionError("extreme-corrupt-bytecode: expected VMError")


EXTREME_CASES: list[Callable[[], None]] = [
    extreme_integer_case,
    extreme_stack_case,
    extreme_variables_case,
    extreme_label_chain_case,
    extreme_deep_call_case,
    extreme_step_limit_case,
    extreme_parser_case,
    extreme_error_case,
    extreme_corrupt_bytecode_case,
]


CASE_GENERATORS: list[Callable[[random.Random, int], None]] = [
    arithmetic_case,
    variable_case,
    branch_case,
    loop_case,
    call_case,
    error_case,
]


def run_stress_tests(count: int, seed: int) -> None:
    rng = random.Random(seed)
    for index in range(count):
        CASE_GENERATORS[index % len(CASE_GENERATORS)](rng, index)


def run_extreme_tests() -> None:
    for case in EXTREME_CASES:
        case()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic VM stress tests.")
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260614)
    parser.add_argument(
        "--profile",
        choices=["random", "extreme", "all"],
        default="random",
        help="choose the stress profile to run",
    )
    args = parser.parse_args()

    if args.profile in {"random", "all"}:
        run_stress_tests(args.count, args.seed)
        print(f"{args.count} random stress tests passed (seed={args.seed})")
    if args.profile in {"extreme", "all"}:
        run_extreme_tests()
        print(f"{len(EXTREME_CASES)} extreme stress scenarios passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
