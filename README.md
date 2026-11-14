# Vinted Studio

App locale per Windows: scelta cartella, riconoscimento foto tramite OpenAI, annunci modificabili, prezzi fissi per categoria, esportazione foto e dati. T-shirt **5 €**, felpe **15 €**. Il [listino completo](PREZZI.md) contiene 34 categorie modificabili: camicie 10 €, jeans e maglioni 15 €, giacche 20 €, cappotti e piumini 30 €. Sono prezzi iniziali scelti per il guardaroba, non quotazioni di mercato. Nessun dato inventato per completare campi mancanti.

## Uso quotidiano: il percorso più semplice

1. Fai doppio clic su **Avvia.bat**. Le dipendenze si installano solo al primo avvio o quando cambiano i requisiti; se l'app è già aperta si riapre la pagina esistente.
2. Al primo utilizzo incolla la chiave OpenAI API direttamente nell'app. Su Windows puoi ricordarla sul PC, cifrata con DPAPI e legata al tuo account Windows. Non occorre impostare variabili nel terminale. Su altri sistemi resta valida solo per la sessione.
3. Clicca **Aggiungi un capo**, oppure trascina tutte le foto di quel capo nell'area apposita. L'app crea la sottocartella e avvia l'analisi automaticamente: non devi ordinare o rinominare i file.
4. Le schede mostrano subito solo i campi mancanti. I dati completi rimangono sotto **Vedi o modifica tutti i dati**. Le modifiche si salvano automaticamente dopo una breve pausa; **Salva ora** resta disponibile come alternativa.
5. Premi **Scarica tutti i pronti** per ricevere un solo ZIP con foto e testi di ogni annuncio completo. Il comando non pubblica gli annunci sul sito.

In **Impostazioni → Valori che usi spesso** puoi indicare taglia, marca, materiale, pacco e stato ricorrenti. Sono facoltativi, si applicano esclusivamente ai campi vuoti di annunci nuovi ed esistenti e non sostituiscono valori già presenti. Usa uno stato predefinito soltanto dopo aver verificato fisicamente che sia corretto per quei capi. Il prezzo rimane quello del listino.

Hai già una cartella organizzata? **Usa una cartella esistente** la collega, salva la scelta, abilita il controllo automatico e avvia l'analisi con una sola selezione. Le foto già raggruppate richiedono una sottocartella per capo; le foto nella radice sono considerate capi singoli. La scansione richiede che le foto siano state copiate completamente. L'app deve rimanere aperta.

## Avvio da terminale (facoltativo)

Richiede Python 3.12+. Da PowerShell nella cartella progetto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:OPENAI_API_KEY = 'la-tua-chiave'
python app.py
```

Si apre http://127.0.0.1:8765. La variabile API è facoltativa se inserisci la chiave nell'interfaccia. La chiave salvata su Windows è in `data/api-key.dpapi`, esclusa da Git, e non viene mai restituita dalle API dell'app al browser. Per sostituirla usa **Impostazioni → Avanzate → Cambia chiave API**; deselezionando il salvataggio viene rimossa anche l'eventuale chiave precedentemente ricordata. Le chiamate API hanno un costo e le foto vengono inviate a OpenAI. Senza chiave è possibile aggiungere foto e configurare l'app, ma non analizzare nuovi capi.

Per ogni aggiunta seleziona esclusivamente foto dello stesso capo, da 1 a 20 immagini JPG/PNG/WEBP e massimo 20 MB complessivi. L'app non raggruppa automaticamente foto di capi diversi per somiglianza. L'esportazione singola rimane disponibile in `data/exports/<id>/`. Nel download ZIP i riferimenti alle foto sono relativi, senza percorsi personali del PC.

Il prezzo è la voce esatta della tabella `pricing.base`, senza maggiorazioni; per cambiare i prezzi usa i campi della tabella nelle impostazioni. Il JSON avanzato consente di modificare anche il motore a formula. Categoria non riconosciuta: usa `altro` e verifica. Puoi attivare il motore alternativo con `mode: "formula"`: base categoria o prezzo originale × retail_ratio, moltiplicatori stato e marca, margine trattativa, arrotondamento e limiti. Il prezzo originale si inserisce manualmente. Le preferenze e il percorso personale della cartella vengono salvati in `data/settings.json`, escluso da Git; `config.json` rimane il modello pubblico. Salvare le preferenze ricalcola i prezzi di tutti gli annunci modificabili, senza toccare quelli pubblicati o con invio da verificare.

## Integrazione browser: da completare sul sito reale

**La pubblicazione automatica sul tuo account non è ancora configurata né collaudata.** È presente un adapter Playwright che richiede una sessione utente e selettori verificati sulla versione corrente di Vinted. Non usa API private né aggira CAPTCHA. L'utilizzo di strumenti esterni va verificato rispetto ai termini Vinted e alle autorizzazioni del tuo account: https://www.vinted.it/terms_and_conditions.

```powershell
python -m playwright install chromium
python publisher.py --login
```

Il login si effettua nel browser, senza fornire password all'app. La sessione è conservata in `browser-profile/`: proteggi questa cartella.

Copia `vinted-selectors.example.json` in `vinted-selectors.json` e configura tutti i selettori reali. L'adapter supporta campi testuali (`fill`), select HTML (`select`) e menu personalizzati (`click_option`, con traduzioni tramite `values`). Categorie gerarchiche e menu complessi possono richiedere di estendere l'adapter; il template non garantisce la compatibilità con il sito corrente.

```powershell
python publisher.py ID_ANNUNCIO
python publisher.py ID_ANNUNCIO --publish
```

Il primo comando compila e lascia il controllo all'utente. Il secondo invia solo se sono configurati anche `publish` e `success`. Non c'è un invio automatico in background dei nuovi capi. Un timeout dopo l'invio lascia lo stato `publishing`: verifica il tuo profilo prima di qualsiasi nuovo tentativo. Nessun retry automatico della pubblicazione. Un lock blocca publisher concorrenti e modifiche dall'editor durante la compilazione. Se il processo termina bruscamente, il lock può rimanere: verifica il profilo Vinted e lo stato degli annunci prima di rimuovere `data/publisher.lock`. Evita scansioni durante la pubblicazione.

## Verifiche

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m coverage run -m unittest discover -v
python -m coverage report -m
python -m ruff check .
python -m pip_audit -r requirements.txt
```

La suite include prezzi di tutte le categorie, validazione dati, raggruppamento e deduplicazione, richieste HTTP, salvataggio, esportazione, protezioni locali, protocollo immagini AI e stati del publisher. Chromium verifica il flusso completo su desktop e mobile. Le chiamate AI e il sito Vinted sono simulati nei test: nessun costo API e nessun annuncio reale. GitHub Actions esegue i controlli su Windows e Linux.

Dettagli e limiti: [VALIDAZIONE.md](VALIDAZIONE.md).

Analisi reale e pubblicazione richiedono rispettivamente chiave API e account, non inclusi nel progetto. L'app ascolta solo su localhost; non esporla su Internet. I dati locali non sono cifrati. Non eliminare gli ID archiviati se vuoi conservare la deduplicazione. Foto, dati, impostazioni personali, chiavi e profili browser sono esclusi dalla repository.

Documentazione visione: https://developers.openai.com/api/docs/guides/images-vision.
