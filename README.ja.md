<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/cli-modelarium-wordmark-dark.svg">
  <img alt="cli modelarium" src="docs/assets/cli-modelarium-wordmark-light.svg" width="420">
</picture>

他の言語で読む: [English](README.md) | [Español](README.es.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [中文](README.zh.md) | [Deutsch](README.de.md) | [Português](README.pt.md) | [Italiano](README.it.md)

注: このREADMEはアクセシビリティのために翻訳されています。Cli Modelarium CLI ツール自体は英語のみで出力されます。すべてのコマンド、エラーメッセージ、出力は、システムロケールに関係なく英語のままです。

> 注: 次の7つのセクションは英語版 README にのみ存在します — *Reproducibility analysis*、*Statistical significance testing*、*Bootstrap confidence intervals*、*Paired tests for same-prompt comparisons*、*McNemar's test for hallucination significance*、*Headless Linux servers*、*More examples*。機能自体はすべて利用可能で、ここに欠けているのはその説明だけです。[README.md](https://github.com/SoraVantia/cli-modelarium/blob/main/README.md) を参照してください。

> 12のクラウドプロバイダー＋ローカルモデルのLLM出力をターミナルから横並びで比較。並列ストリーミング、バッチ評価、LLM-as-judgeスコアリング、ハルシネーション検出、CI/CD対応のアサーション機能を搭載。

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

## 概要

**Cli Modelarium** は、プロバイダー、モデル、システムプロンプト、温度パラメータ間でLLM出力を比較するための洗練されたコマンドラインツールです。ライブ並列ストリーミング、バッチ評価、決定論的テスト、品質スコアリングが組み込まれています。

特定のタスクに適したモデルの評価、CI/CDでのプロンプト回帰テストの実行、ローカルモデルとクラウドAPIの比較、評価データセットの構築などに役立ちます。すべて1つのターミナルコマンドから実行できます。

## システム要件

- Python 3.11 以上（Python 3.10 のユーザーは `cli-modelarium==0.1.1` をインストールしてください）
- 約 350 MB のディスク容量（うち約 3 分の 2 が scipy と numpy）
- macOS（Apple Silicon および Intel）、Windows 10+（x64 および ARM）、Linux（x64 および ARM）
- 初回インストール時のインターネット接続（PyPI ホイールのダウンロード）

## クイックスタート

```bash
pip install cli-modelarium

# APIキーを設定（OSキーチェーンに安全に保存されます）
cli-modelarium configure

# 初めての比較を実行
cli-modelarium "Explain quantum computing in one sentence" \
  --models gpt-5.5,claude-opus-4-8,gemini-3.1-pro-preview \
  --temperatures 0,0.7
```

これだけです。3つのモデルすべてがレスポンスを並列でライブストリーミングし、レイテンシー、トークン数、コストがクリーンな比較テーブルに表示されます。

## 機能

### 🤖 プロバイダー（12のクラウド＋無制限のローカル）

- **クラウドプロバイダー:** OpenAI、Anthropic、Google (Gemini)、xAI (Grok)、DeepSeek、Mistral、Groq、OpenRouter、Alibaba (DashScope)、Z.AI (GLM)、NVIDIA (NIM), Moonshot AI (Kimi)
- **ローカルモデル:** Ollama、LM Studio、vLLM、llama.cpp - localhost で実行される任意の OpenAI 互換サーバー
- 同じ比較内でローカルモデルとクラウドモデルを混在可能
- 呼び出しごとに登録済みの任意のモデル ID を選択可能 - 組み込みのグループショートカットに限定されません

### ⚡ 並列ストリーミング

- すべてのモデルにわたって同時にトークン単位でライブ表示
- モデルごとのTime-to-First-Token (TTFT) トラッキング
- どのモデルが最初に終了するかを確認し、出力の分岐をリアルタイムで観察
- 12のプロバイダーすべてからストリーミング（内部ではSSEを使用）

<p align="center">
  <img src="docs/assets/cli-modelarium-comparison-demo.gif" alt="cli-modelarium のターミナルデモ: 3つのモデルが同じプロンプトへのレスポンスを並列でライブストリーミングし、続いて比較テーブルにモデルごとの Time-to-First-Token、レイテンシー、トークン数、コストが表示されます。" width="718">
</p>

**料金に関する注意:** デモに表示されるコストは録画時点の単一実行のものです。料金は変更されます。いずれの数値も、依拠する前に必ず各プロバイダーで確認してください。

### 📊 複数の比較モード

- **単一プロンプト vs. 複数モデル** - 「どれが最良か？」を素早く比較
- **単一プロンプト vs. 複数の温度パラメータ** - ランダム性が出力に与える影響を確認
- **複数のシステムプロンプト vs. 単一のユーザープロンプト** - プロンプトエンジニアリングのA/Bテスト
- **バッチモード** - 実際の評価作業のためのマルチプロンプト × マルチモデル
- **ローカル vs. クラウドの比較** - ギャップ（あるいはその欠如）を定量化

### 🧪 評価機能

- **統計的再現性分析** - `--runs N` は各構成をN回実行し、レイテンシとトークンの平均値/中央値/標準偏差/変動係数、出力頻度、最頻出力、出力の多様性を報告します。`--check-hallucination` と組み合わせると、複数回の実行にわたるハルシネーション率を測定できます。
- **決定論的アサーション** - 10種類のアサーションタイプ（`contains`、`regex`、`json_valid`、`json_schema`、`max_length_chars`、`latency_under`、`cost_under` など）、合格/不合格の出力とCI終了コード
- **LLM-as-a-judge スコアリング** - 1つのLLMを使用して、他のLLMの出力を品質基準に基づいて評価
- **ジャッジパネル** - 複数のジャッジでスコアを平均化し、バイアスの少ない評価を実現
- **ハルシネーション検出プリセット** - 事実の正確性チェックのための、すぐに使える基準
- **カスタム基準** - 独自のスコアリングルーブリックを定義
- **自己評価の自動スキップ** - ジャッジモデルが評価対象でもある場合、自動的にスキップされます

<p align="center">
  <img src="docs/assets/cli-modelarium-runs-demo.gif" alt="cli-modelarium のターミナルデモ: 同じプロンプトを2つのモデルで複数回繰り返し、続いて変動係数、ブートストラップ信頼区間、およびペアごとの統計的有意性の判定が表示されます。" width="1428">
</p>

### 💾 出力フォーマット

- **ライブターミナル** - プログレスバーとストリーミング表示を備えたRichベースのパネル
- **CSV** - スプレッドシート対応（Excel、Google Sheets、pandasで開く）
- **JSON** - スクリプトとパイプライン向けに構造化
- **Markdown** - ブログ記事やレポート向けの美しいテーブル
- **終了コード** - CI/CD向けに合格/不合格ステータスを反映する 0/1/2

### 💰 コスト透明性

- 各プロバイダーが報告する使用状況からの呼び出しごとのコスト表示
- 比較ごとの合計コストサマリー
- LLM-as-judgeが有効な場合、ジャッジコストを別途表示
- ローカルモデルは「Free」と表示
- 予期せぬ請求を防ぐ `--max-cost` フラグ

### 🔒 セキュリティ

- APIキーは `keyring` 経由でOSネイティブのキーチェーンに保存（Mac Keychain、Windows Credential Manager、Linux Secret Service）
- 形式検証により、保存前にペーストエラーをキャッチ
- エラーメッセージのリダクションにより、トレースバックでのキーリークを防止
- ローカルモデルURLのlocalhost専用検証
- 責任ある開示ポリシーを記載した `SECURITY.md`

### 🛡️ レート制限処理

- プロバイダーごとの同時実行制限（デフォルト5）- 全プロバイダーに同じ値が適用されるため、ご自身のティアと照らして確認してください
- 指数バックオフによる自動429リトライ
- Anthropicの529「overloaded」はレート制限とは別に処理
- 上位ティアのパワーユーザー向けの `--concurrency` フラグ
- モデルごとの優雅な失敗処理（他のモデルは継続）
- DashScopeの無料ティアおよびフラッグシップのQwen (qwen3.7-max) のレート制限は、ほとんどのプロバイダーよりも厳しくなっています。429に遭遇した場合は `--concurrency` を下げてください。
- Moonshot は利用前に最低 1 ドルのチャージが必要で、無料ティアはありません。Tier0 は同時リクエスト1件、毎分3リクエスト、1日150万トークンです。累計10ドルのチャージで Tier1 になります。Tier0 では `--concurrency` を下げてください。

### 🌐 クロスプラットフォーム

- macOS、Windows（10+およびARM）、Linuxで同一の動作
- すべてのファイルI/Oは `pathlib` + 明示的なUTF-8エンコーディングを使用
- CSV書き込みはWindows互換性のため `newline=""` を使用
- Python 3.11+ が必要

### 📋 開発者体験

- **シングルCLIバイナリ** - `pip install cli-modelarium` で完了
- **洗練されたRichベースのUI** - Claude Codeレベルのターミナルポリッシュ
- **JSON出力** - 何にでもパイプ可能（`jq`、スクリプト、モニタリング）
- **CI/CD対応** - 終了コード、構造化出力、GitHub Actionsのサンプル付属
- **Apache 2.0 ライセンス** - 商用・非商用を問わず、あらゆるプロジェクトで使用可能

## 例

### コーディングタスクで3つのモデルを比較

```bash
cli-modelarium "Write a Python function to find the longest palindromic substring" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview
```

### アサーション付きバッチ評価

`eval.json` を作成:

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

実行:

```bash
cli-modelarium batch eval.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output results.csv
```

### LLMジャッジによる出力のスコアリング

```bash
cli-modelarium "Explain recursion in one paragraph" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview,local/llama-3.3-70b \
  --judge claude-opus-4-7 \
  --judge-criteria "accuracy,clarity,brevity"
```

<p align="center">
  <img src="docs/assets/cli-modelarium-judge-demo.gif" alt="cli-modelarium のターミナルデモ: LLMジャッジが2つのモデルを採点し、比較テーブルにモデルごとのスコアが表示された後、各回答の下にジャッジの記述による評価理由が表示されます。" width="848">
</p>

**デモに関する注意:** スコアとコストは録画時点の単一実行のものです。ジャッジのスコアは参考信号であり、正解ではありません。実行ごと、モデルバージョンごとに正確には再現されません。料金は変わります。数値に依拠する前にプロバイダーで確認してください。

### 既知の事実に対するハルシネーション検出

```bash
cli-modelarium "Tell me about the Eiffel Tower" \
  --models gpt-5.5,claude-opus-4-7 \
  --judge claude-opus-4-7 \
  --check-hallucination \
  --expected-facts "Built 1887-1889,Located in Paris France,Designed by Gustave Eiffel"
```

### ローカルモデルとクラウドAPIの比較

```bash
# まずOllamaを起動: ollama run llama3.3
cli-modelarium "Summarize the key features of microservices architecture" \
  --models local/llama-3.3-70b,gpt-5.5,claude-opus-4-7
```

### CI/CDで実行（GitHub Actionsの例）

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

合格率が90%を下回ると、コマンドは終了コード1で終了し、ビルドが失敗します。

#### 終了コード

| コード | 意味 |
|--------|------|
| `0` | 成功。 |
| `1` | アサーション失敗 - 1つ以上のアサーションが通らなかった、または `batch` の実行が何も検証しなかった。アサーションの判定を出すのは `batch` のみですが、`compare` も予期しないエラーでは `1` で終了することがあります。 |
| `2` | 実行を完了できなかった。 |

コード `2` は複数の異なる原因を含み、**それらを区別しません**。APIキーの未設定、未知のモデル、提供終了したモデル、プロバイダーのエラー、コスト上限の超過、不正な形式のバッチファイル、許可されないフラグの組み合わせ、出力ファイルの競合、バッチサイズ上限の超過のいずれもコード `2` になります。

パイプラインをこれらのコードで制御する前に、次の2点を把握しておいてください。

- **呼び出しの失敗はアサーションより優先されます。** モデル呼び出しが1つでも失敗すると、`batch` はアサーションの判定を報告せずに `2` で終了します。アサーションも失敗していた場合でも同じです。テストスイートの失敗と無効なAPIキーは、終了コードからは区別できません。
- **ローカルサーバーに到達できないことは失敗ではありません。** サーバーが応答しない場合でも `list-models --local` は `0` で終了するため、終了コードでサーバーの有無を判定することはできません。

実行が*なぜ*失敗したかを知るには、JSON出力の各結果にある `error` フィールドを読んでください。プロバイダーのメッセージが入り、認証情報らしき文字列は伏字にされます。

```bash
cli-modelarium batch ./eval/test_suite.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output-format json --output results.json
code=$?
if [ "$code" -eq 2 ]; then
  jq -r '.results[] | select(.error) | "\(.model): \(.error)"' results.json
fi
```

`--output-format json` が必要です。デフォルトの出力には機械可読なエラーフィールドがありません。なお、モデルを呼び出す*前*に発生した失敗（キーの未設定、未知のモデル、不正なバッチファイル）ではJSONがまったく生成されないため、その場合はコンソールのメッセージが唯一の手がかりになります。

**プライバシーに関する注意:** JSON、CSV、Markdown のいずれの出力形式にも、各結果のプロンプト全文とモデル応答全文、さらにプロバイダーのエラーメッセージが含まれます。JSON にはさらに各ジャッジモデルの推論テキストが含まれます。`--include-reasoning` はコンソール表示のみを制御し、ファイルには影響しません。CSV と Markdown には含まれません。出力ファイルをコミットしたり、公開されるCIアーティファクトとしてアップロードしたりする前に、機密情報として扱ってください。 データの保持や学習に関する条件はプロバイダーごとに異なります。本ツールはそのいずれについても主張しません。設定する各プロバイダーの規約をご確認ください。Claude Fable 5.1 は 30 日間のデータ保持を必要とし、ゼロデータリテンションでは利用できません。

## 設定

### APIキー

Cli Modelarium はAPIキーをOSネイティブのキーチェーン（Mac Keychain、Windows Credential Manager、`keyring` 経由のLinux Secret Service）に保存します。キーが平文でディスクに触れることはありません。

```bash
# インタラクティブセットアップ（推奨）
cli-modelarium configure

# または個別に設定
cli-modelarium keys set openai
cli-modelarium keys set anthropic
cli-modelarium keys set google

# 設定済みのキーを確認
cli-modelarium keys list

# キーを削除
cli-modelarium keys delete openai
```

環境変数も使用できます（CI/CDに便利）:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
```

環境変数はキーチェーンストレージよりも優先されます。

### ローカルモデル（Ollama、LM Studio など）

ローカルモデルはOpenAI互換エンドポイント経由で動作します - APIキーは不要です。ツールはOllamaのデフォルトポートを自動検出します。

```bash
# デフォルト: Ollamaがlocalhost:11434にあると想定
cli-modelarium "test" --models local/llama-3.3

# 代わりにLM Studioを使用
cli-modelarium "test" --models local/qwen-3-32b --local-url http://localhost:1234/v1

# カスタムローカルURLをデフォルトとして保存
cli-modelarium keys set local --base-url http://localhost:1234/v1
```

## サポートされているプロバイダー

| プロバイダー | APIキー必要 | ストリーミング | コストトラッキング |
|----------|-----------------|-----------|---------------|
| OpenAI (GPT-5, GPT-5 mini, o3, o4-mini, など) | ✅ | ✅ | ✅ |
| Anthropic (Claude Opus 4.8, Sonnet 4.6, Haiku 4.5, など) | ✅ | ✅ | ✅ |
| Google (Gemini 3.5 Flash, Gemini 3.1 Pro, など) | ✅ | ✅ | ✅ |
| xAI (Grok 4.3, など) | ✅ | ✅ | ✅ |
| DeepSeek (V4 Pro, V4 Flash, など) | ✅ | ✅ | ✅ |
| Mistral (Large, Medium, Small) | ✅ | ✅ | ✅ |
| Groq (Llama 3.3, Llama 4 Scout, gpt-oss) | ✅ | ✅ | ✅ |
| OpenRouter (登録済みの8つのID: Qwen、DeepSeek R1、Llama 3.3、gpt-oss、GLM) | ✅ | ✅ | ✅ |
| Alibaba/DashScope (Qwen3.7 Max, Qwen3.6 Flash, Qwen3 Coder, など、一部のQwenモデル、International/Singapore) | ✅ | ✅ | ✅ |
| Z.AI/GLM (GLM-5.2, GLM-4.7, GLM-4.5 Air, など；OpenAI互換、海外エンドポイント) | ✅ | ✅ | ✅ |
| NVIDIA NIM (登録済みの9つのID: Nemotron、Gemma 4、Mistral Nemotron、MiniMax M3、Laguna、Llama 3.1) | ✅ | ✅ | 公開レートなし |
| Moonshot AI / Kimi (登録済みの4つのID: K3、K2.7 Code、K2.7 Code HighSpeed、K2.6) | ✅ | ✅ | ✅ |
| **ローカル: Ollama** | ❌ | ✅ | 無料 |
| **ローカル: LM Studio** | ❌ | ✅ | 無料 |
| **ローカル: vLLM** | ❌ | ✅ | 無料 |
| **ローカル: llama.cpp server** | ❌ | ✅ | 無料 |

現在サポートされているすべてのモデルを確認するには `cli-modelarium list-models` を実行してください。

## モデルグループ

モデルIDを列挙する代わりに、`--models` はグループのショートカットを受け付けます。静的グループはそのまま展開されます。以下に挙げるすべてのメンバーが実行されるため、グループが対象とする各プロバイダーのキーが必要であり、最初に見つかった不足キーの時点で実行は中断されます。動的グループの `all` と `all-local` は例外で、これらは実際に設定済みの内容に対して解決されます。

**静的グループ**（メンバーシップは固定）:

| グループ | モデル |
|-------|--------|
| `all-premium` / `all-flagship` | gpt-5.6-sol, claude-opus-5, gemini-3.1-pro-preview, grok-4.6, deepseek-v4-pro, mistral-large-latest, qwen3.8-max, glm-5.2 |
| `all-budget` | gpt-5.4-nano, claude-haiku-4-5, gemini-3.1-flash-lite, grok-4.20-0309-non-reasoning, deepseek-v4-flash, mistral-small-latest, qwen3.7-plus, glm-4.5-air |
| `all-reasoning` | o3, o4-mini, deepseek-v4-pro, magistral-medium-latest, magistral-small-latest, glm-5.2 |
| `all-cheap` | gpt-4o-mini, claude-haiku-4-5, gemini-2.5-flash-lite, deepseek-v4-flash, mistral-small-latest, qwen-flash, glm-4.7-flashx |
| `all-open-weight` | openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, llama-3.3-70b-versatile, meta-llama/llama-4-scout-17b-16e-instruct |

**動的グループ**（実行時に解決）:

- `all` — 設定済みのAPIキーを持っているすべてのクラウドモデル（ローカルモデル、OpenRouter、NVIDIAを除く。後者2つはプロバイダーの全カタログではなく登録済みの一部であり、NVIDIAはコストを提示できません）。これは多数のモデルにファンアウトする可能性があるため、`--max-cost` と組み合わせてください。
- `all-local` — 実行中のローカルサーバー（Ollama / LM Studio / vLLM / llama.cpp）が報告するすべてのモデル。サーバーに到達できない場合は、エラーではなく明確なメッセージが表示されます。

```bash
cli-modelarium "CAP定理を説明して" --models all-budget
cli-modelarium "CAP定理を説明して" --models all --max-cost 0.50
cli-modelarium "CAP定理を説明して" --models all-local
```

## 仕組み

Cli Modelarium は、OpenAIの `messages` 配列、Anthropicのトップレベル `system` パラメータ、Googleの `system_instruction` など、API間の違いを隠すモジュラーなプロバイダー抽象化レイヤーを使用しています。すべてのプロバイダーは同じ非同期ストリーミングインターフェースを実装しているため、CLIは `asyncio.gather()` ですべてを並列に実行できます。

コスト計算は、各プロバイダーが報告する `usage` フィールド（入力トークン、出力トークン、キャッシュされたトークン）に現在の価格定数を乗算して算出されます。価格データは **2026年7月29日** に公式プロバイダードキュメントから検証されました - 注意事項については [注意事項と制限](#注意事項と制限) を参照してください。

ローカルモデルの場合、Ollama、LM Studio、vLLM、llama.cpp はすべてOpenAI互換のRESTエンドポイントを公開しているため、カスタム `base_url` を使用した同じOpenAI Python SDKが使用されます。

## 注意事項と制限

### 価格データ

Cli Modelarium に組み込まれている価格の大半は、**2026年7月29日** に公式プロバイダードキュメントから検証されました。一部のエントリは、レジストリ内の各項目の横に記載された独自の検証日を持ちます。Z.AI/GLM の価格が最も古く、**2026年6月22日** です。LLMの価格は頻繁に変更されます（時には月単位で）。`pricing_as_of` 日付は JSON 出力に含まれ、コンソールにも表示されます。CSV 出力と Markdown 出力には含まれません。予算編成や本番環境の決定にコスト計算を信頼する前に、必ず各プロバイダーの公式価格ページと照合してください。

価格は、各プロバイダーの100万トークンあたりの標準/定価の公開レートです（バッチ、優先、オフピーク、プロモーション価格ではありません）。入力サイズによってティアが分かれるモデルでは、エントリー/短コンテキストのティアを表示し、キャッシュ価格はキャッシュ読み取りレートです。DashScope/Qwenのコストは非思考（non-thinking）レートを反映しています（ツールは `enable_thinking=false` を送信します）。

NVIDIA NIM は例外です。NVIDIA はホスト型 NIM エンドポイントのトークン単価を公開していないため、NVIDIA モデルのコストは追跡されません。コスト列に表示されるゼロはレートが存在しないことを示すものであり、価格がゼロという意味ではありません。このコストは常にゼロであるため、NVIDIA モデルでは `--max-cost` が発動することはなく、`cost_under` アサーションは常に合格します。どちらもこのプロバイダーでは支出の保護になりません。アクセスはトークン単位の課金ではなくアカウントのクレジットで計測されるため、注意すべきなのは予期しない請求ではなくクレジットの枯渇です。NVIDIA モデルが実行に含まれる場合は、その旨を伝える注意パネルが表示されます。

モデルごとの現在のレートを確認するには `cli-modelarium pricing`（または `pricing --all`）を実行してください。

### レート制限

レート制限処理とデフォルトのプロバイダーごとの同時実行設定は、**2026年6月21日** に検証されたプロバイダーのレート制限に基づいています。お客様の特定のティアの制限は、ここで想定されているデフォルトとは異なる場合があります。本番環境のキャパシティ前提を構築する前に、プロバイダーの公式ダッシュボードと現在の制限を照合してください。

### モデルの利用可能性

Cli Modelarium がサポートするモデルは、**2026年8月15日** にプロバイダーが提供していたものを反映しています。プロバイダーは定期的に新しいモデルをリリースし、古いモデルを廃止し、機能を調整しています。レジストリ内のモデルが動作しなくなった場合は、`cli-modelarium list-models` を実行し、プロバイダーのドキュメントを確認してください。

### 本番グレードのゲートウェイではありません

Cli Modelarium は評価と比較のために設計されています - 開発者のターミナルからプロバイダー間でアドホックな横並びのテストを実行します。本番環境の推論ゲートウェイではありません。本番規模のルーティング、ロードバランシング、フォールバックチェーン、またはSLA管理された推論が必要な場合は、その目的のために特別に構築されたツールを探してください。

### プロバイダー間のトークン数比較

結果に表示されるトークン数は、各プロバイダーのAPIによって報告されます。プロバイダーごとに異なるトークナイザーを使用するため、同じテキストに対して「出力トークン」をプロバイダー間で直接比較することはできません。本番環境での使用に対するコスト効率を比較する場合は、実際のワークロードで実際のプロンプトを実行し、プロバイダー間のトークン単位の計算だけに頼らないでください。

### LLM-as-a-Judge の使用

Cli Modelarium には、`--judge` フラグで有効化されるオプションのLLM-as-a-judgeスコアリングが含まれており、1つのLLMを使用して他のLLMからの出力を評価します。これは標準的なベンチマーキング手法であり、サポートされているすべてのプロバイダーの利用規約の下で、評価/ベンチマーキング活動として許可されています。

`--judge` を使用する場合、お客様は使用する各プロバイダーのモデルの利用規約に従う責任があります。各プロバイダーの利用規約は、評価対象のモデルとジャッジモデル自体の両方に適用されます。

**ジャッジバイアスの注意:** LLMジャッジには文書化されたバイアスがあります（自己選好、同じファミリーへの選好、冗長性への選好）。ジャッジスコアは有用なシグナルであり、グラウンドトゥルースではありません。バイアスを軽減するために、ジャッジパネル（複数モデルでの `--judges`）を使用してください。

### ハルシネーション検出

ハルシネーション検出プリセットは、モデル間の有用な比較シグナルであり、グラウンドトゥルースの検証ではありません。検出精度は、使用するジャッジモデル、必要なドメイン知識、`--expected-facts` 経由で参照事実が提供されているかどうかによって異なります。絶対的な正しさの検証ではなく、相対的な品質比較に使用してください。

### 比較方法論

LLMは温度 > 0 で非決定論的です - 同じプロンプトを再実行すると、異なる出力が生成される可能性があります。単一の比較実行では、各モデルから1つのサンプルが表示されるだけであり、決定的な品質判定ではありません。

より信頼性の高い結論を導き出すには:
- `--runs 5`（またはそれ以上）を使用すると、各比較を自動的にN回実行し、統計サマリー（平均/中央値のレイテンシ、変動係数、最頻出力、出力の多様性）を確認できます。変動係数が 0.05 を下回れば、実行間でモデルの挙動が安定していることを示します。
- ハルシネーションの一貫性を分析するには、`--runs` と `--check-hallucination` を組み合わせて、複数回の実行でモデルがどの程度の頻度でハルシネーションを起こすか（ハルシネーション率）を確認してください。
- より決定論的な出力のために `--temperatures 0` を使用。一部のモデルは温度設定を一切受け付けません - `claude-opus-4-7`、`claude-opus-4-8`、`claude-opus-5`、`claude-sonnet-5`、`claude-fable-5`、`claude-fable-5-1`、`o3`、`o4-mini`、`gpt-5`、`gpt-5.5`、`gpt-5.6-sol`、`gpt-5.6-terra`、`gpt-5.6-luna`、`kimi-k3`、`kimi-k2.7-code`、`kimi-k2.7-code-highspeed`、`kimi-k2.6` です。ツールはこれらのモデルに対してこのフィールドを省略するため呼び出しは成功し、モデルはプロバイダーのデフォルト値で実行されます。
- 1つだけでなく、複数のプロンプトにわたって比較する
- 体系的な分析のために実行結果を保存するには `--output json` フラグを使用（`--runs > 1` の場合、JSON にはセルごとの `stats_by_cell` 集計が含まれます）

これら12のモデルは温度フィールドなしで呼び出され、JSON 出力の `models_without_temperature` には、その実行で影響を受けたモデルが列挙されます。知っておくべき結果が3つあります。複数の値を指定した `--temperatures` のスイープは、これらのモデルに対しては実際のスイープではなく同一のリクエストを発行します。その場合ツールは警告を表示します。結果テーブル、CSV、および各 JSON 結果レコードに表示される温度は、実際に適用された値ではなく**要求された**値です。そして `--significance` は、これがラベルではなく結論そのものを変えうる場面です。温度を省略するモデルと温度を尊重するモデルを比較すると、サンプリングによる分散の差が生じますが、Welch や Mann-Whitney はそれをモデルの品質差であるかのように報告します。この場合も警告は表示されます。影響を受けるモデルと受けないモデルを混在させた有意差検定は、プロバイダーのデフォルト温度で実行されたモデル名を挙げた `Temperature not applied` パネルを表示し、JSON 出力の `significance_temperature_mixed` を `true` にします。複数温度かつ混在している実行では、両方のメッセージが1つのパネルにまとめて表示されます。CSV には同等の情報はありません。

## このプロジェクトについて

Cli Modelarium は **SoraVantia GK** の製品です。**Lavelle Hatcher Jr** が開発し、現在も保守を担当しています。

- 📦 リポジトリ: [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium)
- 💬 質問・不具合: [issueを開く](../../issues)
- 🔧 メンテナー: [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

## 構築した理由

プロバイダー間でLLM出力を比較するのは面倒です - SDKが異なり、認証パターンが異なり、レスポンス形状が異なり、コストとレイテンシーのデータと一緒に横並びで確認する簡単な方法がありません。洗練されたクラウドプレイグラウンドは一度に1つのプロバイダーしか表示せず、利用可能なオープンソースのオプションは本番環境のルーティングに焦点を当てているか、チーム向けに最適化された本格的な評価プラットフォームのいずれかです。

Cli Modelarium は、1つのことをうまく行う小さく集中したCLIツールです: 品質スコアリング、アサーション、バッチモード、ストリーミングによる横並び比較 - すべてターミナル優先の開発者ワークフロー向けに設計されています。

意図的に焦点が絞られています: 本番環境のルーティング、エージェントオーケストレーション、ファインチューニング、GUIはありません。コマンドラインからのクリーンで高速な比較だけです。

モジュラーなプロバイダー抽象化、並列実行、透明なコスト計算、ローカルユーザー向けのOSキーチェーンシステムによる安全なキーストレージを使用して構築されています。

## コントリビューション

Issue と PR を歓迎します。ガイドラインについては [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

セキュリティ問題については、[SECURITY.md](SECURITY.md) を参照してください - セキュリティ上の懸念事項について公開のissueを提出しないでください。

## ライセンス

[Apache License, Version 2.0](LICENSE) の下でライセンスされています。

帰属表示の要件については [NOTICE](NOTICE) ファイルを参照してください。

---

SoraVantia GK の製品です。[Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr) が開発・保守しています

Apache 2.0 の下でライセンスされています。Issue、PR、会話を歓迎します。
