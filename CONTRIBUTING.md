# Contributing

Thanks for helping improve RemoteCraft.

## Development setup

```bash
git clone https://github.com/zaydzaari/RemoteCraft.git
cd RemoteCraft
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

## Before opening a pull request

```bash
ruff format --check .
ruff check .
pytest --cov=remotecraft --cov-report=term-missing
python -m build
```

Keep changes focused and include tests for behavior changes. Remote lifecycle tests should
use a fake SSH session and must not require access to a real server.

## Security-sensitive changes

Changes to authentication, input validation, remote command construction, download
verification, path handling, or host-key policy need explicit regression tests. Never add
real credentials or `.env` files to commits, fixtures, screenshots, issues, or pull
requests.

Report suspected vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
