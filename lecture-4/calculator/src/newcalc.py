import math
import flet as ft


class CalcButton(ft.ElevatedButton):
    def __init__(self, text, button_clicked, expand=1):
        super().__init__()
        self.text = text
        self.expand = expand
        self.on_click = button_clicked
        self.data = text


class DigitButton(CalcButton):
    def __init__(self, text, button_clicked, expand=1):
        CalcButton.__init__(self, text, button_clicked, expand)
        self.bgcolor = ft.Colors.WHITE24
        self.color = ft.Colors.WHITE


class ActionButton(CalcButton):
    def __init__(self, text, button_clicked):
        CalcButton.__init__(self, text, button_clicked)
        self.bgcolor = ft.Colors.ORANGE
        self.color = ft.Colors.WHITE


class ExtraActionButton(CalcButton):
    def __init__(self, text, button_clicked):
        CalcButton.__init__(self, text, button_clicked)
        self.bgcolor = ft.Colors.BLUE_GREY_100
        self.color = ft.Colors.BLACK


class SciButton(CalcButton):
    def __init__(self, text, button_clicked, tooltip=None):
        CalcButton.__init__(self, text, button_clicked)
        self.bgcolor = ft.Colors.BLUE_GREY_200
        self.color = ft.Colors.BLACK
        if tooltip:
            self.tooltip = tooltip


class CalculatorApp(ft.Container):
    def __init__(self):
        super().__init__()
        self.reset()

        self.result = ft.Text(value="0", color=ft.Colors.WHITE, size=20)
        self.width = 350
        self.bgcolor = ft.Colors.BLACK
        self.border_radius = ft.border_radius.all(20)
        self.padding = 20
        self.content = ft.Column(
            controls=[
                ft.Row(controls=[self.result], alignment="end"),
                # 科学計算ボタン行（最低5つ以上）
                ft.Row(
                    controls=[
                        SciButton(text="sin", button_clicked=self.button_clicked, tooltip="sin(x) (radian)"),
                        SciButton(text="cos", button_clicked=self.button_clicked, tooltip="cos(x) (radian)"),
                        SciButton(text="tan", button_clicked=self.button_clicked, tooltip="tan(x) (radian)"),
                        SciButton(text="√", button_clicked=self.button_clicked, tooltip="sqrt(x)"),
                    ]
                ),
                ft.Row(
                    controls=[
                        SciButton(text="x²", button_clicked=self.button_clicked, tooltip="x squared"),
                        SciButton(text="1/x", button_clicked=self.button_clicked, tooltip="reciprocal"),
                        SciButton(text="ln", button_clicked=self.button_clicked, tooltip="natural log"),
                        SciButton(text="exp", button_clicked=self.button_clicked, tooltip="e^x"),
                    ]
                ),
                ft.Row(
                    controls=[
                        ExtraActionButton(text="AC", button_clicked=self.button_clicked),
                        ExtraActionButton(text="+/-", button_clicked=self.button_clicked),
                        ExtraActionButton(text="%", button_clicked=self.button_clicked),
                        ActionButton(text="/", button_clicked=self.button_clicked),
                    ]
                ),
                ft.Row(
                    controls=[
                        DigitButton(text="7", button_clicked=self.button_clicked),
                        DigitButton(text="8", button_clicked=self.button_clicked),
                        DigitButton(text="9", button_clicked=self.button_clicked),
                        ActionButton(text="*", button_clicked=self.button_clicked),
                    ]
                ),
                ft.Row(
                    controls=[
                        DigitButton(text="4", button_clicked=self.button_clicked),
                        DigitButton(text="5", button_clicked=self.button_clicked),
                        DigitButton(text="6", button_clicked=self.button_clicked),
                        ActionButton(text="-", button_clicked=self.button_clicked),
                    ]
                ),
                ft.Row(
                    controls=[
                        DigitButton(text="1", button_clicked=self.button_clicked),
                        DigitButton(text="2", button_clicked=self.button_clicked),
                        DigitButton(text="3", button_clicked=self.button_clicked),
                        ActionButton(text="+", button_clicked=self.button_clicked),
                    ]
                ),
                ft.Row(
                    controls=[
                        DigitButton(text="0", expand=2, button_clicked=self.button_clicked),
                        DigitButton(text=".", button_clicked=self.button_clicked),
                        ActionButton(text="=", button_clicked=self.button_clicked),
                    ]
                ),
            ]
        )

    def button_clicked(self, e):
        data = e.control.data
        print(f"Button clicked with data = {data}")
        if self.result.value == "Error" or data == "AC":
            self.result.value = "0"
            self.reset()

        elif data in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."):
            if self.result.value == "0" or self.new_operand is True:
                self.result.value = data
                self.new_operand = False
            else:
                self.result.value = self.result.value + data

        elif data in ("+", "-", "*", "/"):
            self.result.value = self.calculate(self.operand1, float(self.result.value), self.operator)
            self.operator = data
            if self.result.value == "Error":
                self.operand1 = 0.0
            else:
                self.operand1 = float(self.result.value)
            self.new_operand = True

        elif data in ("="):
            self.result.value = self.calculate(self.operand1, float(self.result.value), self.operator)
            self.reset()

        elif data in ("%"):
            try:
                self.result.value = self.format_number(float(self.result.value) / 100.0)
                self.reset()
            except Exception:
                self.result.value = "Error"
                self.reset()

        elif data in ("+/-"):
            try:
                val = float(self.result.value)
                if val > 0:
                    self.result.value = "-" + str(self.format_number(val))
                elif val < 0:
                    self.result.value = str(self.format_number(abs(val)))
            except Exception:
                self.result.value = "Error"
                self.reset()

        # 科学計算（単項関数）
        elif data in ("sin", "cos", "tan", "√", "x²", "1/x", "ln", "exp"):
            try:
                x = float(self.result.value)
                if data == "sin":
                    y = math.sin(x)
                elif data == "cos":
                    y = math.cos(x)
                elif data == "tan":
                    y = math.tan(x)
                elif data == "√":
                    if x < 0:
                        raise ValueError("sqrt domain")
                    y = math.sqrt(x)
                elif data == "x²":
                    y = x * x
                elif data == "1/x":
                    if x == 0:
                        raise ZeroDivisionError("division by zero")
                    y = 1.0 / x
                elif data == "ln":
                    if x <= 0:
                        raise ValueError("ln domain")
                    y = math.log(x)
                elif data == "exp":
                    y = math.exp(x)
                self.result.value = str(self.format_number(y))
                # 科学計算は結果確定とみなし次の入力で新オペランド開始
                self.new_operand = True
                # 連続演算に備えてオペランド1を更新
                self.operand1 = float(self.result.value)
            except Exception:
                self.result.value = "Error"
                self.reset()

        self.update()

    def format_number(self, num):
        try:
            if isinstance(num, float) and num.is_integer():
                return int(num)
            return num
        except Exception:
            return num

    def calculate(self, operand1, operand2, operator):
        try:
            if operator == "+":
                return self.format_number(operand1 + operand2)
            elif operator == "-":
                return self.format_number(operand1 - operand2)
            elif operator == "*":
                return self.format_number(operand1 * operand2)
            elif operator == "/":
                if operand2 == 0:
                    return "Error"
                else:
                    return self.format_number(operand1 / operand2)
            else:
                # 未定義演算子
                return self.format_number(operand2)
        except Exception:
            return "Error"

    def reset(self):
        self.operator = "+"
        self.operand1 = 0.0
        self.new_operand = True


def main(page: ft.Page):
    page.title = "Simple Calculator (Scientific Mode)"
    page.theme_mode = ft.ThemeMode.DARK
    calc = CalculatorApp()
    page.add(calc)


ft.app(main)