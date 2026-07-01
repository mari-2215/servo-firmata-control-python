# Servo Firmata Control

Interface grafica em Python para controlar 6 servomotores com Arduino Uno usando Firmata.

O projeto atende a fase de controle de servomotores:

- 6 servos mapeados em D3, D5, D6, D9, D10 e D11.
- Interface moderna com 3 abas.
- Gravacao de posturas para formar dataset.
- Execucao simulada sem Arduino.
- Execucao real no Arduino via Firmata.
- Vetor de controle com angulo, velocidade, ordem e modo.
- Logs salvos em `logs/`.

## Mapeamento

| Motor | Pino Arduino |
| --- | --- |
| M1 | D3 |
| M2 | D5 |
| M3 | D6 |
| M4 | D9 |
| M5 | D10 |
| M6 | D11 |

## Preparar o Arduino

1. Abra a Arduino IDE.
2. Va em `File > Examples > Firmata > StandardFirmata`.
3. Selecione `Arduino Uno`.
4. Escolha a porta.
5. Faca upload.

O projeto Python usa Firmata, entao nao precisa de um sketch proprio alem do `StandardFirmata`.

## Instalar dependencias

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Rodar

```bash
python servo_control_app.py
```

## Abas da interface

### 1. Gravar dataset

Use os sliders para configurar:

- angulo de cada servo;
- velocidade individual;
- nome de cada motor;
- ordem de execucao;
- modo `sequencial` ou `simultaneo`.

Depois clique em `Salvar postura`.

Cada postura gera um arquivo `.json` dentro de `logs/`.

### 2. Executar simulacao

Lista todas as posturas salvas e executa sem Arduino conectado.

Os servos virtuais se movem na tela respeitando:

- angulo salvo;
- velocidade salva;
- ordem salva;
- modo sequencial ou simultaneo.

### 3. Executar Arduino

Conecte o Arduino com Firmata usando a porta serial, por exemplo:

- Windows: `COM3`
- Linux: `/dev/ttyACM0` ou `/dev/ttyACM1`

Depois selecione uma postura e clique em `Executar`.

## Formato do vetor

Exemplo:

```text
Ex1_M1_30_V1_5_M2_60_V2_8_M3_90_V3_10_M4_45_V4_6_M5_120_V5_7_M6_20_V6_4_ORDEM_1-2-3-4-5-6_MODO_SEQUENCIAL
```

O vetor contem:

- nome da postura;
- angulo de cada motor;
- velocidade de cada motor;
- ordem de execucao;
- modo de execucao.

## Tratamento de erros

A interface trata:

- Arduino nao conectado;
- porta serial invalida;
- arquivo de postura ausente;
- postura/vetor mal formatado;
- dependencia `pyfirmata` ausente.

## Estrutura

```text
servo-firmata-control-python/
  servo_control_app.py
  requirements.txt
  logs/
  arduino/
  docs/
```

## Documentacao

- `docs/tutorial.md`: passo a passo de instalacao, gravacao, simulacao e execucao no Arduino.
- `docs/architecture.md`: resumo tecnico do fluxo entre interface, Firmata, Arduino e servos.
