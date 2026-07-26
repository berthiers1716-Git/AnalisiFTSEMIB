#!/usr/bin/env python3
# File: recupera_storico.py
#
# Recupera automaticamente, per un intervallo di date passate, i dati opzioni
# FTSEMIB direttamente da Euronext (stesso endpoint live usato da monitora_euronext.py)
# e popola il log eventi_volume.csv - senza bisogno di aver scaricato/copiato nulla
# a mano in quei giorni.
#
# Utile per:
# - colmare buchi nel passato (es. giorni in cui il copia-incolla manuale e' stato
#   fatto con dati incompleti, o semplicemente dimenticato)
# - evitare lo stress di dover ricordarsi ogni giorno di scaricare i dati
#
# Lo spot di ciascun giorno viene preso automaticamente dal CSV storico prezzi
# FTSEMIB (time,open,high,low,close), se fornito - altrimenti va indicato un
# valore fisso (--spot), usato per tutti i giorni (meno preciso).
#
# Esempio:
#   python3 recupera_storico.py --da 2026-07-01 --a 2026-07-22 \
#       --prezzi INDEX_FTSEMIB__1D__1_.csv --soglia 100
# -----------------------------------------------------------------------------

import argparse
import sys
import time
import datetime as dt
import pandas as pd

from euronext_live_module import crea_sessione, fetch_live_html_batched, parse_live_html, \
    log_significant_volume_events_live, SCADENZE_NOTE

VOLUME_LOG_PATH = "dati_locali/eventi_volume.csv"
CONTRACT_MULTIPLIER = 2.5
DEFAULT_THRESHOLD = 100
DEFAULT_BATCH_SIZE = 5
PAUSA_TRA_GIORNI_SEC = 2  # cortesia verso il server: non incalzare richieste senza pause


def carica_spot_storico(percorso_csv):
    """Legge il CSV storico prezzi (time,open,high,low,close) e ritorna {date: close}."""
    df = pd.read_csv(percorso_csv, parse_dates=['time'])
    return dict(zip(df['time'].dt.date, df['close']))


def main():
    parser = argparse.ArgumentParser(description="Recupera storicamente eventi volume FTSEMIB da Euronext.")
    parser.add_argument('--da', type=str, required=True, help="Data iniziale, formato YYYY-MM-DD")
    parser.add_argument('--a', type=str, required=True, help="Data finale, formato YYYY-MM-DD")
    parser.add_argument('--prezzi', type=str, default=None,
                         help="CSV storico prezzi FTSEMIB (time,open,high,low,close) per lo spot automatico")
    parser.add_argument('--spot', type=float, default=None,
                         help="Spot fisso da usare per tutti i giorni, se non fornisci --prezzi "
                              "o per le date assenti nel CSV storico")
    parser.add_argument('--soglia', type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument('--scadenze', nargs='*', default=None)
    parser.add_argument('--batch', type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument('--solo-feriali', action='store_true', default=True,
                         help="Salta sabato/domenica (default: attivo)")
    args = parser.parse_args()

    spot_storico = carica_spot_storico(args.prezzi) if args.prezzi else {}

    data_inizio = dt.datetime.strptime(args.da, "%Y-%m-%d").date()
    data_fine = dt.datetime.strptime(args.a, "%Y-%m-%d").date()
    if data_inizio > data_fine:
        print("[ERRORE] --da deve essere precedente o uguale a --a", file=sys.stderr)
        sys.exit(1)

    session = crea_sessione()
    giorno = data_inizio
    totale_nuovi = 0
    totale_oi_completati = 0
    giorni_saltati = []
    giorni_falliti = []

    while giorno <= data_fine:
        if args.solo_feriali and giorno.weekday() >= 5:  # 5=sabato, 6=domenica
            giorno += dt.timedelta(days=1)
            continue

        spot_del_giorno = spot_storico.get(giorno, args.spot)
        if spot_del_giorno is None:
            print(f"{giorno}: nessuno spot disponibile (ne' da --prezzi ne' da --spot), giorno saltato.")
            giorni_saltati.append(giorno)
            giorno += dt.timedelta(days=1)
            continue

        trade_date_str = giorno.strftime("%m-%d-%Y")
        try:
            html_parts = fetch_live_html_batched(
                session, expiries=args.scadenze or SCADENZE_NOTE, trade_date=trade_date_str,
                batch_size=args.batch, verbose=False
            )
            df_raw = pd.concat([parse_live_html(h) for h in html_parts], ignore_index=True)
            n_new, n_fix, _ = log_significant_volume_events_live(
                df_raw, spot_del_giorno, CONTRACT_MULTIPLIER, args.soglia, VOLUME_LOG_PATH
            )
            print(f"{giorno} (spot {spot_del_giorno:,.2f}): {n_new} nuovi eventi, {n_fix} OI completati "
                  f"({len(df_raw)} righe lette).")
            totale_nuovi += n_new
            totale_oi_completati += n_fix
        except Exception as e:
            print(f"{giorno}: [ERRORE] {e}")
            giorni_falliti.append(giorno)

        giorno += dt.timedelta(days=1)
        time.sleep(PAUSA_TRA_GIORNI_SEC)

    print(f"\n--- Riepilogo ---")
    print(f"Nuovi eventi totali: {totale_nuovi}  |  OI completati totali: {totale_oi_completati}")
    if giorni_saltati:
        print(f"Giorni saltati (nessuno spot disponibile): {giorni_saltati}")
    if giorni_falliti:
        print(f"Giorni falliti (errore nel recupero): {giorni_falliti}")


if __name__ == '__main__':
    main()
