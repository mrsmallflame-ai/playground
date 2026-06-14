import io
import unittest

from vm import Instruction, VMError, VirtualMachine, assemble, disassemble, run_source


class FunctionalVMTests(unittest.TestCase):
    def run_program(self, source: str) -> tuple[str, list[object]]:
        output = io.StringIO()
        vm = run_source(source, stdout=output)
        return output.getvalue(), vm.stack

    def test_arithmetic(self) -> None:
        output, stack = self.run_program(
            """
            PUSH 6
            PUSH 7
            MUL
            PRINTLN
            HALT
            """
        )

        self.assertEqual(output, "42\n")
        self.assertEqual(stack, [])

    def test_loop_and_variables(self) -> None:
        output, _ = self.run_program(
            """
            PUSH 5
            STORE n
            PUSH 1
            STORE acc

            loop:
              LOAD n
              PUSH 1
              LE
              JNZ done

              LOAD acc
              LOAD n
              MUL
              STORE acc

              LOAD n
              PUSH 1
              SUB
              STORE n
              JMP loop

            done:
              LOAD acc
              PRINTLN
              HALT
            """
        )

        self.assertEqual(output, "120\n")

    def test_call_and_return(self) -> None:
        output, _ = self.run_program(
            """
            PUSH 9
            CALL square
            PRINTLN
            HALT

            square:
              DUP
              MUL
              RET
            """
        )

        self.assertEqual(output, "81\n")

    def test_disassemble_resolves_labels(self) -> None:
        program = assemble(
            """
            JMP end
            PUSH 1
            end:
              HALT
            """
        )

        self.assertEqual(
            disassemble(program),
            "\n".join(
                [
                    "0000: JMP 2",
                    "0001: PUSH 1",
                    "0002: HALT",
                ]
            ),
        )

    def test_stack_underflow_reports_source_line(self) -> None:
        with self.assertRaisesRegex(VMError, "line 2: stack underflow"):
            run_source(
                """
                POP
                """
            )

    def test_invalid_comparison_raises_vm_error(self) -> None:
        with self.assertRaisesRegex(VMError, "cannot compare 'x' and 1"):
            run_source(
                """
                PUSH "x"
                PUSH 1
                LT
                """
            )

    def test_invalid_call_target_does_not_mutate_call_stack(self) -> None:
        vm = VirtualMachine([Instruction("CALL", 99, line=1)])

        with self.assertRaisesRegex(VMError, "jump target out of range"):
            vm.run()

        self.assertEqual(vm.call_stack, [])

    def test_max_steps_catches_runaway_programs(self) -> None:
        with self.assertRaisesRegex(VMError, "maximum step count reached"):
            run_source(
                """
                loop:
                  JMP loop
                """,
                max_steps=5,
            )


if __name__ == "__main__":
    unittest.main()
