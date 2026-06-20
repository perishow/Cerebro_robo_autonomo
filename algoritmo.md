# Algoritmo geral do mapeamento do robô

```pseudo
loop  
  o robô determina se está em um duto ou em um bueiro;
  se estado = duto: 
    robô segue em frente procurando entulhos; 
  se estado = bueiro:
    robô vasculha os 3 angulos e registra novas conexões;
    robô decide qual duto seguir a partir do critério da busca em profundidade;  
```

# Especificação dos passos

## Como o robô determina se está em um duto ou bueiro?

O robô determina onde está a partir da leitura e interpretação do leitor de proximidade superior.
Uma distância de treshold é determinada de acordo com o tamanho do duto. Se o sensor não identificar
leitura depois dessa distância ou a distância lida for muito alta, ele deve estar em um bueiro,
caso contrário ele está em um Duto.

## Como o robô identifica entulho?

O robô determina que algo é um entulho usando o sensor de proximidade frontal, mas só considera
bloqueio quando a leitura estiver bem perto e o robô ainda estiver em um duto. O sensor superior
continua sendo usado para confirmar que o robô está dentro do duto, mas ele não entra mais como
critério de bloqueio.

O limite de distância fica configurado no código em `LIMIAR_BLOQUEIO_FRONTAL` dentro de
`movimento_autonomo/cerebro_foda.py`.

## Como o robô vasculha os 3 angulos?

Ao identificar que está em um bueiro, o robô deve iniciar o procedimento de reconhecimento. Nesse
procedimento ele deve se posicionar no meio do bueiro e realizar a sequencia de rotação: -90°, +90°, +90°.
A cada etapa de rotação, ocorrerá uma leitura do sensor de proximidade frontal que determinará se à frente
tem uma parede ou um duto. caso tenha um duto, mapeie e passe para a próxima etapa de rotação. Ao final das
etapas de rotação, o robô utiliza o critério da busca em profundidade para decidir qual duto ele vai explorar.

# Requisitos do software

- Estrutura de dados Grafo implementada.
- Algoritmo de busca em profundidade para esse grafo.
- script de monitoramento do estado do robô.
