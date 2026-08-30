<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/cli-modelarium-wordmark-dark.svg">
  <img alt="cli modelarium" src="docs/assets/cli-modelarium-wordmark-light.svg" width="420">
</picture>

Lire ceci dans d'autres langues : [English](README.md) | [日本語](README.ja.md) | [Español](README.es.md) | [한국어](README.ko.md) | [中文](README.zh.md) | [Deutsch](README.de.md) | [Português](README.pt.md) | [Italiano](README.it.md)

Note : Ce README est traduit à des fins d'accessibilité. L'outil CLI Cli Modelarium lui-même ne produit que des sorties en anglais. Toutes les commandes, messages d'erreur et sorties restent en anglais quelle que soit la locale du système.

> Remarque : sept sections n'existent que dans le README anglais — *Reproducibility analysis*, *Statistical significance testing*, *Bootstrap confidence intervals*, *Paired tests for same-prompt comparisons*, *McNemar's test for hallucination significance*, *Headless Linux servers* et *More examples*. Les fonctionnalités elles-mêmes sont pleinement disponibles ; seule leur documentation manque ici. Voir [README.md](https://github.com/SoraVantia/cli-modelarium/blob/main/README.md).

> Comparez les sorties de LLM côte à côte depuis votre terminal - 12 fournisseurs cloud + modèles locaux, avec streaming parallèle, évaluation par lots, scoring LLM-as-judge, détection d'hallucinations et assertions prêtes pour CI/CD.

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

## Ce que ça fait

**Cli Modelarium** est un outil en ligne de commande soigné pour comparer les sorties de LLM entre fournisseurs, modèles, prompts système et températures - avec streaming parallèle en direct, évaluation par lots, tests déterministes et scoring de qualité intégrés.

Utile pour évaluer quel modèle convient à votre tâche spécifique, exécuter des tests de régression de prompts en CI/CD, comparer des modèles locaux aux APIs cloud ou construire des jeux de données d'évaluation - le tout depuis une seule commande de terminal.

## Configuration requise

- Python 3.11 ou supérieur (utilisateurs de Python 3.10 : installez `cli-modelarium==0.1.1`)
- ~350 Mo d'espace disque (scipy et numpy en représentent environ deux tiers)
- macOS (Apple Silicon et Intel), Windows 10+ (x64 et ARM), Linux (x64 et ARM)
- Accès à internet pour la première installation (téléchargement du wheel PyPI)

## Démarrage rapide

```bash
pip install cli-modelarium

# Configurer les clés API (enregistrées de manière sécurisée dans le trousseau de votre OS)
cli-modelarium configure

# Exécuter votre première comparaison
cli-modelarium "Explain quantum computing in one sentence" \
  --models gpt-5.5,claude-opus-4-8,gemini-3.1-pro-preview \
  --temperatures 0,0.7
```

C'est tout. Vous verrez les trois modèles diffuser leurs réponses en direct en parallèle, avec la latence, les nombres de tokens et le coût affichés dans un tableau de comparaison clair.

## Fonctionnalités

### 🤖 Fournisseurs (12 cloud + locaux illimités)

- **Fournisseurs cloud :** OpenAI, Anthropic, Google (Gemini), xAI (Grok), DeepSeek, Mistral, Groq, OpenRouter, Alibaba (DashScope), Z.AI (GLM), NVIDIA (NIM), Moonshot AI (Kimi)
- **Modèles locaux :** Ollama, LM Studio, vLLM, llama.cpp - tout serveur compatible OpenAI s'exécutant sur localhost
- Mélangez les modèles locaux et cloud dans la même comparaison
- Choisissez n'importe quel identifiant de modèle enregistré par appel - sans vous limiter aux raccourcis de groupes intégrés

### ⚡ Streaming parallèle

- Affichage en direct token par token sur tous les modèles simultanément
- Suivi du Time-to-First-Token (TTFT) par modèle
- Voyez quel modèle termine en premier, observez les sorties diverger en temps réel
- Streams depuis les 12 fournisseurs (SSE en interne)

<p align="center">
  <img src="docs/assets/cli-modelarium-comparison-demo.gif" alt="Démonstration de cli-modelarium dans le terminal : trois modèles diffusent leurs réponses au même prompt en parallèle, puis un tableau de comparaison affiche le Time-to-First-Token, la latence, les nombres de tokens et le coût par modèle." width="718">
</p>

**Note sur les tarifs :** les coûts affichés dans les démos proviennent d'une seule exécution au moment de l'enregistrement. Les tarifs changent ; vérifiez-les auprès du fournisseur avant de vous fier à un chiffre.

### 📊 Modes de comparaison multiples

- **Un prompt vs. plusieurs modèles** - comparaisons rapides « lequel est le meilleur ? »
- **Un prompt vs. plusieurs températures** - voyez comment l'aléatoire affecte la sortie
- **Plusieurs prompts système vs. un prompt utilisateur** - tests A/B de prompt engineering
- **Mode par lots** - multi-prompt × multi-modèle pour un vrai travail d'évaluation
- **Comparaisons local vs. cloud** - quantifiez l'écart (ou son absence)

### 🧪 Fonctionnalités d'évaluation

- **Analyse statistique de reproductibilité** - `--runs N` exécute chaque configuration N fois et rapporte moyenne/médiane/écart-type/CV de la latence et des tokens, la fréquence des sorties, la sortie modale et la diversité des sorties. Combinez-le avec `--check-hallucination` pour mesurer le taux d'hallucination sur plusieurs exécutions.
- **Assertions déterministes** - 10 types d'assertions (`contains`, `regex`, `json_valid`, `json_schema`, `max_length_chars`, `latency_under`, `cost_under` et plus) avec sortie pass/fail et codes de sortie CI
- **Scoring LLM-as-a-judge** - Utilisez un LLM pour scorer les sorties d'autres LLMs sur des critères de qualité
- **Panels de juges** - Plusieurs juges moyennent les scores pour une évaluation moins biaisée
- **Preset de détection d'hallucinations** - Critères prêts à l'emploi pour la vérification de la précision factuelle
- **Critères personnalisés** - Définissez vos propres grilles de scoring
- **Auto-omission de l'auto-évaluation** - Les modèles juges sont automatiquement omis quand ils sont aussi jugés

<p align="center">
  <img src="docs/assets/cli-modelarium-runs-demo.gif" alt="Démonstration de cli-modelarium dans le terminal : le même prompt est répété plusieurs fois sur deux modèles, puis le coefficient de variation, les intervalles de confiance bootstrap et un verdict de significativité statistique par paires sont affichés." width="1428">
</p>

### 💾 Formats de sortie

- **Terminal en direct** - Panneaux basés sur Rich avec barres de progression et affichage streaming
- **CSV** - Compatible tableurs (ouvrir dans Excel, Google Sheets, pandas)
- **JSON** - Structuré pour scripts et pipelines
- **Markdown** - Beaux tableaux pour articles de blog et rapports
- **Codes de sortie** - 0/1/2 reflétant le statut pass/fail pour CI/CD

### 💰 Transparence des coûts

- Coût par appel affiché à partir de l'usage rapporté par chaque fournisseur
- Résumé du coût total par comparaison
- Coût du juge affiché séparément quand LLM-as-judge est activé
- Les modèles locaux affichés comme « Free »
- Flag `--max-cost` pour éviter les factures surprises

### 🔒 Sécurité

- Clés API stockées dans le trousseau natif de l'OS via `keyring` (Mac Keychain, Windows Credential Manager, Linux Secret Service)
- La validation du format détecte les erreurs de collage avant le stockage
- La rédaction des messages d'erreur empêche la fuite de clés dans les tracebacks
- Validation localhost uniquement pour les URLs de modèles locaux
- `SECURITY.md` avec politique de divulgation responsable

### 🛡️ Gestion des limites de débit

- Limites de concurrence par fournisseur (défaut 5) - une seule valeur pour tous les fournisseurs, à vérifier face à votre propre tier
- Réessai automatique 429 avec backoff exponentiel
- Le 529 « overloaded » d'Anthropic est géré séparément des limites de débit
- Flag `--concurrency` pour les utilisateurs avancés sur des tiers supérieurs
- Échec gracieux par modèle (les autres modèles continuent)
- Les limites de débit du tier gratuit de DashScope et du modèle Qwen phare (qwen3.7-max) sont plus strictes que chez la plupart des fournisseurs ; réduisez `--concurrency` si vous rencontrez des 429.
- Moonshot exige un rechargement minimum de 1 $ avant toute utilisation : il n'y a pas de palier gratuit. Le Tier0 correspond à 1 requête simultanée, 3 requêtes par minute et 1,5 M de tokens par jour ; 10 $ de rechargement cumulé font passer au Tier1. Réduisez `--concurrency` en Tier0.

### 🌐 Multiplateforme

- Fonctionne de manière identique sur macOS, Windows (10+ et ARM) et Linux
- Toutes les E/S de fichiers utilisent `pathlib` + encodage UTF-8 explicite
- L'écriture CSV utilise `newline=""` pour la compatibilité Windows
- Python 3.11+ requis

### 📋 Expérience développeur

- **Binaire CLI unique** - `pip install cli-modelarium` et c'est tout
- **UI soignée basée sur Rich** - Polissage de terminal au niveau Claude Code
- **Sortie JSON** - Pipez dans n'importe quoi (`jq`, scripts, monitoring)
- **Prêt pour CI/CD** - Codes de sortie, sortie structurée, exemple GitHub Actions inclus
- **Licence Apache 2.0** - Utilisez dans n'importe quel projet, commercial ou autre

## Exemples

### Comparer 3 modèles sur une tâche de programmation

```bash
cli-modelarium "Write a Python function to find the longest palindromic substring" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview
```

### Évaluation par lots avec assertions

Créez `eval.json` :

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

Exécutez-le :

```bash
cli-modelarium batch eval.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output results.csv
```

### Scorer les sorties avec un juge LLM

```bash
cli-modelarium "Explain recursion in one paragraph" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview,local/llama-3.3-70b \
  --judge claude-opus-4-7 \
  --judge-criteria "accuracy,clarity,brevity"
```

<p align="center">
  <img src="docs/assets/cli-modelarium-judge-demo.gif" alt="Démonstration de cli-modelarium dans le terminal : un juge LLM note deux modèles ; un tableau comparatif affiche un score par modèle, suivi du raisonnement écrit du juge." width="848">
</p>

**Note sur la démo :** les scores et les coûts proviennent d'une seule exécution au moment de l'enregistrement. Les scores du juge sont un signal, pas une vérité de référence, et ne se reproduisent pas exactement d'une exécution ou d'une version de modèle à l'autre. Les tarifs changent ; vérifiez-les auprès du fournisseur avant de vous fier à un chiffre.

### Détecter les hallucinations contre des faits connus

```bash
cli-modelarium "Tell me about the Eiffel Tower" \
  --models gpt-5.5,claude-opus-4-7 \
  --judge claude-opus-4-7 \
  --check-hallucination \
  --expected-facts "Built 1887-1889,Located in Paris France,Designed by Gustave Eiffel"
```

### Comparer un modèle local aux APIs cloud

```bash
# Démarrer Ollama d'abord : ollama run llama3.3
cli-modelarium "Summarize the key features of microservices architecture" \
  --models local/llama-3.3-70b,gpt-5.5,claude-opus-4-7
```

### Exécuter en CI/CD (exemple GitHub Actions)

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

La commande se termine avec le code 1 si le taux de réussite tombe sous 90 %, faisant échouer le build.

#### Codes de sortie

| Code | Signification |
|------|---------------|
| `0` | Succès. |
| `1` | Échec d'assertion - une ou plusieurs assertions n'ont pas été satisfaites, ou une exécution `batch` n'a rien vérifié. Seul `batch` rend un verdict d'assertion ; `compare` peut malgré tout se terminer par `1` sur une erreur inattendue. |
| `2` | L'exécution n'a pas pu aboutir. |

Le code `2` recouvre plusieurs causes distinctes et **ne les distingue pas** : une clé d'API manquante, un modèle inconnu, un modèle retiré, une erreur du fournisseur, un plafond de coût dépassé, un fichier de lot mal formé, une combinaison de flags rejetée, un conflit de fichier de sortie ou une limite de taille de lot dépassée.

Deux règles méritent d'être connues avant de conditionner un pipeline à ces codes :

- **Les échecs d'appel priment sur les assertions.** Si un appel de modèle échoue, `batch` se termine avec `2` sans rendre de verdict d'assertion, même si des assertions ont également échoué. Une suite en échec et une clé d'API invalide se ressemblent du point de vue du code de sortie.
- **Un serveur local injoignable n'est pas un échec.** `list-models --local` se termine avec `0` lorsqu'aucun serveur ne répond ; le code de sortie ne permet donc pas de le détecter.

Pour savoir *pourquoi* une exécution a échoué, lisez le champ `error` de chaque résultat dans la sortie JSON - il contient le message du fournisseur, les chaînes ressemblant à des identifiants étant expurgées :

```bash
cli-modelarium batch ./eval/test_suite.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output-format json --output results.json
code=$?
if [ "$code" -eq 2 ]; then
  jq -r '.results[] | select(.error) | "\(.model): \(.error)"' results.json
fi
```

`--output-format json` est indispensable : la sortie par défaut ne comporte aucun champ d'erreur exploitable par un script. Notez que les échecs survenant *avant* tout appel de modèle (clé manquante, modèle inconnu, fichier de lot incorrect) ne produisent aucun JSON ; le message affiché en console est alors le seul signal.

**Note de confidentialité :** tous les formats de sortie - JSON, CSV et Markdown - contiennent le prompt complet et la réponse complète du modèle pour chaque résultat, ainsi que tout message d'erreur du fournisseur. JSON contient en outre le texte de raisonnement de chaque juge ; `--include-reasoning` ne contrôle que l'affichage console, pas le fichier, et CSV et Markdown ne le contiennent pas. Considérez tout fichier de sortie comme sensible avant de le committer ou de le publier comme artefact de CI public. Les conditions de conservation des données et d'entraînement diffèrent selon les fournisseurs, cet outil n'affirme rien à leur sujet, et il convient de vérifier les conditions de chaque fournisseur que vous configurez.

## Configuration

### Clés API

Cli Modelarium stocke les clés API dans le trousseau natif de votre OS (Mac Keychain, Windows Credential Manager ou Linux Secret Service via `keyring`). Les clés ne touchent jamais le disque en clair.

```bash
# Configuration interactive (recommandée)
cli-modelarium configure

# Ou définir individuellement
cli-modelarium keys set openai
cli-modelarium keys set anthropic
cli-modelarium keys set google

# Vérifier quelles clés sont configurées
cli-modelarium keys list

# Supprimer une clé
cli-modelarium keys delete openai
```

Vous pouvez aussi utiliser les variables d'environnement (utile pour CI/CD) :

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
```

Les variables d'environnement ont priorité sur le stockage du trousseau.

### Modèles locaux (Ollama, LM Studio, etc.)

Les modèles locaux fonctionnent via des endpoints compatibles OpenAI - pas de clés API nécessaires. L'outil détecte automatiquement le port Ollama par défaut.

```bash
# Défaut : suppose Ollama sur localhost:11434
cli-modelarium "test" --models local/llama-3.3

# Utiliser LM Studio à la place
cli-modelarium "test" --models local/qwen-3-32b --local-url http://localhost:1234/v1

# Enregistrer une URL locale personnalisée par défaut
cli-modelarium keys set local --base-url http://localhost:1234/v1
```

## Fournisseurs supportés

| Fournisseur | Clés API Requises | Streaming | Suivi des Coûts |
|----------|-----------------|-----------|---------------|
| OpenAI (GPT-5, GPT-5 mini, o3, o4-mini, etc.) | ✅ | ✅ | ✅ |
| Anthropic (Claude Opus 4.8, Sonnet 4.6, Haiku 4.5, etc.) | ✅ | ✅ | ✅ |
| Google (Gemini 3.5 Flash, Gemini 3.1 Pro, etc.) | ✅ | ✅ | ✅ |
| xAI (Grok 4.3, etc.) | ✅ | ✅ | ✅ |
| DeepSeek (V4 Pro, V4 Flash, etc.) | ✅ | ✅ | ✅ |
| Mistral (Large, Medium, Small) | ✅ | ✅ | ✅ |
| Groq (Llama 3.3, Llama 4 Scout, gpt-oss) | ✅ | ✅ | ✅ |
| OpenRouter (8 identifiants enregistrés : Qwen, DeepSeek R1, Llama 3.3, gpt-oss, GLM) | ✅ | ✅ | ✅ |
| Alibaba/DashScope (Qwen3.7 Max, Qwen3.6 Flash, Qwen3 Coder, etc. ; modèles Qwen sélectionnés, International/Singapour) | ✅ | ✅ | ✅ |
| Z.AI/GLM (GLM-5.2, GLM-4.7, GLM-4.5 Air, etc. ; compatible OpenAI, point de terminaison international) | ✅ | ✅ | ✅ |
| NVIDIA NIM (9 identifiants enregistrés : Nemotron, Gemma 4, Mistral Nemotron, MiniMax M3, Laguna, Llama 3.1) | ✅ | ✅ | Aucun tarif publié |
| Moonshot AI / Kimi (4 ID enregistrés : K3, K2.7 Code, K2.7 Code HighSpeed, K2.6) | ✅ | ✅ | ✅ |
| **Local : Ollama** | ❌ | ✅ | Gratuit |
| **Local : LM Studio** | ❌ | ✅ | Gratuit |
| **Local : vLLM** | ❌ | ✅ | Gratuit |
| **Local : llama.cpp server** | ❌ | ✅ | Gratuit |

Exécutez `cli-modelarium list-models` pour voir tous les modèles actuellement supportés.

## Groupes de modèles

Au lieu d'énumérer des identifiants de modèles, `--models` accepte un raccourci de groupe. Les groupes statiques sont développés tels quels : chaque membre listé ci-dessous est exécuté, vous avez donc besoin d'une clé pour chaque fournisseur couvert par le groupe, et l'exécution s'interrompt à la première clé manquante. Les groupes dynamiques `all` et `all-local` font exception : ceux-là sont résolus en fonction de ce que vous avez réellement configuré.

**Groupes statiques** (composition fixe) :

| Groupe | Modèles |
|-------|--------|
| `all-premium` / `all-flagship` | gpt-5.6-sol, claude-opus-5, gemini-3.1-pro-preview, grok-4.6, deepseek-v4-pro, mistral-large-latest, qwen3.8-max, glm-5.2 |
| `all-budget` | gpt-5.4-nano, claude-haiku-4-5, gemini-3.1-flash-lite, grok-4.20-0309-non-reasoning, deepseek-v4-flash, mistral-small-latest, qwen3.7-plus, glm-4.5-air |
| `all-reasoning` | o3, o4-mini, deepseek-v4-pro, magistral-medium-latest, magistral-small-latest, glm-5.2 |
| `all-cheap` | gpt-4o-mini, claude-haiku-4-5, gemini-2.5-flash-lite, deepseek-v4-flash, mistral-small-latest, qwen-flash, glm-4.7-flashx |
| `all-open-weight` | openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, llama-3.3-70b-versatile, meta-llama/llama-4-scout-17b-16e-instruct |

**Groupes dynamiques** (résolus à l'exécution) :

- `all` — tous les modèles cloud pour lesquels vous avez une clé d'API configurée (exclut les modèles locaux, OpenRouter et NVIDIA : ces deux derniers sont un sous-ensemble enregistré et non le catalogue complet du fournisseur, et le coût de NVIDIA ne peut pas être indiqué). Cela peut se déployer sur de nombreux modèles, alors associez-le à `--max-cost`.
- `all-local` — tous les modèles signalés par votre serveur local en cours d'exécution (Ollama / LM Studio / vLLM / llama.cpp). Si aucun serveur n'est joignable, vous obtenez un message clair au lieu d'une erreur.

```bash
cli-modelarium "Explique le théorème CAP" --models all-budget
cli-modelarium "Explique le théorème CAP" --models all --max-cost 0.50
cli-modelarium "Explique le théorème CAP" --models all-local
```

## Comment ça marche

Cli Modelarium utilise une couche d'abstraction de fournisseur modulaire qui masque les différences d'API entre le tableau `messages` d'OpenAI, le paramètre `system` de niveau supérieur d'Anthropic, le `system_instruction` de Google et d'autres. Chaque fournisseur implémente la même interface de streaming asynchrone, donc la CLI peut tous les exécuter en parallèle avec `asyncio.gather()`.

Les calculs de coût proviennent du champ `usage` rapporté par chaque fournisseur (tokens d'entrée, tokens de sortie, tokens en cache) multiplié par les constantes de tarification actuelles. Les données de tarification ont été vérifiées depuis la documentation officielle des fournisseurs le **29 juillet 2026** - voir [Notes et limitations](#notes-et-limitations) pour les mises en garde.

Pour les modèles locaux, le même SDK Python OpenAI est utilisé avec une `base_url` personnalisée, puisque Ollama, LM Studio, vLLM et llama.cpp exposent tous des endpoints REST compatibles OpenAI.

## Notes et limitations

### Données de tarification

La plupart des tarifications intégrées dans Cli Modelarium ont été vérifiées depuis la documentation officielle des fournisseurs le **29 juillet 2026**. Certaines entrées portent leur propre date de vérification, indiquée à côté de chacune dans le registre ; les tarifs Z.AI/GLM sont les plus anciens, du **22 juin 2026**. Les tarifs des LLM changent fréquemment (parfois mensuellement). La date `pricing_as_of` figure dans la sortie JSON et s'affiche dans la console ; les sorties CSV et Markdown ne la contiennent pas. Vérifiez toujours par rapport à la page officielle de tarification de chaque fournisseur avant de vous fier aux calculs de coûts pour la budgétisation ou les décisions de production.

Les prix correspondent au tarif public standard/catalogue de chaque fournisseur par tranche de 1M de tokens (pas la tarification par lots, prioritaire, hors pointe ou promotionnelle) ; pour les modèles à paliers selon la taille d'entrée, le palier d'entrée/contexte court est affiché, et la tarification en cache correspond au tarif de lecture du cache. Les coûts de DashScope/Qwen reflètent les tarifs sans raisonnement (l'outil envoie `enable_thinking=false`).

NVIDIA NIM constitue l'exception. NVIDIA ne publie aucun tarif par token pour ses points de terminaison NIM hébergés : le coût n'est donc pas suivi pour les modèles NVIDIA, et le zéro affiché dans la colonne de coût correspond à l'absence de tarif, non à un prix nul. Comme ce coût est toujours nul, `--max-cost` ne se déclenchera jamais sur un modèle NVIDIA et une assertion `cost_under` réussira toujours ; ni l'un ni l'autre ne vous offre de protection sur les dépenses chez ce fournisseur. L'accès est décompté en crédits du compte plutôt que facturé par token : ce qu'il faut surveiller, c'est l'épuisement de vos crédits, pas une facture inattendue. Un panneau d'avertissement s'affiche dès qu'un modèle NVIDIA participe à une exécution.

Exécutez `cli-modelarium pricing` (ou `pricing --all`) pour obtenir les tarifs actuels par modèle.

### Limites de débit

La gestion des limites de débit et les paramètres de concurrence par défaut par fournisseur sont basés sur les limites de débit des fournisseurs vérifiées le **21 juin 2026**. Les limites de votre tier spécifique peuvent différer des valeurs par défaut supposées ici. Vérifiez vos limites actuelles par rapport au tableau de bord officiel du fournisseur avant de bâtir des hypothèses de capacité de production.

### Disponibilité des modèles

Les modèles supportés par Cli Modelarium reflètent ce que les fournisseurs proposaient le **15 août 2026**. Les fournisseurs publient régulièrement de nouveaux modèles, déprécient les anciens et ajustent les capacités. Si un modèle dans le registre ne fonctionne plus, exécutez `cli-modelarium list-models` et consultez la documentation du fournisseur.

### Pas une passerelle de qualité production

Cli Modelarium est conçu pour l'évaluation et la comparaison - exécution de tests ad-hoc côte à côte entre fournisseurs depuis un terminal de développeur. Ce n'est PAS une passerelle d'inférence de production. Si vous avez besoin de routage à l'échelle de production, d'équilibrage de charge, de chaînes de fallback ou d'inférence gérée par SLA, cherchez des outils construits spécifiquement à cet effet.

### Comparaisons de nombre de tokens entre fournisseurs

Les nombres de tokens affichés dans les résultats sont rapportés par l'API de chaque fournisseur. Différents fournisseurs utilisent différents tokenizers, donc les « tokens de sortie » ne sont pas directement comparables entre fournisseurs pour le même texte. Si vous comparez l'efficacité des coûts pour un usage en production, exécutez de vrais prompts dans votre charge de travail réelle - ne vous fiez pas uniquement aux calculs par token entre fournisseurs.

### Utilisation de LLM-as-a-Judge

Cli Modelarium inclut un scoring LLM-as-a-judge optionnel (activé avec le flag `--judge`), qui utilise un LLM pour évaluer les sorties d'autres LLMs. C'est une méthodologie de benchmarking standard et c'est autorisé par les Conditions d'utilisation de tous les fournisseurs supportés en tant qu'activité d'évaluation/benchmarking.

En utilisant `--judge`, vous êtes responsable de respecter les Conditions d'utilisation de chaque fournisseur dont vous utilisez les modèles. Les ToS de chaque fournisseur s'appliquent à la fois aux modèles évalués et au modèle juge lui-même.

**Avis sur le biais du juge :** Les juges LLM ont des biais documentés (préférence pour soi, préférence pour la même famille, préférence pour la verbosité). Les scores du juge sont un signal utile, pas une vérité absolue. Utilisez des panels de juges (`--judges` avec plusieurs modèles) pour réduire les biais.

### Détection d'hallucinations

Le preset de détection d'hallucinations est un signal de comparaison utile entre modèles, pas une validation de vérité absolue. La précision de la détection varie selon le modèle juge utilisé, les connaissances du domaine requises et si des faits de référence sont fournis via `--expected-facts`. Utilisez-le pour la comparaison de qualité relative, pas pour la vérification d'exactitude absolue.

### Méthodologie de comparaison

Les LLMs sont non déterministes à température > 0 - réexécuter le même prompt peut produire des sorties différentes. Une seule exécution de comparaison vous montre UN échantillon de chaque modèle, pas un verdict de qualité définitif.

Pour tirer des conclusions plus fiables :
- Utilisez `--runs 5` (ou plus) pour exécuter automatiquement chaque comparaison N fois et voir des résumés statistiques : latence moyenne/médiane, coefficient de variation, sortie modale et diversité des sorties. Un coefficient de variation inférieur à 0,05 indique un comportement de modèle stable d'une exécution à l'autre.
- Pour l'analyse de la cohérence des hallucinations, combinez `--runs` avec `--check-hallucination` afin de voir à quelle fréquence le modèle hallucine sur plusieurs exécutions (le taux d'hallucination).
- Utilisez `--temperatures 0` pour des sorties plus déterministes. Certains modèles n'acceptent aucun réglage de température - `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `o3`, `o4-mini`, `gpt-5`, `gpt-5.5`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `kimi-k3`, `kimi-k2.7-code`, `kimi-k2.7-code-highspeed` et `kimi-k2.6`. L'outil omet le champ pour ceux-ci afin que l'appel aboutisse, et ils s'exécutent avec la valeur par défaut de leur fournisseur.
- Comparez sur plusieurs prompts, pas seulement un
- Utilisez le flag `--output json` pour sauvegarder les exécutions pour analyse systématique (avec `--runs > 1`, le JSON inclut des agrégats `stats_by_cell` par cellule)

Ces douze modèles sont appelés sans le champ de température, et `models_without_temperature` dans la sortie JSON nomme ceux concernés par une exécution donnée. Trois conséquences méritent d'être connues. Un balayage `--temperatures` à plusieurs valeurs émet des requêtes identiques plutôt qu'un véritable balayage sur ces modèles, et l'outil affiche un avertissement dans ce cas. La température indiquée dans le tableau de résultats, dans le CSV et dans chaque enregistrement JSON est la valeur **demandée**, pas celle appliquée. Et `--significance` est l'endroit où cela peut changer une conclusion plutôt qu'une étiquette : comparer un modèle qui omet la température à un modèle qui la respecte produit un écart de variance qui est un artefact d'échantillonnage, et Welch ou Mann-Whitney le rapporteront comme s'il s'agissait d'une différence de qualité entre modèles. Ce cas est bien signalé : toute exécution de significativité mêlant un modèle concerné à un modèle qui ne l'est pas affiche un panneau `Temperature not applied` nommant les modèles ayant tourné à la température par défaut du fournisseur, et met `significance_temperature_mixed` à `true` dans la sortie JSON. Une exécution multi-températures qui est aussi mixte reçoit les deux messages dans un seul panneau. Le CSV ne porte aucun signal équivalent.

## À propos du projet

Cli Modelarium est un produit de **SoraVantia GK**. Il a été créé à l'origine par **Lavelle Hatcher Jr**, qui continue de le maintenir.

- 📦 Dépôt : [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium)
- 💬 Questions ou bogues : [ouvrir une issue](../../issues)
- 🔧 Mainteneur : [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

## Pourquoi je l'ai construit

Comparer les sorties de LLM entre fournisseurs est fastidieux - différents SDKs, différents patterns d'authentification, différentes formes de réponses, aucun moyen facile de les voir côte à côte avec des données de coût et de latence. Les playgrounds cloud soignés ne montrent qu'un seul fournisseur à la fois, et les options open source disponibles se concentrent soit sur le routage de production, soit sont des plateformes d'évaluation complètes optimisées pour les équipes.

Cli Modelarium est le petit outil CLI focalisé qui fait bien une chose : comparaison côte à côte avec scoring de qualité, assertions, mode par lots et streaming - le tout conçu pour le workflow développeur centré sur le terminal.

C'est intentionnellement focalisé : pas de routage de production, pas d'orchestration d'agent, pas de fine-tuning, pas de GUI. Juste une comparaison propre et rapide depuis la ligne de commande.

Construit avec une abstraction de fournisseur modulaire, exécution parallèle, calcul de coût transparent et stockage sécurisé des clés via les systèmes de trousseau OS pour les utilisateurs locaux.

## Contribuer

Issues et PRs bienvenus. Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les directives.

Pour les problèmes de sécurité, veuillez consulter [SECURITY.md](SECURITY.md) - ne déposez pas d'issues publiques pour des préoccupations de sécurité.

## Licence

Sous licence [Apache License, Version 2.0](LICENSE).

Voir le fichier [NOTICE](NOTICE) pour les exigences d'attribution.

---

Un produit de SoraVantia GK, créé et maintenu par [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

Sous licence Apache 2.0. Issues, PRs et conversations bienvenus.
