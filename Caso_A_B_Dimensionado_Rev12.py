import py_dss_interface
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker  # Adicionado para controlar a quantidade de informações nos eixos
import numpy as np
import random
import pandas as pd  # Biblioteca para Estatística Descritiva
import copy  # Necessário para salvar os dados de tensão de cada caso
import os  # Para criar a pasta e salvar os gráficos automaticamente


# ==============================================================================
# 1. FUNÇÕES DE APOIO (ACRÉSCIMO PARA LIMPEZA E ADEQUAÇÃO DOS RAMAIS)
# ==============================================================================
def limpar_elementos_conflitantes():
    """Reseta monitores e medidores antigos para não interferir na simulação."""
    dss.text("Disable Monitor.*")
    dss.text("Disable EnergyMeter.*")


def adequar_ramais_ligacao_especificos(buses_alvo):
    """Varre as linhas, identifica ramais (RM) conectados às cargas sorteadas e os torna trifásicos."""
    ramais_alterados = []
    i = dss.lines.first()
    while i > 0:
        nome = dss.lines.name
        if nome.upper().endswith("RM") and dss.lines.phases < 4:
            bus1_base = dss.lines.bus1.split('.')[0]
            bus2_base = dss.lines.bus2.split('.')[0]

            if bus1_base in buses_alvo or bus2_base in buses_alvo:
                lc_parts = dss.lines.linecode.split('_')
                novo_lc = "_".join(lc_parts[:-1]) + "_4"
                bus1_antigo = dss.lines.bus1
                bus2_antigo = dss.lines.bus2
                lc_antigo = dss.lines.linecode
                fases_antigas = dss.lines.phases

                dss.text(
                    f"edit Line.{nome} phases=4 bus1={bus1_base}.1.2.3.4 bus2={bus2_base}.1.2.3.4 linecode={novo_lc}")

                ramais_alterados.append({
                    'nome': nome, 'fases_antigas': fases_antigas, 'bus1_antigo': bus1_antigo,
                    'bus2_antigo': bus2_antigo, 'lc_antigo': lc_antigo, 'bus1_novo': f"{bus1_base}.1.2.3.4",
                    'bus2_novo': f"{bus2_base}.1.2.3.4", 'linecode_novo': novo_lc, 'bus1_base': bus1_base
                })
        i = dss.lines.next()
    return ramais_alterados


def auditoria_topologia_ramais(ramais_alterados):
    """Verifica os ramais alterados e procura por potenciais fases soltas na rede a montante."""
    if not ramais_alterados:
        return

    print("\n" + "-" * 115)
    print(f" AUDITORIA RAMAIS: {len(ramais_alterados)} RAMAL(IS) ALTERADO(S) PARA TRIFÁSICO")
    print("-" * 115)
    print(
        f"{'RAMAL':<15} | {'BUS1 (ANT->NOV)':<30} | {'BUS2 (ANT->NOV)':<28} | {'LINECODE (ANT->NOV)':<28} | {'TOPOLOGIA'}")
    print("-" * 115)

    alertas_fase_solta = 0
    for ramal in ramais_alterados:
        bus1_base = ramal['bus1_base']
        b1_str = f"{ramal['bus1_antigo']} -> {ramal['bus1_novo']}"
        b2_str = f"{ramal['bus2_antigo']} -> {ramal['bus2_novo']}"
        lc_str = f"{ramal['lc_antigo']} -> {ramal['linecode_novo']}"
        aviso = "OK"

        dss.circuit.set_active_bus(bus1_base)
        nodos_disponiveis = dss.bus.nodes
        tem_todas_as_fases = all(fase in nodos_disponiveis for fase in [1, 2, 3])

        if not tem_todas_as_fases:
            fases_em_falta = [f for f in [1, 2, 3] if f not in nodos_disponiveis]
            aviso = f"ERRO: Faltam fases {fases_em_falta} no nó a montante!"
            alertas_fase_solta += 1

        print(f"Line.{ramal['nome']:<10} | {b1_str:<30} | {b2_str:<28} | {lc_str:<28} | {aviso}")

    print("-" * 115)
    if alertas_fase_solta > 0:
        print(f"    -> ALERTA: Foram identificados {alertas_fase_solta} ramais com risco de 'Fase Solta'!")
    else:
        print("    -> SUCESSO: Todos os ramais alterados estão conectado a barramentos plenamente trifásicos.\n")


def mapear_ramais_e_cargas():
    """Identifica os ramais, conta as cargas associadas ao bus1, traduz a ligação e soma a potência (kW)."""
    cargas_por_bus = {}
    dss.loads.first()
    while True:
        bus_carga = dss.cktelement.bus_names[0].split('.')[0].lower()
        nome_carga = dss.loads.name
        num_fases = dss.cktelement.num_phases
        nodos = dss.cktelement.node_order
        kw_carga = dss.loads.kw

        if bus_carga not in cargas_por_bus:
            cargas_por_bus[bus_carga] = []

        cargas_por_bus[bus_carga].append({
            'nome': nome_carga,
            'fases': num_fases,
            'nodos': nodos,
            'kw': kw_carga
        })
        if not dss.loads.next(): break

    mapa_bus1 = {}
    dss.lines.first()
    while True:
        nome_linha = dss.lines.name
        if nome_linha.upper().startswith("RAM_"):
            bus1_base = dss.lines.bus1.split('.')[0].lower()
            bus2_base = dss.lines.bus2.split('.')[0].lower()

            if bus1_base not in mapa_bus1:
                mapa_bus1[bus1_base] = {'total_cargas': 0, 'mono': 0, 'bi': 0, 'tri': 0, 'total_kw': 0.0,
                                        'detalhes': []}

            if bus2_base in cargas_por_bus:
                para_cada_carga = cargas_por_bus[bus2_base]
                for c in para_cada_carga:
                    mapa_bus1[bus1_base]['total_cargas'] += 1
                    mapa_bus1[bus1_base]['total_kw'] += c['kw']
                    fases = c['fases']
                    nodos = c['nodos']
                    kw = c['kw']

                    letras = []
                    for n in nodos:
                        if n == 1:
                            letras.append("A")
                        elif n == 2:
                            letras.append("B")
                        elif n == 3:
                            letras.append("C")
                        elif n == 0 or n == 4:
                            letras.append("N")

                    sigla_ligacao = "".join(letras)
                    if "N" not in sigla_ligacao and fases < 3:
                        sigla_ligacao += "N"

                    if fases == 1:
                        tipo_str = "Monofásica"
                        mapa_bus1[bus1_base]['mono'] += 1
                    elif fases == 2:
                        tipo_str = "Bifásica"
                        mapa_bus1[bus1_base]['bi'] += 1
                    else:
                        tipo_str = "Trifásica"
                        mapa_bus1[bus1_base]['tri'] += 1

                    detalhe = f"Load.{c['nome']:<12} -> {tipo_str:<12} ({sigla_ligacao:<4}) | Potência: {kw:>6.2f} kW"
                    mapa_bus1[bus1_base]['detalhes'].append(detalhe)

        if not dss.lines.next(): break

    return mapa_bus1


# ==============================================================================
# 2. PARÂMETROS DE ESTUDO E INICIALIZAÇÃO
# ==============================================================================
dss = py_dss_interface.DSS()
caminho_master = r"C:\Users\iur_n\Documents\Projeto_Teste\Icoaraci\Conjunto Park dos Pinheiros\OpenDSS\Subtensao_corrigida\Master_Rev_3.dss"

niveis_penetracao = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

str_irrad = "0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2, 0.2, 0.3, 0.3, 0.3, 0.3, 0.5, 0.5, 0.5, 0.5, 0.8, 0.8, 0.8, 0.8, 0.9, 0.9, 0.9, 0.9, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.99, 0.99, 0.99, 0.99, 0.9, 0.9, 0.9, 0.9, 0.7, 0.7, 0.7, 0.7, 0.4, 0.4, 0.4, 0.4, 0.1, 0.1, 0.1, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0"

curvas_fv = f"""
! --- Curvas de Desempenho Estáticas ---
New XYCurve.MyPvsT npts=4 xarray=[0 25 75 100] yarray=[1.2 1.0 0.8 0.6]
New XYCurve.MyEff npts=4 xarray=[0.1 0.2 0.4 1.0] yarray=[0.86 0.9 0.93 0.97]

! --- Perfis Diários (adaptados para 96 pontos @ 15 min) ---
New Loadshape.MyIrrad npts=96 minterval=15 mult=({str_irrad})
New Tshape.MyTemp npts=96 minterval=15 temp=(25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 35, 35, 35, 35, 40, 40, 40, 40, 45, 45, 45, 45, 50, 50, 50, 50, 60, 60, 60, 60, 60, 60, 60, 60, 55, 55, 55, 55, 40, 40, 40, 40, 35, 35, 35, 35, 30, 30, 30, 30, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25)
"""

irrad_valores = [float(x) for x in str_irrad.split(',')]
hsp_calculado = sum(irrad_valores) * 0.25
TD = 0.75

# ==============================================================================
# 2.5 LENDO DADOS DE FATURAMENTO DO EXCEL
# ==============================================================================
caminho_excel = r"C:\Users\iur_n\Documents\Projeto_Teste\Icoaraci\Conjunto Park dos Pinheiros\Dados_BDGD\UCBT.xlsx"
dict_excel_consumo = {}
ramais_excel = set()

print("=" * 105)
print(" CARREGANDO DADOS DA PLANILHA DE CONSUMO (UCBT.xlsx)...")
print("=" * 105)
try:
    df_uc = pd.read_excel(caminho_excel)
    df_uc['RAMAL'] = df_uc['RAMAL'].astype(str).str.strip().str.upper()
    ramais_excel = set(df_uc['RAMAL'])

    cols_energia = [f"ENE_{str(i).zfill(2)}" for i in range(1, 13)]
    for col in cols_energia:
        if col not in df_uc.columns:
            df_uc[col] = 0.0

    df_uc['E_med'] = df_uc[cols_energia].mean(axis=1)
    dict_excel_consumo = dict(zip(df_uc['RAMAL'], df_uc['E_med']))
    print(f"-> Sucesso! {len(dict_excel_consumo)} clientes carregados do Excel.")
    print(f"-> HSP (Horas de Sol Pleno) Calculado via Loadshape: {hsp_calculado:.2f} horas/dia.")
except Exception as e:
    print(f"-> ERRO AO CARREGAR EXCEL: {e}")
    print("-> Verifique se o caminho do arquivo está correto e se o arquivo não está aberto.")

# ==============================================================================
# 3. MAPEAMENTO, CORREÇÃO DE TENSÕES E DIMENSIONAMENTO FOTOVOLTAICO
# ==============================================================================
dss.text(f"Compile '{caminho_master}'")
limpar_elementos_conflitantes()

print("\n" + "=" * 105)
print(" RELATÓRIO: MAPEAMENTO DE CARGAS POR RAMAL DE LIGAÇÃO (BUS1)")
print("=" * 105)
resultado_ramais = mapear_ramais_e_cargas()

if not resultado_ramais:
    print("-> Nenhum ramal iniciando com 'RAM_' foi encontrado ou não há cargas associadas a eles.")
else:
    for bus1, infos in resultado_ramais.items():
        if infos['total_cargas'] > 0:
            print(f"\n[ Poste/Barramento Origem: {bus1.upper()} ]")
            print(f"  -> Total de Cargas: {infos['total_cargas']}")
            print(f"  -> Potência Total Conectada: {infos['total_kw']:.2f} kW")
            print(
                f"  -> Perfil: {infos['mono']} Monofásica(s) | {infos['bi']} Bifásica(s) | {infos['tri']} Trifásica(s)")
            for det in infos['detalhes']:
                print(f"     - {det}")
print("=" * 105)

print("\n" + "=" * 105)
print(" CARACTERIZAÇÃO DA REDE (DADOS PARA A METODOLOGIA DO ARTIGO)")
print("=" * 105)

num_buses = dss.circuit.num_buses
num_lines = dss.lines.count
num_transformers = dss.transformers.count
num_loads = dss.loads.count

total_kw = 0.0
total_kvar = 0.0
qtd_mono, qtd_bi, qtd_tri = 0, 0, 0

fases_mono_detalhe = {'A (1)': 0, 'B (2)': 0, 'C (3)': 0, 'Outras': 0}
fases_bi_detalhe = {'AB (1,2)': 0, 'BC (2,3)': 0, 'CA (1,3)': 0, 'Outras': 0}
fases_tri_detalhe = {'ABC (1,2,3)': 0, 'Outras': 0}

if dss.loads.count > 0:
    dss.loads.first()
    while True:
        total_kw += dss.loads.kw
        total_kvar += dss.loads.kvar
        dss.circuit.set_active_element(f"Load.{dss.loads.name}")
        fases = dss.cktelement.num_phases

        nodos = dss.cktelement.node_order
        fases_ativas = sorted(list(set([n for n in nodos if n in [1, 2, 3]])))

        if fases == 1:
            qtd_mono += 1
            if fases_ativas == [1]:
                fases_mono_detalhe['A (1)'] += 1
            elif fases_ativas == [2]:
                fases_mono_detalhe['B (2)'] += 1
            elif fases_ativas == [3]:
                fases_mono_detalhe['C (3)'] += 1
            else:
                fases_mono_detalhe['Outras'] += 1
        elif fases == 2:
            qtd_bi += 1
            if fases_ativas == [1, 2]:
                fases_bi_detalhe['AB (1,2)'] += 1
            elif fases_ativas == [2, 3]:
                fases_bi_detalhe['BC (2,3)'] += 1
            elif fases_ativas == [1, 3]:
                fases_bi_detalhe['CA (1,3)'] += 1
            else:
                fases_bi_detalhe['Outras'] += 1
        else:
            qtd_tri += 1
            if fases_ativas == [1, 2, 3]:
                fases_tri_detalhe['ABC (1,2,3)'] += 1
            else:
                fases_tri_detalhe['Outras'] += 1

        if not dss.loads.next(): break

print(f"-> Total de Barras (Buses): {num_buses}")
print(f"-> Total de Tramos de Linha (Lines): {num_lines}")
print(f"-> Total de Cargas Mapeadas: {num_loads}")
print(f"   - Monofásicas: {qtd_mono} cargas")
if qtd_mono > 0:
    print(
        f"      * Fase A: {fases_mono_detalhe['A (1)']} | Fase B: {fases_mono_detalhe['B (2)']} | Fase C: {fases_mono_detalhe['C (3)']} | Outras: {fases_mono_detalhe['Outras']}")
print(f"   - Bifásicas: {qtd_bi} cargas")
if qtd_bi > 0:
    print(
        f"      * Fases AB: {fases_bi_detalhe['AB (1,2)']} | Fases BC: {fases_bi_detalhe['BC (2,3)']} | Fases CA: {fases_bi_detalhe['CA (1,3)']} | Outras: {fases_bi_detalhe['Outras']}")
print(f"   - Trifásicas: {qtd_tri} cargas")
if qtd_tri > 0:
    print(f"      * Fases ABC: {fases_tri_detalhe['ABC (1,2,3)']} | Outras: {fases_tri_detalhe['Outras']}")

print(f"-> Potência Ativa Instalada nas Cargas: {total_kw:.2f} kW")
print(f"-> Potência Reativa Instalada nas Cargas: {total_kvar:.2f} kvar")

if num_transformers > 0:
    dss.transformers.first()
    nome_trafo = dss.transformers.name
    dss.circuit.set_active_element(f"Transformer.{nome_trafo}")
    fases_trafo = dss.cktelement.num_phases
    tipo_fase_trafo = "Monofásico" if fases_trafo == 1 else "Bifásico" if fases_trafo == 2 else "Trifásico"

    conns_str = dss.text(f"? Transformer.{nome_trafo}.conns").replace('[', '').replace(']', '').replace(' ', '').lower()
    conns_list = conns_str.split(',')


    def traduzir_conn(c):
        if 'w' in c or 'y' in c: return "Estrela (Wye)"
        if 'd' in c: return "Triângulo (Delta)"
        return c.capitalize()


    conn_prim = traduzir_conn(conns_list[0]) if len(conns_list) > 0 else "Desconhecida"
    conn_sec = traduzir_conn(conns_list[1]) if len(conns_list) > 1 else "Desconhecida"
    kva_trafo = dss.transformers.kva

    print(f"\n-> Transformador Principal (Subestação): {nome_trafo}")
    print(f"   - Potência Nominal: {kva_trafo} kVA")
    print(f"   - Fases: {fases_trafo} ({tipo_fase_trafo})")
    print(f"   - Conexão Primário: {conn_prim}")
    print(f"   - Conexão Secundário: {conn_sec}")
else:
    print("\n-> Transformador Principal: NENHUM TRANSFORMADOR ENCONTRADO NO CIRCUITO.")

cargas_info = []
cargas_corrigidas = 0

print("\n" + "=" * 105)
print(" AUDITORIA 0.5: VERIFICAÇÃO E CORREÇÃO ATIVA DE TENSÕES NAS CARGAS E MAPEAMENTO")
print("=" * 105)

nomes_opendss = set()
dss.loads.first()
while True:
    nome = dss.loads.name
    kw = dss.loads.kw
    kv_original = dss.loads.kv

    ramal_id = nome.upper()
    if ramal_id.startswith("BT_"):
        ramal_id = ramal_id[3:]

    nomes_opendss.add(ramal_id)

    dss.circuit.set_active_element(f"Load.{nome}")
    fases = dss.cktelement.num_phases
    barramento = dss.cktelement.bus_names[0]

    conn_raw = dss.text(f"? Load.{nome}.conn").strip().lower()
    tipo_ligacao = "Estrela (Wye)" if "w" in conn_raw else "Triângulo (Delta)"
    tipo_fase = "Monofásico" if fases == 1 else "Bifásico" if fases == 2 else "Trifásico"

    kv_correto = 0.220 if fases > 1 else 0.127

    if abs(kv_original - kv_correto) > 0.005:
        dss.loads.kv = kv_correto
        cargas_corrigidas += 1
        if cargas_corrigidas <= 5:
            print(
                f"    [ALERTA CORRIGIDO] Carga {nome} ({tipo_fase}). Tensão alterada de {kv_original:.3f} kV para {kv_correto:.3f} kV.")

    consumo_medio = dict_excel_consumo.get(ramal_id, None)
    taxa_minima = 0.0
    e_g_mes = 0.0

    if consumo_medio is not None:
        if fases == 1:
            taxa_minima = 30.0
        elif fases == 2:
            taxa_minima = 50.0
        else:
            taxa_minima = 100.0

        e_g_mes = max(consumo_medio - taxa_minima, 0)
        e_g_dia = e_g_mes / 30.0

        if e_g_dia > 0:
            pv_kwp = e_g_dia / (TD * hsp_calculado)
        else:
            pv_kwp = 0.01
    else:
        pv_kwp = kw * 1.5

    cargas_info.append({
        'nome': nome, 'kw': kw, 'fases': fases, 'kv': kv_correto,
        'barramento': barramento, 'tipo': tipo_fase, 'ligacao': tipo_ligacao,
        'pv_kw': pv_kwp,
        'e_med': consumo_medio if consumo_medio is not None else 0.0,
        'taxa_min': taxa_minima,
        'e_g_mes': e_g_mes,
        'td': TD,
        'hsp': hsp_calculado
    })

    if not dss.loads.next(): break

if cargas_corrigidas > 0:
    print(f"\n-> SUCESSO! Foram detectadas e corrigidas as tensões de {cargas_corrigidas} cargas.")
else:
    print("\n-> VERIFICAÇÃO OK! Todas as cargas já possuíam tensões corretas.")

# ==============================================================================
# AUDITORIA 0.75: BATIMENTO DE CARGAS E ESTATÍSTICA DO DIMENSIONAMENTO
# ==============================================================================
print("\n" + "=" * 105)
print(" AUDITORIA 0.75: CRUZAMENTO OPEN-DSS x EXCEL E ANÁLISE DE POTÊNCIA")
print("=" * 105)
print(f"-> Total de Cargas Mapeadas no OpenDSS: {len(nomes_opendss)}")
print(f"   - Monofásicas: {qtd_mono} | Bifásicas: {qtd_bi} | Trifásicas: {qtd_tri}")

faltam_no_excel = nomes_opendss - ramais_excel
faltam_no_opendss = ramais_excel - nomes_opendss

if faltam_no_excel:
    print(f"\n-> ALERTA: {len(faltam_no_excel)} Cargas estão no OpenDSS mas NÃO existem na planilha Excel:")
    lista_faltam_ex = list(faltam_no_excel)
    print(f"   {lista_faltam_ex[:10]} ... (mostrando até 10)")
else:
    print("\n-> SUCESSO: Todas as cargas do OpenDSS foram encontradas na planilha do Excel!")

if faltam_no_opendss:
    print(f"\n-> INFO: {len(faltam_no_opendss)} Ramais estão no Excel mas NÃO existem no modelo do OpenDSS:")
    lista_faltam_dss = sorted(list(faltam_no_opendss))
    for i in range(0, len(lista_faltam_dss), 10):
        print("   " + ", ".join(lista_faltam_dss[i:i + 10]))

df_dimensionamento = pd.DataFrame(cargas_info)
df_dimensionamento['PV_Perc(%)'] = np.where(df_dimensionamento['kw'] > 0.001,
                                            (df_dimensionamento['pv_kw'] / df_dimensionamento['kw']) * 100.0,
                                            np.nan)

print("\n>>> TABELA DE DIMENSIONAMENTO (Amostra de 10 cargas):")
print(df_dimensionamento[['nome', 'kw', 'pv_kw', 'PV_Perc(%)']].head(10).to_string(index=False, float_format="%.3f"))

print("\n>>> ESTATÍSTICA DESCRITIVA DA PENETRAÇÃO RELATIVA (PV vs Carga Instalada):")
print(df_dimensionamento[['PV_Perc(%)']].describe().to_string())

print("\n>>> AUDITORIA DA MEMÓRIA DE CÁLCULO FV (Amostra de 10 cargas):")
print("-> Fórmula ANEEL: PV_kWp = ((E_med - Tx_Min) / 30 dias) / (TD * HSP)")
print("-" * 115)
print(
    f"{'NOME DA CARGA':<15} | {'E_MED(kWh)':<10} | {'DESC.(Tx)':<9} | {'E_GERAR/MÊS':<11} | {'TD':<4} | {'HSP':<4} | {'PV_kWp (INJETADO)'}")
print("-" * 115)
for c in df_dimensionamento.head(10).itertuples():
    if c.e_med == 0.0 and c.taxa_min == 0.0:
        print(
            f"Load.{c.nome:<10} | {'N/A (Falta no Excel) - Usado Regra Antiga de 1.5 * kW':<70} | {c.pv_kw:>10.3f} kW")
    else:
        print(
            f"Load.{c.nome:<10} | {c.e_med:>10.2f} | {c.taxa_min:>9.1f} | {c.e_g_mes:>11.2f} | {c.td:>4.2f} | {c.hsp:>4.2f} | {c.pv_kw:>10.3f} kW")
print("-" * 115)

# ==============================================================================
# PREPARAÇÃO PARA SIMULAÇÕES
# ==============================================================================
random.seed(42)
random.shuffle(cargas_info)
total_cargas = len(cargas_info)

cenarios_fv = {pl: cargas_info[0: int(total_cargas * (pl / 100.0))] for pl in niveis_penetracao}

passos = 96
tempo_horas = np.linspace(0.25, 24, passos)
passo_alvo = 48

historico_plot = {
    'A': {'P_tot': {}, 'Q_tot': {}, 'S_tot': {}, 'P_fase_A': {}, 'P_fase_B': {}, 'P_fase_C': {},
          'Losses_kW': {}, 'Losses_kvar': {}, 'boxplot_v': [], 'boxplot_fd_iec': [],
          'tensoes_pu': {}, 'fd_iec': {}, 'linhas': {}, 'cargas_bus': {}, 'pvs_bus': {}},
    'B': {'P_tot': {}, 'Q_tot': {}, 'S_tot': {}, 'P_fase_A': {}, 'P_fase_B': {}, 'P_fase_C': {},
          'Losses_kW': {}, 'Losses_kvar': {}, 'boxplot_v': [], 'boxplot_fd_iec': [],
          'tensoes_pu': {}, 'fd_iec': {}, 'linhas': {}, 'cargas_bus': {}, 'pvs_bus': {}}
}

limite_prodist = 3.0

# ==============================================================================
# LÓGICA DE EXECUÇÃO: RODA TODO O CÓDIGO PARA O CASO A E DEPOIS PARA O CASO B
# ==============================================================================
for caso in ['A', 'B']:

    print("\n" + "*" * 115)
    if caso == 'A':
        print(f" INICIANDO SIMULAÇÕES: CASO A (FV conectada com as mesmas fases da carga) ".center(115, '*'))
    else:
        print(f" INICIANDO SIMULAÇÕES: CASO B (FV forçada como Trifásica independente da carga) ".center(115, '*'))
    print("*" * 115)

    dados_boxplot_tensoes = []
    dados_boxplot_fd_iec = []
    labels_boxplot = []

    hist_V_pu = {}
    hist_V_pu_A = {}
    hist_V_pu_B = {}
    hist_V_pu_C = {}

    hist_P_tot, hist_Q_tot, hist_S_tot = {}, {}, {}
    hist_P_fase_A, hist_P_fase_B, hist_P_fase_C = {}, {}, {}
    hist_Losses_kW, hist_Losses_kvar = {}, {}
    hist_FD_iec = {}

    for pl in niveis_penetracao:
        print("\n" + "=" * 105)
        print(f" INICIANDO CENÁRIO DE PENETRAÇÃO (PL): {pl}% - CASO {caso}")
        print("=" * 105)

        dss.text(f"Compile '{caminho_master}'")
        limpar_elementos_conflitantes()
        cargas_selecionadas = cenarios_fv[pl]

        if caso == 'B':
            buses_alvo = [c['barramento'].split('.')[0] for c in cargas_selecionadas]
            ramais_alterados = adequar_ramais_ligacao_especificos(buses_alvo)
            auditoria_topologia_ramais(ramais_alterados)
            dss.text("CalcVoltageBases")

        dss.loads.first()
        while True:
            fases = dss.cktelement.num_phases
            dss.loads.kv = 0.220 if fases > 1 else 0.127
            if not dss.loads.next(): break

        for linha in curvas_fv.strip().split('\n'):
            if linha.strip() and not linha.startswith('!'): dss.text(linha)

        for c in cargas_selecionadas:
            potencia_fv = c['pv_kw']

            if caso == 'A':
                comando_pv = (f"New PVSystem.PV_{c['nome']} phases={c['fases']} conn=Wye bus1={c['barramento']} "
                              f"kV={c['kv']} kVA={potencia_fv} irrad=1 Pmpp={potencia_fv} temperature=25 "
                              f"PF=1 effcurve=MyEff P-TCurve=MyPvsT Daily=MyIrrad Tdaily=MyTemp")
            else:
                barra_tri = c['barramento'].split('.')[0] + ".1.2.3.4"
                comando_pv = (f"New PVSystem.PV_{c['nome']} phases=3 conn=Wye bus1={barra_tri} "
                              f"kV=0.220 kVA={potencia_fv} irrad=1 Pmpp={potencia_fv} temperature=25 "
                              f"PF=1 effcurve=MyEff P-TCurve=MyPvsT Daily=MyIrrad Tdaily=MyTemp")
            dss.text(comando_pv)

        print("-" * 105)
        print(" AUDITORIA 1.5: CHECAGEM DE INTEGRIDADE DA MEMÓRIA BEFORE FLUXO DE POTÊNCIA")
        print("-" * 105)

        falhas_encontradas = 0
        dss.loads.first()
        while True:
            fases = dss.cktelement.num_phases
            kv_memoria = dss.loads.kv
            kv_esperado = 0.220 if fases > 1 else 0.127
            if abs(kv_memoria - kv_esperado) > 0.005: falhas_encontradas += 1
            if not dss.loads.next(): break

        if falhas_encontradas == 0:
            print("    -> SUCESSO: A memória do OpenDSS foi varrida e TODAS as cargas mantêm as tensões corrigidas.")
        else:
            print(f"    -> ERRO CRÍTICO: A correção se perdeu in {falhas_encontradas} cargas!")

        total_pvs = dss.pvsystems.count
        print(f"\n-> Status da Memória OpenDSS: {total_pvs} PVSystems injetados e ativos.")

        if total_pvs > 0:
            print("-" * 105)
            print(" AUDITORIA 2: AMOSTRA DE PVS CONECTADOS (MONO/BI/TRIFÁSICOS E TIPO DE LIGAÇÃO)")
            print(
                f"{'NOME DO PV':<18} | {'Pmpp (kW)':<10} | {'TENSÃO(kV)':<10} | {'TIPO':<12} | {'LIGAÇÃO':<15} | {'BARRA'}")
            print("-" * 105)

            dss.pvsystems.first()
            exemplos_pvs = {1: 0, 2: 0, 3: 0}

            while True:
                nome_pv = dss.pvsystems.name
                kw_pv = dss.pvsystems.pmpp
                dss.circuit.set_active_element(f"PVSystem.{nome_pv}")
                fases_pv = dss.cktelement.num_phases
                barramento_pv = dss.cktelement.bus_names[0]
                kv_pv = float(dss.text(f"? PVSystem.{nome_pv}.kV"))
                conn_pv_raw = dss.text(f"? PVSystem.{nome_pv}.conn").strip().lower()
                tipo_ligacao = "Estrela (Wye)" if "w" in conn_pv_raw else "Triângulo (Delta)"
                tipo_pv = "Monofásico" if fases_pv == 1 else "Bifásico" if fases_pv == 2 else "Trifásico"

                if exemplos_pvs.get(fases_pv, 0) < 3:
                    print(
                        f"PVSystem.{nome_pv:<9} | {kw_pv:>6.2f} kW | {kv_pv:<10.3f} | {tipo_pv:<12} | {tipo_ligacao:<15} | {barramento_pv}")
                    exemplos_pvs[fases_pv] = exemplos_pvs.get(fases_pv, 0) + 1

                if sum(exemplos_pvs.values()) >= 9 or not dss.pvsystems.next(): break

        barras_trifasicas = []
        for b in dss.circuit.buses_names:
            dss.circuit.set_active_bus(b)
            nodos = list(dss.bus.nodes)
            if 1 in nodos and 2 in nodos and 3 in nodos:
                barras_trifasicas.append(b)

        dss.text("Set mode=daily stepsize=15m number=1")
        dss.text("Reset")

        P_tot_lista, Q_tot_lista, S_tot_lista = [], [], []
        P_fase_A, P_fase_B, P_fase_C = [], [], []
        Losses_kW_lista, Losses_kvar_lista = [], []

        nos_rede = dss.circuit.nodes_names
        tensoes_pu = {no: [] for no in nos_rede}

        fd_por_barra_iec = {b: [] for b in barras_trifasicas}

        buses_circuit = [b.lower() for b in dss.circuit.buses_names]
        hist_cargas_bus_pl = {b: [] for b in buses_circuit}
        hist_pvs_bus_pl = {b: [] for b in buses_circuit}
        hist_linhas_pl = {}

        print(f"\n   [Processando fluxo de potência in 96 passos para PL {pl}%...]")

        dss.transformers.first()
        trafo_subestacao = dss.transformers.name

        for i in range(passos):
            dss.solution.solve()

            dss.circuit.set_active_element(f"Transformer.{trafo_subestacao}")
            pot_trafo = dss.cktelement.powers
            condutores_por_terminal = dss.cktelement.num_conductors

            idx_sec = condutores_por_terminal * 2

            p_a = -pot_trafo[idx_sec + 0]
            p_b = -pot_trafo[idx_sec + 2]
            p_c = -pot_trafo[idx_sec + 4]

            q_a = -pot_trafo[idx_sec + 1]
            q_b = -pot_trafo[idx_sec + 3]
            q_c = -pot_trafo[idx_sec + 5]

            p_t = p_a + p_b + p_c
            q_t = q_a + q_b + q_c
            s_t = np.sqrt(p_t ** 2 + q_t ** 2)

            P_tot_lista.append(p_t)
            Q_tot_lista.append(q_t)
            S_tot_lista.append(s_t)

            P_fase_A.append(p_a)
            P_fase_B.append(p_b)
            P_fase_C.append(p_c)

            perdas_sistema = dss.circuit.losses
            perdas_kw = perdas_sistema[0] / 1000.0
            perdas_kvar = perdas_sistema[1] / 1000.0
            Losses_kW_lista.append(perdas_kw)
            Losses_kvar_lista.append(perdas_kvar)

            for no, v in zip(nos_rede, dss.circuit.buses_vmag_pu):
                if v > 0.1:
                    tensoes_pu[no].append(v)

            for b in barras_trifasicas:
                dss.circuit.set_active_bus(b)
                nodos = list(dss.bus.nodes)
                vmags = dss.bus.vmag_angle[0::2]
                vangs = dss.bus.vmag_angle[1::2]

                idx_a = nodos.index(1)
                idx_b = nodos.index(2)
                idx_c = nodos.index(3)

                va, vb, vc = vmags[idx_a], vmags[idx_b], vmags[idx_c]
                ang_a, ang_b, ang_c = vangs[idx_a], vangs[idx_b], vangs[idx_c]

                if va > 0.1 and vb > 0.1 and vc > 0.1:
                    V_a_cplx = va * np.exp(1j * np.radians(ang_a))
                    V_b_cplx = vb * np.exp(1j * np.radians(ang_b))
                    V_c_cplx = vc * np.exp(1j * np.radians(ang_c))

                    a = np.exp(1j * np.radians(120))
                    a2 = np.exp(1j * np.radians(240))

                    V_pos = (V_a_cplx + a * V_b_cplx + a2 * V_c_cplx) / 3.0
                    V_neg = (V_a_cplx + a2 * V_b_cplx + a * V_c_cplx) / 3.0

                    v_pos_mag = abs(V_pos)
                    v_neg_mag = abs(V_neg)

                    fd_iec = (v_neg_mag / v_pos_mag) * 100.0 if v_pos_mag > 0.1 else 0.0
                    fd_por_barra_iec[b].append(fd_iec)
                else:
                    pass

            dss.lines.first()
            while True:
                nome_linha = dss.lines.name.lower()
                nodes = dss.cktelement.node_order
                powers = dss.cktelement.powers[0: dss.cktelement.num_phases * 2: 2]
                p_fases = {1: 0.0, 2: 0.0, 3: 0.0}
                for n, p_val in zip(nodes, powers):
                    if n in [1, 2, 3]: p_fases[n] = p_val
                if nome_linha not in hist_linhas_pl:
                    hist_linhas_pl[nome_linha] = []
                hist_linhas_pl[nome_linha].append([p_fases[1], p_fases[2], p_fases[3]])
                if not dss.lines.next(): break

            load_step = {b: [0.0, 0.0, 0.0] for b in buses_circuit}
            dss.loads.first()
            while True:
                b_name = dss.cktelement.bus_names[0].split('.')[0].lower()
                if b_name in load_step:
                    nodes = dss.cktelement.node_order
                    powers = dss.cktelement.powers[0: dss.cktelement.num_phases * 2: 2]
                    for n, p_val in zip(nodes, powers):
                        if n in [1, 2, 3]:
                            load_step[b_name][n - 1] += p_val
                if not dss.loads.next(): break
            for b in buses_circuit:
                hist_cargas_bus_pl[b].append(load_step[b])

            pv_step = {b: [0.0, 0.0, 0.0] for b in buses_circuit}
            if dss.pvsystems.count > 0:
                dss.pvsystems.first()
                while True:
                    b_name = dss.cktelement.bus_names[0].split('.')[0].lower()
                    if b_name in pv_step:
                        nodes = dss.cktelement.node_order
                        powers = dss.cktelement.powers[0: dss.cktelement.num_phases * 2: 2]
                        for n, p_val in zip(nodes, powers):
                            if n in [1, 2, 3]:
                                pv_step[b_name][n - 1] += (-p_val)
                    if not dss.pvsystems.next(): break
            for b in buses_circuit:
                hist_pvs_bus_pl[b].append(pv_step[b])

            if i == 48:
                print(f"\n   >>> AUDITORIA 3: SNAPSHOT DO PASSO {i} (Aprox. 12:00h - Pico Solar) <<<")
                print(
                    f"   Potência na Subestação -> P Total: {p_t:.2f} kW | Q Total: {q_t:.2f} kvar | S Total: {s_t:.2f} kVA")
                print(f"   PERDAS TÉCNICAS TOTAIS -> Ativa: {perdas_kw:.3f} kW | Reativa: {perdas_kvar:.3f} kvar")

        print(f"   [Simulação {pl}% concluída com sucesso.]\n")

        historico_plot[caso]['linhas'][pl] = hist_linhas_pl
        historico_plot[caso]['cargas_bus'][pl] = hist_cargas_bus_pl
        historico_plot[caso]['pvs_bus'][pl] = hist_pvs_bus_pl

        historico_plot[caso]['tensoes_pu'][pl] = copy.deepcopy(tensoes_pu)
        historico_plot[caso]['fd_iec'][pl] = copy.deepcopy(fd_por_barra_iec)

        hist_P_tot[pl] = P_tot_lista
        hist_Q_tot[pl] = Q_tot_lista
        hist_S_tot[pl] = S_tot_lista
        hist_P_fase_A[pl] = P_fase_A
        hist_P_fase_B[pl] = P_fase_B
        hist_P_fase_C[pl] = P_fase_C
        hist_Losses_kW[pl] = Losses_kW_lista
        hist_Losses_kvar[pl] = Losses_kvar_lista

        print("=" * 105)
        print(f" AUDITORIA 5: VIOLAÇÕES DE TENSÃO E DESEQUILÍBRIO - CENÁRIO {pl}%")
        print("=" * 105)

        nos_fase = [no for no in nos_rede if no.endswith(('.1', '.2', '.3'))]
        barras_subtensao = set()
        barras_sobretensao = set()

        detalhes_sobretensao_fases = {}

        todas_tensoes_do_cenario = []
        tensoes_A_cenario = []
        tensoes_B_cenario = []
        tensoes_C_cenario = []

        for no in nos_fase:
            valores_no = tensoes_pu[no]
            if len(valores_no) > 0:
                todas_tensoes_do_cenario.extend(valores_no)
                nome_barra = no.split('.')[0]
                fase_num = no.split('.')[-1]
                fase_letra = 'A' if fase_num == '1' else 'B' if fase_num == '2' else 'C' if fase_num == '3' else fase_num

                if no.endswith('.1'):
                    tensoes_A_cenario.extend(valores_no)
                elif no.endswith('.2'):
                    tensoes_B_cenario.extend(valores_no)
                elif no.endswith('.3'):
                    tensoes_C_cenario.extend(valores_no)

                if min(valores_no) < 0.92: barras_subtensao.add(nome_barra)
                if max(valores_no) > 1.05:
                    barras_sobretensao.add(nome_barra)
                    if nome_barra not in detalhes_sobretensao_fases:
                        detalhes_sobretensao_fases[nome_barra] = set()
                    detalhes_sobretensao_fases[nome_barra].add(fase_letra)

        dados_boxplot_tensoes.append(todas_tensoes_do_cenario)

        hist_V_pu[pl] = todas_tensoes_do_cenario
        hist_V_pu_A[pl] = tensoes_A_cenario
        hist_V_pu_B[pl] = tensoes_B_cenario
        hist_V_pu_C[pl] = tensoes_C_cenario

        todas_fd_iec_do_cenario = []
        for v_fd in fd_por_barra_iec.values(): todas_fd_iec_do_cenario.extend(v_fd)
        dados_boxplot_fd_iec.append(todas_fd_iec_do_cenario)
        hist_FD_iec[pl] = todas_fd_iec_do_cenario

        labels_boxplot.append(f"{pl}%")

        if barras_subtensao:
            print(f"-> SUBTENSÃO (< 0.92 p.u.): Identificada in {len(barras_subtensao)} barras.")
        else:
            print("-> SUBTENSÃO (< 0.92 p.u.): OK! Nenhuma barra apresentou violação.")

        if barras_sobretensao:
            print(f"\n-> SOBRETENSÃO (> 1.05 p.u.): Identificada in {len(barras_sobretensao)} barras.")
            print(f"{'BARRA VIOLADA':<25} | {'FASES COM SOBRETENSÃO'}")
            print("-" * 55)
            for b_rep in sorted(list(barras_sobretensao)):
                fases_str = ", ".join(sorted(list(detalhes_sobretensao_fases[b_rep])))
                print(f"{b_rep:<25} | {fases_str}")
        else:
            print("\n-> SOBRETENSÃO (> 1.05 p.u.): OK! Nenhuma barra apresentou violação.")

        print("\n" + "=" * 105)
        print(f" ANÁLISE DE TENDÊNCIA DE DESEQUILÍBRIO (Métrica Módulo 8 PRODIST) - CENÁRIO {pl}%")
        print("=" * 105)

        barras_reprovadas_iec = []

        for b in barras_trifasicas:
            if len(fd_por_barra_iec[b]) > 0:
                fd95_iec = np.percentile(fd_por_barra_iec[b], 95)
                if fd95_iec > limite_prodist:
                    barras_reprovadas_iec.append((b, fd95_iec))

        print(
            f"[AVISO ACADÉMICO: A simulação de 24h não atende à exigência legal de medição contínua de 168h do PRODIST. Os resultados abaixo atestam apenas a TENDÊNCIA de impacto fotovoltaico no desequilíbrio.]")
        print(f"[MÉTODO IEC - PRODIST / COMPONENTES SIMÉTRICAS]")
        print(
            f"-> Status de Tendência: Das {len(barras_trifasicas)} barras avaliadas, {len(barras_reprovadas_iec)} indicam tendência de Violação (> {limite_prodist}%).")
        if len(barras_reprovadas_iec) > 0:
            print(f"{'BARRA REPROVADA':<25} | {'FD95% (IEC)':<15} | {'DIAGNÓSTICO (TENDÊNCIA)'}")
            print("-" * 75)
            for b_rep, val in barras_reprovadas_iec:
                print(f"{b_rep:<25} | {val:>7.3f} %       | TENDÊNCIA ACIMA DA NORMA")
        else:
            print("   >>> REDE ESTABLE (IEC): Nenhuma barra violou o limite de tendência neste cenário. <<<")
        print("=" * 105 + "\n")

    print("\n" + "=" * 115)
    print(f" 6. RESUMO ESTATÍSTICO CONSOLIDADO E PADRONIZADO - CASO {caso} ")
    print("=" * 115)


    def gerar_tabela_estatistica(dicionario_hist, titulo):
        df = pd.DataFrame({f"{k}% FV": pd.Series(v) for k, v in dicionario_hist.items()})
        stats = df.describe(percentiles=[.01, .05, .25, .5, .75, .95, .99]).T
        stats['skewness'] = df.skew()
        stats['kurtosis'] = df.kurt()
        print(f"\n>>> TABELA: {titulo}")
        print(stats.map(lambda x: f"{x:.4f}").to_string())
        return stats


    gerar_tabela_estatistica(hist_V_pu, "Tensões Medidas in Todas as Fases (p.u.)")
    gerar_tabela_estatistica(hist_V_pu_A, "Tensões Medidas - Fase A (p.u.)")
    gerar_tabela_estatistica(hist_V_pu_B, "Tensões Medidas - Fase B (p.u.)")
    gerar_tabela_estatistica(hist_V_pu_C, "Tensões Medidas - Fase C (p.u.)")

    gerar_tabela_estatistica(hist_FD_iec, "Fator de Desequilíbrio de Tensão - FD (%) [MÉTODO IEC / PRODIST]")

    gerar_tabela_estatistica(hist_P_tot, "Potência Ativa Total na Subestação (kW)")
    gerar_tabela_estatistica(hist_Q_tot, "Potência Reativa Total na Subestação (kvar)")
    gerar_tabela_estatistica(hist_S_tot, "Potência Aparente Total na Subestação (kVA)")

    gerar_tabela_estatistica(hist_P_fase_A, "Potência Ativa - Fase A (kW)")
    gerar_tabela_estatistica(hist_P_fase_B, "Potência Ativa - Fase B (kW)")
    gerar_tabela_estatistica(hist_P_fase_C, "Potência Ativa - Fase C (kW)")

    gerar_tabela_estatistica(hist_Losses_kW, "Perdas Técnicas Ativas Totais (kW)")
    gerar_tabela_estatistica(hist_Losses_kvar, "Perdas Técnicas Reativas Totais (kvar)")

    historico_plot[caso]['P_tot'] = hist_P_tot
    historico_plot[caso]['Q_tot'] = hist_Q_tot
    historico_plot[caso]['S_tot'] = hist_S_tot
    historico_plot[caso]['P_fase_A'] = hist_P_fase_A
    historico_plot[caso]['P_fase_B'] = hist_P_fase_B
    historico_plot[caso]['P_fase_C'] = hist_P_fase_C
    historico_plot[caso]['Losses_kW'] = hist_Losses_kW
    historico_plot[caso]['Losses_kvar'] = hist_Losses_kvar
    historico_plot[caso]['boxplot_v'] = dados_boxplot_tensoes
    historico_plot[caso]['boxplot_fd_iec'] = dados_boxplot_fd_iec

# ==============================================================================
# NOVA SEÇÃO: 7. CÁLCULO DA HOSTING CAPACITY (HC)
# ==============================================================================
print("\n" + "=" * 115)
print(" 7. CÁLCULO DA HOSTING CAPACITY (HC) - CAPACIDADE DE HOSPEDAGEM ")
print("=" * 115)
print("-> Metodologia: A Hosting Capacity é o nível máximo de penetração fotovoltaica seguro.")
print(f"-> Limite de Tensão: 0.92 a 1.05 p.u. | Limite de Desequilíbrio (PRODIST): {limite_prodist}% (Percentil 95)\n")

for caso in ['A', 'B']:
    hc_tensao = 100
    hc_fd = 100

    for pl in niveis_penetracao:
        violou_v = False
        tensoes_cenario = historico_plot[caso]['tensoes_pu'][pl]
        for no, valores in tensoes_cenario.items():
            if len(valores) > 0:
                if min(valores) < 0.92 or max(valores) > 1.05:
                    violou_v = True
                    break
        if violou_v:
            idx = niveis_penetracao.index(pl)
            hc_tensao = niveis_penetracao[idx - 1] if idx > 0 else 0
            break

    for pl in niveis_penetracao:
        violou_fd = False
        fd_cenario = historico_plot[caso]['fd_iec'][pl]
        for barra, valores in fd_cenario.items():
            if len(valores) > 0:
                fd95 = np.percentile(valores, 95)
                if fd95 > limite_prodist:
                    violou_fd = True
                    break
        if violou_fd:
            idx = niveis_penetracao.index(pl)
            hc_fd = niveis_penetracao[idx - 1] if idx > 0 else 0
            break

    hc_global = hc_tensao

    str_hc_tensao = f"{hc_tensao}% (ou superior)" if hc_tensao == 100 else f"{hc_tensao}%"
    str_hc_fd = f"{hc_fd}% (ou superior)" if hc_fd == 100 else f"{hc_fd}%"
    str_hc_global = f"{hc_global}% (ou superior)" if hc_global == 100 else f"{hc_global}%"

    print(f"[CENÁRIO DA REDE - CASO {caso}]")
    print(f"   -> HC por Tensão (Métrica 1): {str_hc_tensao}")
    print(f"   -> HC por Desequilíbrio (Métrica 2 - IEC): {str_hc_fd}")
    print(f"   -> HOSTING CAPACITY GLOBAL: {str_hc_global}\n")

# ==============================================================================
# NOVA SEÇÃO: PLOTS UNIFICADOS (CASO A vs CASO B) E SALVAMENTO AUTOMÁTICO
# ==============================================================================
print("=" * 60)
print(" SALVANDO GRÁFICOS UNIFICADOS PADRÃO CBA/IFAC... ")
print("=" * 60)

pasta_saida = "Graficos_Artigo_Alta_Res"
os.makedirs(pasta_saida, exist_ok=True)
print(f"-> Pasta de destino criada: {os.path.abspath(pasta_saida)}")

# --- Ajuste 1: Chave Mestra para Desligar todos os Títulos Gerais ---
EXIBIR_TITULO_GERAL = False

# --- Ajustes Globais de Estilo para Publicação CBA/IFAC ---
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman'],
    'mathtext.fontset': 'stix',
    'font.size': 32,
    'axes.titlesize': 38,
    'axes.labelsize': 36,
    'xtick.labelsize': 30,
    'ytick.labelsize': 30,
    'legend.fontsize': 30,
    'figure.titlesize': 42,
    'lines.linewidth': 4.0
})

# --- PROCESSAMENTO EXTRATO DE PERDAS DE ENERGIA TOTAIS DIÁRIAS (kWh, kvarh, kVAh) ---
for caso in ['A', 'B']:
    historico_plot[caso]['E_loss_kW'] = {}
    historico_plot[caso]['E_loss_kvar'] = {}
    historico_plot[caso]['E_loss_kVA'] = {}
    for pl in niveis_penetracao:
        p_losses = np.array(historico_plot[caso]['Losses_kW'][pl])
        q_losses = np.array(historico_plot[caso]['Losses_kvar'][pl])
        # Integração numérica (Soma * delta_t onde delta_t = 15 min / 60 min = 0.25 h)
        historico_plot[caso]['E_loss_kW'][pl] = np.sum(p_losses) * 0.25
        historico_plot[caso]['E_loss_kvar'][pl] = np.sum(q_losses) * 0.25
        historico_plot[caso]['E_loss_kVA'][pl] = np.sum(np.sqrt(p_losses ** 2 + q_losses ** 2)) * 0.25

cores_cenarios = {
    0: '#000080', 10: '#0000cd', 20: '#0000ff', 30: '#0080ff', 40: '#00ffff',
    50: '#00ff80', 60: '#00ff00', 70: '#80ff00', 80: '#ffff00', 90: '#ff8000', 100: '#ff0000'
}

# ------------------------------------------------------------------------------
# 1. BOXPLOTS: TENSÕES E FD% (LADO A LADO)
# ------------------------------------------------------------------------------
fig_bx_v, ax_bx_v = plt.subplots(figsize=(16, 10))
pos_A = np.arange(len(niveis_penetracao)) * 2.0 - 0.4
pos_B = np.arange(len(niveis_penetracao)) * 2.0 + 0.4

dados_v_A = [d if len(d) > 0 else [0] for d in historico_plot['A']['boxplot_v']]
dados_v_B = [d if len(d) > 0 else [0] for d in historico_plot['B']['boxplot_v']]

bp_A_v = ax_bx_v.boxplot(dados_v_A, positions=pos_A, widths=0.6, patch_artist=True,
                         boxprops=dict(facecolor='#1f77b4', alpha=0.7),
                         flierprops=dict(marker='o', markersize=2, alpha=0.3))
bp_B_v = ax_bx_v.boxplot(dados_v_B, positions=pos_B, widths=0.6, patch_artist=True,
                         boxprops=dict(facecolor='#ff7f0e', alpha=0.7),
                         flierprops=dict(marker='o', markersize=2, alpha=0.3))

ax_bx_v.axhline(y=1.05, color='r', linestyle='--', linewidth=3.0, label='Lim. Sup. (1.05 p.u.)')
ax_bx_v.axhline(y=0.92, color='r', linestyle='--', linewidth=3.0, label='Lim. Inf. (0.92 p.u.)')
ax_bx_v.set_xticks(np.arange(len(niveis_penetracao)) * 2.0)
ax_bx_v.set_xticklabels([f"{p}%" for p in niveis_penetracao])
if EXIBIR_TITULO_GERAL: ax_bx_v.set_title('Evolução da Dispersão de Tensão por Nível de Penetração FV')
ax_bx_v.set_xlabel('Nível de Penetração FV (%)')
ax_bx_v.set_ylabel('Tensão (p.u.)')
ax_bx_v.yaxis.set_major_locator(ticker.MaxNLocator(10))
ax_bx_v.grid(True, linestyle='--', alpha=0.7)

ax_bx_v.legend([bp_A_v["boxes"][0], bp_B_v["boxes"][0]], ['Caso A', 'Caso B'],
               loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=2)
fig_bx_v.tight_layout(rect=[0, 0.20, 1, 1])
fig_bx_v.savefig(os.path.join(pasta_saida, "1_Boxplot_Tensoes.png"), dpi=300, bbox_inches='tight')
plt.close(fig_bx_v)

# Boxplot FD% - IEC
fig_bx_fd_iec, ax_bx_fd_iec = plt.subplots(figsize=(16, 10))
dados_fd_iec_A = [d if len(d) > 0 else [0] for d in historico_plot['A']['boxplot_fd_iec']]
dados_fd_iec_B = [d if len(d) > 0 else [0] for d in historico_plot['B']['boxplot_fd_iec']]

bp_A_fd_iec = ax_bx_fd_iec.boxplot(dados_fd_iec_A, positions=pos_A, widths=0.6, patch_artist=True,
                                   boxprops=dict(facecolor='#1f77b4', alpha=0.7),
                                   flierprops=dict(marker='o', markersize=2, alpha=0.3))
bp_B_fd_iec = ax_bx_fd_iec.boxplot(dados_fd_iec_B, positions=pos_B, widths=0.6, patch_artist=True,
                                   boxprops=dict(facecolor='#ff7f0e', alpha=0.7),
                                   flierprops=dict(marker='o', markersize=2, alpha=0.3))

perc95_A_iec = [np.percentile(d, 95) if len(d) > 0 else 0 for d in dados_fd_iec_A]
perc95_B_iec = [np.percentile(d, 95) if len(d) > 0 else 0 for d in dados_fd_iec_B]
ax_bx_fd_iec.scatter(pos_A, perc95_A_iec, color='green', marker='*', s=300, zorder=5)
ax_bx_fd_iec.scatter(pos_B, perc95_B_iec, color='green', marker='*', s=300, zorder=5)

ax_bx_fd_iec.axhline(y=limite_prodist, color='black', linestyle='--', linewidth=3.0,
                     label=f'Lim. PRODIST ({limite_prodist}%)')
ax_bx_fd_iec.set_xticks(np.arange(len(niveis_penetracao)) * 2.0)
ax_bx_fd_iec.set_xticklabels([f"{p}%" for p in niveis_penetracao])
if EXIBIR_TITULO_GERAL: ax_bx_fd_iec.set_title('Dispersão do Desequilíbrio de Tensão - MÉTODO IEC (PRODIST)')
ax_bx_fd_iec.set_xlabel('Nível de Penetração FV (%)')
ax_bx_fd_iec.set_ylabel('Fator de Desequilíbrio (%)')
ax_bx_fd_iec.yaxis.set_major_locator(ticker.MaxNLocator(10))
ax_bx_fd_iec.grid(True, linestyle='--', alpha=0.7)

perc_marker_iec = plt.Line2D([0], [0], color='w', marker='*', markerfacecolor='green', markeredgecolor='green',
                             markersize=15)
ax_bx_fd_iec.legend([bp_A_fd_iec["boxes"][0], bp_B_fd_iec["boxes"][0], perc_marker_iec],
                    ['Caso A', 'Caso B', '95º Percentil'],
                    loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=3)
fig_bx_fd_iec.tight_layout(rect=[0, 0.20, 1, 1])
fig_bx_fd_iec.savefig(os.path.join(pasta_saida, "2_Boxplot_FD_IEC.png"), dpi=300, bbox_inches='tight')
plt.close(fig_bx_fd_iec)


# ------------------------------------------------------------------------------
# FUNÇÃO AUXILIAR PARA SINCRONIZAR EIXOS Y
# ------------------------------------------------------------------------------
def sincronizar_eixos_y(axs):
    ymin_global = float('inf')
    ymax_global = float('-inf')
    for ax in axs.flat:
        ylim = ax.get_ylim()
        if ylim[0] < ymin_global:
            ymin_global = ylim[0]
        if ylim[1] > ymax_global:
            ymax_global = ylim[1]
    for ax in axs.flat:
        ax.set_ylim(ymin_global, ymax_global)


# ------------------------------------------------------------------------------
# 2. GRÁFICOS DE LINHA: TOTAIS (P, Q, S)
# ------------------------------------------------------------------------------
fig_tot, axs_tot = plt.subplots(2, 3, figsize=(26, 16))
if EXIBIR_TITULO_GERAL: fig_tot.suptitle('Evolução das Potências Totais (P, Q, S) - Comparação Casos A e B')
limite_potencia = 75.0
titulos_tot = ['Potência Ativa Total', 'Potência Reativa Total', 'Potência Aparente Total']
ylabels_tot = ['Potência Ativa (kW)', 'Potência Reativa (kvar)', 'Potência Aparente (kVA)']

for row, c in enumerate(['A', 'B']):
    for pl in niveis_penetracao:
        axs_tot[row, 0].plot(tempo_horas, historico_plot[c]['P_tot'][pl], color=cores_cenarios[pl], label=f'{pl}% FV')
        axs_tot[row, 1].plot(tempo_horas, historico_plot[c]['Q_tot'][pl], color=cores_cenarios[pl], label=f'{pl}% FV')
        axs_tot[row, 2].plot(tempo_horas, historico_plot[c]['S_tot'][pl], color=cores_cenarios[pl], label=f'{pl}% FV')

    for col in range(3):
        axs_tot[row, col].set_title(f'Caso {c} - {titulos_tot[col]}')
        axs_tot[row, col].set_xlabel('Tempo (h)')
        axs_tot[row, col].set_ylabel(ylabels_tot[col])
        axs_tot[row, col].set_xlim(0, 24)
        axs_tot[row, col].set_xticks(np.arange(0, 25, 2))
        axs_tot[row, col].yaxis.set_major_locator(ticker.MaxNLocator(8))
        axs_tot[row, col].grid(True, linestyle='--', alpha=0.7)

    axs_tot[row, 2].axhline(y=limite_potencia, color='black', linestyle='--', linewidth=3.0,
                            label=f'Pot. Nom. ({limite_potencia})')

sincronizar_eixos_y(axs_tot[:, 0:1])
sincronizar_eixos_y(axs_tot[:, 1:2])
sincronizar_eixos_y(axs_tot[:, 2:3])

handles, labels = axs_tot[0, 2].get_legend_handles_labels()
fig_tot.legend(handles, labels, loc='lower center', ncol=6, bbox_to_anchor=(0.5, 0.02))

fig_tot.tight_layout(rect=[0, 0.16, 1, 0.92])
fig_tot.subplots_adjust(hspace=0.7, wspace=0.5)
fig_tot.savefig(os.path.join(pasta_saida, "3_Potencias_Totais.png"), dpi=300, bbox_inches='tight')
plt.close(fig_tot)

# ------------------------------------------------------------------------------
# 3. GRÁFICOS DE LINHA: POTÊNCIA POR FASE (A, B, C)
# ------------------------------------------------------------------------------
fig_fase, axs_fase = plt.subplots(3, 2, figsize=(20, 24))
if EXIBIR_TITULO_GERAL: fig_fase.suptitle('Evolução da Potência Ativa por Fase - Comparação Casos A e B')

for col, c in enumerate(['A', 'B']):
    for row, f_key in enumerate(['P_fase_A', 'P_fase_B', 'P_fase_C']):
        ax = axs_fase[row, col]
        for pl in niveis_penetracao:
            ax.plot(tempo_horas, historico_plot[c][f_key][pl], color=cores_cenarios[pl], label=f'{pl}% FV')

        if row == 0:
            ax.set_title(f'a) Caso A' if c == 'A' else 'b) Caso B', fontsize=38, pad=20)
        else:
            ax.set_title('')

        fase_nome = f_key[-1]
        ax.text(0.5, 0.95, f'Fase {fase_nome}', transform=ax.transAxes, ha='center', va='top',
                fontsize=36, bbox=dict(facecolor='white', alpha=0.8, edgecolor='none', pad=2))

        ax.set_xlabel('Tempo (h)')
        if col == 0:
            ax.set_ylabel('Potência Ativa (kW)')
        else:
            ax.set_ylabel('')

        ax.set_xlim(0, 24)
        ax.set_xticks(np.arange(0, 25, 2))
        ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
        ax.grid(True, linestyle='--', alpha=0.7)

sincronizar_eixos_y(axs_fase)

handles, labels = axs_fase[0, 0].get_legend_handles_labels()
fig_fase.legend(handles, labels, loc='lower center', ncol=4, bbox_to_anchor=(0.5, 0.05), frameon=False)

fig_fase.tight_layout(rect=[0, 0.18, 1, 1.0])
fig_fase.subplots_adjust(hspace=0.25, wspace=0.15)
fig_fase.savefig(os.path.join(pasta_saida, "4_Potencia_Por_Fase.png"), dpi=300, bbox_inches='tight')
plt.close(fig_fase)

# ------------------------------------------------------------------------------
# 4. GRÁFICOS DE LINHA: PERDAS (Ativa e Reativa)
# ------------------------------------------------------------------------------
fig_loss, axs_loss = plt.subplots(2, 2, figsize=(20, 16))
if EXIBIR_TITULO_GERAL: fig_loss.suptitle('Evolução das Perdas Técnicas Totais do Sistema - Comparação Casos A e B')

for col, c in enumerate(['A', 'B']):
    for pl in niveis_penetracao:
        axs_loss[0, col].plot(tempo_horas, historico_plot[c]['Losses_kW'][pl], color=cores_cenarios[pl],
                              label=f'{pl}% FV')
        axs_loss[1, col].plot(tempo_horas, historico_plot[c]['Losses_kvar'][pl], color=cores_cenarios[pl],
                              label=f'{pl}% FV')

    if col == 0:
        axs_loss[0, col].set_ylabel('Perda Ativa (kW)')
        axs_loss[1, col].set_ylabel('Perda Reativa (kvar)')
    else:
        axs_loss[0, col].set_ylabel('')
        axs_loss[1, col].set_ylabel('')

    axs_loss[0, col].set_title(f'a) Caso A' if c == 'A' else 'b) Caso B', fontsize=38, pad=20)
    axs_loss[1, col].set_title('')

    for row in range(2):
        axs_loss[row, col].set_xlabel('Tempo (h)')
        axs_loss[row, col].set_xlim(0, 24)
        axs_loss[row, col].set_xticks(np.arange(0, 25, 2))
        axs_loss[row, col].yaxis.set_major_locator(ticker.MaxNLocator(8))
        axs_loss[row, col].grid(True, linestyle='--', alpha=0.7)

sincronizar_eixos_y(axs_loss)

handles, labels = axs_loss[0, 0].get_legend_handles_labels()
fig_loss.legend(handles, labels, loc='lower center', ncol=4, bbox_to_anchor=(0.5, 0.05), frameon=False)

fig_loss.tight_layout(rect=[0, 0.20, 1, 1.0])
fig_loss.subplots_adjust(hspace=0.30, wspace=0.15)
fig_loss.savefig(os.path.join(pasta_saida, "5_Perdas_Tecnicas.png"), dpi=300, bbox_inches='tight')
plt.close(fig_loss)

# ------------------------------------------------------------------------------
# 5. PERFIS DE TENSÃO E FD% POR CENÁRIO DE PENETRAÇÃO (pl)
# ------------------------------------------------------------------------------
for pl in niveis_penetracao:

    # --- Perfil de Tensão (2x3) ---
    fig_v_pl, axs_v = plt.subplots(2, 3, figsize=(26, 16))
    if EXIBIR_TITULO_GERAL: fig_v_pl.suptitle(f'Perfil de Tensão - Penetração Fotovoltaica {pl}%')

    for row, c in enumerate(['A', 'B']):
        tensoes = historico_plot[c]['tensoes_pu'][pl]
        nos_A = [no for no in tensoes.keys() if no.endswith('.1')]
        nos_B = [no for no in tensoes.keys() if no.endswith('.2')]
        nos_C = [no for no in tensoes.keys() if no.endswith('.3')]


        def plot_voltage_subplots(ax, nos, title):
            for no in nos:
                if len(tensoes[no]) == len(tempo_horas):
                    ax.plot(tempo_horas, tensoes[no], linewidth=1.5)

            ax.axhline(y=1.05, color='r', linestyle='--', linewidth=3.0)
            ax.axhline(y=0.92, color='r', linestyle='--', linewidth=3.0)
            ax.set_title(title)
            ax.set_xlabel('Tempo (h)')
            ax.set_ylabel('Tensão (p.u.)')
            ax.set_xlim(0, 24)
            ax.set_xticks(np.arange(0, 25, 2))
            ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
            ax.set_ylim(0.90, 1.10)
            ax.grid(True, linestyle='--', alpha=0.7)


        plot_voltage_subplots(axs_v[row, 0], nos_A, f'Caso {c} - Fase A')
        plot_voltage_subplots(axs_v[row, 1], nos_B, f'Caso {c} - Fase B')
        plot_voltage_subplots(axs_v[row, 2], nos_C, f'Caso {c} - Fase C')

    linha_barras = plt.Line2D([0], [0], color='gray', linewidth=2.5, label='Perfil das Barras da Rede')
    lim_line = plt.Line2D([0], [0], color='red', linestyle='--', linewidth=3.0,
                          label='Limites PRODIST (0.92 - 1.05 p.u.)')

    fig_v_pl.legend(handles=[linha_barras, lim_line], loc='lower center',
                    ncol=2, bbox_to_anchor=(0.5, 0.02))

    fig_v_pl.tight_layout(rect=[0, 0.16, 1, 1.0])
    fig_v_pl.subplots_adjust(hspace=0.7, wspace=0.5)
    fig_v_pl.savefig(os.path.join(pasta_saida, f"6_Perfil_Tensao_PL_{pl}.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_v_pl)

    # --- Perfil de FD% (1x2) - MÉTODO IEC ---
    fig_fd_iec_pl, axs_fd_iec = plt.subplots(1, 2, figsize=(22, 10))
    if EXIBIR_TITULO_GERAL: fig_fd_iec_pl.suptitle(f'Fator de Desequilíbrio (MÉTODO IEC/PRODIST) - Penetração {pl}%')

    for col, c in enumerate(['A', 'B']):
        fd_data = historico_plot[c]['fd_iec'][pl]
        ax = axs_fd_iec[col]
        for b, vals in fd_data.items():
            if len(vals) == len(tempo_horas):
                ax.plot(tempo_horas, vals, linewidth=1.5)

        ax.axhline(y=limite_prodist, color='black', linestyle='--', linewidth=3.0)
        ax.set_title(f'Caso {c} (IEC)')
        ax.set_xlabel('Tempo (h)')
        ax.set_ylabel('Fator de Desequilíbrio (%)')
        ax.set_xlim(0, 24)
        ax.set_xticks(np.arange(0, 25, 2))
        ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
        ax.grid(True, linestyle='--', alpha=0.7)

    linha_fd = plt.Line2D([0], [0], color='gray', linewidth=2.5, label='Fator de Desequilíbrio nas Barras')
    lim_fd_iec = plt.Line2D([0], [0], color='black', linestyle='--', linewidth=3.0,
                            label=f'Lim. PRODIST ({limite_prodist}%)')

    sincronizar_eixos_y(axs_fd_iec)

    fig_fd_iec_pl.legend(handles=[linha_fd, lim_fd_iec], loc='lower center',
                         ncol=2, bbox_to_anchor=(0.5, 0.02))

    fig_fd_iec_pl.tight_layout(rect=[0, 0.20, 1, 1.0])
    fig_fd_iec_pl.subplots_adjust(wspace=0.5)
    fig_fd_iec_pl.savefig(os.path.join(pasta_saida, f"7_Perfil_FD_IEC_PL_{pl}.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_fd_iec_pl)

# ------------------------------------------------------------------------------
# 6. GRÁFICOS DA BARRA COM MAIOR DESEQUILÍBRIO E EXTRAÇÃO DE DADOS
# ------------------------------------------------------------------------------
print("=" * 60)
print(" GERANDO GRÁFICOS AVANÇADOS DA BARRA COM MAIOR DESEQUILÍBRIO... ")
print("=" * 60)

fd_caso_a_100 = historico_plot['A']['fd_iec'][100]
barra_pior_fd = None
max_fd = -1.0

for barra, valores in fd_caso_a_100.items():
    if len(valores) > 48:
        fd_12h = valores[48]
        if fd_12h > max_fd:
            max_fd = fd_12h
            barra_pior_fd = barra

if barra_pior_fd is not None:
    barra_pior_fd_lower = barra_pior_fd.lower()
    print(f"-> Barra identificada: {barra_pior_fd} com FD de {max_fd:.2f}% às 12:00h no Caso A (PL 100%).")

    all_lines_topo = []
    dss.lines.first()
    while True:
        b1 = dss.lines.bus1.split('.')[0].lower()
        b2 = dss.lines.bus2.split('.')[0].lower()
        all_lines_topo.append({'name': dss.lines.name.lower(), 'b1': b1, 'b2': b2})
        if not dss.lines.next(): break

    linha_critica = None
    for l in all_lines_topo:
        if l['b2'] == barra_pior_fd_lower or l['b1'] == barra_pior_fd_lower:
            linha_critica = l['name']
            if l['b2'] == barra_pior_fd_lower:
                break

    buses_jusante = set([barra_pior_fd_lower])
    added = True
    while added:
        added = False
        for l in all_lines_topo:
            if l['b1'] in buses_jusante and l['b2'] not in buses_jusante:
                buses_jusante.add(l['b2'])
                added = True

    fases_idx = [0, 1, 2]
    fases_nomes = ['Fase A', 'Fase B', 'Fase C']

    dados_tab_tensao = {'A': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}},
                        'B': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}}}
    dados_tab_fluxo = {'A': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}}, 'B': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}}}
    dados_tab_carga_jus = {'A': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}},
                           'B': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}}}
    dados_tab_geracao_jus = {'A': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}},
                             'B': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}}}

    # --- PLOT 8: Perfil de Tensão Horário ---
    fig_v_barra, axs_v_barra = plt.subplots(2, 3, figsize=(26, 16))
    if EXIBIR_TITULO_GERAL: fig_v_barra.suptitle(
        f'Perfil de Tensão Horário - Barra Crítica {barra_pior_fd}\n(Selecionada pelo maior FD no Caso A, PL 100% às ~12h)')

    fases_v_idx = ['.1', '.2', '.3']
    for row, c in enumerate(['A', 'B']):
        for col, (f_idx_v, f_nome) in enumerate(zip(fases_v_idx, fases_nomes)):
            ax = axs_v_barra[row, col]
            no_alvo = f"{barra_pior_fd}{f_idx_v}"

            for pl in niveis_penetracao:
                tensoes_cenario = historico_plot[c]['tensoes_pu'][pl]
                if no_alvo in tensoes_cenario and len(tensoes_cenario[no_alvo]) == len(tempo_horas):
                    ax.plot(tempo_horas, tensoes_cenario[no_alvo], color=cores_cenarios[pl], label=f'{pl}% FV')
                    dados_tab_tensao[c][f_nome][pl] = tensoes_cenario[no_alvo]

            ax.axhline(y=1.05, color='r', linestyle='--', linewidth=3.0, label='Lim. Sup. (1.05)')
            ax.axhline(y=0.92, color='r', linestyle='--', linewidth=3.0, label='Lim. Inf. (0.92)')
            ax.set_title(f'Caso {c} - {f_nome}')
            ax.set_xlabel('Tempo (h)')
            ax.set_ylabel('Tensão (p.u.)')
            ax.set_xlim(0, 24)
            ax.set_xticks(np.arange(0, 25, 2))
            ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
            ax.grid(True, linestyle='--', alpha=0.7)

    sincronizar_eixos_y(axs_v_barra)

    handles, labels = axs_v_barra[0, 0].get_legend_handles_labels()
    fig_v_barra.legend(handles, labels, loc='lower center', ncol=6, bbox_to_anchor=(0.5, 0.02))

    fig_v_barra.tight_layout(rect=[0, 0.16, 1, 1.0])
    fig_v_barra.subplots_adjust(hspace=0.7, wspace=0.5)
    fig_v_barra.savefig(os.path.join(pasta_saida, "8_Perfil_Tensao_Barra_Critica.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_v_barra)

    if linha_critica is not None:
        # --- PLOT 9: Fluxo de Potência Ativa (kW) por Fase na Linha Crítica ---
        fig_fluxo, axs_fluxo = plt.subplots(2, 3, figsize=(26, 16))
        if EXIBIR_TITULO_GERAL: fig_fluxo.suptitle(
            f'Fluxo de Potência Ativa (kW) por Fase na Linha Crítica: {linha_critica.upper()}\n(Alimentadora da Barra {barra_pior_fd})')

        for row, c in enumerate(['A', 'B']):
            for col, (f_i, f_nome) in enumerate(zip(fases_idx, fases_nomes)):
                ax = axs_fluxo[row, col]
                for pl in niveis_penetracao:
                    try:
                        dados_fase = [passo[f_i] if abs(passo[f_i]) > 1e-4 else 0.0 for passo in
                                      historico_plot[c]['linhas'][pl][linha_critica]]
                        ax.plot(tempo_horas, dados_fase, color=cores_cenarios[pl], label=f'{pl}% FV')
                        dados_tab_fluxo[c][f_nome][pl] = dados_fase
                    except Exception:
                        pass

                ax.set_title(f'Caso {c} - {f_nome}')
                ax.set_xlabel('Tempo (h)')
                ax.set_ylabel('Potência Ativa (kW)')
                ax.set_xlim(0, 24)
                ax.set_xticks(np.arange(0, 25, 2))
                ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
                ax.grid(True, linestyle='--', alpha=0.7)

        sincronizar_eixos_y(axs_fluxo)

        handles, labels = axs_fluxo[0, 0].get_legend_handles_labels()
        fig_fluxo.legend(handles, labels, loc='lower center', ncol=6, bbox_to_anchor=(0.5, 0.02))

        fig_fluxo.tight_layout(rect=[0, 0.16, 1, 1.0])
        fig_fluxo.subplots_adjust(hspace=0.7, wspace=0.5)
        fig_fluxo.savefig(os.path.join(pasta_saida, "9_Fluxo_Potencia_Linha_Critica.png"), dpi=300, bbox_inches='tight')
        plt.close(fig_fluxo)

    # --- PLOT 10: Balanço Carga vs. Geração a Jusante ---
    fig_bal, axs_bal = plt.subplots(2, 3, figsize=(26, 16))
    if EXIBIR_TITULO_GERAL: fig_bal.suptitle(
        f'Balanço Carga vs. Geração a Jusante da Barra {barra_pior_fd}\n(Incluindo a Própria Barra)')

    for row, c in enumerate(['A', 'B']):
        for col, (f_i, f_nome) in enumerate(zip(fases_idx, fases_nomes)):
            ax = axs_bal[row, col]

            carga_jusante = []
            for passo_idx in range(passos):
                c_sum = sum([historico_plot[c]['cargas_bus'][0].get(b, [[0, 0, 0]] * passos)[passo_idx][f_i] for b in
                             buses_jusante])
                carga_jusante.append(c_sum)

            dados_tab_carga_jus[c][f_nome][0] = carga_jusante

            ax.plot(tempo_horas, carga_jusante, color='black', linewidth=4.0, label='Carga Total')

            for pl in niveis_penetracao:
                if pl == 0:
                    dados_tab_geracao_jus[c][f_nome][pl] = [0.0] * passos
                    continue
                pv_jusante = []
                for passo_idx in range(passos):
                    p_sum = sum([historico_plot[c]['pvs_bus'][pl].get(b, [[0, 0, 0]] * passos)[passo_idx][f_i] for b in
                                 buses_jusante])
                    pv_jusante.append(p_sum)

                ax.plot(tempo_horas, pv_jusante, color=cores_cenarios[pl], linestyle='--', label=f'FV {pl}%')
                dados_tab_geracao_jus[c][f_nome][pl] = pv_jusante

            ax.set_title(f'Caso {c} - {f_nome}')
            ax.set_xlabel('Tempo (h)')
            ax.set_ylabel('Potência Ativa (kW)')
            ax.set_xlim(0, 24)
            ax.set_xticks(np.arange(0, 25, 2))
            ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
            ax.grid(True, linestyle='--', alpha=0.7)

    sincronizar_eixos_y(axs_bal)

    handles, labels = axs_bal[0, 0].get_legend_handles_labels()
    fig_bal.legend(handles, labels, loc='lower center', ncol=6, bbox_to_anchor=(0.5, 0.02))

    fig_bal.tight_layout(rect=[0, 0.16, 1, 1.0])
    fig_bal.subplots_adjust(hspace=0.7, wspace=0.5)
    fig_bal.savefig(os.path.join(pasta_saida, "10_Balanco_Carga_Geracao_Jusante.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_bal)

    # ==============================================================================
    # EXTRAS: IMPLEMENTAÇÃO DAS SUGESTÕES E ENVELOPE (NOVOS GRÁFICOS)
    # ==============================================================================

    passo_alvo = 48

    dados_impacto_fd = {'A': [], 'B': []}
    dados_heatmap = {'A': [], 'B': []}
    dados_jacare_v = {'A': {'Fase A': [], 'Fase B': [], 'Fase C': []},
                      'B': {'Fase A': [], 'Fase B': [], 'Fase C': []}}
    dados_jacare_p = {'A': {'Fase A': [], 'Fase B': [], 'Fase C': []},
                      'B': {'Fase A': [], 'Fase B': [], 'Fase C': []}}

    for caso in ['A', 'B']:
        for pl in niveis_penetracao:
            fd_12h = historico_plot[caso]['fd_iec'][pl][barra_pior_fd][passo_alvo]
            dados_impacto_fd[caso].append(fd_12h)

            dados_heatmap[caso].append(historico_plot[caso]['fd_iec'][pl][barra_pior_fd])

            for col, f_nome in enumerate(fases_nomes):
                no_fase = f"{barra_pior_fd}.{col + 1}"
                v_fase = historico_plot[caso]['tensoes_pu'][pl][no_fase][passo_alvo]
                dados_jacare_v[caso][f_nome].append(v_fase)

            if linha_critica is not None:
                for col, f_nome in enumerate(fases_nomes):
                    p_fase = historico_plot[caso]['linhas'][pl][linha_critica][passo_alvo][col]
                    p_fase = p_fase if abs(p_fase) > 1e-4 else 0.0
                    dados_jacare_p[caso][f_nome].append(p_fase)

    # --- PLOT 11: Curva de Impacto ---
    fig_imp, ax_imp = plt.subplots(figsize=(16, 10))
    ax_imp.plot(niveis_penetracao, dados_impacto_fd['A'], 'o-', label='Caso A (Ligação Real)', color='#d62728',
                linewidth=3.5, markersize=12)
    ax_imp.plot(niveis_penetracao, dados_impacto_fd['B'], 's-', label='Caso B (Ligação Trifásica)', color='#1f77b4',
                linewidth=3.5, markersize=12)
    ax_imp.axhline(y=limite_prodist, color='black', linestyle='--', linewidth=3.5,
                   label=f'Lim. PRODIST ({limite_prodist}%)')
    if EXIBIR_TITULO_GERAL:
        ax_imp.set_title(f'Curva de Impacto: Fator de Desequilíbrio às ~12h00\nBarra Crítica: {barra_pior_fd}', pad=25)

    ax_imp.set_xlabel('Nível de Penetração FV (%)', labelpad=15)
    ax_imp.set_ylabel('Fator de Desequilíbrio (%)', labelpad=20)
    ax_imp.set_xticks(niveis_penetracao)
    ax_imp.yaxis.set_major_locator(ticker.MaxNLocator(10))
    ax_imp.grid(True, linestyle='--', alpha=0.7)

    ax_imp.legend(loc='upper center', bbox_to_anchor=(0.5, -0.35), ncol=3)
    fig_imp.subplots_adjust(left=0.15, right=0.95, top=0.85, bottom=0.35)
    fig_imp.savefig(os.path.join(pasta_saida, "11_Curva_Impacto_FD.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_imp)

    # --- PLOT 12: Mapa de Calor ---
    fig_hm, axs_hm = plt.subplots(1, 2, figsize=(24, 10))
    if EXIBIR_TITULO_GERAL: fig_hm.suptitle(
        f'Mapa de Calor (Heatmap) do Fator de Desequilíbrio - Barra Crítica {barra_pior_fd}')

    for col, c in enumerate(['A', 'B']):
        ax = axs_hm[col]
        matriz = np.array(dados_heatmap[c])
        cax = ax.pcolormesh(tempo_horas, niveis_penetracao, matriz, cmap='jet', vmin=0, vmax=max(3.5, np.max(matriz)),
                            shading='auto')
        ax.set_title(f'Caso {c}')
        ax.set_xlabel('Tempo (h)')
        ax.set_ylabel('Nível de Penetração FV (%)')
        ax.set_yticks(niveis_penetracao)
        ax.set_xticks(np.arange(0, 25, 2))

    cbar = fig_hm.colorbar(cax, ax=axs_hm, orientation='vertical', fraction=0.02, pad=0.04)
    cbar.set_label('Fator de Desequilíbrio (%)', size=32, labelpad=25)
    cbar.ax.axhline(limite_prodist, color='black', linestyle='--', linewidth=3.5)

    fig_hm.subplots_adjust(top=0.80, bottom=0.15, left=0.08, right=0.85, wspace=0.45)
    fig_hm.savefig(os.path.join(pasta_saida, "12_Heatmap_FD.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_hm)

    # --- PLOT 13: Efeito Boca de Jacaré (Tensão) ---
    fig_jac_v, axs_jac_v = plt.subplots(1, 2, figsize=(22, 12))
    if EXIBIR_TITULO_GERAL: fig_jac_v.suptitle(
        f'Afastamento das Tensões às ~12h00 (Efeito "Boca de Jacaré")\nBarra Crítica: {barra_pior_fd}')

    for col, c in enumerate(['A', 'B']):
        ax = axs_jac_v[col]
        ax.plot(niveis_penetracao, dados_jacare_v[c]['Fase A'], 'o-', label='Fase A', color='#1f77b4', linewidth=3.5,
                markersize=12)
        ax.plot(niveis_penetracao, dados_jacare_v[c]['Fase B'], 's-', label='Fase B', color='#ff7f0e', linewidth=3.5,
                markersize=12)
        ax.plot(niveis_penetracao, dados_jacare_v[c]['Fase C'], '^-', label='Fase C', color='#2ca02c', linewidth=3.5,
                markersize=12)
        ax.axhline(y=1.05, color='r', linestyle='--', linewidth=3.5, label='Lim. Sup. (1.05 p.u.)')
        ax.axhline(y=0.92, color='r', linestyle='--', linewidth=3.5, label='Lim. Inf. (0.92 p.u.)')
        ax.set_title(f'a) Caso A' if c == 'A' else 'b) Caso B', fontsize=38, pad=20)
        ax.set_xlabel('Nível de Penetração FV (%)')
        if col == 0:
            ax.set_ylabel('Tensão (p.u.)')
        ax.set_xticks(niveis_penetracao)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
        ax.grid(True, linestyle='--', alpha=0.7)

    sincronizar_eixos_y(axs_jac_v)

    handles, labels = axs_jac_v[0].get_legend_handles_labels()
    fig_jac_v.legend(handles, labels, loc='lower center', ncol=5, bbox_to_anchor=(0.5, 0.05), frameon=False)

    fig_jac_v.tight_layout(rect=[0, 0.20, 1, 1.0])
    fig_jac_v.subplots_adjust(bottom=0.25, wspace=0.15)
    fig_jac_v.savefig(os.path.join(pasta_saida, "13_Afastamento_Tensoes_12h.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_jac_v)

    # --- PLOT 14: Efeito Boca de Jacaré (Potência) ---
    if linha_critica is not None:
        fig_jac_p, axs_jac_p = plt.subplots(1, 2, figsize=(22, 10))
        if EXIBIR_TITULO_GERAL: fig_jac_p.suptitle(
            f'Afastamento do Fluxo de Potência Ativa às ~12h00\nLinha Crítica: {linha_critica.upper()}')

        for col, c in enumerate(['A', 'B']):
            ax = axs_jac_p[col]
            ax.plot(niveis_penetracao, dados_jacare_p[c]['Fase A'], 'o-', label='Fase A', color='#1f77b4',
                    linewidth=3.5, markersize=12)
            ax.plot(niveis_penetracao, dados_jacare_p[c]['Fase B'], 's-', label='Fase B', color='#ff7f0e',
                    linewidth=3.5, markersize=12)
            ax.plot(niveis_penetracao, dados_jacare_p[c]['Fase C'], '^-', label='Fase C', color='#2ca02c',
                    linewidth=3.5, markersize=12)
            ax.set_title(f'Caso {c}')
            ax.set_xlabel('Nível de Penetração FV (%)')
            ax.set_ylabel('Potência Ativa (kW)')
            ax.set_xticks(niveis_penetracao)
            ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
            ax.grid(True, linestyle='--', alpha=0.7)

        sincronizar_eixos_y(axs_jac_p)

        handles, labels = axs_jac_p[0].get_legend_handles_labels()
        fig_jac_p.legend(handles, labels, loc='lower center', ncol=3, bbox_to_anchor=(0.5, 0.02))

        fig_jac_p.tight_layout(rect=[0, 0.20, 1, 1.0])
        fig_jac_p.subplots_adjust(wspace=0.5)
        fig_jac_p.savefig(os.path.join(pasta_saida, "14_Afastamento_Potencias_12h.png"), dpi=300, bbox_inches='tight')
        plt.close(fig_jac_p)

    # --- PLOT 15: Envelope Diário do Maior Desequilíbrio da Rede ---
    dados_max_fd_diario = {'A': {}, 'B': {}}
    for caso in ['A', 'B']:
        for pl in niveis_penetracao:
            fd_todas_barras = historico_plot[caso]['fd_iec'][pl]
            fd_max_por_passo = []
            for t in range(passos):
                maior_fd_instante = max([fd_todas_barras[b][t] for b in fd_todas_barras if
                                         len(fd_todas_barras[b]) > t]) if fd_todas_barras else 0.0
                fd_max_por_passo.append(maior_fd_instante)
            dados_max_fd_diario[caso][pl] = fd_max_por_passo

    fig_env_fd, axs_env_fd = plt.subplots(1, 2, figsize=(22, 12))
    if EXIBIR_TITULO_GERAL: fig_env_fd.suptitle('Evolução Diária do Fator de Desequilíbrio Máximo da Rede')

    for col, caso in enumerate(['A', 'B']):
        ax = axs_env_fd[col]
        for pl in niveis_penetracao:
            ax.plot(tempo_horas, dados_max_fd_diario[caso][pl], color=cores_cenarios[pl], label=f'{pl}% FV')

        ax.axhline(y=limite_prodist, color='black', linestyle='--', linewidth=3.5,
                   label=f'Lim. PRODIST ({limite_prodist}%)')
        ax.set_title(f'a) Caso A' if caso == 'A' else 'b) Caso B', fontsize=38, pad=20)
        ax.set_xlabel('Tempo (h)')
        if col == 0:
            ax.set_ylabel('Fator de Desequilíbrio Máximo (%)')
        ax.set_xlim(0, 24)
        ax.set_xticks(np.arange(0, 25, 2))
        ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
        ax.grid(True, linestyle='--', alpha=0.7)

    sincronizar_eixos_y(axs_env_fd)

    handles, labels = axs_env_fd[0].get_legend_handles_labels()
    fig_env_fd.legend(handles, labels, loc='lower center', ncol=4, bbox_to_anchor=(0.5, 0.0), frameon=False)

    fig_env_fd.tight_layout(rect=[0, 0.18, 1, 1.0])
    fig_env_fd.subplots_adjust(bottom=0.25, wspace=0.15)
    fig_env_fd.savefig(os.path.join(pasta_saida, "15_Max_FD_Diario_Envelope.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_env_fd)

    # --- PLOT 16: Maior Tensão da Rede por Fase ---
    dados_max_v_rede = {'A': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}},
                        'B': {'Fase A': {}, 'Fase B': {}, 'Fase C': {}}}

    for caso in ['A', 'B']:
        for pl in niveis_penetracao:
            tensoes_cenario = historico_plot[caso]['tensoes_pu'][pl]
            nos_A = [n for n in tensoes_cenario.keys() if n.endswith('.1')]
            nos_B = [n for n in tensoes_cenario.keys() if n.endswith('.2')]
            nos_C = [n for n in tensoes_cenario.keys() if n.endswith('.3')]

            max_v_A, max_v_B, max_v_C = [], [], []

            for t in range(passos):
                v_A = [tensoes_cenario[n][t] for n in nos_A if len(tensoes_cenario[n]) > t]
                max_v_A.append(max(v_A) if v_A else 0.0)

                v_B = [tensoes_cenario[n][t] for n in nos_B if len(tensoes_cenario[n]) > t]
                max_v_B.append(max(v_B) if v_B else 0.0)

                v_C = [tensoes_cenario[n][t] for n in nos_C if len(tensoes_cenario[n]) > t]
                max_v_C.append(max(v_C) if v_C else 0.0)

            dados_max_v_rede[caso]['Fase A'][pl] = max_v_A
            dados_max_v_rede[caso]['Fase B'][pl] = max_v_B
            dados_max_v_rede[caso]['Fase C'][pl] = max_v_C

    fig_max_v, axs_max_v = plt.subplots(3, 2, figsize=(20, 24))
    if EXIBIR_TITULO_GERAL: fig_max_v.suptitle('Maior Tensão Global da Rede por Fase ao Longo do Dia (Pior Caso)')

    for col, c in enumerate(['A', 'B']):
        for row, f_nome in enumerate(['Fase A', 'Fase B', 'Fase C']):
            ax = axs_max_v[row, col]
            for pl in niveis_penetracao:
                ax.plot(tempo_horas, dados_max_v_rede[c][f_nome][pl], color=cores_cenarios[pl], label=f'{pl}% FV')

            ax.axhline(y=1.05, color='r', linestyle='--', linewidth=3.0, label='Lim. Sup. (1.05 p.u.)')

            if row == 0:
                ax.set_title(f'a) Caso A' if c == 'A' else 'b) Caso B', fontsize=38, pad=20)
            else:
                ax.set_title('')

            ax.text(0.03, 0.95, f_nome, transform=ax.transAxes, ha='left', va='top',
                    fontsize=36, bbox=dict(facecolor='white', alpha=0.8, edgecolor='none', pad=2))

            ax.set_xlabel('Tempo (h)')
            if col == 0:
                ax.set_ylabel('Tensão Máxima (p.u.)')
            else:
                ax.set_ylabel('')

            ax.set_xlim(0, 24)
            ax.set_xticks(np.arange(0, 25, 2))
            ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
            ax.grid(True, linestyle='--', alpha=0.7)

    sincronizar_eixos_y(axs_max_v)

    handles, labels = axs_max_v[0, 0].get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    fig_max_v.legend(by_label.values(), by_label.keys(), loc='lower center', ncol=4, bbox_to_anchor=(0.5, 0.05),
                     frameon=False)

    fig_max_v.tight_layout(rect=[0, 0.18, 1, 1.0])
    fig_max_v.subplots_adjust(hspace=0.25, wspace=0.15)
    fig_max_v.savefig(os.path.join(pasta_saida, "16_Maior_Tensao_Rede_Por_Fase.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_max_v)

    # --- PLOT 17: Comparativo de Barras no Horário de Pico de Desequilíbrio ---
    fd_todas_PL100_A = historico_plot['A']['fd_iec'][100]

    max_fd_rede_passos = []
    for t in range(passos):
        vals_t = [fd_todas_PL100_A[b][t] for b in fd_todas_PL100_A if len(fd_todas_PL100_A[b]) > t]
        max_fd_rede_passos.append(max(vals_t) if vals_t else 0.0)

    idx_pior_horario = np.argmax(max_fd_rede_passos)
    h_pico = tempo_horas[idx_pior_horario]
    h_str = f"{int(h_pico):02d}:{int((h_pico % 1) * 60):02d}h"

    v_max_A_bars, v_max_B_bars = [], []
    fd_max_A_bars, fd_max_B_bars = [], []

    for pl in niveis_penetracao:
        dict_v_A = historico_plot['A']['tensoes_pu'][pl]
        v_A = [dict_v_A[no][idx_pior_horario] for no in dict_v_A.keys() if
               no.endswith(('.1', '.2', '.3')) and len(dict_v_A[no]) > idx_pior_horario]
        v_max_A_bars.append(max(v_A) if v_A else 1.0)

        dict_v_B = historico_plot['B']['tensoes_pu'][pl]
        v_B = [dict_v_B[no][idx_pior_horario] for no in dict_v_B.keys() if
               no.endswith(('.1', '.2', '.3')) and len(dict_v_B[no]) > idx_pior_horario]
        v_max_B_bars.append(max(v_B) if v_B else 1.0)

        dict_fd_A = historico_plot['A']['fd_iec'][pl]
        fd_A = [dict_fd_A[b][idx_pior_horario] for b in dict_fd_A.keys() if len(dict_fd_A[b]) > idx_pior_horario]
        fd_max_A_bars.append(max(fd_A) if fd_A else 0.0)

        dict_fd_B = historico_plot['B']['fd_iec'][pl]
        fd_B = [dict_fd_B[b][idx_pior_horario] for b in dict_fd_B.keys() if len(dict_fd_B[b]) > idx_pior_horario]
        fd_max_B_bars.append(max(fd_B) if fd_B else 0.0)

    fig_barras, axs_barras = plt.subplots(2, 1, figsize=(18, 20))
    x = np.arange(len(niveis_penetracao))
    largura = 0.35

    bar_v_a = axs_barras[0].bar(x - largura / 2, v_max_A_bars, largura, label='Caso A', color='#1f77b4',
                                edgecolor='black')
    bar_v_b = axs_barras[0].bar(x + largura / 2, v_max_B_bars, largura, label='Caso B', color='#ff7f0e',
                                edgecolor='black')
    lim_v = axs_barras[0].axhline(y=1.05, color='r', linestyle='--', linewidth=3.5, label='Lim. Sup. (1.05 p.u.)')
    axs_barras[0].set_ylabel('Tensão Máxima (p.u.)')
    axs_barras[0].set_title(f'a) Tensão máxima ({h_str})', fontsize=38, pad=25)

    limite_superior_y = max(max(v_max_A_bars), max(v_max_B_bars)) + 0.02
    axs_barras[0].set_ylim(0.95, limite_superior_y)
    axs_barras[0].yaxis.set_major_locator(ticker.MaxNLocator(8))

    axs_barras[0].set_xticks(x)
    axs_barras[0].set_xticklabels([f"{p}%" for p in niveis_penetracao])
    axs_barras[0].grid(True, axis='y', linestyle='--', alpha=0.7)

    axs_barras[1].bar(x - largura / 2, fd_max_A_bars, largura, label='Caso A', color='#1f77b4', edgecolor='black')
    axs_barras[1].bar(x + largura / 2, fd_max_B_bars, largura, label='Caso B', color='#ff7f0e', edgecolor='black')
    lim_fd = axs_barras[1].axhline(y=limite_prodist, color='black', linestyle='--', linewidth=3.5,
                                   label='Lim. PRODIST (3.0%)')
    axs_barras[1].set_ylabel('FD Máximo (%)')
    axs_barras[1].set_xlabel('Nível de Penetração FV (%)')
    axs_barras[1].set_title(f'b) Fator de desequilíbrio máximo ({h_str})', fontsize=38, pad=25)

    axs_barras[1].yaxis.set_major_locator(ticker.MaxNLocator(8))
    axs_barras[1].set_xticks(x)
    axs_barras[1].set_xticklabels([f"{p}%" for p in niveis_penetracao])
    axs_barras[1].grid(True, axis='y', linestyle='--', alpha=0.7)

    fig_barras.legend([lim_v, bar_v_a, bar_v_b, lim_fd],
                      ['Lim. Sup. (1.05 p.u.)', 'Caso A', 'Caso B', 'Lim. PRODIST (3.0%)'],
                      loc='lower center', ncol=4, bbox_to_anchor=(0.5, 0.05), frameon=False)

    fig_barras.tight_layout(rect=[0, 0.12, 1, 1.0])
    fig_barras.subplots_adjust(hspace=0.35, bottom=0.15)
    fig_barras.savefig(os.path.join(pasta_saida, "17_Comparativo_Maximos_Pico.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_barras)

    # ------------------------------------------------------------------------------
    # 18. NOVO GRÁFICO: SUBPLOT COMPARATIVO DE PERDAS DE ENERGIA TOTAIS DIÁRIAS (1 col x 3 lin)
    # ------------------------------------------------------------------------------
    fig_energy, axs_energy = plt.subplots(3, 1, figsize=(18, 26))
    x_eng = np.arange(len(niveis_penetracao))
    largura_eng = 0.35

    metrics_eng = ['E_loss_kW', 'E_loss_kvar', 'E_loss_kVA']
    titulos_eng = ['a) Perda Coletiva de Energia Ativa Diária', 'b) Perda Coletiva de Energia Reativa Diária',
                   'c) Perda Coletiva de Energia Aparente Diária']
    ylabels_eng = ['Energia Ativa (kWh)', 'Energia Reativa (kvarh)', 'Energia Aparente (kVAh)']

    for row in range(3):
        ax = axs_energy[row]
        metric = metrics_eng[row]

        vals_A = [historico_plot['A'][metric][pl] for pl in niveis_penetracao]
        vals_B = [historico_plot['B'][metric][pl] for pl in niveis_penetracao]

        bar_eng_a = ax.bar(x_eng - largura_eng / 2, vals_A, largura_eng, label='Caso A', color='#1f77b4',
                           edgecolor='black')
        bar_eng_b = ax.bar(x_eng + largura_eng / 2, vals_B, largura_eng, label='Caso B', color='#ff7f0e',
                           edgecolor='black')

        ax.set_ylabel(ylabels_eng[row])
        ax.set_title(titulos_eng[row], fontsize=38, pad=25)
        ax.set_xticks(x_eng)
        ax.set_xticklabels([f"{p}%" for p in niveis_penetracao])
        ax.grid(True, axis='y', linestyle='--', alpha=0.7)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(8))
        """
        # Adiciona rótulos de valores estáticos acima de cada barra do subplot
        for rect in bar_eng_a:
            height = rect.get_height()
            ax.annotate(f'{height:.1f}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 5),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=18, fontname='Times New Roman')

        for rect in bar_eng_b:
            height = rect.get_height()
            ax.annotate(f'{height:.1f}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 5),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=18, fontname='Times New Roman')
        """
    axs_energy[2].set_xlabel('Nível de Penetração FV (%)')

    # Mantém a mesma dimensão de eixo Y de forma global para facilitar comparação estática
    sincronizar_eixos_y(axs_energy)

    fig_energy.legend([bar_eng_a, bar_eng_b], ['Caso A', 'Caso B'],
                      loc='lower center', ncol=2, bbox_to_anchor=(0.5, 0.04), frameon=False)

    fig_energy.tight_layout(rect=[0, 0.10, 1, 1.0])
    fig_energy.subplots_adjust(hspace=0.45, bottom=0.15)
    fig_energy.savefig(os.path.join(pasta_saida, "18_Comparativo_Energia_Perdida.png"), dpi=300, bbox_inches='tight')
    plt.close(fig_energy)

    # ==============================================================================
    # 8. TABELAS DE RESUMO ESTATÍSTICO DA BARRA CRÍTICA E NOVOS GRÁFICOS
    # ==============================================================================
    print("\n" + "=" * 115)
    print(f" 8. RESUMO ESTATÍSTICO CONSOLIDADO - BARRA CRÍTICA ({barra_pior_fd.upper()}) ")
    print("=" * 115)


    def gerar_tabela_estatistica_critica(dicionario_hist, titulo):
        if not dicionario_hist: return
        df = pd.DataFrame({f"{k}% FV": pd.Series(v) for k, v in dicionario_hist.items()})
        stats = df.describe(percentiles=[.01, .05, .25, .5, .75, .95, .99]).T
        stats['skewness'] = df.skew()
        stats['kurtosis'] = df.kurt()
        print(f"\n>>> TABELA: {titulo}")
        print(stats.map(lambda x: f"{x:.4f}").to_string())


    print("\n" + "-" * 115)
    print(f" IMPACTO DO FATOR DE DESEQUILÍBRIO (FD%) - BARRA {barra_pior_fd.upper()} ".center(115, '-'))
    print("-" * 115)
    df_impacto = pd.DataFrame({'Caso A (12h00)': dados_impacto_fd['A'], 'Caso B (12h00)': dados_impacto_fd['B']},
                              index=[f"{pl}%" for pl in niveis_penetracao])
    df_impacto.index.name = "PL"

    max_diario = {'A': [], 'B': []}
    for c in ['A', 'B']:
        for pl in niveis_penetracao:
            max_diario[c].append(max(historico_plot[c]['fd_iec'][pl][barra_pior_fd]))
    df_impacto['Caso A (Máx Diário)'] = max_diario['A']
    df_impacto['Caso B (Máx Diário)'] = max_diario['B']
    print("\n>>> TABELA: Curva de Impacto (FD% às 12h00 e Máximo Diário)")
    print(df_impacto.to_string(float_format="%.3f"))

    print("\n" + "-" * 115)
    print(f" AFASTAMENTO DAS TENSÕES ÀS 12H00 (p.u.) - BARRA {barra_pior_fd.upper()} ".center(115, '-'))
    print("-" * 115)
    for caso in ['A', 'B']:
        df_jac_v = pd.DataFrame(dados_jacare_v[caso], index=[f"{pl}%" for pl in niveis_penetracao])
        df_jac_v.index.name = "PL"
        df_jac_v['Desvio Máx (p.u.)'] = df_jac_v.max(axis=1) - df_jac_v.min(axis=1)
        print(f"\n>>> TABELA: Tensão Efeito Boca de Jacaré - Caso {caso}")
        print(df_jac_v.to_string(float_format="%.4f"))

    if linha_critica is not None:
        print("\n" + "-" * 115)
        print(f" AFASTAMENTO DE POTÊNCIAS ÀS 12H00 (kW) - LINHA {linha_critica.upper()} ".center(115, '-'))
        print("-" * 115)
        for caso in ['A', 'B']:
            df_jac_p = pd.DataFrame(dados_jacare_p[caso], index=[f"{pl}%" for pl in niveis_penetracao])
            df_jac_p.index.name = "PL"
            print(f"\n>>> TABELA: Potência Efeito Boca de Jacaré - Caso {caso}")
            print(df_jac_p.to_string(float_format="%.4f"))

    print("\n" + "-" * 115)
    print(f" TENSÃO (p.u.) 24 HORAS - BARRA CRÍTICA {barra_pior_fd.upper()} ".center(115, '-'))
    print("-" * 115)
    for caso in ['A', 'B']:
        for f_nome in fases_nomes:
            if dados_tab_tensao[caso][f_nome]:
                gerar_tabela_estatistica_critica(dados_tab_tensao[caso][f_nome],
                                                 f"Tensão (p.u.) - Caso {caso} - {f_nome}")

    print("\n" + "-" * 115)
    print(f" FLUXO DE POTÊNCIA ATIVA NA LINHA (kW) 24 HORAS - LINHA {linha_critica.upper()} ".center(115, '-'))
    print("-" * 115)
    for caso in ['A', 'B']:
        for f_nome in fases_nomes:
            if dados_tab_fluxo[caso][f_nome]:
                gerar_tabela_estatistica_critica(dados_tab_fluxo[caso][f_nome],
                                                 f"Fluxo de Potência (kW) - Caso {caso} - {f_nome}")

    print("\n" + "-" * 115)
    print(f" DEMANDA A JUSANTE CONSTANTE (kW) 24 HORAS - BARRA CRÍTICA {barra_pior_fd.upper()} ".center(115, '-'))
    print("-" * 115)
    for caso in ['A', 'B']:
        for f_nome in fases_nomes:
            if dados_tab_carga_jus[caso][f_nome]:
                gerar_tabela_estatistica_critica(dados_tab_carga_jus[caso][f_nome],
                                                 f"Demanda a Jusante (kW) - Caso {caso} - {f_nome}")

    print("\n" + "-" * 115)
    print(f" GERAÇÃO FOTOVOLTAICA A JUSANTE (kW) 24 HORAS - BARRA CRÍTICA {barra_pior_fd.upper()} ".center(115, '-'))
    print("-" * 115)
    for caso in ['A', 'B']:
        for f_nome in fases_nomes:
            if dados_tab_geracao_jus[caso][f_nome]:
                gerar_tabela_estatistica_critica(dados_tab_geracao_jus[caso][f_nome],
                                                 f"Geração FV a Jusante (kW) - Caso {caso} - {f_nome}")

    print("\n" + "-" * 115)
    print(f" ENVELOPE DIÁRIO DO MAIOR FD% DA REDE ".center(115, '-'))
    print("-" * 115)
    for caso in ['A', 'B']:
        df_env_fd = pd.DataFrame({f"PL {pl}%": pd.Series(v) for pl, v in dados_max_fd_diario[caso].items()})
        if not df_env_fd.empty:
            stats_env_fd = df_env_fd.describe(percentiles=[.01, .05, .25, .5, .75, .95, .99]).T
            print(f"\n>>> TABELA: Desequilíbrio Máximo na Rede ao longo das 24h - Caso {caso}")
            print(stats_env_fd[['min', 'max', 'mean', 'std', '95%']].map(lambda x: f"{x:.4f}").to_string())

    print("\n" + "-" * 115)
    print(f" MAIOR TENSÃO GLOBAL DA REDE (p.u.) 24 HORAS ".center(115, '-'))
    print("-" * 115)
    for caso in ['A', 'B']:
        for f_nome in fases_nomes:
            if dados_max_v_rede[caso][f_nome]:
                gerar_tabela_estatistica_critica(dados_max_v_rede[caso][f_nome],
                                                 f"Tensão Máxima na Rede (p.u.) - Caso {caso} - {f_nome}")

else:
    print("-> Não foi possível identificar a barra (verifique se as barras possuem as 3 fases).")

# ==============================================================================
# 9. TABELA COMPARATIVA DE PERDAS DE ENERGIA TOTAIS DIÁRIAS (SOLICITAÇÃO DO USUÁRIO)
# ==============================================================================
print("\n" + "=" * 115)
print(" 9. TABELA COMPARATIVA DE PERDAS DE ENERGIA TOTAIS DIÁRIAS DA REDE ".center(115, '='))
print("=" * 115)

linhas_tab_energia = []
for pl in niveis_penetracao:
    linhas_tab_energia.append({
        'Cenário FV (%)': pl,
        'Ativa Caso A (kWh)': historico_plot['A']['E_loss_kW'][pl],
        'Ativa Caso B (kWh)': historico_plot['B']['E_loss_kW'][pl],
        'Reativa Caso A (kvarh)': historico_plot['A']['E_loss_kvar'][pl],
        'Reativa Caso B (kvarh)': historico_plot['B']['E_loss_kvar'][pl],
        'Total Caso A (kVAh)': historico_plot['A']['E_loss_kVA'][pl],
        'Total Caso B (kVAh)': historico_plot['B']['E_loss_kVA'][pl]
    })

df_perdas_energia_total = pd.DataFrame(linhas_tab_energia)
print(df_perdas_energia_total.to_string(index=False, float_format="%.2f"))
print("=" * 115 + "\n")

print("\n" + "=" * 60)
print(f" SUCESSO! Todos os gráficos foram salvos na pasta: '{pasta_saida}'")
print("=" * 60)