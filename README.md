# Cerebro_robo_autonomo

## Como rodar:

- Abre a cena "simulacao/rativa_circuito.ttt" no coppelia
- Inicia o servidor de visualização web:

```bash
python3 -m motor_grafo.servidor_visualizacao
```

- Executa a simulação:

```bash
sudo env VISUALIZADOR_SEPARADO=1 \
/home/peri/Área\ de\ trabalho/Cerebro_robo_autonomo/coppelia/bin/python \
-m movimento_autonomo.cerebro_foda
```

obs: substitua a segunda linha pelo caminho para o python da sua venv.

Ao executar o script a simulação deve iniciar sozinha e o robô deve caminhar livre e petulante pelsa fronteiras da
aventura.
