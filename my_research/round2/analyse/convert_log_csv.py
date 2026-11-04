"""
Script pour extraire les données de prix et de trades depuis un fichier log.

Modifie les variables ROUND et DAY ci-dessous, puis lance :
    python extract_log.py <fichier.log>

Génère deux fichiers dans le répertoire courant :
    prices_round_X_day_Y.csv
    trades_round_X_day_Y.csv
"""

import json
import csv
import sys
import os

# ─── À MODIFIER ───────────────────────────────────────────────────────────────
ROUND = 2
DAY   = 3
# ──────────────────────────────────────────────────────────────────────────────


def parse_log(log_path: str):
    with open(log_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_prices(activities_log: str, output_path: str):
    lines = activities_log.strip().split("\n")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        for line in lines:
            writer.writerow(line.split(";"))
    print(f"  ✓ Prices : {output_path}  ({len(lines) - 1} lignes)")


def write_trades(trade_history: list, output_path: str):
    fieldnames = ["timestamp", "buyer", "seller", "symbol", "currency", "price", "quantity"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for trade in trade_history:
            writer.writerow({k: trade.get(k, "") for k in fieldnames})
    print(f"  ✓ Trades : {output_path}  ({len(trade_history)} trades)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_log.py <fichier.log>")
        sys.exit(1)

    log_path = sys.argv[1]
    if not os.path.isfile(log_path):
        print(f"Erreur : fichier introuvable -> {log_path}")
        sys.exit(1)

    print(f"\nLecture : {log_path}")
    data = parse_log(log_path)

    suffix      = f"round_{ROUND}_day_{DAY}"
    prices_path = os.path.join(os.getcwd(), f"prices_{suffix}.csv")
    trades_path = os.path.join(os.getcwd(), f"trades_{suffix}.csv")

    write_prices(data.get("activitiesLog", ""), prices_path)
    write_trades(data.get("tradeHistory", []), trades_path)

    print(f"\nFichiers générés dans : {os.getcwd()}")


if __name__ == "__main__":
    main()
