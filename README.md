# Cerebro_robo_autonomo

## Como rodar:

- Abre a cena "simulacao/rativa_circuito.ttt" no coppelia
- executa o script "movimento_autonomo/cerebro_foda" como módulo a partir da raíz do projeto

obs: abaixo está um exemplo de como fazer isso no linux:

```bash
sudo /<Caminho absoluto para a pasta do projeto>/Cerebro_robo_autonomo/coppelia/bin/python -m movimento_autonomo.cerebro_foda

# No meu caso:

sudo /home/peri/Área\ de\ trabalho/Cerebro_robo_autonomo/coppelia/bin/python -m movimento_autonomo.cerebro_foda
```

Ao executar o script a simulação deve iniciar sozinha e o robô deve caminhar livre e petulante pelsa fronteiras da
aventura.
