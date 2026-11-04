# Hypothèses de simulation

Ce document centralise les hypothèses explicites du moteur local.

## Principes

- Les hypothèses doivent être explicites et testables.
- Les écarts connus avec l'environnement officiel doivent être documentés ici.
- Les comportements non observables doivent être isolés derrière des modes configurables.

## Hypothèses V1

- Les ordres sont traités timestamp par timestamp.
- Le `TradingState` est reconstruit à chaque itération à partir des snapshots de marché.
- Les ordres sont d'abord matchés contre le carnet.
- Le matching contre `market_trades` est heuristique et dépend du mode configuré.
- Les limites sont vérifiées en pire cas, produit par produit, avant matching.
- Le PnL de fin de timestamp est mark-to-market au `mid_price`.
- Les conversions sont gérées par une règle locale explicite, susceptible d'être recalibrée plus tard.

## Modes de matching `market_trades`

- `none`: aucun matching contre les trades de marché
- `all`: matching si le prix est au moins aussi bon que le quote
- `worse`: matching seulement si le prix est strictement meilleur pour la contrepartie
- `calibrated`: mode prévu pour intégrer une calibration contre des logs officiels

## Limitations connues V1

- Le timeout de `Trader.run()` est soft, pas hard, sur Windows.
- Les conversions sont prévues et testées au niveau moteur, mais non validées contre des logs officiels au moment de l'initialisation du projet.
