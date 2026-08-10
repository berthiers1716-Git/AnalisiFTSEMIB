#!/usr/bin/env python3
"""
impacchetta_html.py — Impacchetta un HTML "salvato con pagina completa" (con la
sua sottocartella *_files di immagini/CSS/JS) in un UNICO file HTML autosufficiente,
pronto per essere mostrato dentro Streamlit con st.components.v1.html(...) senza
bisogno di static file serving.

Cosa fa:
- <link rel="stylesheet" href="locale.css">  -> sostituito con <style> ... </style>
  contenente il CSS, con gli eventuali url(...) interni che puntano a immagini
  LOCALI convertiti anch'essi in base64 (data URI).
- <script src="locale.js"></script>          -> sostituito con <script>...</script>
  contenente il JS inline.
- <img src="locale.png">                     -> src sostituito con un data URI
  base64 (image/png, image/jpeg, image/gif, image/svg+xml, ...).
- Link/risorse REMOTE (http://, https://, //cdn...) vengono lasciati invariati:
  non c'è nulla da inlineare (richiederebbero una connessione a internet comunque).
- Risorse referenziate ma NON presenti fisicamente nella cartella (tipico: icone
  decorative di plugin lightbox tipo ../images/nav_next.png) vengono lasciate
  come URL relativo invariato: nella pagina finale mancherà solo quell'icona
  decorativa, il contenuto principale (testo, immagini dell'articolo) non risente.

Uso da riga di comando:
    python3 impacchetta_html.py "sorgente.html" "destinazione.html"

Uso come funzione (es. dall'app Streamlit):
    from impacchetta_html import impacchetta_html
    html_autosufficiente = impacchetta_html("sorgente.html")
"""

import base64
import mimetypes
import os
import re
import sys

from bs4 import BeautifulSoup

_ESTENSIONI_IMMAGINE = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.svg': 'image/svg+xml', '.webp': 'image/webp',
    '.ico': 'image/x-icon', '.bmp': 'image/bmp',
}

_RE_URL_CSS = re.compile(r'url\(\s*([\'"]?)([^\'")]+)\1\s*\)')


def _e_remoto(percorso):
    return percorso.startswith(('http://', 'https://', '//', 'data:', 'mailto:'))


def _leggi_file_locale(percorso_html, riferimento):
    """Risolve un riferimento relativo (href/src) rispetto alla cartella dell'HTML
    sorgente e ne legge il contenuto binario. Ritorna None se il file non esiste."""
    riferimento_pulito = riferimento.split('#')[0].split('?')[0]
    percorso_assoluto = os.path.normpath(
        os.path.join(os.path.dirname(percorso_html), riferimento_pulito)
    )
    if os.path.isfile(percorso_assoluto):
        with open(percorso_assoluto, 'rb') as f:
            return f.read(), percorso_assoluto
    return None, None


def _a_data_uri(contenuto_bytes, percorso_file):
    _, ext = os.path.splitext(percorso_file)
    mime = _ESTENSIONI_IMMAGINE.get(ext.lower())
    if mime is None:
        mime, _ = mimetypes.guess_type(percorso_file)
        mime = mime or 'application/octet-stream'
    b64 = base64.b64encode(contenuto_bytes).decode('ascii')
    return f"data:{mime};base64,{b64}"


def _inlinea_url_dentro_css(css_testo, percorso_html):
    """Sostituisce gli url(...) locali dentro un blocco CSS con data URI, lasciando
    invariati quelli già in data: URI o quelli remoti/non risolvibili localmente."""
    def _sostituisci(m):
        riferimento = m.group(2)
        if _e_remoto(riferimento):
            return m.group(0)
        contenuto, percorso_assoluto = _leggi_file_locale(percorso_html, riferimento)
        if contenuto is None:
            # risorsa non presente (es. icona decorativa mancante): lascio invariato
            return m.group(0)
        data_uri = _a_data_uri(contenuto, percorso_assoluto)
        return f'url("{data_uri}")'
    return _RE_URL_CSS.sub(_sostituisci, css_testo)


def impacchetta_html(percorso_html_sorgente):
    """Ritorna una stringa HTML autosufficiente (immagini/CSS/JS locali inlineati)."""
    with open(percorso_html_sorgente, encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    n_css, n_js, n_img, n_mancanti = 0, 0, 0, 0

    for link in soup.find_all('link', rel=lambda v: v and 'stylesheet' in v):
        href = link.get('href')
        if not href or _e_remoto(href):
            continue
        contenuto, percorso_assoluto = _leggi_file_locale(percorso_html_sorgente, href)
        if contenuto is None:
            n_mancanti += 1
            continue
        css_testo = contenuto.decode('utf-8', errors='replace')
        css_testo = _inlinea_url_dentro_css(css_testo, percorso_html_sorgente)
        nuovo_tag = soup.new_tag('style')
        nuovo_tag.string = css_testo
        link.replace_with(nuovo_tag)
        n_css += 1

    for script in soup.find_all('script', src=True):
        src = script.get('src')
        if not src or _e_remoto(src):
            continue
        contenuto, _ = _leggi_file_locale(percorso_html_sorgente, src)
        if contenuto is None:
            n_mancanti += 1
            continue
        js_testo = contenuto.decode('utf-8', errors='replace')
        nuovo_tag = soup.new_tag('script')
        nuovo_tag.string = js_testo
        script.replace_with(nuovo_tag)
        n_js += 1

    for img in soup.find_all('img', src=True):
        src = img.get('src')
        if not src or _e_remoto(src):
            continue
        contenuto, percorso_assoluto = _leggi_file_locale(percorso_html_sorgente, src)
        if contenuto is None:
            n_mancanti += 1
            continue
        img['src'] = _a_data_uri(contenuto, percorso_assoluto)
        n_img += 1
        # anche il set srcset, se presente, va inlineato o rimosso: lo rimuovo
        # perche' punterebbe comunque a file esterni non piu' referenziabili.
        if img.has_attr('srcset'):
            del img['srcset']

    print(
        f"[impacchetta_html] CSS inlineati: {n_css} | JS inlineati: {n_js} | "
        f"Immagini inlineate: {n_img} | Risorse non trovate (ignorate): {n_mancanti}",
        file=sys.stderr
    )

    return str(soup)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Uso: python3 impacchetta_html.py <sorgente.html> <destinazione.html>")
        sys.exit(1)
    sorgente, destinazione = sys.argv[1], sys.argv[2]
    html_finale = impacchetta_html(sorgente)
    with open(destinazione, 'w', encoding='utf-8') as f:
        f.write(html_finale)
    dimensione_mb = os.path.getsize(destinazione) / (1024 * 1024)
    print(f"Scritto '{destinazione}' ({dimensione_mb:.2f} MB)")
