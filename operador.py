import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
# Importamos as funções do seu arquivo original (certifique-se que o nome do arquivo seja exatamente este)
from matemático import get_gamma_data_v2, get_gamma_levels 

st.set_page_config(page_title="GEX SIGNAL - Operacional", layout="centered")

# --- CONFIGURAÇÃO ---
st.title("🎯 GEX SIGNAL: Tomada de Decisão")
ticker = st.sidebar.text_input("Ticker para Operar", value="QQQ").upper()
capital = st.sidebar.number_input("Capital da Operação (USD)", value=1000)

# Obtendo os dados sincronizados
calls_data, puts_data, current_price, df_price, current_expiry = get_gamma_data_v2(ticker)

if not calls_data.empty:
    levels = get_gamma_levels(calls_data, puts_data, current_price)
    
    # --- LÓGICA DE DECISÃO ---
    zero_gamma = levels['zero']
    put_wall = levels['put']
    call_wall = levels['call']
    
    status = ""
    cor_status = ""
    acao = ""
    alvo = 0
    stop = 0
    detalhe = ""

    # CENÁRIO 1: COMPRA (BULLISH)
    if current_price > zero_gamma:
        status = "ZONA DE ESTABILIDADE (GAMA POSITIVO)"
        cor_status = "green"
        if current_price <= put_wall * 1.01: # Perto da Put Wall
            acao = "COMPRA FORTE (Repique na Muralha)"
            alvo = zero_gamma
            stop = put_wall * 0.99
        else:
            acao = "COMPRA (Retorno à Média)"
            alvo = call_wall
            stop = zero_gamma

    # CENÁRIO 2: VENDA (BEARISH/ALERTA)
    else:
        status = "ZONA DE ACELERAÇÃO (GAMA NEGATIVO)"
        cor_status = "red"
        if current_price < zero_gamma:
            acao = "VENDA (Momentum de Queda)"
            alvo = put_wall
            stop = zero_gamma * 1.005
            detalhe = "Cuidado: Volatilidade alta abaixo do Zero Gamma!"

    # --- INTERFACE DE SINAL ---
    st.subheader(f"Monitorando: {ticker} | Preço: ${current_price:.2f}")
    
    st.markdown(f"""
    <div style="background-color: {cor_status}; padding: 20px; border-radius: 10px; text-align: center;">
        <h2 style="color: white; margin: 0;">{acao}</h2>
        <p style="color: white; font-weight: bold;">{status}</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # --- TABELA DE EXECUÇÃO ---
    col1, col2 = st.columns(2)
    with col1:
        st.metric("🎯 Alvo (Take Profit)", f"${alvo:.2f}")
        st.write(f"**Potencial:** {((alvo/current_price)-1)*100:.2f}%")
    with col2:
        st.metric("🛡️ Stop Loss (Saída)", f"${stop:.2f}")
        st.write(f"**Risco:** {((stop/current_price)-1)*100:.2f}%")

    st.info(f"💡 **Explicação:** {detalhe if detalhe else 'O mercado tende a ser atraído pelos níveis de maior liquidez (Walls).'}")

    # --- CHECKLIST OPERACIONAL ---
    st.markdown("### ✅ Checklist para Entrar:")
    if current_price > zero_gamma:
        st.write("- [ ] Preço está acima do Zero Gamma? **Sim**")
        st.write(f"- [ ] O alvo ${alvo} compensa o risco?")
    else:
        st.write("- [ ] O mercado perdeu o suporte do Zero Gamma? **Sim**")
        st.write("- [ ] Existe volume de venda confirmando?")

else:
    st.error("Não foi possível carregar os dados para este Ticker.")

st.caption("Nota: Este app é uma ferramenta de auxílio baseada em dados matemáticos. Use gerenciamento de risco.")
