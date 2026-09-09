<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/cli-modelarium-wordmark-dark.svg">
  <img alt="cli modelarium" src="docs/assets/cli-modelarium-wordmark-light.svg" width="420">
</picture>

用其他语言阅读: [English](README.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Português](README.pt.md) | [Italiano](README.it.md)

注意: 此 README 是为了可访问性而翻译的。Cli Modelarium CLI 工具本身仅输出英文。无论系统区域设置如何，所有命令、错误消息和输出均保持英文。

> 注意：以下七个章节仅存在于英文 README 中 — *Reproducibility analysis*、*Statistical significance testing*、*Bootstrap confidence intervals*、*Paired tests for same-prompt comparisons*、*McNemar's test for hallucination significance*、*Headless Linux servers*、*More examples*。功能本身均可正常使用，此处缺少的只是它们的说明。请参阅 [README.md](https://github.com/SoraVantia/cli-modelarium/blob/main/README.md)。

> 在终端中并排比较 LLM 输出 - 12 个云服务提供商 + 本地模型，支持并行流式传输、批量评估、LLM-as-judge 评分、幻觉检测和 CI/CD 就绪的断言。

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

## 功能简介

**Cli Modelarium** 是一款精心打造的命令行工具，用于跨提供商、模型、系统提示和温度参数比较 LLM 输出 - 内置实时并行流式传输、批量评估、确定性测试和质量评分。

适用于评估哪个模型适合您的特定任务、在 CI/CD 中运行提示回归测试、将本地模型与云 API 进行比较，或构建评估数据集 - 一切都通过单个终端命令完成。

## 系统要求

- Python 3.11 或更高版本（Python 3.10 用户请安装 `cli-modelarium==0.1.1`）
- 约 350 MB 磁盘空间（其中约三分之二为 scipy 和 numpy）
- macOS（Apple Silicon 和 Intel）、Windows 10+（x64 和 ARM）、Linux（x64 和 ARM）
- 首次安装需要联网（下载 PyPI wheel）

## 快速开始

```bash
pip install cli-modelarium

# 配置 API 密钥（安全保存到您的操作系统密钥链中）
cli-modelarium configure

# 运行您的第一次比较
cli-modelarium "Explain quantum computing in one sentence" \
  --models gpt-5.5,claude-opus-4-8,gemini-3.1-pro-preview
```

就这么简单。您将看到三个模型并行实时流式传输响应，延迟、令牌数和成本显示在简洁的比较表中。

## 特性

### 🤖 提供商（12 个云端 + 无限本地）

- **云服务提供商:** OpenAI、Anthropic、Google (Gemini)、xAI (Grok)、DeepSeek、Mistral、Groq、OpenRouter、Alibaba (DashScope)、Z.AI (GLM)、NVIDIA (NIM), Moonshot AI (Kimi)
- **本地模型:** Ollama、LM Studio、vLLM、llama.cpp - 任何在 localhost 上运行的 OpenAI 兼容服务器
- 在同一比较中混合使用本地和云模型
- 每次调用可选择任何已注册的模型 ID - 不限于内置的分组快捷方式

### ⚡ 并行流式传输

- 同时跨所有模型逐令牌实时显示
- 每个模型的 Time-to-First-Token (TTFT) 跟踪
- 查看哪个模型首先完成，实时观察输出分歧
- 来自所有 12 个提供商的流（底层使用 SSE）

<p align="center">
  <img src="docs/assets/cli-modelarium-comparison-demo.gif" alt="cli-modelarium 终端演示：三个模型并行实时流式传输对同一提示的响应，随后比较表显示每个模型的 Time-to-First-Token、延迟、令牌数和成本。" width="718">
</p>

**价格提示：** 演示中显示的成本来自录制时的单次运行。定价会变化；在依赖任何数字之前，请对照提供商进行验证。

### 📊 多种比较模式

- **单一提示 vs. 多个模型** - 快速"哪个最好？"比较
- **单一提示 vs. 多个温度** - 查看随机性如何影响输出
- **多个系统提示 vs. 一个用户提示** - A/B 测试提示工程
- **批量模式** - 用于实际评估工作的多提示 × 多模型
- **本地 vs. 云比较** - 量化差距（或其缺失）

### 🧪 评估功能

- **统计可复现性分析** - `--runs N` 将每个配置运行 N 次，并报告延迟和令牌的平均值/中位数/标准差/变异系数、输出频率、众数输出和输出多样性。与 `--check-hallucination` 结合使用可测量多次运行中的幻觉率。
- **确定性断言** - 10 种断言类型（`contains`、`regex`、`json_valid`、`json_schema`、`max_length_chars`、`latency_under`、`cost_under` 等），具有通过/失败输出和 CI 退出代码
- **LLM-as-a-judge 评分** - 使用一个 LLM 根据质量标准对其他 LLM 的输出进行评分
- **评判面板** - 多个评判平均得分以减少偏见的评估
- **幻觉检测预设** - 用于事实准确性检查的开箱即用标准
- **自定义标准** - 定义您自己的评分规则
- **自评自动跳过** - 当评判模型也是被评判对象时自动跳过

<p align="center">
  <img src="docs/assets/cli-modelarium-runs-demo.gif" alt="cli-modelarium 终端演示：同一提示在两个模型上重复运行多次，随后显示变异系数、自举置信区间和成对统计显著性判定。" width="1428">
</p>

### 💾 输出格式

- **实时终端** - 基于 Rich 的面板，带有进度条和流式显示
- **CSV** - 电子表格友好（在 Excel、Google Sheets、pandas 中打开） **契约是标题行，而不是列位置。** 随着工具演进会追加列，请按名称读取。
- **JSON** - 为脚本和管道结构化
- **Markdown** - 用于博客文章和报告的精美表格
- **退出代码** - 反映 CI/CD 通过/失败状态的 0/1/2/3

### 💰 成本透明度

- 从每个提供商报告的使用情况显示每次调用成本
- 每次比较的总成本汇总
- 启用 LLM-as-judge 时单独显示评判成本
- 本地模型显示为 "Free"
- `--max-cost` 标志会在超出上限后停止发起新的调用（已发出的调用仍会执行完毕，因此它限制的是一次运行，而不是阻止账单）

### 🔒 安全性

- 通过 `keyring` 将 API 密钥存储在 OS 原生密钥链中（Mac Keychain、Windows Credential Manager、Linux Secret Service）
- 格式验证在存储前捕获粘贴错误
- 错误消息编辑防止密钥在回溯中泄漏
- 仅限 localhost 的本地模型 URL 验证
- 包含负责任披露政策的 `SECURITY.md`

### 🛡️ 速率限制处理

- 每个提供商的并发限制（默认 5）- 所有提供商共用同一个值，请对照你自己的层级确认
- 自动 429 重试，带指数退避
- Anthropic 的 529 "overloaded" 与速率限制分开处理
- 为较高层级的高级用户提供 `--concurrency` 标志
- 每个模型的优雅失败（其他模型继续）
- DashScope 免费层级和旗舰 Qwen (qwen3.7-max) 的速率限制比大多数提供商更严格；如果遇到 429，请降低 `--concurrency`
- Moonshot 在使用前需要至少充值 1 美元，没有免费层级。Tier0 为 1 个并发请求、每分钟 3 次请求、每天 150 万 tokens；累计充值 10 美元升至 Tier1。在 Tier0 上请调低 `--concurrency`。

### 🌐 跨平台

- 在 macOS、Windows（10+ 和 ARM）和 Linux 上以相同方式工作
- 所有文件 I/O 使用 `pathlib` + 显式 UTF-8 编码
- CSV 写入使用 `newline=""` 以兼容 Windows
- 需要 Python 3.11+

### 📋 开发者体验

- **单一 CLI 二进制文件** - `pip install cli-modelarium` 即可完成
- **精致的基于 Rich 的 UI** - Claude Code 级别的终端打磨
- **JSON 输出** - 可通过管道输入任何工具（`jq`、脚本、监控）
- **CI/CD 就绪** - 退出代码、结构化输出、包含 GitHub Actions 示例
- **Apache 2.0 许可** - 可用于任何项目，商业或其他

## 示例

### 在编码任务上比较 3 个模型

```bash
cli-modelarium "Write a Python function to find the longest palindromic substring" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview
```

### 带断言的批量评估

创建 `eval.json`:

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

运行它:

```bash
cli-modelarium batch eval.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output results.csv
```

### 使用 LLM 评判对输出进行评分

```bash
cli-modelarium "Explain recursion in one paragraph" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview,local/llama-3.3-70b \
  --judge claude-opus-4-7 \
  --judge-criteria "accuracy,clarity,brevity"
```

<p align="center">
  <img src="docs/assets/cli-modelarium-judge-demo.gif" alt="cli-modelarium 终端演示：LLM 评判为两个模型打分，比较表显示每个模型的分数，每条回答下方显示评判写出的评分理由。" width="848">
</p>

**演示提示：** 分数和成本来自录制时的单次运行。评判分数是参考信号而非绝对标准，在不同运行或模型版本之间不会精确重现。定价会变化；在依赖任何数字之前，请对照提供商进行验证。

### 针对已知事实检测幻觉

```bash
cli-modelarium "Tell me about the Eiffel Tower" \
  --models gpt-5.5,claude-opus-4-7 \
  --judge claude-opus-4-7 \
  --check-hallucination \
  --expected-facts "Built 1887-1889,Located in Paris France,Designed by Gustave Eiffel"
```

### 将本地模型与云 API 进行比较

```bash
# 首先启动 Ollama: ollama run llama3.3
cli-modelarium "Summarize the key features of microservices architecture" \
  --models local/llama-3.3-70b,gpt-5.5,claude-opus-4-7
```

### 在 CI/CD 中运行（GitHub Actions 示例）

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

如果通过率低于 90%，命令将以代码 1 退出，从而使构建失败。

#### 退出代码

| 代码 | 含义 |
|------|------|
| `0` | 成功。 |
| `1` | 断言失败——一个或多个断言未通过，某次 `batch` 运行什么都没有验证，或某个模型拒绝作答而使已配置的断言未被评估。只有 `batch` 会给出断言结论；`compare` 在发生意外错误时仍可能以 `1` 退出。 |
| `2` | 运行未能完成。 |
| `3` | `--max-cost` 停止了本次运行。已经发出的调用会被允许完成，因此保存的输出包含实测数据并标记出从未发出的调用。该上限限制的是后续调用，而非已经产生的花费。 |
| `4` | `diff` 发现了差异。之所以是独立的代码，是因为其他所有非零代码都表示出了问题，而报告了变化的 `diff` 是成功的。只有 `diff` 会返回它。 |

代码 `2` 涵盖多种不同的原因，并且**不区分它们**：缺少 API 密钥、未知模型、已停用的模型、提供商错误、超出成本上限、格式错误的批处理文件、被拒绝的标志组合、输出文件冲突，或超出批处理大小上限。

在让流水线依赖这些代码之前，有三条规则值得了解：

- **调用失败优先于断言。** 只要有一次模型调用失败，`batch` 就会以 `2` 退出而不报告断言结论，即便断言同样失败也是如此。从退出代码看，失败的测试套件和无效的 API 密钥并无区别。
- **无法访问本地服务器不算失败。** 即使没有服务器响应，`list-models --local` 仍以 `0` 退出，因此无法用退出代码来检测服务器是否运行。
- **拒绝会让门禁失败，无论通过率是多少。** 被拒绝的请求没有可供断言的输出，因此其断言被记为错误并从通过率中排除——也就是说上方显示的通过率只描述了得到回应的那些请求。只要有拒绝导致任何已配置的断言未被评估，即便通过率为 100%，`batch` 也会以 `1` 退出。具体数量会在 JSON 的 `total_assertions_refused` 中给出。

若要了解运行*为何*失败，请读取 JSON 输出中每条结果的 `error` 字段——其中包含提供商的消息，形似凭据的字符串会被遮蔽：

```bash
cli-modelarium batch ./eval/test_suite.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output-format json --output results.json
code=$?
if [ "$code" -eq 2 ]; then
  jq -r '.results[] | select(.error) | "\(.model): \(.error)"' results.json
fi
```

拒绝不是错误——被拒绝的请求上 `error` 仍为 `null`，这样其费用会保留在所有合计中，报告它的是退出代码 `1` 而非 `2`。因此对于因拒绝而变红的那次运行，`select(.error)` 什么都不会返回。要同时覆盖两者：

```bash
jq -r '.results[] | select(.error or .refused)
       | "\(.model): \(.error // "refused: " + (.stop_category // "no category"))"' results.json
```

`--output-format json` 是必需的：默认输出不含任何机器可读的错误字段。请注意，在调用任何模型*之前*发生的失败（缺少密钥、未知模型、批处理文件有误）根本不会生成 JSON；此时控制台消息是唯一的信号。

#### 运行标识

每份 JSON 输出都带有四个顶层字段，用来说明*这是哪一次运行*。在本次发布之前它做不到这一点：同一条命令运行两次，产生的 JSON 只在 `latency_ms` 和 `ttft_ms` 上有差异，其余完全相同。针对已发布的 0.1.9 所做的一次探测，正是相隔 93 秒测到了这样一对，而更快的那次是第二次运行——所以连"延迟更高的先运行"这种猜测也会把两者排反。剩下的唯一信号是文件系统的 mtime，而它经不起 `git add`、复制、tar 解包或产物上传中的任何一种。

| 字段 | 含义 |
|------|------|
| `started_at` | 运行开始的时刻——ISO 8601 UTC，秒级精度，`Z` 后缀。在解析参数之前、在任何提供商调用之前取得，因此是开始时间而非结束时间。 |
| `run_id` | 标识本次运行的 UUID。经过复制和重命名仍然保留，并能区分同一秒内开始的两次运行。 |
| `experiment_key` | 对定义该实验的输入所做 SHA-256 的前 16 位十六进制字符。共享同一个值的两份输出测量的是同一件事。 |
| `invocation` | 解析后的参数：命令名、模型列表、温度、系统提示词和评判模型。 |

四个字段同样来自 `compare` 和 `batch`，无条件输出。Markdown 另外还带有 `Started at` 和 `Run ID`；CSV 一个都不带，因为标识是运行级的，而 CSV 是行级的。

```bash
# 两份输出到底能不能比较？
[ "$(jq -r .experiment_key before.json)" = "$(jq -r .experiment_key after.json)" ] \
  && echo "同一实验" || echo "不同实验 - 不要比较"
```

`started_at` 采用秒和 `Z` 而不是微秒和 `+00:00`，是因为 shell 监控脚本最先会用到的 jq `fromdateiso8601` 对另外两种写法都不接受。

**`invocation` 记录的是实际运行了什么，而不是你敲了什么。** 以 `--models all-flagship` 启动的运行会列出该分组展开后的实际模型 id，这正是使用者需要的：分组成员属于注册表状态，会在版本之间变化，仅凭分组名谁也无法复现这次运行。

**任何机密都到不了 `invocation`，而且这是许可名单而非脱敏处理。** 该字段由四个具名键构建，因此没有在其中列名的东西根本进不来。排除 `--local-url` 是因为它可能在 userinfo 位置携带凭据（`http://user:pass@host/v1`），这种形态不能交给任何模式匹配去把关。排除文件路径是因为路径会泄露家目录和用户名，而真正重要的内容本来就已经记录下来了。用一份固定清单来构建字段是更强的保证：脱敏处理必须认出每一个被送到它面前的机密，而这里根本不会见到机密。

**`experiment_key` 所哈希的内容：** 解析后的命令名、提示词、模型列表、温度、解析后的系统提示词、评判模型，以及运行次数。测量值在设计上被排除——延迟、成本和 token 计数正是被比较的输出，一个随它们变动的键永远不会匹配上。输出目标同样被排除，因为 `--output report.json` 和管道到 stdout 的 `--output-format json` 是同一个实验的两种写法。输入内容在这里和常量本身处都有记录，因为一个输入不明的哈希比没有哈希更糟：两个键不同，若不知道变的是实验还是哈希方式，使用者什么也判断不了。`EXPERIMENT_KEY_VERSION` 出于同样的理由而存在，并在哈希输入发生变化时递增——绝不为纯粹外观上的改动而递增。

**运行次数包含在键里。** 对相同单元格执行 `--runs 1` 和 `--runs 10` 不会共享同一个键，这是有意为之：后者回答的是前者无法回答的方差问题，把两者合在一起的监控等于拿点估计去和一个分布作比较。

**模型列表刻意不排序。** 排序会让 `--models a,b` 和 `--models b,a` 共享一个键，以"测量的是相同单元格"为由这也说得通——但 `compare` 中的 `prompt_id` 是基于位置的行序号，所以在这两次运行里 `p1` 指向的是不同的模型。用 `(experiment_key, prompt_id)` 去连接两者的使用者，会在两个键彼此吻合的情况下把每一行都对错位。误判为"不同"，代价是少做一次比较；误判为"相同"，则是悄悄毁掉一次比较。温度列表保持给定顺序也是同样的道理。

**`experiment_key` 相同并不意味着结果相同。** 在 `gemini-3.8-flash` 上的实测：两次在键所能看到的一切方面都完全相同的调用，返回了相同的输出文本（两次都是 `Paris`），输出 token 却是 65 和 58，成本是 `$0.00025125` 和 `$0.000225`。在输入固定为 10、且返回了结果的八次运行中，`output_tokens` 的跨度是 58 到 66，因为思考型模型的内部 token 会逐次调用而变化。这八次是全部，而不是从中挑选出来的：2026-09-06 共尝试十四次，其中六次返回 503，成为零 token 的死单元，无法从中取得跨度。所以同一实验的两次运行之间成本发生变动是正常的，并不能作为"有什么东西变了"的证据。这一点是支持这个键的理由，而不是反对它的理由：成本不同的两次运行仍然能被识别为同一个实验——而在追问这个差异是否有意义之前，你恰恰需要的就是这一点。

#### 比较两次运行

`diff` 读取你已经拥有的两份 JSON 输出，报告发生了什么变化。它不写入、不存储、也不监视任何东西。

```bash
cli-modelarium compare "capital of France?" --models gpt-5.5,claude-opus-4-8 --output before.json
# ... 稍后 ...
cli-modelarium compare "capital of France?" --models gpt-5.5,claude-opus-4-8 --output after.json

cli-modelarium diff before.json after.json
```

<p align="center">
  <img src="docs/assets/cli-modelarium-diff-demo-4model.gif" alt="cli-modelarium 终端演示：同一次比较在 claude-fable-5-1、gemini-3.8-flash、gemini-3.7-flash 和 claude-haiku-4-5 四个模型上运行两次，随后 diff 报告每条回答的文本都没有变化，而成本在两行 Gemini 上发生变动、在两行 Claude 上保持不变。" width="1088">
</p>

**方向由参数顺序决定。** 无论时间戳怎么写，第一个文件都被读作较早的那次运行。输出中没有任何字段能为同一秒内写下的两次运行排序——`started_at` 是秒级精度，而 `run_id` 是不含时间的随机 UUID——所以始终可用的规则就是你敲进去的顺序。当 `started_at` 与之相悖时，`diff` 会指出这一点并继续。

比较的是单元格，不是文件。`--temperatures 0,0` 会把同一个单元格请求两次，因此可能存在模型、温度和系统提示词都相同的两行；连接时还会数出每一行在自己所属单元格分组内的位置。未发生变化的单元格默认隐藏，`--all` 可以显示。

**每个显示出来的单元格都会在数字之前说明响应文本是否发生了变化。** 思考型模型经常以不同的 token 成本返回相同的文本，所以"成本变了而回答没变"才是通常的读法；反过来，如果回答变了而 token 数恰好相同，那就没有任何东西在动，这一行本会被隐藏。它只说相同或不同，绝不给出相似度分数——在那里写一个百分比，就是造出输出中并不存在的数字。如果某一侧拒绝、出错或被中止，就没有可比较的回答，命令会如实说明。

**它拒绝的情况：** 提示词改变、运行次数改变（一次是点估计，十次是分布），以及 `batch` 输出对 `compare` 输出。增加或移除模型不算拒绝：重叠的单元格依然可比，只在一侧出现的单元格会单独列出。

**它加限定而不拒绝的情况：** 依据不同价目表计算的两份输出仍然可比，但成本差异中有一部分来自价格表而非模型本身，因此这一点会在任何成本数字之前说明。被截断的运行、更换过的评判模型，以及早于 0.2.0 的输出，都以同样方式标注。较早的输出仍会通过匹配行内容来比较，并且 `diff` 会明确指出那种格式无法告诉它的两件事——是哪个命令写出了这份输出，以及运行了哪些评判模型。

显著性判定会分别从两侧打印出来，并且从不相减。p 值描述的是一个样本，因此来自两次独立运行的两个 p 值都是真的，而它们的差不是其中任何一个所包含的量。

`--output-format json` 会带上每一个单元格（无论是否变化）、全部六项指标以及每一条限定说明。控制台只显示发生变化的单元格的成本、延迟和输出 token。退出代码见上表：没有变化是 `0`，有变化是 `4`，无法比较的一对是 `2`。

**隐私提示：** JSON、CSV 和 Markdown 每种输出格式都会嵌入每条结果的完整提示词、完整系统提示词和完整模型响应，以及提供商的任何错误消息。JSON 还会嵌入每个评判模型的推理文本；`--include-reasoning` 仅控制控制台显示，不影响文件，CSV 和 Markdown 不包含该内容。在提交输出文件或将其作为公开 CI 产物上传之前，请将其视为敏感信息。 数据保留和训练条款因提供商而异，本工具不对其中任何一项作出声明，请查阅你所配置的每个提供商的条款。Claude Fable 5.1 需要 30 天数据保留，不支持零数据保留。 评判模型是第二个提供商：`--judge` 会把你的提示词连同模型响应一起发送给它，因此启用评判会扩大能看到提示词的范围。第一个模型拒绝的请求，现在不会再发送给评判模型。 `compare` 报告还会在 JSON 和 Markdown 的 `methodology` 块中记录生成它的环境——工具版本、已安装的 `scipy` 精确版本以及完整的 Python 版本——无论运行多少次都是如此。这是主机元数据而非您的数据，但它精确锁定了依赖版本。CSV 完全不包含这些内容，`batch` 也不会记录。

## 配置

### API 密钥

Cli Modelarium 将 API 密钥存储在您的 OS 原生密钥链中（Mac Keychain、Windows Credential Manager 或通过 `keyring` 的 Linux Secret Service）。密钥永远不会以明文形式写入磁盘。

```bash
# 交互式设置（推荐）
cli-modelarium configure

# 或单独设置
cli-modelarium keys set openai
cli-modelarium keys set anthropic
cli-modelarium keys set google

# 检查配置了哪些密钥
cli-modelarium keys list

# 删除密钥
cli-modelarium keys delete openai
```

您也可以使用环境变量（对 CI/CD 有用）:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
```

环境变量优先于密钥链存储。

### 本地模型（Ollama、LM Studio 等）

本地模型通过 OpenAI 兼容端点工作 - 无需 API 密钥。该工具自动检测默认的 Ollama 端口。

```bash
# 默认: 假定 Ollama 在 localhost:11434
cli-modelarium "test" --models local/llama-3.3

# 改用 LM Studio
cli-modelarium "test" --models local/qwen-3-32b --local-url http://localhost:1234/v1

# 将自定义本地 URL 保存为默认值
cli-modelarium keys set local --base-url http://localhost:1234/v1
```

## 支持的提供商

| 提供商 | 需要 API 密钥 | 流式传输 | 成本跟踪 | 定价验证 |
|----------|-----------------|-----------|---------------|------------------|
| OpenAI (GPT-6 Astra, GPT-5.6 Sol, GPT-5.5, o3 等) | ✅ | ✅ | ✅ | `first-party` |
| Anthropic (Claude Opus 5, Sonnet 5, Fable 5.1, Haiku 4.5 等) | ✅ | ✅ | ✅ | `first-party` |
| Google (Gemini 3.8 Flash, 3.7 Flash, 3.1 Pro 等) | ✅ | ✅ | ✅ | `first-party` |
| xAI (Grok 4.6, Grok 4.3 等) | ✅ | ✅ | ✅ | `first-party` |
| DeepSeek (V4 Pro, V4 Flash 等) | ✅ | ✅ | ✅ | `first-party` |
| Mistral (Medium, Large, Small, Codestral) | ✅ | ✅ | ✅ | `first-party` |
| Groq (Llama 3.3, Llama 4 Scout, gpt-oss) | ✅ | ✅ | ✅ | `third-party` |
| OpenRouter (已注册的 8 个 ID：Qwen、DeepSeek R1、Llama 3.3、gpt-oss、GLM) | ✅ | ✅ | ✅ | `unchecked` |
| Alibaba/DashScope (Qwen3.8 Max, Qwen3.7 Max, Qwen3 Coder 等；精选 Qwen 模型，国际/新加坡) | ✅ | ✅ | ✅ | `first-party` |
| Z.AI/GLM (GLM-5.2、GLM-4.7、GLM-4.5 Air 等；OpenAI 兼容，海外端点) | ✅ | ✅ | ✅ | `first-party` |
| NVIDIA NIM (已注册的 9 个 ID：Nemotron、Gemma 4、Mistral Nemotron、MiniMax M3、Laguna、Llama 3.1) | ✅ | ✅ | 无公开费率 | `unpublished` |
| Moonshot AI / Kimi (4 个已注册 ID：K3、K2.7 Code、K2.7 Code HighSpeed、K2.6) | ✅ | ✅ | ✅ | `reseller` |
| **本地: Ollama** | ❌ | ✅ | 免费 | — |
| **本地: LM Studio** | ❌ | ✅ | 免费 | — |
| **本地: vLLM** | ❌ | ✅ | 免费 | — |
| **本地: llama.cpp server** | ❌ | ✅ | 免费 | — |

运行 `cli-modelarium list-models` 查看所有当前支持的模型。

## 模型组

`--models` 接受组快捷方式，而无需逐一列出模型 ID。静态组会原样展开：下表列出的每个成员都会运行，因此该组涉及的每个提供商你都需要有密钥，一旦遇到第一个缺失的密钥，运行即中止。动态组 `all` 和 `all-local` 是例外，它们会根据你实际已配置的内容进行解析。

**静态组**（成员固定）：

| 组 | 模型 |
|-------|--------|
| `all-premium` / `all-flagship` | gpt-5.6-sol, claude-opus-5, gemini-3.1-pro-preview, grok-4.6, deepseek-v4-pro, mistral-large-latest, qwen3.8-max, glm-5.2 |
| `all-budget` | gpt-5.4-nano, claude-haiku-4-5, gemini-3.1-flash-lite, grok-4.20-0309-non-reasoning, deepseek-v4-flash, mistral-small-latest, qwen3.7-plus, glm-4.5-air |
| `all-reasoning` | o3, o4-mini, deepseek-v4-pro, glm-5.2 |
| `all-cheap` | gpt-4o-mini, claude-haiku-4-5, gemini-2.5-flash-lite, deepseek-v4-flash, mistral-small-latest, qwen-flash, glm-4.7-flashx |
| `all-open-weight` | openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, llama-3.3-70b-versatile, meta-llama/llama-4-scout-17b-16e-instruct |

**动态组**（在运行时解析）：

- `all` — 你已配置 API 密钥的每一个云端模型（不包括本地模型、OpenRouter 和 NVIDIA：后两者是已注册的子集而非提供商的完整目录，且 NVIDIA 的成本无法给出）。这可能会扩展到许多模型，因此请搭配 `--max-cost` 使用。
- `all-local` — 你正在运行的本地服务器（Ollama / LM Studio / vLLM / llama.cpp）所报告的每一个模型。如果没有可访问的服务器，你将收到清晰的提示信息，而不是错误。

```bash
cli-modelarium "解释 CAP 定理" --models all-budget
cli-modelarium "解释 CAP 定理" --models all --max-cost 0.50
cli-modelarium "解释 CAP 定理" --models all-local
```

## 工作原理

Cli Modelarium 使用模块化的提供商抽象层，隐藏了 OpenAI 的 `messages` 数组、Anthropic 的顶级 `system` 参数、Google 的 `system_instruction` 以及其他 API 之间的差异。每个提供商都实现了相同的异步流式接口，因此 CLI 可以使用 `asyncio.gather()` 并行运行它们。

成本计算来自每个提供商报告的 `usage` 字段（输入令牌、输出令牌、缓存令牌）乘以当前定价常数。大部分定价数据于 **2026 年 9 月 6 日** 从官方提供商文档中验证；有四个提供商未被完全覆盖 - 详细注意事项请参阅 [注意事项与限制](#注意事项与限制)。

对于本地模型，使用相同的 OpenAI Python SDK 加上自定义 `base_url`，因为 Ollama、LM Studio、vLLM 和 llama.cpp 都暴露了 OpenAI 兼容的 REST 端点。

## 注意事项与限制

### 定价数据

Cli Modelarium 内置的大部分定价均于 **2026 年 9 月 6 日** 从官方提供商文档中验证。部分条目带有各自的验证日期，标注在注册表中每个条目旁。Groq、Moonshot、NVIDIA 和 OpenRouter 在本次核对中未完全验证，注册表中已标注为未验证。已知有两组价格会到期：`gemini-3.6-flash`、`gemini-3.7-flash` 和 `gemini-3.8-flash` 采用的是将在 2027 年 1 月 1 日翻倍的初期优惠价格，`gpt-5.6-sol` 采用的是将在 2026 年 11 月 21 日前后结束的促销价格。两者都会让今天运行的成本对比显得比日后同样的运行更便宜，而且是统一变动的，因此输出中不会有任何异常之处。LLM 定价经常变化（有时每月一次）。`pricing_as_of` 日期包含在 JSON 和 Markdown 输出中，并显示在控制台上；CSV 输出不包含该日期。在依赖成本计算进行预算或生产决策之前，请始终对照每个提供商的官方定价页面进行验证。

价格为每个提供商每 100 万令牌的标准/标价公开费率（非批量、优先、非高峰或促销定价；有一个已注明的例外：`gpt-5.6-sol` 当前公布的费率为促销价）；对于按输入大小分层的模型，显示入门/短上下文层级，缓存定价为缓存读取费率。DashScope/Qwen 成本反映非思考费率（该工具发送 `enable_thinking=false`）。

NVIDIA NIM 是例外。NVIDIA 未公布其托管 NIM 端点的每令牌费率，因此不会跟踪 NVIDIA 模型的成本：成本列中显示的零表示没有费率，而不是价格为零。由于该成本始终为零，`--max-cost` 在 NVIDIA 模型上永远不会触发，`cost_under` 断言也总是通过——两者在该提供商上都无法为您提供任何支出保护。访问按账户额度计量，而非按令牌计费，因此需要留意的是额度耗尽，而不是意外账单。只要运行中包含 NVIDIA 模型，就会输出一个提示面板。

运行 `cli-modelarium pricing`（或 `pricing --all`）以获取当前的每个模型费率。

### 速率限制

速率限制处理和默认的每个提供商的并发设置基于 **2026 年 6 月 21 日** 验证的提供商速率限制。您的特定层级的限制可能与此处假定的默认值不同。在构建生产容量假设之前，请对照提供商的官方仪表板验证您当前的限制。

### 模型可用性

Cli Modelarium 支持的模型反映了 **2026 年 8 月 15 日** 提供商提供的内容。提供商会定期发布新模型、弃用旧模型并调整能力。如果注册表中的模型不再工作，请运行 `cli-modelarium list-models` 并查看提供商的文档。

### 不是生产级网关

Cli Modelarium 是为评估和比较而设计的 - 从开发者终端跨提供商运行临时并排测试。它不是生产推理网关。如果您需要生产规模的路由、负载均衡、回退链或 SLA 管理的推理，请寻找专门为此目的构建的工具。

### 跨提供商的令牌计数比较

结果中显示的令牌计数由每个提供商的 API 报告。不同的提供商使用不同的分词器，因此"输出令牌"在相同文本下不能直接跨提供商比较。如果您要比较生产使用的成本效率，请在实际工作负载中运行真实提示 - 不要仅依赖跨提供商的每令牌数学计算。

### LLM-as-a-Judge 使用

Cli Modelarium 包含可选的 LLM-as-a-judge 评分（通过 `--judge` 标志启用），它使用一个 LLM 来评估其他 LLM 的输出。这是标准的基准测试方法，并且在所有支持的提供商的服务条款下作为评估/基准测试活动是被允许的。

使用 `--judge` 时，您有责任遵守您使用其模型的每个提供商的服务条款。每个提供商的 ToS 同时适用于被评判的模型和评判模型本身。

**评判偏见提示:** LLM 评判有已记录的偏见（自我偏好、同家族偏好、冗长偏好）。评判分数是有用的信号，而不是基本事实。使用评判面板（带多个模型的 `--judges`）来减少偏见。

### 幻觉检测

幻觉检测预设是模型之间有用的比较信号，而不是基本事实验证。检测准确性取决于使用的评判模型、所需的领域知识以及是否通过 `--expected-facts` 提供参考事实。将其用于相对质量比较，而不是绝对正确性验证。

### 比较方法论

LLM 在温度 > 0 时是非确定性的 - 重新运行相同的提示可能产生不同的输出。单次比较运行向您显示每个模型的一个样本，而不是最终的质量判决。

要得出更可靠的结论:
- 使用 `--runs 5`（或更高）自动将每个比较运行 N 次并查看统计摘要：平均/中位数延迟、变异系数、众数输出和输出多样性。变异系数低于 0.05 表示模型在多次运行中行为稳定。
- 若要分析幻觉一致性，请将 `--runs` 与 `--check-hallucination` 结合使用，以查看模型在多次运行中产生幻觉的频率（幻觉率）。
- 使用 `--temperatures 0` 获得更确定性的输出。部分模型完全不接受温度设置 - `claude-opus-4-7`、`claude-opus-4-8`、`claude-opus-5`、`claude-sonnet-5`、`claude-fable-5`、`claude-fable-5-1`、`o3`、`o4-mini`、`gpt-5`、`gpt-5.5`、`gpt-5.6-sol`、`gpt-5.6-terra`、`gpt-5.6-luna`, `gpt-6-astra`, `gemini-3.8-flash`、`kimi-k3`、`kimi-k2.7-code`、`kimi-k2.7-code-highspeed` 和 `kimi-k2.6`。该工具会为这些模型省略该字段，从而使调用仍能成功，它们将以提供商的默认值运行。
- 使用 `--system-prompts "请简洁。,请详细。"` 可以让同一个提示在多个系统提示下运行并并排比较。它会像 `--models` 和 `--temperatures` 一样成倍增加调用次数。当存在多个时，报告会为每一行标注 `SP 1`、`SP 2` 等，并打印给出完整文本的图例——按单元格汇总表中的 `SP 2` 与其上方表格中的 `SP 2` 是同一个提示。CSV 和 JSON 则在每一行携带完整的系统提示。
- 跨多个提示比较，而不仅仅是一个
- 使用 `--output-format json` 标志保存运行结果以进行系统分析（当 `--runs > 1` 时，JSON 包含按单元格的 `stats_by_cell` 聚合）

这十九个模型在调用时会省略温度字段，JSON 输出中的 `models_without_temperature` 会列出某次运行中受影响的模型。有三个后果值得了解。针对这些模型使用多个值的 `--temperatures` 扫描会发出相同的请求，而不是真正的扫描，此时该工具会打印警告。结果表格、CSV 和每条 JSON 结果记录中显示的温度是**请求的**值，而非实际应用的值。而 `--significance` 正是这可能改变结论而非仅仅改变标签的地方：将省略温度的模型与遵循温度的模型进行比较会产生方差差异，这是采样造成的假象，但 Welch 或 Mann-Whitney 会将其报告为模型质量差异。这种情况同样会有提示：任何将受影响模型与未受影响模型混合的显著性运行，都会打印一个 `Temperature not applied` 面板，列出以提供商默认温度运行的模型，并将 JSON 输出中的 `significance_temperature_mixed` 设为 `true`。既是多温度又存在混合的运行，两条消息会合并显示在同一个面板中。CSV 不含等效信号。

## 关于本项目

Cli Modelarium 是 **SoraVantia GK** 的产品，由 **Lavelle Hatcher Jr** 创建并持续维护。

- 📦 仓库: [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium)
- 💬 问题或缺陷: [打开 issue](../../issues)
- 🔧 维护者: [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

## 为什么构建它

跨提供商比较 LLM 输出很繁琐 - 不同的 SDK、不同的认证模式、不同的响应形状，没有简单的方法可以并排查看它们以及成本和延迟数据。精致的云游乐场一次只显示一个提供商，可用的开源选项要么专注于生产路由，要么是为团队优化的完整评估平台。

Cli Modelarium 是一个专注的小型 CLI 工具，专门做好一件事: 带有质量评分、断言、批量模式和流式传输的并排比较 - 一切都为终端优先的开发者工作流程设计。

它是有意聚焦的: 没有生产路由、没有代理编排、没有微调、没有 GUI。只有来自命令行的清洁、快速的比较。

通过模块化的提供商抽象、并行执行、透明的成本计算和通过 OS 密钥链系统为本地用户提供的安全密钥存储构建。

## 贡献

欢迎 issues 和 PR。请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解指南。

对于安全问题，请参阅 [SECURITY.md](SECURITY.md) - 请勿为安全问题提交公开 issue。

## 许可证

依据 [Apache License, Version 2.0](LICENSE) 授权。

请参阅 [NOTICE](NOTICE) 文件了解归属要求。

---

SoraVantia GK 出品，由 [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr) 创建并维护

依据 Apache 2.0 授权。欢迎 issues、PR 和对话。
