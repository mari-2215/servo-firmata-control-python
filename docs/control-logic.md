# Logica de controle

## Entradas

O receptor FS-A6 entrega sinais PWM tipicos de radio controle:

- cerca de 1000 us em um extremo
- cerca de 1500 us no centro
- cerca de 2000 us no outro extremo

O codigo le dois canais:

- vertical: escolhe frente ou re
- horizontal: define desvio lateral

## Modo frente/re

O canal vertical e dividido pelo centro:

- abaixo de centerUs - deadbandUs: um modo
- acima de centerUs + deadbandUs: o outro modo
- dentro da zona morta: mantem o ultimo modo

Por padrao, vertical alto chama re. Se o radio estiver invertido, use `reverseWhenVerticalIsHigh = false`.

## Desvio horizontal

O canal horizontal vira um valor normalizado entre -1.0 e +1.0.

Depois, esse valor e multiplicado por `maxSteeringDeg`, que por padrao e 45 graus.

~~~text
steeringDeg = horizontalNormalizado * 45
~~~

Se esquerda e direita ficarem invertidas, use `invertHorizontal = true`.

## Angulo absoluto

A referencia nunca e acumulada. O alvo sempre nasce desta formula:

~~~text
baseAngle = modo re ? 180 : 0
targetAngle = baseAngle + steeringDeg
~~~

Depois o angulo e normalizado para a escala 0..360.

Esse ponto e importante: ao alternar entre frente e re varias vezes, o codigo continua mirando 0 ou 180. Ele nao soma 180 repetidamente.

## Saida para o servo

A saida fica desligada em `ReceiverMonitorOnly`. Nesse modo o firmware so imprime diagnostico.

Em `Position360Servo`, o alvo em graus e convertido para PWM entre `servoPosition0Us` e `servoPosition360Us`. O padrao agora e 1000..2000 us para evitar mandar extremos agressivos.

## Suavizacao

`maxRateDegPerSecond` limita a velocidade de mudanca do comando. O alvo continua absoluto, mas o comando enviado ao servo caminha ate ele aos poucos.

Se voce quiser uma troca mais rapida entre frente e re, aumente esse valor em `makeAzimuthConfig()`.

## Failsafe

Se o canal vertical ficar sem pulso valido, o codigo mantem o ultimo modo conhecido.

Se o canal horizontal ficar sem pulso valido, o desvio lateral volta para zero. Isso deixa o leme alinhado com a referencia atual, em vez de manter uma curva indefinida.

Em failsafe, a saida para o servo nao e atualizada.

## Servo 360 de rotacao continua

Um servo de rotacao continua nao sabe ir para 135, 180 ou 225 graus; ele so gira mais rapido ou mais devagar. Para nao perder referencia com esse tipo de servo, adicione feedback de posicao e feche a malha de controle.
