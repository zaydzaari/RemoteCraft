# Roadmap

RemoteCraft stays intentionally small: one trusted operator, one trusted Linux host, and
one clear Vanilla Minecraft workflow. Roadmap items should preserve that focus and the
strict SSH boundary.

## Near term

- Show exactly which remote host tools are missing in the dashboard.
- Add an Ubuntu installer smoke test and document other tested distributions.
- Add a read-only `server.properties` view before considering validated editing.
- Add explicit backup creation, retention, and restore confirmation.

## Later

- Replace the GNU Screen implementation with a process-adapter boundary and user-level
  systemd implementation.
- Add a host inventory model without weakening per-host path and key controls.
- Evaluate Paper support behind a separate, tested server-type adapter.
- Add read-only CPU, memory, and disk telemetry with bounded polling.

## Not planned

- A general-purpose web terminal
- Multi-tenant hosting or billing
- Automatic trust of unknown SSH host keys
- Unverified server or plugin downloads

Open a [feature request](https://github.com/zaydzaari/RemoteCraft/issues/new/choose) or
start a [Discussion](https://github.com/zaydzaari/RemoteCraft/discussions) before working
on a large change.
