# Painel de Opções

App Streamlit para operar opções da B3 com dados da [brapi](https://brapi.dev):
cotação do ativo, cadeia com IV e gregas, calculadora Black & Scholes, payoff de
estratégias, superfície de volatilidade e glossário com os conceitos (os mesmos
textos aparecem como dicas ⓘ nos campos e colunas).

## Rodar

```bash
pip install -r requirements.txt
copy .env.example .env      # e preencha BRAPI_API_KEY (https://brapi.dev/dashboard)
streamlit run app.py
```

Sem chave só funcionam PETR4, VALE3, ITUB4 e MGLU3 (sandbox da brapi).

## Login

O painel pede usuário e senha (streamlit-authenticator, mesmo esquema do
painel de setores). Localmente as credenciais ficam em `credenciais.yaml`
(fora do git); crie o primeiro usuário com `python gerar_usuario.py`.

## Publicação (Streamlit Community Cloud)

Repositório `josetmag/painel-opcoes`, público (o Community Cloud só permite um
app privado por conta). Nada sensível vai no código: em Settings > Secrets do
app cole o bloco de `python gerar_usuario.py --secrets` mais a linha
`BRAPI_API_KEY = "..."` (modelo em `secrets_streamlit.toml.example`).

## Abas

| Aba | O que mostra |
| --- | --- |
| Cadeia e gregas | Séries do vencimento com moneyness, último/bid/ask, OI, IV e gregas recalculadas com o preço atual; sorriso de IV, OI por strike, posições coberto/descoberto/bloqueado |
| Calculadora B&S | Prêmio, gregas, P(exercício), solver de IV a partir do preço de mercado; prêmio × preço do ativo, gregas × preço, decaimento com o tempo |
| Payoff de estratégias | 14 estratégias pré-montadas (travas, straddle, strangle, borboleta, condor, collar, venda coberta…) com pernas editáveis, prêmios da cadeia, curva no vencimento e T+0, breakevens, ganho/perda máximos, probabilidade de lucro e gregas da posição |
| Superfície de vol | Superfície 3D (moneyness × prazo × IV), sorrisos por vencimento, estrutura a termo da IV ATM vs vol realizada (10/21/63/126/252 dias) e prêmio de vol |
| Conceitos | Moneyness, Black & Scholes, IV, delta, gamma, theta, vega, rho, paridade put-call, superfície, OI, com fórmulas |

## Convenções

- Cotação do ativo: até 5 min de atraso (plano Pro). Opções, IV, gregas e OI: fechamento do pregão anterior.
- Gregas "ao vivo" = Black & Scholes-Merton com o spot atual e a IV do fechamento (sem dividendos, salvo o `q` da sidebar).
- Tempo: dias corridos/365 por padrão (igual à brapi) ou dias úteis/252.
- Theta mostrado por dia; vega e rho por ponto percentual.
- IV ATM = mediana das séries com |delta| entre 0,35 e 0,65 (robusta a séries ilíquidas).

## Arquivos

- `app.py` interface · `bs.py` modelo e gregas · `estrategias.py` presets e payoff ·
  `brapi_opcoes.py` cliente da API · `conceitos.py` glossário.
- `bs.py` reproduz as gregas publicadas pela brapi (conferido com PETRK516/PETRW516 em 26/10/2026).
