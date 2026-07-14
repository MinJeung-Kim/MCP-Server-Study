"""계산기 앱 — MCP와 무관한 순수 로직.

이 파일만 떼어내도 그대로 동작한다.
MCP는 나중에 이 클래스를 '감싸기'만 할 뿐, 여기를 고치지 않는다.
(기존 앱을 건드리지 않고 MCP로 노출하는 실무 패턴)
"""

import ast
import operator
from dataclasses import dataclass, field


class CalculatorError(Exception):
    """계산 중 발생한 오류."""


@dataclass
class Calculator:
    """사칙연산과 수식 평가를 지원하는 계산기."""

    history: list[str] = field(default_factory=list)

    # ── 기본 연산 ────────────────────────────────────
    def add(self, a: float, b: float) -> float:
        """더하기."""
        result = a + b
        self._record(f"{a} + {b} = {result}")
        return result

    def subtract(self, a: float, b: float) -> float:
        """빼기."""
        result = a - b
        self._record(f"{a} - {b} = {result}")
        return result

    def multiply(self, a: float, b: float) -> float:
        """곱하기."""
        result = a * b
        self._record(f"{a} × {b} = {result}")
        return result

    def divide(self, a: float, b: float) -> float:
        """나누기. 0으로 나누면 오류."""
        if b == 0:
            raise CalculatorError("0으로 나눌 수 없습니다.")
        result = a / b
        self._record(f"{a} ÷ {b} = {result}")
        return result

    def power(self, base: float, exponent: float) -> float:
        """거듭제곱."""
        result = base**exponent
        self._record(f"{base} ^ {exponent} = {result}")
        return result

    # ── 수식 평가 ────────────────────────────────────
    # 안전을 위해 eval() 대신 AST로 파싱한다.
    # eval()은 임의 코드 실행 위험이 있어 절대 쓰면 안 된다.
    _OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    def evaluate(self, expression: str) -> float:
        """수식 문자열을 계산한다. 예: "(2 + 3) * 4"."""
        try:
            tree = ast.parse(expression, mode="eval")
            result = self._eval_node(tree.body)
        except CalculatorError:
            raise
        except Exception as e:
            raise CalculatorError(f"잘못된 수식입니다: {expression}") from e

        self._record(f"{expression} = {result}")
        return result

    def _eval_node(self, node) -> float:
        """AST 노드를 재귀적으로 계산한다. 허용된 연산만 통과."""
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise CalculatorError("숫자만 사용할 수 있습니다.")
            return node.value

        if isinstance(node, ast.BinOp):
            op = self._OPS.get(type(node.op))
            if op is None:
                raise CalculatorError("허용되지 않은 연산자입니다.")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if op is operator.truediv and right == 0:
                raise CalculatorError("0으로 나눌 수 없습니다.")
            return op(left, right)

        if isinstance(node, ast.UnaryOp):
            op = self._OPS.get(type(node.op))
            if op is None:
                raise CalculatorError("허용되지 않은 연산자입니다.")
            return op(self._eval_node(node.operand))

        raise CalculatorError("허용되지 않은 표현식입니다.")

    # ── 히스토리 ─────────────────────────────────────
    def _record(self, entry: str) -> None:
        self.history.append(entry)

    def get_history(self, limit: int = 10) -> list[str]:
        """최근 계산 기록을 반환한다."""
        return self.history[-limit:]

    def clear_history(self) -> None:
        """기록을 모두 지운다."""
        self.history.clear()


# ── 단독 실행: CLI 계산기 ─────────────────────────────
if __name__ == "__main__":
    calc = Calculator()
    print("계산기 (종료: q)")
    while True:
        expr = input("> ").strip()
        if expr.lower() in ("q", "quit", "exit"):
            break
        if not expr:
            continue
        try:
            print(f"= {calc.evaluate(expr)}")
        except CalculatorError as e:
            print(f"오류: {e}")
    print("\n기록:")
    for h in calc.get_history():
        print(f"  {h}")
