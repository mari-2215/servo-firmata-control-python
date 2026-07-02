# Azimutal Minerva

Controle de leme azimutal para Arduino Mega usando FlySky FS-i4 com receptor FS-A6.

O projeto le dois canais PWM do receptor:

- canal vertical: escolhe entre referencia normal e referencia de re.
- canal horizontal: esterca 45 graus para a esquerda ou 45 graus para a direita.

A regra principal e que o angulo do servo e sempre calculado como posicao absoluta. O codigo nunca manda girar mais 180 graus em cima do valor anterior. Isso evita acumulo de erro e ajuda a manter a referencia durante a troca entre frente e re.

## Primeiro upload: modo monitor

Por seguranca, o firmware sobe em `ReceiverMonitorOnly`. Nesse modo o Arduino le o receptor, calcula os alvos e imprime tudo no monitor serial, mas nao manda pulso para o servo.

Use esse modo primeiro, porque ele mostra se o radio esta chegando certo antes de mover o leme:

~~~text
out=monitor mode=forward steering=0.00 target=0.00 command=0.00 servoUs=1000 vUs=1100 hUs=1500 failsafe=no
~~~

Se `vUs` ou `hUs` aparecer com `!`, o canal esta sem pulso recente ou fora da faixa esperada. Confira fio, canal e GND comum.

Depois que as leituras estiverem certas, mude em `src/main.cpp`:

~~~cpp
const ServoOutputMode servoOutputMode = ServoOutputMode::Position360Servo;
~~~

## Aviso importante sobre servo 360

Esta logica assume um servo 360 posicional, ou seja, um servo que aceita um comando PWM para ir a um angulo absoluto entre 0 e 360 graus.

Se o seu servo 360 for de rotacao continua, o PWM controla velocidade e sentido, nao posicao. Nesse caso, o servo vai parecer doido: `1000 us` gira para um lado, `1500 us` para, e `2000 us` gira para o outro. Nenhum codigo consegue garantir a referencia de 180 graus sem um sensor de posicao, como encoder, potenciometro ou AS5600. Para barco azimutal, use servo posicional 360 ou adicione feedback de posicao.

## Mapa de controle

| Entrada do FS-i4 | Sinal aproximado | Resultado |
| --- | ---: | --- |
| Vertical para baixo | abaixo de 1500 us | referencia normal, 0 graus |
| Vertical para cima | acima de 1500 us | referencia de re, 180 graus |
| Horizontal no centro | perto de 1500 us | sem desvio lateral |
| Horizontal para esquerda | perto de 1000 us | -45 graus da referencia atual |
| Horizontal para direita | perto de 2000 us | +45 graus da referencia atual |

Exemplos:

- frente + centro: 0 graus
- frente + esquerda: 315 graus, que equivale a -45 graus
- frente + direita: 45 graus
- re + centro: 180 graus
- re + esquerda: 135 graus
- re + direita: 225 graus

Se os sentidos ficarem invertidos, ajuste em `src/main.cpp`:

~~~cpp
const bool reverseWhenVerticalIsHigh = true;
const bool invertHorizontal = false;
~~~

## Hardware alvo

- Arduino Mega 2560
- FlySky FS-i4
- Receptor FlySky FS-A6
- Servo 360 posicional
- Fonte/BEC separado para o servo, com GND em comum com o Arduino

Ligacao sugerida:

| Sinal | Pino Arduino Mega |
| --- | --- |
| FS-A6 canal vertical, sugerido CH3 | D18 |
| FS-A6 canal horizontal, sugerido CH1 | D19 |
| Sinal do servo azimutal | D9 |
| GND do receptor, Arduino e BEC | comum |

Nao alimente o servo pelo pino 5V do Arduino se ele tiver carga mecanica. Use uma fonte/BEC adequada para o servo.

## Estrutura

- src/main.cpp: leitura dos canais PWM no Arduino Mega e comando do servo.
- include/AzimuthControl.h: interface da logica de controle.
- src/AzimuthControl.cpp: calculo de modo, desvio lateral e angulo absoluto.
- test/test_azimuth_logic/test_main.cpp: testes da logica sem hardware.
- docs/: detalhes de hardware, logica, calibracao e testes.
- docs/calibration.md: roteiro para descobrir os intervalos reais do FS-i4/FS-A6.

## Como ajustar

Os principais ajustes ficam em `src/main.cpp`:

- `servoOutputMode`: deixa em monitor ou liga a saida para servo posicional 360.
- `verticalMinUs`, `verticalCenterUs`, `verticalMaxUs`: intervalo real do canal vertical.
- `horizontalMinUs`, `horizontalCenterUs`, `horizontalMaxUs`: intervalo real do canal horizontal.
- `reverseWhenVerticalIsHigh`: inverte qual metade vertical chama a re.
- `invertHorizontal`: inverte esquerda/direita.
- `rcMinUs`, `rcCenterUs`, `rcMaxUs`: calibracao dos sinais do receptor.
- `rcDeadbandUs`: zona morta para evitar jitter perto do centro.
- `servoPosition0Us`, `servoPosition360Us`: faixa PWM aceita pelo servo 360 posicional.
- `servoZeroOffsetDeg`: correcao caso o zero mecanico do servo nao esteja alinhado com o barco.
- `maxRateDegPerSecond`: velocidade maxima de mudanca de angulo.

Tambem confira `makeAzimuthConfig()` para ajustar:

- `forwardReferenceDeg`
- `reverseReferenceDeg`
- `maxSteeringDeg`

## Testes

Com PlatformIO instalado:

~~~bash
pio test -e native
~~~

Para compilar para Arduino Mega:

~~~bash
pio run -e mega2560
~~~

Para gravar no Arduino Mega:

~~~bash
pio run -e mega2560 -t upload
~~~
