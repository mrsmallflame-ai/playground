# functional-vm

A small, working stack-based virtual machine written in Python. It includes:

- an assembler for readable `.fvm` programs
- a bytecode interpreter with a data stack, variables, jumps, and function calls
- a CLI for running and disassembling programs
- sample programs and unit tests

## Running it

From this directory:

```bash
python3 vm.py run examples/hello.fvm
python3 vm.py run examples/factorial.fvm
python3 vm.py run examples/function-call.fvm
```

Disassemble a program:

```bash
python3 vm.py disassemble examples/factorial.fvm
```

Run tests:

```bash
python3 -m unittest
python3 stress_vm.py --count 10000
python3 stress_vm.py --profile extreme
```

## Instruction Set

| Instruction | Stack effect | Description |
|-------------|--------------|-------------|
| `PUSH <value>` | `-> value` | Push an integer or quoted string. |
| `POP` | `a ->` | Drop the top stack value. |
| `DUP` | `a -> a a` | Duplicate the top stack value. |
| `SWAP` | `a b -> b a` | Swap the top two values. |
| `LOAD <name>` | `-> value` | Push a stored variable. |
| `STORE <name>` | `value ->` | Store a variable. |
| `ADD`, `SUB`, `MUL`, `DIV`, `MOD` | `a b -> result` | Integer arithmetic. |
| `EQ`, `NE`, `LT`, `LE`, `GT`, `GE` | `a b -> 0/1` | Comparisons. |
| `JMP <label>` | unchanged | Jump to a label. |
| `JZ <label>` | `condition ->` | Jump if condition is zero. |
| `JNZ <label>` | `condition ->` | Jump if condition is non-zero. |
| `CALL <label>` | unchanged | Call a label as a subroutine. |
| `RET` | unchanged | Return from a subroutine. |
| `PRINT` | `value ->` | Print without a newline. |
| `PRINTLN` | `value ->` | Print with a newline. |
| `HALT` | unchanged | Stop execution. |

Labels end with a colon:

```fvm
loop:
  LOAD n
  PUSH 1
  SUB
```

Comments start with `#`.

## Notes

- This is intentionally small and dependency-free so it can be copied, modified,
  or extended inside the playground.
- The VM stops after a configurable maximum instruction count to catch runaway
  programs.
