# Diagnostico de bancada

Use este roteiro quando o servo nao obedecer ou parecer fora de controle.

## 1. Comece em modo monitor

Confirme que `src/main.cpp` esta assim:

~~~cpp
const ServoOutputMode servoOutputMode = ServoOutputMode::ReceiverMonitorOnly;
~~~

Nesse modo o servo fica sem comando. Abra o monitor serial em 115200 baud e mova os sticks.

## 2. Confira os canais

O esperado e:

| Movimento | vUs | hUs |
| --- | ---: | ---: |
| vertical para baixo | perto de 1000 | nao importa |
| vertical para cima | perto de 2000 | nao importa |
| horizontal esquerda | nao importa | perto de 1000 |
| horizontal direita | nao importa | perto de 2000 |
| centro | perto de 1500 | perto de 1500 |

Se `vUs` muda quando voce mexe no horizontal, os fios dos canais estao trocados.

Se `hUs` muda ao contrario, mude:

~~~cpp
const bool invertHorizontal = true;
~~~

Se a re fica na metade errada do vertical, mude:

~~~cpp
const bool reverseWhenVerticalIsHigh = false;
~~~

## 3. Confira o tipo de servo

Com servo de rotacao continua, `1000 us`, `1500 us` e `2000 us` significam velocidade, nao angulo.

Sintoma tipico:

- em `1000 us`, ele gira para um lado sem parar
- em `1500 us`, ele para ou quase para
- em `2000 us`, ele gira para o outro lado sem parar

Se esse for o seu caso, ele nao consegue fazer `180 graus` com referencia confiavel sem sensor de posicao. Para nao perder referencia, adicione encoder/potenciometro/AS5600 ou troque para servo 360 posicional.

## 4. Ligue a saida so depois do monitor estar correto

Quando `vUs`, `hUs`, `target` e `servoUs` estiverem coerentes, habilite:

~~~cpp
const ServoOutputMode servoOutputMode = ServoOutputMode::Position360Servo;
~~~

Teste sem carga mecanica antes de colocar no leme.

## Intervalos errados

Se `vPct` e `hPct` nao chegam perto de -100 e 100 nos extremos, siga `docs/calibration.md` e copie `vSeen/hSeen` para as constantes em `src/main.cpp`.
