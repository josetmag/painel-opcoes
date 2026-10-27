"""
Cria ou atualiza usuarios do dashboard.

    python gerar_usuario.py                  # modo interativo (pergunta tudo)
    python gerar_usuario.py --listar         # mostra quem tem acesso
    python gerar_usuario.py --remover jose   # tira o acesso
    python gerar_usuario.py --secrets        # imprime o bloco p/ Streamlit Cloud

A senha nunca e gravada em texto: fica so o hash bcrypt, em `credenciais.yaml`
(que esta no .gitignore e nao vai para o GitHub).
"""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

import bcrypt
import yaml

RAIZ = Path(__file__).resolve().parent
ARQ = RAIZ / "credenciais.yaml"


def carregar() -> dict:
    if ARQ.exists():
        with open(ARQ, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def salvar(cfg: dict) -> None:
    cfg.setdefault("cookie", {})
    # Chave que assina o cookie de sessao; gerada uma vez e reaproveitada.
    if not cfg["cookie"].get("key"):
        cfg["cookie"]["key"] = secrets.token_urlsafe(32)
    cfg["cookie"].setdefault("expiry_days", 7)
    with open(ARQ, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    print(f"-> {ARQ}")


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


VAR_SENHA = "DASH_SENHA"

AJUDA_SEM_TERMINAL = f"""
Este comando precisa de um terminal de verdade para pedir a senha sem
mostrá-la na tela, e a entrada atual não é interativa.

Duas saídas:

1. Abra o PowerShell em {RAIZ} e rode `python gerar_usuario.py` lá.

2. Ou passe os dados sem prompt, com a senha numa variável de ambiente:

     $env:{VAR_SENHA} = "sua-senha-aqui"
     python gerar_usuario.py --login jose --nome "José"
     Remove-Item Env:\\{VAR_SENHA}

   Cuidado: nesse modo a senha aparece no histórico do terminal.
"""


def _perguntar(rotulo: str, padrao: str = "") -> str:
    try:
        return input(rotulo).strip()
    except EOFError:
        sys.exit(AJUDA_SEM_TERMINAL)


def _obter_senha() -> str:
    """Le a senha da variavel de ambiente ou, se houver terminal, do prompt."""
    do_ambiente = os.environ.get(VAR_SENHA)
    if do_ambiente:
        return do_ambiente
    try:
        senha = getpass.getpass("Senha: ")
        repetida = getpass.getpass("Repita a senha: ")
    except (EOFError, getpass.GetPassWarning):
        sys.exit(AJUDA_SEM_TERMINAL)
    if senha != repetida:
        sys.exit("As senhas não conferem.")
    return senha


def cmd_adicionar(login: str = "", nome: str = "", email: str = "") -> None:
    cfg = carregar()
    usuarios = cfg.setdefault("credentials", {}).setdefault("usernames", {})

    login = login or _perguntar("Usuário (login): ")
    if not login:
        sys.exit("Login vazio.")
    if login in usuarios and not os.environ.get(VAR_SENHA):
        if _perguntar(f"'{login}' já existe. Sobrescrever? [s/N] ").lower() != "s":
            sys.exit("Cancelado.")

    nome = nome or _perguntar("Nome de exibição: ") or login
    email = email or _perguntar("E-mail (opcional): ")

    senha = _obter_senha()
    if len(senha) < 8:
        sys.exit("Senha muito curta (mínimo 8 caracteres).")

    usuarios[login] = {
        "name": nome,
        "email": email or f"{login}@local",
        "password": hash_senha(senha),
    }
    salvar(cfg)
    print(f"Usuário '{login}' pronto. Total: {len(usuarios)}.")


def cmd_listar() -> None:
    usuarios = carregar().get("credentials", {}).get("usernames", {})
    if not usuarios:
        print("Nenhum usuário cadastrado.")
        return
    print(f"{len(usuarios)} usuário(s) com acesso:")
    for login, d in usuarios.items():
        print(f"  - {login:<15} {d.get('name','')} <{d.get('email','')}>")


def cmd_remover(login: str) -> None:
    cfg = carregar()
    usuarios = cfg.get("credentials", {}).get("usernames", {})
    if login not in usuarios:
        sys.exit(f"'{login}' não existe.")
    del usuarios[login]
    salvar(cfg)
    print(f"Usuário '{login}' removido.")


def cmd_nova_chave() -> None:
    """Troca a chave que assina o cookie de sessao (invalida os logins ativos)."""
    cfg = carregar()
    cfg.setdefault("cookie", {})["key"] = secrets.token_urlsafe(32)
    salvar(cfg)
    print("Nova cookie.key gerada. Rode --secrets e atualize o Streamlit Cloud.")


def cmd_secrets() -> None:
    """Imprime o conteudo pronto para colar em Settings > Secrets."""
    cfg = carregar()
    usuarios = cfg.get("credentials", {}).get("usernames", {})
    if not usuarios:
        sys.exit("Nenhum usuário cadastrado ainda. Rode sem argumentos antes.")

    linhas = [
        "# Cole isto em Settings > Secrets do app no Streamlit Cloud",
        "",
        "[cookie]",
        f'key = "{cfg.get("cookie", {}).get("key", secrets.token_urlsafe(32))}"',
        f'expiry_days = {cfg.get("cookie", {}).get("expiry_days", 7)}',
        "",
    ]
    for login, d in usuarios.items():
        linhas += [
            f"[credentials.usernames.{login}]",
            f'name = "{d.get("name", login)}"',
            f'email = "{d.get("email", "")}"',
            f'password = "{d["password"]}"',
            "",
        ]
    print("\n".join(linhas))


def main() -> None:
    p = argparse.ArgumentParser(description="Usuários do painel de opções")
    p.add_argument("--listar", action="store_true", help="lista os usuários")
    p.add_argument("--remover", metavar="LOGIN", help="remove um usuário")
    p.add_argument("--secrets", action="store_true",
                   help="imprime o bloco TOML para o Streamlit Cloud")
    p.add_argument("--nova-chave-cookie", action="store_true",
                   help="sorteia uma cookie.key nova (desloga todo mundo)")
    p.add_argument("--login", default="", help="login, sem perguntar")
    p.add_argument("--nome", default="", help="nome de exibicao, sem perguntar")
    p.add_argument("--email", default="", help="e-mail, sem perguntar")
    a = p.parse_args()

    if a.listar:
        cmd_listar()
    elif a.remover:
        cmd_remover(a.remover)
    elif a.secrets:
        cmd_secrets()
    elif a.nova_chave_cookie:
        cmd_nova_chave()
    else:
        cmd_adicionar(a.login, a.nome, a.email)


if __name__ == "__main__":
    main()
