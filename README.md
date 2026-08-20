# CBA-Capacidade-Hospedagem-OpenDSS-Python
Arquivos de simulação do artigo para o Congresso Brasileiro de Automática
CBA - Capacidade de Hospedagem (OpenDSS + Python)
Este repositório contém os dados e os códigos-fonte utilizados no artigo "Avaliação da Capacidade de Hospedagem de Sistemas Fotovoltaicos em Redes de Distribuição Utilizando Conexão Monofásica e Trifásica", submetido ao Congresso Brasileiro de Automática (CBA).

📁 Estrutura dos Arquivos
⚠️ Importante: Para o correto funcionamento da simulação, todos os arquivos listados abaixo devem ser mantidos juntos na mesma pasta local.

🐍 Código Principal (Python)
Caso_A_B_Dimensionado_Rev12.py: Script principal responsável por coordenar a simulação, interagir com o OpenDSS e gerar os resultados e gráficos.

⚡ Modelagem da Rede (OpenDSS)
Master_Rev_3.dss (Arquivo principal de compilação do circuito)

BDGD_LineCodes.dss

BDGD_Lines_RAMLIG.dss

BDGD_Lines_SSDBT.dss

BDGD_Loads_UCBT.dss

BDGD_LoadShapes.dss

BDGD_Monitors_Barras.dss

BDGD_Monitors_Trafos_e_Reatores.dss

BDGD_Transformers.dss

PVSystems_Gerados.dss

🚀 Como Executar
Pré-requisitos: Certifique-se de ter o ambiente Python configurado e todas as bibliotecas solicitadas no início do código instaladas (ex: dss-python, pandas, matplotlib, numpy, etc.).

Execução: Abra o script Caso_A_B_Dimensionado_Rev12.py na sua IDE de preferência e execute o código.

⚠️ Avisos Importantes (Troubleshooting)
Caso o código apresente erros na primeira execução, o problema muito provavelmente está relacionado aos diretórios (caminhos de pasta absolutos) configurados no script. Verifique e ajuste os seguintes itens no código Python:

Caminho do arquivo Master: Verifique se a linha de comando que compila o arquivo Master_Rev_3.dss está apontando para o endereço correto da pasta no seu computador atual.

Diretório de saída dos gráficos: Verifique os comandos de salvamento das figuras e altere o caminho de destino para uma pasta existente na sua máquina.

Para resolver ambos os casos, basta alterar os caminhos no script Python para o endereço da pasta local onde você guardou os arquivos baixados deste repositório.
