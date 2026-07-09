from __future__ import annotations

import asyncio
import csv
import json
import math
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from pyfirmata import Arduino, SERVO, util
except ImportError:  # The API keeps simulation mode alive without Arduino deps.
    Arduino = None
    SERVO = None
    util = None

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR = BASE_DIR / "exports"
WEB_DIST = BASE_DIR / "web" / "dist"
SERVO_PINS = [3, 5, 6, 9, 10, 11]
SERVO_COUNT = 6
MAX_SAFE_JUMP = 110
HIGH_SPEED = 16
COMMON_SERIAL_PORTS = [
    "/dev/ttyACM0",
    "/dev/ttyACM1",
    "/dev/ttyACM2",
    "/dev/ttyUSB0",
    "/dev/ttyUSB1",
    "/dev/ttyUSB2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
]


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


class ServoPayload(BaseModel):
    index: int = Field(ge=1, le=6)
    pin: int
    name: str
    angle: int = Field(ge=0, le=180)
    speed: int = Field(ge=1, le=20)


class PosturePayload(BaseModel):
    name: str
    servos: list[ServoPayload]
    order: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6])
    mode: str = "sequencial"


class ConnectPayload(BaseModel):
    port: str = ""


class ExecutePayload(BaseModel):
    name: str
    arduino: bool = False
    global_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    force: bool = False


class ShowcasePayload(BaseModel):
    arduino: bool = False
    global_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    force: bool = False


class LivePayload(BaseModel):
    servo_index: int = Field(ge=1, le=6)
    angle: int = Field(ge=0, le=180)


class ServoManager:
    def __init__(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        EXPORT_DIR.mkdir(exist_ok=True)
        self.servos = [ServoState(i + 1, SERVO_PINS[i], f"Motor {i + 1}") for i in range(SERVO_COUNT)]
        self.board = None
        self.iterator = None
        self.servo_pins: dict[int, Any] = {}
        self.connected_port = ""
        self.status = "API pronta em modo simulacao."
        self.last_action = "Sem envio ainda"
        self.last_servo = "Nenhum servo"
        self.last_timestamp = "-"
        self.stop_motion = threading.Event()
        self.motion_lock = threading.Lock()
        self.events: list[dict[str, Any]] = []
        self.event_id = 0
        self.lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "servos": [asdict(servo) for servo in self.servos],
                "connected": self.board is not None,
                "port": self.connected_port,
                "status": self.status,
                "lastAction": self.last_action,
                "lastServo": self.last_servo,
                "lastTimestamp": self.last_timestamp,
                "postures": self.list_postures(),
                "ports": list_serial_ports(),
            }

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        with self.lock:
            self.event_id += 1
            event = {
                "id": self.event_id,
                "type": event_type,
                "payload": payload or {},
                "state": self.snapshot_unlocked(),
            }
            self.events.append(event)
            self.events = self.events[-200:]

    def snapshot_unlocked(self) -> dict[str, Any]:
        return {
            "servos": [asdict(servo) for servo in self.servos],
            "connected": self.board is not None,
            "port": self.connected_port,
            "status": self.status,
            "lastAction": self.last_action,
            "lastServo": self.last_servo,
            "lastTimestamp": self.last_timestamp,
            "postures": self.list_postures(),
            "ports": list_serial_ports(),
        }

    def get_events_after(self, last_id: int) -> list[dict[str, Any]]:
        with self.lock:
            return [event for event in self.events if event["id"] > last_id]

    def list_postures(self) -> list[str]:
        return sorted(path.stem for path in LOG_DIR.glob("*.json"))

    def save_posture(self, payload: PosturePayload) -> Posture:
        posture = Posture(
            name=safe_name(payload.name),
            servos=[ServoState(item.index, SERVO_PINS[item.index - 1], item.name, item.angle, item.speed) for item in payload.servos],
            order=normalize_order(payload.order),
            mode=payload.mode if payload.mode in {"sequencial", "simultaneo"} else "sequencial",
        )
        data = {
            "vector": posture.vector,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "posture": asdict(posture),
        }
        (LOG_DIR / f"{posture.name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.status = f"Postura salva: {posture.name}"
        self.emit("posture_saved", {"name": posture.name, "vector": posture.vector})
        return posture

    def load_posture(self, name: str) -> Posture:
        path = LOG_DIR / f"{safe_name(name)}.json"
        if not path.exists():
            raise FileNotFoundError(f"Arquivo de postura ausente: {path.name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload["posture"]
        servos = [ServoState(**item) for item in raw["servos"]]
        return Posture(raw["name"], servos, list(raw["order"]), raw["mode"])

    def connect(self, port: str = "") -> None:
        if Arduino is None:
            raise RuntimeError("Instale pyfirmata para conectar ao Arduino.")
        candidates = candidate_ports(port)
        if not candidates:
            raise RuntimeError("Nenhuma porta serial detectada e nenhum candidato conhecido disponivel.")
        self.disconnect(silent=True)
        errors = []
        for candidate in candidates:
            board = None
            try:
                board = Arduino(candidate)
                time.sleep(2.0)  # Arduino Uno resets when the serial port opens.
                iterator = util.Iterator(board) if util is not None else None
                if iterator is not None:
                    iterator.start()
                servo_pins = {}
                for pin in SERVO_PINS:
                    board.digital[pin].mode = SERVO
                    servo_pins[pin] = board.digital[pin]
                    board.digital[pin].write(0)
                    time.sleep(0.03)
                self.board = board
                self.iterator = iterator
                self.servo_pins = servo_pins
                self.connected_port = candidate
                self.status = f"Arduino conectado em {candidate}"
                self.emit("connected", {"port": candidate, "attempts": candidates})
                return
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
                if board is not None:
                    try:
                        board.exit()
                    except Exception:
                        pass
                self.board = None
                self.iterator = None
                self.servo_pins = {}
                self.connected_port = ""
        detected = ", ".join(item["device"] for item in list_serial_ports()) or "nenhuma porta listada pelo sistema"
        attempted = ", ".join(candidates)
        raise RuntimeError(
            "Nao consegui conectar ao Arduino. "
            f"Portas detectadas: {detected}. "
            f"Tentativas: {attempted}. "
            "Feche Serial Monitor/Arduino IDE e confirme StandardFirmata. "
            f"Erros: {' | '.join(errors[-6:])}"
        )

    def disconnect(self, silent: bool = False) -> None:
        if self.board is not None:
            self.board.exit()
        self.board = None
        self.iterator = None
        self.servo_pins = {}
        self.connected_port = ""
        self.status = "Arduino desconectado."
        if not silent:
            self.emit("disconnected")

    def execute(self, payload: ExecutePayload) -> dict[str, Any]:
        posture = self.load_posture(payload.name)
        warnings = self.safety_warnings(posture)
        if payload.arduino and self.board is None:
            raise RuntimeError("Arduino nao conectado.")
        if warnings and not payload.force:
            return {"accepted": False, "warnings": warnings, "vector": posture.vector}
        self.stop_motion.clear()
        worker = threading.Thread(target=self.execute_worker, args=(posture, payload.arduino, payload.global_speed), daemon=True)
        worker.start()
        return {"accepted": True, "warnings": warnings, "vector": posture.vector}

    def showcase(self, payload: ShowcasePayload) -> dict[str, Any]:
        names = self.list_postures()
        if not names:
            raise RuntimeError("Nao ha posturas salvas.")
        if payload.arduino and self.board is None:
            raise RuntimeError("Arduino nao conectado.")
        blocked = []
        if not payload.force:
            for name in names:
                blocked.extend(self.safety_warnings(self.load_posture(name)))
        if blocked:
            return {"accepted": False, "warnings": blocked}
        self.stop_motion.clear()
        worker = threading.Thread(target=self.showcase_worker, args=(names, payload.arduino, payload.global_speed), daemon=True)
        worker.start()
        return {"accepted": True, "warnings": []}

    def showcase_worker(self, names: list[str], arduino: bool, global_speed: float) -> None:
        if not self.motion_lock.acquire(blocking=False):
            self.status = "Ja existe uma execucao em andamento."
            self.emit("busy")
            return
        try:
            self.status = "Coreografia iniciada."
            self.emit("showcase_started", {"count": len(names), "arduino": arduino})
            for name in names:
                if self.stop_motion.is_set():
                    break
                posture = self.load_posture(name)
                self.status = f"Coreografia: {posture.name}"
                self.emit("execution_started", {"name": posture.name, "arduino": arduino, "vector": posture.vector})
                if posture.mode == "simultaneo":
                    self.execute_simultaneous(posture, arduino, global_speed)
                else:
                    self.execute_sequential(posture, arduino, global_speed)
                self.emit("execution_finished", {"name": posture.name})
                time.sleep(0.35)
            self.status = "Coreografia finalizada."
            self.emit("showcase_finished")
        except Exception as exc:
            self.status = f"Erro na coreografia: {exc}"
            self.emit("error", {"message": str(exc)})
        finally:
            self.motion_lock.release()

    def execute_worker(self, posture: Posture, arduino: bool, global_speed: float) -> None:
        if not self.motion_lock.acquire(blocking=False):
            self.status = "Ja existe uma execucao em andamento."
            self.emit("busy")
            return
        try:
            self.status = f"Executando {posture.name} ({'Arduino' if arduino else 'simulacao'})"
            self.emit("execution_started", {"name": posture.name, "arduino": arduino, "vector": posture.vector})
            if posture.mode == "simultaneo":
                self.execute_simultaneous(posture, arduino, global_speed)
            else:
                self.execute_sequential(posture, arduino, global_speed)
            self.status = f"Execucao concluida: {posture.name}"
            self.emit("execution_finished", {"name": posture.name})
        except Exception as exc:
            self.status = f"Erro: {exc}"
            self.emit("error", {"message": str(exc)})
        finally:
            self.motion_lock.release()

    def execute_sequential(self, posture: Posture, arduino: bool, global_speed: float) -> None:
        current = [servo.angle for servo in self.servos]
        targets = {servo.index: servo for servo in posture.servos}
        for servo_index in posture.order:
            if self.stop_motion.is_set():
                return
            servo = targets.get(servo_index)
            if servo is not None:
                self.move_one_servo(current, servo, arduino, global_speed)

    def execute_simultaneous(self, posture: Posture, arduino: bool, global_speed: float) -> None:
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
            time.sleep(max(0.008, 0.03 / global_speed))

    def move_one_servo(self, current: list[int], servo: ServoState, arduino: bool, global_speed: float) -> None:
        idx = servo.index - 1
        delay = max(0.006, 0.12 / max(1, servo.speed) / global_speed)
        while current[idx] != servo.angle and not self.stop_motion.is_set():
            step = 1 if servo.angle > current[idx] else -1
            current[idx] += step
            self.set_servo_angle(idx, current[idx], arduino)
            time.sleep(delay)

    def set_servo_angle(self, idx: int, angle: int, arduino: bool) -> None:
        with self.lock:
            self.servos[idx].angle = int(angle)
            servo_index = idx + 1
            self.last_action = f"{'Arduino' if arduino else 'Simulacao'}: {angle} deg"
            self.last_servo = f"M{servo_index} / D{SERVO_PINS[idx]}"
            self.last_timestamp = datetime.now().strftime("%H:%M:%S")
        if arduino:
            self.send_to_arduino(servo_index, angle)
        self.emit("servo_update", {"servoIndex": servo_index, "angle": angle, "arduino": arduino})

    def send_to_arduino(self, servo_index: int, angle: int) -> None:
        if self.board is None:
            raise RuntimeError("Arduino nao conectado.")
        pin = SERVO_PINS[servo_index - 1]
        self.servo_pins[pin].write(angle)

    def live(self, payload: LivePayload) -> None:
        self.set_servo_angle(payload.servo_index - 1, payload.angle, arduino=True)

    def stop(self) -> None:
        self.stop_motion.set()
        self.status = "Execucao interrompida."
        self.emit("stopped")

    def export_dataset(self) -> Path:
        target = EXPORT_DIR / f"dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["postura", "modo", "ordem", "vetor", "motor", "pino", "nome", "angulo", "velocidade"])
            for name in self.list_postures():
                posture = self.load_posture(name)
                for servo in posture.servos:
                    writer.writerow([posture.name, posture.mode, "-".join(map(str, posture.order)), posture.vector, servo.index, servo.pin, servo.name, servo.angle, servo.speed])
        self.status = f"Dataset exportado: {target.name}"
        self.emit("dataset_exported", {"file": target.name})
        return target

    def safety_warnings(self, posture: Posture) -> list[str]:
        warnings = []
        current = {servo.index: self.servos[servo.index - 1].angle for servo in posture.servos}
        for servo in posture.servos:
            delta = abs(servo.angle - current[servo.index])
            if delta >= MAX_SAFE_JUMP and servo.speed >= HIGH_SPEED:
                warnings.append(f"M{servo.index}: salto de {delta} graus com velocidade {servo.speed}.")
        return warnings

    def estimate(self, posture: Posture, global_speed: float = 1.0) -> dict[str, Any]:
        durations = {}
        for servo in posture.servos:
            current_angle = self.servos[servo.index - 1].angle
            delta = abs(servo.angle - current_angle)
            speed = max(1, servo.speed) * global_speed
            durations[str(servo.index)] = max(0.1, delta * (0.12 / speed))
        total = sum(durations.values()) if posture.mode == "sequencial" else max(durations.values(), default=0.1)
        return {"durations": durations, "total": total, "warnings": self.safety_warnings(posture)}


manager = ServoManager()
app = FastAPI(title="Servo Firmata Control API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/state")
def state() -> dict[str, Any]:
    return manager.snapshot()


@app.get("/api/ports")
def ports() -> list[dict[str, str]]:
    return list_serial_ports()


@app.get("/api/postures")
def postures() -> list[str]:
    return manager.list_postures()


@app.get("/api/postures/{name}")
def get_posture(name: str) -> dict[str, Any]:
    try:
        posture = manager.load_posture(name)
        return {"posture": asdict(posture), "vector": posture.vector, "estimate": manager.estimate(posture)}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/postures")
def save_posture(payload: PosturePayload) -> dict[str, Any]:
    try:
        posture = manager.save_posture(payload)
        return {"posture": asdict(posture), "vector": posture.vector}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/connect")
def connect(payload: ConnectPayload) -> dict[str, Any]:
    try:
        manager.connect(payload.port.strip())
        return manager.snapshot()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/autoconnect")
def autoconnect() -> dict[str, Any]:
    try:
        manager.connect("")
        return manager.snapshot()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/disconnect")
def disconnect() -> dict[str, Any]:
    manager.disconnect()
    return manager.snapshot()


@app.post("/api/execute")
def execute(payload: ExecutePayload) -> dict[str, Any]:
    try:
        return manager.execute(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/showcase")
def showcase(payload: ShowcasePayload) -> dict[str, Any]:
    try:
        return manager.showcase(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/live")
def live(payload: LivePayload) -> dict[str, Any]:
    try:
        manager.live(payload)
        return manager.snapshot()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/stop")
def stop() -> dict[str, Any]:
    manager.stop()
    return manager.snapshot()


@app.post("/api/export")
def export_dataset() -> dict[str, str]:
    path = manager.export_dataset()
    return {"file": path.name, "path": str(path)}


@app.get("/api/events")
async def events() -> StreamingResponse:
    async def stream():
        last_id = 0
        while True:
            pending = manager.get_events_after(last_id)
            for event in pending:
                last_id = event["id"]
                yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
            await asyncio.sleep(0.15)

    return StreamingResponse(stream(), media_type="text/event-stream")


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/", response_model=None)
def index():
    index_file = WEB_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Rode o frontend com: cd web && npm install && npm run dev"}


def normalize_order(order: list[int]) -> list[int]:
    seen = []
    for item in order:
        if 1 <= int(item) <= SERVO_COUNT and int(item) not in seen:
            seen.append(int(item))
    return seen or [1, 2, 3, 4, 5, 6]


def safe_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    return cleaned or "Postura"


def list_serial_ports() -> list[dict[str, str]]:
    if list_ports is None:
        return []
    ports = []
    for port in list_ports.comports():
        ports.append(
            {
                "device": port.device,
                "description": port.description or "",
                "hwid": port.hwid or "",
            }
        )
    return ports


def normalize_port_name(port: str) -> str:
    value = port.strip()
    if not value:
        return ""
    lowered = value.lower().replace("\\", "/")
    if lowered.startswith("/dev/") or lowered.upper().startswith("COM"):
        return value
    if re.fullmatch(r"acm\d+", lowered):
        return "/dev/tty" + lowered.upper()
    if re.fullmatch(r"ttyacm\d+", lowered):
        return "/dev/" + lowered
    if re.fullmatch(r"usb\d+", lowered):
        return "/dev/tty" + lowered.upper()
    if re.fullmatch(r"ttyusb\d+", lowered):
        return "/dev/" + lowered
    if re.fullmatch(r"com\d+", lowered):
        return lowered.upper()
    return value


def candidate_ports(preferred: str = "") -> list[str]:
    candidates = []
    normalized = normalize_port_name(preferred)
    if normalized:
        candidates.append(normalized)
    for port in sorted(list_serial_ports(), key=port_priority):
        candidates.append(port["device"])
    candidates.extend(COMMON_SERIAL_PORTS)
    return unique_items(candidates)


def autodetect_port(preferred: str = "") -> str:
    candidates = candidate_ports(preferred)
    return candidates[0] if candidates else ""


def port_priority(port: dict[str, str]) -> int:
    haystack = f"{port['device']} {port['description']} {port['hwid']}".lower()
    if any(token in haystack for token in ("arduino", "uno", "ch340", "ch341")):
        return 0
    if any(token in haystack for token in ("acm", "usbmodem", "ttyusb", "usb serial", "usb-serial")):
        return 1
    return 2


def unique_items(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
