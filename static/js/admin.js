// =========================
// Helpers (UI)
// =========================
function show(el, msg, isErr = false) {
  if (!el) return;
  el.textContent = msg || "";
  el.classList.remove("d-none");
  el.className = isErr ? "text-danger small mt-2" : "text-success small mt-2";
}

function hide(el) {
  if (!el) return;
  el.classList.add("d-none");
}

function safeNum(val, def = 0) {
  const n = Number(val);
  return Number.isFinite(n) ? n : def;
}

function fmt0(x) {
  const n = Number(x || 0);
  return Number.isFinite(n) ? Math.round(n).toString() : "0";
}

function fmtMoney(val) {
  const n = safeNum(val, 0);
  return n.toLocaleString("ru-RU");
}

function fmtDate(dt) {
  try {
    if (!dt) return "—";
    return new Date(dt).toLocaleString("ru-RU");
  } catch {
    return "—";
  }
}

function ymdLocal(d) {
  try {
    const x = d instanceof Date ? d : new Date(d);
    const y = x.getFullYear();
    const m = String(x.getMonth() + 1).padStart(2, "0");
    const day = String(x.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  } catch {
    return "";
  }
}

function normalizePhone(phone) {
  if (!phone) return "";
  let p = String(phone).replace(/\D/g, "");
  if (!p) return "";
  if (p.startsWith("8") && p.length === 11) p = "7" + p.slice(1);
  if (p.length === 10) p = "7" + p;
  if (p.length > 11) p = p.slice(-11);
  return p;
}

function getQueryParam(name) {
  try {
    const u = new URL(window.location.href);
    return u.searchParams.get(name);
  } catch {
    return null;
  }
}

// =========================
// AI reco dismiss (localStorage)
// =========================
const AI_DISMISS_KEY = "ltv_ai_dismissed_v1";

function aiLoadDismissed() {
  try {
    const raw = localStorage.getItem(AI_DISMISS_KEY);
    const obj = raw ? JSON.parse(raw) : {};
    return obj && typeof obj === "object" ? obj : {};
  } catch {
    return {};
  }
}

function aiSaveDismissed(obj) {
  try {
    localStorage.setItem(AI_DISMISS_KEY, JSON.stringify(obj || {}));
  } catch {
    // ignore
  }
}

function aiRecoKey(context, phone, r) {
  const c = String(context || "business").trim();
  const p = String(phone || "").trim();
  const a = String(r?.action || "").trim();
  const t = String(r?.target || "").trim();
  const w = String(r?.why || "").trim();
  return `${c}|${p}|${a}|${t}|${w}`.slice(0, 480);
}

function aiIsDismissed(key) {
  const obj = aiLoadDismissed();
  return Boolean(obj && obj[key]);
}

function aiDismiss(key) {
  const obj = aiLoadDismissed();
  obj[key] = Date.now();
  aiSaveDismissed(obj);
}

function aiExecuteReco(context, phone, r) {
  const target = String(r?.target || "").trim();

  // 1) strict nav target (preferred)
  if (target.startsWith("nav:")) {
    const url = target.slice(4).trim();
    if (url.startsWith("/")) {
      window.location.href = url;
      return true;
    }
  }

  // 2) fallback heuristics
  const action = String(r?.action || "").toLowerCase();
  if (action.includes("кампан")) {
    window.location.href = "/admin/campaigns";
    return true;
  }
  if (action.includes("аналит") || action.includes("сегмент")) {
    window.location.href = "/admin/analytics";
    return true;
  }
  if (context === "client" && phone) {
    window.location.href = `/admin/transactions?phone=${encodeURIComponent(phone)}`;
    return true;
  }

  // 3) no-op
  if (typeof uiToast === "function") uiToast("Для этой рекомендации нет действия (target не nav:...)", "warning");
  return false;
}

// =========================
// Русификация "Tier" (только UI; API оставляем Bronze/Silver/Gold)
// =========================
const TIER_RU = { Bronze: "Бронза", Silver: "Серебро", Gold: "Золото" };

function tierRu(tier) {
  const t = String(tier || "").trim();
  return TIER_RU[t] || (t ? t : "Бронза");
}

function tierBadgeClass(tier) {
  const t = String(tier || "").trim();
  if (t === "Gold") return "bg-warning text-dark";
  if (t === "Silver") return "bg-info text-dark";
  return "bg-secondary";
}

// ТОЛЕРАНТНОСТЬ к старым/разным полям
function getRedeem(t) {
  return safeNum(t?.redeem_points ?? t?.redeemPoints ?? t?.redeem_bonus ?? t?.redeemBonus ?? 0, 0);
}
function getEarned(t) {
  return safeNum(t?.earned_points ?? t?.earnedPoints ?? t?.earned_bonus ?? t?.earnedBonus ?? 0, 0);
}

// =========================
// API
// =========================
async function apiGet(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data?.detail || `${r.status} ${r.statusText}`);
  return data;
}

async function apiPost(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(data),
  });
  const out = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(out?.detail || `${r.status} ${r.statusText}`);
  return out;
}

// =========================
// Theme
// =========================
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("theme", theme);
  const icon = document.getElementById("themeIcon");
  if (icon) icon.textContent = theme === "dark" ? "🌙" : "☀️";
}

function initTheme() {
  const saved = localStorage.getItem("theme");
  // ✅ по умолчанию LIGHT (под ваш дизайн)
  applyTheme(saved || "light");

  const btn = document.getElementById("themeToggle");
  if (btn) {
    btn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme") || "light";
      applyTheme(cur === "dark" ? "light" : "dark");
    });
  }
}

// =========================
// Add page class to <body> (critical for per-page styles)
// =========================
function applyBodyPageClass() {
  const page = String(window.__ADMIN_PAGE__ || "").trim();
  if (!page) return;
  try {
    document.body.classList.add(`page-${page}`);
    document.body.dataset.page = page;
  } catch {
    // ignore
  }
}

// =========================
// Global AI Panel (offcanvas)
// =========================
function initAiPanel() {
  const ctxEl = document.getElementById("aiPanelContext");
  const qEl = document.getElementById("aiPanelQuestion");
  const sendBtn = document.getElementById("aiPanelSendBtn");
  const clearBtn = document.getElementById("aiPanelClearBtn");
  const modeBadge = document.getElementById("aiPanelMode");
  const errEl = document.getElementById("aiPanelError");
  const ansEl = document.getElementById("aiPanelAnswer");
  const ulInsights = document.getElementById("aiPanelInsights");
  const boxRecos = document.getElementById("aiPanelRecos");

  if (!qEl || !sendBtn || !modeBadge || !ansEl || !ulInsights || !boxRecos || !ctxEl) return;

  let currentContext = "business";
  let currentPhone = null;
  let currentRecos = [];

  function setMode(mode) {
    const m = String(mode || "—");
    modeBadge.textContent = m;

    modeBadge.classList.remove("text-bg-secondary", "text-bg-success", "text-bg-warning", "text-bg-danger", "text-bg-info");
    if (m === "openai") modeBadge.classList.add("text-bg-success");
    else if (m === "gemini") modeBadge.classList.add("text-bg-success");
    else if (m === "heuristic") modeBadge.classList.add("text-bg-info");
    else if (m === "error") modeBadge.classList.add("text-bg-danger");
    else modeBadge.classList.add("text-bg-secondary");
  }

  function setError(text) {
    if (!errEl) return;
    errEl.textContent = text || "Ошибка";
    errEl.classList.remove("d-none");
  }

  function clearError() {
    if (!errEl) return;
    errEl.classList.add("d-none");
    errEl.textContent = "";
  }

  function renderInsights(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      ulInsights.innerHTML = `<li class="text-muted">—</li>`;
      return;
    }
    ulInsights.innerHTML = list.slice(0, 10).map((s) => `<li>${String(s)}</li>`).join("");
  }

  function renderRecos(items) {
    const list = Array.isArray(items) ? items : [];

    // filter dismissed
    const filtered = list.filter((r) => !aiIsDismissed(aiRecoKey(currentContext, currentPhone, r)));
    currentRecos = filtered;

    if (!filtered.length) {
      boxRecos.innerHTML = `<div class="text-muted small">—</div>`;
      return;
    }

    boxRecos.innerHTML = filtered.slice(0, 10).map((r, idx) => {
      const action = r?.action ? String(r.action) : "Действие";
      const target = r?.target ? String(r.target) : "—";
      const why = r?.why ? String(r.why) : "";
      const expected = r?.expected_effect ? String(r.expected_effect) : "";
      const risk = r?.risk ? String(r.risk) : "";
      const bonus = Number.isFinite(Number(r?.suggested_bonus)) ? Math.trunc(Number(r.suggested_bonus)) : null;

      return `
        <div class="border rounded p-2">
          <div class="d-flex align-items-start justify-content-between gap-2">
            <div class="fw-semibold">${action}</div>
            ${bonus !== null ? `<span class="badge text-bg-secondary">Бонус: ${bonus}</span>` : ``}
          </div>
          <div class="text-muted small mt-1"><span class="fw-semibold">Цель:</span> ${target}</div>
          ${why ? `<div class="small mt-2"><span class="text-muted">Почему:</span> ${why}</div>` : ``}
          ${expected ? `<div class="small mt-1"><span class="text-muted">Эффект:</span> ${expected}</div>` : ``}
          ${risk ? `<div class="small mt-1"><span class="text-muted">Риск:</span> ${risk}</div>` : ``}

          <div class="d-flex gap-2 mt-2">
            <button class="btn btn-sm btn-primary" type="button" data-ai-act="execute" data-ai-idx="${idx}">
              Выполнить
            </button>
            <button class="btn btn-sm btn-outline-secondary" type="button" data-ai-act="dismiss" data-ai-idx="${idx}">
              Скрыть
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  function inferContext() {
    // default: business
    const page = window.__ADMIN_PAGE__ || "";
    const rawPhone = window.__CLIENT_PHONE__ || "";
    const phone = normalizePhone(rawPhone);

    if (String(page) === "client" && phone) {
      return { context: "client", phone, label: `Контекст: client · ${phone}` };
    }
    return { context: "business", phone: null, label: "Контекст: business" };
  }

  async function ask() {
    clearError();

    const { context, phone, label } = inferContext();
    currentContext = context;
    currentPhone = phone;
    ctxEl.textContent = label;

    const question = String(qEl.value || "").trim();
    if (question.length < 2) {
      setError("Введите вопрос (минимум 2 символа)");
      return;
    }

    setMode("—");
    ansEl.textContent = "Загрузка…";
    renderInsights([]);
    renderRecos([]);
    sendBtn.disabled = true;

    try {
      const payload = { context, question, phone };
      const data = await apiPost("/api/ai/ask", payload);

      setMode(data?.mode || "—");
      ansEl.textContent = data?.answer ? String(data.answer) : "—";
      renderInsights(data?.insights);
      renderRecos(data?.recommendations);

      if (typeof uiToast === "function") uiToast(`AI ответил (${String(data?.mode || "ai")})`, "info");
    } catch (e) {
      setMode("error");
      ansEl.textContent = "—";
      setError(String(e.message || e));
      if (typeof uiToast === "function") uiToast("AI ошибка", "error");
    } finally {
      sendBtn.disabled = false;
    }
  }

  function clearAll() {
    clearError();
    qEl.value = "";
    ansEl.textContent = "—";
    renderInsights([]);
    renderRecos([]);
    setMode("—");
  }

  // recos click delegation
  boxRecos.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-ai-act]");
    if (!btn) return;

    const act = btn.getAttribute("data-ai-act");
    const idx = Number(btn.getAttribute("data-ai-idx") || "-1");
    if (!Number.isFinite(idx) || idx < 0 || idx >= currentRecos.length) return;

    const r = currentRecos[idx];
    const key = aiRecoKey(currentContext, currentPhone, r);

    if (act === "dismiss") {
      aiDismiss(key);
      renderRecos(currentRecos);
      if (typeof uiToast === "function") uiToast("Рекомендация скрыта", "info");
      return;
    }

    if (act === "execute") {
      if (typeof uiToast === "function") uiToast("Выполняю…", "info");
      aiExecuteReco(currentContext, currentPhone, r);
    }
  });

  // init context label once
  const initCtx = inferContext();
  currentContext = initCtx.context;
  currentPhone = initCtx.phone;
  ctxEl.textContent = initCtx.label;

  sendBtn.addEventListener("click", ask);
  clearBtn?.addEventListener("click", clearAll);

  qEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      ask();
    }
  });
}

// =========================
// AI Overview Widget (универсально для любых страниц)
// =========================
function initAiOverviewWidget() {
  const btn = document.getElementById("aiReloadBtn");
  const badge = document.getElementById("aiModeBadge");
  const ulInsights = document.getElementById("aiInsights");
  const boxRecos = document.getElementById("aiRecos");
  const errEl = document.getElementById("aiError");

  if (!btn || !badge || !ulInsights || !boxRecos) return;

  let currentContext = "business";
  let currentPhone = null;
  let currentRecos = [];

  function setBadge(mode) {
    const m = String(mode || "—");
    badge.textContent = m;

    badge.classList.remove(
      "text-bg-secondary",
      "text-bg-success",
      "text-bg-warning",
      "text-bg-danger",
      "text-bg-info"
    );
    if (m === "openai") badge.classList.add("text-bg-success");
    else if (m === "gemini") badge.classList.add("text-bg-success");
    else if (m === "heuristic") badge.classList.add("text-bg-info");
    else if (m === "error") badge.classList.add("text-bg-danger");
    else badge.classList.add("text-bg-secondary");
  }

  function setLoading() {
    hide(errEl);
    setBadge("—");
    ulInsights.innerHTML = `<li class="text-muted">Загрузка…</li>`;
    boxRecos.innerHTML = `<div class="text-muted small">Загрузка…</div>`;
  }

  function showError(msg) {
    if (!errEl) return;
    errEl.textContent = msg || "Ошибка";
    errEl.classList.remove("d-none");
  }

  function renderInsights(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      ulInsights.innerHTML = `<li class="text-muted">Нет инсайтов</li>`;
      return;
    }
    ulInsights.innerHTML = list
      .slice(0, 10)
      .map((s) => `<li>${String(s)}</li>`)
      .join("");
  }

  function renderRecos(items) {
    const list = Array.isArray(items) ? items : [];
    const filtered = list.filter((r) => !aiIsDismissed(aiRecoKey(currentContext, currentPhone, r)));
    currentRecos = filtered;

    if (!filtered.length) {
      boxRecos.innerHTML = `<div class="text-muted small">Нет рекомендаций</div>`;
      return;
    }

    boxRecos.innerHTML = filtered.slice(0, 10).map((r, idx) => {
      const action = r?.action ? String(r.action) : "Действие";
      const target = r?.target ? String(r.target) : "—";
      const why = r?.why ? String(r.why) : "";
      const expected = r?.expected_effect ? String(r.expected_effect) : "";
      const risk = r?.risk ? String(r.risk) : "";
      const bonus = Number.isFinite(Number(r?.suggested_bonus))
        ? Math.trunc(Number(r.suggested_bonus))
        : null;

      return `
        <div class="border rounded p-2">
          <div class="d-flex align-items-start justify-content-between gap-2">
            <div class="fw-semibold">${action}</div>
            ${bonus !== null ? `<span class="badge text-bg-secondary">Бонус: ${bonus}</span>` : ``}
          </div>
          <div class="text-muted small mt-1"><span class="fw-semibold">Цель:</span> ${target}</div>
          ${why ? `<div class="small mt-2"><span class="text-muted">Почему:</span> ${why}</div>` : ``}
          ${expected ? `<div class="small mt-1"><span class="text-muted">Эффект:</span> ${expected}</div>` : ``}
          ${risk ? `<div class="small mt-1"><span class="text-muted">Риск:</span> ${risk}</div>` : ``}

          <div class="d-flex gap-2 mt-2">
            <button class="btn btn-sm btn-primary" type="button" data-ai-act="execute" data-ai-idx="${idx}">
              Выполнить
            </button>
            <button class="btn btn-sm btn-outline-secondary" type="button" data-ai-act="dismiss" data-ai-idx="${idx}">
              Скрыть
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  function inferRequest() {
    const page = String(window.__ADMIN_PAGE__ || "");
    const phone = normalizePhone(window.__CLIENT_PHONE__ || "");

    if (page === "client" && phone) {
      currentContext = "client";
      currentPhone = phone;
      return {
        kind: "ask",
        payload: {
          context: "client",
          phone,
          question:
            "Дай персональные инсайты и рекомендации по этому клиенту. Укажи следующий лучший шаг (Next Best Action). " +
            "Пожалуйста, заполняй target как nav:/admin/...."
        }
      };
    }

    currentContext = "business";
    currentPhone = null;
    return { kind: "overview" };
  }

  async function load() {
    setLoading();
    btn.disabled = true;

    try {
      const req = inferRequest();
      const data =
        req.kind === "ask"
          ? await apiPost("/api/ai/ask", req.payload)
          : await apiGet("/api/ai/overview");

      setBadge(data?.mode || "—");
      renderInsights(data?.insights);
      renderRecos(data?.recommendations);

      if (typeof uiToast === "function") {
        const mode = data?.mode ? String(data.mode) : "ai";
        uiToast(`AI обновлён (${mode})`, "info");
      }
    } catch (e) {
      setBadge("error");
      showError(`AI ошибка: ${e.message}`);
      ulInsights.innerHTML = `<li class="text-muted">—</li>`;
      boxRecos.innerHTML = `<div class="text-muted small">—</div>`;
      if (typeof uiToast === "function") uiToast("AI ошибка", "error");
    } finally {
      btn.disabled = false;
    }
  }

  window.__AI_OVERVIEW_RELOAD__ = load;

  // click delegation for recos
  boxRecos.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-ai-act]");
    if (!b) return;

    const act = b.getAttribute("data-ai-act");
    const idx = Number(b.getAttribute("data-ai-idx") || "-1");
    if (!Number.isFinite(idx) || idx < 0 || idx >= currentRecos.length) return;

    const r = currentRecos[idx];
    const key = aiRecoKey(currentContext, currentPhone, r);

    if (act === "dismiss") {
      aiDismiss(key);
      renderRecos(currentRecos);
      if (typeof uiToast === "function") uiToast("Рекомендация скрыта", "info");
      return;
    }

    if (act === "execute") {
      if (typeof uiToast === "function") uiToast("Выполняю…", "info");
      aiExecuteReco(currentContext, currentPhone, r);
    }
  });

  btn.addEventListener("click", load);
  load();
}

// =========================
// Page: Desktop (/admin)
// =========================
function initDesktopPage() {
  const elNewClients = document.getElementById("dashNewClients");
  const elActiveCampaigns = document.getElementById("dashActiveCampaigns");
  const elCampaignList = document.getElementById("dashCampaignList");

  const elKpiRevenue7 = document.getElementById("dashKpiRevenue7");
  const elKpiRevenue30 = document.getElementById("dashKpiRevenue30");
  const elKpiTx30 = document.getElementById("dashKpiTx30");
  const elKpiAvg30 = document.getElementById("dashKpiAvg30");

  const elAlerts = document.getElementById("dashAlertsList");
  const elSegments = document.getElementById("dashSegmentsList");
  const elUpdatedAt = document.getElementById("dashUpdatedAt");
  const reloadBtn = document.getElementById("dashReloadBtn");

  // today + recent
  const elTodayRevenue = document.getElementById("dashTodayRevenue");
  const elTodayTx = document.getElementById("dashTodayTx");
  const elTodayAvg = document.getElementById("dashTodayAvg");
  const elRecentTx = document.getElementById("dashRecentTxList");

  const any =
    elNewClients || elActiveCampaigns || elCampaignList || elKpiRevenue7 || elAlerts || elSegments || elUpdatedAt ||
    elTodayRevenue || elRecentTx;
  if (!any) return;

  function pickWindow(windows, days) {
    const list = Array.isArray(windows) ? windows : [];
    const d = Number(days);
    return (
      list.find((w) => Number(w?.days) === d) ||
      list.find((w) => String(w?.label || "").includes(String(d))) ||
      null
    );
  }

  function renderCampaigns(list) {
    const arr = Array.isArray(list) ? list : [];
    if (!arr.length) {
      if (elCampaignList) elCampaignList.innerHTML = `<div class="text-muted small">Кампаний пока нет</div>`;
      if (elActiveCampaigns) elActiveCampaigns.textContent = "0";
      return;
    }

    const active = arr.filter((c) => {
      const st = String(c?.status || "draft");
      return st === "draft" || st === "ready";
    });

    if (elActiveCampaigns) elActiveCampaigns.textContent = fmt0(active.length);

    const sorted = [...arr].sort((a, b) => {
      const ida = safeNum(a?.id ?? 0, 0);
      const idb = safeNum(b?.id ?? 0, 0);
      return idb - ida;
    });

    const top = sorted.slice(0, 4);
    if (!elCampaignList) return;

    elCampaignList.innerHTML = top
      .map((c) => {
        const id = c?.id ?? "—";
        const name = c?.name ? String(c.name) : `Кампания #${id}`;
        const st = String(c?.status || "draft");
        const seg = c?.segment_key ? String(c.segment_key) : "—";
        return `
          <a class="dash-item" href="/admin/campaigns/${id}">
            <i class="bi bi-megaphone"></i>
            <div class="flex-grow-1">
              <div class="fw-semibold">${name}</div>
              <div class="meta">Сегмент: ${seg} · Статус: ${st}</div>
            </div>
            <i class="bi bi-chevron-right ms-auto"></i>
          </a>
        `;
      })
      .join("");
  }

  function renderAlerts(alerts) {
    const list = Array.isArray(alerts) ? alerts : [];
    if (!elAlerts) return;

    if (!list.length) {
      elAlerts.innerHTML = `<div class="text-muted small">Алертов нет</div>`;
      return;
    }

    elAlerts.innerHTML = list.slice(0, 6).map((a) => {
      const title = a?.title ? String(a.title) : "Алерт";
      const hint = a?.hint ? String(a.hint) : "";
      const cnt = fmt0(a?.count ?? 0);
      const href = a?.href ? String(a.href) : "/admin/analytics";
      const level = String(a?.level || "info");

      const badge =
        level === "danger"
          ? "text-bg-danger"
          : level === "warning"
          ? "text-bg-warning text-dark"
          : "text-bg-secondary";

      return `
        <a class="dash-item" href="${href}">
          <i class="bi bi-bell"></i>
          <div class="flex-grow-1">
            <div class="fw-semibold">${title}</div>
            ${hint ? `<div class="meta">${hint}</div>` : ``}
          </div>
          <span class="badge ${badge}">${cnt}</span>
        </a>
      `;
    }).join("");
  }

  function renderSegments(segments) {
    const list = Array.isArray(segments) ? segments : [];
    if (!elSegments) return;

    if (!list.length) {
      elSegments.innerHTML = `<div class="text-muted small">Сегментов нет</div>`;
      return;
    }

    elSegments.innerHTML = list.slice(0, 6).map((s) => {
      const key = s?.key ? String(s.key) : "";
      const title = s?.title ? String(s.title) : "Сегмент";
      const cnt = fmt0(s?.clients ?? 0);
      const hint = s?.hint ? String(s.hint) : "";
      const href = key ? `/admin/analytics/segment/${encodeURIComponent(key)}` : "/admin/analytics";

      return `
        <a class="dash-item" href="${href}">
          <i class="bi bi-people"></i>
          <div class="flex-grow-1">
            <div class="fw-semibold">${title}</div>
            ${hint ? `<div class="meta">${hint}</div>` : ``}
          </div>
          <span class="badge text-bg-secondary">${cnt}</span>
        </a>
      `;
    }).join("");
  }

  function renderRecentTx(list) {
    if (!elRecentTx) return;
    const arr = Array.isArray(list) ? list : [];
    if (!arr.length) {
      elRecentTx.innerHTML = `<div class="text-muted small">Транзакций пока нет</div>`;
      return;
    }

    const top = arr.slice(0, 6);
    elRecentTx.innerHTML = top.map((t) => {
      const phone = String(t?.user_phone || "—");
      const paid = safeNum(t?.paid_amount ?? t?.amount ?? 0, 0);
      const created = t?.created_at ? fmtDate(t.created_at) : "—";
      const redeem = fmt0(getRedeem(t));
      const earned = fmt0(getEarned(t));
      return `
        <a class="dash-item" href="/admin/client/${encodeURIComponent(phone)}">
          <i class="bi bi-receipt"></i>
          <div class="flex-grow-1">
            <div class="fw-semibold">${fmtMoney(paid)} ₸ · ${phone}</div>
            <div class="meta">${created} · списано ${redeem} · начислено ${earned}</div>
          </div>
          <i class="bi bi-chevron-right ms-auto"></i>
        </a>
      `;
    }).join("");
  }

  function computeToday(txList) {
    const today = ymdLocal(new Date());
    let sum = 0;
    let cnt = 0;

    (Array.isArray(txList) ? txList : []).forEach((t) => {
      const dt = t?.created_at ? new Date(t.created_at) : null;
      if (!dt || Number.isNaN(dt.getTime())) return;
      if (ymdLocal(dt) !== today) return;
      const paid = safeNum(t?.paid_amount ?? t?.amount ?? 0, 0);
      sum += paid;
      cnt += 1;
    });

    const avg = cnt > 0 ? sum / cnt : 0;
    return { sum, cnt, avg };
  }

  async function load() {
    if (reloadBtn) reloadBtn.disabled = true;

    try {
      // analytics overview for KPI + alerts + segments
      const an = await apiGet("/api/analytics/overview");

      const win7 = pickWindow(an?.windows, 7);
      const win30 = pickWindow(an?.windows, 30);

      if (elKpiRevenue7) elKpiRevenue7.textContent = fmtMoney(win7?.revenue ?? 0);
      if (elKpiRevenue30) elKpiRevenue30.textContent = fmtMoney(win30?.revenue ?? 0);
      if (elKpiTx30) elKpiTx30.textContent = fmt0(win30?.transactions ?? 0);

      const tx30 = safeNum(win30?.transactions ?? 0, 0);
      const rev30 = safeNum(win30?.revenue ?? 0, 0);
      const avg30 =
        Number.isFinite(Number(win30?.avg_check)) ? safeNum(win30?.avg_check, 0) : (tx30 > 0 ? rev30 / tx30 : 0);
      if (elKpiAvg30) elKpiAvg30.textContent = fmtMoney(avg30);

      // new clients (segment "new" if present)
      const segs = Array.isArray(an?.segments) ? an.segments : [];
      const segNew = segs.find((s) => String(s?.key || "") === "new");
      if (elNewClients) elNewClients.textContent = fmt0(segNew?.clients ?? 0);

      renderAlerts(an?.alerts);
      renderSegments(an?.segments);

      if (elUpdatedAt) elUpdatedAt.textContent = fmtDate(new Date());
    } catch (e) {
      if (elUpdatedAt) elUpdatedAt.textContent = "Ошибка обновления";
      if (elAlerts) elAlerts.innerHTML = `<div class="text-danger small">Ошибка: ${String(e.message || e)}</div>`;
      if (elSegments) elSegments.innerHTML = `<div class="text-danger small">Ошибка: ${String(e.message || e)}</div>`;
    }

    try {
      // campaigns list for right panel
      const cps = await apiGet("/api/campaigns/");
      renderCampaigns(cps);
    } catch (e) {
      if (elCampaignList) elCampaignList.innerHTML = `<div class="text-danger small">Ошибка кампаний: ${String(e.message || e)}</div>`;
      if (elActiveCampaigns) elActiveCampaigns.textContent = "—";
    }

    try {
      // recent transactions + today metrics
      const tx = await apiGet("/api/transactions/?limit=200&offset=0");
      const list = Array.isArray(tx) ? tx : [];

      // render recent
      renderRecentTx(list);

      // compute today
      const today = computeToday(list);
      if (elTodayRevenue) elTodayRevenue.textContent = `${fmtMoney(today.sum)} ₸`;
      if (elTodayTx) elTodayTx.textContent = fmt0(today.cnt);
      if (elTodayAvg) elTodayAvg.textContent = `${fmtMoney(today.avg)} ₸`;
    } catch (e) {
      if (elRecentTx) elRecentTx.innerHTML = `<div class="text-danger small">Ошибка транзакций: ${String(e.message || e)}</div>`;
      if (elTodayRevenue) elTodayRevenue.textContent = "—";
      if (elTodayTx) elTodayTx.textContent = "—";
      if (elTodayAvg) elTodayAvg.textContent = "—";
    }

    if (reloadBtn) reloadBtn.disabled = false;
  }

  reloadBtn?.addEventListener("click", async () => {
    await load();
    if (typeof window.__AI_OVERVIEW_RELOAD__ === "function") window.__AI_OVERVIEW_RELOAD__();
  });

  load();
}

// =========================
// Page: News (/admin/news)
// =========================
function initNewsPage() {
  const feed = document.getElementById("newsFeed");
  const updatedAt = document.getElementById("newsUpdatedAt");
  const reloadBtn = document.getElementById("newsReloadBtn");
  if (!feed) return;

  let currentFilter = "all";

  function setActiveFilter(val) {
    currentFilter = val;
    document.querySelectorAll("[data-news-filter]").forEach((b) => {
      const f = b.getAttribute("data-news-filter");
      b.classList.toggle("active", f === val);
    });
  }

  function item(icon, title, meta, href, kind) {
    const k = kind ? `data-kind="${kind}"` : "";
    const tagOpen = href ? `<a class="dash-item" href="${href}" ${k}>` : `<div class="dash-item" ${k}>`;
    const tagClose = href ? `</a>` : `</div>`;
    return `
      ${tagOpen}
        <i class="bi ${icon}"></i>
        <div class="flex-grow-1">
          <div class="fw-semibold">${title}</div>
          <div class="meta">${meta}</div>
        </div>
        <i class="bi bi-chevron-right ms-auto"></i>
      ${tagClose}
    `;
  }

  function applyFilterHtml(html) {
    // simple: rebuild by filtering rendered nodes
    const wrap = document.createElement("div");
    wrap.innerHTML = html;
    const nodes = [...wrap.querySelectorAll(".dash-item")];

    const filtered = nodes.filter((n) => {
      const k = n.getAttribute("data-kind") || "all";
      if (currentFilter === "all") return true;
      return k === currentFilter;
    });

    if (!filtered.length) {
      feed.innerHTML = `<div class="text-muted small">Нет событий по фильтру</div>`;
      return;
    }
    feed.innerHTML = filtered.map((n) => n.outerHTML).join("");
  }

  async function load() {
    if (reloadBtn) reloadBtn.disabled = true;
    feed.innerHTML = `<div class="text-muted small">Загрузка…</div>`;

    let html = "";

    try {
      const an = await apiGet("/api/analytics/overview");
      const alerts = Array.isArray(an?.alerts) ? an.alerts : [];
      if (alerts.length) {
        html += `<div class="text-muted small mt-1">Алерты</div>`;
        html += alerts.slice(0, 6).map((a) => {
          const title = String(a?.title || "Алерт");
          const meta = String(a?.hint || "");
          const cnt = fmt0(a?.count ?? 0);
          const href = String(a?.href || "/admin/analytics");
          return item("bi-bell", `${title} · ${cnt}`, meta || "—", href, "al");
        }).join("");
      }
    } catch {
      // ignore
    }

    try {
      const cps = await apiGet("/api/campaigns/");
      const list = Array.isArray(cps) ? cps : [];
      html += `<div class="text-muted small mt-3">Кампании</div>`;
      if (!list.length) {
        html += `<div class="text-muted small">Кампаний пока нет</div>`;
      } else {
        const top = [...list].sort((a,b)=>safeNum(b?.id,0)-safeNum(a?.id,0)).slice(0, 6);
        html += top.map((c) => {
          const id = c?.id ?? "—";
          const name = String(c?.name || `Кампания #${id}`);
          const seg = String(c?.segment_key || "—");
          const st = String(c?.status || "draft");
          return item("bi-megaphone", name, `Сегмент: ${seg} · Статус: ${st}`, `/admin/campaigns/${id}`, "cp");
        }).join("");
      }
    } catch {
      // ignore
    }

    try {
      const tx = await apiGet("/api/transactions/?limit=30&offset=0");
      const list = Array.isArray(tx) ? tx : [];
      html += `<div class="text-muted small mt-3">Транзакции</div>`;
      if (!list.length) {
        html += `<div class="text-muted small">Транзакций пока нет</div>`;
      } else {
        html += list.slice(0, 10).map((t) => {
          const phone = String(t?.user_phone || "—");
          const paid = safeNum(t?.paid_amount ?? t?.amount ?? 0, 0);
          const dt = t?.created_at ? fmtDate(t.created_at) : "—";
          return item("bi-receipt", `${fmtMoney(paid)} ₸ · ${phone}`, dt, `/admin/client/${encodeURIComponent(phone)}`, "tx");
        }).join("");
      }
    } catch {
      // ignore
    }

    if (!html.trim()) html = `<div class="text-muted small">Нет данных</div>`;
    if (updatedAt) updatedAt.textContent = fmtDate(new Date());

    applyFilterHtml(html);
    if (reloadBtn) reloadBtn.disabled = false;
  }

  document.querySelectorAll("[data-news-filter]").forEach((b) => {
    b.addEventListener("click", () => {
      setActiveFilter(b.getAttribute("data-news-filter") || "all");
      // rerender by re-loading to keep simple and consistent
      load();
    });
  });

  reloadBtn?.addEventListener("click", load);

  setActiveFilter("all");
  load();
}

// =========================
// Page: Analytics (/admin/analytics)
// =========================
function initAnalyticsPage() {
  const reloadBtn = document.getElementById("anReloadBtn");
  const msgEl = document.getElementById("anMsg");
  const tbody = document.getElementById("anWindowsTbody");
  const segBox = document.getElementById("anSegmentsBox");
  const alertsBox = document.getElementById("anAlertsBox");

  if (!tbody || !segBox) return;

  function setMsg(text) {
    if (!msgEl) return;
    msgEl.textContent = text || "";
  }

  function setLoading() {
    if (alertsBox) alertsBox.innerHTML = `<div class="text-muted">Загрузка…</div>`;
    tbody.innerHTML = `<tr><td colspan="5" class="text-muted">Загрузка…</td></tr>`;
    segBox.innerHTML = `<div class="text-muted">Загрузка…</div>`;
    setMsg("");
  }

  function renderAlerts(alerts) {
    if (!alertsBox) return;
    const list = Array.isArray(alerts) ? alerts : [];
    if (!list.length) {
      alertsBox.innerHTML = `<div class="text-muted">Алертов нет</div>`;
      return;
    }

    function badge(level) {
      if (level === "danger") return "text-bg-danger";
      if (level === "warning") return "text-bg-warning text-dark";
      return "text-bg-secondary";
    }

    alertsBox.innerHTML = list.map((a) => {
      const title = a?.title || "Алерт";
      const level = String(a?.level || "info");
      const cnt = safeNum(a?.count ?? 0, 0);
      const hint = a?.hint || "";
      const href = a?.href || "#";

      return `
        <a class="border rounded p-2 d-flex align-items-center justify-content-between text-decoration-none"
           href="${href}">
          <div>
            <div class="fw-semibold text-body">${String(title)}</div>
            ${hint ? `<div class="text-muted small">${String(hint)}</div>` : ``}
          </div>
          <div class="badge ${badge(level)}">${fmt0(cnt)}</div>
        </a>
      `;
    }).join("");
  }

  function renderWindows(windows) {
    const list = Array.isArray(windows) ? windows : [];
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-muted">Нет данных</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map((w) => {
      const label = w?.label || (Number.isFinite(Number(w?.days)) ? `${Math.trunc(Number(w.days))} дней` : "—");
      const revenue = safeNum(w?.revenue ?? 0, 0);
      const tx = safeNum(w?.transactions ?? 0, 0);
      const clients = safeNum(w?.clients ?? 0, 0);
      const avg = Number.isFinite(Number(w?.avg_check)) ? safeNum(w.avg_check, 0) : (tx > 0 ? (revenue / tx) : 0);

      return `
        <tr>
          <td>${String(label)}</td>
          <td class="text-end">${fmtMoney(revenue)}</td>
          <td class="text-end">${fmt0(tx)}</td>
          <td class="text-end">${fmt0(clients)}</td>
          <td class="text-end">${fmtMoney(avg)}</td>
        </tr>
      `;
    }).join("");
  }

  function renderSegments(segments) {
    const list = Array.isArray(segments) ? segments : [];
    if (!list.length) {
      segBox.innerHTML = `<div class="text-muted">Сегментов пока нет</div>`;
      return;
    }

    segBox.innerHTML = list.map((s) => {
      const key = s?.key || "";
      const title = s?.title || "Сегмент";
      const cnt = safeNum(s?.clients ?? 0, 0);
      const hint = s?.hint || "";

      return `
        <a class="border rounded p-2 d-flex align-items-center justify-content-between text-decoration-none"
           href="/admin/analytics/segment/${encodeURIComponent(key)}">
          <div>
            <div class="fw-semibold text-body">${String(title)}</div>
            ${hint ? `<div class="text-muted small">${String(hint)}</div>` : ``}
          </div>
          <div class="badge text-bg-secondary">${fmt0(cnt)}</div>
        </a>
      `;
    }).join("");
  }

  async function load() {
    setLoading();
    if (reloadBtn) reloadBtn.disabled = true;

    try {
      const data = await apiGet("/api/analytics/overview");
      renderAlerts(data?.alerts);
      renderWindows(data?.windows);
      renderSegments(data?.segments);

      setMsg(`Обновлено: ${fmtDate(new Date())}`);
      if (typeof uiToast === "function") uiToast("Аналитика обновлена", "info");
    } catch (e) {
      if (alertsBox) alertsBox.innerHTML = `<div class="text-danger">Ошибка алертов: ${String(e.message || e)}</div>`;
      tbody.innerHTML = `<tr><td colspan="5" class="text-danger">Ошибка: ${String(e.message || e)}</td></tr>`;
      segBox.innerHTML = `<div class="text-danger">Ошибка сегментов: ${String(e.message || e)}</div>`;
      setMsg("");
      if (typeof uiToast === "function") uiToast("Ошибка аналитики", "error");
    } finally {
      if (reloadBtn) reloadBtn.disabled = false;
    }
  }

  reloadBtn?.addEventListener("click", async () => {
    await load();
    if (typeof window.__AI_OVERVIEW_RELOAD__ === "function") window.__AI_OVERVIEW_RELOAD__();
  });

  load();
}

// =========================
// Page: Campaigns (/admin/campaigns)
// =========================
function initCampaignsPage() {
  const tbody = document.getElementById("cpTbody");
  if (!tbody) return;

  const msgEl = document.getElementById("cpMsg");

  const openBtn = document.getElementById("cpOpenCreateBtn");
  const closeBtn = document.getElementById("cpCloseCreateBtn");
  const box = document.getElementById("cpCreateBox");
  const errEl = document.getElementById("cpCreateErr");

  const fName = document.getElementById("cpName");
  const fSeg = document.getElementById("cpSegment");
  const fR = document.getElementById("cpR");
  const fF = document.getElementById("cpF");
  const fM = document.getElementById("cpM");
  const fBonus = document.getElementById("cpBonus");
  const fQ = document.getElementById("cpQ");
  const fSort = document.getElementById("cpSort");
  const fNote = document.getElementById("cpNote");
  const createBtn = document.getElementById("cpCreateBtn");

  function setMsg(text) {
    if (!msgEl) return;
    msgEl.textContent = text || "";
  }

  function showErr(text) {
    if (!errEl) return;
    errEl.textContent = text || "Ошибка";
    errEl.classList.remove("d-none");
  }

  function hideErr() {
    if (!errEl) return;
    errEl.classList.add("d-none");
  }

  function badgeStatus(s) {
    const st = String(s || "draft");
    if (st === "ready") return "text-bg-success";
    if (st === "sent") return "text-bg-secondary";
    return "text-bg-warning text-dark";
  }

  function row(c) {
    const id = c?.id ?? "—";
    const name = c?.name || "—";
    const seg = c?.segment_key || "—";
    const bonus = safeNum(c?.suggested_bonus ?? 0, 0);
    const st = c?.status || "draft";
    const total = safeNum(c?.recipients_total ?? 0, 0);
    const created = fmtDate(c?.created_at);

    return `
      <tr>
        <td>${id}</td>
        <td>${String(name)}</td>
        <td><span class="badge text-bg-secondary">${String(seg)}</span></td>
        <td class="text-end">${fmtMoney(bonus)}</td>
        <td><span class="badge ${badgeStatus(st)}">${String(st)}</span></td>
        <td class="text-end">${fmt0(total)}</td>
        <td class="text-muted">${created}</td>
        <td class="text-end">
          <a class="btn btn-sm btn-outline-primary" href="/admin/campaigns/${id}">Открыть</a>
        </td>
      </tr>
    `;
  }

  async function load() {
    try {
      const data = await apiGet("/api/campaigns/");
      const list = Array.isArray(data) ? data : [];
      if (!list.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-muted">Кампаний пока нет</td></tr>`;
        return;
      }
      tbody.innerHTML = list.map(row).join("");
      setMsg(`Кампаний: ${fmt0(list.length)}`);
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-danger">Ошибка: ${String(e.message || e)}</td></tr>`;
    }
  }

  function openCreate() {
    hideErr();
    box?.classList.remove("d-none");
  }
  function closeCreate() {
    hideErr();
    box?.classList.add("d-none");
  }

  // ✅ prefill from query params (для AI "Выполнить")
  function tryPrefillFromQuery() {
    const name = getQueryParam("name");
    const segment_key = getQueryParam("segment_key") || getQueryParam("segment");
    const bonus = getQueryParam("bonus");

    if (!name && !segment_key && !bonus) return;

    openCreate();
    if (fName && name) fName.value = String(name);
    if (fSeg && segment_key) fSeg.value = String(segment_key);
    if (fBonus && bonus !== null && bonus !== undefined && bonus !== "") fBonus.value = String(Math.trunc(safeNum(bonus, 0)));

    // очистим URL (чтобы не повторялось при refresh)
    try {
      const u = new URL(window.location.href);
      u.searchParams.delete("name");
      u.searchParams.delete("segment");
      u.searchParams.delete("segment_key");
      u.searchParams.delete("bonus");
      window.history.replaceState({}, "", u.pathname + (u.searchParams.toString() ? "?" + u.searchParams.toString() : ""));
    } catch {
      // ignore
    }
  }

  openBtn?.addEventListener("click", openCreate);
  closeBtn?.addEventListener("click", closeCreate);

  createBtn?.addEventListener("click", async () => {
    hideErr();

    const name = String(fName?.value || "").trim();
    const segment_key = String(fSeg?.value || "").trim();
    if (!name) return showErr("Укажи название кампании");
    if (!segment_key) return showErr("Укажи сегмент");

    const payload = {
      name,
      segment_key,
      r_min: fR?.value ? Number(fR.value) : null,
      f_min: fF?.value ? Number(fF.value) : null,
      m_min: fM?.value ? Number(fM.value) : null,
      q: (fQ?.value || "").trim() || null,
      sort: (fSort?.value || "").trim() || null,
      suggested_bonus: Math.trunc(safeNum(fBonus?.value, 0)),
      note: (fNote?.value || "").trim() || null,
    };

    try {
      createBtn.disabled = true;
      const created = await apiPost("/api/campaigns/", payload);
      if (typeof uiToast === "function") uiToast("Кампания создана", "success");

      if (fName) fName.value = "";
      if (fBonus) fBonus.value = "0";
      if (fQ) fQ.value = "";
      if (fNote) fNote.value = "";
      if (fR) fR.value = "";
      if (fF) fF.value = "";
      if (fM) fM.value = "";

      closeCreate();
      await load();

      if (created?.id) window.location.href = `/admin/campaigns/${created.id}`;
    } catch (e) {
      showErr(String(e.message || e));
      if (typeof uiToast === "function") uiToast("Ошибка создания кампании", "error");
    } finally {
      createBtn.disabled = false;
    }
  });

  load();
  tryPrefillFromQuery();
}

// =========================
// Page: Campaign detail (/admin/campaigns/{id})
// =========================
function initCampaignDetailPage() {
  const id = Number(window.__CAMPAIGN_ID__ || 0);
  if (!id) return;

  const titleEl = document.getElementById("cdTitle");
  const metaEl = document.getElementById("cdMeta");
  const msgEl = document.getElementById("cdMsg");
  const errEl = document.getElementById("cdErr");
  const tbody = document.getElementById("cdTbody");

  const reloadBtn = document.getElementById("cdReloadBtn");
  const buildBtn = document.getElementById("cdBuildBtn");

  if (!tbody) return;

  function setMsg(text) {
    if (!msgEl) return;
    msgEl.textContent = text || "";
  }

  function showErr(text) {
    if (!errEl) return;
    errEl.textContent = text || "Ошибка";
    errEl.classList.remove("d-none");
  }
  function hideErr() {
    if (!errEl) return;
    errEl.classList.add("d-none");
  }

  function row(r) {
    const phone = String(r?.phone || "—");
    const name = r?.full_name ? String(r.full_name) : "—";
    const tier = String(r?.tier || "Bronze");

    const p90 = safeNum(r?.purchases_90d ?? 0, 0);
    const rev90 = safeNum(r?.revenue_90d ?? 0, 0);

    const last = r?.last_purchase_at ? fmtDate(r.last_purchase_at) : "—";
    const rec = Number.isFinite(Number(r?.recency_days)) ? fmt0(r.recency_days) : "—";
    const rfm = String(r?.rfm || "111");
    const rCls = tierBadgeClass(tier);

    return `
      <tr>
        <td>${phone}</td>
        <td>${name}</td>
        <td><span class="badge ${rCls}">${tierRu(tier)}</span></td>
        <td class="text-end">${fmt0(p90)}</td>
        <td class="text-end">${fmtMoney(rev90)}</td>
        <td>${last}</td>
        <td class="text-end">${rec === "99999" ? "—" : rec}</td>
        <td class="text-end"><span class="badge text-bg-secondary">${rfm}</span></td>
        <td class="text-end"><a class="btn btn-sm btn-outline-secondary" href="/admin/client/${phone}">Карточка</a></td>
      </tr>
    `;
  }

  async function load() {
    hideErr();
    tbody.innerHTML = `<tr><td colspan="9" class="text-muted">Загрузка…</td></tr>`;

    try {
      const data = await apiGet(`/api/campaigns/${id}`);
      const c = data?.campaign;

      if (titleEl) titleEl.textContent = c?.name || `Кампания #${id}`;
      if (metaEl) {
        const seg = c?.segment_key || "—";
        const st = c?.status || "draft";
        const bonus = fmtMoney(c?.suggested_bonus ?? 0);
        const total = fmt0(data?.recipients_total ?? 0);
        metaEl.textContent = `Сегмент: ${seg} · Статус: ${st} · Бонус: ${bonus} · Клиентов: ${total}`;
      }

      const preview = Array.isArray(data?.recipients_preview) ? data.recipients_preview : [];
      if (!preview.length) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-muted">Список клиентов не собран. Нажми “Собрать список клиентов”.</td></tr>`;
      } else {
        tbody.innerHTML = preview.map(row).join("");
      }

      setMsg(`Обновлено: ${fmtDate(new Date())}`);
    } catch (e) {
      showErr(String(e.message || e));
      tbody.innerHTML = `<tr><td colspan="9" class="text-danger">Ошибка</td></tr>`;
      setMsg("");
    }
  }

  async function build() {
    hideErr();
    try {
      buildBtn.disabled = true;
      setMsg("Сбор клиентов…");
      await apiPost(`/api/campaigns/${id}/build`, {});
      if (typeof uiToast === "function") uiToast("Список клиентов собран", "success");
      await load();
    } catch (e) {
      showErr(String(e.message || e));
      if (typeof uiToast === "function") uiToast("Ошибка сборки списка", "error");
    } finally {
      buildBtn.disabled = false;
    }
  }

  reloadBtn?.addEventListener("click", load);
  buildBtn?.addEventListener("click", build);

  load();
}

// =========================
// Page: Clients list (/admin/clients)
// =========================
function initClientsList() {
  const btnSearch = document.getElementById("btnSearch");
  const btnRefresh = document.getElementById("btnRefresh");
  const btnRefreshTop = document.getElementById("btnRefreshTop");
  const searchPhone = document.getElementById("searchPhone");
  const usersTableBody = document.getElementById("usersTableBody");
  const usersError = document.getElementById("usersError");
  const searchError = document.getElementById("searchError");

  if (!usersTableBody) return;

  async function loadUsers() {
    try {
      hide(usersError);
      const data = await apiGet("/api/users/");
      const items = Array.isArray(data) ? data : [];

      usersTableBody.innerHTML = items
        .map((u) => {
          const t = u.tier || "Bronze";
          return `
            <tr>
              <td>${u.id}</td>
              <td>${u.phone}</td>
              <td>${u.full_name || "—"}</td>
              <td><span class="badge ${tierBadgeClass(t)}">${tierRu(t)}</span></td>
              <td class="text-end">
                <a href="/admin/client/${u.phone}" class="btn btn-sm btn-outline-primary">
                  <i class="bi bi-arrow-right"></i>
                </a>
              </td>
            </tr>
          `;
        })
        .join("");

      if (typeof uiToast === "function") uiToast("Клиенты обновлены", "info");
    } catch (e) {
      show(usersError, `Ошибка: ${e.message}`, true);
      usersTableBody.innerHTML = `<tr><td colspan="5" class="text-muted">Ошибка загрузки</td></tr>`;
    }
  }

  if (btnSearch) {
    btnSearch.addEventListener("click", () => {
      hide(searchError);
      const phone = normalizePhone((searchPhone?.value || "").trim());
      if (!phone) {
        show(searchError, "Введите номер телефона", true);
        return;
      }
      window.location.href = `/admin/client/${phone}`;
    });

    searchPhone?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") btnSearch.click();
    });
  }

  [btnRefresh, btnRefreshTop].forEach((b) => b?.addEventListener("click", loadUsers));
  loadUsers();
}

// =========================
// Page: Client card (/admin/client/{phone})
// =========================
function initClientCard() {
  const phoneRaw = window.__CLIENT_PHONE__ || "";
  const phone = normalizePhone(phoneRaw);
  if (!phone) return;

  const btnReload = document.getElementById("btnReload");
  const btnCreateTx = document.getElementById("btnCreateTx");

  const clientError = document.getElementById("clientError");
  const clientNotFound = document.getElementById("clientNotFound");
  const birthdayBanner = document.getElementById("birthdayBanner");

  // Metrics
  const mFullName = document.getElementById("mFullName");
  const mTier = document.getElementById("mTier");
  const mTotalSpent = document.getElementById("mTotalSpent");
  const mCount = document.getElementById("mCount");
  const mAvg = document.getElementById("mAvg");
  const mBonus = document.getElementById("mBonus");

  // Tx table
  const txTableBody = document.getElementById("txTableBody");
  const txError = document.getElementById("txError");
  const txMsg = document.getElementById("txMsg");

  // Form fields
  const fAmount = document.getElementById("fAmount");
  const fPaid = document.getElementById("fPaid");
  const fRedeem = document.getElementById("fRedeem");
  const fMethod = document.getElementById("fMethod");
  const fName = document.getElementById("fName");
  const fBirth = document.getElementById("fBirth");
  const fTier = document.getElementById("fTier");
  const fComment = document.getElementById("fComment");

  function resetMetrics() {
    if (mFullName) mFullName.textContent = "—";
    if (mTier) {
      mTier.textContent = "—";
      mTier.className = "badge text-bg-secondary";
    }
    if (mTotalSpent) mTotalSpent.textContent = "0";
    if (mCount) mCount.textContent = "0";
    if (mAvg) mAvg.textContent = "0";
    if (mBonus) mBonus.textContent = "0";
  }

  async function loadMetrics() {
    try {
      hide(clientError);
      clientNotFound?.classList.add("d-none");
      birthdayBanner?.classList.add("d-none");

      const data = await apiGet(`/api/crm/client/${phone}`);

      if (mFullName) mFullName.textContent = data.full_name || "—";

      const tier = data.tier || "Bronze";
      if (mTier) {
        mTier.textContent = tierRu(tier);
        mTier.className = `badge ${tierBadgeClass(tier)}`;
      }

      if (mTotalSpent) mTotalSpent.textContent = fmtMoney(data.total_spent);
      if (mCount) mCount.textContent = fmt0(data.purchases_count);
      if (mAvg) mAvg.textContent = fmtMoney(data.avg_check);
      if (mBonus) mBonus.textContent = fmt0(data.bonus_balance);
    } catch (e) {
      resetMetrics();
      const msg = String(e.message || "");
      if (msg.toLowerCase().includes("client not found") || msg.includes("404")) {
        clientNotFound?.classList.remove("d-none");
        return;
      }
      show(clientError, `Ошибка CRM: ${e.message}`, true);
      clientError?.classList.remove("d-none");
    }
  }

  async function loadTransactions() {
    if (!txTableBody) return;
    try {
      hide(txError);
      const rows = await apiGet(`/api/transactions/by-phone/${phone}`);
      const list = Array.isArray(rows) ? rows : [];

      if (!list.length) {
        txTableBody.innerHTML = `<tr><td colspan="6" class="text-muted">Транзакций пока нет</td></tr>`;
        return;
      }

      txTableBody.innerHTML = list
        .map(
          (t) => `
          <tr>
            <td>${t.id ?? "—"}</td>
            <td>${fmtDate(t.created_at)}</td>
            <td class="text-end">${fmtMoney(t.amount)}</td>
            <td class="text-end">${fmtMoney(t.paid_amount ?? t.amount)}</td>
            <td class="text-end">${fmt0(getRedeem(t))}</td>
            <td class="text-end">${fmt0(getEarned(t))}</td>
          </tr>
        `
        )
        .join("");
    } catch (e) {
      show(txError, `Ошибка загрузки транзакций: ${e.message}`, true);
      txError?.classList.remove("d-none");
      txTableBody.innerHTML = `<tr><td colspan="6" class="text-muted">Ошибка</td></tr>`;
    }
  }

  async function reloadAll() {
    await loadMetrics();
    await loadTransactions();
  }

  btnReload?.addEventListener("click", reloadAll);

  btnCreateTx?.addEventListener("click", async () => {
    hide(txMsg);

    const amount = Math.trunc(safeNum(fAmount?.value, 0));
    if (!amount || amount <= 0) {
      show(txMsg, "Введите сумму > 0", true);
      txMsg?.classList.remove("d-none");
      return;
    }

    const paid = fPaid?.value ? Math.trunc(safeNum(fPaid.value, 0)) : null;
    const redeem = Math.trunc(safeNum(fRedeem?.value, 0));

    const payload = {
      user_phone: phone,
      amount,
      paid_amount: paid && paid > 0 ? paid : null,
      redeem_points: redeem >= 0 ? redeem : 0,
      payment_method: fMethod?.value || "CASH",
      full_name: (fName?.value || "").trim() || null,
      birth_date: (fBirth?.value || "").trim() || null,
      tier: (fTier?.value || "").trim() || null,
      comment: (fComment?.value || "").trim() || "",
    };

    try {
      btnCreateTx.disabled = true;
      const res = await apiPost("/api/transactions/", payload);

      show(txMsg, `✓ Транзакция создана (ID: ${res.id || "—"})`, false);
      txMsg?.classList.remove("d-none");
      if (typeof uiToast === "function") uiToast("Транзакция проведена", "success");

      if (fPaid) fPaid.value = "";
      if (fRedeem) fRedeem.value = "0";
      if (fName) fName.value = "";
      if (fBirth) fBirth.value = "";
      if (fTier) fTier.value = "";
      if (fComment) fComment.value = "";

      setTimeout(reloadAll, 250);
    } catch (e) {
      show(txMsg, `✗ ${e.message}`, true);
      txMsg?.classList.remove("d-none");
      if (typeof uiToast === "function") uiToast("Ошибка создания транзакции", "error");
    } finally {
      btnCreateTx.disabled = false;
    }
  });

  reloadAll();
}

// =========================
// Page: Transactions (/admin/transactions)
// =========================
function initTransactionsPage() {
  const tbody = document.getElementById("txTbody");
  if (!tbody) return;

  const count = document.getElementById("txCount");
  const phoneEl = document.getElementById("txPhone");
  const searchBtn = document.getElementById("txSearchBtn");
  const refreshBtn = document.getElementById("txRefreshBtn");

  function setCount(n) {
    if (count) count.textContent = String(n ?? "—");
  }

  function renderRows(list) {
    const arr = Array.isArray(list) ? list : [];
    setCount(arr.length);

    if (!arr.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-muted">Транзакции не найдены.</td></tr>`;
      return;
    }

    tbody.innerHTML = arr
      .map((t) => {
        const phone = t.user_phone ?? "—";
        return `
          <tr>
            <td>${t.id ?? "—"}</td>
            <td class="text-muted">${fmtDate(t.created_at)}</td>
            <td>${phone}</td>
            <td class="text-end">${fmtMoney(t.amount)}</td>
            <td class="text-end">${fmtMoney(t.paid_amount ?? t.amount)}</td>
            <td class="text-end">${fmtMoney(getRedeem(t))}</td>
            <td class="text-end">${fmtMoney(getEarned(t))}</td>
            <td class="text-muted">${(t.comment ?? "").toString()}</td>
            <td class="text-end">
              <a class="btn btn-sm btn-outline-secondary" href="/admin/client/${phone}">
                Карточка
              </a>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  async function loadByPhone(phone) {
    const data = await apiGet(`/api/transactions/by-phone/${phone}`);
    renderRows(data);
  }

  async function onSearch() {
    const phone = normalizePhone(phoneEl?.value || "");
    if (!phone) {
      if (typeof uiToast === "function") uiToast("Введите корректный телефон", "warning");
      return;
    }
    try {
      await loadByPhone(phone);
    } catch (e) {
      if (typeof uiToast === "function") uiToast(`Ошибка: ${e.message}`, "error");
      tbody.innerHTML = `<tr><td colspan="9" class="text-danger">Ошибка загрузки транзакций</td></tr>`;
      setCount("—");
    }
  }

  searchBtn?.addEventListener("click", onSearch);
  phoneEl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") onSearch();
  });
  refreshBtn?.addEventListener("click", onSearch);

  // ✅ prefill from query ?phone=
  const qPhone = normalizePhone(getQueryParam("phone") || "");
  if (qPhone && phoneEl) {
    phoneEl.value = qPhone;
    onSearch();
  }
}

// =========================
// Page: Settings (/admin/settings)
// =========================
function initSettingsPage() {
  const msg = document.getElementById("stMsg");
  const reloadBtn = document.getElementById("stReloadBtn");
  const saveBtn = document.getElementById("stSaveBtn");

  if (!reloadBtn || !saveBtn) return;

  const ids = [
    "earn_bronze_percent",
    "earn_silver_percent",
    "earn_gold_percent",
    "redeem_max_percent",
    "activation_days",
    "burn_days",
    "birthday_bonus_amount",
    "birthday_bonus_days_before",
    "birthday_bonus_ttl_days",
  ];

  function showMsg(text, isErr = false) {
    if (!msg) return;
    msg.textContent = text;
    msg.classList.remove("d-none", "text-danger", "text-success");
    msg.classList.add(isErr ? "text-danger" : "text-success");
  }

  function readForm() {
    const out = {};
    ids.forEach((k) => {
      const el = document.getElementById(k);
      out[k] = Math.trunc(safeNum(el?.value, 0));
    });
    return out;
  }

  function fillForm(data) {
    ids.forEach((k) => {
      const el = document.getElementById(k);
      if (el) el.value = data?.[k] ?? "";
    });
  }

  async function load() {
    try {
      const data = await apiGet("/api/settings/");
      fillForm(data);
      if (typeof uiToast === "function") uiToast("Настройки загружены", "info");
    } catch (e) {
      showMsg(`Ошибка загрузки: ${e.message}`, true);
    }
  }

  async function save() {
    try {
      const payload = readForm();
      const data = await fetch("/api/settings/", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      }).then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.detail || `${r.status} ${r.statusText}`);
        return j;
      });

      fillForm(data);
      showMsg("✓ Сохранено. Новые правила применятся к следующим транзакциям.");
      if (typeof uiToast === "function") uiToast("Настройки сохранены", "success");
    } catch (e) {
      showMsg(`Ошибка сохранения: ${e.message}`, true);
      if (typeof uiToast === "function") uiToast("Ошибка сохранения", "error");
    }
  }

  reloadBtn.addEventListener("click", load);
  saveBtn.addEventListener("click", save);

  load();
}

// =========================
// Entry
// =========================
document.addEventListener("DOMContentLoaded", () => {
  initTheme();

  // важно: чтобы работали page-* стили (и твой .page-desktop #aiPanelBtn)
  applyBodyPageClass();

  const page = window.__ADMIN_PAGE__;
  if (page === "desktop") initDesktopPage();
  else if (page === "news") initNewsPage();
  else if (page === "clients" || page === "index") initClientsList();
  else if (page === "client") initClientCard();
  else if (page === "transactions") initTransactionsPage();
  else if (page === "settings") initSettingsPage();
  else if (page === "analytics") initAnalyticsPage();
  else if (page === "campaigns") initCampaignsPage();
  else if (page === "campaign_detail") initCampaignDetailPage();

  initAiOverviewWidget();
  initAiPanel();
});
