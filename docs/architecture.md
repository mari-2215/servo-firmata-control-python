# Arquitetura

## Componentes

```text
React Web UI
  -> REST API / Server-Sent Events
  -> FastAPI backend
  -> simulacao local ou pyfirmata
  -> Arduino Uno com StandardFirmata
  -> servomotores
```

O projeto tambem mantem `servo_control_app.py` como fallback local em Tkinter.

## Fluxo de gravacao

1. Usuario ajusta angulo, velocidade e nome de cada motor.
2. O React gera a pre-visualizacao, a timeline e o grafico.
3. O botao de salvar envia `POST /api/postures`.
4. A API gera o vetor de controle.
5. A postura e salva em `logs/*.json`.

## Fluxo de simulacao

1. Usuario seleciona uma postura salva.
2. O React carrega o JSON por `GET /api/postures/{nome}`.
3. O botao de execucao envia `POST /api/execute` com `arduino=false`.
4. A API interpola o movimento e publica eventos por `GET /api/events`.
5. Os servos virtuais sao atualizados em tempo real.
6. Nenhum Arduino e necessario.

## Fluxo com Arduino

1. Arduino roda `StandardFirmata`.
2. Python abre a porta serial com `pyfirmata`.
3. Cada pino D3, D5, D6, D9, D10 e D11 e configurado como servo.
4. O React envia `POST /api/execute` com `arduino=true`.
5. A API interpola o movimento em pequenos passos.
6. Cada passo e enviado ao Arduino pelo protocolo Firmata.
7. O estado volta ao React por SSE, atualizando painel ao vivo, grafico e servos virtuais.

## Endpoints principais

- `GET /api/state`: estado atual, servos, conexao e posturas salvas.
- `GET /api/events`: canal SSE para eventos em tempo real.
- `POST /api/postures`: salva postura/dataset.
- `GET /api/postures/{nome}`: carrega postura e estimativa.
- `POST /api/connect`: conecta na porta serial do Arduino.
- `POST /api/execute`: executa uma postura na simulacao ou Arduino.
- `POST /api/showcase`: executa todas as posturas em coreografia.
- `POST /api/live`: envia um angulo direto para um servo.
- `POST /api/export`: exporta o dataset em CSV.
