"use strict";

const state = {
  token: sessionStorage.getItem("remotecraft-token") || "",
  servers: [],
  activeServer: null,
  poller: null,
};

const elements = {
  connection: document.querySelector("#connection-state"),
  credentialsButton: document.querySelector("#credentials-button"),
  credentialsDialog: document.querySelector("#credentials-dialog"),
  credentialsClose: document.querySelector("#credentials-close"),
  credentialsForm: document.querySelector("#credentials-form"),
  credentialsError: document.querySelector("#credentials-error"),
  tokenInput: document.querySelector("#api-token"),
  forgetToken: document.querySelector("#forget-token"),
  refreshButton: document.querySelector("#refresh-button"),
  createForm: document.querySelector("#create-form"),
  serverRows: document.querySelector("#server-rows"),
  emptyState: document.querySelector("#empty-state"),
  totalCount: document.querySelector("#total-count"),
  onlineCount: document.querySelector("#online-count"),
  offlineCount: document.querySelector("#offline-count"),
  hostState: document.querySelector("#host-state"),
  versionSelect: document.querySelector("#server-version"),
  consoleDialog: document.querySelector("#console-dialog"),
  consoleClose: document.querySelector("#console-close"),
  consoleTitle: document.querySelector("#console-title"),
  consoleServerState: document.querySelector("#console-server-state"),
  consoleOutput: document.querySelector("#console-output"),
  commandForm: document.querySelector("#command-form"),
  commandInput: document.querySelector("#server-command"),
  toasts: document.querySelector("#toasts"),
};

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || body.error || message;
    } catch (_error) {
      // Keep the status-based fallback when a proxy returns non-JSON errors.
    }
    throw new ApiError(message, response.status);
  }
  return response.status === 204 ? null : response.json();
}

function setConnection(connected) {
  elements.connection.textContent = connected ? "Connected" : "Disconnected";
  elements.connection.dataset.state = connected ? "online" : "offline";
}

function toast(message, type = "success") {
  const notice = document.createElement("div");
  notice.className = `toast ${type}`;
  notice.textContent = message;
  elements.toasts.append(notice);
  window.setTimeout(() => notice.remove(), 4500);
}

function actionButton(label, action, server, variant = "secondary", disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `button button-${variant} button-small`;
  button.textContent = label;
  button.dataset.action = action;
  button.dataset.serverId = server.id;
  button.disabled = disabled;
  return button;
}

function renderServers() {
  elements.serverRows.replaceChildren();
  const online = state.servers.filter((server) => server.status === "online").length;
  elements.totalCount.textContent = String(state.servers.length);
  elements.onlineCount.textContent = String(online);
  elements.offlineCount.textContent = String(state.servers.length - online);
  elements.emptyState.classList.toggle("visible", state.servers.length === 0);

  for (const server of state.servers) {
    const row = document.createElement("tr");
    const identity = document.createElement("td");
    const identityWrap = document.createElement("div");
    identityWrap.className = "server-name";
    const name = document.createElement("strong");
    name.textContent = server.name;
    const id = document.createElement("span");
    id.textContent = server.id.slice(0, 12);
    identityWrap.append(name, id);
    identity.append(identityWrap);

    const release = document.createElement("td");
    release.textContent = server.version;
    const memory = document.createElement("td");
    memory.textContent = `${server.ram_gb} GB`;
    const status = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `status-badge ${server.status}`;
    badge.textContent = server.status;
    status.append(badge);

    const actions = document.createElement("td");
    const actionWrap = document.createElement("div");
    actionWrap.className = "row-actions";
    const isOnline = server.status === "online";
    actionWrap.append(
      actionButton("Start", "start", server, "primary", isOnline),
      actionButton("Stop", "stop", server, "secondary", !isOnline),
      actionButton("Restart", "restart", server, "secondary", !isOnline),
      actionButton("Console", "console", server, "secondary"),
      actionButton("Kill", "kill", server, "danger", !isOnline),
      actionButton("Delete", "delete", server, "danger", isOnline),
    );
    actions.append(actionWrap);
    row.append(identity, release, memory, status, actions);
    elements.serverRows.append(row);
  }
}

async function loadVersions() {
  const data = await api("/api/versions?limit=30");
  elements.versionSelect.replaceChildren();
  for (const version of data.versions) {
    const option = document.createElement("option");
    option.value = version;
    option.textContent = version;
    elements.versionSelect.append(option);
  }
}

async function refresh({ quiet = false } = {}) {
  if (!state.token) {
    setConnection(false);
    if (!elements.credentialsDialog.open) {
      elements.credentialsDialog.showModal();
    }
    return;
  }
  elements.refreshButton.disabled = true;
  try {
    const [servers, host] = await Promise.all([api("/api/servers"), api("/api/host")]);
    state.servers = servers;
    elements.hostState.textContent = host.ready ? "Ready" : "Tools missing";
    elements.hostState.style.color = host.ready ? "var(--green-strong)" : "var(--amber)";
    renderServers();
    setConnection(true);
  } catch (error) {
    setConnection(false);
    elements.hostState.textContent = "Unavailable";
    if (error.status === 401) {
      sessionStorage.removeItem("remotecraft-token");
      state.token = "";
      if (!elements.credentialsDialog.open) {
        elements.credentialsDialog.showModal();
      }
    } else if (!quiet) {
      toast(error.message, "error");
    }
  } finally {
    elements.refreshButton.disabled = false;
  }
}

async function connectWithToken(token) {
  state.token = token.trim();
  elements.credentialsError.textContent = "";
  try {
    await api("/api/servers");
    sessionStorage.setItem("remotecraft-token", state.token);
    elements.credentialsDialog.close();
    await Promise.all([loadVersions(), refresh()]);
    startPolling();
  } catch (error) {
    state.token = "";
    setConnection(false);
    elements.credentialsError.textContent = error.message;
  }
}

async function runAction(server, action) {
  const labels = {
    start: "Starting server",
    stop: "Stopping server",
    restart: "Restarting server",
    kill: "Killing server process",
  };
  try {
    await api(`/api/servers/${server.id}/${action}`, { method: "POST" });
    toast(`${labels[action]}: ${server.name}`);
    await refresh({ quiet: true });
  } catch (error) {
    toast(error.message, "error");
  }
}

async function deleteServer(server) {
  const confirmed = window.confirm(
    `Delete ${server.name} and its remote files? This cannot be undone.`,
  );
  if (!confirmed) {
    return;
  }
  try {
    const query = new URLSearchParams({ confirm: server.name });
    await api(`/api/servers/${server.id}?${query}`, { method: "DELETE" });
    toast(`Deleted ${server.name}`);
    await refresh({ quiet: true });
  } catch (error) {
    toast(error.message, "error");
  }
}

async function openConsole(server) {
  state.activeServer = server;
  elements.consoleTitle.textContent = server.name;
  elements.consoleServerState.textContent = server.status.toUpperCase();
  elements.commandInput.disabled = server.status !== "online";
  elements.commandForm.querySelector("button").disabled = server.status !== "online";
  elements.consoleOutput.textContent = "Loading logs...";
  if (!elements.consoleDialog.open) {
    elements.consoleDialog.showModal();
  }
  try {
    const data = await api(`/api/servers/${server.id}/logs?lines=150`);
    elements.consoleOutput.textContent = data.available
      ? data.lines.join("\n")
      : "No log file is available yet.";
    elements.consoleOutput.scrollTop = elements.consoleOutput.scrollHeight;
  } catch (error) {
    elements.consoleOutput.textContent = error.message;
  }
}

function startPolling() {
  window.clearInterval(state.poller);
  state.poller = window.setInterval(() => refresh({ quiet: true }), 10000);
}

elements.credentialsButton.addEventListener("click", () => {
  elements.tokenInput.value = "";
  elements.credentialsError.textContent = "";
  if (!elements.credentialsDialog.open) {
    elements.credentialsDialog.showModal();
  }
});

elements.credentialsClose.addEventListener("click", () => elements.credentialsDialog.close());

elements.credentialsForm.addEventListener("submit", (event) => {
  event.preventDefault();
  connectWithToken(elements.tokenInput.value);
});

elements.forgetToken.addEventListener("click", () => {
  sessionStorage.removeItem("remotecraft-token");
  state.token = "";
  state.servers = [];
  renderServers();
  setConnection(false);
  elements.credentialsError.textContent = "Token removed from this browser session.";
});

elements.refreshButton.addEventListener("click", () => refresh());

elements.createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(elements.createForm);
  const payload = {
    name: String(form.get("name")),
    version: String(form.get("version")),
    ram_gb: Number(form.get("ram_gb")),
    accept_eula: form.get("accept_eula") === "on",
  };
  const submit = elements.createForm.querySelector("button[type='submit']");
  submit.disabled = true;
  try {
    await api("/api/servers", { method: "POST", body: JSON.stringify(payload) });
    toast(`Created ${payload.name}`);
    elements.createForm.reset();
    await refresh({ quiet: true });
  } catch (error) {
    toast(error.message, "error");
  } finally {
    submit.disabled = false;
  }
});

elements.serverRows.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const server = state.servers.find((item) => item.id === button.dataset.serverId);
  if (!server) {
    return;
  }
  if (button.dataset.action === "console") {
    openConsole(server);
  } else if (button.dataset.action === "delete") {
    deleteServer(server);
  } else {
    runAction(server, button.dataset.action);
  }
});

elements.consoleClose.addEventListener("click", () => elements.consoleDialog.close());

elements.commandForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeServer) {
    return;
  }
  const command = elements.commandInput.value.trim();
  if (!command) {
    return;
  }
  try {
    await api(`/api/servers/${state.activeServer.id}/command`, {
      method: "POST",
      body: JSON.stringify({ command }),
    });
    elements.commandInput.value = "";
    toast("Command sent");
    window.setTimeout(() => openConsole(state.activeServer), 650);
  } catch (error) {
    toast(error.message, "error");
  }
});

renderServers();
if (state.token) {
  Promise.all([loadVersions(), refresh()]).then(startPolling).catch(() => refresh());
} else {
  elements.credentialsDialog.showModal();
}
