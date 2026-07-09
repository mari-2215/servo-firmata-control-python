import React, { useEffect, useMemo, useState } from "react";
import { Activity, Cable, Download, Gauge, Pause, Play, Radio, Save, Sparkles, Square, Zap } from "lucide-react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const SERVO_PINS = [3, 5, 6, 9, 10, 11];
const API = "";

const emptyServos = SERVO_PINS.map((pin, index) => ({
  index: index + 1,
  pin,
  name: `Motor ${index + 1}`,
  angle: 0,
  speed: 5,
}));

function App() {
  const [tab, setTab] = useState("dataset");
  const [state, setState] = useState(null);
  const [servos, setServos] = useState(emptyServos);
  const [postureName, setPostureName] = useState("Postura_1");
  const [mode, setMode] = useState("sequencial");
  const [order, setOrder] = useState("1-2-3-4-5-6");
  const [selected, setSelected] = useState("");
  const [selectedPosture, setSelectedPosture] = useState(null);
  const [port, setPort] = useState("");
  const [ports, setPorts] = useState([]);
  const [globalSpeed, setGlobalSpeed] = useState(1);
  const [live, setLive] = useState(false);
  const [force, setForce] = useState(false);
  const [toast, setToast] = useState("");
  const [connectionLog, setConnectionLog] = useState("Aguardando conexao.");

  useEffect(() => {
    bootstrap();
    const source = new EventSource(`${API}/api/events`);
    const updateFromEvent = (event) => {
      const data = JSON.parse(event.data);
      setState(data.state);
      setServos(data.state.servos);
    };
    [
      "connected",
      "disconnected",
      "posture_saved",
      "dataset_exported",
      "execution_started",
      "servo_update",
      "execution_finished",
      "showcase_started",
      "showcase_finished",
      "stopped",
      "busy",
      "error",
    ].forEach((eventName) => source.addEventListener(eventName, updateFromEvent));
    source.addEventListener("execution_started", (event) => setToast(JSON.parse(event.data).payload.name + " em execucao"));
    source.addEventListener("execution_finished", (event) => setToast(JSON.parse(event.data).payload.name + " finalizada"));
    return () => source.close();
  }, []);

  useEffect(() => {
    if (selected) loadPosture(selected);
  }, [selected]);

  const currentPosture = useMemo(() => {
    const cleanOrder = order
      .split(/[^1-6]+/)
      .map(Number)
      .filter(Boolean)
      .filter((item, index, array) => array.indexOf(item) === index);
    return {
      name: postureName,
      servos,
      order: cleanOrder.length ? cleanOrder : [1, 2, 3, 4, 5, 6],
      mode,
    };
  }, [postureName, servos, order, mode]);

  const displayPosture = selectedPosture?.posture || currentPosture;
  const vector = selectedPosture?.vector || makeVector(currentPosture);
  const estimate = estimatePosture(displayPosture, servos, globalSpeed);
  const warnings = estimate?.warnings || [];

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || response.statusText);
    }
    return response.json();
  }

  async function refreshState() {
    const next = await api("/api/state");
    setState(next);
    setServos(next.servos);
    setPorts(next.ports || []);
    if (!port && next.ports?.length) setPort(next.ports[0].device);
    return next;
  }

  async function bootstrap() {
    const next = await refreshState();
    if (!next.connected) {
      try {
        const connected = await api("/api/autoconnect", { method: "POST" });
        setState(connected);
        setServos(connected.servos);
        setPorts(connected.ports || []);
        setPort(connected.port || "");
        setToast(`Arduino conectado automaticamente em ${connected.port}`);
      } catch (error) {
        setConnectionLog(error.message);
        setToast(`Auto connect aguardando Arduino: ${error.message}`);
      }
    }
  }

  async function refreshPorts() {
    try {
      const nextPorts = await api("/api/ports");
      setPorts(nextPorts);
      if (!port && nextPorts.length) setPort(nextPorts[0].device);
      setToast(nextPorts.length ? `${nextPorts.length} porta(s) detectada(s)` : "Nenhuma porta serial detectada");
      setConnectionLog(nextPorts.length ? nextPorts.map((item) => `${item.device} ${item.description || item.hwid || ""}`).join(" | ") : "Nenhuma porta serial detectada.");
    } catch (error) {
      setConnectionLog(error.message);
      setToast(`Erro ao buscar portas: ${error.message}`);
    }
  }

  async function savePosture() {
    const saved = await api("/api/postures", { method: "POST", body: JSON.stringify(currentPosture) });
    setSelected(saved.posture.name);
    setToast(`Postura salva: ${saved.posture.name}`);
    await refreshState();
  }

  async function loadPosture(name) {
    const loaded = await api(`/api/postures/${name}`);
    setSelectedPosture(loaded);
    setToast(`Postura carregada: ${name}`);
  }

  async function connect() {
    setToast(`Conectando${port ? ` em ${port}` : " automaticamente"}...`);
    try {
      const next = await api("/api/connect", { method: "POST", body: JSON.stringify({ port }) });
      setState(next);
      setServos(next.servos);
      setPorts(next.ports || []);
      setPort(next.port || port);
      setConnectionLog(`Conectado em ${next.port}`);
      setToast(`Arduino conectado em ${next.port}`);
    } catch (error) {
      setConnectionLog(error.message);
      setToast(`Falha ao conectar: ${error.message}`);
    }
  }

  async function autoconnect() {
    setToast("Escaneando portas e tentando conectar...");
    try {
      const next = await api("/api/autoconnect", { method: "POST" });
      setState(next);
      setServos(next.servos);
      setPorts(next.ports || []);
      setPort(next.port || "");
      setConnectionLog(`Conectado em ${next.port}`);
      setToast(`Arduino conectado automaticamente em ${next.port}`);
    } catch (error) {
      setConnectionLog(error.message);
      setToast(`Auto connect falhou: ${error.message}`);
    }
  }

  async function disconnect() {
    const next = await api("/api/disconnect", { method: "POST" });
    setState(next);
    setToast("Arduino desconectado");
  }

  async function execute(arduino) {
    const name = selected || currentPosture.name;
    if (!selected) await savePosture();
    const result = await api("/api/execute", {
      method: "POST",
      body: JSON.stringify({ name, arduino, global_speed: Number(globalSpeed), force }),
    });
    if (!result.accepted) {
      setToast(`Validacao pediu confirmacao: ${result.warnings.join(" | ")}`);
      setForce(true);
      return;
    }
    setToast(arduino ? "Execucao no Arduino iniciada" : "Simulacao iniciada");
  }

  async function choreography(arduino) {
    const result = await api("/api/showcase", {
      method: "POST",
      body: JSON.stringify({ arduino, global_speed: Number(globalSpeed), force }),
    });
    if (!result.accepted) {
      setToast(`Coreografia bloqueada: ${result.warnings.join(" | ")}`);
      setForce(true);
      return;
    }
    setToast("Coreografia iniciada");
  }

  async function stop() {
    const next = await api("/api/stop", { method: "POST" });
    setState(next);
    setToast("Execucao interrompida");
  }

  async function exportDataset() {
    const result = await api("/api/export", { method: "POST" });
    setToast(`CSV exportado: ${result.file}`);
  }

  async function updateServo(index, patch) {
    const next = servos.map((servo) => (servo.index === index ? { ...servo, ...patch } : servo));
    setServos(next);
    if (live && state?.connected && "angle" in patch) {
      await api("/api/live", { method: "POST", body: JSON.stringify({ servo_index: index, angle: Number(patch.angle) }) });
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Python API + React + Firmata</p>
          <h1>Servo Firmata Control</h1>
        </div>
        <div className="status-strip">
          <StatusPill icon={<Radio size={16} />} label={state?.connected ? `Arduino ${state.port}` : "Simulacao"} live={state?.connected} />
          <StatusPill icon={<Activity size={16} />} label={state?.status || "Inicializando"} />
          <StatusPill icon={<Gauge size={16} />} label={`${globalSpeed}x`} />
        </div>
      </header>

      <nav className="tabs">
        <button className={tab === "dataset" ? "active" : ""} onClick={() => setTab("dataset")}>Dataset</button>
        <button className={tab === "simulate" ? "active" : ""} onClick={() => setTab("simulate")}>Simulacao</button>
        <button className={tab === "arduino" ? "active" : ""} onClick={() => setTab("arduino")}>Arduino</button>
      </nav>

      {tab === "dataset" && (
        <section className="workspace three-col">
          <ServoEditor servos={servos} onChange={updateServo} />
          <ControlPanel
            postureName={postureName}
            setPostureName={setPostureName}
            mode={mode}
            setMode={setMode}
            order={order}
            setOrder={setOrder}
            onSave={savePosture}
            onExport={exportDataset}
            vector={makeVector(currentPosture)}
          />
          <InsightPanel posture={currentPosture} estimate={estimatePosture(currentPosture, servos, globalSpeed)} />
        </section>
      )}

      {tab === "simulate" && (
        <section className="workspace two-col">
          <PostureLibrary postures={state?.postures || []} selected={selected} setSelected={setSelected} refresh={refreshState} />
          <RunPanel
            title="Execucao simulada"
            arduino={false}
            connected
            selected={selected}
            posture={displayPosture}
            liveServos={servos}
            estimate={estimate}
            vector={vector}
            warnings={warnings}
            globalSpeed={globalSpeed}
            setGlobalSpeed={setGlobalSpeed}
            force={force}
            setForce={setForce}
            onExecute={() => execute(false)}
            onChoreography={() => choreography(false)}
            onStop={stop}
          />
        </section>
      )}

      {tab === "arduino" && (
        <section className="workspace two-col">
          <div className="stack">
            <ArduinoPanel
              port={port}
              setPort={setPort}
              ports={ports}
              connected={state?.connected}
              live={live}
              setLive={setLive}
              onConnect={connect}
              onAutoConnect={autoconnect}
              onRefreshPorts={refreshPorts}
              onDisconnect={disconnect}
              state={state}
              connectionLog={connectionLog}
            />
            <PostureLibrary postures={state?.postures || []} selected={selected} setSelected={setSelected} refresh={refreshState} />
          </div>
          <RunPanel
            title="Execucao no Arduino"
            arduino
            connected={state?.connected}
            selected={selected}
            posture={displayPosture}
            liveServos={servos}
            estimate={estimate}
            vector={vector}
            warnings={warnings}
            globalSpeed={globalSpeed}
            setGlobalSpeed={setGlobalSpeed}
            force={force}
            setForce={setForce}
            onExecute={() => execute(true)}
            onChoreography={() => choreography(true)}
            onStop={stop}
          />
        </section>
      )}

      {toast && <div className="toast" onAnimationEnd={() => setToast("")}>{toast}</div>}
    </main>
  );
}

function ServoEditor({ servos, onChange }) {
  return (
    <section className="panel servo-editor">
      <div className="panel-title">
        <Zap size={18} />
        <h2>Controle dos servos</h2>
      </div>
      <div className="servo-grid">
        {servos.map((servo) => (
          <article className="servo-card" key={servo.index}>
            <div className="servo-card-head">
              <strong>M{servo.index}</strong>
              <span>D{servo.pin}</span>
            </div>
            <input value={servo.name} onChange={(event) => onChange(servo.index, { name: event.target.value })} />
            <label>Angulo <b>{servo.angle} deg</b></label>
            <input type="range" min="0" max="180" value={servo.angle} onChange={(event) => onChange(servo.index, { angle: Number(event.target.value) })} />
            <label>Velocidade <b>V{servo.speed}</b></label>
            <input type="range" min="1" max="20" value={servo.speed} onChange={(event) => onChange(servo.index, { speed: Number(event.target.value) })} />
          </article>
        ))}
      </div>
    </section>
  );
}

function ControlPanel({ postureName, setPostureName, mode, setMode, order, setOrder, onSave, onExport, vector }) {
  return (
    <section className="panel command-panel">
      <div className="panel-title">
        <Save size={18} />
        <h2>Gravacao</h2>
      </div>
      <label>Nome da postura</label>
      <input value={postureName} onChange={(event) => setPostureName(event.target.value)} />
      <label>Modo</label>
      <div className="segmented">
        <button className={mode === "sequencial" ? "active" : ""} onClick={() => setMode("sequencial")}>Sequencial</button>
        <button className={mode === "simultaneo" ? "active" : ""} onClick={() => setMode("simultaneo")}>Simultaneo</button>
      </div>
      <label>Ordem</label>
      <input value={order} onChange={(event) => setOrder(event.target.value)} />
      <div className="button-row">
        <button className="primary" onClick={onSave}><Save size={16} /> Salvar</button>
        <button onClick={onExport}><Download size={16} /> CSV</button>
      </div>
      <div className="vector-box">{vector}</div>
    </section>
  );
}

function InsightPanel({ posture, estimate }) {
  return (
    <section className="panel visual-panel">
      <div className="panel-title">
        <Sparkles size={18} />
        <h2>Visual tecnico</h2>
      </div>
      <ServoStage servos={posture.servos} />
      <Timeline posture={posture} estimate={estimate} />
      <AngleChart servos={posture.servos} warnings={estimate.warnings} />
    </section>
  );
}

function PostureLibrary({ postures, selected, setSelected, refresh }) {
  return (
    <section className="panel library">
      <div className="panel-title">
        <Square size={18} />
        <h2>Posturas salvas</h2>
      </div>
      <button onClick={refresh}>Atualizar lista</button>
      <div className="posture-list">
        {postures.map((name) => (
          <button key={name} className={selected === name ? "selected" : ""} onClick={() => setSelected(name)}>
            {name}
          </button>
        ))}
      </div>
    </section>
  );
}

function RunPanel({ title, connected, posture, liveServos, estimate, vector, warnings, globalSpeed, setGlobalSpeed, force, setForce, onExecute, onChoreography, onStop }) {
  return (
    <section className="panel run-panel">
      <div className="panel-title">
        <Play size={18} />
        <h2>{title}</h2>
      </div>
      <div className="run-actions">
        <button className="primary" disabled={!connected} onClick={onExecute}><Play size={16} /> Executar</button>
        <button disabled={!connected} onClick={onChoreography}><Sparkles size={16} /> Coreografia</button>
        <button className="danger" onClick={onStop}><Pause size={16} /> Parar</button>
      </div>
      <div className="speed-strip">
        {[0.5, 1, 1.5, 2].map((value) => (
          <button key={value} className={Number(globalSpeed) === value ? "active" : ""} onClick={() => setGlobalSpeed(value)}>{value}x</button>
        ))}
      </div>
      <label className="checkline">
        <input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} />
        Forcar mesmo com alerta de seguranca
      </label>
      {warnings.length > 0 && <div className="warning">{warnings.join(" | ")}</div>}
      <ServoStage servos={liveServos} />
      <Timeline posture={posture} estimate={estimate} />
      <AngleChart servos={posture.servos} warnings={warnings} />
      <div className="vector-box">{vector}</div>
    </section>
  );
}

function ArduinoPanel({ port, setPort, ports, connected, live, setLive, onConnect, onAutoConnect, onRefreshPorts, onDisconnect, state, connectionLog }) {
  return (
    <section className="panel arduino-panel">
      <div className="panel-title">
        <Cable size={18} />
        <h2>Arduino Uno</h2>
      </div>
      <div className="connect-row">
        <select value={port} onChange={(event) => setPort(event.target.value)}>
          <option value="">Auto detectar</option>
          {ports.map((item) => (
            <option key={item.device} value={item.device}>
              {item.device} - {item.description || item.hwid || "porta serial"}
            </option>
          ))}
        </select>
        <button onClick={onRefreshPorts}>Buscar portas</button>
        <button onClick={onAutoConnect}>Auto</button>
      </div>
      <div className="connect-row">
        <input placeholder="Vazio = auto, ou COM3, /dev/ttyACM0, /dev/ttyACM1" value={port} onChange={(event) => setPort(event.target.value)} />
        <button className="primary" onClick={onConnect}>Conectar</button>
        <button onClick={onDisconnect}>Desconectar</button>
      </div>
      <label className="checkline">
        <input type="checkbox" checked={live} onChange={(event) => setLive(event.target.checked)} />
        Live control pelos sliders
      </label>
      <div className="telemetry">
        <span>Estado</span><b>{connected ? `Conectado em ${state?.port}` : "Desconectado"}</b>
        <span>Ultima acao</span><b>{state?.lastAction || "-"}</b>
        <span>Ultimo servo</span><b>{state?.lastServo || "-"}</b>
        <span>Horario</span><b>{state?.lastTimestamp || "-"}</b>
      </div>
      <div className="connection-log">{connectionLog}</div>
    </section>
  );
}

function ServoStage({ servos }) {
  return (
    <div className="servo-stage">
      {servos.map((servo) => {
        const rotation = servo.angle - 90;
        return (
          <div className="servo-dial" key={servo.index}>
            <div className="dial-face">
              <i style={{ transform: `rotate(${rotation}deg)` }} />
              <em />
            </div>
            <strong>M{servo.index}</strong>
            <span>{servo.angle} deg</span>
          </div>
        );
      })}
    </div>
  );
}

function Timeline({ posture, estimate }) {
  const total = Math.max(estimate.total || 0.1, 0.1);
  let cursor = 0;
  return (
    <div className="timeline">
      <div className="timeline-head">
        <b>{posture.mode}</b>
        <span>{total.toFixed(1)}s estimados</span>
      </div>
      {posture.order.map((index) => {
        const servo = posture.servos.find((item) => item.index === index);
        if (!servo) return null;
        const duration = estimate.durations?.[String(index)] || 0.1;
        const width = Math.max(7, (duration / total) * 100);
        const left = posture.mode === "sequencial" ? cursor : 0;
        if (posture.mode === "sequencial") cursor += width;
        return (
          <div className="timeline-row" key={index}>
            <span>M{index}</span>
            <div>
              <i style={{ width: `${width}%`, left: `${left}%` }} />
            </div>
            <b>{duration.toFixed(1)}s</b>
          </div>
        );
      })}
    </div>
  );
}

function AngleChart({ servos, warnings }) {
  return (
    <div className="angle-chart">
      {servos.map((servo) => {
        const risky = warnings.some((warning) => warning.startsWith(`M${servo.index}:`));
        return (
          <div className="bar-wrap" key={servo.index}>
            <span>{servo.angle}</span>
            <i className={risky ? "risky" : ""} style={{ height: `${Math.max(4, (servo.angle / 180) * 100)}%` }} />
            <b>M{servo.index}</b>
          </div>
        );
      })}
    </div>
  );
}

function StatusPill({ icon, label, live }) {
  return (
    <div className={`status-pill ${live ? "live" : ""}`}>
      {icon}
      <span>{label}</span>
    </div>
  );
}

function makeVector(posture) {
  const chunks = [safeName(posture.name)];
  posture.servos.forEach((servo) => {
    chunks.push(`M${servo.index}_${servo.angle}`);
    chunks.push(`V${servo.index}_${servo.speed}`);
  });
  chunks.push(`ORDEM_${posture.order.join("-")}`);
  chunks.push(`MODO_${posture.mode.toUpperCase()}`);
  return chunks.join("_");
}

function estimatePosture(posture, currentServos, globalSpeed) {
  const durations = {};
  posture.servos.forEach((servo) => {
    const current = currentServos.find((item) => item.index === servo.index)?.angle || 0;
    const delta = Math.abs(servo.angle - current);
    durations[String(servo.index)] = Math.max(0.1, delta * (0.12 / Math.max(1, servo.speed) / Number(globalSpeed || 1)));
  });
  const values = Object.values(durations);
  const total = posture.mode === "sequencial" ? values.reduce((sum, item) => sum + item, 0) : Math.max(...values, 0.1);
  const warnings = posture.servos
    .filter((servo) => Math.abs(servo.angle - (currentServos.find((item) => item.index === servo.index)?.angle || 0)) >= 110 && servo.speed >= 16)
    .map((servo) => `M${servo.index}: salto alto com velocidade ${servo.speed}.`);
  return { durations, total, warnings };
}

function safeName(value) {
  return String(value || "Postura").trim().replace(/[^A-Za-z0-9_-]+/g, "_") || "Postura";
}

createRoot(document.getElementById("root")).render(<App />);
