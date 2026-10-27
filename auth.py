"""
Autenticacao do dashboard (usuario + senha).

Usa streamlit-authenticator: os usuarios sao definidos por voce, ninguem se
cadastra sozinho. As senhas ficam sempre em hash bcrypt -- nunca em texto.

Onde ficam as credenciais, na ordem em que sao procuradas:

1. `st.secrets` -- usado no Streamlit Community Cloud. Voce cola o bloco na
   tela "Settings > Secrets" do app (nada disso vai para o GitHub).
2. `credenciais.yaml` na raiz do projeto -- usado quando roda na sua maquina.
   Esta no .gitignore.

Para criar/alterar usuarios: `python gerar_usuario.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
import streamlit_authenticator as stauth
import yaml

RAIZ = Path(__file__).resolve().parent
ARQ_CREDENCIAIS = RAIZ / "credenciais.yaml"

# Fallback do cookie de sessao. E sobrescrito pelo secret `cookie.key` no
# deploy -- e la que ele precisa ser secreto, porque assina o cookie.
COOKIE_NOME = "painel_opcoes"
COOKIE_KEY_PADRAO = "chave-local-trocar-no-deploy"
COOKIE_DIAS = 7


def _de_secrets() -> tuple[dict[str, Any] | None, str, int]:
    """Le credenciais de st.secrets. Retorna (credenciais, cookie_key, dias)."""
    try:
        if "credentials" not in st.secrets:
            return None, COOKIE_KEY_PADRAO, COOKIE_DIAS
        # st.secrets devolve objetos AttrDict; o authenticator precisa de dict
        # puro e mutavel (ele grava o hash de volta quando auto_hash roda).
        cred = _para_dict(st.secrets["credentials"])
        cookie = st.secrets.get("cookie", {})
        return (
            cred,
            cookie.get("key", COOKIE_KEY_PADRAO),
            int(cookie.get("expiry_days", COOKIE_DIAS)),
        )
    except Exception:
        # Sem arquivo de secrets configurado (comum ao rodar local).
        return None, COOKIE_KEY_PADRAO, COOKIE_DIAS


def _para_dict(obj: Any) -> Any:
    """Converte AttrDict/Mapping aninhado do st.secrets em dict comum."""
    if hasattr(obj, "items"):
        return {k: _para_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_para_dict(v) for v in obj]
    return obj


def _de_yaml() -> tuple[dict[str, Any] | None, str, int]:
    if not ARQ_CREDENCIAIS.exists():
        return None, COOKIE_KEY_PADRAO, COOKIE_DIAS
    with open(ARQ_CREDENCIAIS, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cookie = cfg.get("cookie", {}) or {}
    return (
        cfg.get("credentials"),
        cookie.get("key", COOKIE_KEY_PADRAO),
        int(cookie.get("expiry_days", COOKIE_DIAS)),
    )


def _carregar() -> tuple[dict[str, Any], str, int]:
    for origem in (_de_secrets, _de_yaml):
        cred, key, dias = origem()
        if cred and cred.get("usernames"):
            return cred, key, dias
    return {}, COOKIE_KEY_PADRAO, COOKIE_DIAS


def exigir_login() -> str:
    """Mostra a tela de login e interrompe a pagina se nao autenticado.

    Retorna o nome do usuario autenticado.
    """
    credenciais, cookie_key, cookie_dias = _carregar()

    if not credenciais:
        st.error("Nenhum usuário cadastrado.")
        st.markdown(
            "Rode `python gerar_usuario.py` para criar o primeiro acesso "
            "(local), ou preencha os *Secrets* do app no Streamlit Cloud."
        )
        st.stop()

    autenticador = stauth.Authenticate(
        credenciais, COOKIE_NOME, cookie_key, cookie_dias
    )
    # Guardado para o logout poder ser desenhado depois, na sidebar.
    st.session_state["_autenticador"] = autenticador

    try:
        # `fields` aceita dicionario parcial: a biblioteca testa cada rotulo com
        # `not in fields`, entao passar so o titulo preserva Username, Password
        # e o texto do botao.
        autenticador.login(
            location="main",
            fields={"Form name": "Login - Painel de Opções"},
        )
    except Exception as e:  # senha mal formada no secrets, hash invalido, etc.
        st.error(f"Falha na autenticação: {e}")
        st.stop()

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Usuário ou senha incorretos.")
        st.stop()
    if status is None:
        st.info("Entre com seu usuário e senha para ver o painel.")
        st.stop()

    return st.session_state.get("name") or st.session_state.get("username", "")


def botao_logout(local: str = "sidebar") -> None:
    autenticador = st.session_state.get("_autenticador")
    if autenticador is not None:
        autenticador.logout("Sair", location=local)
