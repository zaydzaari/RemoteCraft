# Security policy

## Supported versions

RemoteCraft is currently alpha software. Security fixes are applied to the latest release
and the default branch only.

## Reporting a vulnerability

Please use [GitHub private vulnerability reporting](https://github.com/zaydzaari/RemoteCraft/security/advisories/new).
Do not open a public issue for a suspected vulnerability or include live credentials,
hostnames, tokens, private keys, or server logs in a report.

Include the affected version, a minimal reproduction, the expected impact, and any
suggested mitigation. You should receive an initial response within seven days.

## Deployment guidance

- Keep the HTTP server bound to loopback whenever possible.
- Use an SSH tunnel or a hardened HTTPS reverse proxy for remote access.
- Generate a unique, random API token of at least 32 characters.
- Prefer key-based SSH authentication with a dedicated, unprivileged user.
- Verify the remote SSH fingerprint before adding it to `known_hosts`.
- Do not grant the remote user passwordless `sudo` access.
- Keep the remote Java runtime and the control-plane Python dependencies patched.
