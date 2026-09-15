# File: scarica_futures_euronext.py
#
# Scarica lo snapshot del future FIB-DMIL da Euronext (Open/High/Low/Last/
# Settle/Volume/Open Interest per ciascuna scadenza quotata) e lo archivia in
# uno storico CSV persistente locale - pensato per non perdere l'OI di una
# scadenza (es. Set 2026) quando esce dalla pagina live dopo il settlement.
#
# USO:
#   python3 scarica_futures_euronext.py                        # solo oggi
#   python3 scarica_futures_euronext.py --data 2026-06-19      # un giorno storico
#   python3 scarica_futures_euronext.py --da 2026-06-19 --a 2026-09-14   # intervallo (backfill)
#
# Nell'intervallo salta automaticamente sabato/domenica; un giorno che dà
# errore (es. festivo di borsa) non blocca gli altri - viene segnalato e si
# passa al successivo.
#
# Se il parsing fallisce (l'endpoint/formato ipotizzato in
# euronext_futures_live_module.py non fosse esatto), salva la risposta grezza
# in debug_futures_raw.html e stampa le istruzioni per sistemarlo.
#
# Ultima modifica: 2026-09-14
# - Corretto un bug: trade_date non veniva passato a parse_live_html, quindi
#   Data_Scarico risultava sempre "oggi" anche scaricando un giorno storico.
# - Aggiunto il backfill su intervallo di date (--da/--a), con pausa educata
#   (ora configurabile con --pausa) tra le richieste e prosecuzione automatica
#   sui giorni che danno errore.
# - STORICO_PATH ora ancorato alla cartella dello script (non alla cartella da
#   cui lo lanci): stessa idea già applicata a guida_git.md in gestore_git.py,
#   per non ritrovarsi con più copie dei dati in posti diversi a seconda di
#   dove/come si lancia lo script.
# -----------------------------------------------------------------------------

import argparse
import os
import time
import datetime as dt

from euronext_futures_live_module import (
    crea_sessione, fetch_scadenze_disponibili, fetch_live_html,
    parse_live_html, aggiorna_storico_oi, mostra_diagnostica_grezza,
)

_CARTELLA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
STORICO_PATH = os.path.join(_CARTELLA_SCRIPT, "dati_locali", "storico_oi_future.csv")
PAUSA_DEFAULT_SEC = 5  # cortesia verso il server Euronext nei backfill multi-giorno


def scarica_un_giorno(session, scadenze, data_str):
    """data_str: 'YYYY-MM-DD', oppure None per oggi. Ritorna il DataFrame del
    giorno, o None se il parsing fallisce (con diagnostica già salvata)."""
    trade_date_euronext = None
    if data_str:
        trade_date_euronext = dt.datetime.strptime(data_str, "%Y-%m-%d").strftime("%m-%d-%Y")

    try:
        html_text = fetch_live_html(session, expiries=scadenze, trade_date=trade_date_euronext)
    except Exception as e:
        print(f"  ❌ Richiesta fallita per {data_str or 'oggi'}: {e}")
        return None

    try:
        return parse_live_html(html_text, trade_date=data_str)
    except ValueError as e:
        print(f"  ⚠️  {e}")
        print("  Salvo la risposta grezza per la diagnosi...")
        mostra_diagnostica_grezza(session, expiries=scadenze, trade_date=trade_date_euronext,
                                   percorso_output=f"debug_futures_raw_{data_str or 'oggi'}.html")
        return None


def main():
    parser = argparse.ArgumentParser(description="Scarica prezzi/OI del future FIB da Euronext.")
    parser.add_argument("--data", help="Un giorno storico singolo, formato YYYY-MM-DD")
    parser.add_argument("--da", help="Inizio intervallo per il backfill, formato YYYY-MM-DD")
    parser.add_argument("--a", help="Fine intervallo per il backfill, formato YYYY-MM-DD (default: oggi)")
    parser.add_argument("--pausa", type=float, default=PAUSA_DEFAULT_SEC,
                         help=f"Secondi di pausa tra una richiesta e l'altra nel backfill "
                              f"(default: {PAUSA_DEFAULT_SEC}; alza fino a 60 se il server sembra bloccarti)")
    args = parser.parse_args()

    print("Connessione a Euronext...")
    session = crea_sessione()
    scadenze = fetch_scadenze_disponibili(session)
    print(f"Scadenze rilevate: {scadenze}")

    if args.da:
        inizio = dt.datetime.strptime(args.da, "%Y-%m-%d").date()
        fine = dt.datetime.strptime(args.a, "%Y-%m-%d").date() if args.a else dt.date.today()
        giorni = []
        d = inizio
        while d <= fine:
            if d.weekday() < 5:  # 0-4 = lun-ven, salta sab/dom
                giorni.append(d)
            d += dt.timedelta(days=1)

        print(f"\nBackfill di {len(giorni)} giorni lavorativi, da {inizio} a {fine}...")
        totale_nuove = 0
        for i, giorno in enumerate(giorni, 1):
            data_str = giorno.strftime("%Y-%m-%d")
            print(f"[{i}/{len(giorni)}] {data_str}...")
            df = scarica_un_giorno(session, scadenze, data_str)
            if df is not None:
                n_nuove, storico = aggiorna_storico_oi(df, STORICO_PATH)
                totale_nuove += n_nuove
                print(f"  ✅ {n_nuove} righe nuove")
            if i < len(giorni):
                time.sleep(args.pausa)
        print(f"\n✅ Backfill completato: {totale_nuove} righe nuove aggiunte a '{STORICO_PATH}'.")
        return

    data_singola = args.data
    print(f"\nScarico i dati per {data_singola or 'oggi'}...")
    df = scarica_un_giorno(session, scadenze, data_singola)
    if df is None:
        return

    print("\nDati scaricati:")
    print(df.to_string(index=False))

    n_nuove, storico = aggiorna_storico_oi(df, STORICO_PATH)
    print(f"\n✅ {n_nuove} righe nuove aggiunte a '{STORICO_PATH}' "
          f"(totale storico: {len(storico)} righe).")


if __name__ == "__main__":
    main()
