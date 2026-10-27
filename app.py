"""Painel de opções: cotação, cadeia com gregas, calculadora Black & Scholes,
payoff de estratégias, superfície de volatilidade e glossário.

Rodar: streamlit run app.py
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import brapi_opcoes as api
import bs
import estrategias as es
from conceitos import CONCEITOS

TZ = ZoneInfo("America/Sao_Paulo")
COR_CALL, COR_PUT, COR_SPOT, COR_NEUTRA = "#4ED6A0", "#FF7A7A", "#E6FF01", "#9aa0ad"
COR_T0, COR_VENC = "#7FB3FF", "#E6FF01"

st.set_page_config(page_title="Painel de Opções", page_icon="📈", layout="wide")


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def dica(nome: str) -> str:
    return CONCEITOS[nome]["curto"]


def fmt_brl(v, casas=2) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "n/d"
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def fmt_num(v, casas=2, sufixo="") -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "n/d"
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + sufixo


def fmt_pnl(v) -> str:
    if v is None:
        return "n/d"
    if v == math.inf:
        return "ilimitado"
    if v == -math.inf:
        return "ilimitada"
    return fmt_brl(v)


def hoje_br() -> date:
    return datetime.now(TZ).date()


def dias_ate(venc: str) -> int:
    return (date.fromisoformat(venc) - hoje_br()).days


def T_de(venc: str, base: int) -> float:
    if base == 252:
        return bs.anos(bs.dias_uteis(hoje_br(), date.fromisoformat(venc)), 252)
    return bs.anos(dias_ate(venc), 365)


def layout_plotly(fig: go.Figure, altura: int = 420, **kw) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=altura,
        margin=dict(l=40, r=20, t=80, b=40),
        title=dict(y=0.97, yanchor="top"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
        hovermode="x unified",
        **kw,
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)")
    return fig


def grade_precos(S: float, largura: float = 0.35, n: int = 801):
    return np.linspace(S * (1 - largura), S * (1 + largura), n)


# --------------------------------------------------------------------------- #
# Dados (cache)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=60, show_spinner=False)
def q_cotacao(sym: str) -> dict:
    return api.cotacao(sym)


@st.cache_data(ttl=3600, show_spinner=False)
def q_vencimentos(sym: str) -> list[str]:
    return api.vencimentos(sym)


@st.cache_data(ttl=900, show_spinner=False)
def q_cadeia(sym: str, venc: str):
    return api.cadeia(sym, venc)


@st.cache_data(ttl=900, show_spinner=False)
def q_analytics(sym: str, venc: str):
    return api.analytics(sym, venc)


@st.cache_data(ttl=900, show_spinner=False)
def q_posicoes(sym: str, venc: str):
    return api.posicoes(sym, venc)


@st.cache_data(ttl=3600, show_spinner=False)
def q_historico(sym: str) -> pd.DataFrame:
    return api.historico(sym, "1y")


@st.cache_data(ttl=3600, show_spinner=False)
def q_selic():
    return api.selic()


def carregar(fn, *args):
    """Chama fn(*args) e devolve (resultado, mensagem_de_erro)."""
    try:
        return fn(*args), None
    except api.BrapiAuthError as e:
        return None, f"Autenticação: {e}"
    except api.BrapiRateLimitError as e:
        return None, f"Limite de requisições da brapi: {e}"
    except api.BrapiNotFoundError as e:
        return None, f"Não encontrado: {e}"
    except api.BrapiError as e:
        return None, f"Erro da brapi: {e}"
    except Exception as e:  # rede, parse
        return None, f"Falha ao consultar a brapi: {e}"


@st.cache_data(ttl=900, show_spinner=False)
def cadeia_completa(sym: str, venc: str) -> tuple[pd.DataFrame, str | None]:
    """Cadeia + analytics num DataFrame só (uma linha por série)."""
    cad, data_cad = api.cadeia(sym, venc)
    try:
        ana, _ = api.analytics(sym, venc)
    except api.BrapiError:
        ana = pd.DataFrame()
    if cad.empty:
        return cad, data_cad
    if not ana.empty:
        cols = ["symbol", "model", "underlyingPrice", "riskFreeRate", "dividendYield", "timeToExpirationYears",
                "impliedVolatility", "delta", "gamma", "theta", "vega", "rho", "confidence", "nullReason"]
        cad = cad.merge(ana[cols], on="symbol", how="left")
    else:
        for c in ("impliedVolatility", "delta", "gamma", "theta", "vega", "rho", "confidence"):
            cad[c] = np.nan
    return cad, data_cad


def iv_atm_robusta(df: pd.DataFrame, S: float) -> float | None:
    """IV no dinheiro: mediana das séries com |delta| entre 0,35 e 0,65; senão o strike mais próximo do spot."""
    com_iv = df[df["impliedVolatility"].notna() & (df["impliedVolatility"] > 0)]
    if com_iv.empty:
        return None
    miolo = com_iv[com_iv["delta"].abs().between(0.35, 0.65)] if "delta" in com_iv else pd.DataFrame()
    if len(miolo) >= 2:
        return float(miolo["impliedVolatility"].median())
    k_atm = com_iv.loc[(com_iv["strike"] - S).abs().idxmin(), "strike"]
    return float(com_iv.loc[np.isclose(com_iv["strike"], k_atm), "impliedVolatility"].mean())


def preco_referencia(row) -> float | None:
    """Prêmio de referência de uma série: meio do bid/ask se os dois existem, senão último."""
    bid, ask, close = row.get("bid"), row.get("ask"), row.get("close")
    try:
        if bid and ask and float(bid) > 0 and float(ask) > 0 and float(ask) >= float(bid):
            return (float(bid) + float(ask)) / 2
    except (TypeError, ValueError):
        pass
    try:
        return float(close) if close is not None and float(close) > 0 else None
    except (TypeError, ValueError):
        return None


def gregas_ao_vivo(df: pd.DataFrame, S: float, T: float, r: float, q: float, base: int) -> pd.DataFrame:
    """Recalcula preço teórico e gregas com o spot atual e a IV do fechamento."""
    out = df.copy()
    cols = {"moneyness": [], "situacao": [], "teorico": [], "delta_vivo": [], "gamma_vivo": [], "theta_dia": [], "vega_pt": [], "prob_exercicio": []}
    for _, row in out.iterrows():
        tipo = row["side"]
        K = float(row["strike"])
        iv = row.get("impliedVolatility")
        cols["moneyness"].append(bs.moneyness(tipo, S, K))
        cols["situacao"].append(bs.classifica_moneyness(tipo, S, K))
        if iv is None or not np.isfinite(iv) or T <= 0:
            for k in ("teorico", "delta_vivo", "gamma_vivo", "theta_dia", "vega_pt", "prob_exercicio"):
                cols[k].append(np.nan)
            continue
        g = bs.gregas(tipo, S, K, T, r, float(iv), q)
        cols["teorico"].append(g.preco)
        cols["delta_vivo"].append(g.delta)
        cols["gamma_vivo"].append(g.gamma)
        cols["theta_dia"].append(g.theta / base)
        cols["vega_pt"].append(g.vega / 100)
        cols["prob_exercicio"].append(g.prob_exercicio)
    for k, v in cols.items():
        out[k] = v
    return out


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("Painel de Opções")
    ticker = st.text_input("Ativo-objeto", value=st.session_state.get("ticker", "PETR4"), help="Ticker da B3 (ação, ETF ou índice com opções).").strip().upper()
    st.session_state["ticker"] = ticker

    auto = st.toggle("Atualizar cotação a cada 60 s", value=False, help="Recarrega só o bloco de cotação. Os dados de opções são do fechamento do dia.")
    if st.button("Atualizar agora", width="stretch"):
        q_cotacao.clear()
        st.rerun()

    st.divider()
    st.subheader("Parâmetros do modelo")
    base = st.radio("Contagem de dias", [365, 252], format_func=lambda b: "Corridos / 365 (padrão brapi)" if b == 365 else "Úteis / 252", horizontal=False,
                    help="Como converter dias até o vencimento em anos (T). A brapi calcula IV e gregas com dias corridos/365.")
    selic_api = q_selic() if api.api_key() else None
    r_default = (selic_api or 0.1375) * 100
    r_pct = st.number_input("Taxa livre de risco (% a.a.)", value=float(round(r_default, 2)), step=0.25, min_value=0.0, max_value=50.0,
                            help=("Selic do dia via brapi." if selic_api else "Selic padrão; defina BRAPI_API_KEY para buscar a atual.") + " Usada como r no Black & Scholes.")
    q_pct = st.number_input("Dividend yield (% a.a.)", value=0.0, step=0.5, min_value=0.0, max_value=30.0,
                            help="Rendimento contínuo de dividendos (q). A brapi usa 0 nas gregas publicadas.")
    lote = st.number_input("Lote (contratos por operação)", value=100, step=100, min_value=1, help="Opções de ação na B3 têm lote padrão de 100.")
    r, q = r_pct / 100, q_pct / 100

    st.divider()
    if not api.api_key():
        st.warning(f"Sem BRAPI_API_KEY: só {', '.join(api.SANDBOX)} funcionam. Coloque a chave num arquivo .env ou nos Secrets do Streamlit.", icon="🔑")
    st.caption("Dados: brapi.dev. Cotação do ativo com até 5 min de atraso; opções, IV e gregas do fechamento do pregão anterior.")


# --------------------------------------------------------------------------- #
# Cabeçalho (cotação do ativo)
# --------------------------------------------------------------------------- #
@st.fragment(run_every="60s" if auto else None)
def bloco_cotacao():
    cot, erro = carregar(q_cotacao, ticker)
    if erro:
        st.error(erro)
        st.session_state["S"] = None
        return
    S = cot["preco"]
    st.session_state["S"] = S
    hora = cot.get("hora")
    try:
        ref = datetime.fromisoformat(hora.replace("Z", "+00:00")).astimezone(TZ)
        ref_txt = f"{ref:%d/%m/%Y %H:%M}"
        atrasado = ref.date() != hoje_br()
    except Exception:
        ref_txt, atrasado = "n/d", True

    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1.4])
    c1.metric(f"{cot['symbol']} · {cot.get('nome') or ''}", fmt_brl(S), f"{fmt_num(cot.get('variacao'))} ({fmt_num(cot.get('variacao_pct'))}%)")
    c2.metric("Abertura", fmt_brl(cot.get("abertura")))
    c3.metric("Mín / Máx do dia", f"{fmt_num(cot.get('minima'))} / {fmt_num(cot.get('maxima'))}")
    c4.metric("Fech. anterior", fmt_brl(cot.get("fechamento_anterior")))
    c5.metric("Referência da cotação", ref_txt, "não é de hoje" if atrasado else "hoje", delta_color="inverse" if atrasado else "off",
              help="Horário (Brasília) da última negociação que a brapi recebeu. No plano Pro o atraso é de até 5 minutos.")


bloco_cotacao()
S = st.session_state.get("S")
if not S:
    st.stop()

vencs, erro_v = carregar(q_vencimentos, ticker)
if erro_v:
    st.error(erro_v)
    st.stop()
vencs = [v for v in vencs if dias_ate(v) >= 0]
if not vencs:
    st.warning("Nenhum vencimento futuro com negócios para este ativo.")
    st.stop()


venc_padrao = next((v for v in vencs if dias_ate(v) >= 20), vencs[0])
idx_padrao = vencs.index(venc_padrao)


def rotulo_venc(v: str) -> str:
    d = dias_ate(v)
    return f"{date.fromisoformat(v):%d/%m/%Y}  ({d} dias)"


tab_cadeia, tab_calc, tab_payoff, tab_surf, tab_conceitos = st.tabs(
    ["Cadeia e gregas", "Calculadora B&S", "Payoff de estratégias", "Superfície de vol", "Conceitos"]
)

# =========================================================================== #
# 1. Cadeia
# =========================================================================== #
with tab_cadeia:
    col_a, col_b, col_c = st.columns([1.3, 1, 1.2])
    venc = col_a.selectbox("Vencimento", vencs, index=idx_padrao, format_func=rotulo_venc, key="venc_cadeia")
    lado = col_b.radio("Mostrar", ["Ambos", "Calls", "Puts"], horizontal=True, key="lado_cadeia")
    faixa = col_c.slider("Faixa de strikes em torno do preço (%)", 5, 50, 15, step=5, key="faixa_cadeia")

    T = T_de(venc, base)
    dados, erro = carregar(cadeia_completa, ticker, venc)
    if erro:
        st.error(erro)
    elif dados is None or dados[0].empty:
        st.info("Sem séries negociadas neste vencimento.")
    else:
        df, data_fech = dados
        df = df[(df["strike"] >= S * (1 - faixa / 100)) & (df["strike"] <= S * (1 + faixa / 100))]
        if lado == "Calls":
            df = df[df["side"] == "call"]
        elif lado == "Puts":
            df = df[df["side"] == "put"]
        df = gregas_ao_vivo(df, S, T, r, q, base)

        # métricas de topo
        iv_atm = iv_atm_robusta(df, S)
        oi_c = float(df.loc[df["side"] == "call", "openInterest"].fillna(0).sum())
        oi_p = float(df.loc[df["side"] == "put", "openInterest"].fillna(0).sum())
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Dias até o vencimento", f"{dias_ate(venc)} corridos", f"{bs.dias_uteis(hoje_br(), date.fromisoformat(venc))} úteis", delta_color="off")
        m2.metric("IV no dinheiro (ATM)", fmt_num(iv_atm * 100 if iv_atm else None, 1, "%"), help=dica("Volatilidade implícita") + " Aqui: mediana das séries com |delta| entre 0,35 e 0,65.")
        m3.metric("Movimento esperado (1σ)", f"± {fmt_brl(bs.movimento_esperado(S, iv_atm, T))}" if iv_atm else "n/d",
                  help="S × σ × √T: faixa onde o ativo deve ficar em ~68% dos cenários até o vencimento, usando a IV ATM.")
        m4.metric("Razão put/call (OI)", fmt_num(oi_p / oi_c if oi_c else None, 2), help=dica("Contratos em aberto (OI)"))
        m5.metric("Fechamento dos dados de opções", f"{date.fromisoformat(data_fech):%d/%m/%Y}" if data_fech else "n/d",
                  help="Último, bid/ask, volume, OI, IV e gregas vêm do fechamento deste pregão. As gregas 'ao vivo' recalculam com o preço atual do ativo e a IV do fechamento.")

        st.markdown("##### Séries")
        st.caption("Gregas **ao vivo** = Black & Scholes com o preço atual do ativo e a IV do fechamento. Passe o mouse no cabeçalho para a explicação de cada coluna.")
        vis = df[["symbol", "side", "optionStyle", "strike", "moneyness", "situacao", "close", "bid", "ask", "teorico", "volume", "openInterest",
                  "impliedVolatility", "delta_vivo", "gamma_vivo", "theta_dia", "vega_pt", "prob_exercicio", "confidence"]].copy()
        vis["side"] = vis["side"].map({"call": "Call", "put": "Put"})
        vis["optionStyle"] = vis["optionStyle"].map({"european": "Europeia", "american": "Americana"}).fillna("")
        vis["impliedVolatility"] = vis["impliedVolatility"] * 100
        vis["prob_exercicio"] = vis["prob_exercicio"] * 100

        def _cor_linha(row):
            if row["situacao"] == "ATM":
                return ["background-color: rgba(230,255,1,0.12)"] * len(row)
            if row["situacao"] == "ITM":
                return ["background-color: rgba(78,214,160,0.08)"] * len(row)
            return [""] * len(row)

        st.dataframe(
            vis.style.apply(_cor_linha, axis=1),
            width="stretch",
            hide_index=True,
            height=min(60 + 35 * len(vis), 700),
            column_config={
                "symbol": st.column_config.TextColumn("Série"),
                "side": st.column_config.TextColumn("Tipo"),
                "optionStyle": st.column_config.TextColumn("Estilo", help="Europeia: exercício só no vencimento. Americana: a qualquer momento (a brapi usa árvore binomial)."),
                "strike": st.column_config.NumberColumn("Strike", format="R$ %.2f"),
                "moneyness": st.column_config.NumberColumn("Moneyness", format="%.3f", help=dica("Moneyness") + " Aqui: S/K para call, K/S para put. >1 = ITM."),
                "situacao": st.column_config.TextColumn("Situação", help="ITM = dentro do dinheiro, ATM = no dinheiro (±2%), OTM = fora do dinheiro."),
                "close": st.column_config.NumberColumn("Último", format="%.2f", help="Último negócio do fechamento."),
                "bid": st.column_config.NumberColumn("Bid", format="%.2f", help="Melhor oferta de compra no fechamento (0 = sem oferta)."),
                "ask": st.column_config.NumberColumn("Ask", format="%.2f", help="Melhor oferta de venda no fechamento (0 = sem oferta)."),
                "teorico": st.column_config.NumberColumn("Teórico (vivo)", format="%.2f", help="Preço Black & Scholes com o spot atual e a IV do fechamento. Compare com o último: diferença = quanto o ativo andou desde o fechamento."),
                "volume": st.column_config.NumberColumn("Vol. negociado", format="%d"),
                "openInterest": st.column_config.NumberColumn("Contratos em aberto", format="%d", help=dica("Contratos em aberto (OI)")),
                "impliedVolatility": st.column_config.NumberColumn("IV %", format="%.1f", help=dica("Volatilidade implícita")),
                "delta_vivo": st.column_config.NumberColumn("Delta", format="%.3f", help=dica("Delta")),
                "gamma_vivo": st.column_config.NumberColumn("Gamma", format="%.4f", help=dica("Gamma")),
                "theta_dia": st.column_config.NumberColumn("Theta/dia", format="%.4f", help=dica("Theta") + f" Aqui por dia (base {base})."),
                "vega_pt": st.column_config.NumberColumn("Vega/pt", format="%.4f", help=dica("Vega")),
                "prob_exercicio": st.column_config.NumberColumn("P(exercício) %", format="%.0f", help="N(d2) para call e N(-d2) para put: probabilidade neutra ao risco de terminar dentro do dinheiro."),
                "confidence": st.column_config.TextColumn("Confiança", help="Qualidade da IV calculada pela brapi (high = preço de fechamento consistente; low = pouca liquidez ou bid/ask largo)."),
            },
        )

        # gráficos
        g1, g2 = st.columns(2)
        with g1:
            fig = go.Figure()
            for s_, cor, nome in (("call", COR_CALL, "Calls"), ("put", COR_PUT, "Puts")):
                sub = df[(df["side"] == s_) & df["impliedVolatility"].notna()].sort_values("strike")
                if not sub.empty:
                    fig.add_trace(go.Scatter(x=sub["strike"], y=sub["impliedVolatility"] * 100, mode="lines+markers", name=nome, line=dict(color=cor),
                                             hovertemplate="Strike %{x:.2f}<br>IV %{y:.1f}%<extra>" + nome + "</extra>"))
            fig.add_vline(x=S, line=dict(color=COR_SPOT, dash="dot"), annotation_text="spot", annotation_position="top")
            fig.update_layout(title="Sorriso de volatilidade (IV por strike)", xaxis_title="Strike", yaxis_title="IV (% a.a.)")
            st.plotly_chart(layout_plotly(fig, 380), width="stretch")
            st.caption(dica("Superfície de volatilidade"))
        with g2:
            fig = go.Figure()
            for s_, cor, nome in (("call", COR_CALL, "Calls"), ("put", COR_PUT, "Puts")):
                sub = df[df["side"] == s_].sort_values("strike")
                if not sub.empty:
                    fig.add_trace(go.Bar(x=sub["strike"], y=sub["openInterest"], name=nome, marker_color=cor, opacity=0.85,
                                         hovertemplate="Strike %{x:.2f}<br>OI %{y:,.0f}<extra>" + nome + "</extra>"))
            fig.add_vline(x=S, line=dict(color=COR_SPOT, dash="dot"), annotation_text="spot", annotation_position="top")
            fig.update_layout(title="Contratos em aberto por strike", xaxis_title="Strike", yaxis_title="Contratos", barmode="group")
            st.plotly_chart(layout_plotly(fig, 380), width="stretch")
            st.caption("Strikes com muito OI tendem a 'segurar' o preço perto do vencimento (hedge dos lançadores).")

        with st.expander("Posições em aberto: coberto, descoberto e bloqueado"):
            pos, erro_p = carregar(q_posicoes, ticker, venc)
            if erro_p:
                st.warning(erro_p)
            elif pos is not None and not pos[0].empty:
                dfp = pos[0]
                dfp = dfp[(dfp["strike"] >= S * (1 - faixa / 100)) & (dfp["strike"] <= S * (1 + faixa / 100))]
                fig = go.Figure()
                for col, nome, cor in (("coveredQuantity", "Coberto", COR_CALL), ("uncoveredQuantity", "Descoberto", COR_PUT), ("blockedQuantity", "Bloqueado", COR_NEUTRA)):
                    fig.add_trace(go.Bar(x=dfp["symbol"], y=dfp[col], name=nome, marker_color=cor))
                fig.update_layout(barmode="stack", title=f"Composição das posições (relatório de {pos[1] or 'n/d'})", xaxis_title="Série", yaxis_title="Contratos")
                st.plotly_chart(layout_plotly(fig, 360), width="stretch")
                st.caption("Coberto: lançador tem a ação. Descoberto: lançador sem a ação (risco de chamada de margem). Bloqueado: ação depositada em garantia na B3.")
            else:
                st.info("Sem relatório de posições para este vencimento.")

# =========================================================================== #
# 2. Calculadora
# =========================================================================== #
with tab_calc:
    st.markdown("##### Black & Scholes-Merton")
    st.caption(dica("Black & Scholes"))
    e1, e2, e3, e4, e5, e6 = st.columns(6)
    tipo = e1.selectbox("Tipo", ["call", "put"], format_func=str.upper, key="calc_tipo")
    S_c = e2.number_input("Preço do ativo (S)", value=float(round(S, 2)), step=0.1, min_value=0.01, key="calc_S", help="Padrão: cotação atual.")
    K_c = e3.number_input("Strike (K)", value=float(round(S, 0)), step=0.5, min_value=0.01, key="calc_K")
    dias_c = e4.number_input("Dias até o vencimento", value=max(dias_ate(venc_padrao), 1), step=1, min_value=0, key="calc_dias", help=f"Base {base}: corridos/365 ou úteis/252 conforme a sidebar.")
    vol_c = e5.number_input("Volatilidade (% a.a.)", value=35.0, step=1.0, min_value=0.1, max_value=500.0, key="calc_vol", help=dica("Volatilidade implícita"))
    preco_mkt = e6.number_input("Preço de mercado (p/ IV)", value=0.0, step=0.05, min_value=0.0, key="calc_mkt", help="Informe o prêmio negociado para o painel resolver a vol implícita.")

    T_c = bs.anos(dias_c, base)
    sig_c = vol_c / 100
    g = bs.gregas(tipo, S_c, K_c, T_c, r, sig_c, q)

    if preco_mkt > 0:
        iv = bs.vol_implicita(tipo, preco_mkt, S_c, K_c, T_c, r, q)
        if iv is None:
            st.warning("Preço fora dos limites de arbitragem para esses parâmetros (abaixo do intrínseco descontado ou acima do máximo). Não há IV que o reproduza.")
        else:
            st.success(f"Vol implícita do preço {fmt_brl(preco_mkt)}: **{iv * 100:.2f}% a.a.** (o modelo com {vol_c:.1f}% dá {fmt_brl(g.preco)}).")

    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    k1.metric("Prêmio teórico", fmt_brl(g.preco), f"intrínseco {fmt_num(float(bs.valor_intrinseco(tipo, S_c, K_c)))}", delta_color="off", help="Valor do tempo = prêmio − intrínseco.")
    k2.metric("Moneyness", f"{bs.moneyness(tipo, S_c, K_c):.3f} · {bs.classifica_moneyness(tipo, S_c, K_c)}", help=dica("Moneyness"))
    k3.metric("Delta", fmt_num(g.delta, 3), help=dica("Delta"))
    k4.metric("Gamma", fmt_num(g.gamma, 4), help=dica("Gamma"))
    k5.metric("Theta / dia", fmt_num(g.theta / base, 4), f"{fmt_num(g.theta, 2)} ao ano", delta_color="off", help=dica("Theta"))
    k6.metric("Vega / ponto", fmt_num(g.vega / 100, 4), help=dica("Vega"))
    k7.metric("Rho / ponto", fmt_num(g.rho / 100, 4), help=dica("Rho"))
    st.caption(f"P(exercício) = {g.prob_exercicio * 100:.1f}% · d1 = {g.d1:.3f} · d2 = {g.d2:.3f} · T = {T_c:.4f} anos · "
               f"movimento esperado 1σ = ± {fmt_brl(bs.movimento_esperado(S_c, sig_c, T_c))}")

    S_grid = grade_precos(S_c)
    c_left, c_right = st.columns(2)
    with c_left:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=S_grid, y=bs.preco(tipo, S_grid, K_c, T_c, r, sig_c, q), name="Hoje (modelo)", line=dict(color=COR_T0)))
        fig.add_trace(go.Scatter(x=S_grid, y=bs.valor_intrinseco(tipo, S_grid, K_c), name="No vencimento (intrínseco)", line=dict(color=COR_VENC, dash="dash")))
        fig.add_vline(x=S_c, line=dict(color=COR_SPOT, dash="dot"))
        fig.update_layout(title="Prêmio em função do preço do ativo", xaxis_title="Preço do ativo", yaxis_title="Prêmio (R$)")
        st.plotly_chart(layout_plotly(fig, 380), width="stretch")
        st.caption("A distância entre as duas curvas é o valor do tempo. Ele é máximo no dinheiro e some no vencimento.")

        dias_grid = np.arange(max(int(dias_c), 1), 0, -1)
        fig = go.Figure()
        for mult, nome in ((0.95, "5% OTM"), (1.0, "ATM"), (1.05, "5% ITM")):
            K_ = S_c / mult if tipo == "call" else S_c * mult
            fig.add_trace(go.Scatter(x=dias_grid, y=[float(bs.preco(tipo, S_c, K_, bs.anos(d, base), r, sig_c, q)) for d in dias_grid], name=nome))
        fig.update_layout(title="Decaimento do prêmio com o tempo (theta)", xaxis_title="Dias até o vencimento", yaxis_title="Prêmio (R$)")
        fig.update_xaxes(autorange="reversed")
        st.plotly_chart(layout_plotly(fig, 340), width="stretch")
        st.caption("O decaimento acelera nas últimas semanas, sobretudo no dinheiro.")
    with c_right:
        fig = make_subplots(rows=2, cols=2, subplot_titles=("Delta", "Gamma", f"Theta por dia (base {base})", "Vega por ponto"))
        gre = [bs.gregas(tipo, float(s_), K_c, T_c, r, sig_c, q) for s_ in S_grid[::4]]
        xs = S_grid[::4]
        fig.add_trace(go.Scatter(x=xs, y=[x.delta for x in gre], name="Delta", line=dict(color=COR_CALL)), row=1, col=1)
        fig.add_trace(go.Scatter(x=xs, y=[x.gamma for x in gre], name="Gamma", line=dict(color=COR_T0)), row=1, col=2)
        fig.add_trace(go.Scatter(x=xs, y=[x.theta / base for x in gre], name="Theta/dia", line=dict(color=COR_PUT)), row=2, col=1)
        fig.add_trace(go.Scatter(x=xs, y=[x.vega / 100 for x in gre], name="Vega/pt", line=dict(color=COR_VENC)), row=2, col=2)
        for rr in (1, 2):
            for cc in (1, 2):
                fig.add_vline(x=S_c, line=dict(color=COR_SPOT, dash="dot"), row=rr, col=cc)
        fig.update_layout(showlegend=False, title="Gregas em função do preço do ativo")
        st.plotly_chart(layout_plotly(fig, 740), width="stretch")
        st.caption("Gamma e vega têm pico no dinheiro; theta é mais negativo exatamente onde o gamma é maior.")

# =========================================================================== #
# 3. Payoff
# =========================================================================== #
with tab_payoff:
    p1, p2 = st.columns([1.4, 1])
    venc_p = p1.selectbox("Vencimento", vencs, index=idx_padrao, format_func=rotulo_venc, key="venc_payoff")
    preset = p2.selectbox("Estratégia", list(es.PRESETS), key="preset", help="Modelo de pernas; edite strikes, prêmios e quantidades na tabela.")
    T_p = T_de(venc_p, base)
    dados_p, erro_p = carregar(cadeia_completa, ticker, venc_p)
    cad_p = dados_p[0] if dados_p and not dados_p[0].empty else pd.DataFrame()
    if erro_p:
        st.warning(f"Cadeia indisponível ({erro_p}). Os prêmios precisam ser digitados.")

    strikes = sorted(cad_p["strike"].dropna().unique().tolist()) if not cad_p.empty else None

    def _premio(tipo_, k_):
        if cad_p.empty:
            return None
        row = cad_p[(cad_p["side"] == tipo_) & (np.isclose(cad_p["strike"], k_))]
        return preco_referencia(row.iloc[0]) if not row.empty else None

    def _vol(tipo_, k_):
        if cad_p.empty:
            return None
        row = cad_p[(cad_p["side"] == tipo_) & (np.isclose(cad_p["strike"], k_))]
        v = row.iloc[0]["impliedVolatility"] if not row.empty else None
        return float(v) if v is not None and np.isfinite(v) else None

    chave_montagem = (preset, venc_p, ticker)
    if st.session_state.get("pernas_chave") != chave_montagem:
        st.session_state["pernas_chave"] = chave_montagem
        st.session_state["pernas_df"] = pd.DataFrame([
            {"Tipo": {"call": "Call", "put": "Put", "acao": "Ação"}[p["tipo"]], "Lado": "Compra" if p["lado"] > 0 else "Venda",
             "Strike": p["strike"] if p["tipo"] != "acao" else None, "Prêmio": round(p["premio"], 2), "Qtd": p["qtd"], "Vol %": round(p["vol"] * 100, 1) if p["vol"] else None}
            for p in es.montar_pernas(preset, S, strikes, _premio, _vol)
        ])

    info = es.PRESETS[preset]
    st.info(f"**{preset}** · visão: {info['visao']}. {info['resumo']}", icon="🧭")
    st.caption("Prêmio pré-preenchido = meio do bid/ask do fechamento (ou último). Vol = IV da série. Para a ação, 'Prêmio' é o preço de compra.")
    editado = st.data_editor(
        st.session_state["pernas_df"], num_rows="dynamic", width="stretch", key="editor_pernas", hide_index=True,
        column_config={
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Call", "Put", "Ação"], required=True),
            "Lado": st.column_config.SelectboxColumn("Lado", options=["Compra", "Venda"], required=True),
            "Strike": st.column_config.NumberColumn("Strike", format="%.2f", help="Strike da opção (vazio para ação)."),
            "Prêmio": st.column_config.NumberColumn("Prêmio", format="%.2f", help="Preço por unidade pago (compra) ou recebido (venda)."),
            "Qtd": st.column_config.NumberColumn("Qtd", min_value=1, step=1, format="%d", help="Múltiplos do lote."),
            "Vol %": st.column_config.NumberColumn("Vol %", format="%.1f", help="IV usada para marcar a perna na curva de hoje (T+0)."),
        },
    )

    pernas = []
    for _, row in editado.dropna(subset=["Tipo", "Lado"]).iterrows():
        tipo_ = {"Call": "call", "Put": "put", "Ação": "acao"}[row["Tipo"]]
        premio_ = float(row["Prêmio"]) if pd.notna(row["Prêmio"]) else (S if tipo_ == "acao" else 0.0)
        strike_ = float(row["Strike"]) if pd.notna(row["Strike"]) else 0.0
        if tipo_ != "acao" and strike_ <= 0:
            continue
        pernas.append({"tipo": tipo_, "lado": 1 if row["Lado"] == "Compra" else -1, "strike": strike_, "premio": premio_,
                       "qtd": int(row["Qtd"]) if pd.notna(row["Qtd"]) else 1, "vol": float(row["Vol %"]) / 100 if pd.notna(row["Vol %"]) and row["Vol %"] else 0.0})

    if not pernas:
        st.warning("Adicione ao menos uma perna.")
    else:
        vols = [p["vol"] for p in pernas if p["vol"]]
        vol_ref = float(np.mean(vols)) if vols else 0.30
        ST = grade_precos(S, 0.40, 1601)
        pnl_venc = es.payoff_vencimento(pernas, ST, int(lote))
        dias_rest = dias_ate(venc_p)
        d_sel = st.slider("Curva intermediária: dias que faltam para o vencimento", 0, max(dias_rest, 1), max(dias_rest, 1), key="dias_t0",
                          help="0 = no vencimento. A curva usa Black & Scholes com a vol de cada perna.")
        T_sel = bs.anos(d_sel, base) if base == 365 else bs.anos(d_sel * 252 / 365, 252)
        pnl_t0 = es.valor_t0(pernas, ST, T_de(venc_p, base), r, q, vol_ref, int(lote))
        pnl_sel = es.valor_t0(pernas, ST, T_sel, r, q, vol_ref, int(lote))
        res = es.resumo(pernas, ST, pnl_venc)
        custo = es.custo_liquido(pernas, int(lote))
        prob = es.prob_lucro(ST, pnl_venc, S, vol_ref, T_p)
        gp = es.gregas_posicao(pernas, S, T_p, r, q, vol_ref, int(lote))

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Custo líquido (opções)", fmt_brl(custo), "débito" if custo > 0 else ("crédito" if custo < 0 else "zero"), delta_color="off",
                  help="Soma dos prêmios pagos menos recebidos, vezes o lote. Não inclui a compra da ação.")
        m2.metric("Ganho máximo", fmt_pnl(res["ganho_max"]))
        m3.metric("Perda máxima", fmt_pnl(res["perda_max"]))
        m4.metric("Breakeven", " · ".join(fmt_num(b) for b in res["breakevens"]) or "n/d", help="Preços do ativo no vencimento em que o resultado é zero.")
        m5.metric("Prob. de lucro no vencimento", fmt_num(prob * 100, 0, "%"), help=f"Distribuição lognormal sem deriva com vol {vol_ref * 100:.1f}% (média das IVs das pernas).")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ST, y=pnl_venc, name="No vencimento", line=dict(color=COR_VENC, width=3)))
        fig.add_trace(go.Scatter(x=ST, y=pnl_t0, name="Hoje (T+0)", line=dict(color=COR_T0, dash="dot")))
        if 0 < d_sel < dias_rest:
            fig.add_trace(go.Scatter(x=ST, y=pnl_sel, name=f"Faltando {d_sel} dias", line=dict(color=COR_CALL, dash="dash")))
        fig.add_hline(y=0, line=dict(color=COR_NEUTRA))
        fig.add_vline(x=S, line=dict(color=COR_SPOT, dash="dot"), annotation_text="spot", annotation_position="top")
        for b in res["breakevens"]:
            fig.add_vline(x=b, line=dict(color=COR_NEUTRA, dash="dot"))
        fig.add_trace(go.Scatter(x=ST, y=np.where(pnl_venc >= 0, pnl_venc, 0), fill="tozeroy", mode="none", fillcolor="rgba(78,214,160,0.15)", showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=ST, y=np.where(pnl_venc < 0, pnl_venc, 0), fill="tozeroy", mode="none", fillcolor="rgba(255,122,122,0.15)", showlegend=False, hoverinfo="skip"))
        fig.update_layout(title=f"Resultado por lote de {int(lote)} ({ticker}, vencimento {date.fromisoformat(venc_p):%d/%m/%Y})",
                          xaxis_title="Preço do ativo no vencimento", yaxis_title="Lucro / prejuízo (R$)")
        st.plotly_chart(layout_plotly(fig, 460), width="stretch")

        st.markdown("##### Gregas da posição (por lote)")
        g1, g2, g3, g4, g5 = st.columns(5)
        g1.metric("Delta", fmt_num(gp["delta"], 1), help="Equivalente em ações: quanto a posição ganha por R$ 1 de alta do ativo.")
        g2.metric("Gamma", fmt_num(gp["gamma"], 2), help=dica("Gamma"))
        g3.metric("Theta / dia", fmt_brl(gp["theta"] / base), help="Quanto a posição ganha (+) ou perde (−) por dia só pela passagem do tempo.")
        g4.metric("Vega / ponto", fmt_brl(gp["vega"] / 100), help="Resultado por +1 ponto de IV em todas as pernas.")
        g5.metric("Rho / ponto", fmt_brl(gp["rho"] / 100), help=dica("Rho"))

# =========================================================================== #
# 4. Superfície de volatilidade
# =========================================================================== #
with tab_surf:
    st.caption(dica("Superfície de volatilidade"))
    padrao_surf = [v for v in vencs if dias_ate(v) >= 7][:6] or vencs[:6]
    sel = st.multiselect("Vencimentos", vencs, default=padrao_surf, format_func=rotulo_venc, key="vencs_surf",
                         help="Cada vencimento é uma chamada à brapi (cache de 15 min). Vencimentos com menos de 7 dias têm IV muito ruidosa.")
    f1, f2, f3 = st.columns([1, 1, 1.2])
    eixo = f1.radio("Eixo de strike", ["Moneyness (K/S)", "Strike (R$)"], horizontal=True, key="eixo_surf")
    faixa_m = f2.slider("Faixa de moneyness (%)", 5, 50, 20, step=5, key="faixa_surf", help="Strikes entre S×(1−faixa) e S×(1+faixa). Muito fora do dinheiro a IV é pouco confiável.")
    so_alta = f3.toggle("Só séries com confiança alta", value=False, key="conf_surf", help="Mantém apenas IVs marcadas como 'high' pela brapi (preço de fechamento consistente). Reduz ruído, mas pode deixar buracos.")
    if not sel:
        st.info("Escolha ao menos um vencimento.")
    else:
        frames = []
        barra = st.progress(0.0, text="Carregando IV por vencimento…")
        for i, v in enumerate(sel):
            d_, e_ = carregar(q_analytics, ticker, v)
            if d_ is not None and not d_[0].empty:
                a = d_[0].copy()
                a["venc"] = v
                a["dias"] = dias_ate(v)
                frames.append(a)
            barra.progress((i + 1) / len(sel))
        barra.empty()
        if not frames:
            st.warning("Sem dados de IV para os vencimentos escolhidos.")
        else:
            surf = pd.concat(frames, ignore_index=True)
            surf = surf[surf["impliedVolatility"].notna() & (surf["impliedVolatility"] > 0) & (surf["impliedVolatility"] <= 2.0)]
            surf = surf[(surf["strike"] >= S * (1 - faixa_m / 100)) & (surf["strike"] <= S * (1 + faixa_m / 100))]
            surf = surf[surf["delta"].isna() | (surf["delta"].abs().between(0.02, 0.98))]
            if so_alta:
                surf = surf[surf["confidence"] == "high"]
            # usa OTM de cada lado para o sorriso "limpo" (puts abaixo do spot, calls acima)
            surf["otm"] = ((surf["side"] == "put") & (surf["strike"] <= S)) | ((surf["side"] == "call") & (surf["strike"] > S))
            surf["moneyness"] = surf["strike"] / S
            otm = surf[surf["otm"]].sort_values(["dias", "strike"])

            # estrutura a termo ATM e vol realizada
            atm_rows = []
            for v, grp in surf.groupby("venc"):
                iv_ = iv_atm_robusta(grp, S)
                if iv_:
                    atm_rows.append({"venc": v, "dias": int(grp["dias"].iloc[0]), "iv_atm": iv_})
            termo = pd.DataFrame(atm_rows, columns=["venc", "dias", "iv_atm"]).sort_values("dias")

            hist, erro_h = carregar(q_historico, ticker)
            rv = {}
            if hist is not None and not hist.empty:
                for jan in (10, 21, 63, 126, 252):
                    v_ = bs.vol_realizada(hist["close"].values, jan)
                    if v_:
                        rv[jan] = v_

            c1, c2, c3 = st.columns(3)
            iv1 = float(termo.iloc[0]["iv_atm"]) if not termo.empty else None
            c1.metric("IV ATM mais curta", fmt_num(iv1 * 100 if iv1 else None, 1, "%"), f"{termo.iloc[0]['dias']} dias" if not termo.empty else None, delta_color="off")
            c2.metric("Vol realizada 21 dias", fmt_num(rv.get(21, None) and rv[21] * 100, 1, "%"), help="Desvio-padrão anualizado (√252) dos últimos 21 retornos diários.")
            premio_vol = (iv1 - rv[21]) * 100 if iv1 and 21 in rv else None
            c3.metric("Prêmio de vol (IV − RV)", fmt_num(premio_vol, 1, " p.p."), help="Positivo: mercado paga mais vol do que o ativo entregou (favorece vender vol). Negativo: favorece comprar.")

            x_col = "moneyness" if eixo.startswith("Moneyness") else "strike"
            x_lab = "Moneyness K/S" if x_col == "moneyness" else "Strike (R$)"

            s1, s2 = st.columns([1.3, 1])
            with s1:
                # superfície interpolada numa grade comum
                xs = np.linspace(otm[x_col].min(), otm[x_col].max(), 60)
                ys, Z = [], []
                for v, grp in otm.groupby("venc"):
                    grp = grp.sort_values(x_col).drop_duplicates(x_col)
                    if len(grp) < 3:
                        continue
                    iv_suave = grp["impliedVolatility"].rolling(3, center=True, min_periods=1).median().values * 100
                    z = np.interp(xs, grp[x_col].values, iv_suave, left=np.nan, right=np.nan)
                    ys.append(int(grp["dias"].iloc[0]))
                    Z.append(z)
                if len(ys) >= 2:
                    ordem = np.argsort(ys)
                    fig = go.Figure(go.Surface(x=xs, y=np.array(ys)[ordem], z=np.array(Z)[ordem], colorscale="Viridis", colorbar=dict(title="IV %"),
                                               hovertemplate=x_lab + " %{x:.3f}<br>Dias %{y}<br>IV %{z:.1f}%<extra></extra>"))
                    fig.update_layout(title="Superfície de volatilidade implícita (OTM, mediana móvel de 3 strikes)", scene=dict(xaxis_title=x_lab, yaxis_title="Dias até o vencimento", zaxis_title="IV (%)"),
                                      template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", height=520, margin=dict(l=0, r=0, t=50, b=0))
                    st.plotly_chart(fig, width="stretch", config={"scrollZoom": False})
                else:
                    st.info("Escolha pelo menos dois vencimentos com séries suficientes para desenhar a superfície.")
            with s2:
                fig = go.Figure()
                for v, grp in otm.groupby("venc"):
                    grp = grp.sort_values(x_col)
                    fig.add_trace(go.Scatter(x=grp[x_col], y=grp["impliedVolatility"] * 100, mode="lines+markers", name=f"{date.fromisoformat(v):%d/%m} ({int(grp['dias'].iloc[0])}d)"))
                fig.add_vline(x=1.0 if x_col == "moneyness" else S, line=dict(color=COR_SPOT, dash="dot"))
                fig.update_layout(title="Sorrisos por vencimento", xaxis_title=x_lab, yaxis_title="IV (%)")
                st.plotly_chart(layout_plotly(fig, 520), width="stretch")

            t1, t2 = st.columns(2)
            with t1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=termo["dias"], y=termo["iv_atm"] * 100, mode="lines+markers", name="IV ATM", line=dict(color=COR_VENC)))
                for jan, v_ in sorted(rv.items()):
                    fig.add_trace(go.Scatter(x=[jan], y=[v_ * 100], mode="markers", name=f"RV {jan}d", marker=dict(size=10, symbol="diamond")))
                fig.update_layout(title="Estrutura a termo: IV ATM vs vol realizada", xaxis_title="Dias (prazo da IV / janela da RV)", yaxis_title="Vol (% a.a.)")
                st.plotly_chart(layout_plotly(fig, 380), width="stretch")
                st.caption("Curva ascendente = contango (normal). Curva invertida = estresse ou evento próximo.")
            with t2:
                if hist is not None and not hist.empty and len(hist) > 30:
                    h = hist.copy()
                    h["ret"] = np.log(h["close"]).diff()
                    h["rv21"] = h["ret"].rolling(21).std() * math.sqrt(252) * 100
                    h["rv63"] = h["ret"].rolling(63).std() * math.sqrt(252) * 100
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=h["date"], y=h["rv21"], name="RV 21d", line=dict(color=COR_T0)))
                    fig.add_trace(go.Scatter(x=h["date"], y=h["rv63"], name="RV 63d", line=dict(color=COR_CALL)))
                    if iv1:
                        fig.add_hline(y=iv1 * 100, line=dict(color=COR_VENC, dash="dash"), annotation_text="IV ATM atual")
                    fig.update_layout(title="Vol realizada no último ano", xaxis_title="", yaxis_title="Vol (% a.a.)")
                    st.plotly_chart(layout_plotly(fig, 380), width="stretch")
                elif erro_h:
                    st.warning(erro_h)

            with st.expander("Tabela da superfície (IV %, OTM, por strike × vencimento)"):
                piv = otm.pivot_table(index="strike", columns="venc", values="impliedVolatility", aggfunc="mean") * 100
                piv.columns = [f"{date.fromisoformat(c):%d/%m/%y}" for c in piv.columns]
                st.dataframe(piv.round(1), width="stretch")

# =========================================================================== #
# 5. Conceitos
# =========================================================================== #
with tab_conceitos:
    st.markdown("Os mesmos textos aparecem como dicas (ⓘ) nos campos e colunas do painel.")
    for nome, c in CONCEITOS.items():
        with st.expander(f"**{nome}** — {c['curto']}"):
            st.latex(c["formula"])
            st.markdown(c["longo"])
    st.caption("Notação: S preço do ativo, K strike, T prazo em anos, r taxa livre de risco, q dividend yield, σ volatilidade, N(·) normal acumulada, n(·) densidade normal.")
