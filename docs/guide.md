# Guide de Reussite Prosperity 4

Derniere mise a jour: 2026-03-20

## But de ce guide

Ce fichier n'est pas une doc generale sur Prosperity.

Son seul but est de repondre a la question:

**comment bien travailler et comment maximiser ses chances de reussite dans Prosperity 4 ?**

Il rassemble:

- les conseils les plus utiles d'anciens participants;
- les habitudes des meilleures equipes;
- le bon workflow de travail;
- les outils a avoir;
- les pieges a eviter;
- un plan concret pour savoir par ou commencer.

## Le principe le plus important

La plupart des equipes moyennes pensent que le plus dur est de "trouver la bonne strategie".

En pratique, ce qui separe souvent les meilleures equipes des autres, c'est surtout:

- la preparation avant les rounds;
- la qualite du workflow;
- la vitesse d'iteration;
- la capacite a comprendre un produit rapidement;
- la discipline pour ne pas overfit.

Autrement dit:

**la difference ne vient pas seulement d'une bonne idee, mais d'un bon systeme de travail.**

## Ce que font les meilleures equipes

En regardant les repos publics de bonnes equipes des editions precedentes, on retrouve presque toujours les memes ingredients.

### 1. Elles preparent l'environnement avant que le vrai round commence

Elles n'attendent pas l'ouverture du round pour:

- installer Python et les outils;
- organiser le repo;
- comprendre le format des donnees;
- mettre en place un logger;
- apprendre a relire un carnet d'ordres;
- monter un backtester ou un replay local.

Elles arrivent deja prêtes a travailler.

### 2. Elles ont un cycle de recherche rapide

Leur boucle de travail ressemble a:

1. lire les donnees;
2. formuler une hypothese;
3. tester vite;
4. visualiser;
5. corriger;
6. retester;
7. soumettre une version propre.

Elles evitent de rester trop longtemps dans la theorie ou dans le code "joli mais inutile".

### 3. Elles se servent beaucoup d'outils

Presque toutes les bonnes equipes publiques avaient:

- un backtester local;
- un visualizer ou dashboard;
- des notebooks de recherche;
- un logger lisible;
- une organisation propre par round ou par produit.

### 4. Elles travaillent produit par produit

Elles ne codent pas un monstre unique des le debut.

Elles se demandent:

- quelle est la structure de ce produit ?
- est-il stable, volatil, mean reverting, trendant ?
- y a-t-il une vraie fair value identifiable ?
- les fills passifs ont-ils l'air probables ?
- quel est le vrai risque principal ?

Puis elles developpent une logique simple adaptee a ce produit.

### 5. Elles restent simples plus longtemps que les autres

Le pattern recurrent chez les bonnes equipes:

- d'abord une baseline propre;
- ensuite seulement des raffinements;
- peu de parametres;
- pas de complexite gratuite.

## Ce que disaient ou faisaient quelques equipes fortes

## Frankfurt Hedgehogs

Repo:

- https://github.com/TimoDiehm/imc-prosperity-3

Ce qui ressort de leur approche:

- preparation tres serieuse avant competition;
- fork d'un backtester open-source;
- validation sur le site officiel quand les bots ou les mecanismes specifiques comptaient;
- dashboard maison pour visualiser le carnet et les trades;
- grande insistance sur la microstructure;
- rejet explicite de l'overfit au score du site.

Leur idee forte:

- utiliser le backtester pour aller vite;
- utiliser le site officiel pour verifier la realite.

## Alpha Animals

Repo:

- https://github.com/CarterT27/imc-prosperity-3

Ce qui ressort:

- notebooks de recherche;
- algorithme proprement isole;
- usage intensif du backtester et du visualizer;
- retour d'experience tres clair sur les limites du backtester, surtout quand certaines mecaniques sont mal modelisees.

Leur lecon importante:

- si le backtester ne reproduit pas bien une mecanique, il faut la verifier ailleurs avant d'en faire le coeur de la strategie.

## Linear Utility

Repo:

- https://github.com/ericcccsliu/imc-prosperity-2

Ce qui ressort:

- outils maison;
- backtester maison;
- dashboard maison;
- structure de repo tres propre;
- optimisation sur un petit nombre de parametres utiles.

Leur force:

- environnement de travail tres maitrise;
- forte capacite a iterer proprement.

## Les outils a avoir

Si tu veux travailler comme les equipes serieuses, voici le minimum utile.

## 1. Un backtester ou au moins un replay local

Le nom qui revient le plus souvent dans la communaute est:

- `jmerle/imc-prosperity-3-backtester`

Ce qu'il apporte:

- replay local rapide;
- debug hors plateforme;
- iteration tres rapide;
- integration naturelle dans un workflow de recherche.

Si aucun backtester Prosperity 4 n'est public ou mature:

- il faut en construire un minimal soi-meme;
- au pire, un replay timestamp par timestamp avec une logique simple est deja tres utile.

## 2. Un visualizer ou dashboard

Le deuxieme outil critique.

Pourquoi:

- Prosperity est tres centre carnet d'ordres;
- regarder seulement le `mid_price` est insuffisant;
- il faut voir les bids, asks, trades, fills, position, PnL et logs.

Un visualizer sert a repondre a des questions comme:

- est-ce qu'on se fait prendre trop vite ?
- est-ce qu'on quote au mauvais prix ?
- est-ce qu'on frappe trop agressivement ?
- ou part la perte ?
- quand notre inventaire part-il dans le mauvais sens ?

## 3. Des notebooks

Les notebooks servent a:

- explorer les donnees;
- tester vite une hypothese;
- calculer une fair value;
- comparer plusieurs signaux;
- inspecter les regimes.

Ils ne remplacent pas le backtester.

Ils servent a aller vite avant de coder dans le moteur.

## 4. Un logger propre

Sans logger, on avance a l'aveugle.

Mais il faut un logger utile, pas du bruit.

A logguer localement:

- fair value estimee;
- position;
- taille et prix des quotes;
- decisions d'agression;
- raison de certaines actions;
- indicateurs internes.

Avant soumission:

- reduire fortement les logs;
- garder seulement ceux qui aident vraiment.

## Le bon workflow

Voici le workflow le plus sain pour travailler.

## Etape 1. Comprendre la donnee avant de coder

Avant toute strategie:

- lire les schemas des fichiers;
- verifier les delimiters;
- regarder les timestamps;
- verifier les produits presents;
- mesurer spread, volatilite, profondeur, nombre de trades;
- regarder si les buyer/seller sont renseignes ou non;
- comparer jour par jour.

La bonne question n'est pas "quelle strategie dois-je coder ?" mais:

**qu'est-ce que la donnee raconte vraiment ?**

## Etape 2. Formuler une hypothese simple

Exemples:

- le produit a une fair value presque fixe;
- le produit mean revert autour d'un niveau;
- le produit trend parfois par blocs;
- certains niveaux du carnet semblent ancrer le vrai prix;
- le spread est suffisamment large pour faire du market making.

Une bonne hypothese doit etre:

- simple;
- testable;
- falsifiable.

## Etape 3. Construire une baseline

Ne pas viser "la meilleure strategie" d'abord.

Viser:

- une strategie propre;
- qui respecte les limites;
- qui fait quelque chose d'explicable;
- qui permet de mesurer ce qui marche et ce qui casse.

Une bonne baseline doit deja:

- gerer la position;
- gerer les limites;
- gerer les quotes buy et sell;
- gerer un minimum de fair value.

## Etape 4. Backtester

But du backtest:

- verifier que la logique marche;
- mesurer ou part le PnL;
- voir si le risque est maitrise;
- detecter les comportements bizarres.

Ce qu'il faut regarder:

- PnL total;
- PnL par produit;
- distribution de position;
- drawdowns;
- nombre de trades;
- decomposition maker / taker si possible;
- timestamps des pertes.

## Etape 5. Visualiser

Une fois les resultats obtenus, il faut voir:

- a quels moments l'algo a perdu;
- si les quotes etaient trop agressives;
- si la fair value etait decalee;
- si l'inventaire s'accumulait mal;
- si certaines executions sont trompeuses dans le backtest.

Beaucoup de progression se fait ici.

## Etape 6. Ajuster peu de choses a la fois

Erreur classique:

- changer 8 parametres en meme temps;
- ajouter 3 features a la fois;
- ne plus savoir ce qui a cause l'amelioration ou la degradation.

Bonne pratique:

- modifier une idee a la fois;
- mesurer;
- documenter;
- conserver les versions utiles.

## Etape 7. Soumettre une version stable

Avant une soumission serieuse:

- verifier que le code est propre;
- verifier qu'il respecte bien les limites;
- reduire les logs;
- enlever les essais incomplets;
- preferer une version robuste a une version "geniale" mais fragile.

## Par ou commencer concretement

Si tu debutes ou si le repo est encore jeune, commence dans cet ordre.

## Phase A. Mettre le terrain en ordre

1. Avoir un repo propre.
2. Avoir un loader de donnees.
3. Avoir un notebook d'EDA.
4. Avoir un mini replay local.
5. Avoir un squelette `Trader`.

Sans ca, tu vas perdre du temps partout.

## Phase B. Obtenir une baseline par produit

Pour chaque produit:

1. trouver une fair value initiale;
2. definir quand acheter;
3. definir quand vendre;
4. definir comment tenir compte de la position;
5. verifier que le risque est controle.

## Phase C. Comprendre les pertes

Ensuite seulement:

- identifier les situations qui coutent cher;
- comprendre si le probleme vient:
  - de la fair value;
  - du spread;
  - des fills;
  - du risque;
  - du regime de marche.

## Phase D. Raffiner avec discipline

Ajouts possibles apres baseline:

- fair value glissante;
- skew d'inventaire;
- controle de volatilite;
- differenciation maker / taker;
- filtres de regime;
- ajustement des tailles.

## Ce qui est vraiment important

Si on resume tres brutalement:

### Important

- comprendre la microstructure;
- avoir un bon workflow;
- visualiser;
- respecter le risque;
- iterer vite;
- garder une trace de ce qu'on apprend;
- preferer robuste a clever.

### Peu important au debut

- modeles compliques;
- sur-optimisation;
- tricks obscurs;
- gros refactors de style;
- code "parfait" au lieu de code testable.

## Les plus grosses erreurs a eviter

## 1. Overfit

Le piege numero un.

Exemples:

- ajuster un seuil exactement sur deux jours historiques;
- choisir une strategie uniquement parce qu'elle marche sur le backtest local;
- empiler des parametres jusqu'a faire monter artificiellement le PnL.

## 2. Croire que le backtester dit toute la verite

Le backtester est un outil.

Ce n'est pas la realite absolue.

Les grosses divergences possibles:

- comportement des bots;
- fills passifs;
- conversions;
- subtilites non modelisees.

## 3. Ne pas penser en pire cas pour les limites

Le moteur regarde le cas ou tous les ordres seraient executes.

Donc:

- une strategie qui "semble" prudente peut etre massivement rejetee si elle ne compte pas bien ses quantites.

## 4. Logger comme un notebook pendant la soumission

Trop de logs = risque inutile.

## 5. Vouloir faire complexe trop tot

Un algo simple, lisible et testable vaut mieux qu'un systeme trop ambitieux que personne ne comprend.

## Le meilleur ordre mental pour analyser un produit

Quand un nouveau produit arrive, poser toujours ces questions:

1. Quelle est sa structure globale ?
2. Y a-t-il une fair value naturelle ?
3. Est-elle fixe ou mobile ?
4. Le spread est-il exploitable ?
5. Les quotes passives ont-elles des chances d'etre prises ?
6. Le produit est-il plutot maker-friendly ou taker-friendly ?
7. Quel est le risque principal:
   - mauvais pricing
   - inventaire
   - volatilite
   - mauvaise simulation
8. Quelle est la baseline la plus simple qui fait sens ?

## Le bon rythme de travail pendant un round

Quand le round est actif, le bon rythme est souvent:

### Debut de round

- lire la spec;
- comprendre les produits;
- faire l'EDA;
- identifier 1 a 3 hypotheses serieuses.

### Milieu de round

- transformer les hypotheses en baseline;
- comparer les variantes;
- isoler ce qui marche vraiment;
- debugger les pertes.

### Fin de round

- stabiliser;
- simplifier si besoin;
- nettoyer la soumission;
- choisir la version la plus robuste.

Erreur classique de fin de round:

- casser une version correcte en voulant ajouter "le dernier trick".

## Ce que je recommande pour ce repo maintenant

Vu l'etat actuel du projet, le meilleur workflow est:

1. garder `doc.md` comme reference generale du projet;
2. utiliser ce `guide.md` comme playbook de travail;
3. construire un `stage0` propre et minimal;
4. obtenir une baseline `EMERALDS` et une baseline `TOMATOES`;
5. backtester et visualiser;
6. documenter les resultats produit par produit.

## Checklist minimale pour bien demarrer

- un loader CSV fiable
- un notebook EDA
- un replay local
- un `Trader` baseline
- une gestion de position propre
- des logs utiles
- une note par produit

## Checklist avant une soumission

- la strategie est explicable
- les limites de position sont respectees
- les tailles d'ordres sont coherentes
- les logs sont limites
- aucune partie experimentale inachevee n'est laissee active
- la version choisie est robuste, pas juste brillante sur un test

## En une phrase

Pour reussir Prosperity, il faut moins chercher un coup de genie que construire une machine de travail:

- comprendre vite;
- tester vite;
- visualiser vite;
- corriger vite;
- rester simple;
- rester discipline.

## Sources d'inspiration

Repos communautaires tres utiles:

- https://github.com/TimoDiehm/imc-prosperity-3
- https://github.com/CarterT27/imc-prosperity-3
- https://github.com/ericcccsliu/imc-prosperity-2
- https://github.com/jmerle/imc-prosperity-3-backtester
- https://github.com/jmerle/imc-prosperity-3-visualizer

Threads Reddit utiles:

- https://www.reddit.com/r/quantfinance/comments/1rtlsvn/how_to_actually_compete_in_imc_prosperity_4/
- https://www.reddit.com/r/quantfinance/comments/1rr5ik7/how_to_prepare_for_imc_prosperity/
- https://www.reddit.com/r/algotrading/comments/1jroybp/is_anyone_doing_imc_prosperity_3_algo_trading/
