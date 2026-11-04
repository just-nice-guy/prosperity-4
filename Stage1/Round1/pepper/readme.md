# INTARIAN_PEPPER_ROOT — Round 1

## Profil produit

**Trend lineaire quasi-deterministe** avec derive constante de `+0.001` par tick
(soit `+1000` par journee complete de 1_000_000 ticks).
Famille: cousin eloigne de STARFRUIT (P2) et KELP (P3), mais avec une structure
bien plus propre. Ce n'est **pas** un simple random walk ni du mean reversion.

## EDA stage1 (days -2, -1, 0)

| Day | open | close | slope OLS / tick | r-squared | residu std |
|---|---|---|---|---|---|
| -2 |  9998.5 | 11001.5 | 0.001000 | 1.0000 | 1.12 |
| -1 | 10998.5 | 11998.0 | 0.001000 | 1.0000 | 1.26 |
|  0 | 11998.5 | 13000.0 | 0.001000 | 1.0000 | 1.34 |

- **Fit lineaire parfait** (`r^2 = 1.0`) sur les 3 jours, residu std ~1.3.
- **Continuite inter-jours**: close du jour N = open du jour N+1 => pas de reset.
- **Spread**: mediane 12-14 (augmente avec le niveau absolu), min 2, max ~20.
- **Profondeur**: ~25 unites totales par cote, L1 ~11 unites, niveaux 1.7 / 3.
- **Tick Delta-mid**: std 1.6-1.9, mean|Delta| 1.0-1.2, ~39% de ticks sans changement.
- **Livre vide**: ~4% des ticks ont un cote manquant.
- **Trades**: 332-344 / jour, qty moyenne 5.2, max 8.

## Fair value

```
fv(ts) = a + b * ts
```

avec `b = 0.001` (derive historique constante) et `a` = open du jour courant.

En live, on estimera `a, b` par OLS glissante sur les `N` derniers mids valides
(`N ~ 200..500`), avec prior `b = 0.001`. Si la pente empirique diverge trop
de la pente historique, basculer en mode neutre (MM sur mid courant).

## Strategie baseline proposee (pas encore codee)

- **FV dynamique**: droite `a + 0.001 * ts` reestimee en continu.
- **Quoting**: `fv +/- k` avec `k = 2` ticks (le residu est ~1.3, c'est tenable).
- **Skew asymetrique pro-trend**: position cible positive par defaut, pas neutre.
  La derive positive recompense une position longue. Avellaneda-Stoikov modifie:
  `r = fv - gamma * sigma * (pos - target_long)`.
- **Taking**:
  - Achat de tout ask < `fv - edge`.
  - Vente de tout bid > `fv + edge`.
- **Protection contre regime change**: si |pente_empirique - 0.001| > seuil,
  ne pas faire confiance a la composante trend et retomber sur MM neutre.
- **Worst-case fully-filled** obligatoire.

## Risques et pieges

- **Le trader TOMATOES de stage0 est inadapte ici**: son composant OU mean-reverting
  va lutter contre la derive lineaire. Ne pas copier tel quel, reecrire light.
- **Propriete trop belle**: les 3 jours historiques ont exactement la meme pente.
  Risque que le vrai jour de competition ait une pente differente, pas de pente,
  ou un regime piecewise. Prevoir un fallback neutre.
- **Saut de niveau entre jours**: nul dans les donnees historiques (continuite
  parfaite), mais possible en live. Reinitialiser `a` au premier tick du jour.
- **Limite de position Round 1 non encore verifiee** dans le wiki officiel.

## A confirmer avant soumission

- Limite de position officielle pour INTARIAN_PEPPER_ROOT (Round 1 wiki).
- Presence ou non d'un challenge manuel sur ce produit.
- Verification que la derive `0.001` tient bien sur le tout premier tick live.
