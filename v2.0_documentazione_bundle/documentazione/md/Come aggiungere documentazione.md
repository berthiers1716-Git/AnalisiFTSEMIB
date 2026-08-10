# Come aggiungere documentazione al tab Teoria

Tre tipi di risorse, in tre posti diversi:

## 📝 Markdown
Copia il file `.md` in `documentazione/md/`. Compare subito nell'elenco al
prossimo ricaricamento della pagina — nessun passaggio aggiuntivo.

## 📄 PDF
Copia il file `.pdf` in `static/pdf/`. Richiede che in `.streamlit/config.toml`
sia presente:

```toml
[server]
enableStaticServing = true
```

(già impostato in questo progetto). Il documento si apre in una nuova scheda
del browser, usando il visualizzatore PDF nativo.

## 🌐 HTML "salvato con pagina completa"
Per documenti come pagine web salvate dal browser (un file `.html` +
sottocartella `_files` con immagini/CSS/JS):

1. Crea una sottocartella in `documentazione/html_sorgente/<nome del documento>/`
2. Copiaci dentro il file `.html` e la sua sottocartella di risorse, così come
   li ha salvati il browser
3. Nel tab Teoria, sezione HTML, comparirà un bottone **"📦 Impacchetta"** —
   premilo una volta: il documento viene convertito in un unico file
   autosufficiente (immagini in base64, CSS/JS incorporati) e salvato in
   `documentazione/html_pronto/`
4. Da quel momento è disponibile istantaneamente nell'elenco, senza dover
   ripetere l'impacchettamento (a meno di modificare i file sorgente)
