# Calibracao dos canais do FS-i4/FS-A6

Use este roteiro quando o leme nao obedecer, inverter comandos ou trocar frente/re no ponto errado.

## 1. Deixe em modo monitor

Em `src/main.cpp`, mantenha:

~~~cpp
const ServoOutputMode servoOutputMode = ServoOutputMode::ReceiverMonitorOnly;
~~~

Nesse modo o servo nao recebe comando. O Arduino so mede o receptor e imprime no serial.

## 2. Mova os sticks ate os extremos

Abra o monitor serial em 115200 baud e mova:

- vertical totalmente para baixo e para cima
- horizontal totalmente para esquerda e para direita

A linha do serial vai mostrar algo assim:

~~~text
vUs=1510 vPct=0.40 hUs=1504 hPct=0.80 failsafe=no vSeen=1118..1892 mid=1505 hSeen=1122..1885 mid=1503
~~~

Use os valores de `vSeen`, `hSeen` e `mid` para preencher as constantes.

## 3. Copie os intervalos reais para o codigo

Exemplo:

~~~cpp
const uint16_t verticalMinUs = 1118;
const uint16_t verticalCenterUs = 1505;
const uint16_t verticalMaxUs = 1892;
const uint16_t horizontalMinUs = 1122;
const uint16_t horizontalCenterUs = 1503;
const uint16_t horizontalMaxUs = 1885;
~~~

Nao precisa ser perfeito no primeiro teste. O importante e o centro ficar perto do valor parado e os extremos cobrirem o movimento real.

## 4. Ajuste sentido se necessario

Se colocar o vertical para cima nao chamar re, troque:

~~~cpp
const bool reverseWhenVerticalIsHigh = false;
~~~

Se esquerda/direita ficarem trocadas, troque:

~~~cpp
const bool invertHorizontal = true;
~~~

## 5. Ligue a saida do servo por ultimo

Quando `vPct` e `hPct` ficarem perto de `-100`, `0` e `100` nos extremos/centro, habilite:

~~~cpp
const ServoOutputMode servoOutputMode = ServoOutputMode::Position360Servo;
~~~

Teste primeiro sem carga mecanica no leme.

## Se aparecer `!` depois de vUs ou hUs

Exemplo: `vUs=1500!` significa que o canal nao recebeu pulso recente. Verifique fio do canal, GND comum e se o receptor esta pareado.
