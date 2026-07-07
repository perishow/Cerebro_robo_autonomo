# Cerebro_robo_autonomo

## Como rodar

- Abra a cena "simulacao/rativa_circuito.ttt" no Coppelia
- Inicie o servidor de visualização web:

```bash
python3 -m motor_grafo.servidor_visualizacao
```

- Execute a simulação:

```bash
sudo env VISUALIZADOR_SEPARADO=1 \
/home/peri/Área\ de\ trabalho/Cerebro_robo_autonomo/coppelia/bin/python \
-m movimento_autonomo.cerebro_foda
```

Obs.: substitua a segunda linha pelo caminho para o Python da sua venv.

Ao executar o script, a simulação deve iniciar sozinha, e o robô deve caminhar livre e petulante pelas fronteiras da
aventura.

# Como funciona

Abaixo, tem-se a explicação da lógica com a qual o robô percorre as redes de escoamento de maneira autônoma.

## Tabela de interpretações

| superior | frontal | interpretação |
| --- | --- | --- |
| 0 | 0 | Está no bueiro com duto à frente |
| 0 | 1 | Está no bueiro sem duto à frente |
| 1 | 0 | Está dentro de um duto |
| 1 | 1 | Achou uma obstrução no duto |

A partir dessa interpretação, o robô realizará os seguintes passos:

Caso esteja em um duto (situação 10), ele continua em frente até alguma leitura mudar. Quando a leitura muda para 00 ou 01, o robô inicia a rotina de "bueiro",
posiciona-se no centro do bueiro e vira seu sensor frontal para onde estariam os outros 3 dutos, começando pelo mais à esquerda. Nesse momento, ele considera que
já existe um duto no caminho por onde veio, realiza a leitura e registra se existe ou não um duto em cada direção. Após esse mapeamento de dutos, ele segue viagem
pelo primeiro duto encontrado. Caso o robô se encontre na situação 11, ou seja, caso encontre uma obstrução, ele marca o duto como bloqueado, tira uma foto da
obstrução e volta para o bueiro por onde veio. Quando o robô se encontra em uma situação em que não há novos dutos para percorrer, ele realiza um backtracking
para procurar por dutos ainda não percorridos. Quando realmente não houver mais caminhos a seguir, ele volta ao início e finaliza sua operação.

Durante toda a operação, pode-se visualizar o trabalho de mapeamento do robô a partir da plataforma web, que recebe o grafo da rede de escoamento e o representa
de uma forma entendível e bonita.
