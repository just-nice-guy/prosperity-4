# ASH_COATED_OSMIUM — Round 1

## Profil produit

Produit **stable mean-reverting** ancre autour de `10000`.
Famille: successeur direct de PEARLS (P1), AMETHYSTS (P2), RAINFOREST_RESIN (P3).

## EDA stage1 (days -2, -1, 0)

| Day | mean(mid) | std | open | close |
|---|---|---|---|---|
| -2 | 9998.16  | 4.73 | 10000.0 | 9993.5  |
| -1 | 10000.83 | 3.82 | 9992.0  | 10002.0 |
|  0 | 10001.62 | 5.22 | 10003.0 | 10007.0 |
| **overall** | **10000.21** | 4.86 | range 9981.5 - 10017.5 | |

- **Spread**: mediane `16`, mode `16` (~60%), queue a `18/19`, min `5`, max `22`.
- **AR(1) sur mid**: phi ~ `0.88-0.93`, equilibre `~10000` sur les 3 jours => forte mean reversion vers 10000.
- **Profondeur**: ~31 unites totales par cote sur 3 niveaux, L1 ~14 unites.
- **Niveaux remplis**: moyenne 1.7 / 3 par cote.
- **Tick Delta-mid**: std ~1.92, mean|Delta| ~1.25, ~32% de ticks sans changement.
- **Livre vide**: ~4% des ticks ont un cote manquant, ~0.2% ont les deux cotes vides.
- **Trades**: 411-429 / jour, qty moyenne 5.2, max 10.

## Fair value

`FV = 10000` constante.
Optionnel: EMA tres lente (alpha ~ 0.01) pour detecter une derive si le simulateur decide d'en introduire une en live.

## Strategie baseline proposee (pas encore codee)

- **Taking agressif**: achat de tout ask <= 9998, vente de tout bid >= 10002 (edge >= 2 ticks net).
- **Quoting passif**: autour de `10000 +/- 2..3` selon inventaire, 2 niveaux empiles (gap 1 tick).
- **Skew d'inventaire**: Avellaneda-Stoikov leger (gamma ~0.02) reservation price `r = 10000 - gamma * sigma * pos`.
- **Anti-cross**: clamp des quotes passives a `best_bid..best_ask - 1`.
- **Regime de gestion**:
  - soft_limit a 50% de la position limite => reduire la taille sur le cote "risque".
  - reduce-only a 70% => ne quoter que le cote qui ramene vers zero.
- **Fallback livre vide**: si `bid_price_1` ou `ask_price_1` est None, ne pas quoter cette iteration.
- **Worst-case fully-filled** tracking obligatoire avant chaque `Order()`.

## Risques et pieges

- Spread large => tentation de quoter trop serre. A valider par backtest.
- Livre souvent creux => les fills passifs peuvent etre moins frequents que ce que le spread suggere.
- Limite de position Round 1 **non encore verifiee** dans le wiki officiel.

## A confirmer avant soumission

- Limite de position officielle pour ASH_COATED_OSMIUM (Round 1 wiki).
- Presence ou non d'un challenge manuel sur ce produit.
