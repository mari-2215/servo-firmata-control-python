# Tutorial rapido

## 1. Preparar o Arduino

1. Conecte o Arduino Uno por USB.
2. Abra a Arduino IDE.
3. Abra `File > Examples > Firmata > StandardFirmata`.
4. Selecione a placa `Arduino Uno`.
5. Selecione a porta serial correta.
6. Faca upload do exemplo.

O Python controla os servos pelo protocolo Firmata, entao o Arduino precisa estar com esse firmware carregado.

## 2. Instalar e abrir a interface

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python servo_control_app.py
```

No Linux/macOS, troque a ativacao do ambiente por:

```bash
source .venv/bin/activate
```

## 3. Gravar uma postura

1. Abra a aba `1. Gravar dataset`.
2. Ajuste o angulo e a velocidade de M1 ate M6.
3. Opcionalmente, altere o nome dos motores.
4. Escolha o modo `sequencial` ou `simultaneo`.
5. Informe a ordem, por exemplo `1-2-3-4-5-6`.
6. Clique em `Salvar postura`.

A interface salva um arquivo JSON em `logs/` e gera um vetor de controle com nome, angulos, velocidades, ordem e modo.

## 4. Executar sem Arduino

1. Abra `2. Executar simulacao`.
2. Selecione uma postura salva.
3. Clique em `Executar`.

Os servos virtuais mostram o movimento interpolado e respeitam o modo, a ordem e as velocidades salvas.

## 5. Executar no Arduino

1. Abra `3. Executar Arduino`.
2. Digite a porta serial, como `COM3`, `/dev/ttyACM0` ou `/dev/ttyACM1`.
3. Clique em `Conectar Firmata`.
4. Selecione uma postura.
5. Clique em `Executar`.

Durante a execucao, a interface envia cada angulo ao Arduino via Firmata. No modo sequencial, um servo termina antes do proximo. No modo simultaneo, todos caminham juntos em pequenos passos.

## 6. Erros comuns

- `pyfirmata` ausente: rode `pip install -r requirements.txt`.
- Porta invalida: confira a porta na Arduino IDE ou no gerenciador de dispositivos.
- Arduino nao responde: faca upload do `StandardFirmata` novamente.
- Lista vazia: salve uma postura na primeira aba ou verifique a pasta `logs/`.
