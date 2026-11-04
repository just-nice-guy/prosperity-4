# Guide Prosperity 4

Derniere mise a jour: 2026-03-20

## Objet de ce guide

Ce document est une version longue, detaillee et en francais du contexte du projet.

Il a 5 objectifs:

1. expliquer clairement ce qu'est Prosperity 4;
2. fixer le contexte officiel utile pour developper des algorithmes;
3. resumer ce que contient deja ce repository;
4. documenter les donnees locales disponibles et ce qu'elles racontent;
5. rassembler les meilleurs conseils, outils et methodes provenant d'anciens participants performants.

Ce guide doit etre considere comme un document vivant.

Quand de nouvelles informations officielles, de nouveaux rounds, de nouveaux produits, ou de nouvelles strategies apparaissent, il faut le mettre a jour.

## Convention de lecture

Le contenu ci-dessous melange trois types d'informations:

- `Officiel`: provenant du wiki Prosperity 4 ou du site officiel.
- `Observation locale`: provenant directement des fichiers presents dans ce repo.
- `Conseil communautaire`: provenant de GitHub, Reddit ou de writeups publics d'anciens participants.

Regle de priorite:

- si une info communautaire contredit l'officiel, l'officiel gagne;
- si l'officiel est ambigu mais que le comportement constate en pratique diverge, il faut noter la divergence et privilegier le comportement reel pour coder.

## Resume executif

Si on devait reduire tout le projet a quelques idees directrices, ce serait:

- Prosperity 4 est une competition de trading algorithmique en Python, organisee par IMC.
- On soumet une classe `Trader` qui recoit un `TradingState` a chaque iteration et renvoie des ordres.
- Le moteur est un simulateur de marche contre des bots, pas contre les autres equipes.
- Le Tutorial Round porte sur `EMERALDS` et `TOMATOES`.
- `EMERALDS` est un produit stable et `TOMATOES` un produit plus fluctuant.
- Ce repo est encore a un stade tres initial: donnees brutes, peu de documentation, pas encore d'algo.
- Les meilleures equipes des editions precedentes avaient presque toutes:
  - un backtester local;
  - un visualizer ou dashboard;
  - des notebooks de recherche;
  - un bon logger;
  - une approche tres structuree et peu overfit.

## Ce qu'est Prosperity 4

Source: `Officiel`

Prosperity 4 est le challenge en ligne de trading algorithmique d'IMC.

Le cadre general officiel:

- le challenge est pense principalement pour des etudiants;
- il simule des marches avec des produits fictifs;
- la monnaie du jeu est `XIRECs`;
- les equipes doivent maximiser leur PnL;
- il existe une partie algorithmique et une partie manuelle;
- les rounds se succedent avec de nouveaux produits et de nouvelles mecaniques;
- le tutorial round sert a prendre en main l'environnement avant les rounds competitifs.

La couche "storyline" parle d'un voyage vers la planete `Intara` via `XIREN`. C'est surtout du decor narratif, mais certains noms reviennent dans la plateforme:

- `XIREN`
- `XIRECs`
- `Intara`

Ce vocabulaire fait partie du contexte officiel du jeu.

## But concret de ce repository

Source: `Observation locale` + `Inference`

Le but concret de ce repo devrait etre:

1. comprendre l'environnement Prosperity 4;
2. analyser les donnees du Tutorial Round;
3. construire un workflow de recherche local;
4. implementer un premier `Trader` propre;
5. iterer sur des strategies produit par produit;
6. conserver la memoire du projet dans une doc persistante.

Au moment de la redaction de ce guide, le repo est clairement centre sur `stage0`, c'est-a-dire la phase tutorial / pre-round:

- `EMERALDS`
- `TOMATOES`
- fichiers de donnees brutes
- dossiers par produit encore vides

Il faut donc voir ce repo comme une base de travail Prosperity 4, pas encore comme une base de code mature.

## Etat actuel du repository

Source: `Observation locale`

Inventaire actuel:

- `README.md`: placeholder minimal
- `doc.md`: premiere synthese structurante
- `stage0/Tomato/readme.md`: vide
- `stage0/emerald/readme.md`: vide
- `stage0/intial data/`: donnees historiques tutorial round

Point important:

- le nom du dossier `intial data` contient une faute de frappe. Il faut le garder en tete pour tous les scripts, paths, loaders et outils.

Ce qui manque encore:

- un `trader.py`
- un datamodel local
- un loader de donnees propre
- un backtester ou replay local
- des notebooks de recherche
- un logger utile
- une structure de code par round

## Carte du wiki officiel Prosperity 4

Source: `Officiel`

Le wiki clone contient principalement:

- `What is Prosperity?`
- `Who is IMC?`
- `Storyline`
- `Round Schedule`
- `Game Mechanics Overview`
- `Rules`
- `FAQ`
- `Trading glossary`
- `Programming resources`
- `Writing an Algorithm in Python`
- `Tutorial Round - Simulator Practice`

Ce sont les pages les plus importantes pour le developpement algo.

## Calendrier officiel

Source: `Officiel`

La competition est structuree ainsi:

- 16 jours au total
- 5 rounds
- deux phases actives separees par une intermission

Le calendrier officiel liste:

| Round | Debut | Fin | Remarques |
| --- | --- | --- | --- |
| Round 1 | Mardi 14 avril 2026, 12:00 CEST | Vendredi 17 avril 2026, 12:00 CEST |  |
| Round 2 | Vendredi 17 avril 2026, 12:00 CEST | Lundi 20 avril 2026, 12:00 CEST | inclut environ 3h de calcul entre R1 et R2 |
| Intermission | Lundi 20 avril 2026, 12:00 CEST | Vendredi 24 avril 2026, 12:00 CEST | inclut le calcul des scores R2 |
| Round 3 | Vendredi 24 avril 2026, 12:00 CEST | Dimanche 26 avril 2026, 12:00 CEST |  |
| Round 4 | Dimanche 26 avril 2026, 12:00 CEST | Mardi 28 avril 2026, 12:00 CEST | inclut environ 3h de calcul entre R3 et R4 |
| Round 5 | Mardi 28 avril 2026, 12:00 CEST | Jeudi 30 avril 2026, 12:00 CEST | inclut environ 3h de calcul entre R4 et R5 |
| Annonce des gagnants | dans les 2 semaines apres la fin du Round 5 |  | verification d'eligibilite |

Informations logistiques officielles a retenir:

- la date de reference est donnee en `CEST (UTC+2)`;
- le `Tutorial Round` est disponible jusqu'au debut du Round 1;
- l'ouverture d'un nouveau round est annoncee par email et sur Discord;
- le calcul des scores prend approximativement 3 heures entre certains rounds.

## Fonctionnement general de la plateforme

Source: `Officiel`

Chaque round comporte:

- un challenge algorithmique;
- un challenge manuel.

Le challenge manuel:

- est independant du challenge algorithmique;
- ne modifie pas le PnL algo;
- peut apporter du score total, mais n'influe pas sur la logique du `Trader`.

Le challenge algorithmique:

- consiste a uploader un fichier Python;
- la derniere soumission active au moment de la cloture est celle qui compte;
- les algorithmes sont evalues chacun de leur cote contre des bots;
- les equipes ne tradent pas directement les unes contre les autres.

Le Tutorial Round:

- permet de tester son code un grand nombre de fois;
- donne du feedback presque immediat;
- est la bonne periode pour construire son environnement de travail.

## Regles et points administratifs utiles

Source: `Officiel`

Points importants pour le projet:

- l'inscription doit etre complete avant le debut du Round 1;
- on peut changer d'equipe jusqu'a la fin du Round 2;
- apres Round 2, la composition de l'equipe est verrouillee;
- un participant ne peut appartenir qu'a une seule equipe;
- le plagiat, l'exploitation de bugs de plateforme, les faux documents ou d'autres abus peuvent mener a une disqualification.

Submissions:

- si un fichier n'est pas marque `active`, il ne compte pas;
- si un ancien fichier est actif et qu'un nouveau n'a pas ete active a temps, l'ancien reste la soumission effective;
- les logs de debug peuvent etre telecharges depuis l'interface.

## Le coeur technique: la classe Trader

Source: `Officiel`

L'interface officielle attend une classe `Trader`.

La methode principale:

```python
def run(self, state: TradingState):
    ...
    return result, conversions, traderData
```

Retours attendus:

- `result`: dictionnaire `produit -> liste d'Order`
- `conversions`: entier pour demander des conversions, ou `0`
- `traderData`: chaine de caracteres pour conserver un etat d'une iteration a l'autre

Cas special note par le wiki:

- au `Round 2`, la classe doit aussi definir `bid()`
- la doc dit qu'il est acceptable de toujours laisser `bid()` dans la classe, il sera ignore hors du round concerne

Exemple de squelette conceptuel:

```python
class Trader:
    def bid(self):
        return 15

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        traderData = ""
        return result, conversions, traderData
```

## Pourquoi `traderData` est crucial

Source: `Officiel`

Le wiki explique que l'infrastructure d'execution est basee sur `AWS Lambda`.

Consequence:

- la plateforme est `stateless`;
- les variables globales, variables de classe, caches memo ou etats implicites ne sont pas garantis entre deux appels.

Donc:

- si une strategie a besoin de memoire, il faut la serialiser dans `traderData`;
- le wiki mentionne explicitement `jsonpickle` comme exemple de serialisation possible.

Limite importante:

- `traderData` est tronque a `50_000` caracteres.

Consequence pratique:

- stocker de petits etats compacts;
- eviter d'y mettre de longues series historiques brutes;
- preferer des statistiques resumees: moyennes glissantes, var, regime, timestamp, quantiles, etat d'inventaire interne, etc.

## Le modele de donnees officiel

Source: `Officiel`

Le wiki donne un `datamodel.py` de reference. Les classes essentielles sont:

- `Listing`
- `Order`
- `OrderDepth`
- `Trade`
- `Observation`
- `ConversionObservation`
- `TradingState`

### TradingState

Champs principaux:

- `traderData`
- `timestamp`
- `listings`
- `order_depths`
- `own_trades`
- `market_trades`
- `position`
- `observations`

Interpretation:

- `order_depths`: le carnet d'ordres observable
- `own_trades`: les trades impliquant notre soumission depuis le dernier etat
- `market_trades`: les trades entre autres participants depuis le dernier etat
- `position`: inventaire signe par produit
- `observations`: signaux additionnels, souvent utiles aux rounds avec conversions

### OrderDepth

Le wiki donne:

```python
class OrderDepth:
    def __init__(self):
        self.buy_orders: Dict[int, int] = {}
        self.sell_orders: Dict[int, int] = {}
```

Interpretation:

- `buy_orders`: `prix -> volume`
- `sell_orders`: `prix -> volume`

Le carnet agrege les ordres par niveau de prix.

### Trade

Champs importants:

- `symbol`
- `price`
- `quantity`
- `buyer`
- `seller`
- `timestamp`

Point tres important du wiki:

- `buyer` et `seller` sont souvent vides;
- ils ne deviennent non vides que si la soumission est elle-meme contrepartie;
- la valeur speciale utilisee est `SUBMISSION`.

### Order

Le wiki rappelle:

- `quantity > 0` signifie un achat
- `quantity < 0` signifie une vente

## Logique d'execution du moteur

Source: `Officiel`

Le moteur fonctionne par iterations.

La doc mentionne:

- environ `1_000` iterations pour les tests de developpement;
- `10_000` iterations pour la simulation finale d'un round.

Chaque iteration:

1. le simulateur construit un `TradingState`;
2. il appelle `run()`;
3. la strategie renvoie des ordres;
4. ces ordres peuvent frapper le carnet existant ou devenir passifs;
5. les bots peuvent reagir pendant l'iteration;
6. si les quotes passives ne sont pas prises, elles sont annulees a la fin de l'iteration.

Ce dernier point change beaucoup la maniere de penser le market making:

- ce ne sont pas des quotes qui restent indefiniment;
- il faut raisonner sur un horizon court, iteration par iteration.

## Semantique des ordres et matching

Source: `Officiel`

Regles de matching:

- un ordre d'achat execute contre des asks a prix inferieur ou egal;
- un ordre de vente execute contre des bids a prix superieur ou egal.

Le prix d'execution suit la logique de l'ordre resting.

La plateforme applique:

- `price-time priority`

Autrement dit:

- meilleur prix d'abord;
- a meme prix, l'ordre le plus ancien est servi avant.

Consequence pratique:

- quand on poste une quote passive, l'emplacement dans la file a ce prix a de l'importance;
- si plusieurs bots sont deja a ce prix, on passe apres eux.

## Limites de position

Source: `Officiel`

C'est un des points les plus importants techniquement.

Le wiki precise:

- la limite de position est absolue;
- elle s'applique produit par produit;
- si l'ensemble des ordres envoyes sur un produit, dans le pire cas ou tout serait execute, depasse la limite, alors tous les ordres de ce produit sont rejetes.

Ce que cela veut dire concretement:

- on ne peut pas raisonner "je n'attends qu'un fill partiel";
- il faut raisonner `worst case fully filled`.

Exemple:

- limite = `80`
- position actuelle = `70`
- si on envoie `+15` au total en buy sur ce produit, c'est rejetable
- meme si en pratique on pense ne recevoir que `3`, le moteur regarde le cas ou tout serait execute

Consequence:

- il faut une couche de controle de risque avant l'envoi d'ordres.

## Observations et conversions

Source: `Officiel`

Le wiki decrit `Observation` avec deux composantes:

- `plainValueObservations`
- `conversionObservations`

Les conversions servent aux rounds qui impliquent:

- import / export;
- arbitrage de localisation;
- couts de transport;
- tarifs;
- signaux externes.

Le wiki indique:

- une conversion se demande via la valeur retour `conversions`;
- la conversion n'est pas obligatoire;
- elle ne peut pas exceder la quantite que l'on detient dans le sens correspondant;
- des couts peuvent s'appliquer: transport, import tariff, export tariff.

Important:

- la page officielle contient quelques incoherences de nommage mineures dans l'appendice sur `ConversionObservation`;
- quand un round utilise reellement ces champs, il faut verifier la spec concrete ou le datamodel fourni a ce moment-la.

## Contraintes techniques de runtime

Source: `Officiel`

Le wiki indique:

- Python `3.12`
- librairies autorisees:
  - toutes les librairies standard Python 3.12
  - `pandas`
  - `NumPy`
- autres librairies externes: non supportees

Performance:

- `run()` doit repondre dans `900 ms`
- l'objectif moyen est plutot `<= 100 ms`

Logs:

- les `print()` apparaissent dans les logs de debug sur la plateforme

Consequence pratique:

- localement on peut utiliser plus d'outils si necessaire;
- mais le code soumis doit rester compatible avec l'environnement officiel;
- le logging de soumission doit rester compact.

## Le Tutorial Round officiel

Source: `Officiel`

La page tutorial dit explicitement:

- on y trade `EMERALDS` et `TOMATOES`
- `EMERALDS` a une valeur plutot stable
- `TOMATOES` fluctue
- le but est d'ecrire son premier algo, l'uploader, le tester, et se familiariser avec l'interface

Limites officielles tutorial:

- `EMERALDS`: 80
- `TOMATOES`: 80

Challenge manuel:

- `N/A` pendant le tutorial round

## Donnees locales disponibles dans ce repo

Source: `Observation locale`

Fichiers presents:

- `stage0/intial data/prices_round_0_day_-2.csv`
- `stage0/intial data/prices_round_0_day_-1.csv`
- `stage0/intial data/trades_round_0_day_-2.csv`
- `stage0/intial data/trades_round_0_day_-1.csv`

Important:

- le separateur est `;`
- pas `,`

### Schema des fichiers de prix

Colonnes observees:

- `day`
- `timestamp`
- `product`
- `bid_price_1`
- `bid_volume_1`
- `bid_price_2`
- `bid_volume_2`
- `bid_price_3`
- `bid_volume_3`
- `ask_price_1`
- `ask_volume_1`
- `ask_price_2`
- `ask_volume_2`
- `ask_price_3`
- `ask_volume_3`
- `mid_price`
- `profit_and_loss`

### Schema des fichiers de trades

Colonnes observees:

- `timestamp`
- `buyer`
- `seller`
- `symbol`
- `currency`
- `price`
- `quantity`

Produits presents:

- `EMERALDS`
- `TOMATOES`

Monnaie:

- `XIRECS`

## Statistiques locales des donnees

Source: `Observation locale`

### Fichiers de prix

Par fichier:

- `20_000` lignes au total
- `10_000` lignes par produit

Timestamps:

- min = `0`
- max = `999900`
- pas = `100`

### Fichiers de trades

Nombre de trades:

- day `-2`: `588`
- day `-1`: `631`

Repartition:

- day `-2`:
  - `TOMATOES`: `397`
  - `EMERALDS`: `191`
- day `-1`:
  - `TOMATOES`: `423`
  - `EMERALDS`: `208`

Autres observations:

- `profit_and_loss` vaut `0` partout dans les prix
- `buyer` et `seller` sont vides dans les trades locaux

Ce dernier point est coherent avec la doc officielle.

## Analyse locale des produits

Source: `Observation locale`

### EMERALDS

Caracteristiques observees:

- moyenne du `mid_price` sur les deux jours: `10000.00`
- ecart-type d'environ `0.72` a `0.73`
- spread top-of-book observe surtout a `8` ou `16`
- ouverture et cloture des deux jours a `10000.0`
- plage de `bid_price_1` day `-2`: `9992` a `10000`
- plage de `ask_price_1` day `-2`: `10000` a `10008`

Interpretation:

- produit tres stable;
- proche d'un exercice introductif de market making;
- la fair value semble pratiquement ancree autour de `10000`.

Strategie naturelle candidate:

- market making simple;
- prise des erreurs manifestes autour d'une fair value presque fixe;
- gestion d'inventaire legere mais indispensable.

### TOMATOES

Caracteristiques observees:

- moyenne du `mid_price` day `-2`: `5007.95`
- moyenne du `mid_price` day `-1`: `4977.57`
- ecart-type du `mid_price`:
  - day `-2`: `10.29`
  - day `-1`: `14.58`
- day `-1`: ouverture autour de `5006.0`, cloture autour de `4957.0`
- day `-2`: ouverture autour de `5000.0`, cloture autour de `5006.5`
- spread top-of-book plus variable que sur `EMERALDS`

Interpretation:

- produit significativement plus mobile;
- demande une fair value dynamique;
- un simple market making "statique" risque d'etre insuffisant.

Strategie naturelle candidate:

- quote autour d'une fair value adaptative;
- eventuellement petite composante mean reversion si les mouvements tres courts reversent;
- controle d'inventaire plus agressif que sur `EMERALDS`.

### Conclusion locale

Le tutorial round local confirme presque parfaitement la description officielle:

- `EMERALDS` = stable
- `TOMATOES` = fluctuant

## Implication strategique immediate pour Stage 0

Source: `Inference`

Un plan Stage 0 raisonnable:

### Strategie EMERALDS

- estimer fair value = `10000`
- prendre les asks trop bas
- vendre contre les bids trop hauts
- placer des quotes autour de la fair value avec une petite edge
- tenir compte de la position

### Strategie TOMATOES

- estimer une fair value glissante
- decider quand prendre agressivement le carnet
- eventuellement poster des quotes avec une edge dependant de la volatilite et de la position
- se mefier des phases directionnelles

### Priorite

Ne pas commencer par "maximiser le PnL".

Commencer par:

1. comprendre le carnet;
2. comprendre les fills;
3. comprendre les limites de position;
4. construire un algo propre, petit et explicable.

## Outils a avoir

Cette section melange recommandations officielles et outils communautaires tres souvent cites.

## Outils officiellement compatibles avec la plateforme

Source: `Officiel`

Dans le code soumis:

- Python 3.12
- standard library
- `pandas`
- `NumPy`

Editeur recommande par le wiki:

- VS Code, ou un IDE equivalent

## Outils de recherche locale recommandes

Source: `Pratique`

Pour le travail local dans ce repo, il est utile d'avoir:

- notebooks Jupyter pour EDA et prototypage rapide
- scripts `pandas` pour charger et nettoyer les CSV
- graphiques simples pour voir:
  - `mid_price`
  - spread
  - profondeur du carnet
  - trades
  - position simulee
- un format de log compact
- un replay / backtester local

## Backtester: ce qu'il faut savoir

Source: `GitHub communautaire`

Le nom qui revient le plus souvent dans les repos performants est:

- [jmerle/imc-prosperity-3-backtester](https://github.com/jmerle/imc-prosperity-3-backtester)

Points utiles:

- il permet de rejouer un algo localement sur les donnees Prosperity 3
- il produit un format de sortie proche de l'environnement officiel
- il fonctionne bien pour des cycles rapides d'experimentation

Etat de la recherche au moment de ce guide:

- je n'ai pas trouve de backtester public Prosperity 4 etabli et evident a la date du 2026-03-20
- donc, pour P4, il faut probablement:
  - soit adapter un backtester des editions precedentes;
  - soit en construire un petit minimal localement pour Stage 0.

## Visualizer et dashboard

Source: `GitHub communautaire`

Le visualizer souvent cite:

- [jmerle/imc-prosperity-3-visualizer](https://github.com/jmerle/imc-prosperity-3-visualizer)

Pourquoi c'est important:

- Prosperity est tres "market microstructure"
- juste lire des CSV ou des PnL finaux ne suffit pas
- il faut voir le carnet, les timestamps, les trades, l'inventaire, les quotes, les niveaux du book

Les meilleures equipes ont souvent fait plus que juste utiliser un visualizer standard:

- elles ont construit leur propre dashboard;
- elles ont ajoute une synchronisation par timestamp;
- elles ont couple carnet + logs + position + PnL sur le meme ecran.

## Les meilleurs conseils des anciens participants

Source: `GitHub communautaire` + `Reddit`

Les points qui reviennent le plus chez les equipes tres bien classees:

### 1. Preparer l'environnement avant le premier round

C'est probablement le conseil le plus important.

Ce que cela veut dire:

- avoir deja un repo propre;
- avoir deja un loader de donnees;
- avoir deja un logger;
- avoir deja un replay local minimal;
- avoir deja lu plusieurs writeups d'anciennes equipes.

Les top teams disent que l'ecart entre les tres bonnes equipes et les equipes moyennes vient souvent plus de cette preparation que de la "brillance mathematique pure".

### 2. Comprendre la microstructure, pas seulement les prix

Il faut regarder:

- qui quote ou frappe;
- comment les volumes apparaissent;
- quels niveaux du carnet sont "epais";
- ou se trouve la vraie pression;
- comment nos quotes passives sont susceptibles d'etre remplies.

Les meilleures equipes insistent beaucoup sur:

- order book intuition
- visualisation
- timestamp-by-timestamp analysis

### 3. Utiliser deux canaux de validation

Le pattern recurrent:

- backtester local pour la vitesse;
- site officiel pour la realite.

Pourquoi:

- le backtester est rapide, scriptable, parametrable;
- mais il ne reproduit pas toujours parfaitement le comportement des bots, les conversions, ni les probabilites de fill passif.

### 4. Garder les strategies simples et robustes

Beaucoup de writeups publics haut niveau disent en substance:

- peu de parametres;
- des hypotheses claires;
- une edge explicable;
- eviter les modeles trop fragiles;
- ne pas confondre bon backtest et vraie edge.

### 5. Utiliser les notebooks pour le prototypage rapide

Pattern standard des meilleures equipes:

- idees initiales dans notebook
- backtest rapide vectorise si possible
- puis integration dans le moteur de simulation

Ce workflow permet:

- de filtrer vite les mauvaises idees;
- de ne pas surinvestir trop tot dans du code de prod.

### 6. Ne pas overfit au score du site

Plusieurs equipes tres fortes le disent explicitement:

- optimiser pour le score de la plateforme seulement est dangereux;
- on peut capter du bruit ou des details aleatoires du simulateur;
- il faut preferer des strategies qui generalisent.

### 7. Faire attention aux logs

Un detail tres pratique:

- trop de `print()` peut devenir un vrai probleme;
- certaines equipes mentionnent des soucis de runtime / AWS Lambda / logs trop verbeux.

Conclusion:

- logger localement beaucoup si besoin;
- soumettre une version plus propre et plus silencieuse.

### 8. Documenter les hypotheses

Les meilleurs repos publics sont rarement juste un `trader.py`.

Ils contiennent souvent:

- des notebooks
- des notes produit par produit
- des logs
- des hypotheses expliquees
- des scripts d'analyse

Pourquoi c'est fort:

- on ne recommence pas a zero a chaque round;
- on garde la memoire des erreurs.

## Ce que faisaient concretement les meilleures equipes

Source: `GitHub communautaire`

## Frankfurt Hedgehogs

Source:

- [TimoDiehm/imc-prosperity-3](https://github.com/TimoDiehm/imc-prosperity-3)

Ce qui ressort de leur writeup:

- ils ont fini 2e mondial;
- ils se sont appuyes sur un fork du backtester open-source de Jmerle;
- ils utilisaient aussi le site Prosperity pour valider les comportements sensibles aux bots;
- ils avaient leur propre dashboard;
- ils insistent beaucoup sur:
  - la preparation;
  - la simplicite;
  - la robustesse;
  - la comprehension structurelle;
  - le rejet de l'overfit aveugle.

Un point tres fort de leur methodologie:

- si une strategie depend surtout d'interactions de bots, ils la validaient plutot via le site;
- si elle depend surtout de logique simple de prise ou de quoting, ils la validaient surtout via le backtester.

Autre idee importante:

- ils faisaient du prototypage rapide dans des notebooks avant d'investir dans une simulation complete.

## Alpha Animals

Source:

- [CarterT27/imc-prosperity-3](https://github.com/CarterT27/imc-prosperity-3)

Ce qui ressort:

- top 10 mondial;
- notebooks de recherche;
- donnees par round;
- `trader.py`;
- usage intensif du backtester et du visualizer de Jmerle.

Leur retour d'experience important:

- certains mecanismes, notamment les conversions, peuvent etre mal supportes par un backtester;
- si on ne verifie pas sur le site officiel, on peut comprendre une mecanique de travers et perdre beaucoup de PnL.

## Linear Utility

Source:

- [ericcccsliu/imc-prosperity-2](https://github.com/ericcccsliu/imc-prosperity-2)

Ce qui ressort:

- 2e mondial sur Prosperity 2;
- outils maison au lieu de s'appuyer surtout sur l'open-source;
- backtester interne;
- dashboard interne;
- repo tres propre par round;
- usage de grid search sur un nombre limite de parametres.

Un point important:

- ils reconstruisaient un environnement de backtest qui ressemblait de tres pres au moteur officiel;
- ils generaient des logs proches du format du site.

## Outils communautaires a connaitre

Source: `GitHub communautaire`

Liste utile:

- [jmerle/imc-prosperity-3-backtester](https://github.com/jmerle/imc-prosperity-3-backtester)
- [jmerle/imc-prosperity-3-visualizer](https://github.com/jmerle/imc-prosperity-3-visualizer)
- [jmerle/imc-prosperity-2](https://github.com/jmerle/imc-prosperity-2)
- [jmerle/imc-prosperity-2-backtester](https://github.com/jmerle/imc-prosperity-2-backtester)
- [jmerle/imc-prosperity-2-visualizer](https://github.com/jmerle/imc-prosperity-2-visualizer)
- [jmerle/imc-prosperity-2-submitter](https://github.com/jmerle/imc-prosperity-2-submitter)
- [jmerle/imc-prosperity-2-leaderboard](https://github.com/jmerle/imc-prosperity-2-leaderboard)

## Conseils Reddit utiles

Source: `Reddit communautaire`

Les threads Reddit trouves ne sont pas une source officielle, mais les themes utiles sont coherents avec les writeups GitHub:

- preparer avant le jour 1;
- lire les meilleurs repos publics avant le debut;
- construire un backtester ou au moins savoir en utiliser un;
- avoir des bases en:
  - market making
  - stat arb
  - options
  - arbitrage de conversion / location
- se mefier du bruit sur Discord et des screenshots de PnL incroyables;
- garder la tete froide.

Point de prudence:

- certains posts avancent des archetypes de rounds recurrents d'une annee sur l'autre;
- cela peut etre inspirant;
- ce n'est pas une garantie officielle.

## Les pieges principaux

En pratique, voici les erreurs qu'il faut eviter.

### 1. Overfit

Exemples:

- ajuster trop finement un seuil sur deux jours de donnees;
- choisir un modele uniquement parce qu'il "gagne" sur l'historique;
- multiplier les parametres sans justification.

### 2. Oublier le risque de fill complet

Si on oublie le controle de limite de position, l'algo peut voir tous ses ordres rejetes sur un produit.

### 3. Faire confiance aveuglement au backtester

Problemes connus:

- comportement des bots pas parfaitement reproduit
- conversions mal modelisees
- probabilites de fills passifs mal capturees

### 4. Logger trop

Trop de logs peut nuire a la soumission finale.

### 5. Partir directement sur une strategie complexe

Mieux vaut:

- une baseline simple, correcte, testable

que:

- une machine plus sophistiquee mais mal comprise.

### 6. Travailler sans visualisation

Sur Prosperity, ne regarder que des courbes de mid-price est souvent insuffisant.

## Ce qu'il faudrait construire dans ce repo

Cette section est une recommandation pratique.

## Structure cible minimale

Exemple de structure souhaitable a court terme:

- `guide.md`
- `doc.md`
- `stage0/`
- `stage0/data_loader.py`
- `stage0/trader.py`
- `stage0/backtest.py`
- `stage0/notebooks/`
- `stage0/strategies/emeralds.py`
- `stage0/strategies/tomatoes.py`
- `stage0/logging_utils.py`

## Baseline minimale a construire

Pour Stage 0:

1. loader des CSV prices/trades
2. datamodel local simplifie pour le replay
3. boucle de replay timestamp par timestamp
4. `Trader` baseline
5. strategie `EMERALDS`
6. strategie `TOMATOES`
7. logs utiles

## Baseline recommandee produit par produit

### EMERALDS baseline

Objectif:

- exploiter l'ancrage autour de `10000`

Composants:

- fair value fixe a `10000`
- prise agressive des asks sous fair
- vente agressive des bids au-dessus
- quoting passif autour de fair
- skew de quote selon position

### TOMATOES baseline

Objectif:

- capter une fair value plus mobile

Composants:

- estimateur glissant de fair value
- eventuellement micro mean reversion
- quoting plus prudent si la volatilite monte
- penalite plus forte sur l'inventaire

## Workflow recommande

Workflow de travail propose:

1. explorer les CSV dans un notebook
2. definir une hypothese produit
3. coder une version simple
4. rejouer localement
5. inspecter les trades et quotes
6. corriger les erreurs de logique et de risque
7. documenter les enseignements

## Comment maintenir ce guide dans le temps

A chaque nouveau round, mettre a jour:

- les produits disponibles
- les limites de position
- les nouveaux champs d'observation
- les nouvelles hypotheses de strategie
- les outils utilises
- les ecarts constates entre la doc et la pratique

Checklist de maintenance:

1. relire le wiki officiel du round;
2. noter les limites et produits;
3. ajouter les fichiers de donnees correspondants;
4. resumer les nouvelles mecaniques de marche;
5. documenter les erreurs de l'algo precedent;
6. mettre la date de mise a jour.

## Plan d'action concret pour ce repo

Si l'objectif est de devenir rapidement productif, l'ordre logique est:

1. creer un `trader.py` baseline;
2. creer un petit replay local sur les CSV tutorial round;
3. ajouter un notebook d'analyse `EMERALDS` / `TOMATOES`;
4. implementer le controle de position propre;
5. ajouter un logger compact;
6. documenter les resultats dans les readmes de `stage0/Tomato` et `stage0/emerald`.

## Ce qu'il faut retenir en une phrase

Si on veut bien faire Prosperity 4, il faut moins chercher "une formule magique" que construire un systeme de travail solide:

- bonne lecture du marche
- bon backtesting
- bonne visualisation
- bonne discipline de risque
- bonne documentation

## Sources

### Sources officielles

- Prosperity 4 Wiki:
  - https://www.notion.so/Prosperity-4-Wiki-3de66194bb4c82abba1181f0addae60b?source=copy_link
- Writing an Algorithm in Python:
  - https://www.notion.so/Writing-an-Algorithm-in-Python-02066194bb4c8261aedb818b308bd654
- Programming resources:
  - https://www.notion.so/Programming-resources-71e66194bb4c82508fd901c0bb7a826a
- Game Mechanics Overview:
  - https://www.notion.so/Game-Mechanics-Overview-d7466194bb4c8212b97981838b7618c6
- Tutorial Round - Simulator Practice:
  - https://www.notion.so/Tutorial-Round-Simulator-Practice-17166194bb4c83048c1a811dcf62ef12
- Rules:
  - https://www.notion.so/Rules-cba66194bb4c82f48523017162c85511
- FAQ:
  - https://www.notion.so/FAQ-fe666194bb4c832f84f701ffaa49d556
- Round Schedule:
  - https://www.notion.so/Round-Schedule-d8266194bb4c833fbcd581bc15ab2c8f
- Trading glossary:
  - https://www.notion.so/Trading-glossary-9d566194bb4c835295cb8107128474cf
- What is Prosperity?:
  - https://www.notion.so/What-is-Prosperity-e7966194bb4c82008056819631c0fdbf
- Who is IMC?:
  - https://www.notion.so/Who-is-IMC-3b266194bb4c82d3a6bb81b32ba3ad6b
- Storyline:
  - https://www.notion.so/Storyline-e2d66194bb4c8238a00c81f64d1364a2

### Sources GitHub communautaires

- Frankfurt Hedgehogs:
  - https://github.com/TimoDiehm/imc-prosperity-3
- Alpha Animals:
  - https://github.com/CarterT27/imc-prosperity-3
- Linear Utility:
  - https://github.com/ericcccsliu/imc-prosperity-2
- Jmerle Prosperity 3 Backtester:
  - https://github.com/jmerle/imc-prosperity-3-backtester
- Jmerle Prosperity 3 Visualizer:
  - https://github.com/jmerle/imc-prosperity-3-visualizer
- Jmerle Prosperity 2 Overview:
  - https://github.com/jmerle/imc-prosperity-2
- Jmerle Prosperity 2 Backtester:
  - https://github.com/jmerle/imc-prosperity-2-backtester
- Jmerle Prosperity 2 Visualizer:
  - https://github.com/jmerle/imc-prosperity-2-visualizer
- Jmerle Prosperity 2 Submitter:
  - https://github.com/jmerle/imc-prosperity-2-submitter
- Jmerle Prosperity 2 Leaderboard:
  - https://github.com/jmerle/imc-prosperity-2-leaderboard

### Sources Reddit communautaires

- How to actually compete in IMC Prosperity 4:
  - https://www.reddit.com/r/quantfinance/comments/1rtlsvn/how_to_actually_compete_in_imc_prosperity_4/
- How to prepare for IMC Prosperity:
  - https://www.reddit.com/r/quantfinance/comments/1rr5ik7/how_to_prepare_for_imc_prosperity/
- Is anyone doing IMC Prosperity 3 algo trading challenge?:
  - https://www.reddit.com/r/algotrading/comments/1jroybp/is_anyone_doing_imc_prosperity_3_algo_trading/
