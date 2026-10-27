function initIntegrationKeys() {
  const body = document.getElementById("apiKeysBody");
  if (!body) return;
  const el = id => document.getElementById(id);
  const error = message => {
    el("apiKeyError").textContent = message || "";
    el("apiKeyError").classList.toggle("d-none", !message);
  };
  const clearSecret = () => {
    el("apiKeySecret").value = "";
    el("apiKeySecretBox").classList.add("d-none");
  };
  const utc = value => /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value + "Z";
  const date = value => value ? fmtDate(utc(value)) : "—";

  async function load() {
    try {
      const keys = await apiGet("/api/accounts/integration-keys");
      body.replaceChildren();
      if (!keys.length) {
        const cell = body.insertRow().insertCell();
        cell.colSpan = 6;
        cell.className = "text-muted";
        cell.textContent = "Подключений нет";
      }
      for (const key of keys) {
        const row = body.insertRow();
        const name = row.insertCell();
        name.textContent = key.name;
        const prefix = document.createElement("div");
        prefix.className = "small text-muted font-monospace";
        prefix.textContent = "ltv_live_" + key.public_id;
        name.appendChild(prefix);
        name.title = key.scopes.join(", ");
        row.insertCell().textContent = String(key.tenant_id);
        row.insertCell().textContent = date(key.expires_at);
        row.insertCell().textContent = date(key.last_used_at);
        const expired = Date.parse(utc(key.expires_at)) <= Date.now();
        row.insertCell().textContent = key.revoked_at ? "Отозван" : expired ? "Истёк" : "Активен";
        const actions = row.insertCell();
        actions.className = "text-end";
        if (!key.revoked_at) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "btn btn-sm btn-outline-danger";
          button.title = "Отозвать ключ";
          button.setAttribute("aria-label", "Отозвать ключ");
          button.innerHTML = '<i class="bi bi-x-circle"></i>';
          button.addEventListener("click", async () => {
            if (!confirm("Отозвать API-ключ? Подключённая касса потеряет доступ.")) return;
            button.disabled = true;
            try {
              await apiDelete(`/api/accounts/integration-keys/${key.id}`);
              clearSecret();
              error("");
              await load();
            } catch (e) { error(e.message); button.disabled = false; }
          });
          actions.appendChild(button);
        }
      }
    } catch (e) { error(e.message); }
  }

  el("apiKeyCreate").addEventListener("click", async () => {
    const name = el("apiKeyName").value.trim();
    const scopes = Array.from(document.querySelectorAll('input[name="apiKeyScope"]:checked'), input => input.value);
    if (!name || !scopes.length) { error("Укажите название и хотя бы одно разрешение"); return; }
    const button = el("apiKeyCreate");
    button.disabled = true;
    clearSecret();
    error("");
    try {
      const result = await apiPost("/api/accounts/integration-keys", {
        name, scopes, expires_in_days: Number(el("apiKeyDays").value),
      });
      el("apiKeySecret").value = result.token;
      el("apiKeySecretBox").classList.remove("d-none");
      await load();
    } catch (e) { error(e.message); }
    finally { button.disabled = false; }
  });
  el("apiKeyCopy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(el("apiKeySecret").value); uiToast("Ключ скопирован", "success"); }
    catch { error("Копирование недоступно. Выделите ключ в поле"); }
  });
  el("apiKeyHide").addEventListener("click", clearSecret);
  el("apiKeyRefresh").addEventListener("click", load);
  window.addEventListener("pagehide", clearSecret);
  load();
}
