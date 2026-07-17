# Cérebro autônomo para robô hexápode

Este projeto controla, no CoppeliaSim, um robô hexápode projetado para
explorar redes de escoamento formadas por bueiros e dutos. O robô atravessa
pisos planos e dutos cilíndricos, identifica caminhos e obstruções, constrói um
mapa topológico da rede e retorna por caminhos já conhecidos quando encontra um
beco sem saída.

## Características do hexápode

- Seis patas controladas por cinemática inversa (`simIK`).
- Marcha do tipo *wave gait*, com no máximo uma pata em balanço por vez, para
  priorizar estabilidade.
- Movimento para frente no eixo local `+Y`, com avanço, ré, parada e giro no
  próprio eixo.
- Elevação suave do corpo antes da calibração e da caminhada.
- Controle automático de altura, inclinação e rumo.
- Adaptação das patas ao perfil curvo do duto e redistribuição de apoio entre
  as seis patas.
- Detecção de teto, saída de duto, paredes laterais e entulho frontal.
- Exploração autônoma com retorno de ré ao encontrar uma obstrução.
- Visualização, no navegador, do grafo criado durante a exploração.

## Sensores

Os nomes abaixo devem existir exatamente assim na hierarquia da cena do
CoppeliaSim.

| Sensor | Tipo/posição | Uso |
| --- | --- | --- |
| `/bottomSensor` | Proximidade, no centro e apontado para baixo | Mede a distância do corpo ao piso. A leitura alimenta o controle proporcional de altura e serve de referência para o perfil do terreno. |
| `/leftDepthSensor` | Proximidade, na lateral esquerda e apontado para baixo | Mede a altura do piso no lado esquerdo para adaptar as patas à curvatura e à transição entre bueiro e duto. |
| `/rightDepthSensor` | Proximidade, na lateral direita e apontado para baixo | Faz a mesma medição no lado direito. A combinação das duas laterais permite reconhecer um perfil cilíndrico aproximadamente simétrico. |
| `/frontalSensor` | Proximidade, apontado para a frente | Detecta obstáculos. Dentro de um duto, uma leitura a até `0,40 m`, confirmada duas vezes, é tratada como entulho. |
| `/upSensor` | Proximidade, apontado para cima | Detecta o teto. A presença persistente confirma que o robô entrou em um duto; a ausência persistente confirma a saída para um bueiro. |
| `/superLeftSensor` | Proximidade arquitetural, apontado para a esquerda | No centro de um bueiro, detecta parede ou abertura à esquerda. |
| `/superFrontalSensor` | Proximidade arquitetural, apontado para a frente | Detecta parede ou abertura à frente durante o mapeamento do bueiro. |
| `/superRightSensor` | Proximidade arquitetural, apontado para a direita | Detecta parede ou abertura à direita durante o mapeamento do bueiro. |
| `/GyroSensor` | Referência de orientação presa ao corpo | Fornece *roll*, *pitch* e *yaw*. Um controle PD estabiliza a inclinação e corrige o rumo pela extensão ou retração dos alvos das patas. |

O controlador também requer os objetos `/base`, `/legBase`, `/footTip0` a
`/footTip5` e `/footTarget0` a `/footTarget5`.

## Mapeamento e navegação

O projeto não implementa SLAM nem produz um mapa geométrico detalhado. Ele usa
um **mapa topológico**, representado por um grafo:

- os bueiros e os trechos de duto são nós;
- as conexões transitáveis são arestas;
- cada aresta guarda seu estado (`livre` ou `bloqueado`) e o ângulo mundial
  (*yaw*) necessário para segui-la;
- bueiros já visitados são reconhecidos quando a posição XY medida fica a até
  `0,60 m` de uma posição conhecida.

### Como o robô sabe onde está

O `/upSensor` é a principal referência para distinguir os dois ambientes. Ao
avançar a partir de um bueiro, o robô considera que entrou em um duto quando o
sensor detecta teto continuamente por dois segundos. Enquanto há teto, ele
mantém o modo de travessia: segue o rumo do duto e adapta altura, inclinação e
apoio das patas ao piso curvo. Os sensores de profundidade laterais ajudam nessa
adaptação ao reconhecer o perfil cilíndrico.

Quando o teto deixa de ser detectado continuamente por dois segundos, o robô
entende que saiu do duto e chegou a um bueiro. Ele avança por um tempo definido
para se posicionar no centro, para e compara sua posição XY com as posições já
armazenadas. Se estiver a até `0,60 m` de uma delas, reconhece um bueiro já
visitado; caso contrário, cria um novo nó no mapa.

### Como novos caminhos são encontrados

Em cada bueiro novo, os sensores `/superLeftSensor`, `/superFrontalSensor` e
`/superRightSensor` observam simultaneamente as direções esquerda, frente e
direita durante um segundo. Uma detecção representa uma parede; a ausência de
detecção representa uma possível entrada de duto. A entrada só é adicionada ao
grafo quando pelo menos 70% das amostras daquela direção indicam abertura. Se
essa proporção não for atingida, a direção é considerada fechada e não se torna
uma opção de navegação.

Cada abertura confirmada é registrada como um trecho de duto livre, junto com
o *yaw* mundial necessário para alinhar o robô à entrada. Ao chegar novamente a
um bueiro conhecido, o mapa existente é reutilizado, evitando registrar o mesmo
local e seus caminhos como novas descobertas.

### Busca em profundidade e backtracking

A exploração usa **busca em profundidade (DFS)**. Em cada bueiro, o robô
escolhe um duto com estado `livre` que ainda não tenha sido visitado, guarda o
nó atual em uma pilha e segue por esse caminho. Assim, ele aprofunda uma
ramificação da rede antes de tentar as alternativas deixadas para trás.

Existem duas situações de retorno:

- **Backtracking por entulho:** se o `/frontalSensor`, já dentro de um duto,
  confirmar duas leituras de obstáculo a no máximo `0,40 m`, o trecho e sua
  conexão são marcados como `bloqueado`, e a posição XY do entulho é salva. O
  robô volta de ré pelo mesmo duto, confirma a saída pela ausência de teto,
  centraliza-se novamente no bueiro anterior e procura outra opção. O caminho
  bloqueado não participa das escolhas futuras da DFS.
- **Backtracking por fim de ramificação:** se não houver dutos livres e ainda
  não visitados no bueiro atual, o robô retira da pilha o local anterior e
  retorna por conexões livres já conhecidas. Esse retorno continua até encontrar
  um bueiro com algum caminho inédito. Quando a pilha fica vazia, o robô voltou
  ao ponto inicial sem restarem caminhos acessíveis; então ele para e encerra o
  mapeamento.

O ciclo completo consiste em centralizar e reconhecer o bueiro, registrar suas
aberturas, escolher uma delas pela DFS, alinhar-se ao *yaw* salvo, atravessar o
duto e atualizar o grafo na chegada ou no encontro de uma obstrução. O processo
se repete até que toda a rede acessível tenha sido explorada.

## Algoritmo de locomoção

A marcha é uma *wave gait*: as seis patas recebem fases diferentes e apenas
uma entra na fase de balanço de cada vez. Os alvos `/footTarget0` a
`/footTarget5` descrevem a passada, e o `simIK` resolve a posição das juntas.

Sobre a marcha básica são combinadas quatro correções:

- altura do corpo, calculada a partir do `/bottomSensor`;
- perfil lateral do piso, calculado pelos sensores esquerdo e direito;
- equilíbrio de *roll* e *pitch*, por controle PD usando o `/GyroSensor`;
- manutenção ou mudança de *yaw*, misturada à passada como componente
  tangencial.

Dentro do duto, as duas patas mais externas são encurtadas e as outras quatro
são alongadas gradualmente. Isso evita que o robô fique apoiado somente nos
pontos mais altos da superfície cilíndrica.

## Como executar `cerebro_hexapod.py`

Os comandos abaixo consideram que o terminal está na **raiz deste projeto**,
isto é, no diretório que contém `README.md`, `movimento_autonomo/`,
`motor_grafo/` e `simulacao/`.

1. Entre na raiz do projeto:

   ```bash
   cd /caminho/para/Cerebro_robo_autonomo
   ```

2. Abra o CoppeliaSim e carregue a cena integrada do hexápode
   `simulacao/rativa_final.ttt`. Confirme que a ZMQ Remote API está disponível
   em `localhost:23000`. Não é necessário iniciar a simulação manualmente: o
   cérebro faz isso depois de conectar e inicializar o robô.

3. Ainda na raiz, execute:

   ```bash
   PYTHONPATH="$PWD:$PWD/movimento_autonomo" \
   python3 movimento_autonomo/cerebro_hexapod.py
   ```

   As duas entradas de `PYTHONPATH` tornam acessíveis, respectivamente, o
   pacote `motor_grafo` na raiz e o controlador
   `movimento_autonomo/hexapod_controller_melhor.py`.

4. Acesse `http://127.0.0.1:8765` para acompanhar o mapa. Por padrão, o próprio
   cérebro inicia esse servidor e atualiza `front-end/grafo_atual.json`.

Para executar o visualizador em outro terminal, inicie-o a partir da raiz:

```bash
python3 -m motor_grafo.servidor_visualizacao
```

Depois, execute o cérebro com o servidor interno desativado:

```bash
VISUALIZADOR_SEPARADO=1 \
PYTHONPATH="$PWD:$PWD/movimento_autonomo" \
python3 movimento_autonomo/cerebro_hexapod.py
```

Use `Ctrl+C` para encerrar pelo terminal. O programa também trata o botão
**Stop** do CoppeliaSim e salva um último *snapshot* do grafo antes de sair.

## Estrutura principal

```text
movimento_autonomo/
├── cerebro_hexapod.py           # exploração, DFS e mapa topológico
├── hexapod_controller_melhor.py # marcha, IK, sensores e estabilização
└── cerebro_cubo.py              # cérebro do modelo cúbico legado
motor_grafo/
├── grafo_modulo.py              # estrutura de dados do mapa
└── servidor_visualizacao.py     # API e servidor web
front-end/                          # interface de visualização
simulacao/                          # cenas do CoppeliaSim
```

## Vídeos de demonstração

O diretório [`videos/`](videos/) contém vídeos que demonstram a execução do robô.
