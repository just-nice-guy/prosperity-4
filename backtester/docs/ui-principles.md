# Principes UI / UX

## Objectif

Construire une webapp locale de recherche, pas une simple interface admin.

## Références visuelles

- terminaux de recherche / trading modernes
- dashboards sobres et denses
- hiérarchie claire de l'information

## Principes retenus

- un timestamp pilote la vue
- une sélection produit pilote les panneaux liés
- peu de chrome visuel
- lisibilité très forte des données de marché
- couleurs cohérentes:
  - bid: bleu / vert
  - ask: rouge / orange
  - pnl positif: vert
  - pnl négatif: rouge

## UX V1

- page `Runs` pour lancer et suivre les backtests
- page `Run Detail` comme poste de pilotage principal
- page `Comparison` pour mesurer les écarts avec des logs officiels
- navigation clavier rapide prévue dès l'architecture
