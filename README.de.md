<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/cli-modelarium-wordmark-dark.svg">
  <img alt="cli modelarium" src="docs/assets/cli-modelarium-wordmark-light.svg" width="420">
</picture>

Lesen Sie dies in anderen Sprachen: [English](README.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [中文](README.zh.md) | [Português](README.pt.md) | [Italiano](README.it.md)

Hinweis: Diese README ist aus Gründen der Zugänglichkeit übersetzt. Das Cli Modelarium CLI-Tool selbst gibt nur Englisch aus. Alle Befehle, Fehlermeldungen und Ausgaben bleiben unabhängig von Ihrer System-Locale auf Englisch.

> Hinweis: Sieben Abschnitte gibt es bisher nur im englischen README — *Reproducibility analysis*, *Statistical significance testing*, *Bootstrap confidence intervals*, *Paired tests for same-prompt comparisons*, *McNemar's test for hallucination significance*, *Headless Linux servers* und *More examples*. Die Funktionen selbst sind vollständig verfügbar; nur ihre Dokumentation fehlt hier. Siehe [README.md](https://github.com/SoraVantia/cli-modelarium/blob/main/README.md).

> Vergleichen Sie LLM-Ausgaben nebeneinander von Ihrem Terminal aus - 12 Cloud-Anbieter + lokale Modelle, mit parallelem Streaming, Batch-Evaluierung, LLM-as-Judge-Scoring, Halluzinationserkennung und CI/CD-fähigen Assertions.

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

## Was es tut

**Cli Modelarium** ist ein ausgereiftes Kommandozeilen-Tool zum Vergleichen von LLM-Ausgaben über Anbieter, Modelle, System-Prompts und Temperaturen hinweg - mit eingebautem Live-Parallel-Streaming, Batch-Evaluierung, deterministischen Tests und Qualitäts-Scoring.

Nützlich, um zu bewerten, welches Modell zu Ihrer spezifischen Aufgabe passt, Prompt-Regressionstests in CI/CD auszuführen, lokale Modelle mit Cloud-APIs zu vergleichen oder Evaluierungs-Datasets zu erstellen - alles aus einem einzigen Terminal-Befehl.

## Systemanforderungen

- Python 3.11 oder höher (Nutzer von Python 3.10: installieren Sie `cli-modelarium==0.1.1`)
- ~350 MB Speicherplatz (scipy und numpy machen etwa zwei Drittel davon aus)
- macOS (Apple Silicon und Intel), Windows 10+ (x64 und ARM), Linux (x64 und ARM)
- Internetzugang für die Erstinstallation (Download des PyPI-Wheels)

## Schnellstart

```bash
pip install cli-modelarium

# API-Schlüssel konfigurieren (sicher im OS-Keychain gespeichert)
cli-modelarium configure

# Führen Sie Ihren ersten Vergleich aus
cli-modelarium "Explain quantum computing in one sentence" \
  --models gpt-5.5,claude-opus-4-8,gemini-3.1-pro-preview
```

Das ist alles. Sie sehen alle drei Modelle ihre Antworten parallel live streamen, mit Latenz, Token-Anzahl und Kosten, die in einer übersichtlichen Vergleichstabelle angezeigt werden.

## Funktionen

### 🤖 Anbieter (12 Cloud + unbegrenzt lokal)

- **Cloud-Anbieter:** OpenAI, Anthropic, Google (Gemini), xAI (Grok), DeepSeek, Mistral, Groq, OpenRouter, Alibaba (DashScope), Z.AI (GLM), NVIDIA (NIM), Moonshot AI (Kimi)
- **Lokale Modelle:** Ollama, LM Studio, vLLM, llama.cpp - jeder OpenAI-kompatible Server, der auf localhost läuft
- Mischen Sie lokale und Cloud-Modelle im selben Vergleich
- Wählen Sie pro Aufruf eine beliebige registrierte Modell-ID - nicht auf die integrierten Gruppen-Kürzel beschränkt

### ⚡ Paralleles Streaming

- Live-Anzeige Token für Token über alle Modelle gleichzeitig
- Time-to-First-Token (TTFT)-Tracking pro Modell
- Sehen Sie, welches Modell zuerst fertig ist, beobachten Sie Ausgaben in Echtzeit divergieren
- Streams von allen 12 Anbietern (SSE im Hintergrund)

<p align="center">
  <img src="docs/assets/cli-modelarium-comparison-demo.gif" alt="Terminal-Demo von cli-modelarium: Drei Modelle streamen ihre Antworten auf denselben Prompt parallel, anschließend zeigt eine Vergleichstabelle Time-to-First-Token, Latenz, Token-Anzahl und Kosten pro Modell." width="718">
</p>

**Preishinweis:** Die Kostenangaben in Demos stammen aus einem einzelnen Lauf zum Aufnahmezeitpunkt. Preise ändern sich; überprüfen Sie sie beim Anbieter, bevor Sie sich auf eine Angabe verlassen.

### 📊 Mehrere Vergleichsmodi

- **Einzelner Prompt vs. mehrere Modelle** - schnelle "welches ist am besten?"-Vergleiche
- **Einzelner Prompt vs. mehrere Temperaturen** - sehen Sie, wie Zufälligkeit die Ausgabe beeinflusst
- **Mehrere System-Prompts vs. ein User-Prompt** - A/B-Test von Prompt-Engineering
- **Batch-Modus** - Multi-Prompt × Multi-Modell für echte Evaluierungsarbeit
- **Lokale vs. Cloud-Vergleiche** - quantifizieren Sie die Lücke (oder deren Fehlen)

### 🧪 Evaluierungsfunktionen

- **Statistische Reproduzierbarkeitsanalyse** - `--runs N` führt jede Konfiguration N-mal aus und meldet Mittelwert/Standardabweichung/VK von Latenz und Tokens, Ausgabehäufigkeit, Modalausgabe und Ausgabediversität. Kombinieren Sie es mit `--check-hallucination`, um die Halluzinationsrate über mehrere Läufe zu messen.
- **Deterministische Assertions** - 10 Assertion-Typen (`contains`, `regex`, `json_valid`, `json_schema`, `max_length_chars`, `latency_under`, `cost_under` und mehr) mit Pass/Fail-Ausgabe und CI-Exit-Codes
- **LLM-as-a-Judge-Scoring** - Verwenden Sie ein LLM, um Ausgaben anderer nach Qualitätskriterien zu bewerten
- **Judge-Panels** - Mehrere Judges mitteln Punktzahlen für eine weniger voreingenommene Bewertung
- **Halluzinationserkennungs-Preset** - Sofort einsatzbereite Kriterien für die Überprüfung der sachlichen Genauigkeit
- **Benutzerdefinierte Kriterien** - Definieren Sie Ihre eigenen Bewertungsrubriken
- **Auto-Skip bei Selbstbewertung** - Judge-Modelle werden automatisch übersprungen, wenn sie auch bewertet werden

<p align="center">
  <img src="docs/assets/cli-modelarium-runs-demo.gif" alt="Terminal-Demo von cli-modelarium: derselbe Prompt wird mehrfach über zwei Modelle wiederholt, anschließend werden Variationskoeffizient, Bootstrap-Konfidenzintervalle und ein paarweises statistisches Signifikanzurteil ausgegeben." width="1428">
</p>

### 💾 Ausgabeformate

- **Live-Terminal** - Rich-basierte Panels mit Fortschrittsbalken und Streaming-Anzeige
- **CSV** - Tabellenkalkulationsfreundlich (in Excel, Google Sheets, pandas öffnen) **Die Kopfzeile ist der Vertrag, nicht die Spaltenposition.** Spalten werden angehängt, wenn das Werkzeug wächst - lesen Sie nach Namen.
- **JSON** - Strukturiert für Skripte und Pipelines
- **Markdown** - Schöne Tabellen für Blogbeiträge und Berichte
- **Exit-Codes** - 0/1/2/3 reflektieren Pass/Fail-Status für CI/CD

### 💰 Kostentransparenz

- Kosten pro Aufruf basierend auf der von jedem Anbieter gemeldeten Nutzung
- Gesamtkostenübersicht pro Vergleich
- Judge-Kosten separat angezeigt, wenn LLM-as-Judge aktiviert ist
- Lokale Modelle werden als "Free" angezeigt
- `--max-cost`-Flag, das nach Überschreiten der Grenze keine neuen Aufrufe mehr startet (bereits laufende Aufrufe werden zu Ende geführt, es begrenzt also einen Lauf und verhindert keine Rechnung)

### 🔒 Sicherheit

- API-Schlüssel werden über `keyring` im OS-nativen Keychain gespeichert (Mac Keychain, Windows Credential Manager, Linux Secret Service)
- Format-Validierung fängt Einfügefehler vor der Speicherung ab
- Redaktion von Fehlermeldungen verhindert Schlüssellecks in Tracebacks
- Localhost-only-Validierung für lokale Modell-URLs
- `SECURITY.md` mit Responsible-Disclosure-Richtlinie

### 🛡️ Rate-Limit-Handhabung

- Concurrency-Limits pro Anbieter (Standard 5) - ein Wert für alle Anbieter, prüfen Sie ihn gegen Ihre eigene Tier
- Automatischer 429-Retry mit exponentiellem Backoff
- Anthropics 529 "overloaded" wird separat von Rate-Limits behandelt
- `--concurrency`-Flag für Power-User in höheren Tiers
- Graceful Fehlerbehandlung pro Modell (andere Modelle laufen weiter)
- Die Rate-Limits des DashScope-Free-Tiers und des Flaggschiff-Qwen (qwen3.7-max) sind strenger als bei den meisten Anbietern; verringern Sie `--concurrency`, falls Sie auf 429 stoßen.
- Moonshot erfordert vor jeder Nutzung eine Mindestaufladung von 1 $ - es gibt keinen kostenlosen Tarif. Tier0 sind 1 gleichzeitige Anfrage, 3 Anfragen pro Minute und 1,5 Mio. Tokens pro Tag; ab 10 $ kumulierter Aufladung gilt Tier1. Senken Sie `--concurrency` in Tier0.

### 🌐 Plattformübergreifend

- Funktioniert identisch auf macOS, Windows (10+ und ARM) und Linux
- Alle Datei-I/O verwenden `pathlib` + explizite UTF-8-Codierung
- CSV-Schreiben verwendet `newline=""` für Windows-Kompatibilität
- Python 3.11+ erforderlich

### 📋 Entwicklererfahrung

- **Einzelne CLI-Binary** - `pip install cli-modelarium` und fertig
- **Ausgereifte Rich-basierte UI** - Terminal-Politur auf Claude-Code-Niveau
- **JSON-Ausgabe** - In alles pipen (`jq`, Skripte, Monitoring)
- **CI/CD-bereit** - Exit-Codes, strukturierte Ausgabe, GitHub-Actions-Beispiel enthalten
- **Apache-2.0-lizenziert** - Verwendung in jedem Projekt, kommerziell oder anderweitig

## Beispiele

### Vergleichen Sie 3 Modelle bei einer Coding-Aufgabe

```bash
cli-modelarium "Write a Python function to find the longest palindromic substring" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview
```

### Batch-Evaluierung mit Assertions

Erstellen Sie `eval.json`:

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

Führen Sie es aus:

```bash
cli-modelarium batch eval.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output results.csv
```

### Bewerten Sie Ausgaben mit einem LLM-Judge

```bash
cli-modelarium "Explain recursion in one paragraph" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview,local/llama-3.3-70b \
  --judge claude-opus-4-7 \
  --judge-criteria "accuracy,clarity,brevity"
```

<p align="center">
  <img src="docs/assets/cli-modelarium-judge-demo.gif" alt="Terminal-Demo von cli-modelarium: Zwei Modelle werden von einem LLM-Judge bewertet; eine Vergleichstabelle zeigt eine Punktzahl pro Modell, darunter erscheint die schriftliche Begründung des Judges." width="848">
</p>

**Demo-Hinweis:** Punktzahlen und Kostenangaben stammen aus einem einzelnen Lauf zum Aufnahmezeitpunkt. Judge-Punktzahlen sind ein Signal, keine Grundwahrheit, und reproduzieren sich weder über Läufe noch über Modellversionen exakt. Preise ändern sich; überprüfen Sie sie beim Anbieter, bevor Sie sich auf eine Angabe verlassen.

### Halluzinationen gegen bekannte Fakten erkennen

```bash
cli-modelarium "Tell me about the Eiffel Tower" \
  --models gpt-5.5,claude-opus-4-7 \
  --judge claude-opus-4-7 \
  --check-hallucination \
  --expected-facts "Built 1887-1889,Located in Paris France,Designed by Gustave Eiffel"
```

### Lokales Modell mit Cloud-APIs vergleichen

```bash
# Ollama zuerst starten: ollama run llama3.3
cli-modelarium "Summarize the key features of microservices architecture" \
  --models local/llama-3.3-70b,gpt-5.5,claude-opus-4-7
```

### In CI/CD ausführen (GitHub Actions-Beispiel)

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

Der Befehl beendet mit Code 1, wenn die Pass-Rate unter 90% fällt, wodurch der Build fehlschlägt.

#### Exit-Codes

| Code | Bedeutung |
|------|-----------|
| `0` | Erfolg. |
| `1` | Assertion-Fehler - eine oder mehrere Assertions sind fehlgeschlagen, ein `batch`-Lauf hat nichts geprüft, oder ein Modell hat abgelehnt und konfigurierte Assertions unausgewertet gelassen. Nur `batch` liefert ein Assertion-Urteil; `compare` kann bei einem unerwarteten Fehler dennoch mit `1` enden. |
| `2` | Der Lauf konnte nicht abgeschlossen werden. |
| `3` | `--max-cost` hat den Lauf gestoppt. Bereits gestartete Aufrufe durften beendet werden, daher enthält die gespeicherte Ausgabe das Gemessene und markiert die nie ausgeführten Aufrufe. Die Obergrenze begrenzt weitere Aufrufe, nicht bereits entstandene Kosten. |
| `4` | `diff` hat einen Unterschied gefunden. Ein eigener Code, weil jeder andere Code ungleich null bedeutet, dass etwas schiefging, ein `diff` mit gemeldeter Bewegung aber erfolgreich war. Nur `diff` erzeugt ihn. |

Code `2` deckt mehrere verschiedene Ursachen ab und **unterscheidet nicht zwischen ihnen**: ein fehlender API-Schlüssel, ein unbekanntes Modell, ein eingestelltes Modell, ein Provider-Fehler, ein überschrittenes Kostenlimit, eine fehlerhafte Batch-Datei, eine abgelehnte Flag-Kombination, ein Konflikt bei der Ausgabedatei oder ein überschrittenes Batch-Größenlimit.

Drei Regeln sollten Sie kennen, bevor Sie eine Pipeline darauf aufbauen:

- **Aufruffehler haben Vorrang vor Assertions.** Schlägt ein Modellaufruf fehl, beendet `batch` mit `2`, ohne ein Assertion-Ergebnis zu melden - selbst wenn auch Assertions fehlgeschlagen sind. Eine rote Suite und ein ungültiger API-Schlüssel sehen am Exit-Code gleich aus.
- **Ein nicht erreichbarer lokaler Server ist kein Fehler.** `list-models --local` beendet mit `0`, wenn kein Server antwortet; der Exit-Code eignet sich also nicht zur Erkennung.
- **Eine Ablehnung lässt das Gate scheitern, unabhängig von der Erfolgsquote.** Eine abgelehnte Anfrage liefert keine Ausgabe, gegen die geprüft werden könnte; ihre Assertions werden daher als fehlerhaft erfasst und aus der Erfolgsquote ausgeschlossen - die Quote darüber beschreibt also nur die beantworteten Anfragen. `batch` endet mit `1`, sobald eine Ablehnung konfigurierte Assertions unausgewertet gelassen hat, selbst bei einer Quote von 100 %. Wie viele, meldet die JSON-Ausgabe unter `total_assertions_refused`.

Um herauszufinden, *warum* ein Lauf fehlgeschlagen ist, lesen Sie das Feld `error` jedes Ergebnisses aus der JSON-Ausgabe - es enthält die Meldung des Providers, wobei zugangsdatenähnliche Zeichenketten redigiert werden:

```bash
cli-modelarium batch ./eval/test_suite.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output-format json --output results.json
code=$?
if [ "$code" -eq 2 ]; then
  jq -r '.results[] | select(.error) | "\(.model): \(.error)"' results.json
fi
```

Eine Ablehnung ist kein Fehler - `error` bleibt bei einer abgelehnten Anfrage `null`, damit deren Kosten in allen Summen erhalten bleiben, und gemeldet wird sie über Exit-Code `1` statt `2`. `select(.error)` liefert daher nichts für den Lauf, den eine Ablehnung rot gemacht hat. Um beides abzudecken:

```bash
jq -r '.results[] | select(.error or .refused)
       | "\(.model): \(.error // "refused: " + (.stop_category // "no category"))"' results.json
```

`--output-format json` ist erforderlich - die Standardausgabe enthält kein maschinenlesbares Fehlerfeld. Beachten Sie: Fehler, die *vor* dem ersten Modellaufruf auftreten (fehlender Schlüssel, unbekanntes Modell, fehlerhafte Batch-Datei), erzeugen überhaupt kein JSON; dort ist die Konsolenmeldung das einzige Signal.

#### Run-Identität

Jede JSON-Ausgabe enthält vier Felder auf oberster Ebene, die sagen, *welcher Lauf* sie ist. Vor diesem Release war das nicht möglich: Zwei Läufe desselben Befehls erzeugten JSON, das sich in `latency_ms` und `ttft_ms` unterschied und sonst in nichts. Eine Messung gegen das veröffentlichte 0.1.9 erfasste genau dieses Paar im Abstand von 93 Sekunden, und der zweite Lauf war der schnellere - selbst "höhere Latenz lief früher" hätte die beiden also falsch herum geordnet. Als einziges Signal blieb die Dateisystem-mtime, und die überlebt weder `git add` noch eine Kopie, ein tar-Extrakt oder einen Artefakt-Upload.

| Feld | Was es ist |
|------|------------|
| `started_at` | Wann der Lauf begann - ISO 8601 UTC, Sekundengenauigkeit, `Z`-Suffix. Erfasst vor der Flag-Auflösung und vor jedem Provider-Aufruf, also eine Start- und keine Endzeit. |
| `run_id` | Eine UUID, die diesen Lauf identifiziert. Sie überlebt Kopieren und Umbenennen und trennt zwei Läufe, die in derselben Sekunde begannen. |
| `experiment_key` | Sechzehn Hex-Zeichen eines SHA-256 über die Eingaben, die das Experiment definieren. Zwei Ausgaben mit demselben Schlüssel messen dasselbe. |
| `invocation` | Die aufgelösten Flags: Befehlsname, Modellliste, Temperaturen, System-Prompts und Judge-Modelle. |

Alle vier kommen gleichermaßen aus `compare` und `batch`, bedingungslos. Markdown führt zusätzlich `Started at` und `Run ID`; CSV führt keines davon, denn Identität ist lauf-, CSV aber zeilenbezogen.

```bash
# Sind zwei Ausgaben überhaupt vergleichbar?
[ "$(jq -r .experiment_key before.json)" = "$(jq -r .experiment_key after.json)" ] \
  && echo "gleiches Experiment" || echo "anderes Experiment - nicht vergleichen"
```

`started_at` nutzt Sekunden und `Z` statt Mikrosekunden und `+00:00`, weil jq's `fromdateiso8601` - das Erste, wonach ein Shell-Monitor greift - beide anderen Schreibweisen ablehnt.

**`invocation` hält fest, was lief, nicht was Sie getippt haben.** Ein mit `--models all-flagship` gestarteter Lauf listet die IDs auf, zu denen diese Gruppe expandierte - genau das braucht ein Konsument: Gruppenzugehörigkeit ist Registry-Zustand und ändert sich zwischen Releases, der Name allein würde also niemandem erlauben, den Lauf zu reproduzieren.

**Nichts Geheimes kann `invocation` erreichen, und das ist eine Positivliste und keine Redaktions-Passage.** Das Feld wird aus vier benannten Schlüsseln gebaut, also kommt nichts hinein, was dort nicht genannt ist. `--local-url` ist ausgeschlossen, weil es Zugangsdaten in der Userinfo-Position tragen kann (`http://user:pass@host/v1`) - eine Form, bei der man keinem Mustervergleich trauen kann. Dateipfade sind ausgeschlossen, weil ein Pfad ein Home-Verzeichnis und einen Benutzernamen preisgibt, während der Inhalt, auf den es ankommt, ohnehin aufgezeichnet wird. Das Feld aus einer festen Liste zu bauen ist die stärkere Zusage: Eine Redaktions-Passage müsste jedes Geheimnis erkennen, das man ihr zeigt, und diese hier bekommt keines zu sehen.

**Was `experiment_key` hasht:** den aufgelösten Befehlsnamen, die Prompts, die Modellliste, die Temperaturen, die aufgelösten System-Prompts, die Judge-Modelle und die Anzahl der Durchläufe. Gemessene Werte sind konstruktionsbedingt ausgeschlossen - Latenz, Kosten und Token-Zahlen sind die Ausgaben, die verglichen werden, und ein Schlüssel, der sich mit ihnen bewegte, würde nie übereinstimmen. Ebenso das Ausgabeziel, denn `--output report.json` und nach stdout geleitetes `--output-format json` sind dasselbe Experiment, zweimal geschrieben. Die Eingaben sind hier und an der Konstante selbst dokumentiert, weil ein Hash mit unbekannten Eingaben schlechter ist als gar keiner: Zwei Schlüssel, die sich unterscheiden, sagen einem Konsumenten nichts, solange er nicht weiß, ob sich das Experiment geändert hat oder das Hashing. `EXPERIMENT_KEY_VERSION` existiert aus demselben Grund und wird erhöht, wenn sich die Hash-Eingaben ändern - nie für eine kosmetische Änderung.

**Die Anzahl der Durchläufe steckt im Schlüssel.** `--runs 1` und `--runs 10` über dieselben Zellen teilen sich keinen, und zwar absichtlich: Der zweite beantwortet eine Frage nach der Varianz, die der erste nicht beantworten kann, ein Monitor, der beide zusammenwirft, vergliche also eine Punktschätzung mit einer Verteilung.

**Die Modellliste wird bewusst nicht sortiert.** Sortieren ließe `--models a,b` und `--models b,a` denselben Schlüssel teilen, was sich damit begründen ließe, dass dieselben Zellen gemessen werden - aber `prompt_id` ist in `compare` eine positionsbasierte Zeilennummer, also ist `p1` in diesen beiden Läufen ein anderes Modell. Ein Konsument, der sie über `(experiment_key, prompt_id)` verbindet, brächte jede Zeile aus der Reihe, während beide Schlüssel übereinstimmten. Ein falsches "unterschiedlich" kostet einen ausgelassenen Vergleich; ein falsches "gleich" verdirbt stillschweigend einen. Die Temperaturliste behält die angegebene Reihenfolge aus demselben Grund.

**Ein identischer `experiment_key` bedeutet nicht identische Ergebnisse.** Live gemessen an `gemini-3.8-flash`: Zwei Aufrufe, die in allem identisch waren, was der Schlüssel sehen kann, lieferten denselben Ausgabetext - beide Male `Paris` - mit 65 und dann 58 Output-Tokens, zu Kosten von `$0.00025125` und dann `$0.000225`. Über die acht Läufe, die ein Ergebnis lieferten, spannte `output_tokens` 58 bis 66 bei konstant 10 Input-Tokens, weil die internen Tokens eines Thinking-Modells von Aufruf zu Aufruf schwanken. Diese acht sind der gesamte Durchlauf und keine Auswahl daraus: Am 2026-09-06 liefen vierzehn Versuche, und sechs kamen mit 503 zurück - tote Zellen mit null Tokens, aus denen sich keine Spanne bilden lässt. Dass Kosten sich zwischen zwei Läufen desselben Experiments bewegen, ist daher normal und kein Beleg dafür, dass sich etwas geändert hätte. Das spricht *für* den Schlüssel und nicht gegen ihn: Zwei Läufe, die sich in den Kosten unterscheiden, lassen sich immer noch als dasselbe Experiment erkennen - und das braucht man, bevor man fragen kann, ob der Unterschied etwas bedeutet.

#### Zwei Läufe vergleichen

`diff` liest zwei JSON-Ausgaben, die Sie bereits haben, und meldet, was sich bewegt hat. Es schreibt nichts, speichert nichts und überwacht nichts.

```bash
cli-modelarium compare "capital of France?" --models gpt-5.5,claude-opus-4-8 --output before.json
# ... später ...
cli-modelarium compare "capital of France?" --models gpt-5.5,claude-opus-4-8 --output after.json

cli-modelarium diff before.json after.json
```

<p align="center">
  <img src="docs/assets/cli-modelarium-diff-demo-4model.gif" alt="Terminal-Demo von cli-modelarium: derselbe Vergleich wird zweimal über claude-fable-5-1, gemini-3.8-flash, gemini-3.7-flash und claude-haiku-4-5 ausgeführt, dann meldet diff für jede Antwort unveränderten Text, während die Kosten bei den beiden Gemini-Zeilen schwanken und bei den beiden Claude-Zeilen konstant bleiben." width="1088">
</p>

**Die Argumentreihenfolge bestimmt die Richtung.** Die erste Datei gilt als der frühere Lauf, was auch immer die Zeitstempel sagen. Nichts in einer Ausgabe kann zwei Läufe aus derselben Sekunde ordnen - `started_at` hat Sekundengenauigkeit und `run_id` ist eine zufällige UUID ohne Zeitanteil - also ist die immer verfügbare Regel die, die Sie getippt haben. Widerspricht `started_at`, sagt `diff` das und macht weiter.

Verglichen werden Zellen, nicht Dateien. Zwei Zeilen können Modell, Temperatur und System-Prompt teilen, denn `--temperatures 0,0` fordert dieselbe Zelle zweimal an; der Join zählt daher zusätzlich die Position jeder Zeile innerhalb ihrer eigenen Zellgruppe. Unveränderte Zellen werden ausgeblendet, `--all` zeigt sie.

**Jede angezeigte Zelle meldet vor ihren Zahlen, ob sich der Antworttext geändert hat.** Ein Thinking-Modell liefert routinemäßig denselben Text bei anderen Token-Kosten, also ist "die Kosten haben sich bewegt, die Antwort nicht" die normale Lesart - und eine geänderte Antwort bei gleicher Token-Zahl hätte sonst nichts bewegt und wäre ausgeblendet worden. Es gilt gleich oder nicht gleich, nie ein Ähnlichkeitswert: ein Prozentsatz dort wäre eine Zahl, die die Ausgabe nicht enthält. Hat eine Seite abgelehnt, einen Fehler gehabt oder wurde sie gestoppt, gibt es keine Antwort zu vergleichen, und das Kommando sagt genau das.

**Was abgelehnt wird:** ein geänderter Prompt, eine geänderte Anzahl Durchläufe (ein Lauf ist eine Punktschätzung, zehn sind eine Verteilung) und eine `batch`-Ausgabe gegen eine `compare`-Ausgabe. Ein hinzugefügtes oder entferntes Modell ist keine Ablehnung - die überlappenden Zellen bleiben vergleichbar, und Zellen, die nur auf einer Seite liefen, werden gesondert aufgeführt.

**Was stattdessen eingeschränkt wird:** Zwei nach unterschiedlichen Preistabellen berechnete Ausgaben bleiben vergleichbar, aber ein Teil des Kostenunterschieds ist die Preisliste und nicht das Modell - das wird vor jeder Kostenzahl gesagt. Ein abgebrochener Lauf, ein geändertes Judge-Modell und eine Ausgabe älter als 0.2.0 werden ebenso gekennzeichnet. Eine ältere Ausgabe wird trotzdem verglichen, über den Zeileninhalt, und `diff` benennt die zwei Dinge, die diese Form nicht hergibt: welcher Befehl die Ausgabe geschrieben hat und welche Judge-Modelle liefen.

Signifikanz-Urteile werden von beiden Seiten ausgegeben und nie voneinander abgezogen. Ein p-Wert beschreibt eine Stichprobe; zwei davon aus unabhängigen Läufen sind beide wahr, und ihre Differenz ist keine Größe, die einer von beiden enthält.

`--output-format json` führt jede Zelle, verändert oder nicht, alle sechs Metriken und jede Einschränkung. Die Konsole zeigt Kosten, Latenz und Output-Tokens der bewegten Zellen. Die Exit-Codes stehen in der Tabelle oben: nichts bewegt ist `0`, etwas bewegt ist `4`, und ein nicht vergleichbares Paar ist `2`.

**Datenschutzhinweis:** Jedes Ausgabeformat - JSON, CSV und Markdown - enthält den vollständigen Prompt, den vollständigen System-Prompt und die vollständige Modellantwort jedes Ergebnisses sowie eventuelle Provider-Fehlermeldungen. JSON enthält zusätzlich den Begründungstext jedes Judge-Modells; `--include-reasoning` steuert nur die Konsolenanzeige, nicht die Datei, und CSV und Markdown enthalten ihn nicht. Behandeln Sie jede Ausgabedatei als sensibel, bevor Sie sie committen oder als öffentliches CI-Artefakt hochladen. Aufbewahrungs- und Trainingsbedingungen unterscheiden sich je nach Anbieter, dieses Tool trifft dazu keine Aussage, und Sie sollten die Bedingungen jedes von Ihnen konfigurierten Anbieters prüfen. Claude Fable 5.1 erfordert eine 30-tägige Aufbewahrung und ist nicht unter Zero Data Retention verfügbar. Ein Judge-Modell ist ein zweiter Anbieter: `--judge` sendet neben der Modellantwort auch Ihren Prompt an ihn, Judging erweitert also den Kreis derer, die den Prompt sehen. Eine Anfrage, die das erste Modell ablehnt, wird nun gar nicht mehr an einen Judge gesendet. Ein `compare`-Bericht hält zusätzlich die Umgebung fest, in der er entstanden ist - die Tool-Version, die exakt installierte `scipy`-Version und die vollständige Python-Version - im `methodology`-Block von JSON und Markdown, bei jeder Anzahl von Durchläufen. Das sind Host-Metadaten und nicht Ihre Daten, legen aber eine Abhängigkeitsversion genau fest. CSV enthält davon nichts, und `batch` zeichnet nichts davon auf.

## Konfiguration

### API-Schlüssel

Cli Modelarium speichert API-Schlüssel im OS-nativen Keychain Ihres Systems (Mac Keychain, Windows Credential Manager oder Linux Secret Service über `keyring`). Schlüssel berühren niemals die Festplatte im Klartext.

```bash
# Interaktives Setup (empfohlen)
cli-modelarium configure

# Oder einzeln einstellen
cli-modelarium keys set openai
cli-modelarium keys set anthropic
cli-modelarium keys set google

# Überprüfen, welche Schlüssel konfiguriert sind
cli-modelarium keys list

# Einen Schlüssel entfernen
cli-modelarium keys delete openai
```

Sie können auch Umgebungsvariablen verwenden (nützlich für CI/CD):

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
```

Umgebungsvariablen haben Vorrang vor der Keychain-Speicherung.

### Lokale Modelle (Ollama, LM Studio usw.)

Lokale Modelle funktionieren über OpenAI-kompatible Endpunkte - keine API-Schlüssel erforderlich. Das Tool erkennt automatisch den Standard-Ollama-Port.

```bash
# Standard: nimmt Ollama auf localhost:11434 an
cli-modelarium "test" --models local/llama-3.3

# Stattdessen LM Studio verwenden
cli-modelarium "test" --models local/qwen-3-32b --local-url http://localhost:1234/v1

# Eine benutzerdefinierte lokale URL als Standard speichern
cli-modelarium keys set local --base-url http://localhost:1234/v1
```

## Unterstützte Anbieter

| Anbieter | API-Schlüssel erforderlich | Streaming | Kostenverfolgung | Preise geprüft |
|----------|-----------------|-----------|---------------|------------------|
| OpenAI (GPT-6 Astra, GPT-5.6 Sol, GPT-5.5, o3, usw.) | ✅ | ✅ | ✅ | `first-party` |
| Anthropic (Claude Opus 5, Sonnet 5, Fable 5.1, Haiku 4.5, usw.) | ✅ | ✅ | ✅ | `first-party` |
| Google (Gemini 3.8 Flash, 3.7 Flash, 3.1 Pro, usw.) | ✅ | ✅ | ✅ | `first-party` |
| xAI (Grok 4.6, Grok 4.3, usw.) | ✅ | ✅ | ✅ | `first-party` |
| DeepSeek (V4 Pro, V4 Flash, usw.) | ✅ | ✅ | ✅ | `first-party` |
| Mistral (Medium, Large, Small, Codestral) | ✅ | ✅ | ✅ | `first-party` |
| Groq (Llama 3.3, Llama 4 Scout, gpt-oss) | ✅ | ✅ | ✅ | `third-party` |
| OpenRouter (8 registrierte IDs: Qwen, DeepSeek R1, Llama 3.3, gpt-oss, GLM) | ✅ | ✅ | ✅ | `unchecked` |
| Alibaba/DashScope (Qwen3.8 Max, Qwen3.7 Max, Qwen3 Coder, usw.; ausgewählte Qwen-Modelle, International/Singapur) | ✅ | ✅ | ✅ | `first-party` |
| Z.AI/GLM (GLM-5.3, GLM-5.2, GLM-4.7, usw.; OpenAI-kompatibel, Overseas-Endpunkt) | ✅ | ✅ | ✅ | `first-party` |
| NVIDIA NIM (9 registrierte IDs: Nemotron, Gemma 4, Mistral Nemotron, MiniMax M3, Laguna, Llama 3.1) | ✅ | ✅ | Kein veröffentlichter Tarif | `unpublished` |
| Moonshot AI / Kimi (4 registrierte IDs: K3, K2.7 Code, K2.7 Code HighSpeed, K2.6) | ✅ | ✅ | ✅ | `reseller` |
| **Lokal: Ollama** | ❌ | ✅ | Kostenlos | — |
| **Lokal: LM Studio** | ❌ | ✅ | Kostenlos | — |
| **Lokal: vLLM** | ❌ | ✅ | Kostenlos | — |
| **Lokal: llama.cpp server** | ❌ | ✅ | Kostenlos | — |

Führen Sie `cli-modelarium list-models` aus, um alle derzeit unterstützten Modelle zu sehen.

## Modellgruppen

Anstatt Modell-IDs aufzulisten, akzeptiert `--models` ein Gruppenkürzel. Statische Gruppen werden unverändert expandiert: Jedes unten aufgeführte Mitglied wird ausgeführt, Sie benötigen also einen Schlüssel für jeden Anbieter, den die Gruppe umfasst, und der Lauf bricht beim ersten fehlenden Schlüssel ab. Die dynamischen Gruppen `all` und `all-local` sind die Ausnahme - diese werden gegen das aufgelöst, was Sie tatsächlich konfiguriert haben.

**Statische Gruppen** (feste Zusammensetzung):

| Gruppe | Modelle |
|-------|--------|
| `all-premium` / `all-flagship` | gpt-5.6-sol, claude-opus-5, gemini-3.1-pro-preview, grok-4.6, deepseek-v4-pro, mistral-large-latest, qwen3.8-max, glm-5.2 |
| `all-budget` | gpt-5.4-nano, claude-haiku-4-5, gemini-3.1-flash-lite, grok-4.20-0309-non-reasoning, deepseek-v4-flash, mistral-small-latest, qwen3.7-plus, glm-4.5-air |
| `all-reasoning` | o3, o4-mini, deepseek-v4-pro, glm-5.2 |
| `all-cheap` | gpt-4o-mini, claude-haiku-4-5, gemini-2.5-flash-lite, deepseek-v4-flash, mistral-small-latest, qwen-flash, glm-4.7-flashx |
| `all-open-weight` | openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, llama-3.3-70b-versatile, meta-llama/llama-4-scout-17b-16e-instruct |

**Dynamische Gruppen** (zur Laufzeit aufgelöst):

- `all` — jedes Cloud-Modell, für das Sie einen konfigurierten API-Schlüssel besitzen (ohne lokale Modelle, OpenRouter und NVIDIA - die letzten beiden sind eine registrierte Teilmenge und nicht der vollständige Katalog des Anbieters, und NVIDIAs Kosten lassen sich nicht angeben). Dies kann sich auf viele Modelle ausweiten, kombinieren Sie es daher mit `--max-cost`.
- `all-local` — jedes Modell, das von Ihrem laufenden lokalen Server (Ollama / LM Studio / vLLM / llama.cpp) gemeldet wird. Wenn kein Server erreichbar ist, erhalten Sie eine klare Meldung anstelle eines Fehlers.

```bash
cli-modelarium "Erkläre das CAP-Theorem" --models all-budget
cli-modelarium "Erkläre das CAP-Theorem" --models all --max-cost 0.50
cli-modelarium "Erkläre das CAP-Theorem" --models all-local
```

## Wie es funktioniert

Cli Modelarium verwendet eine modulare Anbieter-Abstraktionsschicht, die die API-Unterschiede zwischen OpenAIs `messages`-Array, Anthropics `system`-Parameter auf oberster Ebene, Googles `system_instruction` und anderen verbirgt. Jeder Anbieter implementiert dasselbe asynchrone Streaming-Interface, sodass die CLI sie alle parallel mit `asyncio.gather()` ausführen kann.

Kostenberechnungen stammen aus dem von jedem Anbieter gemeldeten `usage`-Feld (Input-Tokens, Output-Tokens, gecachte Tokens), multipliziert mit aktuellen Preiskonstanten. Die meisten Preisdaten wurden am **6. September 2026** aus der offiziellen Anbieterdokumentation überprüft; vier Anbieter wurden nicht vollständig abgedeckt - siehe [Hinweise und Einschränkungen](#hinweise-und-einschränkungen).

Für lokale Modelle wird dasselbe OpenAI Python SDK mit einer benutzerdefinierten `base_url` verwendet, da Ollama, LM Studio, vLLM und llama.cpp alle OpenAI-kompatible REST-Endpunkte bereitstellen.

## Hinweise und Einschränkungen

### Preisdaten

Die meisten in Cli Modelarium integrierten Preise wurden am **6. September 2026** aus der offiziellen Anbieterdokumentation überprüft. Einige Einträge tragen ein eigenes Überprüfungsdatum, das jeweils daneben in der Registry vermerkt ist. Groq, Moonshot, NVIDIA und OpenRouter wurden in diesem Durchgang nicht vollständig überprüft und sind in der Registry als nicht verifiziert gekennzeichnet. Zwei Preisgruppen laufen bekanntermaßen aus: `gemini-3.6-flash`, `gemini-3.7-flash` und `gemini-3.8-flash` haben Einführungspreise, die sich am 1. Januar 2027 verdoppeln, und `gpt-5.6-sol` hat einen Aktionspreis, der um den 21. November 2026 endet. Beide lassen einen heutigen Vergleichslauf günstiger erscheinen, als derselbe Lauf später sein wird, und beide ändern sich einheitlich, sodass in der Ausgabe nichts auffällt. LLM-Preise ändern sich häufig (manchmal monatlich). Das `pricing_as_of`-Datum ist in der JSON- und Markdown-Ausgabe enthalten und wird in der Konsole angezeigt; die CSV-Ausgabe enthält es nicht. Überprüfen Sie immer die offizielle Preisseite jedes Anbieters, bevor Sie sich für Budgetierung oder Produktionsentscheidungen auf Kostenberechnungen verlassen.

Die Preise sind der jeweilige Standard-/Listenpreis jedes Anbieters pro 1 Mio. Tokens (nicht Batch-, Priority-, Off-Peak- oder Aktionspreise, mit einer vermerkten Ausnahme: `gpt-5.6-sol`, dessen aktuell veröffentlichter Preis ein Aktionspreis ist); bei Modellen mit nach Eingabegröße gestaffelten Preisen wird die Einstiegs-/Kurzkontext-Stufe angezeigt, und der Cache-Preis entspricht dem Cache-Read-Tarif. Die Kosten für DashScope/Qwen spiegeln die Nicht-Thinking-Tarife wider (das Tool sendet `enable_thinking=false`).

NVIDIA NIM ist die Ausnahme. NVIDIA veröffentlicht für seine gehosteten NIM-Endpunkte keinen Preis pro Token, daher werden die Kosten für NVIDIA-Modelle nicht erfasst: Die in der Kostenspalte angezeigte Null ist das Fehlen eines Tarifs, kein Preis von null. Da diese Kosten immer null sind, greift `--max-cost` bei einem NVIDIA-Modell nie, und eine `cost_under`-Assertion besteht immer - keines von beidem bietet Ihnen bei diesem Anbieter einen Ausgabenschutz. Der Zugang wird über Kontoguthaben abgerechnet statt pro Token; das zu beachtende Fehlerbild ist also der Verbrauch Ihres Guthabens, nicht eine unerwartete Rechnung. Sobald ein NVIDIA-Modell an einem Lauf beteiligt ist, wird ein Hinweis-Panel ausgegeben.

Führen Sie `cli-modelarium pricing` (oder `pricing --all`) aus, um die aktuellen Tarife pro Modell zu erhalten.

### Rate-Limits

Die Rate-Limit-Handhabung und die Standard-Concurrency-Einstellungen pro Anbieter basieren auf den am **21. Juni 2026** überprüften Anbieter-Rate-Limits. Die Limits Ihres spezifischen Tiers können von den hier angenommenen Standardwerten abweichen. Überprüfen Sie Ihre aktuellen Limits anhand des offiziellen Anbieter-Dashboards, bevor Sie Produktionskapazitätsannahmen treffen.

### Modellverfügbarkeit

Die von Cli Modelarium unterstützten Modelle spiegeln wider, was Anbieter am **15. August 2026** angeboten haben. Anbieter veröffentlichen regelmäßig neue Modelle, veralten ältere und passen Fähigkeiten an. Wenn ein Modell in der Registry nicht mehr funktioniert, führen Sie `cli-modelarium list-models` aus und überprüfen Sie die Dokumentation des Anbieters.

### Kein produktionsreifes Gateway

Cli Modelarium ist für Evaluierung und Vergleich konzipiert - Ausführung von Ad-hoc-Tests nebeneinander über Anbieter hinweg von einem Entwickler-Terminal aus. Es ist KEIN Produktions-Inferenz-Gateway. Wenn Sie produktionsskalierbares Routing, Load-Balancing, Fallback-Chains oder SLA-verwaltete Inferenz benötigen, suchen Sie nach Tools, die speziell für diesen Zweck entwickelt wurden.

### Token-Anzahl-Vergleiche zwischen Anbietern

Die in den Ergebnissen angezeigten Token-Anzahlen werden von der API jedes Anbieters gemeldet. Verschiedene Anbieter verwenden verschiedene Tokenizer, sodass "Output-Tokens" zwischen Anbietern für denselben Text nicht direkt vergleichbar sind. Wenn Sie die Kosteneffizienz für den Produktionseinsatz vergleichen, führen Sie echte Prompts in Ihrer tatsächlichen Workload aus - verlassen Sie sich nicht nur auf Pro-Token-Berechnungen über Anbieter hinweg.

### LLM-as-a-Judge-Nutzung

Cli Modelarium beinhaltet optionales LLM-as-a-Judge-Scoring (aktiviert mit dem `--judge`-Flag), das ein LLM verwendet, um Ausgaben anderer LLMs zu bewerten. Dies ist eine Standard-Benchmarking-Methodik und ist unter den Nutzungsbedingungen aller unterstützten Anbieter als Evaluierungs-/Benchmarking-Aktivität erlaubt.

Bei Verwendung von `--judge` sind Sie dafür verantwortlich, die Nutzungsbedingungen jedes Anbieters einzuhalten, dessen Modelle Sie verwenden. Die ToS jedes Anbieters gelten sowohl für die bewerteten Modelle als auch für das Judge-Modell selbst.

**Judge-Bias-Hinweis:** LLM-Judges haben dokumentierte Voreingenommenheiten (Selbstpräferenz, Präferenz für dieselbe Familie, Verbositäts-Präferenz). Judge-Punktzahlen sind nützliches Signal, keine Ground Truth. Verwenden Sie Judge-Panels (`--judges` mit mehreren Modellen), um Bias zu reduzieren.

### Halluzinationserkennung

Das Halluzinationserkennungs-Preset ist ein nützliches Vergleichssignal zwischen Modellen, keine Ground-Truth-Validierung. Die Erkennungsgenauigkeit variiert je nach verwendetem Judge-Modell, erforderlichem Domänenwissen und ob Referenzfakten über `--expected-facts` bereitgestellt werden. Verwenden Sie es für relativen Qualitätsvergleich, nicht für absolute Korrektheitsverifizierung.

### Vergleichsmethodik

LLMs sind bei Temperatur > 0 nicht deterministisch - das erneute Ausführen desselben Prompts kann unterschiedliche Ausgaben erzeugen. Ein einzelner Vergleichsdurchlauf zeigt Ihnen EINE Stichprobe von jedem Modell, kein endgültiges Qualitätsurteil.

Um zuverlässigere Schlussfolgerungen zu ziehen:
- Verwenden Sie `--runs 5` (oder höher), um jeden Vergleich automatisch N-mal auszuführen und statistische Zusammenfassungen zu sehen: mittlere Latenz, Variationskoeffizient, Modalausgabe und Ausgabediversität. Ein Variationskoeffizient unter 0,05 weist auf stabiles Modellverhalten über die Läufe hinweg hin.
- Für die Analyse der Halluzinationskonsistenz kombinieren Sie `--runs` mit `--check-hallucination`, um zu sehen, wie oft das Modell über mehrere Läufe hinweg halluziniert (die Halluzinationsrate).
- Verwenden Sie `--temperatures 0` für deterministischere Ausgaben. Einige Modelle akzeptieren überhaupt keine Temperatureinstellung - `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `claude-fable-5-1`, `o3`, `o4-mini`, `gpt-5`, `gpt-5.5`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-6-astra`, `gemini-3.8-flash`, `kimi-k3`, `kimi-k2.7-code`, `kimi-k2.7-code-highspeed` und `kimi-k2.6`. Das Tool lässt das Feld für diese Modelle weg, damit der Aufruf dennoch gelingt, und sie laufen stattdessen mit dem Standardwert ihres Anbieters.
- Mit `--system-prompts "Sei knapp.,Sei ausführlich."` führen Sie denselben Prompt unter mehreren System-Prompts aus und vergleichen sie nebeneinander. Es vervielfacht die Aufrufanzahl wie `--models` und `--temperatures`. Sind mehrere im Spiel, kennzeichnen die Berichte jede Zeile mit `SP 1`, `SP 2` usw. und drucken eine Legende mit dem vollständigen Text - `SP 2` in der Zellenübersicht ist derselbe Prompt wie `SP 2` in der Tabelle darüber. CSV und JSON führen stattdessen den vollständigen System-Prompt in jeder Zeile.
- Vergleichen Sie über mehrere Prompts hinweg, nicht nur einen
- Verwenden Sie das `--output-format json`-Flag, um Durchläufe für systematische Analyse zu speichern (bei `--runs > 1` enthält das JSON pro Zelle `stats_by_cell`-Aggregate)

Diese neunzehn Modelle werden ohne das Temperaturfeld aufgerufen, und `models_without_temperature` in der JSON-Ausgabe nennt die in einem bestimmten Lauf betroffenen Modelle. Drei Konsequenzen sollten Sie kennen. Ein `--temperatures`-Durchlauf mit mehreren Werten sendet bei diesen Modellen identische Anfragen statt einer echten Reihe, und das Tool gibt in diesem Fall eine Warnung aus. Die in der Ergebnistabelle, in der CSV-Datei und in jedem JSON-Ergebnisdatensatz angezeigte Temperatur ist der **angeforderte** Wert, nicht der angewendete. Und bei `--significance` kann dies eine Schlussfolgerung verändern statt nur eine Bezeichnung: Vergleicht man ein Modell, das die Temperatur weglässt, mit einem, das sie berücksichtigt, entsteht ein Varianzunterschied, der ein Stichprobenartefakt ist - Welch oder Mann-Whitney melden ihn jedoch, als wäre er ein Qualitätsunterschied zwischen den Modellen. Dieser Fall wird gemeldet: Jeder Signifikanzlauf, der ein betroffenes mit einem nicht betroffenen Modell mischt, gibt ein `Temperature not applied`-Panel aus, das die auf dem Provider-Standard laufenden Modelle benennt, und setzt `significance_temperature_mixed` in der JSON-Ausgabe auf `true`. Ein Lauf mit mehreren Temperaturen, der zugleich gemischt ist, erhält beide Meldungen in einem einzigen Panel. Die CSV-Ausgabe enthält kein entsprechendes Signal.

## Über das Projekt

Cli Modelarium ist ein Produkt von **SoraVantia GK**. Ursprünglich entwickelt von **Lavelle Hatcher Jr**, der es weiterhin betreut.

- 📦 Repository: [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium)
- 💬 Fragen oder Fehler: [Issue öffnen](../../issues)
- 🔧 Betreuer: [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

## Warum ich das gebaut habe

Das Vergleichen von LLM-Ausgaben über Anbieter hinweg ist mühsam - verschiedene SDKs, verschiedene Auth-Patterns, verschiedene Antwortformen, keine einfache Möglichkeit, sie nebeneinander mit Kosten- und Latenzdaten zu sehen. Die ausgereiften Cloud-Playgrounds zeigen jeweils nur einen Anbieter, und die verfügbaren Open-Source-Optionen konzentrieren sich entweder auf Produktions-Routing oder sind vollständige Evaluierungsplattformen, die für Teams optimiert sind.

Cli Modelarium ist das kleine, fokussierte CLI-Tool, das eine Sache gut macht: Nebeneinandervergleich mit Qualitäts-Scoring, Assertions, Batch-Modus und Streaming - alles für den terminal-orientierten Entwickler-Workflow konzipiert.

Es ist bewusst fokussiert: kein Produktions-Routing, keine Agent-Orchestrierung, kein Fine-Tuning, keine GUI. Nur sauberer, schneller Vergleich aus der Kommandozeile.

Gebaut mit einer modularen Anbieter-Abstraktion, paralleler Ausführung, transparenter Kostenberechnung und sicherer Schlüsselspeicherung über OS-Keychain-Systeme für lokale Nutzer.

## Mitwirken

Issues und PRs willkommen. Siehe [CONTRIBUTING.md](CONTRIBUTING.md) für Richtlinien.

Für Sicherheitsprobleme siehe bitte [SECURITY.md](SECURITY.md) - reichen Sie keine öffentlichen Issues für Sicherheitsbedenken ein.

## Lizenz

Lizenziert unter der [Apache License, Version 2.0](LICENSE).

Siehe die [NOTICE](NOTICE)-Datei für Attribution-Anforderungen.

---

Ein Produkt von SoraVantia GK, entwickelt und betreut von [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

Lizenziert unter Apache 2.0. Issues, PRs und Gespräche willkommen.
