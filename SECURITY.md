# Security policy

## Reporting

Please report vulnerabilities privately through GitHub Security Advisories. Do not include live credentials, private package contents, or sensitive import reports in a public issue.

## Scope and safety model

`import-effects` executes the requested import in a child process. It is not a sandbox and does not make untrusted code safe. The child inherits the user's OS account permissions and a largely unchanged environment so ordinary imports continue to work.

The tool never installs packages. It redacts likely credentials from captured messages, never reports environment values, caps target output, validates module names, and applies a timeout. These controls reduce accidental disclosure and runaway imports but are not a security boundary against malicious Python or native code.

Supported security fixes target the latest released version.

