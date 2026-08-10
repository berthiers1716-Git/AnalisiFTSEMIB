# File: documentazione_module.py
#
# Supporto per il tab "Teoria" dell'app: impacchettamento di HTML "salvati con
# pagina completa" (con sottocartella di immagini/CSS/JS) in un unico file
# autosufficiente, e scansione delle cartelle di documentazione (Markdown, PDF,
# HTML sorgente/pronto).
# -----------------------------------------------------------------------------

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
    sorgente e ne legge il contenuto binario. Ritorna (None, None) se non esiste."""
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
    def _sostituisci(m):
        riferimento = m.group(2)
        if _e_remoto(riferimento):
            return m.group(0)
        contenuto, percorso_assoluto = _leggi_file_locale(percorso_html, riferimento)
        if contenuto is None:
            return m.group(0)
        data_uri = _a_data_uri(contenuto, percorso_assoluto)
        return f'url("{data_uri}")'
    return _RE_URL_CSS.sub(_sostituisci, css_testo)


def impacchetta_html(percorso_html_sorgente):
    """
    Impacchetta un HTML 'salvato con pagina completa' (con la sua sottocartella
    *_files di immagini/CSS/JS) in un UNICO file HTML autosufficiente, pronto per
    st.components.v1.html(...) senza bisogno di static file serving.

    - <link rel="stylesheet" href="locale.css"> -> <style>...</style> inline
      (con gli eventuali url(...) interni al CSS, se locali, convertiti in base64)
    - <script src="locale.js"></script>         -> <script>...</script> inline
    - <img src="locale.png">                    -> src sostituito con data URI
    - Risorse remote (http://, https://) lasciate invariate.
    - Risorse referenziate ma non trovate sul disco: lasciate invariate (nella
      pagina finale mancherebbe solo quella specifica risorsa).

    Ritorna la stringa HTML autosufficiente.
    """
    with open(percorso_html_sorgente, encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    n_css, n_js, n_img, n_mancanti = 0, 0, 0, 0

    for link in soup.find_all('link', rel=lambda v: v and 'stylesheet' in v):
        href = link.get('href')
        if not href or _e_remoto(href):
            continue
        contenuto, _ = _leggi_file_locale(percorso_html_sorgente, href)
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
        if img.has_attr('srcset'):
            del img['srcset']

    print(
        f"[impacchetta_html] CSS: {n_css} | JS: {n_js} | Immagini: {n_img} | "
        f"Risorse non trovate (ignorate): {n_mancanti}",
        file=sys.stderr
    )
    return str(soup)


# =============================================================================
# Scansione delle cartelle di documentazione
# =============================================================================

def elenca_markdown(cartella):
    """Ritorna i nomi dei file .md presenti in cartella (non ricorsivo)."""
    if not os.path.isdir(cartella):
        return []
    return sorted(f for f in os.listdir(cartella) if f.lower().endswith('.md'))


def elenca_pdf(cartella):
    """Ritorna i nomi dei file .pdf presenti in cartella (non ricorsivo)."""
    if not os.path.isdir(cartella):
        return []
    return sorted(f for f in os.listdir(cartella) if f.lower().endswith('.pdf'))


def elenca_html_pronti(cartella):
    """Ritorna i nomi dei file .html gia' impacchettati (autosufficienti)."""
    if not os.path.isdir(cartella):
        return []
    return sorted(f for f in os.listdir(cartella) if f.lower().endswith('.html'))


def elenca_html_sorgenti(cartella_radice):
    """
    Ogni sottocartella di cartella_radice rappresenta un documento HTML "salvato
    con pagina completa" (un file .html + eventuale sottocartella *_files
    annessa). Ritorna {nome_sottocartella: percorso_del_file_html_entry}.
    """
    risultato = {}
    if not os.path.isdir(cartella_radice):
        return risultato
    for nome in sorted(os.listdir(cartella_radice)):
        sotto = os.path.join(cartella_radice, nome)
        if not os.path.isdir(sotto):
            continue
        html_in_sotto = [f for f in os.listdir(sotto) if f.lower().endswith('.html')]
        if html_in_sotto:
            risultato[nome] = os.path.join(sotto, html_in_sotto[0])
    return risultato
