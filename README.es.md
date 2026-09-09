<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/cli-modelarium-wordmark-dark.svg">
  <img alt="cli modelarium" src="docs/assets/cli-modelarium-wordmark-light.svg" width="420">
</picture>

Leer esto en otros idiomas: [English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [中文](README.zh.md) | [Deutsch](README.de.md) | [Português](README.pt.md) | [Italiano](README.it.md)

Nota: Este README está traducido por accesibilidad. La herramienta CLI Cli Modelarium en sí solo produce salida en inglés. Todos los comandos, mensajes de error y salidas permanecen en inglés independientemente de la configuración regional del sistema.

> Nota: siete secciones existen solo en el README en inglés — *Reproducibility analysis*, *Statistical significance testing*, *Bootstrap confidence intervals*, *Paired tests for same-prompt comparisons*, *McNemar's test for hallucination significance*, *Headless Linux servers* y *More examples*. Las funciones en sí están plenamente disponibles; lo que falta aquí es su documentación. Consulte [README.md](https://github.com/SoraVantia/cli-modelarium/blob/main/README.md).

> Compare salidas de LLM lado a lado desde su terminal - 12 proveedores en la nube + modelos locales, con streaming paralelo, evaluación por lotes, puntuación LLM-as-judge, detección de alucinaciones y aserciones listas para CI/CD.

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

## Qué hace

**Cli Modelarium** es una herramienta de línea de comandos pulida para comparar salidas de LLM entre proveedores, modelos, prompts de sistema y temperaturas - con streaming paralelo en vivo, evaluación por lotes, pruebas deterministas y puntuación de calidad integrados.

Útil para evaluar qué modelo se adapta a su tarea específica, ejecutar pruebas de regresión de prompts en CI/CD, comparar modelos locales contra APIs en la nube o construir conjuntos de datos de evaluación - todo desde un solo comando de terminal.

## Requisitos del sistema

- Python 3.11 o superior (usuarios de Python 3.10: instale `cli-modelarium==0.1.1`)
- ~350 MB de espacio en disco (scipy y numpy representan unos dos tercios)
- macOS (Apple Silicon e Intel), Windows 10+ (x64 y ARM), Linux (x64 y ARM)
- Acceso a internet para la primera instalación (descarga del wheel de PyPI)

## Inicio rápido

```bash
pip install cli-modelarium

# Configurar las claves de API (se guardan de forma segura en el llavero del SO)
cli-modelarium configure

# Ejecutar su primera comparación
cli-modelarium "Explain quantum computing in one sentence" \
  --models gpt-5.5,claude-opus-4-8,gemini-3.1-pro-preview
```

Eso es todo. Verá los tres modelos transmitir sus respuestas en vivo en paralelo, con la latencia, los conteos de tokens y el costo mostrados en una tabla de comparación limpia.

## Características

### 🤖 Proveedores (12 en la nube + locales ilimitados)

- **Proveedores en la nube:** OpenAI, Anthropic, Google (Gemini), xAI (Grok), DeepSeek, Mistral, Groq, OpenRouter, Alibaba (DashScope), Z.AI (GLM), NVIDIA (NIM), Moonshot AI (Kimi)
- **Modelos locales:** Ollama, LM Studio, vLLM, llama.cpp - cualquier servidor compatible con OpenAI que se ejecute en localhost
- Combine modelos locales y en la nube en la misma comparación
- Elija cualquier ID de modelo registrado por llamada - sin limitarse a los atajos de grupo integrados

### ⚡ Streaming paralelo

- Visualización token por token en vivo en todos los modelos simultáneamente
- Seguimiento del Time-to-First-Token (TTFT) por modelo
- Vea qué modelo termina primero, observe cómo divergen las salidas en tiempo real
- Streams desde los 12 proveedores (SSE por debajo)

<p align="center">
  <img src="docs/assets/cli-modelarium-comparison-demo.gif" alt="Demostración en terminal de cli-modelarium: tres modelos transmiten sus respuestas al mismo prompt en paralelo y luego una tabla de comparación muestra el Time-to-First-Token, la latencia, los conteos de tokens y el costo por modelo." width="718">
</p>

**Nota de precios:** las cifras de costo en las demos provienen de una sola ejecución en el momento de la grabación. Los precios cambian; verifíquelos con el proveedor antes de confiar en cualquier cifra.

### 📊 Múltiples modos de comparación

- **Un solo prompt vs. múltiples modelos** - comparaciones rápidas de "¿cuál es mejor?"
- **Un solo prompt vs. múltiples temperaturas** - vea cómo la aleatoriedad afecta la salida
- **Múltiples prompts de sistema vs. un prompt de usuario** - pruebas A/B de ingeniería de prompts
- **Modo por lotes** - multi-prompt × multi-modelo para trabajo de evaluación real
- **Comparaciones local vs. nube** - cuantifique la brecha (o la falta de ella)

### 🧪 Características de evaluación

- **Análisis estadístico de reproducibilidad** - `--runs N` ejecuta cada configuración N veces e informa media/desviación estándar/CV de latencia y tokens, frecuencia de salida, salida modal y diversidad de salida. Combínelo con `--check-hallucination` para medir la tasa de alucinación entre ejecuciones.
- **Aserciones deterministas** - 10 tipos de aserciones (`contains`, `regex`, `json_valid`, `json_schema`, `max_length_chars`, `latency_under`, `cost_under` y más) con salida de aprobado/fallado y códigos de salida para CI
- **Puntuación LLM-as-a-judge** - Use un LLM para puntuar las salidas de otros según criterios de calidad
- **Paneles de jueces** - Múltiples jueces promedian puntuaciones para una evaluación menos sesgada
- **Preset de detección de alucinaciones** - Criterios listos para usar para la verificación de precisión factual
- **Criterios personalizados** - Defina sus propias rúbricas de puntuación
- **Auto-omisión de autoevaluación** - Los modelos jueces se omiten automáticamente cuando también están siendo juzgados

<p align="center">
  <img src="docs/assets/cli-modelarium-runs-demo.gif" alt="Demostración en terminal de cli-modelarium: el mismo prompt se repite varias veces en dos modelos y luego se informan el coeficiente de variación, los intervalos de confianza bootstrap y un veredicto de significancia estadística por pares." width="1428">
</p>

### 💾 Formatos de salida

- **Terminal en vivo** - Paneles basados en Rich con barras de progreso y visualización de streaming
- **CSV** - Compatible con hojas de cálculo (abrir en Excel, Google Sheets, pandas) **La fila de encabezado es el contrato; la posición de la columna no lo es.** Se añaden columnas a medida que la herramienta crece: lea por nombre.
- **JSON** - Estructurado para scripts y pipelines
- **Markdown** - Tablas elegantes para publicaciones de blog e informes
- **Códigos de salida** - 0/1/2/3 que reflejan el estado de aprobado/fallado para CI/CD

### 💰 Transparencia de costos

- Costo por llamada mostrado desde el uso reportado por cada proveedor
- Resumen del costo total por comparación
- Costo del juez mostrado por separado cuando LLM-as-judge está habilitado
- Los modelos locales se muestran como "Free"
- Flag `--max-cost` que deja de lanzar nuevas llamadas una vez superado el límite (las llamadas ya en curso terminan, así que acota una ejecución en lugar de evitar una factura)

### 🔒 Seguridad

- Las claves de API se almacenan en el llavero nativo del SO a través de `keyring` (Mac Keychain, Windows Credential Manager, Linux Secret Service)
- La validación de formato detecta errores de pegado antes del almacenamiento
- La redacción de mensajes de error previene la fuga de claves en los tracebacks
- Validación exclusiva de localhost para URLs de modelos locales
- `SECURITY.md` con política de divulgación responsable

### 🛡️ Manejo de límites de velocidad

- Límites de concurrencia por proveedor (predeterminado 5) - un único valor para todos los proveedores, contrástelo con su propio nivel
- Reintento automático de 429 con retroceso exponencial
- El 529 "overloaded" de Anthropic se maneja por separado de los límites de velocidad
- Flag `--concurrency` para usuarios avanzados en niveles superiores
- Fallo elegante por modelo (otros modelos continúan)
- Los límites de velocidad del nivel gratuito de DashScope y del Qwen insignia (qwen3.7-max) son más estrictos que los de la mayoría de los proveedores; reduzca `--concurrency` si encuentra errores 429.
- Moonshot exige una recarga mínima de 1 $ antes de cualquier uso: no hay nivel gratuito. Tier0 es 1 solicitud concurrente, 3 solicitudes por minuto y 1,5 M de tokens al día; una recarga acumulada de 10 $ pasa a Tier1. Reduzca `--concurrency` en Tier0.

### 🌐 Multiplataforma

- Funciona de forma idéntica en macOS, Windows (10+ y ARM) y Linux
- Toda la E/S de archivos usa `pathlib` + codificación UTF-8 explícita
- La escritura de CSV usa `newline=""` para compatibilidad con Windows
- Se requiere Python 3.11+

### 📋 Experiencia del desarrollador

- **Binario CLI único** - `pip install cli-modelarium` y listo
- **UI pulida basada en Rich** - Pulido de terminal al nivel de Claude Code
- **Salida JSON** - Conecte a cualquier cosa (`jq`, scripts, monitoreo)
- **Listo para CI/CD** - Códigos de salida, salida estructurada, ejemplo de GitHub Actions incluido
- **Licenciado bajo Apache 2.0** - Úselo en cualquier proyecto, comercial o de otro tipo

## Ejemplos

### Comparar 3 modelos en una tarea de codificación

```bash
cli-modelarium "Write a Python function to find the longest palindromic substring" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview
```

### Evaluación por lotes con aserciones

Cree `eval.json`:

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

Ejecútelo:

```bash
cli-modelarium batch eval.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output results.csv
```

### Puntuar salidas con un juez LLM

```bash
cli-modelarium "Explain recursion in one paragraph" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview,local/llama-3.3-70b \
  --judge claude-opus-4-7 \
  --judge-criteria "accuracy,clarity,brevity"
```

<p align="center">
  <img src="docs/assets/cli-modelarium-judge-demo.gif" alt="Demostración en terminal de cli-modelarium: un juez LLM puntúa dos modelos; una tabla comparativa muestra una puntuación por modelo y debajo aparece el razonamiento escrito del juez." width="848">
</p>

**Nota de la demostración:** las puntuaciones y las cifras de costo provienen de una sola ejecución en el momento de la grabación. Las puntuaciones del juez son una señal, no una verdad absoluta, y no se reproducen exactamente entre ejecuciones ni entre versiones de modelo. Los precios cambian; verifíquelos con el proveedor antes de confiar en cualquier cifra.

### Detectar alucinaciones contra hechos conocidos

```bash
cli-modelarium "Tell me about the Eiffel Tower" \
  --models gpt-5.5,claude-opus-4-7 \
  --judge claude-opus-4-7 \
  --check-hallucination \
  --expected-facts "Built 1887-1889,Located in Paris France,Designed by Gustave Eiffel"
```

### Comparar un modelo local contra APIs en la nube

```bash
# Iniciar Ollama primero: ollama run llama3.3
cli-modelarium "Summarize the key features of microservices architecture" \
  --models local/llama-3.3-70b,gpt-5.5,claude-opus-4-7
```

### Ejecutar en CI/CD (ejemplo de GitHub Actions)

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

El comando termina con código 1 si la tasa de aprobación cae por debajo del 90%, haciendo fallar la build.

#### Códigos de salida

| Código | Significado |
|--------|-------------|
| `0` | Éxito. |
| `1` | Fallo de aserción - una o más aserciones no se cumplieron, una ejecución de `batch` no verificó nada, o un modelo se negó y dejó sin evaluar aserciones configuradas. Solo `batch` emite un veredicto de aserción; `compare` aún puede salir con `1` ante un error inesperado. |
| `2` | La ejecución no pudo completarse. |
| `3` | `--max-cost` detuvo la ejecución. Las llamadas ya iniciadas se dejaron terminar, por lo que la salida guardada contiene lo medido y marca las que nunca se ejecutaron. El límite acota los envíos posteriores, no el gasto ya comprometido. |
| `4` | `diff` encontró una diferencia. Un código propio porque todos los demás códigos distintos de cero significan que algo falló, mientras que un `diff` que informa de un cambio ha tenido éxito. Solo `diff` lo produce. |

El código `2` abarca varias causas distintas y **no distingue entre ellas**: una clave de API ausente, un modelo desconocido, un modelo retirado, un error del proveedor, un límite de coste superado, un archivo de lote mal formado, una combinación de flags rechazada, un conflicto con el archivo de salida o un límite de tamaño de lote superado.

Conviene conocer tres reglas antes de basar una canalización en esto:

- **Los fallos de llamada tienen prioridad sobre las aserciones.** Si falla alguna llamada al modelo, `batch` termina con `2` sin informar del veredicto de las aserciones, aunque estas también hayan fallado. Una suite en rojo y una clave de API inválida se ven igual desde el código de salida.
- **Un servidor local inaccesible no es un fallo.** `list-models --local` termina con `0` cuando ningún servidor responde, así que el código de salida no sirve para detectarlo.
- **Una negativa hace fallar la comprobación, sea cual sea la tasa de aprobación.** Una petición rechazada no produce salida contra la que aseverar, así que sus aserciones se registran como erróneas y quedan excluidas de la tasa - de modo que la tasa mostrada arriba describe solo las peticiones que fueron respondidas. `batch` termina con `1` cuando una negativa dejó alguna aserción configurada sin evaluar, incluso con una tasa del 100 %. El JSON indica cuántas en `total_assertions_refused`.

Para averiguar *por qué* falló una ejecución, lea el campo `error` de cada resultado en la salida JSON - contiene el mensaje del proveedor, con las cadenas con forma de credencial redactadas:

```bash
cli-modelarium batch ./eval/test_suite.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output-format json --output results.json
code=$?
if [ "$code" -eq 2 ]; then
  jq -r '.results[] | select(.error) | "\(.model): \(.error)"' results.json
fi
```

Una negativa no es un error - `error` permanece `null` en una petición rechazada, para que su coste siga contando en todos los totales, y lo que la reporta es el código de salida `1`, no el `2`. Por eso `select(.error)` no devuelve nada en la ejecución que una negativa puso en rojo. Para cubrir ambos casos:

```bash
jq -r '.results[] | select(.error or .refused)
       | "\(.model): \(.error // "refused: " + (.stop_category // "no category"))"' results.json
```

`--output-format json` es obligatorio: la salida por defecto no incluye ningún campo de error legible por máquina. Tenga en cuenta que los fallos que ocurren *antes* de llamar a un modelo (clave ausente, modelo desconocido, archivo de lote incorrecto) no producen JSON alguno; en esos casos el mensaje de consola es la única señal.

#### Identidad de la ejecución

Cada salida JSON lleva cuatro campos de nivel superior que dicen *qué ejecución* es. Antes de esta versión no podía: dos ejecuciones del mismo comando producían un JSON que se diferenciaba en `latency_ms` y `ttft_ms` y en nada más. Una prueba contra la versión publicada 0.1.9 midió exactamente ese par, con 93 segundos de diferencia, y la segunda ejecución fue la más rápida, de modo que incluso "mayor latencia se ejecutó antes" las habría ordenado al revés. La mtime del sistema de archivos era la única señal que quedaba, y no sobrevive a `git add`, a una copia, a una extracción tar ni a la subida de un artefacto.

| Campo | Qué es |
|-------|--------|
| `started_at` | Cuándo empezó la ejecución - ISO 8601 UTC, precisión de segundos, sufijo `Z`. Se toma antes de resolver las opciones y antes de cualquier llamada al proveedor, así que es una hora de inicio y no de finalización. |
| `run_id` | Un UUID que identifica esta ejecución. Sobrevive a copias y renombrados, y separa dos ejecuciones que empezaron en el mismo segundo. |
| `experiment_key` | Dieciséis caracteres hexadecimales de un SHA-256 sobre las entradas que definen el experimento. Dos salidas que comparten uno están midiendo lo mismo. |
| `invocation` | Las opciones resueltas: nombre del comando, lista de modelos, temperaturas, prompts de sistema y modelos juez. |

Los cuatro salen igual de `compare` y de `batch`, sin condiciones. Markdown lleva además `Started at` y `Run ID`; CSV no lleva ninguno, ya que la identidad es de la ejecución y CSV es de la fila.

```bash
# ¿Son siquiera comparables dos salidas?
[ "$(jq -r .experiment_key before.json)" = "$(jq -r .experiment_key after.json)" ] \
  && echo "mismo experimento" || echo "experimento distinto - no comparar"
```

`started_at` usa segundos y `Z` en lugar de microsegundos y `+00:00` porque `fromdateiso8601` de jq - lo primero a lo que recurre un monitor de shell - rechaza las otras dos formas.

**`invocation` registra lo que se ejecutó, no lo que usted escribió.** Una ejecución lanzada con `--models all-flagship` lista los ids a los que ese grupo se expandió, que es lo que necesita un consumidor: la pertenencia a un grupo es estado del registro y cambia entre versiones, así que el nombre por sí solo no permitiría a nadie reproducir la ejecución.

**Nada secreto puede llegar a `invocation`, y eso es una lista de permitidos y no una pasada de redacción.** El campo se construye a partir de cuatro claves nombradas, así que nada que no esté nombrado allí puede entrar. `--local-url` queda excluido porque puede llevar credenciales en la posición de userinfo (`http://user:pass@host/v1`), una forma en la que no cabe confiar en ningún comparador de patrones. Las rutas de archivo quedan excluidas porque una ruta revela un directorio personal y un nombre de usuario, mientras que el contenido que importa se registra de todos modos. Construir el campo a partir de una lista fija es la garantía más fuerte: una pasada de redacción tendría que reconocer todos los secretos que se le muestren, y esta no ve ninguno.

**Qué hashea `experiment_key`:** el nombre resuelto del comando, los prompts, la lista de modelos, las temperaturas, los prompts de sistema resueltos, los modelos juez y el número de ejecuciones. Los valores medidos quedan excluidos por construcción - latencia, coste y recuentos de tokens son las salidas que se comparan, y una clave que se moviera con ellos no coincidiría jamás. También el destino de salida, ya que `--output report.json` y `--output-format json` redirigido a stdout son el mismo experimento escrito dos veces. Las entradas están documentadas aquí y en la propia constante porque un hash con entradas desconocidas es peor que ningún hash: dos claves que difieren no le dicen nada a un consumidor si no sabe si cambió el experimento o cambió el hasheo. `EXPERIMENT_KEY_VERSION` existe por la misma razón, y se incrementa cuando cambian las entradas del hash, nunca por una edición cosmética.

**El número de ejecuciones está en la clave.** `--runs 1` y `--runs 10` sobre las mismas celdas no comparten una, deliberadamente: la segunda responde a una pregunta sobre la varianza que la primera no puede responder, así que un monitor que las juntara estaría comparando una estimación puntual con una distribución.

**La lista de modelos deliberadamente no se ordena.** Ordenarla haría que `--models a,b` y `--models b,a` compartieran clave, lo que es defendible sobre la base de que se miden las mismas celdas - pero `prompt_id` en `compare` es un ordinal de fila posicional, así que `p1` es un modelo distinto en cada una de esas dos ejecuciones. Un consumidor que las uniera por `(experiment_key, prompt_id)` desalinearía todas las filas mientras ambas claves coincidían. Un falso "distinto" cuesta una comparación omitida; un falso "igual" corrompe una en silencio. La lista de temperaturas conserva el orden dado por la misma razón.

**Un `experiment_key` idéntico no significa resultados idénticos.** Medido en vivo sobre `gemini-3.8-flash`: dos invocaciones idénticas en todo lo que la clave puede ver devolvieron el mismo texto de salida - `Paris` las dos veces - con 65 y luego 58 tokens de salida, con un coste de `$0.00025125` y luego `$0.000225`. A lo largo de las ocho ejecuciones que devolvieron un resultado `output_tokens` abarcó de 58 a 66 con una entrada fija de 10, porque los tokens internos de un modelo de razonamiento varían de una llamada a otra. Esas ocho son el barrido completo y no una selección de él: el 2026-09-06 se hicieron catorce intentos y seis devolvieron 503, quedando como celdas muertas con cero tokens de las que no se puede tomar ningún rango. Que el coste se mueva entre dos ejecuciones de un mismo experimento es por tanto normal, y no es prueba de que algo haya cambiado. Eso es un argumento *a favor* de la clave y no en contra: dos ejecuciones que difieren en coste todavía pueden reconocerse como el mismo experimento, que es lo que hace falta antes de poder preguntar si la diferencia significa algo.

#### Comparar dos ejecuciones

`diff` lee dos salidas JSON que usted ya tiene e informa de lo que se ha movido. No escribe nada, no almacena nada y no vigila nada.

```bash
cli-modelarium compare "capital of France?" --models gpt-5.5,claude-opus-4-8 --output before.json
# ... más tarde ...
cli-modelarium compare "capital of France?" --models gpt-5.5,claude-opus-4-8 --output after.json

cli-modelarium diff before.json after.json
```

<p align="center">
  <img src="docs/assets/cli-modelarium-diff-demo-4model.gif" alt="Demo en terminal de cli-modelarium: la misma comparación se ejecuta dos veces sobre claude-fable-5-1, gemini-3.8-flash, gemini-3.7-flash y claude-haiku-4-5, y luego diff informa de que el texto de cada respuesta no cambió mientras el coste se mueve en las dos filas de Gemini y permanece plano en las dos de Claude." width="1088">
</p>

**El orden de los argumentos fija la dirección.** El primer archivo se lee como la ejecución anterior, digan lo que digan las marcas de tiempo. Nada en una salida puede ordenar dos ejecuciones escritas en el mismo segundo - `started_at` tiene precisión de segundos y `run_id` es un UUID aleatorio sin componente temporal -, así que la regla siempre disponible es la que usted escribió. Cuando `started_at` lo contradice, `diff` lo dice y continúa.

Compara celdas, no archivos. Dos filas pueden compartir modelo, temperatura y prompt de sistema, porque `--temperatures 0,0` pide la misma celda dos veces; por eso la unión cuenta además la posición de cada fila dentro de su propio grupo de celdas. Las celdas sin cambios se ocultan; `--all` las muestra.

**Cada celda mostrada indica, antes que sus números, si el texto de la respuesta cambió.** Un modelo de razonamiento devuelve rutinariamente el mismo texto con un coste de tokens distinto, así que "el coste se movió y la respuesta no" es la lectura habitual; y una respuesta distinta con el mismo número de tokens no habría movido nada y habría quedado oculta. Es igual o no igual, nunca una puntuación de similitud: un porcentaje ahí sería un número que la salida no contiene. Si un lado rechazó, falló o fue detenido, no hay respuesta que comparar y el comando lo dice.

**Qué rechaza:** un prompt distinto, un número de ejecuciones distinto (una ejecución es una estimación puntual y diez son una distribución) y una salida de `batch` frente a una de `compare`. Añadir o quitar un modelo no es un rechazo: las celdas coincidentes siguen siendo comparables y las que solo se ejecutaron en un lado se listan aparte.

**Qué matiza en lugar de rechazar:** dos salidas calculadas con tablas de tarifas distintas siguen siendo comparables, pero parte de la diferencia de coste es la lista de precios y no los modelos, así que eso se dice antes de cualquier cifra de coste. Una ejecución truncada, un modelo juez distinto y una salida anterior a 0.2.0 se señalan igual. Una salida antigua se compara de todos modos, emparejando el contenido de las filas, y `diff` nombra las dos cosas que esa forma no puede decirle: qué comando escribió la salida y qué jueces se ejecutaron.

Los veredictos de significancia se imprimen de ambos lados y nunca se restan. Un valor p describe una muestra, de modo que dos procedentes de ejecuciones independientes son ambos ciertos y su diferencia no es una magnitud que ninguno de los dos contenga.

`--output-format json` lleva todas las celdas, cambiadas o no, las seis métricas y todos los matices. La consola muestra coste, latencia y tokens de salida de las celdas que se movieron. Los códigos de salida están en la tabla de arriba: nada se movió es `0`, algo se movió es `4` y un par no comparable es `2`.

**Nota de privacidad:** todos los formatos de salida - JSON, CSV y Markdown - incluyen el prompt completo, el prompt de sistema completo y la respuesta completa del modelo de cada resultado, junto con cualquier mensaje de error del proveedor. JSON incluye además el texto de razonamiento de cada juez; `--include-reasoning` solo controla la visualización en consola, no el archivo, y CSV y Markdown no lo contienen. Trate cualquier archivo de salida como información sensible antes de confirmarlo o subirlo como artefacto público de CI. Las condiciones de retención de datos y de entrenamiento difieren entre proveedores, esta herramienta no afirma nada sobre ninguna de ellas, y conviene revisar las condiciones de cada proveedor que configure. Claude Fable 5.1 requiere una retención de 30 días y no está disponible con retención cero de datos. Un modelo juez es un segundo proveedor: `--judge` le envía su prompt además de la respuesta del modelo, de modo que juzgar amplía quién ve el prompt. Una solicitud que el primer modelo rechaza ya no se envía a ningún juez. Un informe de `compare` también registra el entorno que lo produjo - la versión de la herramienta, la versión exacta de `scipy` instalada y la versión completa de Python - en el bloque `methodology` de JSON y Markdown, con cualquier número de ejecuciones. Son metadatos del host, no sus datos, pero fijan con precisión una versión de dependencia. CSV no incluye nada de esto y `batch` no registra nada de esto.

## Configuración

### Claves de API

Cli Modelarium almacena las claves de API en el llavero nativo de su SO (Mac Keychain, Windows Credential Manager o Linux Secret Service a través de `keyring`). Las claves nunca tocan el disco en texto plano.

```bash
# Configuración interactiva (recomendada)
cli-modelarium configure

# O establezca individualmente
cli-modelarium keys set openai
cli-modelarium keys set anthropic
cli-modelarium keys set google

# Comprobar qué claves están configuradas
cli-modelarium keys list

# Eliminar una clave
cli-modelarium keys delete openai
```

También puede usar variables de entorno (útil para CI/CD):

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
```

Las variables de entorno tienen prioridad sobre el almacenamiento del llavero.

### Modelos locales (Ollama, LM Studio, etc.)

Los modelos locales funcionan a través de endpoints compatibles con OpenAI - no se necesitan claves de API. La herramienta detecta automáticamente el puerto predeterminado de Ollama.

```bash
# Predeterminado: asume Ollama en localhost:11434
cli-modelarium "test" --models local/llama-3.3

# Usar LM Studio en su lugar
cli-modelarium "test" --models local/qwen-3-32b --local-url http://localhost:1234/v1

# Guardar una URL local personalizada como predeterminada
cli-modelarium keys set local --base-url http://localhost:1234/v1
```

## Proveedores compatibles

| Proveedor | Claves de API Necesarias | Streaming | Seguimiento de Costos | Precios verificados |
|----------|-----------------|-----------|---------------|------------------|
| OpenAI (GPT-6 Astra, GPT-5.6 Sol, GPT-5.5, o3, etc.) | ✅ | ✅ | ✅ | `first-party` |
| Anthropic (Claude Opus 5, Sonnet 5, Fable 5.1, Haiku 4.5, etc.) | ✅ | ✅ | ✅ | `first-party` |
| Google (Gemini 3.8 Flash, 3.7 Flash, 3.1 Pro, etc.) | ✅ | ✅ | ✅ | `first-party` |
| xAI (Grok 4.6, Grok 4.3, etc.) | ✅ | ✅ | ✅ | `first-party` |
| DeepSeek (V4 Pro, V4 Flash, etc.) | ✅ | ✅ | ✅ | `first-party` |
| Mistral (Medium, Large, Small, Codestral) | ✅ | ✅ | ✅ | `first-party` |
| Groq (Llama 3.3, Llama 4 Scout, gpt-oss) | ✅ | ✅ | ✅ | `third-party` |
| OpenRouter (8 IDs registrados: Qwen, DeepSeek R1, Llama 3.3, gpt-oss, GLM) | ✅ | ✅ | ✅ | `unchecked` |
| Alibaba/DashScope (Qwen3.8 Max, Qwen3.7 Max, Qwen3 Coder, etc.; modelos Qwen seleccionados, Internacional/Singapur) | ✅ | ✅ | ✅ | `first-party` |
| Z.AI/GLM (GLM-5.3, GLM-5.2, GLM-4.7, etc.; compatible con OpenAI, endpoint internacional) | ✅ | ✅ | ✅ | `first-party` |
| NVIDIA NIM (9 IDs registrados: Nemotron, Gemma 4, Mistral Nemotron, MiniMax M3, Laguna, Llama 3.1) | ✅ | ✅ | Sin tarifa publicada | `unpublished` |
| Moonshot AI / Kimi (4 IDs registrados: K3, K2.7 Code, K2.7 Code HighSpeed, K2.6) | ✅ | ✅ | ✅ | `reseller` |
| **Local: Ollama** | ❌ | ✅ | Gratis | — |
| **Local: LM Studio** | ❌ | ✅ | Gratis | — |
| **Local: vLLM** | ❌ | ✅ | Gratis | — |
| **Local: llama.cpp server** | ❌ | ✅ | Gratis | — |

Ejecute `cli-modelarium list-models` para ver todos los modelos actualmente soportados.

## Grupos de modelos

En lugar de listar IDs de modelos, `--models` acepta un atajo de grupo. Los grupos estáticos se expanden literalmente: se ejecutan todos los miembros listados a continuación, por lo que necesita una clave para cada proveedor que abarque el grupo, y la ejecución se aborta ante la primera que falte. Los grupos dinámicos `all` y `all-local` son la excepción: esos se resuelven según lo que realmente tenga configurado.

**Grupos estáticos** (membresía fija):

| Grupo | Modelos |
|-------|---------|
| `all-premium` / `all-flagship` | gpt-5.6-sol, claude-opus-5, gemini-3.1-pro-preview, grok-4.6, deepseek-v4-pro, mistral-large-latest, qwen3.8-max, glm-5.2 |
| `all-budget` | gpt-5.4-nano, claude-haiku-4-5, gemini-3.1-flash-lite, grok-4.20-0309-non-reasoning, deepseek-v4-flash, mistral-small-latest, qwen3.7-plus, glm-4.5-air |
| `all-reasoning` | o3, o4-mini, deepseek-v4-pro, glm-5.2 |
| `all-cheap` | gpt-4o-mini, claude-haiku-4-5, gemini-2.5-flash-lite, deepseek-v4-flash, mistral-small-latest, qwen-flash, glm-4.7-flashx |
| `all-open-weight` | openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, llama-3.3-70b-versatile, meta-llama/llama-4-scout-17b-16e-instruct |

**Grupos dinámicos** (resueltos en tiempo de ejecución):

- `all` — todos los modelos en la nube para los que tenga una clave de API configurada (excluye los modelos locales, OpenRouter y NVIDIA: estos dos últimos son un subconjunto registrado y no el catálogo completo del proveedor, y el costo de NVIDIA no se puede indicar). Esto puede expandirse a muchos modelos, así que combínelo con `--max-cost`.
- `all-local` — todos los modelos reportados por su servidor local en ejecución (Ollama / LM Studio / vLLM / llama.cpp). Si no se puede acceder a ningún servidor, obtendrá un mensaje claro en lugar de un error.

```bash
cli-modelarium "Explica el teorema CAP" --models all-budget
cli-modelarium "Explica el teorema CAP" --models all --max-cost 0.50
cli-modelarium "Explica el teorema CAP" --models all-local
```

## Cómo funciona

Cli Modelarium usa una capa de abstracción de proveedor modular que oculta las diferencias de API entre el array `messages` de OpenAI, el parámetro `system` de nivel superior de Anthropic, el `system_instruction` de Google y otros. Cada proveedor implementa la misma interfaz de streaming asíncrono, por lo que la CLI puede ejecutarlos todos en paralelo con `asyncio.gather()`.

Los cálculos de costos provienen del campo `usage` reportado por cada proveedor (tokens de entrada, tokens de salida, tokens en caché) multiplicado por las constantes de precios actuales. La mayoría de los datos de precios fueron verificados desde la documentación oficial del proveedor el **6 de septiembre de 2026**; cuatro proveedores no se cubrieron por completo - vea [Notas y Limitaciones](#notas-y-limitaciones).

Para los modelos locales, se usa el mismo SDK de Python de OpenAI con una `base_url` personalizada, ya que Ollama, LM Studio, vLLM y llama.cpp exponen endpoints REST compatibles con OpenAI.

## Notas y Limitaciones

### Datos de precios

La mayoría de los precios incorporados en Cli Modelarium fueron verificados desde la documentación oficial del proveedor el **6 de septiembre de 2026**. Algunas entradas llevan su propia fecha de verificación, indicada junto a cada una en el registro. Groq, Moonshot, NVIDIA y OpenRouter no se verificaron por completo en esa pasada y están marcados como no verificados en el registro. Se sabe que dos conjuntos de tarifas expiran: `gemini-3.6-flash`, `gemini-3.7-flash` y `gemini-3.8-flash` tienen tarifas introductorias que se duplican el 1 de enero de 2027, y `gpt-5.6-sol` tiene una tarifa promocional que termina alrededor del 21 de noviembre de 2026. Ambas hacen que una comparación ejecutada hoy parezca más barata de lo que será más adelante, y ambas cambian de forma uniforme, por lo que nada en la salida resulta llamativo. Los precios de los LLM cambian con frecuencia (a veces mensualmente). La fecha `pricing_as_of` se incluye en la salida JSON y Markdown y se muestra en la consola; la salida CSV no la incluye. Verifique siempre con la página oficial de precios de cada proveedor antes de confiar en los cálculos de costos para presupuestos o decisiones de producción.

Los precios son la tarifa pública estándar/de lista de cada proveedor por cada 1M de tokens (no precios por lotes, prioritarios, de horas valle ni promocionales, con una excepción anotada: `gpt-5.6-sol`, cuya tarifa publicada actual es promocional); para los modelos con niveles según el tamaño de entrada se muestra el nivel de entrada/contexto corto, y el precio en caché es la tarifa de lectura de caché. Los costos de DashScope/Qwen reflejan las tarifas sin razonamiento (la herramienta envía `enable_thinking=false`).

NVIDIA NIM es la excepción. NVIDIA no publica ninguna tarifa por token para sus endpoints NIM alojados, por lo que el costo no se registra para los modelos de NVIDIA: el cero que aparece en la columna de costo es la ausencia de una tarifa, no un precio de cero. Como ese costo siempre es cero, `--max-cost` nunca se activará con un modelo de NVIDIA y una aserción `cost_under` siempre se aprobará; ninguno de los dos le ofrece protección de gasto en este proveedor. El acceso se mide en créditos de la cuenta en lugar de facturarse por token, así que lo que hay que vigilar es agotar los créditos, no una factura inesperada. Se muestra un panel de advertencia siempre que un modelo de NVIDIA forma parte de una ejecución.

Ejecute `cli-modelarium pricing` (o `pricing --all`) para obtener las tarifas actuales por modelo.

### Límites de velocidad

El manejo de los límites de velocidad y las configuraciones de concurrencia predeterminadas por proveedor se basan en los límites de velocidad del proveedor verificados el **21 de junio de 2026**. Los límites de su nivel específico pueden diferir de los predeterminados asumidos aquí. Verifique sus límites actuales con el panel oficial del proveedor antes de construir suposiciones de capacidad de producción.

### Disponibilidad del modelo

Los modelos soportados por Cli Modelarium reflejan lo que los proveedores ofrecían el **15 de agosto de 2026**. Los proveedores lanzan regularmente nuevos modelos, descontinúan los antiguos y ajustan las capacidades. Si un modelo en el registro ya no funciona, ejecute `cli-modelarium list-models` y consulte la documentación del proveedor.

### No es una pasarela de grado de producción

Cli Modelarium está diseñado para evaluación y comparación - ejecutando pruebas ad-hoc lado a lado entre proveedores desde una terminal de desarrollador. NO es una pasarela de inferencia de producción. Si necesita enrutamiento a escala de producción, balanceo de carga, cadenas de fallback o inferencia administrada por SLA, busque herramientas construidas específicamente para ese propósito.

### Comparaciones de conteo de tokens entre proveedores

Los conteos de tokens mostrados en los resultados son reportados por la API de cada proveedor. Diferentes proveedores usan diferentes tokenizadores, por lo que "tokens de salida" no es directamente comparable entre proveedores para el mismo texto. Si está comparando la eficiencia de costos para uso en producción, ejecute prompts reales en su carga de trabajo real - no confíe únicamente en cálculos por token entre proveedores.

### Uso de LLM-as-a-Judge

Cli Modelarium incluye una puntuación LLM-as-a-judge opcional (habilitada con el flag `--judge`), que usa un LLM para evaluar las salidas de otros LLMs. Esta es una metodología de benchmarking estándar y está permitida bajo los Términos de Servicio de todos los proveedores soportados como actividad de evaluación/benchmarking.

Al usar `--judge`, usted es responsable de cumplir con los Términos de Servicio de cada proveedor cuyos modelos use. Los ToS de cada proveedor se aplican tanto a los modelos siendo juzgados como al modelo juez en sí.

**Aviso de sesgo del juez:** Los jueces LLM tienen sesgos documentados (preferencia propia, preferencia por la misma familia, preferencia por la verbosidad). Las puntuaciones del juez son una señal útil, no una verdad fundamental. Use paneles de jueces (`--judges` con múltiples modelos) para reducir el sesgo.

### Detección de alucinaciones

El preset de detección de alucinaciones es una señal de comparación útil entre modelos, no una validación de verdad fundamental. La precisión de la detección varía según el modelo juez utilizado, el conocimiento del dominio requerido y si se proporcionan hechos de referencia a través de `--expected-facts`. Úselo para comparación de calidad relativa, no para verificación de corrección absoluta.

### Metodología de comparación

Los LLMs son no deterministas a temperatura > 0 - volver a ejecutar el mismo prompt puede producir salidas diferentes. Una sola ejecución de comparación le muestra UNA muestra de cada modelo, no un veredicto de calidad definitivo.

Para sacar conclusiones más confiables:
- Use `--runs 5` (o más) para ejecutar automáticamente cada comparación N veces y ver resúmenes estadísticos: latencia media, coeficiente de variación, salida modal y diversidad de salida. Un coeficiente de variación por debajo de 0,05 indica un comportamiento estable del modelo entre ejecuciones.
- Para el análisis de consistencia de alucinaciones, combine `--runs` con `--check-hallucination` para ver con qué frecuencia el modelo produce alucinaciones a lo largo de varias ejecuciones (la tasa de alucinación).
- Use `--temperatures 0` para salidas más deterministas. Algunos modelos no aceptan ninguna configuración de temperatura - `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `claude-fable-5-1`, `o3`, `o4-mini`, `gpt-5`, `gpt-5.5`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-6-astra`, `gemini-3.8-flash`, `kimi-k3`, `kimi-k2.7-code`, `kimi-k2.7-code-highspeed` y `kimi-k2.6`. La herramienta omite el campo para ellos, de modo que la llamada sigue funcionando, y se ejecutan con el valor predeterminado de su proveedor.
- Use `--system-prompts "Sé breve.,Sé detallado."` para ejecutar el mismo prompt con varios prompts de sistema y compararlos en paralelo. Multiplica el número de llamadas igual que `--models` y `--temperatures`. Cuando hay más de uno, los informes etiquetan cada fila como `SP 1`, `SP 2`, etc., e imprimen una leyenda con el texto completo: `SP 2` en el resumen por celda es el mismo prompt que `SP 2` en la tabla anterior. CSV y JSON llevan el prompt de sistema completo en cada fila.
- Compare entre múltiples prompts, no solo uno
- Use el flag `--output-format json` para guardar ejecuciones para análisis sistemático (con `--runs > 1` el JSON incluye agregados `stats_by_cell` por celda)

Esos diecinueve modelos se invocan sin el campo de temperatura, y `models_without_temperature` en la salida JSON nombra los afectados en cada ejecución. Conviene conocer tres consecuencias. Un barrido `--temperatures` con varios valores emite peticiones idénticas en lugar de un barrido real contra esos modelos, y la herramienta muestra una advertencia cuando eso ocurre. La temperatura que aparece en la tabla de resultados, en el CSV y en cada registro de resultado JSON es el valor **solicitado**, no el aplicado. Y `--significance` es donde esto puede cambiar una conclusión en lugar de una etiqueta: comparar un modelo que omite la temperatura con otro que la respeta produce una diferencia de varianza que es un artefacto de muestreo, y Welch o Mann-Whitney la reportarán como si fuera una diferencia de calidad entre modelos. Ese caso sí avisa: cualquier ejecución de significancia que mezcle un modelo afectado con uno no afectado imprime un panel `Temperature not applied` que nombra los modelos que corrieron con la temperatura por defecto del proveedor, y pone `significance_temperature_mixed` en `true` en la salida JSON. Una ejecución con varias temperaturas que además sea mixta recibe ambos mensajes en un único panel. El CSV no incluye una señal equivalente.

## Sobre el proyecto

Cli Modelarium es un producto de **SoraVantia GK**. Fue creado originalmente por **Lavelle Hatcher Jr**, quien continúa manteniéndolo.

- 📦 Repositorio: [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium)
- 💬 Preguntas o errores: [abra un issue](../../issues)
- 🔧 Mantenedor: [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

## Por qué lo construí

Comparar salidas de LLM entre proveedores es tedioso - diferentes SDKs, diferentes patrones de autenticación, diferentes formas de respuesta, ninguna manera fácil de verlos lado a lado con datos de costo y latencia. Los pulidos playgrounds en la nube solo muestran un proveedor a la vez, y las opciones de código abierto disponibles se enfocan en el enrutamiento de producción o son plataformas de evaluación completas optimizadas para equipos.

Cli Modelarium es la pequeña herramienta CLI enfocada que hace bien una cosa: comparación lado a lado con puntuación de calidad, aserciones, modo por lotes y streaming - todo diseñado para el flujo de trabajo del desarrollador centrado en la terminal.

Está intencionalmente enfocado: sin enrutamiento de producción, sin orquestación de agentes, sin ajuste fino, sin GUI. Solo comparación limpia y rápida desde la línea de comandos.

Construido con una abstracción de proveedor modular, ejecución paralela, cálculo de costos transparente y almacenamiento seguro de claves a través de sistemas de llavero del SO para usuarios locales.

## Contribuyendo

Issues y PRs bienvenidos. Vea [CONTRIBUTING.md](CONTRIBUTING.md) para las pautas.

Para problemas de seguridad, por favor vea [SECURITY.md](SECURITY.md) - no presente issues públicos por preocupaciones de seguridad.

## Licencia

Licenciado bajo la [Apache License, Version 2.0](LICENSE).

Vea el archivo [NOTICE](NOTICE) para los requisitos de atribución.

---

Un producto de SoraVantia GK, creado y mantenido por [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

Licenciado bajo Apache 2.0. Issues, PRs y conversaciones bienvenidos.
