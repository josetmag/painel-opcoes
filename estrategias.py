"""Estratégias com opções: pernas, payoff no vencimento e curva T+0 (BSM).

Uma perna é um dict:
  tipo: "call" | "put" | "acao"
  lado: +1 (compra) | -1 (venda)
  strike: float (ignorado para ação)
  premio: float (preço pago/recebido por unidade; para ação, o preço de compra)
  qtd: int (contratos/ações)
  vol: float (IV da perna, fração) - usada na curva T+0
"""

from __future__ import annotations

import math

import numpy as np

import bs

# Presets: offsets em % do spot para escolher strikes; o app casa com os strikes reais da cadeia.
PRESETS: dict[str, dict] = {
    "Call comprada": {
        "visao": "Alta forte", "pernas": [("call", +1, 0.00)],
        "resumo": "Lucro ilimitado se o ativo subir; perda limitada ao prêmio.",
    },
    "Put comprada": {
        "visao": "Queda forte", "pernas": [("put", +1, 0.00)],
        "resumo": "Lucro se o ativo cair; perda limitada ao prêmio.",
    },
    "Venda coberta (ação + call vendida)": {
        "visao": "Neutro / alta moderada", "pernas": [("acao", +1, 0.00), ("call", -1, +0.05)],
        "resumo": "Recebe prêmio em troca de limitar o ganho acima do strike.",
    },
    "Put protetora (ação + put comprada)": {
        "visao": "Alta com seguro", "pernas": [("acao", +1, 0.00), ("put", +1, -0.05)],
        "resumo": "Seguro contra queda; custa o prêmio da put.",
    },
    "Collar (ação + put comprada + call vendida)": {
        "visao": "Proteção barata", "pernas": [("acao", +1, 0.00), ("put", +1, -0.05), ("call", -1, +0.05)],
        "resumo": "A call vendida financia a put: ganho e perda ficam limitados.",
    },
    "Trava de alta com call (bull call spread)": {
        "visao": "Alta moderada", "pernas": [("call", +1, 0.00), ("call", -1, +0.05)],
        "resumo": "Compra call e vende call mais alta: custo menor, ganho limitado.",
    },
    "Trava de baixa com put (bear put spread)": {
        "visao": "Queda moderada", "pernas": [("put", +1, 0.00), ("put", -1, -0.05)],
        "resumo": "Compra put e vende put mais baixa: custo menor, ganho limitado.",
    },
    "Trava de alta com put (bull put spread, crédito)": {
        "visao": "Alta / lateral", "pernas": [("put", -1, 0.00), ("put", +1, -0.05)],
        "resumo": "Recebe crédito; ganha se o ativo ficar acima do strike vendido.",
    },
    "Trava de baixa com call (bear call spread, crédito)": {
        "visao": "Queda / lateral", "pernas": [("call", -1, 0.00), ("call", +1, +0.05)],
        "resumo": "Recebe crédito; ganha se o ativo ficar abaixo do strike vendido.",
    },
    "Straddle comprado": {
        "visao": "Movimento forte (qualquer direção)", "pernas": [("call", +1, 0.00), ("put", +1, 0.00)],
        "resumo": "Compra call e put no mesmo strike: aposta em volatilidade.",
    },
    "Strangle comprado": {
        "visao": "Movimento forte (mais barato que straddle)", "pernas": [("call", +1, +0.05), ("put", +1, -0.05)],
        "resumo": "Call e put fora do dinheiro: precisa de movimento maior para lucrar.",
    },
    "Straddle vendido": {
        "visao": "Lateral (vende vol)", "pernas": [("call", -1, 0.00), ("put", -1, 0.00)],
        "resumo": "Recebe dois prêmios; risco ilimitado se o ativo andar muito.",
    },
    "Borboleta de call": {
        "visao": "Lateral no strike central", "pernas": [("call", +1, -0.05), ("call", -2, 0.00), ("call", +1, +0.05)],
        "resumo": "Lucro máximo se o ativo terminar no strike do meio; risco limitado.",
    },
    "Condor de ferro (iron condor)": {
        "visao": "Lateral numa faixa", "pernas": [("put", +1, -0.10), ("put", -1, -0.05), ("call", -1, +0.05), ("call", +1, +0.10)],
        "resumo": "Vende strangle e compra asas: crédito com risco limitado.",
    },
}


def montar_pernas(preset: str, S: float, strikes: list[float] | None, premio_fn=None, vol_fn=None) -> list[dict]:
    """Cria as pernas de um preset casando offsets com strikes reais (ou S*(1+offset))."""
    pernas = []
    for tipo, lado, off in PRESETS[preset]["pernas"]:
        qtd = abs(lado)
        sinal = 1 if lado > 0 else -1
        if tipo == "acao":
            pernas.append({"tipo": "acao", "lado": sinal, "strike": 0.0, "premio": S, "qtd": qtd, "vol": 0.0})
            continue
        alvo = S * (1 + off)
        strike = min(strikes, key=lambda k: abs(k - alvo)) if strikes else round(alvo, 2)
        premio = premio_fn(tipo, strike) if premio_fn else None
        vol = vol_fn(tipo, strike) if vol_fn else None
        pernas.append({
            "tipo": tipo, "lado": sinal, "strike": float(strike),
            "premio": float(premio) if premio is not None and not (isinstance(premio, float) and math.isnan(premio)) else 0.0,
            "qtd": qtd, "vol": float(vol) if vol is not None and not (isinstance(vol, float) and math.isnan(vol)) else 0.0,
        })
    return pernas


def payoff_vencimento(pernas: list[dict], ST, lote: int = 1):
    """P&L por lote no vencimento numa grade de preços ST."""
    ST = np.asarray(ST, dtype=float)
    total = np.zeros_like(ST)
    for p in pernas:
        q = p["qtd"] * p["lado"] * lote
        if p["tipo"] == "acao":
            total += q * (ST - p["premio"])
        else:
            total += q * (bs.valor_intrinseco(p["tipo"], ST, p["strike"]) - p["premio"])
    return total


def valor_t0(pernas: list[dict], S_grid, T: float, r: float, q: float = 0.0, vol_padrao: float = 0.3, lote: int = 1):
    """P&L por lote hoje (T anos restantes), marcando cada perna pelo BSM."""
    S_grid = np.asarray(S_grid, dtype=float)
    total = np.zeros_like(S_grid)
    for p in pernas:
        qn = p["qtd"] * p["lado"] * lote
        if p["tipo"] == "acao":
            total += qn * (S_grid - p["premio"])
        else:
            vol = p.get("vol") or vol_padrao
            total += qn * (bs.preco(p["tipo"], S_grid, p["strike"], T, r, vol, q) - p["premio"])
    return total


def gregas_posicao(pernas: list[dict], S: float, T: float, r: float, q: float = 0.0, vol_padrao: float = 0.3, lote: int = 1) -> dict:
    """Soma das gregas das pernas (delta em unidades do ativo; theta anual; vega por 1,00 vol)."""
    tot = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}
    for p in pernas:
        qn = p["qtd"] * p["lado"] * lote
        if p["tipo"] == "acao":
            tot["delta"] += qn
            continue
        g = bs.gregas(p["tipo"], S, p["strike"], T, r, p.get("vol") or vol_padrao, q)
        for k in tot:
            tot[k] += qn * getattr(g, k)
    return tot


def custo_liquido(pernas: list[dict], lote: int = 1) -> float:
    """Desembolso (positivo = débito, negativo = crédito) por lote, sem a ação."""
    return float(sum(p["qtd"] * p["lado"] * p["premio"] * lote for p in pernas if p["tipo"] != "acao"))


def breakevens(ST, pnl, tol: float = 1e-9) -> list[float]:
    """Preços onde o P&L cruza zero. Trechos planos em zero contam só nas bordas."""
    ST = np.asarray(ST, dtype=float)
    pnl = np.asarray(pnl, dtype=float)
    sinal = np.where(pnl > tol, 1, np.where(pnl < -tol, -1, 0))
    pontos: list[float] = []
    ultimo = 0
    for i in range(len(ST)):
        s = sinal[i]
        if s == 0:
            continue
        if ultimo != 0 and s != ultimo:
            # cruzamento: interpola entre o último ponto não-nulo anterior e este
            j = i - 1
            while j > 0 and sinal[j] == 0:
                j -= 1
            a, b = pnl[j], pnl[i]
            x = ST[j] + (ST[i] - ST[j]) * (-a) / (b - a) if b != a else ST[i]
            pontos.append(round(float(x), 2))
        elif ultimo == 0 and i > 0 and sinal[i - 1] == 0 and not pontos and np.any(sinal[:i] == 0):
            # saiu de um platô em zero no início da grade
            pontos.append(round(float(ST[i - 1]), 2))
        ultimo = s
    return pontos


def resumo(pernas: list[dict], ST, pnl) -> dict:
    """Máximo ganho/perda na grade (inf quando o payoff continua crescendo na borda)."""
    pnl = np.asarray(pnl, dtype=float)
    ST = np.asarray(ST, dtype=float)
    incl_dir = pnl[-1] - pnl[-2]
    incl_esq = pnl[1] - pnl[0]
    sobe_na_borda = incl_dir > 1e-9 or incl_esq < -1e-9
    cai_na_borda = incl_dir < -1e-9 or incl_esq > 1e-9
    return {
        "ganho_max": math.inf if sobe_na_borda else float(pnl.max()),
        "perda_max": -math.inf if cai_na_borda else float(pnl.min()),
        "breakevens": breakevens(ST, pnl),
    }


def prob_lucro(ST, pnl, S: float, sigma: float, T: float, mu: float = 0.0) -> float:
    """Probabilidade (lognormal) de o P&L no vencimento ser positivo."""
    ST = np.asarray(ST, dtype=float)
    pnl = np.asarray(pnl, dtype=float)
    dens = bs.densidade_lognormal(ST, S, sigma, T, mu)
    massa = np.trapezoid(dens, ST) if hasattr(np, "trapezoid") else np.trapz(dens, ST)
    if massa <= 0:
        return float("nan")
    ganho = np.where(pnl > 0, dens, 0.0)
    p = (np.trapezoid(ganho, ST) if hasattr(np, "trapezoid") else np.trapz(ganho, ST)) / massa
    return float(min(max(p, 0.0), 1.0))
