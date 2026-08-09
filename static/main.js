const state = { watches: [], system: null };

const elements = {
  form: document.querySelector("#watch-form"),
  addButton: document.querySelector("#add-button"),
  campgroundUrl: document.querySelector("#campground-url"),
  startDate: document.querySelector("#start-date"),
  endDate: document.querySelector("#end-date"),
  list: document.querySelector("#watch-list"),
  empty: document.querySelector("#empty-state"),
  count: document.querySelector("#watch-count"),
  systemState: document.querySelector("#system-state"),
  notificationNotice: document.querySelector("#notification-notice"),
  testNotification: document.querySelector("#test-notification-button"),
  checkAll: document.querySelector("#check-all-button"),
  version: document.querySelector("#version-label"),
  toastRegion: document.querySelector("#toast-region"),
};

const statusLabels = {
  pending: "Waiting for first check",
  unavailable: "No matching sites yet",
  available: "Availability found",
  paused: "Paused",
  expired: "Expired",
  error: "Check failed",
};

function localISODate(date = new Date()) {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function setDateMinimums() {
  const today = localISODate();
  elements.startDate.min = today;
  elements.endDate.min = today;
  elements.startDate.addEventListener("change", () => {
    if (!elements.startDate.value) return;
    const checkout = new Date(`${elements.startDate.value}T12:00:00`);
    checkout.setDate(checkout.getDate() + 1);
    const minimum = localISODate(checkout);
    elements.endDate.min = minimum;
    if (!elements.endDate.value || elements.endDate.value <= elements.startDate.value) {
      elements.endDate.value = minimum;
    }
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

async function load() {
  try {
    const [system, watches] = await Promise.all([api("/api/status"), api("/api/watches")]);
    state.system = system;
    state.watches = watches;
    renderSystem();
    renderWatches();
  } catch (error) {
    renderConnectionError();
    toast(error.message, "error");
  }
}

function renderSystem() {
  const { worker, notifications_configured: configured, notification_provider: provider } = state.system;
  const providerLabel = provider === "pushover" ? "Pushover" : "Twilio";
  elements.systemState.className = `system-state ${worker.is_running ? "is-online" : "is-warning"}`;
  elements.systemState.innerHTML = `
    <span class="status-dot"></span>
    <span>${worker.is_running ? "Watcher online" : "Watcher starting"}</span>
  `;
  elements.notificationNotice.hidden = configured;
  elements.testNotification.hidden = !configured;
  if (configured) {
    elements.notificationNotice.hidden = false;
    elements.notificationNotice.classList.add("notice-ready");
    elements.notificationNotice.querySelector("strong").textContent = `${providerLabel} is connected`;
    elements.notificationNotice.querySelector("p").textContent = "Send a test before you rely on your first alert.";
  } else {
    elements.notificationNotice.classList.remove("notice-ready");
  }
  elements.version.textContent = `v${state.system.version}`;
}

function renderConnectionError() {
  elements.systemState.className = "system-state is-error";
  elements.systemState.innerHTML = '<span class="status-dot"></span><span>Connection lost</span>';
}

function renderWatches() {
  const activeCount = state.watches.filter((watch) => watch.is_active).length;
  elements.count.textContent = activeCount;
  elements.empty.hidden = state.watches.length > 0;
  elements.list.innerHTML = state.watches.map(watchCard).join("");
}

function watchCard(watch) {
  const sites = watch.available_sites || [];
  const availableNights = new Set(sites.flatMap((site) => site.available_nights || [])).size;
  const resultLabel = watch.match_mode === "any_night"
    ? `${sites.length} ${plural(sites.length, "site")} · ${availableNights} open ${plural(availableNights, "night")}`
    : `${sites.length} full-stay ${plural(sites.length, "site")}`;
  const siteList = sites.length
    ? `<div class="site-results"><strong>${resultLabel}</strong><span>${escapeHtml(sites.slice(0, 8).map((site) => site.site).join(", "))}${sites.length > 8 ? ` +${sites.length - 8}` : ""}</span></div>`
    : "";
  const error = watch.last_error ? `<p class="watch-error">${escapeHtml(watch.last_error)}</p>` : "";
  const checked = watch.last_checked_at ? `Checked ${relativeTime(watch.last_checked_at)}` : "Not checked yet";
  const nights = dateDifference(watch.start_date, watch.end_date);

  return `
    <article class="watch-card status-${watch.status}" data-id="${watch.id}">
      <div class="watch-accent"></div>
      <div class="watch-main">
        <div class="watch-title-row">
          <div>
            <span class="status-pill"><i></i>${statusLabels[watch.status] || watch.status}</span>
            <h3>${escapeHtml(titleCase(watch.campground_name))}</h3>
          </div>
          <button class="icon-button" data-action="delete" title="Delete watch" aria-label="Delete ${escapeHtml(watch.campground_name)}">×</button>
        </div>
        <div class="trip-row">
          <div><small>ARRIVE</small><strong>${formatDate(watch.start_date)}</strong></div>
          <span class="trip-line"></span>
          <div><small>CHECK OUT</small><strong>${formatDate(watch.end_date)}</strong></div>
          <span class="night-count">${nights} ${plural(nights, "night")}</span>
          <span class="match-count">${watch.match_mode === "any_night" ? "ANY NIGHT" : "WHOLE TRIP"}</span>
        </div>
        ${siteList}
        ${error}
        <div class="watch-footer">
          <span>${checked}</span>
          <div class="watch-actions">
            <a href="${escapeAttribute(watch.campground_url)}" target="_blank" rel="noopener">View campground ↗</a>
            ${watch.is_active ? '<button data-action="check">Check</button><button data-action="toggle">Pause</button>' : watch.status !== "expired" ? '<button data-action="toggle">Resume</button>' : ""}
          </div>
        </div>
      </div>
    </article>`;
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(elements.addButton, true, "Adding…");
  try {
    const watch = await api("/api/watches", {
      method: "POST",
      body: JSON.stringify({
        campground_url: elements.campgroundUrl.value.trim(),
        start_date: elements.startDate.value,
        end_date: elements.endDate.value,
        match_mode: new FormData(elements.form).get("match_mode"),
      }),
    });
    state.watches.push(watch);
    renderWatches();
    elements.form.reset();
    toast(`Now watching ${titleCase(watch.campground_name)}.`);
    await checkOne(watch.id, true);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(elements.addButton, false);
  }
});

elements.list.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest("[data-id]");
  const watch = state.watches.find((item) => item.id === card.dataset.id);
  if (!watch) return;

  const action = button.dataset.action;
  if (action === "delete") {
    if (!window.confirm(`Stop watching ${titleCase(watch.campground_name)}?`)) return;
    try {
      await api(`/api/watches/${watch.id}`, { method: "DELETE" });
      state.watches = state.watches.filter((item) => item.id !== watch.id);
      renderWatches();
      toast("Watch removed.");
    } catch (error) {
      toast(error.message, "error");
    }
    return;
  }

  if (action === "check") await checkOne(watch.id);
  if (action === "toggle") {
    setBusy(button, true);
    try {
      const updated = await api(`/api/watches/${watch.id}/active`, {
        method: "POST",
        body: JSON.stringify({ active: !watch.is_active }),
      });
      replaceWatch(updated);
      toast(updated.is_active ? "Watch resumed." : "Watch paused.");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  }
});

async function checkOne(id, quiet = false) {
  const button = elements.list.querySelector(`[data-id="${id}"] [data-action="check"]`);
  if (button) setBusy(button, true);
  try {
    const updated = await api(`/api/watches/${id}/check`, { method: "POST" });
    replaceWatch(updated);
    if (!quiet) toast(updated.status === "available" ? "Availability found!" : "Check complete.");
  } catch (error) {
    await refreshWatches();
    toast(error.message, "error");
  } finally {
    if (button) setBusy(button, false);
  }
}

elements.checkAll.addEventListener("click", async () => {
  setBusy(elements.checkAll, true, "Checking…");
  try {
    await api("/api/check-all", { method: "POST" });
    await refreshWatches();
    toast("All active watches checked.");
  } catch (error) {
    await refreshWatches();
    toast(error.message, "error");
  } finally {
    setBusy(elements.checkAll, false);
  }
});

elements.testNotification.addEventListener("click", async () => {
  setBusy(elements.testNotification, true, "Sending…");
  try {
    const result = await api("/api/notifications/test", { method: "POST" });
    toast(result.message);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(elements.testNotification, false);
  }
});

async function refreshWatches() {
  state.watches = await api("/api/watches");
  renderWatches();
}

function replaceWatch(updated) {
  state.watches = state.watches.map((watch) => (watch.id === updated.id ? updated : watch));
  renderWatches();
}

function setBusy(button, busy, label = "Working…") {
  if (busy) {
    button.dataset.label = button.innerHTML;
    button.disabled = true;
    button.textContent = label;
  } else {
    button.disabled = false;
    if (button.dataset.label) button.innerHTML = button.dataset.label;
  }
}

function toast(message, type = "success") {
  const item = document.createElement("div");
  item.className = `toast toast-${type}`;
  item.textContent = message;
  elements.toastRegion.appendChild(item);
  requestAnimationFrame(() => item.classList.add("is-visible"));
  setTimeout(() => {
    item.classList.remove("is-visible");
    setTimeout(() => item.remove(), 220);
  }, 3800);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function relativeTime(value) {
  const delta = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function dateDifference(start, end) {
  return Math.round((new Date(`${end}T12:00:00`) - new Date(`${start}T12:00:00`)) / 86_400_000);
}

function plural(count, word) {
  return count === 1 ? word : `${word}s`;
}

function titleCase(value) {
  return value.toLocaleLowerCase().replace(/\b\w/g, (letter) => letter.toLocaleUpperCase());
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}

setDateMinimums();
load();
setInterval(load, 60_000);
