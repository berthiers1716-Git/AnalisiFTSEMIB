#!/usr/bin/env python3
# File: ripara_file_dati.py
#
# Rigenera (sovrascrive) un file dati/YYYYMMDD.csv richiamando Euronext per
# quella data esatta, e scrivendolo nello stesso formato a blocchi/tab-separated
# che l'app e euronext_module.parse_euronext_text si aspettano. Utile quando il
# file copiato a mano era incompleto (es. senza Open Interest perche' scaricato
# troppo presto).
#
# Esempio:
#   python3 ripara_file_dati.py --data 2026-07-10 --file dati/20260710.csv
# -----------------------------------------------------------------------------

import argparse
import datetime as dt
import pandas as pd

from euronext_live_module import crea_sessione, fetch_live_html_batched, parse_live_html, SCADENZE_NOTE

MESI_ABBR = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
             7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}


def scrivi_file_dati(df_raw, filepath, trade_date):
    """
    Scrive df_raw (colonne Strike, Type, Settle, Vol, OI, Expiration Date) nel
    formato a blocchi/tab-separated compatibile con euronext_module.parse_euronext_text
    (Open/High/Low/Last/Change non sono tracciati dal fetch live: si scrivono
    come placeholder, dato che non vengono comunque usati a valle - i calcoli
    usano solo Strike/Type/Settle/Volume/Open Interest).
    """
    header_cols = "Strike\tType\tOpen\tHigh\tLow\tLast\tChange\tSettle\tVolume\tOpen Interest"
    data_str = trade_date.strftime("%-d %B %Y")  # es. "10 July 2026"

    lines = []
    for exp_date, gruppo in df_raw.groupby('Expiration Date'):
        mese_abbr = MESI_ABBR[exp_date.month]
        anno = exp_date.year
        lines.append(f"{mese_abbr} {anno} Prices - {data_str}")
        lines.append("")
        lines.append(header_cols)
        totale_volume = 0
        for row in gruppo.itertuples():
            tipo_lettera = 'C' if row.Type == 'Call' else 'P'
            oi_str = '-' if pd.isna(row.OI) else f"{row.OI:.0f}"
            settle_str = f"{row.Settle:.2f}" if pd.notna(row.Settle) else "N/A"
            vol_int = int(row.Vol)
            totale_volume += vol_int
            lines.append(
                f"{row.Strike:.0f}\t{tipo_lettera}\t0.00\t0.00\t0.00\t0.00\tN/A\t{settle_str}\t{vol_int}\t{oi_str}"
            )
        lines.append(f"\t\t\t\t\t\t\tTotal\t{totale_volume}\t-")
        lines.append("")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description="Rigenera un file dati/YYYYMMDD.csv da un fetch fresco a Euronext.")
    parser.add_argument('--data', type=str, required=True, help="Data da recuperare, formato YYYY-MM-DD")
    parser.add_argument('--file', type=str, required=True, help="Percorso del file da scrivere/sovrascrivere")
    parser.add_argument('--scadenze', nargs='*', default=None)
    parser.add_argument('--batch', type=int, default=5)
    args = parser.parse_args()

    trade_date = dt.datetime.strptime(args.data, "%Y-%m-%d").date()
    trade_date_str = trade_date.strftime("%m-%d-%Y")

    print(f"Recupero dati Euronext per il {trade_date}...")
    session = crea_sessione()
    html_parts = fetch_live_html_batched(
        session, expiries=args.scadenze or SCADENZE_NOTE, trade_date=trade_date_str,
        batch_size=args.batch, verbose=True
    )
    df_raw = pd.concat([parse_live_html(h) for h in html_parts], ignore_index=True)
    print(f"Righe lette: {len(df_raw)}")

    n_con_oi = df_raw['OI'].notna().sum()
    print(f"Righe con Open Interest presente: {n_con_oi}/{len(df_raw)}")

    scrivi_file_dati(df_raw, args.file, trade_date)
    print(f"File scritto: {args.file}")


if __name__ == '__main__':
    main()
