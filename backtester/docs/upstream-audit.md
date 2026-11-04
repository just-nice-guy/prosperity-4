# Audit du repo upstream

Repo audité:

- `Xeeshan85/imc-prosperity-4-backtester`

## Points positifs retenus

- structure simple et lisible
- CLI utilisable rapidement
- logique de replay déjà praticable pour le tutorial round
- modes de matching explicites (`none`, `all`, `worse`)
- packaging propre et CI minimale
- compatibilité avec le visualizer Prosperity 3

## Faiblesses identifiées

- pas de tests visibles
- observations lues mais non injectées dans `TradingState`
- conversions non supportées
- traces Prosperity 3 dans les exports et le visualizer
- hypothèses de matching implicites
- structure correcte pour un utilitaire, moins bonne pour un produit extensible backend + webapp

## Décisions de reprise

Nous reprenons conceptuellement:

- le principe de replay par timestamp
- la séparation entre matching carnet et matching `market_trades`
- la notion de mode de matching configurable
- l'idée d'un export de logs compatible visualizer

Nous rejetons:

- le moteur monolithique
- les sorties partiellement héritées de Prosperity 3
- l'absence de tests
- l'absence de couche API / persistance / comparaison

## Positionnement

Le repo upstream sert de:

- référence fonctionnelle;
- référence d'hypothèses;
- point de comparaison pour le tutorial round.

Il ne sert pas de:

- dépendance runtime;
- moteur officiel;
- source de vérité finale.
