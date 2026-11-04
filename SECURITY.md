# Security Policy

## Supported Versions

UNS (Unified Notification Service, package `uns`) is pre-1.0 software. Security fixes are provided for the latest published release and the current `main` branch. Older release lines are not maintained separately; upgrade to the latest release to receive fixes.

| Version | Supported |
| :--- | :--- |
| Latest published release | Yes |
| Current `main` | Yes |
| Older releases | No |

## Threat Model & Security Boundaries

For an authoritative description of authentication, principal attribution, policy override protections, WebSocket subprotocol handshakes, MCP write gates, and known operational boundaries, read [`docs/SECURITY-MODEL.md`](docs/SECURITY-MODEL.md) before deploying UNS.

## Reporting a Vulnerability

Please report suspected security vulnerabilities through **GitHub Private Vulnerability Reporting** (`Security` -> `Report a vulnerability`) on this repository. **Do not open a public GitHub issue for a security vulnerability.**

Please include:

- Affected version or commit SHA
- Step-by-step reproduction or proof-of-concept test
- Impact and affected deployment surface (HTTP API, WebSocket, `uns-mcp`, `uns-maintain`, or `UNS Console`)
- Relevant logs or payloads with all real credentials redacted

Maintainers will acknowledge reports promptly, validate the finding, coordinate remediation, and publish a security advisory when operator action or upgrading is required.
