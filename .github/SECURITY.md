# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.7.x   | Yes       |
| < 0.7   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in Meshpoint, please report it
responsibly. **Do not open a public GitHub issue.**

Email **security@meshradar.io** with:

- Description of the vulnerability
- Steps to reproduce
- Affected component (edge, cloud, installer, config)
- Potential impact
- Any suggested fix (optional)

You will receive an acknowledgment within 48 hours. We will work with you to
understand the scope, develop a fix, and coordinate disclosure.

## Scope

The following are in scope for security reports:

- Authentication and authorization flaws
- Encryption or key handling issues
- Remote code execution
- Privilege escalation
- Data exposure (API keys, credentials, user data)
- Installer or provisioning script vulnerabilities
- Denial of service against the edge device

## Out of Scope

- Vulnerabilities in upstream dependencies (report those to the upstream project)
- RF interference or jamming (physical layer, not software)
- Issues requiring physical access to the Raspberry Pi

## Development plugin and public-view boundaries

The unreleased v0.8.0 branch adds opt-in public aggregate summaries and optional
apps. Report page-selection bypasses, exposure of private data through public
routes, Viewer writes, plugin asset traversal and source/archive validation
failures through the private reporting process above.

Public viewing is disabled by default. A trusted Viewer login can read more
data than an anonymous summary visitor, including conversations. See
[Dashboard access](../docs/DASHBOARD-ACCESS.md) for the access matrix.

Installed plugins are trusted application code, not a security sandbox.
Reticulum process isolation protects core lifecycle behavior, but does not make
arbitrary third-party code safe. Source pins make revisions explicit; they do
not certify a source. Never install unknown code or restore untrusted backups.
Native dependencies remain separately administered. See
[Plugins and themes](../docs/PLUGINS.md).

## Disclosure process

We follow coordinated disclosure. We ask that you give us reasonable time to
address the issue before any public disclosure. We will credit reporters in
release notes unless anonymity is requested.
