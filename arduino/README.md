# Arduino / Firmata

Este projeto usa o sketch oficial `StandardFirmata`.

## Upload

1. Abra a Arduino IDE.
2. Acesse `File > Examples > Firmata > StandardFirmata`.
3. Selecione a placa `Arduino Uno`.
4. Selecione a porta serial correta.
5. Clique em Upload.

## Pinos usados

| Motor | Pino |
| --- | --- |
| M1 | D3 |
| M2 | D5 |
| M3 | D6 |
| M4 | D9 |
| M5 | D10 |
| M6 | D11 |

O Python configura esses pinos como `SERVO` via Firmata.
