# Hardware

## Componentes

- Arduino Mega 2560
- FlySky FS-i4
- Receptor FlySky FS-A6
- Servo 360 posicional
- Fonte/BEC adequada para o servo

## Ligacao recomendada

| Componente | Sinal | Arduino Mega |
| --- | --- | --- |
| FS-A6 CH3 | controle vertical | D18 |
| FS-A6 CH1 | controle horizontal | D19 |
| Servo azimutal | sinal PWM | D9 |
| FS-A6, BEC, Arduino | GND | comum |

Os pinos D18 e D19 foram escolhidos porque no Arduino Mega eles aceitam interrupcao externa. Assim o codigo mede os pulsos do receptor sem ficar travado esperando pulseIn().

## Alimentacao

O servo deve receber alimentacao de uma fonte/BEC compativel com a corrente dele. O Arduino pode reiniciar ou medir sinais errados se o servo puxar corrente pelo 5V da placa.

Use GND comum entre:

- Arduino
- receptor FS-A6
- fonte/BEC do servo

## Calibracao inicial

1. Ligue o FS-i4 e o receptor.
2. Com o monitor serial em 115200 baud, observe vUs e hUs.
3. Mova os sticks para os extremos.
4. Ajuste rcMinUs, rcCenterUs e rcMaxUs em src/main.cpp.
5. Teste o servo sem carga mecanica antes de instalar no leme.

## Sobre a referencia mecanica

Monte o leme/propulsor de modo que forwardReferenceDeg seja a direcao normal de navegacao. Se o servo estiver fisicamente deslocado, ajuste servoZeroOffsetDeg em vez de mudar a regra de controle.
