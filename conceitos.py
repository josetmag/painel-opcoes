"""Glossário: texto curto (tooltip) e explicação longa com fórmula, em PT-BR."""

CONCEITOS: dict[str, dict] = {
    "Moneyness": {
        "curto": "Quão dentro ou fora do dinheiro a opção está: relação entre o preço do ativo (S) e o strike (K).",
        "formula": r"\text{Call: } \frac{S}{K} \qquad \text{Put: } \frac{K}{S} \qquad \text{log-moneyness} = \ln\frac{K}{S}",
        "longo": (
            "**ITM (in the money)** tem valor intrínseco: call com S > K, put com S < K. "
            "**ATM (at the money)** é S ≈ K, onde gamma, vega e theta são máximos. "
            "**OTM (out of the money)** não tem valor intrínseco; o prêmio é 100% valor do tempo.\n\n"
            "Na prática o mercado também mede moneyness pelo **delta**: uma call de delta 0,25 é 'OTM 25-delta'. "
            "Isso normaliza por volatilidade e prazo, o que o S/K puro não faz."
        ),
    },
    "Black & Scholes": {
        "curto": "Modelo que dá o preço justo de uma opção europeia a partir de S, K, prazo, taxa, dividendos e volatilidade.",
        "formula": (
            r"C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2) \qquad P = K e^{-rT} N(-d_2) - S e^{-qT} N(-d_1)"
            r"\\ d_1 = \frac{\ln(S/K) + (r - q + \sigma^2/2)\,T}{\sigma\sqrt{T}} \qquad d_2 = d_1 - \sigma\sqrt{T}"
        ),
        "longo": (
            "Premissas: preço do ativo lognormal com volatilidade constante, taxa constante, sem custos, exercício só no vencimento. "
            "**N(d2)** é a probabilidade (neutra ao risco) de a call terminar dentro do dinheiro; **N(d1)** é o delta da call.\n\n"
            "No Brasil as opções de ação da B3 podem ser americanas (calls, em geral) ou europeias. A brapi usa BSM para europeias e "
            "árvore binomial (Cox-Ross-Rubinstein) para americanas. Para calls sem dividendo no prazo, o preço americano é igual ao europeu.\n\n"
            "O que o modelo **não** captura: sorriso de volatilidade (vol diferente por strike), saltos, dividendos discretos e juros variáveis. "
            "Por isso o mercado cota em vol implícita e usa o modelo como 'tradutor' entre vol e preço."
        ),
    },
    "Volatilidade implícita": {
        "curto": "A vol que, colocada no Black & Scholes, reproduz o preço de mercado da opção. É o 'preço da incerteza'.",
        "formula": r"\sigma_{imp} : \; BS(S, K, T, r, \sigma_{imp}) = \text{preço de mercado}",
        "longo": (
            "Não se calcula de forma fechada; resolve-se numericamente (aqui por bissecção). "
            "Compare com a **vol realizada** (desvio-padrão anualizado dos retornos passados): se a implícita está bem acima da realizada, "
            "o mercado paga prêmio por proteção, o que favorece estratégias vendidas em vol; se está abaixo, favorece compradas.\n\n"
            "Regra rápida: movimento esperado de 1 desvio até o vencimento ≈ S × σ × √T. "
            "Com σ = 35% e 24 dias (T ≈ 0,066), PETR4 a R$ 54 'deveria' andar cerca de ±R$ 4,85 em 68% dos cenários."
        ),
    },
    "Delta": {
        "curto": "Quanto o prêmio muda para cada R$ 1 de variação do ativo. Também aproxima a probabilidade de exercício.",
        "formula": r"\Delta_{call} = e^{-qT} N(d_1) \in [0, 1] \qquad \Delta_{put} = e^{-qT}\,[N(d_1) - 1] \in [-1, 0]",
        "longo": (
            "Call ATM tem delta ≈ 0,50; muito ITM tende a 1 (anda igual à ação); muito OTM tende a 0.\n\n"
            "**Hedge**: uma posição de 100 calls com delta 0,40 equivale a 40 ações. Para ficar neutro, vende-se 40 ações. "
            "O delta muda com o preço (ver gamma), então o hedge precisa ser rebalanceado.\n\n"
            "**Delta como probabilidade**: é uma aproximação razoável de P(terminar ITM), um pouco acima de N(d2) para calls."
        ),
    },
    "Gamma": {
        "curto": "Quanto o delta muda para cada R$ 1 de variação do ativo. Mede a convexidade: máximo no ATM, perto do vencimento.",
        "formula": r"\Gamma = \frac{e^{-qT}\, n(d_1)}{S\,\sigma\sqrt{T}} \quad (\text{igual para call e put})",
        "longo": (
            "Comprado em opções = **gamma positivo**: o delta cresce quando o ativo sobe e cai quando desce, ou seja, a posição 'acelera' a seu favor. "
            "Vendido em opções = gamma negativo: o movimento joga contra, e o prejuízo cresce de forma convexa.\n\n"
            "Gamma e theta são as duas faces da mesma moeda: quem tem gamma positivo paga theta todos os dias. "
            "Perto do vencimento, opções ATM têm gamma explosivo: pequenos movimentos do ativo viram grandes variações de delta."
        ),
    },
    "Theta": {
        "curto": "Quanto o prêmio perde por dia só pela passagem do tempo, com tudo o mais constante. Negativo para quem compra.",
        "formula": (
            r"\Theta_{call} = -\frac{S e^{-qT} n(d_1)\,\sigma}{2\sqrt{T}} - rKe^{-rT}N(d_2) + qSe^{-qT}N(d_1)"
            r"\qquad \Theta_{dia} = \Theta_{ano} / 365"
        ),
        "longo": (
            "O valor do tempo decai de forma **não linear**: lento longe do vencimento e acelerado nas últimas semanas (proporcional a 1/√T para ATM). "
            "Uma opção ATM com 30 dias perde mais por dia que a mesma opção com 90 dias.\n\n"
            "A brapi devolve theta **anual**; este painel mostra por dia corrido (÷365) e por dia útil (÷252) para comparar com o seu extrato. "
            "Vendedores de opções 'ganham theta'; compradores precisam que o ativo se mova mais que o theta acumulado para lucrar."
        ),
    },
    "Vega": {
        "curto": "Quanto o prêmio muda para cada 1 ponto percentual de variação na volatilidade implícita.",
        "formula": r"\mathcal{V} = S e^{-qT} n(d_1) \sqrt{T} \qquad \text{por ponto} = \mathcal{V}/100",
        "longo": (
            "Maior para opções ATM e de prazo longo (√T). Comprado em opções = vega positivo: ganha quando a vol implícita sobe "
            "(por exemplo antes de um balanço) e perde quando ela cai (o 'crush' de vol após o evento).\n\n"
            "Vega não é uma letra grega; o nome pegou por soar como uma. Em alguns lugares aparece como 'kappa'."
        ),
    },
    "Rho": {
        "curto": "Sensibilidade do prêmio à taxa de juros (por 1 ponto percentual). Relevante no Brasil por causa da Selic alta.",
        "formula": r"\rho_{call} = K T e^{-rT} N(d_2) \qquad \rho_{put} = -K T e^{-rT} N(-d_2)",
        "longo": (
            "Com Selic de dois dígitos o rho importa mais aqui do que nos EUA: calls ficam mais caras e puts mais baratas quando a taxa sobe, "
            "porque o preço a termo do ativo (S·e^{rT}) sobe. É também por isso que o 'strike ATM' relevante é o do termo, não o spot."
        ),
    },
    "Paridade put-call": {
        "curto": "Relação sem arbitragem entre call e put de mesmo strike e vencimento.",
        "formula": r"C - P = S e^{-qT} - K e^{-rT}",
        "longo": (
            "Se a relação não vale, há arbitragem (comprar o lado barato, vender o caro e travar com o ativo). "
            "Na prática, aluguel de ações, dividendos e custo de carrego quebram a igualdade um pouco. Útil para conferir se a IV de call e put "
            "no mesmo strike faz sentido: elas deveriam ser quase iguais."
        ),
    },
    "Superfície de volatilidade": {
        "curto": "IV em função do strike (sorriso/skew) e do prazo (estrutura a termo). Mostra onde o mercado cobra mais por risco.",
        "formula": r"\sigma_{imp}(K, T)",
        "longo": (
            "**Skew**: puts OTM costumam ter IV maior que calls OTM (medo de queda), formando um 'sorriso torto'. "
            "**Estrutura a termo**: vencimentos curtos reagem mais a eventos; vol de curto prazo acima da longa sugere evento próximo ou estresse.\n\n"
            "Operacionalmente: vender a parte cara da superfície e comprar a barata (trades de skew e de calendário) é a essência da operação de vol relativa."
        ),
    },
    "Contratos em aberto (OI)": {
        "curto": "Quantidade de contratos vivos numa série. Diferente de volume (negociados no dia).",
        "formula": r"\text{OI}_{t} = \text{OI}_{t-1} + \text{abertos} - \text{encerrados}",
        "longo": (
            "Strikes com OI muito alto funcionam como 'ímãs' perto do vencimento (hedge dos formadores de mercado) e mostram onde o mercado está posicionado. "
            "A B3 divulga a quebra em **coberto** (lançador tem a ação), **descoberto** e **bloqueado** (ação depositada em garantia). "
            "A razão put/call de OI é um termômetro de proteção: alta = muito hedge comprado."
        ),
    },
}
