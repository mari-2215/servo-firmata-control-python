from __future__ import annotations

import json
import math
import re
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from pyfirmata import Arduino, SERVO
except ImportError:  # The app still works in simulation mode without pyfirmata.
    Arduino = None
    SERVO = None


APP_TITLE = "Servo Firmata Control"
LOG_DIR = Path(__file__).resolve().parent / "logs"
SERVO_PINS = [3, 5, 6, 9, 10, 11]
SERVO_COUNT = 6


@dataclass
class ServoState:
    index: int
    pin: int
    name: str
    angle: int = 0
    speed: int = 5


@dataclass
class Posture:
    name: str
    servos: list[ServoState]
    order: list[int]
    mode: str

    @property
    def vector(self) -> str:
        parts = [self.name]
        for servo in self.servos:
            parts.append(f"M{servo.index}_{servo.angle}")
            parts.append(f"V{servo.index}_{servo.speed}")
        parts.append("ORDEM_" + "-".join(str(item) for item in self.order))
        parts.append("MODO_" + self.mode.upper())
        return "_".join(parts)


class ServoControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x760")
        self.minsize(1040, 680)

        LOG_DIR.mkdir(exist_ok=True)
        self.board = None
        self.servo_pins = {}
        self.connected_port = tk.StringVar(value="")
        self.status = tk.StringVar(value="Simulacao pronta. Todos os servos em zero.")
        self.posture_name = tk.StringVar(value="Postura_1")
        self.execution_mode = tk.StringVar(value="sequencial")
        self.selected_posture = tk.StringVar(value="")
        self.loaded_vector = tk.StringVar(value="Nenhuma postura carregada.")
        self.stop_motion = threading.Event()

        self.servos = [
            ServoState(index=i + 1, pin=SERVO_PINS[i], name=f"Motor {i + 1}")
            for i in range(SERVO_COUNT)
        ]
        self.angle_vars = [tk.IntVar(value=0) for _ in self.servos]
        self.speed_vars = [tk.IntVar(value=5) for _ in self.servos]
        self.name_vars = [tk.StringVar(value=servo.name) for servo in self.servos]

        self._configure_style()
        self._build_layout()
        self.refresh_posture_lists()
        self.update_interface()

    def _configure_style(self) -> None:
        self.configure(bg="#071013")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#071013")
        style.configure("Panel.TFrame", background="#0e1a1e", borderwidth=1, relief="solid")
        style.configure("TLabel", background="#071013", foreground="#eaf2f5", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#071013", foreground="#83a0a8", font=("Segoe UI", 9))
        style.configure("Title.TLabel", background="#071013", foreground="#eaf2f5", font=("Segoe UI", 22, "bold"))
        style.configure("Panel.TLabel", background="#0e1a1e", foreground="#eaf2f5", font=("Segoe UI", 10))
        style.configure("Small.Panel.TLabel", background="#0e1a1e", foreground="#83a0a8", font=("Segoe UI", 8))
        style.configure("TButton", padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TButton", background="#00d9ff", foreground="#001216")
        style.configure("Danger.TButton", background="#ff4f70", foreground="#ffffff")
        style.configure("TNotebook", background="#071013", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        header = ttk.Frame(self, padding=18)
        header.pack(fill="x")
        ttk.Label(header, text="Servo Firmata Control", style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status, style="Muted.TLabel").pack(side="right")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self.record_tab = ttk.Frame(notebook, padding=14)
        self.sim_tab = ttk.Frame(notebook, padding=14)
        self.arduino_tab = ttk.Frame(notebook, padding=14)
        notebook.add(self.record_tab, text="1. Gravar dataset")
        notebook.add(self.sim_tab, text="2. Executar simulacao")
        notebook.add(self.arduino_tab, text="3. Executar Arduino")

        self._build_record_tab()
        self._build_execution_tab(self.sim_tab, arduino=False)
        self._build_execution_tab(self.arduino_tab, arduino=True)

    def _build_record_tab(self) -> None:
        left = ttk.Frame(self.record_tab)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(self.record_tab)
        right.pack(side="right", fill="y", padx=(14, 0))

        self._build_servo_controls(left)
        self._build_virtual_servos(right, title="Servos virtuais")

        save_panel = ttk.Frame(left, style="Panel.TFrame", padding=14)
        save_panel.pack(fill="x", pady=(14, 0))
        ttk.Label(save_panel, text="Nome da postura", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(save_panel, textvariable=self.posture_name, width=28).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        ttk.Label(save_panel, text="Modo de execucao", style="Panel.TLabel").grid(row=0, column=1, sticky="w", padx=(14, 0))
        mode_box = ttk.Combobox(save_panel, textvariable=self.execution_mode, values=["sequencial", "simultaneo"], state="readonly", width=14)
        mode_box.grid(row=1, column=1, sticky="w", padx=(14, 0), pady=(6, 0))

        ttk.Label(save_panel, text="Ordem", style="Panel.TLabel").grid(row=0, column=2, sticky="w", padx=(14, 0))
        self.order_entry = ttk.Entry(save_panel, width=18)
        self.order_entry.insert(0, "1-2-3-4-5-6")
        self.order_entry.grid(row=1, column=2, sticky="w", padx=(14, 0), pady=(6, 0))

        ttk.Button(save_panel, text="Salvar postura", style="Accent.TButton", command=self.salvar_postura).grid(row=1, column=3, padx=(14, 0), pady=(6, 0))
        save_panel.columnconfigure(0, weight=1)

        vector_panel = ttk.Frame(left, style="Panel.TFrame", padding=14)
        vector_panel.pack(fill="x", pady=(12, 0))
        ttk.Label(vector_panel, text="Vetor gerado", style="Panel.TLabel").pack(anchor="w")
        self.current_vector_text = tk.Text(vector_panel, height=3, bg="#091316", fg="#3bee7a", insertbackground="#3bee7a", relief="flat", wrap="word")
        self.current_vector_text.pack(fill="x", pady=(8, 0))
        self.current_vector_text.insert("1.0", self.gerar_vetor())

    def _build_servo_controls(self, parent: ttk.Frame) -> None:
        grid = ttk.Frame(parent)
        grid.pack(fill="both", expand=True)
        for i, servo in enumerate(self.servos):
            panel = ttk.Frame(grid, style="Panel.TFrame", padding=12)
            row, col = divmod(i, 2)
            panel.grid(row=row, column=col, sticky="nsew", padx=7, pady=7)

            ttk.Label(panel, text=f"M{servo.index} - pino {servo.pin}", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Entry(panel, textvariable=self.name_vars[i], width=18).grid(row=0, column=1, sticky="ew", padx=(8, 0))

            ttk.Label(panel, text="Angulo", style="Small.Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 0))
            ttk.Scale(panel, from_=0, to=180, orient="horizontal", variable=self.angle_vars[i], command=lambda _v, idx=i: self.on_servo_change(idx)).grid(row=2, column=0, columnspan=2, sticky="ew")
            ttk.Label(panel, textvariable=self.angle_vars[i], style="Panel.TLabel").grid(row=2, column=2, padx=(8, 0))

            ttk.Label(panel, text="Velocidade", style="Small.Panel.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 0))
            ttk.Scale(panel, from_=1, to=20, orient="horizontal", variable=self.speed_vars[i], command=lambda _v, idx=i: self.on_servo_change(idx)).grid(row=4, column=0, columnspan=2, sticky="ew")
            ttk.Label(panel, textvariable=self.speed_vars[i], style="Panel.TLabel").grid(row=4, column=2, padx=(8, 0))

            panel.columnconfigure(1, weight=1)

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

    def _build_virtual_servos(self, parent: ttk.Frame, title: str) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text=title, style="Panel.TLabel").pack(anchor="w")
        self.canvas = tk.Canvas(panel, width=430, height=500, bg="#091316", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=(12, 0))

    def _build_execution_tab(self, parent: ttk.Frame, arduino: bool) -> None:
        left = ttk.Frame(parent)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(parent)
        right.pack(side="right", fill="both", expand=True, padx=(14, 0))

        list_panel = ttk.Frame(left, style="Panel.TFrame", padding=14)
        list_panel.pack(fill="both", expand=True)
        ttk.Label(list_panel, text="Posturas salvas", style="Panel.TLabel").pack(anchor="w")
        listbox = tk.Listbox(list_panel, bg="#091316", fg="#eaf2f5", selectbackground="#00d9ff", selectforeground="#001216", relief="flat", height=18)
        listbox.pack(fill="both", expand=True, pady=(10, 0))
        if arduino:
            self.arduino_listbox = listbox
        else:
            self.sim_listbox = listbox
        listbox.bind("<<ListboxSelect>>", lambda _event, lb=listbox: self.on_posture_select(lb))

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Atualizar lista", command=self.refresh_posture_lists).pack(side="left")
        ttk.Button(actions, text="Executar", style="Accent.TButton", command=lambda: self.executar_posicoes(arduino=arduino)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Parar", style="Danger.TButton", command=self.stop_motion.set).pack(side="left", padx=(8, 0))

        if arduino:
            conn = ttk.Frame(left, style="Panel.TFrame", padding=14)
            conn.pack(fill="x", pady=(12, 0))
            ttk.Label(conn, text="Porta serial Arduino", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Entry(conn, textvariable=self.connected_port, width=22).grid(row=1, column=0, sticky="ew", pady=(6, 0))
            ttk.Button(conn, text="Conectar Firmata", command=self.connect_arduino).grid(row=1, column=1, padx=(8, 0), pady=(6, 0))
            ttk.Button(conn, text="Desconectar", command=self.disconnect_arduino).grid(row=1, column=2, padx=(8, 0), pady=(6, 0))
            ttk.Label(conn, text="Ex.: COM3, /dev/ttyACM0 ou /dev/ttyACM1", style="Small.Panel.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        vector_panel = ttk.Frame(right, style="Panel.TFrame", padding=14)
        vector_panel.pack(fill="x")
        ttk.Label(vector_panel, text="Vetor carregado", style="Panel.TLabel").pack(anchor="w")
        ttk.Label(vector_panel, textvariable=self.loaded_vector, style="Small.Panel.TLabel", wraplength=520).pack(anchor="w", pady=(8, 0))

        preview_panel = ttk.Frame(right, style="Panel.TFrame", padding=14)
        preview_panel.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(preview_panel, text="Pre-visualizacao", style="Panel.TLabel").pack(anchor="w")
        canvas = tk.Canvas(preview_panel, width=520, height=420, bg="#091316", highlightthickness=0)
        canvas.pack(fill="both", expand=True, pady=(12, 0))
        if arduino:
            self.arduino_canvas = canvas
        else:
            self.sim_canvas = canvas

    def on_servo_change(self, index: int) -> None:
        self.servos[index].angle = int(self.angle_vars[index].get())
        self.servos[index].speed = int(self.speed_vars[index].get())
        self.servos[index].name = self.name_vars[index].get().strip() or f"Motor {index + 1}"
        self.update_interface()
        self._set_current_vector(self.gerar_vetor())

    def atualizar_interface(self) -> None:
        self.update_interface()

    def update_interface(self) -> None:
        self.draw_servos(self.canvas, self.servos)
        if hasattr(self, "sim_canvas"):
            self.draw_servos(self.sim_canvas, self.servos)
        if hasattr(self, "arduino_canvas"):
            self.draw_servos(self.arduino_canvas, self.servos)

    def draw_servos(self, canvas: tk.Canvas, servos: list[ServoState]) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 360)
        cols = 3
        rows = 2
        cell_w = width / cols
        cell_h = height / rows

        for i, servo in enumerate(servos):
            row, col = divmod(i, cols)
            cx = cell_w * col + cell_w / 2
            cy = cell_h * row + cell_h / 2 + 10
            radius = min(cell_w, cell_h) * 0.28
            angle_rad = math.radians(servo.angle - 90)
            x2 = cx + math.cos(angle_rad) * radius
            y2 = cy + math.sin(angle_rad) * radius

            canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline="#24505a", width=2, fill="#0e1a1e")
            canvas.create_line(cx, cy, x2, y2, fill="#3bee7a", width=7, capstyle="round")
            canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill="#00d9ff", outline="")
            canvas.create_text(cx, cy - radius - 22, text=f"M{servo.index} - {servo.name}", fill="#eaf2f5", font=("Segoe UI", 10, "bold"))
            canvas.create_text(cx, cy + radius + 18, text=f"{servo.angle} deg | V{servo.speed} | D{servo.pin}", fill="#83a0a8", font=("Consolas", 9, "bold"))

    def gerar_vetor(self) -> str:
        return self.current_posture().vector

    def current_posture(self) -> Posture:
        return Posture(
            name=safe_name(self.posture_name.get() or "Postura"),
            servos=[ServoState(i + 1, SERVO_PINS[i], self.name_vars[i].get().strip() or f"Motor {i + 1}", int(self.angle_vars[i].get()), int(self.speed_vars[i].get())) for i in range(SERVO_COUNT)],
            order=parse_order(self.order_entry.get()),
            mode=self.execution_mode.get(),
        )

    def salvar_postura(self) -> None:
        try:
            posture = self.current_posture()
            path = LOG_DIR / f"{posture.name}.json"
            payload = {"vector": posture.vector, "posture": asdict(posture)}
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            self.set_status(f"Postura salva: {path.name}")
            self.refresh_posture_lists()
        except Exception as exc:
            messagebox.showerror("Erro ao salvar", str(exc))

    def carregar_posicoes(self, name: str) -> Posture:
        path = LOG_DIR / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Arquivo de postura ausente: {path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = payload["posture"]
            servos = [ServoState(**item) for item in raw["servos"]]
            return Posture(name=raw["name"], servos=servos, order=list(raw["order"]), mode=raw["mode"])
        except Exception as exc:
            raise ValueError(f"Vetor/postura mal formatado em {path.name}: {exc}") from exc

    def refresh_posture_lists(self) -> None:
        names = sorted(path.stem for path in LOG_DIR.glob("*.json"))
        for attr in ("sim_listbox", "arduino_listbox"):
            if hasattr(self, attr):
                listbox = getattr(self, attr)
                listbox.delete(0, "end")
                for name in names:
                    listbox.insert("end", name)

    def on_posture_select(self, listbox: tk.Listbox) -> None:
        if not listbox.curselection():
            return
        name = listbox.get(listbox.curselection()[0])
        self.selected_posture.set(name)
        try:
            posture = self.carregar_posicoes(name)
            self.loaded_vector.set(posture.vector)
            self.draw_servos(self.sim_canvas if listbox is getattr(self, "sim_listbox", None) else self.arduino_canvas, posture.servos)
        except Exception as exc:
            messagebox.showerror("Erro ao carregar", str(exc))

    def executar_posicoes(self, arduino: bool) -> None:
        source_list = self.arduino_listbox if arduino else self.sim_listbox
        if not source_list.curselection():
            messagebox.showwarning("Selecione uma postura", "Escolha uma postura salva antes de executar.")
            return
        try:
            posture = self.carregar_posicoes(source_list.get(source_list.curselection()[0]))
        except Exception as exc:
            messagebox.showerror("Erro ao carregar", str(exc))
            return

        if arduino and self.board is None:
            messagebox.showerror("Arduino nao conectado", "Conecte o Arduino Uno com Firmata antes de executar.")
            return

        self.stop_motion.clear()
        worker = threading.Thread(target=lambda: self.executar_postura_worker(posture, arduino), daemon=True)
        worker.start()

    def executar_postura_worker(self, posture: Posture, arduino: bool) -> None:
        try:
            self.set_status(f"Executando {posture.name} ({'Arduino' if arduino else 'simulacao'})")
            if posture.mode == "simultaneo":
                self.execute_simultaneous(posture, arduino)
            else:
                self.execute_sequential(posture, arduino)
            self.set_status(f"Execucao concluida: {posture.name}")
        except Exception as exc:
            self.set_status(f"Erro: {exc}")

    def execute_sequential(self, posture: Posture, arduino: bool) -> None:
        current = [servo.angle for servo in self.servos]
        target_by_index = {servo.index: servo for servo in posture.servos}
        for servo_index in posture.order:
            if self.stop_motion.is_set():
                return
            servo = target_by_index[servo_index]
            self.move_one_servo(current, servo, arduino)

    def execute_simultaneous(self, posture: Posture, arduino: bool) -> None:
        current = [servo.angle for servo in self.servos]
        remaining = {servo.index: servo for servo in posture.servos}
        while remaining and not self.stop_motion.is_set():
            for servo_index, servo in list(remaining.items()):
                idx = servo_index - 1
                if current[idx] == servo.angle:
                    remaining.pop(servo_index)
                    continue
                step = 1 if servo.angle > current[idx] else -1
                current[idx] += step
                self.set_servo_angle(idx, current[idx], arduino)
            time.sleep(0.03)

    def move_one_servo(self, current: list[int], servo: ServoState, arduino: bool) -> None:
        idx = servo.index - 1
        delay = max(0.01, 0.12 / max(1, servo.speed))
        while current[idx] != servo.angle and not self.stop_motion.is_set():
            step = 1 if servo.angle > current[idx] else -1
            current[idx] += step
            self.set_servo_angle(idx, current[idx], arduino)
            time.sleep(delay)

    def set_servo_angle(self, idx: int, angle: int, arduino: bool) -> None:
        self.servos[idx].angle = int(angle)
        if arduino:
            self.enviar_para_arduino(idx + 1, int(angle))
        self.after(0, lambda servo_idx=idx, servo_angle=int(angle): self.apply_servo_angle(servo_idx, servo_angle))

    def apply_servo_angle(self, idx: int, angle: int) -> None:
        self.angle_vars[idx].set(angle)
        self.update_interface()

    def simular_movimento(self) -> None:
        self.executar_posicoes(arduino=False)

    def enviar_para_arduino(self, servo_index: int, angle: int) -> None:
        if self.board is None:
            raise RuntimeError("Arduino nao conectado.")
        pin = SERVO_PINS[servo_index - 1]
        self.servo_pins[pin].write(angle)

    def connect_arduino(self) -> None:
        if Arduino is None:
            messagebox.showerror("Dependencia ausente", "Instale pyfirmata: pip install pyfirmata")
            return
        port = self.connected_port.get().strip()
        if not port:
            messagebox.showerror("Porta invalida", "Informe a porta serial do Arduino.")
            return
        try:
            self.board = Arduino(port)
            self.servo_pins = {}
            for pin in SERVO_PINS:
                self.board.digital[pin].mode = SERVO
                self.servo_pins[pin] = self.board.digital[pin]
                self.board.digital[pin].write(0)
            self.set_status(f"Arduino conectado em {port}")
        except Exception as exc:
            self.board = None
            messagebox.showerror("Falha ao conectar Arduino", str(exc))

    def disconnect_arduino(self) -> None:
        if self.board is not None:
            self.board.exit()
        self.board = None
        self.servo_pins = {}
        self.set_status("Arduino desconectado.")

    def set_status(self, text: str) -> None:
        self.after(0, self.status.set, text)

    def _set_current_vector(self, vector: str) -> None:
        if hasattr(self, "current_vector_text"):
            self.current_vector_text.delete("1.0", "end")
            self.current_vector_text.insert("1.0", vector)


def parse_order(text: str) -> list[int]:
    numbers = [int(item) for item in re.findall(r"[1-6]", text)]
    if not numbers:
        return [1, 2, 3, 4, 5, 6]
    seen = []
    for number in numbers:
        if number not in seen:
            seen.append(number)
    return seen


def safe_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    return cleaned or "Postura"


def main() -> None:
    app = ServoControlApp()
    app.mainloop()


if __name__ == "__main__":
    main()
