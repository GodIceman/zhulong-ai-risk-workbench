# Security Policy

## Supported versions

Security fixes are applied to the latest commit on `main`. There is currently no separately maintained long-term-support branch.

## Reporting a vulnerability

Please do not publish credentials, exploit details, private media, or personal data in a public issue.

Use GitHub's **Security → Report a vulnerability** flow for this repository. Include the affected version or commit, reproduction steps, impact, and a minimal privacy-safe proof of concept. If private vulnerability reporting is temporarily unavailable, open a public issue containing only a request for a private contact channel and no sensitive details.

## Security scope

Reports are especially useful for:

- media upload validation or path traversal;
- unexpected network transmission of local content;
- cross-origin policy bypass;
- report persistence or deletion failures;
- unsafe model or checkpoint loading;
- dependency or workflow supply-chain risks.

Model accuracy disagreements and normal domain-shift errors are product-quality issues, not security vulnerabilities, unless they enable a concrete security or privacy impact.
