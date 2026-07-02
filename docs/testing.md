# Testes

Os testes ficam em test/test_azimuth_logic/test_main.cpp e validam a logica sem depender do Arduino, receptor ou servo.

## Rodar testes

Com PlatformIO:

~~~bash
pio test -e native
~~~

## O que os testes cobrem

- metade vertical para baixo coloca o modo frente em 0 graus
- metade vertical para cima coloca o modo re em 180 graus
- canal horizontal chega a -45 e +45 graus
- desvio lateral em re e relativo a referencia de 180 graus
- zona morta vertical mantem o ultimo modo
- canais invertidos podem ser corrigidos por configuracao
- perda do canal horizontal ativa failsafe e remove desvio lateral
- alternar frente/re repetidamente nao acumula angulo

## Teste em bancada

Antes de colocar no barco:

1. Deixe `servoOutputMode` em `ReceiverMonitorOnly`.
2. Ligue o receptor e o Arduino com GND comum.
3. Abra o monitor serial em 115200 baud.
4. Confira se `vUs` e `hUs` mudam entre aproximadamente 1000, 1500 e 2000.
5. Verifique se o alvo alterna entre 0 e 180 no canal vertical.
6. Verifique se o horizontal aplica ate 45 graus para cada lado.
7. So depois habilite `Position360Servo` e teste sem carga mecanica.
