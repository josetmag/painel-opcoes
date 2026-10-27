"""Black-Scholes-Merton: preço, gregas, volatilidade implícita e moneyness.

Sem dependência de scipy: a normal acumulada usa math.erf vetorizado.
Convenções (iguais às da brapi):
  - T em anos; o app converte dias corridos/365 ou dias úteis/252.
  - sigma em fração (0.35 = 35% a.a.), r e q em fração a.a. contínua.
  - theta anual (o app divide por 365 ou 252 para "por dia").
  - vega por 1,00 de vol (o app divide por 100 para "por ponto").
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

Tipo = Literal["call", "put"]

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)


def _ncdf_scalar(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


_ncdf_vec = np.vectorize(_ncdf_scalar, otypes=[float])


def N(x):
    """Normal padrão acumulada (aceita escalar ou array)."""
    if np.isscalar(x):
        return _ncdf_scalar(float(x))
    return _ncdf_vec(np.asarray(x, dtype=float))


def n(x):
    """Densidade da normal padrão."""
    x = np.asarray(x, dtype=float)
    return np.exp(-0.5 * x * x) / _SQRT2PI


@dataclass(frozen=True)
class Gregas:
    preco: float
    delta: float
    gamma: float
    vega: float  # por 1,00 de vol (100 pontos)
    theta: float  # anual
    rho: float  # por 1,00 de taxa
    d1: float
    d2: float
    prob_exercicio: float  # N(d2) para call, N(-d2) para put (medida neutra ao risco)


def _d1d2(S, K, T, r, sigma, q):
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    T = np.maximum(np.asarray(T, dtype=float), 1e-10)
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-10)
    sq = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / sq
    d2 = d1 - sq
    return S, K, T, sigma, d1, d2


def preco(tipo: Tipo, S, K, T, r, sigma, q=0.0):
    """Prêmio teórico BSM. Vetorizado em qualquer argumento."""
    S, K, T, sigma, d1, d2 = _d1d2(S, K, T, r, sigma, q)
    dq, dr = np.exp(-q * T), np.exp(-r * T)
    if tipo == "call":
        v = S * dq * N(d1) - K * dr * N(d2)
    else:
        v = K * dr * N(-d2) - S * dq * N(-d1)
    return v


def valor_intrinseco(tipo: Tipo, S, K):
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    return np.maximum(S - K, 0.0) if tipo == "call" else np.maximum(K - S, 0.0)


def gregas(tipo: Tipo, S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> Gregas:
    """Preço e gregas para um único contrato (escalares)."""
    if T <= 0:
        intr = float(valor_intrinseco(tipo, S, K))
        itm = (S > K) if tipo == "call" else (S < K)
        delta = (1.0 if itm else 0.0) * (1 if tipo == "call" else -1)
        return Gregas(intr, delta, 0.0, 0.0, 0.0, 0.0, float("nan"), float("nan"), 1.0 if itm else 0.0)

    S_, K_, T_, sig, d1, d2 = _d1d2(S, K, T, r, sigma, q)
    d1, d2, T_, sig = float(d1), float(d2), float(T_), float(sig)
    dq, dr = math.exp(-q * T_), math.exp(-r * T_)
    nd1 = float(n(d1))
    sqT = math.sqrt(T_)

    gamma = dq * nd1 / (S * sig * sqT)
    vega = S * dq * nd1 * sqT
    termo_comum = -S * dq * nd1 * sig / (2 * sqT)

    if tipo == "call":
        p = S * dq * N(d1) - K * dr * N(d2)
        delta = dq * N(d1)
        theta = termo_comum - r * K * dr * N(d2) + q * S * dq * N(d1)
        rho = K * T_ * dr * N(d2)
        prob = N(d2)
    else:
        p = K * dr * N(-d2) - S * dq * N(-d1)
        delta = dq * (N(d1) - 1.0)
        theta = termo_comum + r * K * dr * N(-d2) - q * S * dq * N(-d1)
        rho = -K * T_ * dr * N(-d2)
        prob = N(-d2)

    return Gregas(float(p), float(delta), float(gamma), float(vega), float(theta), float(rho), d1, d2, float(prob))


def vol_implicita(
    tipo: Tipo, preco_mercado: float, S: float, K: float, T: float, r: float, q: float = 0.0,
    lo: float = 1e-4, hi: float = 5.0, tol: float = 1e-7, max_iter: int = 200,
) -> float | None:
    """Vol implícita por bissecção. None quando o preço está fora dos limites de arbitragem."""
    if T <= 0 or preco_mercado is None or preco_mercado <= 0:
        return None
    # limites de não-arbitragem (com desconto)
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    if tipo == "call":
        piso, teto = max(S * dq - K * dr, 0.0), S * dq
    else:
        piso, teto = max(K * dr - S * dq, 0.0), K * dr
    if preco_mercado <= piso + 1e-12 or preco_mercado >= teto - 1e-12:
        return None
    f_lo = float(preco(tipo, S, K, T, r, lo, q)) - preco_mercado
    f_hi = float(preco(tipo, S, K, T, r, hi, q)) - preco_mercado
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = float(preco(tipo, S, K, T, r, mid, q)) - preco_mercado
        if abs(f_mid) < tol or (hi - lo) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------- #
# Moneyness e utilidades de mercado
# --------------------------------------------------------------------------- #
def moneyness(tipo: Tipo, S: float, K: float) -> float:
    """S/K para call e K/S para put: >1 = dentro do dinheiro (ITM)."""
    return S / K if tipo == "call" else K / S


def classifica_moneyness(tipo: Tipo, S: float, K: float, faixa_atm: float = 0.02) -> str:
    """ITM / ATM / OTM. ATM quando |S/K - 1| <= faixa_atm (2% por padrão)."""
    if abs(S / K - 1.0) <= faixa_atm:
        return "ATM"
    itm = S > K if tipo == "call" else S < K
    return "ITM" if itm else "OTM"


def log_moneyness(S: float, K: float) -> float:
    """ln(K/S): 0 no dinheiro, >0 strike acima do spot."""
    return math.log(K / S)


def anos(dias: float, base: int = 365) -> float:
    """Converte dias em anos (base 365 = corridos, 252 = úteis)."""
    return max(dias, 0.0) / base


def dias_uteis(inicio, fim) -> int:
    """Dias úteis entre duas datas (seg-sex, sem feriados)."""
    return int(np.busday_count(np.datetime64(inicio), np.datetime64(fim)))


def movimento_esperado(S: float, sigma: float, T: float, desvios: float = 1.0) -> float:
    """Movimento esperado (em R$) até T: S * sigma * sqrt(T) * desvios (~68% para 1 desvio)."""
    return S * sigma * math.sqrt(max(T, 0.0)) * desvios


def prob_lognormal_acima(S: float, nivel: float, sigma: float, T: float, mu: float = 0.0) -> float:
    """P(S_T > nivel) sob lognormal com deriva mu (0 = sem deriva) e vol sigma."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > nivel else 0.0
    d = (math.log(S / nivel) + (mu - 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return float(N(d))


def densidade_lognormal(ST, S: float, sigma: float, T: float, mu: float = 0.0):
    """Densidade de S_T (lognormal) numa grade de preços, para probabilidade de lucro."""
    ST = np.asarray(ST, dtype=float)
    if T <= 0 or sigma <= 0:
        return np.zeros_like(ST)
    sq = sigma * math.sqrt(T)
    z = (np.log(ST / S) - (mu - 0.5 * sigma**2) * T) / sq
    return np.exp(-0.5 * z * z) / (ST * sq * _SQRT2PI)


def vol_realizada(precos, janela: int = 21, base: int = 252) -> float | None:
    """Vol realizada anualizada dos últimos `janela` retornos log."""
    p = np.asarray(precos, dtype=float)
    p = p[np.isfinite(p) & (p > 0)]
    if len(p) < janela + 1:
        return None
    ret = np.diff(np.log(p[-(janela + 1):]))
    return float(np.std(ret, ddof=1) * math.sqrt(base))
