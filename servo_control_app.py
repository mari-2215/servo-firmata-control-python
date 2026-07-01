from __future__ import annotations

import csv
import json
import math
import re
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from pyfirmata import Arduino, SERVO
except ImportError:  # The app still works in simulation mode without pyfirmata.
    Arduino = None
    SERVO = None


APP_TITLE = "Servo Firmata Control"
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR = BASE_DIR / "exports"
SERVO_PINS = [3, 5, 6, 9, 10, 11]
SERVO_COUNT = 6
MAX_SAFE_JUMP = 110
HIGH_SPEED = 16


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
        self.geometry("1420x860")
        self.minsize(1180, 740)

        LOG_DIR.mkdir(exist_ok=True)
        EXPORT_DIR.mkdir(exist_ok=True)
        self.board = None
        self.servo_pins = {}
        self.connected_port = tk.StringVar(value="")
        self.status = tk.StringVar(value="Simulacao pronta. Todos os servos em zero.")
        self.posture_name = tk.StringVar(value="Postura_1")
        self.execution_mode = tk.StringVar(value="sequencial")
        self.selected_posture = tk.StringVar(value="")
        self.loaded_vector = tk.StringVar(value="Nenhuma postura carregada.")
        self.global_speed = tk.DoubleVar(value=1.0)
        self.live_control = tk.BooleanVar(value=False)
        self.live_state = tk.StringVar(value="Live off")
        self.board_state = tk.StringVar(value="Arduino desconectado")
        self.last_action = tk.StringVar(value="Sem envio ainda")
        self.last_servo = tk.StringVar(value="Nenhum servo")
        self.last_timestamp = tk.StringVar(value="-")
        self.safety_text = tk.StringVar(value="Validacao: aguardando postura.")
        self.stop_motion = threading.Event()
        self.motion_lock = threading.Lock()

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
        style.configure("Live.Panel.TLabel", background="#0e1a1e", foreground="#3bee7a", font=("Consolas", 10, "bold"))
        style.configure("TButton", padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TButton", background="#00d9ff", foreground="#001216")
        style.configure("Danger.TButton", background="#ff4f70", foreground="#ffffff")
        style.configure("TNotebook", background="#071013", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 10, "bold"))
        style.configure("Horizontal.TScale", background="#0e1a1e")

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
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self.update_interface())

        ttk.Label(save_panel, text="Ordem", style="Panel.TLabel").grid(row=0, column=2, sticky="w", padx=(14, 0))
        self.order_entry = ttk.Entry(save_panel, width=18)
        self.order_entry.insert(0, "1-2-3-4-5-6")
        self.order_entry.grid(row=1, column=2, sticky="w", padx=(14, 0), pady=(6, 0))
        self.order_entry.bind("<KeyRelease>", lambda _event: self.update_interface())

        ttk.Button(save_panel, text="Salvar postura", style="Accent.TButton", command=self.salvar_postura).grid(row=1, column=3, padx=(14, 0), pady=(6, 0))
        ttk.Button(save_panel, text="Exportar dataset", command=self.export_dataset).grid(row=1, column=4, padx=(8, 0), pady=(6, 0))
        save_panel.columnconfigure(0, weight=1)

        vector_panel = ttk.Frame(left, style="Panel.TFrame", padding=14)
        vector_panel.pack(fill="x", pady=(12, 0))
        ttk.Label(vector_panel, text="Vetor gerado", style="Panel.TLabel").pack(anchor="w")
        self.current_vector_text = tk.Text(vector_panel, height=3, bg="#091316", fg="#3bee7a", insertbackground="#3bee7a", relief="flat", wrap="word")
        self.current_vector_text.pack(fill="x", pady=(8, 0))
        self.current_vector_text.insert("1.0", self.gerar_vetor())

        self._build_timeline_panel(left, "Timeline da postura atual", "record_timeline")
        self._build_graph_panel(left, "Grafico de angulos", "record_graph")

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
        listbox = tk.Listbox(list_panel, bg="#091316", fg="#eaf2f5", selectbackground="#00d9ff", selectforeground="#001216", relief="flat", height=14)
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
        ttk.Button(actions, text="Coreografia", command=lambda: self.execute_showcase(arduino=arduino)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Parar", style="Danger.TButton", command=self.stop_motion.set).pack(side="left", padx=(8, 0))

        controls = ttk.Frame(left, style="Panel.TFrame", padding=14)
        controls.pack(fill="x", pady=(12, 0))
        ttk.Label(controls, text="Playback global", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        speed_box = ttk.Combobox(controls, textvariable=self.global_speed, values=[0.5, 1.0, 1.5, 2.0], state="readonly", width=8)
        speed_box.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(controls, text="multiplica a velocidade sem alterar o dataset", style="Small.Panel.TLabel").grid(row=1, column=1, sticky="w", padx=(12, 0))

        if arduino:
            conn = ttk.Frame(left, style="Panel.TFrame", padding=14)
            conn.pack(fill="x", pady=(12, 0))
            ttk.Label(conn, text="Porta serial Arduino", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Entry(conn, textvariable=self.connected_port, width=22).grid(row=1, column=0, sticky="ew", pady=(6, 0))
            ttk.Button(conn, text="Conectar Firmata", command=self.connect_arduino).grid(row=1, column=1, padx=(8, 0), pady=(6, 0))
            ttk.Button(conn, text="Desconectar", command=self.disconnect_arduino).grid(row=1, column=2, padx=(8, 0), pady=(6, 0))
            ttk.Checkbutton(conn, text="Live control", variable=self.live_control, command=self.update_live_state).grid(row=2, column=0, sticky="w", pady=(8, 0))
            ttk.Label(conn, text="Ex.: COM3, /dev/ttyACM0 ou /dev/ttyACM1", style="Small.Panel.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

            live = ttk.Frame(left, style="Panel.TFrame", padding=14)
            live.pack(fill="x", pady=(12, 0))
            for row, (label, var) in enumerate(
                [
                    ("Conexao", self.board_state),
                    ("Live", self.live_state),
                    ("Ultima acao", self.last_action),
                    ("Ultimo servo", self.last_servo),
                    ("Horario", self.last_timestamp),
                ]
            ):
                ttk.Label(live, text=label, style="Small.Panel.TLabel").grid(row=row, column=0, sticky="w", pady=2)
                ttk.Label(live, textvariable=var, style="Live.Panel.TLabel").grid(row=row, column=1, sticky="w", padx=(12, 0), pady=2)

        vector_panel = ttk.Frame(right, style="Panel.TFrame", padding=14)
        vector_panel.pack(fill="x")
        ttk.Label(vector_panel, text="Vetor carregado", style="Panel.TLabel").pack(anchor="w")
        ttk.Label(vector_panel, textvariable=self.loaded_vector, style="Small.Panel.TLabel", wraplength=560).pack(anchor="w", pady=(8, 0))
        ttk.Label(vector_panel, textvariable=self.safety_text, style="Small.Panel.TLabel", wraplength=560).pack(anchor="w", pady=(8, 0))

        preview_panel = ttk.Frame(right, style="Panel.TFrame", padding=14)
        preview_panel.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(preview_panel, text="Pre-visualizacao", style="Panel.TLabel").pack(anchor="w")
        canvas = tk.Canvas(preview_panel, width=560, height=340, bg="#091316", highlightthickness=0)
        canvas.pack(fill="both", expand=True, pady=(12, 0))
        if arduino:
            self.arduino_canvas = canvas
        else:
            self.sim_canvas = canvas

        self._build_timeline_panel(right, "Timeline da execucao", "arduino_timeline" if arduino else "sim_timeline")
        self._build_graph_panel(right, "Perfil angular", "arduino_graph" if arduino else "sim_graph")

    def _build_timeline_panel(self, parent: ttk.Frame, title: str, attr_name: str) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.pack(fill="x", pady=(12, 0))
        ttk.Label(panel, text=title, style="Panel.TLabel").pack(anchor="w")
        canvas = tk.Canvas(panel, height=116, bg="#091316", highlightthickness=0)
        canvas.pack(fill="x", pady=(8, 0))
        setattr(self, attr_name, canvas)

    def _build_graph_panel(self, parent: ttk.Frame, title: str, attr_name: str) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.pack(fill="x", pady=(12, 0))
        ttk.Label(panel, text=title, style="Panel.TLabel").pack(anchor="w")
        canvas = tk.Canvas(panel, height=148, bg="#091316", highlightthickness=0)
        canvas.pack(fill="x", pady=(8, 0))
        setattr(self, attr_name, canvas)

    def on_servo_change(self, index: int) -> None:
        self.servos[index].angle = int(self.angle_vars[index].get())
        self.servos[index].speed = int(self.speed_vars[index].get())
        self.servos[index].name = self.name_vars[index].get().strip() or f"Motor {index + 1}"
        self.update_interface()
        self._set_current_vector(self.gerar_vetor())
        if self.live_control.get() and self.board is not None:
            try:
                self.enviar_para_arduino(index + 1, self.servos[index].angle)
                self.update_live_panel("Live slider", index + 1, self.servos[index].angle)
            except Exception as exc:
                self.set_status(f"Live control falhou: {exc}")

    def atualizar_interface(self) -> None:
        self.update_interface()

    def update_interface(self) -> None:
        posture = self.current_posture()
        self.draw_servos(self.canvas, self.servos)
        self.draw_timeline_if_present("record_timeline", posture)
        self.draw_graph_if_present("record_graph", posture)
        if hasattr(self, "sim_canvas"):
            self.draw_servos(self.sim_canvas, self.servos)
            self.draw_timeline_if_present("sim_timeline", posture)
            self.draw_graph_if_present("sim_graph", posture)
        if hasattr(self, "arduino_canvas"):
            self.draw_servos(self.arduino_canvas, self.servos)
            self.draw_timeline_if_present("arduino_timeline", posture)
            self.draw_graph_if_present("arduino_graph", posture)

    def draw_servos(self, canvas: tk.Canvas, servos: list[ServoState]) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 320)
        cols = 3
        rows = 2
        cell_w = width / cols
        cell_h = height / rows

        for i, servo in enumerate(servos):
            row, col = divmod(i, cols)
            cx = cell_w * col + cell_w / 2
            cy = cell_h * row + cell_h / 2 + 8
            radius = min(cell_w, cell_h) * 0.26
            angle_rad = math.radians(servo.angle - 90)
            x2 = cx + math.cos(angle_rad) * radius
            y2 = cy + math.sin(angle_rad) * radius

            canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline="#24505a", width=2, fill="#0e1a1e")
            canvas.create_line(cx, cy, x2, y2, fill="#3bee7a", width=7, capstyle="round")
            canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill="#00d9ff", outline="")
            canvas.create_text(cx, cy - radius - 20, text=f"M{servo.index} - {servo.name}", fill="#eaf2f5", font=("Segoe UI", 10, "bold"))
            canvas.create_text(cx, cy + radius + 18, text=f"{servo.angle} deg | V{servo.speed} | D{servo.pin}", fill="#83a0a8", font=("Consolas", 9, "bold"))

    def draw_timeline_if_present(self, attr_name: str, posture: Posture) -> None:
        if hasattr(self, attr_name):
            self.draw_timeline(getattr(self, attr_name), posture)

    def draw_timeline(self, canvas: tk.Canvas, posture: Posture) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 116)
        left = 54
        right = width - 18
        y = 24
        lane_gap = 14
        durations = self.estimate_durations(posture)
        total = sum(durations.values()) if posture.mode == "sequencial" else max(durations.values(), default=1)
        total = max(total, 0.1)
        cursor = left

        canvas.create_text(12, 12, text=f"{total:.1f}s", anchor="w", fill="#83a0a8", font=("Consolas", 9, "bold"))
        for servo_index in posture.order:
            servo = next((item for item in posture.servos if item.index == servo_index), None)
            if servo is None:
                continue
            if posture.mode == "sequencial":
                bar_w = max(22, (right - left) * durations[servo.index] / total)
                x1, x2 = cursor, min(right, cursor + bar_w)
                cursor = x2
            else:
                x1 = left
                x2 = left + max(22, (right - left) * durations[servo.index] / total)
            lane_y = y + (servo.index - 1) * lane_gap
            color = "#00d9ff" if servo.index % 2 else "#3bee7a"
            canvas.create_text(12, lane_y + 5, text=f"M{servo.index}", anchor="w", fill="#eaf2f5", font=("Consolas", 9, "bold"))
            canvas.create_rectangle(left, lane_y, right, lane_y + 9, outline="#19363d", fill="#0e1a1e")
            canvas.create_rectangle(x1, lane_y, x2, lane_y + 9, outline="", fill=color)
            canvas.create_text(x2 + 4, lane_y + 5, text=f"{durations[servo.index]:.1f}s", anchor="w", fill="#83a0a8", font=("Consolas", 8))

    def draw_graph_if_present(self, attr_name: str, posture: Posture) -> None:
        if hasattr(self, attr_name):
            self.draw_angle_graph(getattr(self, attr_name), posture)

    def draw_angle_graph(self, canvas: tk.Canvas, posture: Posture) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 148)
        left, right = 38, width - 20
        top, bottom = 18, height - 28
        canvas.create_line(left, bottom, right, bottom, fill="#24505a")
        canvas.create_line(left, top, left, bottom, fill="#24505a")
        for angle in (0, 90, 180):
            y = bottom - (bottom - top) * angle / 180
            canvas.create_line(left, y, right, y, fill="#10252a")
            canvas.create_text(10, y, text=str(angle), anchor="w", fill="#83a0a8", font=("Consolas", 8))

        bar_gap = 10
        bar_w = (right - left - bar_gap * (SERVO_COUNT - 1)) / SERVO_COUNT
        for i, servo in enumerate(posture.servos):
            x1 = left + i * (bar_w + bar_gap)
            x2 = x1 + bar_w
            y1 = bottom - (bottom - top) * servo.angle / 180
            color = "#ff4f70" if self.is_risky_servo(servo) else "#00d9ff"
            canvas.create_rectangle(x1, y1, x2, bottom, fill=color, outline="")
            canvas.create_text((x1 + x2) / 2, bottom + 14, text=f"M{servo.index}", fill="#eaf2f5", font=("Consolas", 9, "bold"))
            canvas.create_text((x1 + x2) / 2, y1 - 8, text=str(servo.angle), fill="#eaf2f5", font=("Consolas", 8))

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
            payload = {
                "vector": posture.vector,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "posture": asdict(posture),
            }
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
            self.safety_text.set(self.safety_report(posture))
            preview = self.sim_canvas if listbox is getattr(self, "sim_listbox", None) else self.arduino_canvas
            self.draw_servos(preview, posture.servos)
            self.draw_selected_posture_aux(posture, arduino=listbox is getattr(self, "arduino_listbox", None))
        except Exception as exc:
            messagebox.showerror("Erro ao carregar", str(exc))

    def draw_selected_posture_aux(self, posture: Posture, arduino: bool) -> None:
        prefix = "arduino" if arduino else "sim"
        self.draw_timeline_if_present(f"{prefix}_timeline", posture)
        self.draw_graph_if_present(f"{prefix}_graph", posture)

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

        if not self.confirm_execution(posture, arduino):
            return

        self.stop_motion.clear()
        worker = threading.Thread(target=lambda: self.executar_postura_worker(posture, arduino), daemon=True)
        worker.start()

    def confirm_execution(self, posture: Posture, arduino: bool) -> bool:
        if arduino and self.board is None:
            messagebox.showerror("Arduino nao conectado", "Conecte o Arduino Uno com Firmata antes de executar.")
            return False
        warnings = self.safety_warnings(posture)
        self.safety_text.set(self.safety_report(posture))
        if warnings:
            return messagebox.askyesno("Validacao de seguranca", "\n".join(warnings) + "\n\nExecutar mesmo assim?")
        return True

    def executar_postura_worker(self, posture: Posture, arduino: bool) -> None:
        if not self.motion_lock.acquire(blocking=False):
            self.set_status("Ja existe uma execucao em andamento.")
            return
        try:
            self.set_status(f"Executando {posture.name} ({'Arduino' if arduino else 'simulacao'})")
            self.loaded_vector.set(posture.vector)
            if posture.mode == "simultaneo":
                self.execute_simultaneous(posture, arduino)
            else:
                self.execute_sequential(posture, arduino)
            self.set_status(f"Execucao concluida: {posture.name}")
        except Exception as exc:
            self.set_status(f"Erro: {exc}")
        finally:
            self.motion_lock.release()

    def execute_sequential(self, posture: Posture, arduino: bool) -> None:
        current = [servo.angle for servo in self.servos]
        target_by_index = {servo.index: servo for servo in posture.servos}
        for servo_index in posture.order:
            if self.stop_motion.is_set():
                return
            servo = target_by_index.get(servo_index)
            if servo is not None:
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
            time.sleep(max(0.008, 0.03 / self.get_global_speed()))

    def move_one_servo(self, current: list[int], servo: ServoState, arduino: bool) -> None:
        idx = servo.index - 1
        delay = max(0.006, 0.12 / max(1, servo.speed) / self.get_global_speed())
        while current[idx] != servo.angle and not self.stop_motion.is_set():
            step = 1 if servo.angle > current[idx] else -1
            current[idx] += step
            self.set_servo_angle(idx, current[idx], arduino)
            time.sleep(delay)

    def set_servo_angle(self, idx: int, angle: int, arduino: bool) -> None:
        self.servos[idx].angle = int(angle)
        if arduino:
            self.enviar_para_arduino(idx + 1, int(angle))
            self.update_live_panel("Execucao Arduino", idx + 1, int(angle))
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

    def execute_showcase(self, arduino: bool) -> None:
        names = sorted(path.stem for path in LOG_DIR.glob("*.json"))
        if not names:
            messagebox.showwarning("Dataset vazio", "Salve pelo menos uma postura antes da coreografia.")
            return
        if arduino and self.board is None:
            messagebox.showerror("Arduino nao conectado", "Conecte o Arduino Uno com Firmata antes de executar.")
            return
        self.stop_motion.clear()
        worker = threading.Thread(target=lambda: self.showcase_worker(names, arduino), daemon=True)
        worker.start()

    def showcase_worker(self, names: list[str], arduino: bool) -> None:
        if not self.motion_lock.acquire(blocking=False):
            self.set_status("Ja existe uma execucao em andamento.")
            return
        try:
            for name in names:
                if self.stop_motion.is_set():
                    break
                posture = self.carregar_posicoes(name)
                self.set_status(f"Coreografia: {name}")
                self.loaded_vector.set(posture.vector)
                self.safety_text.set(self.safety_report(posture))
                if posture.mode == "simultaneo":
                    self.execute_simultaneous(posture, arduino)
                else:
                    self.execute_sequential(posture, arduino)
                time.sleep(0.35)
            self.set_status("Coreografia finalizada.")
        except Exception as exc:
            self.set_status(f"Erro na coreografia: {exc}")
        finally:
            self.motion_lock.release()

    def export_dataset(self) -> None:
        paths = sorted(LOG_DIR.glob("*.json"))
        if not paths:
            messagebox.showwarning("Dataset vazio", "Nao ha posturas salvas para exportar.")
            return
        default = EXPORT_DIR / f"dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        target = filedialog.asksaveasfilename(
            title="Exportar dataset",
            defaultextension=".csv",
            initialfile=default.name,
            initialdir=str(EXPORT_DIR),
            filetypes=[("CSV", "*.csv")],
        )
        if not target:
            return
        try:
            with Path(target).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["postura", "modo", "ordem", "vetor", "motor", "pino", "nome", "angulo", "velocidade"])
                for path in paths:
                    posture = self.carregar_posicoes(path.stem)
                    for servo in posture.servos:
                        writer.writerow([posture.name, posture.mode, "-".join(map(str, posture.order)), posture.vector, servo.index, servo.pin, servo.name, servo.angle, servo.speed])
            self.set_status(f"Dataset exportado: {Path(target).name}")
        except Exception as exc:
            messagebox.showerror("Falha ao exportar", str(exc))

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
            self.board_state.set(f"Conectado em {port}")
            self.update_live_state()
            self.set_status(f"Arduino conectado em {port}")
        except Exception as exc:
            self.board = None
            self.board_state.set("Falha de conexao")
            messagebox.showerror("Falha ao conectar Arduino", str(exc))

    def disconnect_arduino(self) -> None:
        if self.board is not None:
            self.board.exit()
        self.board = None
        self.servo_pins = {}
        self.board_state.set("Arduino desconectado")
        self.update_live_state()
        self.set_status("Arduino desconectado.")

    def update_live_state(self) -> None:
        state = "Live on" if self.live_control.get() and self.board is not None else "Live off"
        self.live_state.set(state)

    def update_live_panel(self, action: str, servo_index: int, angle: int) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.after(0, self.last_action.set, f"{action}: {angle} deg")
        self.after(0, self.last_servo.set, f"M{servo_index} / D{SERVO_PINS[servo_index - 1]}")
        self.after(0, self.last_timestamp.set, now)

    def estimate_durations(self, posture: Posture) -> dict[int, float]:
        durations = {}
        current = {servo.index: self.servos[servo.index - 1].angle for servo in posture.servos}
        for servo in posture.servos:
            delta = abs(servo.angle - current[servo.index])
            speed = max(1, servo.speed) * self.get_global_speed()
            durations[servo.index] = max(0.1, delta * (0.12 / speed))
        return durations

    def safety_warnings(self, posture: Posture) -> list[str]:
        warnings = []
        current = {servo.index: self.servos[servo.index - 1].angle for servo in posture.servos}
        for servo in posture.servos:
            delta = abs(servo.angle - current[servo.index])
            if delta >= MAX_SAFE_JUMP and servo.speed >= HIGH_SPEED:
                warnings.append(f"M{servo.index}: salto de {delta} graus com velocidade {servo.speed}.")
        return warnings

    def safety_report(self, posture: Posture) -> str:
        warnings = self.safety_warnings(posture)
        if not warnings:
            return "Validacao: movimento dentro dos limites configurados."
        return "Validacao: atencao - " + " | ".join(warnings)

    def is_risky_servo(self, servo: ServoState) -> bool:
        current_angle = self.servos[servo.index - 1].angle
        return abs(servo.angle - current_angle) >= MAX_SAFE_JUMP and servo.speed >= HIGH_SPEED

    def get_global_speed(self) -> float:
        try:
            return max(0.5, float(self.global_speed.get()))
        except (tk.TclError, ValueError):
            return 1.0

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
