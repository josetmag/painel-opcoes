"""Cliente brapi para o painel de opções (server-side, chave em BRAPI_API_KEY).

Endpoints usados (todos /api/v2):
  stocks/quote            cotação do ativo-objeto (atualiza a cada ~5 min no plano Pro)
  stocks/historical       fechamentos diários (vol realizada)
  options/expirations     vencimentos com negócios
  options/chain           séries negociadas: último, bid/ask, volume, OI (fechamento)
  options/analytics       IV + gregas (BSM / CRR) calculadas no fechamento
  options/positions       contratos em aberto (coberto / descoberto / bloqueado)
  macro/latest            Selic (taxa livre de risco)

Erros: 401 -> BrapiAuthError, 404 -> BrapiNotFoundError, 429 -> espera Retry-After
e repete; demais -> BrapiError. Campos null viram None/NaN.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests

BASE_URL = "https://brapi.dev/api/v2"
ENV_VAR = "BRAPI_API_KEY"
TIMEOUT = 20
SANDBOX = ("PETR4", "VALE3", "ITUB4", "MGLU3")
AQUI = Path(__file__).resolve().parent


class BrapiError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, code: Optional[str] = None):
        super().__init__(message)
        self.status, self.code = status, code

    def __str__(self) -> str:
        prefix = " ".join(str(x) for x in (self.status, self.code) if x)
        return f"[{prefix}] {self.args[0]}" if prefix else str(self.args[0])


class BrapiAuthError(BrapiError):
    pass


class BrapiNotFoundError(BrapiError):
    pass


class BrapiRateLimitError(BrapiError):
    def __init__(self, message: str, retry_after: float, **kw: Any):
        super().__init__(message, **kw)
        self.retry_after = retry_after


def api_key() -> Optional[str]:
    """BRAPI_API_KEY do ambiente, do .env ao lado deste arquivo ou do st.secrets."""
    key = os.getenv(ENV_VAR)
    if not key:
        try:
            from dotenv import load_dotenv

            load_dotenv(AQUI / ".env", override=False)
            key = os.getenv(ENV_VAR)
        except ImportError:
            pass
    if not key:
        try:
            import streamlit as st

            key = st.secrets.get(ENV_VAR)  # type: ignore[attr-defined]
        except Exception:
            key = None
    key = (key or "").strip().strip('"').strip("'")
    return key or None


def _retry_after(headers) -> float:
    raw = headers.get("Retry-After")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 30.0


def get(path: str, params: dict | None = None, *, max_retries: int = 3, max_wait: float = 90.0) -> dict:
    """GET autenticado em BASE_URL + path com tratamento de 401/404/429/5xx."""
    headers = {"Accept": "application/json", "User-Agent": "painel-opcoes/1.0"}
    key = api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    url = f"{BASE_URL}/{path.lstrip('/')}"
    tentativa = 0
    while True:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        except requests.RequestException:
            if tentativa >= max_retries:
                raise
            tentativa += 1
            time.sleep(min(max_wait, 2**tentativa + random.random()))
            continue

        if r.status_code == 200:
            body = r.json()
            if isinstance(body, dict) and body.get("error"):
                raise BrapiError(str(body.get("message")), 200, body.get("code"))
            return body

        try:
            body = r.json()
        except ValueError:
            body = {}
        msg = str(body.get("message") or f"HTTP {r.status_code}")
        code = body.get("code")

        if r.status_code == 401:
            dica = (
                f" Defina {ENV_VAR} (arquivo .env ou Secrets do Streamlit). Sem chave só funcionam {', '.join(SANDBOX)}."
                if not key
                else f" Confira a chave {ENV_VAR} em https://brapi.dev/dashboard."
            )
            raise BrapiAuthError(msg + dica, 401, code)
        if r.status_code == 403:
            raise BrapiError(msg + " O plano não cobre este dado (https://brapi.dev/pricing).", 403, code)
        if r.status_code == 404:
            raise BrapiNotFoundError(msg, 404, code)
        if r.status_code == 429:
            espera = _retry_after(r.headers)
            if tentativa >= max_retries or espera > max_wait:
                raise BrapiRateLimitError(f"{msg} Tente em {espera:.0f}s.", espera, status=429, code=code)
            tentativa += 1
            time.sleep(espera)
            continue
        if r.status_code >= 500:
            if tentativa >= max_retries:
                raise BrapiError(msg, r.status_code, code)
            tentativa += 1
            time.sleep(min(max_wait, 2**tentativa + random.random()))
            continue
        raise BrapiError(msg, r.status_code, code)


# --------------------------------------------------------------------------- #
# Funções de dados (devolvem dict/DataFrame prontos para o app)
# --------------------------------------------------------------------------- #
def cotacao(symbol: str) -> dict:
    """Cotação do ativo-objeto: preço, variação, hora de referência (UTC ISO)."""
    body = get("stocks/quote", {"symbols": symbol.upper()})
    results = body.get("results") or []
    if not results:
        raise BrapiNotFoundError(f"Sem cotação para {symbol}.", 404)
    item = results[0]
    d = item.get("data") or {}
    return {
        "symbol": item.get("symbol") or symbol.upper(),
        "nome": d.get("longName") or d.get("shortName"),
        "preco": d.get("regularMarketPrice"),
        "variacao": d.get("regularMarketChange"),
        "variacao_pct": d.get("regularMarketChangePercent"),
        "fechamento_anterior": d.get("regularMarketPreviousClose"),
        "abertura": d.get("regularMarketOpen"),
        "maxima": d.get("regularMarketDayHigh"),
        "minima": d.get("regularMarketDayLow"),
        "volume": d.get("regularMarketVolume"),
        "market_cap": d.get("marketCap"),
        "min_52s": d.get("fiftyTwoWeekLow"),
        "max_52s": d.get("fiftyTwoWeekHigh"),
        "hora": d.get("regularMarketTime"),
        "requested_at": body.get("requestedAt"),
    }


def historico(symbol: str, range_: str = "1y") -> pd.DataFrame:
    """Fechamentos diários (colunas: date, close)."""
    body = get("stocks/historical", {"symbols": symbol.upper(), "range": range_, "interval": "1d"})
    results = body.get("results") or []
    if not results:
        return pd.DataFrame(columns=["date", "close"])
    serie = results[0].get("data")
    if isinstance(serie, dict):
        serie = serie.get("historicalDataPrice") or serie.get("history") or serie.get("prices") or []
    df = pd.DataFrame(serie or [])
    if df.empty:
        return pd.DataFrame(columns=["date", "close"])
    if "date" in df.columns:
        if pd.api.types.is_numeric_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"], unit="s", utc=True).dt.tz_convert("America/Sao_Paulo").dt.date
        else:
            df["date"] = pd.to_datetime(df["date"]).dt.date
    cols = [c for c in ("date", "open", "high", "low", "close", "volume", "adjustedClose") if c in df.columns]
    return df[cols].dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def vencimentos(underlying: str) -> list[str]:
    body = get("options/expirations", {"underlying": underlying.upper()})
    return list(body.get("expirations") or [])


_COLS_CADEIA = [
    "symbol", "side", "optionStyle", "strike", "close", "bid", "ask", "open", "high", "low",
    "trades", "volume", "financialVolume", "openInterest", "openInterestChange", "lastTradeDate",
]


def cadeia(underlying: str, vencimento: str) -> tuple[pd.DataFrame, Optional[str]]:
    """Séries negociadas de um vencimento. Retorna (DataFrame, data do fechamento)."""
    body = get("options/chain", {"underlying": underlying.upper(), "expirationDate": vencimento})
    df = pd.DataFrame(body.get("series") or [])
    if df.empty:
        return df, body.get("date")
    for c in _COLS_CADEIA:
        if c not in df.columns:
            df[c] = pd.NA
    return df[_COLS_CADEIA].sort_values(["strike", "side"]).reset_index(drop=True), body.get("date")


_COLS_ANALYTICS = [
    "symbol", "side", "optionStyle", "strike", "model", "underlyingPrice", "optionPrice", "riskFreeRate",
    "dividendYield", "timeToExpirationYears", "impliedVolatility", "delta", "gamma", "theta", "vega", "rho",
    "confidence", "nullReason", "openInterest",
]


def analytics(underlying: str, vencimento: str) -> tuple[pd.DataFrame, Optional[str]]:
    """IV e gregas do fechamento para um vencimento. Retorna (DataFrame, data)."""
    body = get(
        "options/analytics",
        {"underlying": underlying.upper(), "expirationDate": vencimento, "limit": 500},
    )
    df = pd.DataFrame(body.get("analytics") or [])
    if df.empty:
        return df, body.get("date")
    for c in _COLS_ANALYTICS:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[_COLS_ANALYTICS].copy()
    for c in ("impliedVolatility", "delta", "gamma", "theta", "vega", "rho", "underlyingPrice", "optionPrice"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["strike", "side"]).reset_index(drop=True), body.get("date")


def posicoes(underlying: str, vencimento: str) -> tuple[pd.DataFrame, Optional[str]]:
    """Contratos em aberto por série (coberto / descoberto / bloqueado)."""
    body = get("options/positions", {"underlying": underlying.upper(), "expirationDate": vencimento})
    df = pd.DataFrame(body.get("positions") or [])
    cols = ["symbol", "side", "strike", "openInterest", "coveredQuantity", "uncoveredQuantity", "blockedQuantity", "openInterestChange"]
    if df.empty:
        return pd.DataFrame(columns=cols), body.get("date")
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df[cols].sort_values(["strike", "side"]).reset_index(drop=True), body.get("date")


def selic() -> Optional[float]:
    """Selic mais recente em fração a.a. (0.1375). None se indisponível."""
    try:
        body = get("macro/latest", {"symbols": "selic"})
    except BrapiError:
        return None
    for item in body.get("results") or []:
        latest = item.get("latest") or {}
        if latest.get("value") is not None:
            return float(latest["value"]) / 100.0
    return None
