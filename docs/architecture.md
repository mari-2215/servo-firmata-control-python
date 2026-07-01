# Arquitetura

## Componentes

```text
Interface Python
  -> sliders / posturas / simulacao
  -> pyfirmata
  -> Arduino Uno com StandardFirmata
  -> servomotores
```

## Fluxo de gravacao

1. Usuario ajusta angulo, velocidade e nome de cada motor.
2. A interface gera o vetor de controle.
3. A postura e salva em `logs/*.json`.

## Fluxo de simulacao

1. Usuario seleciona uma postura salva.
2. A interface carrega o JSON.
3. Os servos virtuais sao animados na tela.
4. Nenhum Arduino e necessario.

## Fluxo com Arduino

1. Arduino roda `StandardFirmata`.
2. Python abre a porta serial com `pyfirmata`.
3. Cada pino D3, D5, D6, D9, D10 e D11 e configurado como servo.
4. A interface interpola o movimento em pequenos passos.
5. Cada passo e enviado ao Arduino pelo protocolo Firmata.
