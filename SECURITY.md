# Security Policy

## Reporting a Vulnerability

If you find a security vulnerability in Cli Modelarium, please report it
privately so it can be fixed before any public disclosure.

**Please do not open a public issue for security vulnerabilities** - a public
issue would disclose the problem before there's a fix.

Instead, report it through GitHub's private vulnerability reporting:

- https://github.com/SoraVantia/cli-modelarium/security/advisories/new

This goes directly and privately to the maintainer. As this project is
maintained by one person, please allow reasonable time for a fix before public
disclosure. Thank you for reporting responsibly.

## Supported Versions

Only the latest released version receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Security Model

Cli Modelarium is built with these protections in mind:

- **API keys** are stored in your operating system's native keyring (macOS
  Keychain, Windows Credential Manager, Linux Secret Service) - they are not
  written to disk in plaintext by the tool.
- **Secrets are redacted** from displayed output and from the `error` field of
  saved reports. Redaction matches recognisable key prefixes - `sk-proj-`,
  `sk-ant-`, `sk-or-`, `sk-`, `xai-`, `gsk_`, `nvapi-` and `AIza` - along with
  fully-formed `Authorization: Bearer`, `x-api-key:` and `api_key=` forms.
  Mistral and Z.AI keys carry no prefix: their shapes are bare alphanumeric
  strings that cannot be told apart from model ids, request ids, hashes and
  base64 fragments, so no pattern can match them without redacting ordinary
  error text as well. Keys for those two providers are still redacted inside an
  auth header or an `api_key=` parameter, but a bare token quoted in a
  provider's error body is not - treat error output from Mistral and Z.AI as
  potentially sensitive.
- **Local model connections** are restricted to localhost by default.
- **No telemetry** - the tool does not phone home or send analytics.

## Known Limitations

- When you run a comparison, your prompts and inputs are sent to the
  third-party LLM providers you select (OpenAI, Anthropic, and others). How
  those providers handle your data is governed by their own policies, not by
  this tool.
