<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/cli-modelarium-wordmark-dark.svg">
  <img alt="cli modelarium" src="docs/assets/cli-modelarium-wordmark-light.svg" width="420">
</picture>

다른 언어로 읽기: [English](README.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Français](README.fr.md) | [中文](README.zh.md) | [Deutsch](README.de.md) | [Português](README.pt.md) | [Italiano](README.it.md)

참고: 이 README는 접근성을 위해 번역되었습니다. Cli Modelarium CLI 도구 자체는 영어로만 출력됩니다. 모든 명령, 오류 메시지 및 출력은 시스템 로케일에 관계없이 영어로 유지됩니다.

> 참고: 다음 일곱 개 섹션은 영어 README 에만 있습니다 — *Reproducibility analysis*, *Statistical significance testing*, *Bootstrap confidence intervals*, *Paired tests for same-prompt comparisons*, *McNemar's test for hallucination significance*, *Headless Linux servers*, *More examples*. 기능 자체는 모두 사용할 수 있으며, 여기에 없는 것은 해당 설명뿐입니다. [README.md](https://github.com/SoraVantia/cli-modelarium/blob/main/README.md) 를 참조하십시오.

> 터미널에서 LLM 출력을 나란히 비교 - 12개 클라우드 제공자 + 로컬 모델, 병렬 스트리밍, 배치 평가, LLM-as-judge 스코어링, 환각 감지 및 CI/CD 지원 어설션 포함.

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

## 기능 개요

**Cli Modelarium**은 제공자, 모델, 시스템 프롬프트 및 온도 전반에 걸쳐 LLM 출력을 비교하기 위한 세련된 명령줄 도구입니다 - 라이브 병렬 스트리밍, 배치 평가, 결정론적 테스트 및 품질 스코어링이 내장되어 있습니다.

특정 작업에 적합한 모델을 평가하거나, CI/CD에서 프롬프트 회귀 테스트를 실행하거나, 로컬 모델을 클라우드 API와 비교하거나, 평가 데이터셋을 구축하는 데 유용합니다 - 모두 단일 터미널 명령으로 가능합니다.

## 시스템 요구 사항

- Python 3.11 이상 (Python 3.10 사용자는 `cli-modelarium==0.1.1`을 설치하십시오)
- 약 350 MB의 디스크 공간 (그중 약 3분의 2가 scipy와 numpy)
- macOS (Apple Silicon 및 Intel), Windows 10+ (x64 및 ARM), Linux (x64 및 ARM)
- 최초 설치 시 인터넷 연결 (PyPI 휠 다운로드)

## 빠른 시작

```bash
pip install cli-modelarium

# API 키 구성 (OS 키체인에 안전하게 저장됨)
cli-modelarium configure

# 첫 번째 비교 실행
cli-modelarium "Explain quantum computing in one sentence" \
  --models gpt-5.5,claude-opus-4-8,gemini-3.1-pro-preview
```

그게 전부입니다. 세 모델 모두 응답을 병렬로 라이브 스트리밍하며, 지연 시간, 토큰 수 및 비용이 깔끔한 비교 테이블에 표시됩니다.

## 기능

### 🤖 제공자 (12개 클라우드 + 무제한 로컬)

- **클라우드 제공자:** OpenAI, Anthropic, Google (Gemini), xAI (Grok), DeepSeek, Mistral, Groq, OpenRouter, Alibaba (DashScope), Z.AI (GLM), NVIDIA (NIM), Moonshot AI (Kimi)
- **로컬 모델:** Ollama, LM Studio, vLLM, llama.cpp - localhost에서 실행되는 모든 OpenAI 호환 서버
- 동일한 비교에서 로컬 및 클라우드 모델 혼합 가능
- 호출마다 등록된 모든 모델 ID 선택 가능 - 내장 그룹 단축키에 국한되지 않음

### ⚡ 병렬 스트리밍

- 모든 모델에서 동시에 토큰별 라이브 표시
- 모델당 Time-to-First-Token (TTFT) 추적
- 어떤 모델이 먼저 완료되는지 확인하고 출력이 실시간으로 분기되는 것을 관찰
- 12개 제공자 모두에서 스트림 (내부적으로 SSE)

<p align="center">
  <img src="docs/assets/cli-modelarium-comparison-demo.gif" alt="cli-modelarium 터미널 데모: 세 모델이 동일한 프롬프트에 대한 응답을 병렬로 라이브 스트리밍한 후, 비교 테이블에 모델별 Time-to-First-Token, 지연 시간, 토큰 수 및 비용이 표시됩니다." width="718">
</p>

**가격 관련 참고:** 데모에 표시된 비용은 녹화 시점의 단일 실행 결과입니다. 가격은 변경됩니다. 어떤 수치든 의존하기 전에 제공자를 통해 확인하십시오.

### 📊 다양한 비교 모드

- **단일 프롬프트 vs. 여러 모델** - 빠른 "어떤 것이 가장 좋은가?" 비교
- **단일 프롬프트 vs. 여러 온도** - 무작위성이 출력에 어떻게 영향을 미치는지 확인
- **여러 시스템 프롬프트 vs. 하나의 사용자 프롬프트** - 프롬프트 엔지니어링 A/B 테스트
- **배치 모드** - 실제 평가 작업을 위한 멀티 프롬프트 × 멀티 모델
- **로컬 vs. 클라우드 비교** - 격차(또는 그 부재)를 정량화

### 🧪 평가 기능

- **통계적 재현성 분석** - `--runs N`은 각 구성을 N회 실행하고 지연 시간과 토큰의 평균/중앙값/표준편차/변동계수, 출력 빈도, 최빈 출력, 출력 다양성을 보고합니다. `--check-hallucination`과 함께 사용하면 여러 실행에 걸친 환각 발생률을 측정할 수 있습니다.
- **결정론적 어설션** - 10가지 어설션 유형 (`contains`, `regex`, `json_valid`, `json_schema`, `max_length_chars`, `latency_under`, `cost_under` 등), 통과/실패 출력 및 CI 종료 코드 포함
- **LLM-as-a-judge 스코어링** - 한 LLM을 사용하여 품질 기준에 따라 다른 LLM의 출력 점수 매김
- **저지 패널** - 여러 저지가 점수를 평균화하여 덜 편향된 평가 제공
- **환각 감지 프리셋** - 사실 정확성 검사를 위해 즉시 사용 가능한 기준
- **사용자 정의 기준** - 자신만의 스코어링 루브릭 정의
- **자기 평가 자동 건너뛰기** - 저지 모델이 평가 대상이기도 할 때 자동으로 건너뜀

<p align="center">
  <img src="docs/assets/cli-modelarium-runs-demo.gif" alt="cli-modelarium 터미널 데모: 동일한 프롬프트를 두 모델에서 여러 번 반복한 후, 변동 계수, 부트스트랩 신뢰 구간 및 쌍별 통계적 유의성 판정이 표시됩니다." width="1428">
</p>

### 💾 출력 형식

- **라이브 터미널** - 진행 바 및 스트리밍 표시가 있는 Rich 기반 패널
- **CSV** - 스프레드시트 친화적 (Excel, Google Sheets, pandas에서 열기) **계약은 헤더 행이며 열 위치가 아닙니다.** 도구가 성장하면서 열이 추가되므로 이름으로 읽으십시오.
- **JSON** - 스크립트 및 파이프라인을 위한 구조화
- **Markdown** - 블로그 게시물 및 보고서를 위한 깔끔한 테이블
- **종료 코드** - CI/CD를 위해 통과/실패 상태를 반영하는 0/1/2/3

### 💰 비용 투명성

- 각 제공자의 보고된 사용량으로부터 호출별 비용 표시
- 비교당 총 비용 요약
- LLM-as-judge가 활성화될 때 저지 비용 별도 표시
- 로컬 모델은 "Free"로 표시
- 상한을 넘어서면 새 호출 전송을 중단하는 `--max-cost` 플래그(이미 보낸 호출은 끝까지 실행되므로, 청구를 막는 것이 아니라 실행을 제한합니다)

### 🔒 보안

- API 키는 `keyring`을 통해 OS 네이티브 키체인에 저장됨 (Mac Keychain, Windows Credential Manager, Linux Secret Service)
- 형식 검증으로 저장 전에 붙여넣기 오류 포착
- 오류 메시지 수정으로 트레이스백에서 키 누출 방지
- 로컬 모델 URL에 대한 localhost 전용 검증
- 책임 있는 공개 정책이 포함된 `SECURITY.md`

### 🛡️ 속도 제한 처리

- 제공자별 동시성 제한 (기본 5) - 모든 제공자에 동일한 값이 적용되므로 본인의 티어와 대조해 확인하십시오
- 지수 백오프를 사용한 자동 429 재시도
- Anthropic의 529 "overloaded"는 속도 제한과 별도로 처리됨
- 상위 티어의 파워 유저를 위한 `--concurrency` 플래그
- 모델별 우아한 실패 처리 (다른 모델은 계속 진행)
- DashScope 무료 티어 및 플래그십 Qwen (qwen3.7-max)의 속도 제한은 대부분의 제공자보다 더 엄격합니다. 429가 발생하면 `--concurrency`를 낮추십시오.
- Moonshot은 사용 전 최소 1달러 충전이 필요하며 무료 티어가 없습니다. Tier0는 동시 요청 1건, 분당 3요청, 하루 150만 토큰입니다. 누적 10달러를 충전하면 Tier1이 됩니다. Tier0에서는 `--concurrency`를 낮추십시오.

### 🌐 크로스 플랫폼

- macOS, Windows (10+ 및 ARM), Linux에서 동일하게 작동
- 모든 파일 I/O는 `pathlib` + 명시적 UTF-8 인코딩 사용
- CSV 쓰기는 Windows 호환성을 위해 `newline=""` 사용
- Python 3.11+ 필요

### 📋 개발자 경험

- **단일 CLI 바이너리** - `pip install cli-modelarium`으로 완료
- **세련된 Rich 기반 UI** - Claude Code 수준의 터미널 마무리
- **JSON 출력** - 무엇이든 파이프 (`jq`, 스크립트, 모니터링)
- **CI/CD 준비 완료** - 종료 코드, 구조화된 출력, GitHub Actions 예제 포함
- **Apache 2.0 라이선스** - 상업적이든 아니든 모든 프로젝트에서 사용

## 예제

### 코딩 작업에서 3개 모델 비교

```bash
cli-modelarium "Write a Python function to find the longest palindromic substring" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview
```

### 어설션을 사용한 배치 평가

`eval.json` 생성:

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

실행:

```bash
cli-modelarium batch eval.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output results.csv
```

### LLM 저지로 출력 점수 매기기

```bash
cli-modelarium "Explain recursion in one paragraph" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview,local/llama-3.3-70b \
  --judge claude-opus-4-7 \
  --judge-criteria "accuracy,clarity,brevity"
```

<p align="center">
  <img src="docs/assets/cli-modelarium-judge-demo.gif" alt="cli-modelarium 터미널 데모: LLM 저지가 두 모델을 채점하고, 비교 표에 모델별 점수가 표시된 뒤 각 답변 아래에 저지가 작성한 평가 근거가 나타납니다." width="848">
</p>

**데모 관련 참고:** 점수와 비용은 녹화 시점의 단일 실행 결과입니다. 저지 점수는 참고 신호이지 절대적 기준이 아니며, 실행이나 모델 버전에 따라 정확히 재현되지 않습니다. 가격은 변경됩니다. 수치에 의존하기 전에 제공업체에서 확인하십시오.

### 알려진 사실에 대한 환각 감지

```bash
cli-modelarium "Tell me about the Eiffel Tower" \
  --models gpt-5.5,claude-opus-4-7 \
  --judge claude-opus-4-7 \
  --check-hallucination \
  --expected-facts "Built 1887-1889,Located in Paris France,Designed by Gustave Eiffel"
```

### 로컬 모델과 클라우드 API 비교

```bash
# 먼저 Ollama 시작: ollama run llama3.3
cli-modelarium "Summarize the key features of microservices architecture" \
  --models local/llama-3.3-70b,gpt-5.5,claude-opus-4-7
```

### CI/CD에서 실행 (GitHub Actions 예제)

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

통과율이 90% 미만으로 떨어지면 명령이 종료 코드 1로 종료되어 빌드가 실패합니다.

#### 종료 코드

| 코드 | 의미 |
|------|------|
| `0` | 성공. |
| `1` | 어서션 실패 - 하나 이상의 어서션이 통과하지 못했거나, `batch` 실행이 아무것도 검증하지 못했거나, 모델이 거부하여 구성된 어서션이 평가되지 않은 채 남았습니다. 어서션 판정을 내리는 것은 `batch` 뿐이지만, `compare` 도 예기치 않은 오류에서는 `1` 로 종료될 수 있습니다. |
| `2` | 실행을 완료하지 못했습니다. |
| `3` | `--max-cost`가 실행을 중단했습니다. 이미 시작된 호출은 완료되므로 저장된 출력에는 실제 측정값이 담기고 시작되지 않은 호출이 표시됩니다. 이 상한은 이후 전송을 막을 뿐 이미 발생한 비용을 막지는 않습니다. |
| `4` | `diff`가 차이를 발견했습니다. 별도의 코드인 이유는 0이 아닌 다른 코드가 모두 "무언가 잘못되었다"를 뜻하는 반면, 변화를 보고한 `diff`는 성공했기 때문입니다. 이 코드를 내는 것은 `diff`뿐입니다. |

코드 `2` 는 서로 다른 여러 원인을 포괄하며 **그 원인을 구분하지 않습니다.** API 키 누락, 알 수 없는 모델, 지원이 종료된 모델, 제공업체 오류, 비용 상한 초과, 잘못된 형식의 배치 파일, 허용되지 않는 플래그 조합, 출력 파일 충돌, 배치 크기 상한 초과가 모두 코드 `2` 가 됩니다.

파이프라인을 이 코드에 의존시키기 전에 알아 둘 규칙이 세 가지 있습니다.

- **호출 실패가 어서션보다 우선합니다.** 모델 호출이 하나라도 실패하면 `batch` 는 어서션 결과를 보고하지 않고 `2` 로 종료합니다. 어서션도 함께 실패한 경우에도 마찬가지입니다. 실패한 테스트 스위트와 잘못된 API 키는 종료 코드만으로는 구분되지 않습니다.
- **로컬 서버에 연결할 수 없는 것은 실패가 아닙니다.** 응답하는 서버가 없어도 `list-models --local` 은 `0` 으로 종료하므로, 종료 코드로 서버 존재 여부를 판단할 수 없습니다.
- **거부는 통과율과 무관하게 게이트를 실패시킵니다.** 거부된 요청에는 검증할 출력이 없으므로 해당 어서션은 오류로 기록되어 통과율에서 제외됩니다. 즉 위에 표시된 통과율은 응답을 받은 요청만을 설명합니다. 거부로 인해 구성된 어서션이 하나라도 평가되지 않은 채 남으면, 통과율이 100%여도 `batch`는 `1`로 종료합니다. 그 개수는 JSON의 `total_assertions_refused`에 보고됩니다.

실행이 *왜* 실패했는지 확인하려면 JSON 출력에서 각 결과의 `error` 필드를 읽으십시오. 제공업체의 메시지가 담기며, 자격 증명처럼 보이는 문자열은 가려집니다.

```bash
cli-modelarium batch ./eval/test_suite.json \
  --models gpt-5.5,claude-opus-4-7 \
  --output-format json --output results.json
code=$?
if [ "$code" -eq 2 ]; then
  jq -r '.results[] | select(.error) | "\(.model): \(.error)"' results.json
fi
```

거부는 오류가 아닙니다. 거부된 요청에서도 `error`는 `null`로 남아 비용이 모든 합계에 그대로 반영되며, 이를 알리는 것은 종료 코드 `2`가 아니라 `1`입니다. 따라서 거부로 인해 실패한 실행에 대해 `select(.error)`는 아무것도 반환하지 않습니다. 두 경우를 모두 다루려면 다음과 같이 하십시오:

```bash
jq -r '.results[] | select(.error or .refused)
       | "\(.model): \(.error // "refused: " + (.stop_category // "no category"))"' results.json
```

`--output-format json` 이 필요합니다. 기본 출력에는 기계가 읽을 수 있는 오류 필드가 없습니다. 모델을 호출하기 *전에* 발생한 실패(키 누락, 알 수 없는 모델, 잘못된 배치 파일)에서는 JSON이 전혀 생성되지 않으므로, 그런 경우에는 콘솔 메시지가 유일한 신호입니다.

#### 실행 신원

모든 JSON 출력에는 *이것이 어떤 실행인지* 를 알려 주는 최상위 필드가 네 개 들어 있습니다. 이번 릴리스 이전에는 그럴 수 없었습니다. 동일한 명령을 두 번 실행해도 생성되는 JSON은 `latency_ms`와 `ttft_ms`에서만 달랐고 나머지는 전혀 다르지 않았습니다. 공개된 0.1.9를 대상으로 한 조사는 93초 간격으로 바로 그 쌍을 측정했는데, 더 빠른 쪽은 두 번째 실행이었습니다. 즉 "지연이 크면 먼저 실행된 것"이라는 짐작조차 이 둘을 거꾸로 정렬합니다. 남은 단서는 파일 시스템의 mtime뿐이었고, 그것은 `git add`도, 복사도, tar 추출도, 아티팩트 업로드도 견디지 못합니다.

| 필드 | 내용 |
|------|------|
| `started_at` | 실행이 시작된 시각 - ISO 8601 UTC, 초 단위 정밀도, `Z` 접미사. 플래그 해석 전, 어떤 제공업체 호출보다도 먼저 기록되므로 종료 시각이 아니라 시작 시각입니다. |
| `run_id` | 이 실행을 식별하는 UUID. 복사와 이름 변경을 거쳐도 남으며, 같은 초에 시작된 두 실행을 구분합니다. |
| `experiment_key` | 실험을 정의하는 입력에 대한 SHA-256의 앞 16자리 16진 문자. 같은 값을 가진 두 출력은 같은 것을 측정하고 있습니다. |
| `invocation` | 해석된 플래그: 명령 이름, 모델 목록, temperature, 시스템 프롬프트, 판정 모델. |

네 가지 모두 `compare`와 `batch` 양쪽에서 조건 없이 출력됩니다. Markdown은 여기에 더해 `Started at`과 `Run ID`를 싣지만, CSV는 어느 것도 싣지 않습니다. 신원은 실행 단위이고 CSV는 행 단위이기 때문입니다.

```bash
# 두 출력이 애초에 비교 가능한가?
[ "$(jq -r .experiment_key before.json)" = "$(jq -r .experiment_key after.json)" ] \
  && echo "같은 실험" || echo "다른 실험 - 비교하지 말 것"
```

`started_at`이 마이크로초와 `+00:00` 대신 초와 `Z`를 쓰는 이유는, 셸 모니터가 가장 먼저 찾는 jq의 `fromdateiso8601`이 나머지 두 표기를 모두 거부하기 때문입니다.

**`invocation`이 기록하는 것은 실제로 실행된 내용이지, 여러분이 입력한 문자열이 아닙니다.** `--models all-flagship`으로 시작한 실행은 그 그룹이 확장된 실제 모델 id를 나열하며, 이것이 바로 소비자에게 필요한 것입니다. 그룹 구성은 레지스트리 상태라 릴리스마다 바뀌므로, 그룹 이름만으로는 누구도 그 실행을 재현할 수 없습니다.

**어떤 비밀도 `invocation`에 도달할 수 없으며, 이는 가림 처리가 아니라 허용 목록입니다.** 이 필드는 이름이 명시된 네 개의 키로만 구성되므로, 거기에 이름이 없는 것은 들어올 수 없습니다. `--local-url`이 제외된 것은 userinfo 위치에 자격 증명을 담을 수 있기 때문이며(`http://user:pass@host/v1`), 이 형태는 어떤 패턴 대조에도 맡길 수 없습니다. 파일 경로가 제외된 것은 경로가 홈 디렉터리와 사용자 이름을 노출하는 반면, 정작 중요한 내용은 어차피 기록되기 때문입니다. 고정된 목록으로 필드를 구성하는 편이 더 강한 보장입니다. 가림 처리는 자기에게 보인 모든 비밀을 알아볼 수 있어야 하지만, 이쪽은 애초에 비밀을 보지 않습니다.

**`experiment_key`가 해싱하는 대상:** 해석된 명령 이름, 프롬프트, 모델 목록, temperature, 해석된 시스템 프롬프트, 판정 모델, 그리고 실행 횟수입니다. 측정값은 구조상 제외됩니다. 지연, 비용, 토큰 수는 비교되는 쪽의 출력이며, 그것들과 함께 움직이는 키는 결코 일치하지 않습니다. 출력 대상도 마찬가지로 제외됩니다. `--output report.json`과 stdout으로 파이프한 `--output-format json`은 같은 실험을 두 가지 방식으로 쓴 것이기 때문입니다. 입력 내역을 여기와 상수 자체에 모두 문서화한 이유는, 입력을 알 수 없는 해시가 해시가 없는 것보다 나쁘기 때문입니다. 두 키가 다르더라도, 바뀐 것이 실험인지 해싱 방식인지 모른다면 소비자는 아무것도 알 수 없습니다. `EXPERIMENT_KEY_VERSION`도 같은 이유로 존재하며, 해시 입력이 바뀔 때 올라갑니다. 겉모습만 고치는 수정으로는 결코 올리지 않습니다.

**실행 횟수는 키에 포함됩니다.** 같은 셀에 대한 `--runs 1`과 `--runs 10`은 의도적으로 같은 키를 공유하지 않습니다. 후자는 전자가 답할 수 없는 분산에 관한 물음에 답하므로, 둘을 한데 묶는 모니터는 점 추정치를 분포와 비교하게 됩니다.

**모델 목록은 의도적으로 정렬하지 않습니다.** 정렬하면 `--models a,b`와 `--models b,a`가 같은 키를 공유하게 되고, 측정되는 셀이 같다는 점에서 그럴 만도 합니다. 하지만 `compare`의 `prompt_id`는 위치 기반 행 번호이므로, 그 두 실행에서 `p1`은 서로 다른 모델을 가리킵니다. `(experiment_key, prompt_id)`로 둘을 결합한 소비자는 두 키가 일치하는 채로 모든 행을 어긋나게 맞추게 됩니다. 잘못된 "다름" 판정은 비교 한 번을 건너뛰는 대가로 끝나지만, 잘못된 "같음" 판정은 비교 한 번을 조용히 망칩니다. temperature 목록이 주어진 순서를 유지하는 것도 같은 이유입니다.

**`experiment_key`가 같다고 해서 결과가 같지는 않습니다.** `gemini-3.8-flash`에서 실제로 측정한 결과입니다. 키가 볼 수 있는 모든 면에서 동일한 두 번의 호출이 같은 출력 텍스트(두 번 모두 `Paris`)를 돌려주면서도, 출력 토큰은 65와 58, 비용은 `$0.00025125`와 `$0.000225`였습니다. 입력을 10으로 고정하고 결과가 돌아온 여덟 번의 실행에서 `output_tokens`는 58에서 66까지 걸쳐 있었는데, 사고형 모델의 내부 토큰이 호출마다 달라지기 때문입니다. 이 여덟 번은 골라낸 것이 아니라 전체입니다. 2026-09-06에 열네 번을 시도했고 그중 여섯 번은 503이 돌아와 0 토큰의 죽은 셀이 되었으며, 거기서는 범위를 얻을 수 없습니다. 따라서 같은 실험의 두 실행 사이에서 비용이 움직이는 것은 정상이며, 무언가가 바뀌었다는 증거가 아닙니다. 이는 키에 반하는 사실이 아니라 오히려 키를 뒷받침하는 사실입니다. 비용이 다른 두 실행을 그럼에도 같은 실험으로 인식할 수 있다는 것 - 그 차이에 의미가 있는지 묻기 전에 바로 그것이 필요합니다.

#### 두 실행 비교하기

`diff`는 이미 가지고 있는 두 개의 JSON 출력을 읽고 무엇이 움직였는지 보고합니다. 아무것도 쓰지 않고, 저장하지 않으며, 감시하지 않습니다.

```bash
cli-modelarium compare "capital of France?" --models gpt-5.5,claude-opus-4-8 --output before.json
# ... 나중에 ...
cli-modelarium compare "capital of France?" --models gpt-5.5,claude-opus-4-8 --output after.json

cli-modelarium diff before.json after.json
```

<p align="center">
  <img src="docs/assets/cli-modelarium-diff-demo-4model.gif" alt="cli-modelarium 터미널 데모: 동일한 비교를 claude-fable-5-1, gemini-3.8-flash, gemini-3.7-flash, claude-haiku-4-5 네 모델에서 두 번 실행하면, diff가 모든 응답 텍스트는 변하지 않았다고 보고하는 한편 비용은 Gemini 두 행에서는 움직이고 Claude 두 행에서는 그대로다." width="1088">
</p>

**방향은 인자 순서가 정합니다.** 타임스탬프가 무엇을 말하든, 첫 번째 파일이 앞선 실행으로 읽힙니다. 같은 초에 쓰인 두 실행을 정렬할 수 있는 것은 출력 안에 없습니다. `started_at`은 초 단위 정밀도이고 `run_id`는 시각을 담지 않는 무작위 UUID이기 때문입니다. 그래서 언제나 사용할 수 있는 규칙은 여러분이 입력한 순서뿐입니다. `started_at`이 이와 어긋나면 `diff`는 그 사실을 알리고 계속 진행합니다.

비교 대상은 파일이 아니라 셀입니다. `--temperatures 0,0`은 같은 셀을 두 번 요청하므로 모델·temperature·시스템 프롬프트가 같은 행이 둘 존재할 수 있습니다. 그래서 결합은 각 행이 자기 셀 그룹 안에서 몇 번째인지도 함께 셉니다. 변화가 없는 셀은 숨겨지며 `--all`로 볼 수 있습니다.

**표시되는 모든 셀은 숫자보다 먼저 응답 텍스트가 바뀌었는지를 보고합니다.** 사고형 모델은 같은 텍스트를 다른 토큰 비용으로 반환하는 일이 흔하므로 "비용은 움직였고 응답은 그대로"가 일반적인 해석입니다. 반대로 토큰 수가 같은 채 응답만 바뀐 경우에는 그 밖에 움직인 것이 없어 숨겨졌을 것입니다. 같은지 다른지만 알려주며 유사도 점수는 내지 않습니다. 거기에 백분율을 쓰면 출력에 없는 숫자를 만들어 내는 일이기 때문입니다. 한쪽이 거부하거나 오류가 났거나 중단된 경우에는 비교할 응답이 없으며, 명령이 그 사실을 알려줍니다.

**거부하는 것:** 프롬프트 변경, 실행 횟수 변경(한 번은 점추정이고 열 번은 분포입니다), 그리고 `batch` 출력과 `compare` 출력의 조합입니다. 모델을 추가하거나 제거하는 것은 거부 사유가 아닙니다. 겹치는 셀은 여전히 비교 가능하며, 한쪽에서만 실행된 셀은 따로 나열됩니다.

**거부 대신 단서를 다는 것:** 서로 다른 요금표로 계산된 두 출력은 여전히 비교 가능하지만, 비용 차이의 일부는 모델이 아니라 가격표에서 옵니다. 그 사실은 어떤 비용 수치보다 먼저 표시됩니다. 중단된 실행, 바뀐 판정 모델, 0.2.0 이전 출력도 같은 방식으로 표시됩니다. 오래된 출력도 행 내용을 맞춰 비교하며, 그 형식이 알려줄 수 없는 두 가지 - 어떤 명령이 출력을 썼는지, 어떤 판정 모델이 실행되었는지 - 를 `diff`가 명시합니다.

유의성 판정은 양쪽 모두 출력되며 결코 빼지 않습니다. p-값은 하나의 표본을 기술하므로, 독립된 실행에서 나온 두 p-값은 모두 참이고 그 차이는 어느 쪽도 담고 있지 않은 양입니다.

`--output-format json`은 변경 여부와 무관하게 모든 셀, 여섯 개 지표 전부, 그리고 모든 단서를 담습니다. 콘솔에는 움직인 셀의 비용, 지연, 출력 토큰이 표시됩니다. 종료 코드는 위 표에 있습니다. 아무것도 움직이지 않으면 `0`, 무언가 움직이면 `4`, 비교할 수 없는 쌍이면 `2`입니다.

**개인정보 관련 참고:** JSON, CSV, Markdown 등 모든 출력 형식에는 각 결과의 전체 프롬프트, 전체 시스템 프롬프트, 전체 모델 응답, 그리고 제공업체의 오류 메시지가 포함됩니다. JSON에는 각 판정 모델의 추론 텍스트도 포함됩니다. `--include-reasoning`은 콘솔 표시만 제어하며 파일에는 영향을 주지 않고, CSV와 Markdown에는 포함되지 않습니다. 출력 파일을 커밋하거나 공개 CI 아티팩트로 업로드하기 전에 민감한 정보로 취급하십시오. 데이터 보존 및 학습 관련 약관은 제공자마다 다르며, 이 도구는 그중 어느 것도 주장하지 않습니다. 설정하는 각 제공자의 약관을 확인하십시오. Claude Fable 5.1은 30일 데이터 보존을 요구하며 제로 데이터 보존으로는 사용할 수 없습니다. 판정 모델은 두 번째 제공업체입니다. `--judge`는 모델 응답뿐 아니라 프롬프트도 판정 모델에 전송하므로, 판정을 사용하면 프롬프트를 보는 범위가 넓어집니다. 첫 번째 모델이 거부한 요청은 이제 판정 모델로 전송되지 않습니다. `compare` 리포트는 이를 생성한 환경(도구 버전, 설치된 `scipy`의 정확한 버전, 전체 Python 버전)도 실행 횟수와 관계없이 JSON과 Markdown의 `methodology` 블록에 기록합니다. 이는 사용자의 데이터가 아니라 호스트 메타데이터이지만 의존성 버전을 정확히 고정합니다. CSV에는 전혀 포함되지 않으며 `batch`는 아무것도 기록하지 않습니다.

## 구성

### API 키

Cli Modelarium은 API 키를 OS 네이티브 키체인 (Mac Keychain, Windows Credential Manager 또는 `keyring`을 통한 Linux Secret Service)에 저장합니다. 키는 절대로 디스크에 평문으로 저장되지 않습니다.

```bash
# 대화형 설정 (권장)
cli-modelarium configure

# 또는 개별적으로 설정
cli-modelarium keys set openai
cli-modelarium keys set anthropic
cli-modelarium keys set google

# 어떤 키가 구성되었는지 확인
cli-modelarium keys list

# 키 제거
cli-modelarium keys delete openai
```

환경 변수도 사용할 수 있습니다 (CI/CD에 유용):

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
```

환경 변수는 키체인 저장보다 우선합니다.

### 로컬 모델 (Ollama, LM Studio 등)

로컬 모델은 OpenAI 호환 엔드포인트를 통해 작동합니다 - API 키가 필요하지 않습니다. 도구는 Ollama의 기본 포트를 자동으로 감지합니다.

```bash
# 기본값: Ollama가 localhost:11434에 있다고 가정
cli-modelarium "test" --models local/llama-3.3

# 대신 LM Studio 사용
cli-modelarium "test" --models local/qwen-3-32b --local-url http://localhost:1234/v1

# 사용자 정의 로컬 URL을 기본값으로 저장
cli-modelarium keys set local --base-url http://localhost:1234/v1
```

## 지원되는 제공자

| 제공자 | API 키 필요 | 스트리밍 | 비용 추적 | 가격 검증 |
|----------|-----------------|-----------|---------------|------------------|
| OpenAI (GPT-6 Astra, GPT-5.6 Sol, GPT-5.5, o3 등) | ✅ | ✅ | ✅ | `first-party` |
| Anthropic (Claude Opus 5, Sonnet 5, Fable 5.1, Haiku 4.5 등) | ✅ | ✅ | ✅ | `first-party` |
| Google (Gemini 3.8 Flash, 3.7 Flash, 3.1 Pro 등) | ✅ | ✅ | ✅ | `first-party` |
| xAI (Grok 4.6, Grok 4.3 등) | ✅ | ✅ | ✅ | `first-party` |
| DeepSeek (V4 Pro, V4 Flash 등) | ✅ | ✅ | ✅ | `first-party` |
| Mistral (Medium, Large, Small, Codestral) | ✅ | ✅ | ✅ | `first-party` |
| Groq (Llama 3.3, Llama 4 Scout, gpt-oss) | ✅ | ✅ | ✅ | `third-party` |
| OpenRouter (등록된 8개 ID: Qwen, DeepSeek R1, Llama 3.3, gpt-oss, GLM) | ✅ | ✅ | ✅ | `unchecked` |
| Alibaba/DashScope (Qwen3.8 Max, Qwen3.7 Max, Qwen3 Coder 등; 일부 Qwen 모델, International/Singapore) | ✅ | ✅ | ✅ | `first-party` |
| Z.AI/GLM (GLM-5.3, GLM-5.2, GLM-4.7 등; OpenAI 호환, 해외 엔드포인트) | ✅ | ✅ | ✅ | `first-party` |
| NVIDIA NIM (등록된 9개 ID: Nemotron, Gemma 4, Mistral Nemotron, MiniMax M3, Laguna, Llama 3.1) | ✅ | ✅ | 공개된 요금 없음 | `unpublished` |
| Moonshot AI / Kimi (등록된 4개 ID: K3, K2.7 Code, K2.7 Code HighSpeed, K2.6) | ✅ | ✅ | ✅ | `reseller` |
| **로컬: Ollama** | ❌ | ✅ | 무료 | — |
| **로컬: LM Studio** | ❌ | ✅ | 무료 | — |
| **로컬: vLLM** | ❌ | ✅ | 무료 | — |
| **로컬: llama.cpp server** | ❌ | ✅ | 무료 | — |

현재 지원되는 모든 모델을 보려면 `cli-modelarium list-models`를 실행하십시오.

## 모델 그룹

모델 ID를 나열하는 대신 `--models`는 그룹 단축어를 받습니다. 정적 그룹은 그대로 확장됩니다. 아래에 나열된 모든 구성원이 실행되므로 그룹이 포함하는 각 제공자의 키가 필요하며, 키가 없는 첫 번째 지점에서 실행이 중단됩니다. 동적 그룹인 `all`과 `all-local`은 예외로, 이들은 실제로 구성된 항목을 기준으로 확인됩니다.

**정적 그룹** (고정 멤버십):

| 그룹 | 모델 |
|-------|--------|
| `all-premium` / `all-flagship` | gpt-5.6-sol, claude-opus-5, gemini-3.1-pro-preview, grok-4.6, deepseek-v4-pro, mistral-large-latest, qwen3.8-max, glm-5.2 |
| `all-budget` | gpt-5.4-nano, claude-haiku-4-5, gemini-3.1-flash-lite, grok-4.20-0309-non-reasoning, deepseek-v4-flash, mistral-small-latest, qwen3.7-plus, glm-4.5-air |
| `all-reasoning` | o3, o4-mini, deepseek-v4-pro, glm-5.2 |
| `all-cheap` | gpt-4o-mini, claude-haiku-4-5, gemini-2.5-flash-lite, deepseek-v4-flash, mistral-small-latest, qwen-flash, glm-4.7-flashx |
| `all-open-weight` | openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, llama-3.3-70b-versatile, meta-llama/llama-4-scout-17b-16e-instruct |

**동적 그룹** (런타임에 확인됨):

- `all` — 구성된 API 키를 보유한 모든 클라우드 모델(로컬 모델, OpenRouter, NVIDIA 제외. 뒤의 둘은 제공자의 전체 카탈로그가 아니라 등록된 일부이며, NVIDIA는 비용을 제시할 수 없습니다). 많은 모델로 확장될 수 있으므로 `--max-cost`와 함께 사용하십시오.
- `all-local` — 실행 중인 로컬 서버(Ollama / LM Studio / vLLM / llama.cpp)가 보고하는 모든 모델. 도달 가능한 서버가 없으면 오류 대신 명확한 메시지가 표시됩니다.

```bash
cli-modelarium "CAP 정리를 설명하세요" --models all-budget
cli-modelarium "CAP 정리를 설명하세요" --models all --max-cost 0.50
cli-modelarium "CAP 정리를 설명하세요" --models all-local
```

## 작동 방식

Cli Modelarium은 OpenAI의 `messages` 배열, Anthropic의 최상위 `system` 매개변수, Google의 `system_instruction` 등 API 간의 차이를 숨기는 모듈식 제공자 추상화 계층을 사용합니다. 모든 제공자가 동일한 비동기 스트리밍 인터페이스를 구현하므로 CLI는 `asyncio.gather()`로 모든 제공자를 병렬로 실행할 수 있습니다.

비용 계산은 각 제공자의 보고된 `usage` 필드(입력 토큰, 출력 토큰, 캐시된 토큰)에 현재 가격 상수를 곱하여 산출됩니다. 대부분의 가격 데이터는 **2026년 9월 6일**에 공식 제공자 문서에서 검증되었습니다. 네 개 제공자는 완전히 다루어지지 않았습니다 - [참고사항 및 제한사항](#참고사항-및-제한사항)을 참조하십시오.

로컬 모델의 경우 Ollama, LM Studio, vLLM 및 llama.cpp 모두 OpenAI 호환 REST 엔드포인트를 노출하므로 사용자 정의 `base_url`과 함께 동일한 OpenAI Python SDK가 사용됩니다.

## 참고사항 및 제한사항

### 가격 데이터

Cli Modelarium에 포함된 대부분의 가격은 **2026년 9월 6일**에 공식 제공자 문서에서 검증되었습니다. 일부 항목은 레지스트리에서 각 항목 옆에 기재된 자체 검증 날짜를 가집니다. Groq, Moonshot, NVIDIA, OpenRouter는 이번 검증에서 완전히 확인되지 않았으며 레지스트리에 미검증으로 표시되어 있습니다. 두 가지 요금이 만료됩니다. `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.8-flash`는 2027년 1월 1일에 두 배가 되는 도입 요금이며, `gpt-5.6-sol`은 2026년 11월 21일경에 종료되는 프로모션 요금입니다. 둘 다 오늘 실행한 비교를 나중의 동일한 실행보다 저렴해 보이게 만들고 균일하게 변동하므로, 출력에서 이상하게 눈에 띄는 것이 없습니다. LLM 가격은 자주 변경됩니다(때로는 매월). `pricing_as_of` 날짜는 JSON 및 Markdown 출력에 포함되고 콘솔에 표시됩니다. CSV 출력에는 포함되지 않습니다. 예산 책정이나 프로덕션 결정을 위해 비용 계산에 의존하기 전에 항상 각 제공자의 공식 가격 페이지와 대조하여 확인하십시오.

가격은 각 제공자의 1M 토큰당 표준/정가 공개 요금입니다(배치, 우선순위, 오프피크 또는 프로모션 가격이 아님. 주석이 달린 예외가 하나 있습니다: `gpt-5.6-sol`의 현재 공개 요금은 프로모션 가격입니다). 입력 크기별로 티어가 나뉘는 모델의 경우 진입/짧은 컨텍스트 티어가 표시되며, 캐시 가격은 캐시 읽기 요금입니다. DashScope/Qwen 비용은 비사고(non-thinking) 요금을 반영합니다(도구가 `enable_thinking=false`를 전송함).

NVIDIA NIM은 예외입니다. NVIDIA는 호스팅되는 NIM 엔드포인트에 대해 토큰당 요금을 공개하지 않으므로 NVIDIA 모델의 비용은 추적되지 않습니다. 비용 열에 표시되는 0은 요금이 없다는 뜻이며 가격이 0이라는 의미가 아닙니다. 이 비용은 항상 0이기 때문에 NVIDIA 모델에서는 `--max-cost`가 절대 작동하지 않고 `cost_under` 어설션은 항상 통과합니다. 두 가지 모두 이 제공자에서는 지출을 막아 주지 못합니다. 접근은 토큰당 청구가 아니라 계정 크레딧으로 측정되므로, 주의해야 할 것은 예상치 못한 청구서가 아니라 크레딧 소진입니다. NVIDIA 모델이 실행에 포함되면 이를 알리는 주의 패널이 출력됩니다.

모델별 현재 요금을 확인하려면 `cli-modelarium pricing`(또는 `pricing --all`)을 실행하십시오.

### 속도 제한

속도 제한 처리 및 제공자별 기본 동시성 설정은 **2026년 6월 21일**에 검증된 제공자 속도 제한을 기반으로 합니다. 특정 티어의 제한은 여기에 가정된 기본값과 다를 수 있습니다. 프로덕션 용량 가정을 구축하기 전에 제공자의 공식 대시보드에서 현재 제한을 확인하십시오.

### 모델 가용성

Cli Modelarium에서 지원하는 모델은 **2026년 8월 15일**에 제공자가 제공한 것을 반영합니다. 제공자는 정기적으로 새 모델을 출시하고 오래된 모델을 폐기하며 기능을 조정합니다. 레지스트리의 모델이 더 이상 작동하지 않으면 `cli-modelarium list-models`를 실행하고 제공자의 문서를 확인하십시오.

### 프로덕션 등급 게이트웨이가 아님

Cli Modelarium은 평가 및 비교용으로 설계되었습니다 - 개발자 터미널에서 제공자 간에 임시 나란히 비교 테스트를 실행합니다. 프로덕션 추론 게이트웨이가 아닙니다. 프로덕션 규모의 라우팅, 로드 밸런싱, 폴백 체인 또는 SLA 관리 추론이 필요한 경우 해당 목적을 위해 특별히 구축된 도구를 찾으십시오.

### 제공자 간 토큰 수 비교

결과에 표시되는 토큰 수는 각 제공자의 API에서 보고됩니다. 다른 제공자는 다른 토크나이저를 사용하므로 동일한 텍스트에 대해 "출력 토큰"은 제공자 간에 직접 비교할 수 없습니다. 프로덕션 사용을 위한 비용 효율성을 비교하는 경우 실제 워크로드에서 실제 프롬프트를 실행하십시오 - 제공자 간 토큰당 계산에만 의존하지 마십시오.

### LLM-as-a-Judge 사용

Cli Modelarium에는 `--judge` 플래그로 활성화되는 선택적 LLM-as-a-judge 스코어링이 포함되어 있으며, 이는 한 LLM을 사용하여 다른 LLM의 출력을 평가합니다. 이는 표준 벤치마킹 방법론이며 지원되는 모든 제공자의 서비스 약관에 따라 평가/벤치마킹 활동으로 허용됩니다.

`--judge`를 사용할 때 사용자는 사용하는 각 제공자의 모델의 서비스 약관을 준수할 책임이 있습니다. 각 제공자의 ToS는 평가되는 모델과 저지 모델 자체 모두에 적용됩니다.

**저지 편향 공지:** LLM 저지는 문서화된 편향(자기 선호, 동일 패밀리 선호, 장황함 선호)을 가지고 있습니다. 저지 점수는 유용한 신호이지 절대적 진실이 아닙니다. 편향을 줄이려면 저지 패널(여러 모델을 사용한 `--judges`)을 사용하십시오.

### 환각 감지

환각 감지 프리셋은 모델 간의 유용한 비교 신호이지 절대적 진실 검증이 아닙니다. 감지 정확도는 사용된 저지 모델, 필요한 도메인 지식 및 `--expected-facts`를 통해 참조 사실이 제공되는지 여부에 따라 달라집니다. 절대적 정확성 검증이 아닌 상대적 품질 비교에 사용하십시오.

### 비교 방법론

LLM은 온도 > 0에서 비결정론적입니다 - 동일한 프롬프트를 다시 실행하면 다른 출력이 생성될 수 있습니다. 단일 비교 실행은 각 모델에서 하나의 샘플을 보여줄 뿐이지 결정적인 품질 판정이 아닙니다.

더 신뢰할 수 있는 결론을 도출하려면:
- `--runs 5`(또는 그 이상)를 사용하면 각 비교를 자동으로 N회 실행하고 통계 요약(평균/중앙값 지연 시간, 변동계수, 최빈 출력, 출력 다양성)을 확인할 수 있습니다. 변동계수가 0.05 미만이면 실행 간 모델 동작이 안정적임을 의미합니다.
- 환각 일관성 분석을 위해 `--runs`와 `--check-hallucination`을 함께 사용하면 여러 실행에서 모델이 얼마나 자주 환각을 일으키는지(환각 발생률)를 확인할 수 있습니다.
- 더 결정론적인 출력을 위해 `--temperatures 0` 사용. 일부 모델은 온도 설정을 전혀 받아들이지 않습니다 - `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `claude-fable-5-1`, `o3`, `o4-mini`, `gpt-5`, `gpt-5.5`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-6-astra`, `gemini-3.8-flash`, `kimi-k3`, `kimi-k2.7-code`, `kimi-k2.7-code-highspeed`, `kimi-k2.6`입니다. 도구는 이러한 모델에 대해 해당 필드를 생략하여 호출이 성공하도록 하며, 이 모델들은 제공자의 기본값으로 실행됩니다.
- `--system-prompts "간결하게.,자세하게."` 를 사용하면 같은 프롬프트를 여러 시스템 프롬프트로 실행해 나란히 비교할 수 있습니다. `--models`, `--temperatures` 와 마찬가지로 호출 수가 곱해집니다. 두 개 이상일 때 리포트는 각 행에 `SP 1`, `SP 2` 같은 라벨을 붙이고 전체 텍스트를 담은 범례를 출력합니다. 셀별 요약의 `SP 2` 는 그 위 표의 `SP 2` 와 같은 프롬프트입니다. CSV와 JSON은 각 행에 시스템 프롬프트 전문을 그대로 담습니다.
- 하나가 아닌 여러 프롬프트에 걸쳐 비교
- 체계적 분석을 위해 실행 결과를 저장하려면 `--output-format json` 플래그 사용(`--runs > 1`인 경우 JSON에 셀별 `stats_by_cell` 집계가 포함됩니다)

이 열아홉 개 모델은 온도 필드 없이 호출되며, JSON 출력의 `models_without_temperature`가 해당 실행에서 영향을 받은 모델을 나열합니다. 알아두어야 할 결과가 세 가지 있습니다. 여러 값을 지정한 `--temperatures` 스윕은 이러한 모델에 대해 실제 스윕이 아니라 동일한 요청을 보내며, 이 경우 도구가 경고를 출력합니다. 결과 테이블, CSV, 각 JSON 결과 레코드에 표시되는 온도는 실제로 적용된 값이 아니라 **요청된** 값입니다. 그리고 `--significance`는 이것이 라벨이 아니라 결론 자체를 바꿀 수 있는 지점입니다. 온도를 생략하는 모델과 온도를 반영하는 모델을 비교하면 표본 추출로 인한 분산 차이가 생기는데, Welch나 Mann-Whitney는 이를 모델 품질 차이인 것처럼 보고합니다. 이 경우에도 경고가 표시됩니다. 영향을 받는 모델과 받지 않는 모델을 섞은 유의성 검정은 제공업체 기본 온도로 실행된 모델의 이름을 명시한 `Temperature not applied` 패널을 출력하고, JSON 출력의 `significance_temperature_mixed`를 `true`로 설정합니다. 여러 온도를 사용하면서 동시에 혼합된 실행에서는 두 메시지가 하나의 패널에 함께 표시됩니다. CSV에는 이에 상응하는 신호가 없습니다.

## 프로젝트 소개

Cli Modelarium은 **SoraVantia GK**의 제품입니다. **Lavelle Hatcher Jr**가 처음 제작했으며 계속 유지 관리하고 있습니다.

- 📦 저장소: [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium)
- 💬 질문 또는 버그: [이슈 열기](../../issues)
- 🔧 메인테이너: [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)

## 제작 이유

제공자 간에 LLM 출력을 비교하는 것은 번거롭습니다 - 다른 SDK, 다른 인증 패턴, 다른 응답 형태, 비용 및 지연 시간 데이터와 함께 나란히 볼 수 있는 쉬운 방법이 없습니다. 세련된 클라우드 플레이그라운드는 한 번에 한 제공자만 표시하며, 사용 가능한 오픈 소스 옵션은 프로덕션 라우팅에 집중하거나 팀에 최적화된 본격적인 평가 플랫폼입니다.

Cli Modelarium은 한 가지를 잘 수행하는 작고 집중된 CLI 도구입니다: 품질 스코어링, 어설션, 배치 모드 및 스트리밍을 통한 나란히 비교 - 모두 터미널 우선 개발자 워크플로우를 위해 설계되었습니다.

의도적으로 집중되어 있습니다: 프로덕션 라우팅 없음, 에이전트 오케스트레이션 없음, 파인 튜닝 없음, GUI 없음. 명령줄에서 깔끔하고 빠른 비교만.

모듈식 제공자 추상화, 병렬 실행, 투명한 비용 계산, 로컬 사용자를 위한 OS 키체인 시스템을 통한 안전한 키 저장으로 구축되었습니다.

## 기여

이슈와 PR을 환영합니다. 지침은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참조하십시오.

보안 문제는 [SECURITY.md](SECURITY.md)를 참조하십시오 - 보안 우려사항에 대해 공개 이슈를 제출하지 마십시오.

## 라이선스

[Apache License, Version 2.0](LICENSE) 하에 라이선스가 부여됩니다.

귀속 요구사항은 [NOTICE](NOTICE) 파일을 참조하십시오.

---

SoraVantia GK의 제품이며 [Lavelle Hatcher Jr](https://linkedin.com/in/lavellehatcherjr)가 제작 및 유지 관리합니다

Apache 2.0 라이선스 하에 있습니다. 이슈, PR 및 대화를 환영합니다.
