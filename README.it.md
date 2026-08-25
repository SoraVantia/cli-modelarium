<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/cli-modelarium-wordmark-dark.svg">
  <img alt="cli modelarium" src="docs/assets/cli-modelarium-wordmark-light.svg" width="420">
</picture>

Leggi questo in altre lingue: [English](README.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [中文](README.zh.md) | [Deutsch](README.de.md) | [Português](README.pt.md)

Nota: Questo README è tradotto per accessibilità. Lo strumento CLI Cli Modelarium stesso produce output solo in inglese. Tutti i comandi, i messaggi di errore e gli output rimangono in inglese indipendentemente dalle impostazioni locali del sistema.

> Nota: sette sezioni esistono solo nel README in inglese — *Reproducibility analysis*, *Statistical significance testing*, *Bootstrap confidence intervals*, *Paired tests for same-prompt comparisons*, *McNemar's test for hallucination significance*, *Headless Linux servers* e *More examples*. Le funzionalità sono pienamente disponibili; qui manca solo la loro documentazione. Vedere [README.md](https://github.com/SoraVantia/cli-modelarium/blob/main/README.md).

> Confronta gli output degli LLM affiancati dal tuo terminale - 11 provider cloud + modelli locali, con streaming parallelo, valutazione batch, scoring LLM-as-judge, rilevamento delle allucinazioni e asserzioni pronte per CI/CD.

[![CI](https://github.com/SoraVantia/cli-modelarium/actions/workflows/ci.yml/badge.svg)](https://github.com/SoraVantia/cli-modelarium/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cli-modelarium)](https://pypi.org/project/cli-modelarium/)
[![Downloads](https://img.shields.io/pepy/dt/cli-modelarium)](https://pepy.tech/project/cli-modelarium)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platforms-Mac%20%7C%20Windows%20%7C%20Linux-lightgrey)](#)

```bash
pip install cli-modelarium
```

<p align="center">
  <img src="docs/assets/cli-modelarium-demo.png" alt="Cli Modelarium help output showing the banner and available commands" width="520">
</p>

## Cosa fa

**Cli Modelarium** è uno strumento da riga di comando curato per confrontare gli output degli LLM tra provider, modelli, system prompt e temperature - con streaming parallelo live, valutazione batch, test deterministici e scoring di qualità integrati.

Utile per valutare quale modello si adatta al tuo compito specifico, eseguire test di regressione dei prompt in CI/CD, confrontare modelli locali con API cloud o costruire dataset di valutazione - tutto da un singolo comando del terminale.

## Requisiti di sistema

- Python 3.11 o superiore (utenti di Python 3.10: installare `cli-modelarium==0.1.1`)
- ~350 MB di spazio su disco (scipy e numpy ne costituiscono circa due terzi)
- macOS (Apple Silicon e Intel), Windows 10+ (x64 e ARM), Linux (x64 e ARM)
- Accesso a internet per la prima installazione (download del wheel da PyPI)

## Avvio rapido

```bash
pip install cli-modelarium

# Configura le chiavi API (salvate in modo sicuro nel portachiavi del tuo SO)
cli-modelarium configure

# Esegui il tuo primo confronto
cli-modelarium "Explain quantum computing in one sentence" \
  --models gpt-5.5,claude-opus-4-8,gemini-3.1-pro-preview \
  --temperatures 0,0.7
```

Ecco fatto. Si vedranno tutti e tre i modelli trasmettere le loro risposte in parallelo dal vivo, con latenza, conteggi di token e costo mostrati in una tabella di confronto pulita.

## Funzionalità

### 🤖 Provider (11 cloud + locali illimitati)

- **Provider cloud:** OpenAI, Anthropic, Google (Gemini), xAI (Grok), DeepSeek, Mistral, Groq, OpenRouter, Alibaba (DashScope), Z.AI (GLM), NVIDIA (NIM)
- **Modelli locali:** Ollama, LM Studio, vLLM, llama.cpp - qualsiasi server compatibile con OpenAI in esecuzione su localhost
- Combina modelli locali e cloud nello stesso confronto
- Scegli qualsiasi ID modello registrato per chiamata - senza limitarti alle scorciatoie di gruppo integrate

### ⚡ Streaming parallelo

- Visualizzazione live token per token su tutti i modelli contemporaneamente
- Tracciamento Time-to-First-Token (TTFT) per modello
- Vedere quale modello finisce per primo, osservare gli output divergere in tempo reale
- Streams da tutti gli 11 provider (SSE sotto il cofano)

<p align="center">
  <img src="docs/assets/cli-modelarium-comparison-demo.gif" alt="Dimostrazione di cli-modelarium nel terminale: tre modelli trasmettono le loro risposte allo stesso prompt in parallelo, poi una tabella di confronto mostra Time-to-First-Token, latenza, conteggi di token e costo per modello." width="718">
</p>

**Nota sui prezzi:** i costi mostrati nelle demo provengono da una singola esecuzione al momento della registrazione. I prezzi cambiano; verificarli con il provider prima di fare affidamento su qualsiasi cifra.

### 📊 Modalità di confronto multiple

- **Prompt singolo vs. modelli multipli** - confronti rapidi "qual è il migliore?"
- **Prompt singolo vs. temperature multiple** - vedere come la casualità influisce sull'output
- **System prompt multipli vs. un prompt utente** - test A/B di prompt engineering
- **Modalità batch** - multi-prompt × multi-modello per il vero lavoro di valutazione
- **Confronti locale vs. cloud** - quantificare il divario (o la sua assenza)

### 🧪 Funzionalità di valutazione

- **Analisi statistica di riproducibilità** - `--runs N` esegue ogni configurazione N volte e riporta media/mediana/deviazione standard/CV di latenza e token, frequenza degli output, output modale e diversità degli output. Combinalo con `--check-hallucination` per misurare il tasso di allucinazione tra le esecuzioni.
- **Asserzioni deterministiche** - 10 tipi di asserzione (`contains`, `regex`, `json_valid`, `json_schema`, `max_length_chars`, `latency_under`, `cost_under` e altri) con output pass/fail e codici di uscita CI
- **Scoring LLM-as-a-judge** - Usare un LLM per assegnare punteggi agli output di altri LLM su criteri di qualità
- **Pannelli di giudici** - Più giudici calcolano la media dei punteggi per una valutazione meno distorta
- **Preset di rilevamento allucinazioni** - Criteri pronti all'uso per il controllo dell'accuratezza fattuale
- **Criteri personalizzati** - Definire le proprie rubriche di scoring
- **Auto-skip dell'autovalutazione** - I modelli giudici vengono automaticamente saltati quando sono anche giudicati

<p align="center">
  <img src="docs/assets/cli-modelarium-runs-demo.gif" alt="Dimostrazione di cli-modelarium nel terminale: lo stesso prompt viene ripetuto più volte su due modelli, poi vengono riportati il coefficiente di variazione, gli intervalli di confidenza bootstrap e un verdetto di significatività statistica a coppie." width="1428">
</p>

### 💾 Formati di output

- **Terminal live** - Pannelli basati su Rich con barre di avanzamento e visualizzazione streaming
- **CSV** - Adatto ai fogli di calcolo (apri in Excel, Google Sheets, pandas)
- **JSON** - Strutturato per script e pipeline
- **Markdown** - Tabelle eleganti per post di blog e report
- **Codici di uscita** - 0/1/2 che riflettono lo stato pass/fail per CI/CD

### 💰 Trasparenza dei costi

- Costo per chiamata mostrato dall'utilizzo riportato da ciascun provider
- Riepilogo del costo totale per confronto
- Costo del giudice mostrato separatamente quando LLM-as-judge è abilitato
- I modelli locali vengono visualizzati come "Free"
- Flag `--max-cost` per prevenire fatture a sorpresa

### 🔒 Sicurezza

- Le chiavi API sono archiviate nel portachiavi nativo del SO tramite `keyring` (Mac Keychain, Windows Credential Manager, Linux Secret Service)
- La validazione del formato rileva errori di incollaggio prima dell'archiviazione
- La redazione dei messaggi di errore previene la fuga di chiavi nei traceback
- Validazione solo localhost per gli URL dei modelli locali
- `SECURITY.md` con politica di divulgazione responsabile

### 🛡️ Gestione dei limiti di velocità

- Limiti di concorrenza per provider (default 5) rispettano tutte le baseline di livello
- Riprova 429 automatica con backoff esponenziale
- Il 529 "overloaded" di Anthropic è gestito separatamente dai limiti di velocità
- Flag `--concurrency` per utenti avanzati su livelli superiori
- Fallimento elegante per modello (gli altri modelli continuano)
- I limiti di velocità del livello gratuito di DashScope e del modello Qwen di punta (qwen3.7-max) sono più restrittivi rispetto alla maggior parte dei provider; ridurre `--concurrency` se si incontrano errori 429

### 🌐 Multipiattaforma

- Funziona in modo identico su macOS, Windows (10+ e ARM) e Linux
- Tutti gli I/O di file usano `pathlib` + codifica UTF-8 esplicita
- La scrittura CSV usa `newline=""` per la compatibilità con Windows
- Python 3.11+ richiesto

### 📋 Esperienza dello sviluppatore

- **Binary CLI singolo** - `pip install cli-modelarium` e hai finito
- **UI curata basata su Rich** - Rifinitura del terminale di livello Claude Code
- **Output JSON** - Pipe in qualsiasi cosa (`jq`, script, monitoraggio)
- **Pronto per CI/CD** - Codici di uscita, output strutturato, esempio GitHub Actions incluso
- **Licenza Apache 2.0** - Usare in qualsiasi progetto, commerciale o meno

## Esempi

### Confronta 3 modelli su un compito di programmazione

```bash
cli-modelarium "Write a Python function to find the longest palindromic substring" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview
```

### Valutazione batch con asserzioni

Creare `eval.json`:

```json
[
  {
    "id": "math-1",
    "prompt": "What is 2 + 2?",
    "assertions": [
      {"type": "contains", "value": "4"},
      {"type": "max_length_chars", "value": 100}
    ]
  },
  {
    "id": "json-1",
    "prompt": "List 3 colors in JSON array format",
    "assertions": [
      {"type": "json_valid"}
    ]
  }
]
```

Eseguirlo:

```bash
cli-modelarium batch eval.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output results.csv
```

### Valutare gli output con un giudice LLM

```bash
cli-modelarium "Explain recursion in one paragraph" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview,local/llama-3.3-70b \
  --judge claude-opus-4-7 \
  --judge-criteria "accuracy,clarity,brevity"
```

<p align="center">
  <img src="docs/assets/cli-modelarium-judge-demo.gif" alt="Demo da terminale di cli-modelarium: un giudice LLM valuta due modelli; una tabella di confronto mostra un punteggio per modello e sotto compare il ragionamento scritto del giudice." width="848">
</p>

**Nota sulla demo:** i punteggi e i costi provengono da una singola esecuzione al momento della registrazione. I punteggi del giudice sono un segnale, non una verità assoluta, e non si riproducono esattamente tra esecuzioni o versioni del modello. I prezzi cambiano; verificarli con il provider prima di fare affidamento su qualsiasi cifra.

### Rilevare allucinazioni rispetto a fatti noti

```bash
cli-modelarium "Tell me about the Eiffel Tower" \
  --models gpt-5.5,claude-opus-4-7 \
  --judge claude-opus-4-7 \
  --check-hallucination \
  --expected-facts "Built 1887-1889,Located in Paris France,Designed by Gustave Eiffel"
```

### Confrontare un modello locale con API cloud

```bash
# Avviare prima Ollama: ollama run llama3.3
cli-modelarium "Summarize the key features of microservices architecture" \
  --models local/llama-3.3-70b,gpt-5.5,claude-opus-4-7
```

### Eseguire in CI/CD (esempio GitHub Actions)

```yaml
- name: Run LLM evaluation
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    cli-modelarium batch ./eval/test_suite.json \
      --models gpt-5.5,claude-opus-4-7 \
      --output eval_results.json \
      --min-pass-rate 0.90
```

Il comando esce con codice 1 se il tasso di superamento scende sotto il 90%, facendo fallire la build.

#### Codici di uscita

| Codice | Significato |
|--------|-------------|
| `0` | Successo. |
| `1` | Fallimento di un'asserzione - una o più asserzioni non sono state soddisfatte. Solo `batch`; `compare` non prevede asserzioni. |
| `2` | L'esecuzione non è potuta arrivare a termine. |

Il codice `2` copre diverse cause distinte e **non le distingue**: una chiave API mancante, un modello sconosciuto, un modello ritirato, un errore del provider, un tetto di spesa superato, un file batch malformato, una combinazione di flag rifiutata, un conflitto sul file di output o un limite di dimensione del batch superato.

Due regole da conoscere prima di far dipendere una pipeline da questi codici:

- **I fallimenti di chiamata prevalgono sulle asserzioni.** Se una chiamata al modello fallisce, `batch` esce con `2` senza riportare il verdetto delle asserzioni, anche quando anche queste sono fallite. Una suite rossa e una chiave API non valida appaiono identiche dal codice di uscita.
- **Un server locale irraggiungibile non è un fallimento.** `list-models --local` esce con `0` quando nessun server risponde, quindi il codice di uscita non serve a rilevarlo.

Per capire *perché* un'esecuzione è fallita, leggere il campo `error` di ciascun risultato nell'output JSON - contiene il messaggio del provider, con le stringhe simili a credenziali oscurate:

```bash
cli-modelarium batch ./eval/test_suite.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output-format json --output results.json
code=$?
if [ "$code" -eq 2 ]; then
  jq -r '.results[] | select(.error) | "\(.model): \(.error)"' results.json
fi
```

`--output-format json` è necessario: l'output predefinito non contiene alcun campo di errore leggibile da una macchina. Si noti che i fallimenti che avvengono *prima* di qualsiasi chiamata al modello (chiave mancante, modello sconosciuto, file batch errato) non producono alcun JSON; in quei casi il messaggio a console è l'unico segnale.

**Nota sulla privacy:** ogni formato di output - JSON, CSV e Markdown - include il prompt completo e la risposta completa del modello per ogni risultato, insieme a eventuali messaggi di errore del provider. JSON include inoltre il testo di ragionamento di ogni giudice; `--include-reasoning` controlla solo la visualizzazione in console, non il file, e CSV e Markdown non lo contengono. Trattare qualsiasi file di output come sensibile prima di committarlo o caricarlo come artefatto CI pubblico.

## Configurazione

### Chiavi API

Cli Modelarium archivia le chiavi API nel portachiavi nativo del tuo SO (Mac Keychain, Windows Credential Manager o Linux Secret Service tramite `keyring`). Le chiavi non toccano mai il disco in chiaro.

```bash
# Configurazione interattiva (consigliata)
cli-modelarium configure

# Oppure impostare individualmente
cli-modelarium keys set openai
cli-modelarium keys set anthropic
cli-modelarium keys set google

# Verificare quali chiavi sono configurate
cli-modelarium keys list

# Rimuovere una chiave
cli-modelarium keys delete openai
```

Si possono anche usare variabili d'ambiente (utile per CI/CD):

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
```

Le variabili d'ambiente hanno la precedenza sull'archiviazione del portachiavi.

### Modelli locali (Ollama, LM Studio, ecc.)

I modelli locali funzionano tramite endpoint compatibili con OpenAI - nessuna chiave API necessaria. Lo strumento rileva automaticamente la porta predefinita di Ollama.

```bash
# Default: presuppone Ollama su localhost:11434
cli-modelarium "test" --models local/llama-3.3

# Usare LM Studio invece
cli-modelarium "test" --models local/qwen-3-32b --local-url http://localhost:1234/v1

# Salvare un URL locale personalizzato come predefinito
cli-modelarium keys set local --base-url http://localhost:1234/v1
```

## Provider supportati

| Provider | Chiavi API Necessarie | Streaming | Tracciamento Costi |
|----------|-----------------|-----------|---------------|
| OpenAI (GPT-5, GPT-5 mini, o3, o4-mini, ecc.) | ✅ | ✅ | ✅ |
| Anthropic (Claude Opus 4.8, Sonnet 4.6, Haiku 4.5, ecc.) | ✅ | ✅ | ✅ |
| Google (Gemini 3.5 Flash, Gemini 3.1 Pro, ecc.) | ✅ | ✅ | ✅ |
| xAI (Grok 4.3, ecc.) | ✅ | ✅ | ✅ |
| DeepSeek (V4 Pro, V4 Flash, ecc.) | ✅ | ✅ | ✅ |
| Mistral (Large, Medium, Small) | ✅ | ✅ | ✅ |
| Groq (Llama 3.3, Llama 4 Scout, gpt-oss) | ✅ | ✅ | ✅ |
| OpenRouter (8 ID registrati: Qwen, DeepSeek R1, Llama 3.3, gpt-oss, GLM) | ✅ | ✅ | ✅ |
| Alibaba/DashScope (Qwen3.7 Max, Qwen3.6 Flash, Qwen3 Coder, ecc.; modelli Qwen selezionati, Internazionale/Singapore) | ✅ | ✅ | ✅ |
| Z.AI/GLM (GLM-5.2, GLM-4.7, GLM-4.5 Air, ecc.; compatibile con OpenAI, endpoint internazionale) | ✅ | ✅ | ✅ |
| NVIDIA NIM (9 ID registrati: Nemotron, Gemma 4, Mistral Nemotron, MiniMax M3, Laguna, Llama 3.1) | ✅ | ✅ | Nessuna tariffa pubblicata |
| **Locale: Ollama** | ❌ | ✅ | Gratuito |
| **Locale: LM Studio** | ❌ | ✅ | Gratuito |
| **Locale: vLLM** | ❌ | ✅ | Gratuito |
| **Locale: llama.cpp server** | ❌ | ✅ | Gratuito |

Eseguire `cli-modelarium list-models` per vedere tutti i modelli attualmente supportati.

## Gruppi di modelli

Invece di elencare gli ID dei modelli, `--models` accetta una scorciatoia di gruppo. I gruppi statici vengono espansi alla lettera: viene eseguito ogni membro elencato di seguito, quindi serve una chiave per ciascun provider coperto dal gruppo, e l'esecuzione si interrompe alla prima che manca. I gruppi dinamici `all` e `all-local` sono l'eccezione: quelli vengono risolti in base a ciò che hai effettivamente configurato.

**Gruppi statici** (composizione fissa):

| Gruppo | Modelli |
|-------|--------|
| `all-premium` / `all-flagship` | gpt-5.6-sol, claude-opus-5, gemini-3.1-pro-preview, grok-4.6, deepseek-v4-pro, mistral-large-latest, qwen3.8-max, glm-5.2 |
| `all-budget` | gpt-5.4-nano, claude-haiku-4-5, gemini-3.1-flash-lite, grok-4.20-0309-non-reasoning, deepseek-v4-flash, mistral-small-latest, qwen3.7-plus, glm-4.5-air |
| `all-reasoning` | o3, o4-mini, deepseek-v4-pro, magistral-medium-latest, magistral-small-latest, glm-5.2 |
| `all-cheap` | gpt-4o-mini, claude-haiku-4-5, gemini-2.5-flash-lite, deepseek-v4-flash, mistral-small-latest, qwen-flash, glm-4.7-flashx |
| `all-open-weight` | openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, llama-3.3-70b-versatile, meta-llama/llama-4-scout-17b-16e-instruct |

**Gruppi dinamici** (risolti a runtime):

- `all` — ogni modello cloud per cui hai una chiave API configurata (esclude i modelli locali, OpenRouter e NVIDIA: questi ultimi due sono un sottoinsieme registrato e non il catalogo completo del provider, e il costo di NVIDIA non può essere indicato). Questo può espandersi a molti modelli, quindi abbinalo a `--max-cost`.
- `all-local` — ogni modello riportato dal tuo server locale in esecuzione (Ollama / LM Studio / vLLM / llama.cpp). Se nessun server è raggiungibile, ricevi un messaggio chiaro invece di un errore.

```bash
cli-modelarium "Spiega il teorema CAP" --models all-budget
cli-modelarium "Spiega il teorema CAP" --models all --max-cost 0.50
cli-modelarium "Spiega il teorema CAP" --models all-local
```

## Come funziona

Cli Modelarium usa un livello di astrazione del provider modulare che nasconde le differenze API tra l'array `messages` di OpenAI, il parametro `system` di livello superiore di Anthropic, il `system_instruction` di Google e altri. Ogni provider implementa la stessa interfaccia di streaming asincrono, quindi la CLI può eseguirli tutti in parallelo con `asyncio.gather()`.

I calcoli dei costi provengono dal campo `usage` riportato da ciascun provider (token di input, token di output, token in cache) moltiplicato per le costanti di prezzo correnti. I dati sui prezzi sono stati verificati dalla documentazione ufficiale del provider il **29 luglio 2026** - vedere [Note e limitazioni](#note-e-limitazioni) per gli avvertimenti.

Per i modelli locali, viene usato lo stesso SDK Python OpenAI con una `base_url` personalizzata, poiché Ollama, LM Studio, vLLM e llama.cpp espongono tutti endpoint REST compatibili con OpenAI.

## Note e limitazioni

### Dati sui prezzi

La maggior parte dei prezzi integrati in Cli Modelarium è stata verificata dalla documentazione ufficiale del provider il **29 luglio 2026**. Alcune voci portano una propria data di verifica, annotata accanto a ciascuna nel registro; i prezzi Z.AI/GLM sono i più vecchi, del **22 giugno 2026**. I prezzi degli LLM cambiano frequentemente (a volte mensilmente). La data `pricing_as_of` è presente nell'output JSON e viene mostrata nella console; l'output CSV e Markdown non la include. Verificare sempre con la pagina dei prezzi ufficiale di ciascun provider prima di fare affidamento sui calcoli dei costi per il budgeting o le decisioni di produzione.

I prezzi sono la tariffa pubblica standard/di listino di ciascun provider per 1M di token (non i prezzi batch, prioritari, off-peak o promozionali); per i modelli con tariffe a livelli in base alla dimensione dell'input viene mostrato il livello iniziale/a contesto breve, e il prezzo in cache è la tariffa di lettura dalla cache. I costi di DashScope/Qwen riflettono le tariffe non-thinking (lo strumento invia `enable_thinking=false`).

NVIDIA NIM è l'eccezione. NVIDIA non pubblica alcuna tariffa per token per i suoi endpoint NIM ospitati, quindi il costo non viene tracciato per i modelli NVIDIA: lo zero mostrato nella colonna del costo è l'assenza di una tariffa, non un prezzo pari a zero. Poiché quel costo è sempre zero, `--max-cost` non scatterà mai su un modello NVIDIA e un'asserzione `cost_under` risulterà sempre superata: nessuno dei due offre alcuna protezione di spesa su questo provider. L'accesso è misurato in crediti dell'account anziché fatturato per token, quindi ciò da tenere d'occhio è l'esaurimento dei crediti, non una fattura inattesa. Un pannello di avviso viene stampato ogni volta che un modello NVIDIA fa parte di un'esecuzione.

Eseguire `cli-modelarium pricing` (o `pricing --all`) per le tariffe correnti per modello.

### Limiti di velocità

La gestione dei limiti di velocità e le impostazioni di concorrenza predefinite per provider si basano sui limiti di velocità del provider verificati il **21 giugno 2026**. I limiti del livello specifico possono differire dai default assunti qui. Verificare i limiti correnti rispetto alla dashboard ufficiale del provider prima di costruire ipotesi di capacità di produzione.

### Disponibilità del modello

I modelli supportati da Cli Modelarium riflettono ciò che i provider offrivano il **15 agosto 2026**. I provider rilasciano regolarmente nuovi modelli, depreca quelli più vecchi e ne adegua le capacità. Se un modello nel registro non funziona più, eseguire `cli-modelarium list-models` e controllare la documentazione del provider.

### Non è un gateway di produzione

Cli Modelarium è progettato per la valutazione e il confronto - eseguendo test ad-hoc affiancati tra provider da un terminale dello sviluppatore. NON è un gateway di inferenza di produzione. Se serve routing su scala di produzione, bilanciamento del carico, catene di fallback o inferenza gestita da SLA, cercare strumenti specificamente costruiti per quello scopo.

### Confronti del conteggio dei token tra provider

I conteggi dei token mostrati nei risultati sono riportati dall'API di ciascun provider. Provider diversi usano tokenizer diversi, quindi i "token di output" non sono direttamente comparabili tra provider per lo stesso testo. Se si confronta l'efficienza dei costi per l'uso in produzione, eseguire prompt reali nel proprio carico di lavoro effettivo - non fare affidamento esclusivamente sui calcoli per token tra provider.

### Utilizzo di LLM-as-a-Judge

Cli Modelarium include scoring opzionale LLM-as-a-judge (abilitato con il flag `--judge`), che usa un LLM per valutare gli output di altri LLM. Questa è una metodologia di benchmarking standard ed è consentita ai sensi dei Termini di Servizio di tutti i provider supportati come attività di valutazione/benchmarking.

Quando si usa `--judge`, l'utente è responsabile di seguire i Termini di Servizio di ciascun provider di cui usa i modelli. I ToS di ciascun provider si applicano sia ai modelli giudicati che al modello giudice stesso.

**Avviso di pregiudizio del giudice:** I giudici LLM hanno pregiudizi documentati (auto-preferenza, preferenza per la stessa famiglia, preferenza per la verbosità). I punteggi del giudice sono un segnale utile, non verità assoluta. Usare pannelli di giudici (`--judges` con modelli multipli) per ridurre i pregiudizi.

### Rilevamento delle allucinazioni

Il preset di rilevamento delle allucinazioni è un segnale di confronto utile tra modelli, non una convalida di verità assoluta. L'accuratezza del rilevamento varia in base al modello giudice utilizzato, alla conoscenza del dominio richiesta e se i fatti di riferimento sono forniti tramite `--expected-facts`. Usarlo per il confronto della qualità relativa, non per la verifica della correttezza assoluta.

### Metodologia di confronto

Gli LLM non sono deterministici a temperatura > 0 - rieseguire lo stesso prompt può produrre output diversi. Una singola esecuzione di confronto mostra UN campione da ciascun modello, non un verdetto di qualità definitivo.

Per trarre conclusioni più affidabili:
- Usare `--runs 5` (o più) per eseguire automaticamente ogni confronto N volte e vedere riepiloghi statistici: latenza media/mediana, coefficiente di variazione, output modale e diversità degli output. Un coefficiente di variazione inferiore a 0,05 indica un comportamento del modello stabile tra le esecuzioni.
- Per l'analisi della coerenza delle allucinazioni, combinare `--runs` con `--check-hallucination` per vedere con quale frequenza il modello produce allucinazioni su più esecuzioni (il tasso di allucinazione).
- Usare `--temperatures 0` per output più deterministici. Alcuni modelli non accettano alcuna impostazione di temperatura - `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `o3`, `o4-mini`, `gpt-5`, `gpt-5.5`, `gpt-5.6-sol`, `gpt-5.6-terra` e `gpt-5.6-luna`. Lo strumento omette il campo per questi modelli in modo che la chiamata vada comunque a buon fine, ed essi vengono eseguiti con il valore predefinito del provider.
- Confrontare tra più prompt, non solo uno
- Usare il flag `--output json` per salvare le esecuzioni per l'analisi sistematica (con `--runs > 1` il JSON include aggregati `stats_by_cell` per cella)

Questi dodici modelli vengono chiamati senza il campo temperatura, e `models_without_temperature` nell'output JSON indica quelli interessati da una determinata esecuzione. Vale la pena conoscere tre conseguenze. Una serie `--temperatures` con più valori invia richieste identiche anziché una vera serie su questi modelli, e lo strumento stampa un avviso quando ciò accade. La temperatura mostrata nella tabella dei risultati, nel CSV e in ogni record JSON è il valore **richiesto**, non quello applicato. E `--significance` è il punto in cui questo può cambiare una conclusione anziché un'etichetta: confrontare un modello che omette la temperatura con uno che la rispetta produce una differenza di varianza che è un artefatto di campionamento, e Welch o Mann-Whitney la riporteranno come se fosse una differenza di qualità tra modelli. Quel caso viene segnalato: qualsiasi esecuzione di significatività che mescoli un modello interessato con uno non interessato stampa un pannello `Temperature not applied` che nomina i modelli eseguiti alla temperatura predefinita del provider, e imposta `significance_temperature_mixed` su `true` nell'output JSON. Un'esecuzione con più temperature che sia anche mista riceve entrambi i messaggi in un unico pannello. Il CSV non contiene un segnale equivalente.

## Informazioni sul progetto

Cli Modelarium è un prodotto di **SoraVantia GK**. È stato creato originariamente da **Lavelle Hatcher Jr**, che continua a mantenerlo.

- 📦 Repository: [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium)
- 💬 Domande o bug: [apri una issue](../../issues)
- 🔧 Manutentore: [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

## Perché l'ho costruito

Confrontare gli output degli LLM tra provider è noioso - SDK diversi, pattern di autenticazione diversi, forme di risposta diverse, nessun modo facile per vederli affiancati con dati di costo e latenza. I rifiniti playground cloud mostrano solo un provider alla volta, e le opzioni open source disponibili o si concentrano sul routing di produzione o sono piattaforme di valutazione complete ottimizzate per i team.

Cli Modelarium è il piccolo strumento CLI focalizzato che fa una cosa bene: confronto affiancato con scoring di qualità, asserzioni, modalità batch e streaming - tutto progettato per il flusso di lavoro dello sviluppatore terminal-first.

È intenzionalmente focalizzato: nessun routing di produzione, nessuna orchestrazione di agenti, nessun fine-tuning, nessuna GUI. Solo confronto pulito e veloce dalla riga di comando.

Costruito con un'astrazione del provider modulare, esecuzione parallela, calcolo trasparente dei costi e archiviazione sicura delle chiavi tramite sistemi di portachiavi del SO per utenti locali.

## Contribuire

Issues e PR benvenuti. Vedere [CONTRIBUTING.md](CONTRIBUTING.md) per le linee guida.

Per problemi di sicurezza, vedere [SECURITY.md](SECURITY.md) - non aprire issue pubbliche per preoccupazioni di sicurezza.

## Licenza

Concesso in licenza ai sensi della [Apache License, Version 2.0](LICENSE).

Vedere il file [NOTICE](NOTICE) per i requisiti di attribuzione.

---

Un prodotto di SoraVantia GK, creato e mantenuto da [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

Concesso in licenza ai sensi di Apache 2.0. Issues, PR e conversazioni benvenuti.
