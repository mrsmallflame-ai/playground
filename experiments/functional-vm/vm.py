#!/usr/bin/env python3
"""A tiny assembler and stack-based virtual machine."""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


Value = int | str


class VMError(RuntimeError):
    """Raised when a program cannot be assembled or executed."""


@dataclass(frozen=True)
class Instruction:
    op: str
    arg: Value | None = None
    line: int = 0


NO_ARG_OPS = {
    "HALT",
    "POP",
    "DUP",
    "SWAP",
    "ADD",
    "SUB",
    "MUL",
    "DIV",
    "MOD",
    "EQ",
    "NE",
    "LT",
    "LE",
    "GT",
    "GE",
    "RET",
    "PRINT",
    "PRINTLN",
}

ONE_ARG_OPS = {
    "PUSH",
    "LOAD",
    "STORE",
    "JMP",
    "JZ",
    "JNZ",
    "CALL",
}

JUMP_OPS = {"JMP", "JZ", "JNZ", "CALL"}
INTEGER_RE = re.compile(r"^-?\d+$")
LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def parse_value(token: str) -> Value:
    if INTEGER_RE.match(token):
        return int(token)
    return token


def format_arg(arg: Value | None) -> str:
    if arg is None:
        return ""
    if isinstance(arg, str):
        return " " + repr(arg)
    return f" {arg}"


def tokenize(source_line: str, line_number: int) -> list[str]:
    try:
        return shlex.split(source_line, comments=True, posix=True)
    except ValueError as exc:
        raise VMError(f"line {line_number}: {exc}") from exc


def assemble(source: str) -> list[Instruction]:
    labels: dict[str, int] = {}
    unresolved: list[Instruction] = []

    for line_number, source_line in enumerate(source.splitlines(), start=1):
        tokens = tokenize(source_line, line_number)
        if not tokens:
            continue

        if tokens[0].endswith(":"):
            label = tokens[0][:-1]
            if not LABEL_RE.match(label):
                raise VMError(f"line {line_number}: invalid label {label!r}")
            if label in labels:
                raise VMError(f"line {line_number}: duplicate label {label!r}")
            labels[label] = len(unresolved)
            tokens = tokens[1:]
            if not tokens:
                continue

        op = tokens[0].upper()
        args = tokens[1:]

        if op in NO_ARG_OPS:
            if args:
                raise VMError(f"line {line_number}: {op} does not take an argument")
            unresolved.append(Instruction(op=op, line=line_number))
            continue

        if op in ONE_ARG_OPS:
            if len(args) != 1:
                raise VMError(f"line {line_number}: {op} expects exactly one argument")
            arg = parse_value(args[0]) if op == "PUSH" else args[0]
            unresolved.append(Instruction(op=op, arg=arg, line=line_number))
            continue

        raise VMError(f"line {line_number}: unknown instruction {op!r}")

    program: list[Instruction] = []
    for instruction in unresolved:
        if instruction.op not in JUMP_OPS:
            program.append(instruction)
            continue

        label = str(instruction.arg)
        if label not in labels:
            raise VMError(f"line {instruction.line}: unknown label {label!r}")
        program.append(
            Instruction(op=instruction.op, arg=labels[label], line=instruction.line)
        )

    return program


def disassemble(program: list[Instruction]) -> str:
    lines = []
    for address, instruction in enumerate(program):
        lines.append(f"{address:04d}: {instruction.op}{format_arg(instruction.arg)}")
    return "\n".join(lines)


class VirtualMachine:
    def __init__(
        self,
        program: list[Instruction],
        *,
        stdout: TextIO | None = None,
        trace: bool = False,
        max_steps: int = 100_000,
    ) -> None:
        self.program = program
        self.stdout = stdout if stdout is not None else sys.stdout
        self.trace = trace
        self.max_steps = max_steps
        self.ip = 0
        self.steps = 0
        self.stack: list[Value] = []
        self.variables: dict[str, Value] = {}
        self.call_stack: list[int] = []
        self.halted = False

    def run(self) -> "VirtualMachine":
        while not self.halted:
            self.step()
        return self

    def step(self) -> None:
        if self.steps >= self.max_steps:
            raise VMError(f"maximum step count reached ({self.max_steps})")
        if self.ip < 0 or self.ip >= len(self.program):
            raise VMError(f"instruction pointer out of range: {self.ip}")

        instruction = self.program[self.ip]
        if self.trace:
            self.stdout.write(
                f"ip={self.ip:04d} stack={self.stack!r} "
                f"vars={self.variables!r} :: "
                f"{instruction.op}{format_arg(instruction.arg)}\n"
            )

        self.ip += 1
        self.steps += 1
        self.execute(instruction)

    def execute(self, instruction: Instruction) -> None:
        op = instruction.op
        arg = instruction.arg

        if op == "HALT":
            self.halted = True
        elif op == "PUSH":
            if arg is None:
                raise self.error(instruction, "PUSH requires a value")
            self.stack.append(arg)
        elif op == "POP":
            self.pop(instruction)
        elif op == "DUP":
            self.stack.append(self.peek(instruction))
        elif op == "SWAP":
            if len(self.stack) < 2:
                raise self.error(instruction, "SWAP requires two stack values")
            self.stack[-1], self.stack[-2] = self.stack[-2], self.stack[-1]
        elif op == "LOAD":
            name = self.require_name(instruction)
            if name not in self.variables:
                raise self.error(instruction, f"unknown variable {name!r}")
            self.stack.append(self.variables[name])
        elif op == "STORE":
            name = self.require_name(instruction)
            self.variables[name] = self.pop(instruction)
        elif op in {"ADD", "SUB", "MUL", "DIV", "MOD"}:
            self.binary_int(instruction, op)
        elif op in {"EQ", "NE", "LT", "LE", "GT", "GE"}:
            self.compare(instruction, op)
        elif op == "JMP":
            self.jump(instruction)
        elif op == "JZ":
            target = self.require_address(instruction)
            if self.pop(instruction) == 0:
                self.ip = target
        elif op == "JNZ":
            target = self.require_address(instruction)
            if self.pop(instruction) != 0:
                self.ip = target
        elif op == "CALL":
            target = self.require_address(instruction)
            self.call_stack.append(self.ip)
            self.ip = target
        elif op == "RET":
            if not self.call_stack:
                raise self.error(instruction, "RET without CALL")
            self.ip = self.call_stack.pop()
        elif op == "PRINT":
            self.stdout.write(str(self.pop(instruction)))
        elif op == "PRINTLN":
            self.stdout.write(str(self.pop(instruction)) + "\n")
        else:
            raise self.error(instruction, f"unknown instruction {op!r}")

    def pop(self, instruction: Instruction) -> Value:
        if not self.stack:
            raise self.error(instruction, "stack underflow")
        return self.stack.pop()

    def peek(self, instruction: Instruction) -> Value:
        if not self.stack:
            raise self.error(instruction, "stack underflow")
        return self.stack[-1]

    def require_name(self, instruction: Instruction) -> str:
        if not isinstance(instruction.arg, str):
            raise self.error(instruction, f"{instruction.op} requires a name")
        return instruction.arg

    def require_address(self, instruction: Instruction) -> int:
        if not isinstance(instruction.arg, int):
            raise self.error(instruction, f"{instruction.op} requires an address")
        if instruction.arg < 0 or instruction.arg >= len(self.program):
            raise self.error(instruction, f"jump target out of range: {instruction.arg}")
        return instruction.arg

    def jump(self, instruction: Instruction) -> None:
        self.ip = self.require_address(instruction)

    def binary_int(self, instruction: Instruction, op: str) -> None:
        right = self.pop_int(instruction)
        left = self.pop_int(instruction)

        if op == "ADD":
            result = left + right
        elif op == "SUB":
            result = left - right
        elif op == "MUL":
            result = left * right
        elif op == "DIV":
            if right == 0:
                raise self.error(instruction, "division by zero")
            result = left // right
        elif op == "MOD":
            if right == 0:
                raise self.error(instruction, "modulo by zero")
            result = left % right
        else:
            raise self.error(instruction, f"unsupported arithmetic op {op!r}")

        self.stack.append(result)

    def compare(self, instruction: Instruction, op: str) -> None:
        right = self.pop(instruction)
        left = self.pop(instruction)

        try:
            if op == "EQ":
                result = left == right
            elif op == "NE":
                result = left != right
            elif op == "LT":
                result = left < right
            elif op == "LE":
                result = left <= right
            elif op == "GT":
                result = left > right
            elif op == "GE":
                result = left >= right
            else:
                raise self.error(instruction, f"unsupported comparison op {op!r}")
        except TypeError as exc:
            raise self.error(
                instruction,
                f"cannot compare {left!r} and {right!r}",
            ) from exc

        self.stack.append(1 if result else 0)

    def pop_int(self, instruction: Instruction) -> int:
        value = self.pop(instruction)
        if not isinstance(value, int):
            raise self.error(instruction, f"expected integer, got {value!r}")
        return value

    def error(self, instruction: Instruction, message: str) -> VMError:
        return VMError(f"line {instruction.line}: {message}")


def run_source(
    source: str,
    *,
    stdout: TextIO | None = None,
    trace: bool = False,
    max_steps: int = 100_000,
) -> VirtualMachine:
    return VirtualMachine(
        assemble(source),
        stdout=stdout,
        trace=trace,
        max_steps=max_steps,
    ).run()


def run_file(path: Path, *, trace: bool, max_steps: int) -> None:
    run_source(path.read_text(), trace=trace, max_steps=max_steps)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the functional-vm stack machine.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser("run", help="assemble and run a .fvm program")
    run.add_argument("program", type=Path)
    run.add_argument("--trace", action="store_true", help="print each executed step")
    run.add_argument(
        "--max-steps",
        type=int,
        default=100_000,
        help="stop after this many executed instructions",
    )

    disasm = subcommands.add_parser("disassemble", help="print assembled bytecode")
    disasm.add_argument("program", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            run_file(args.program, trace=args.trace, max_steps=args.max_steps)
        elif args.command == "disassemble":
            print(disassemble(assemble(args.program.read_text())))
        else:
            parser.error(f"unknown command {args.command!r}")
    except OSError as exc:
        print(f"file error: {exc}", file=sys.stderr)
        return 1
    except VMError as exc:
        print(f"vm error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
