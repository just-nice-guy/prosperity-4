# Prosperity 4 Backtester

Backtester local Prosperity 4, construit comme une reecriture guidee de la base open source
`Xeeshan85/imc-prosperity-4-backtester`, mais avec:

- un moteur de simulation proprement separe;
- un support reel des observations;
- une architecture prete pour les conversions;
- un systeme d'artefacts et de logs structures;
- une API FastAPI pour une webapp locale;
- un frontend React moderne pour visualiser les runs.

## Structure

- `docs/`: audit, hypotheses de simulation, principes UI
- `backend/`: moteur, API, persistance des runs, tests
- `frontend/`: webapp locale React + TypeScript

## Principes

- le repo tiers sert de reference fonctionnelle, pas de dependance runtime;
- la simulation est concue pour etre plus explicite, testable et calibrable;
- l'accuracy est documentee et comparee a des logs officiels des que disponibles;
- le frontend est local-first, pense comme un outil de recherche.

## Demarrage backend

```powershell
cd backtester/backend
python -m pip install -e .
python -m uvicorn prosperity4bt.api.app:app --reload
```

## Demarrage frontend

```powershell
cd backtester/frontend
npm.cmd install
npm.cmd run dev
```

Par defaut, le frontend tourne sur `http://127.0.0.1:5187`.
Tu peux changer ce port avec `PROSPERITY4BT_FRONTEND_PORT`.

## Donnees

Par defaut, le backend decouvre les donnees deja presentes dans le repo principal:

- `stage0/intial data`

Le systeme de registry est prevu pour accueillir d'autres rounds plus tard.
