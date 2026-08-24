// static/js/whatsapp.js
// Центр WhatsApp-рассылок: аудитория → сообщение → безопасный запуск,
// история с прогрессом, шаблоны, подключение по QR.
// Использует глобальные apiGet/apiPost/apiDelete и uiToast из admin.js.

function initWhatsappPage() {
  if (window.__WA_PAGE_INITED__) return;
  window.__WA_PAGE_INITED__ = true;

  const API = "/api/whatsapp/broadcasts";
  const $ = (id) => document.getElementById(id);

  // ── Состояние ──────────────────────────────────────
  let lastEstimate = null;        // результат /preview
  let allClients = null;          // кэш клиентов для ручного выбора
  const manualSelected = new Map(); // user_id -> {name, phone}
  let historyTimer = null;
  let campaignsCache = [];
  let templatesCache = [];

  // ═══════════════════════════════════════════════════
  // Статус подключения + имя филиала
  // ═══════════════════════════════════════════════════
  async function loadStatus() {
    const badge = $("waStatusBadge");
    if (!badge) return;
    badge.className = "badge text-bg-secondary";
    badge.textContent = "Проверка…";
    try {
      const st = await apiGet("/api/whatsapp/status");
      const ok = !!(st.ok || st.connected);
      badge.className = `badge ${ok ? "text-bg-success" : "text-bg-danger"}`;
      badge.textContent = ok ? "WhatsApp подключён" : "WhatsApp не подключён";
      const logoutBtn = $("waLogoutBtn");
      if (logoutBtn) logoutBtn.classList.toggle("d-none", !ok);
      if (ok && $("waQrBox")) {
        $("waQrBox").innerHTML =
          '<div class="text-success small"><i class="bi bi-check-circle me-1"></i>WhatsApp подключён</div>';
      }
    } catch (e) {
      badge.className = "badge text-bg-danger";
      badge.textContent = "Ошибка статуса";
    }
  }

  async function loadBranchName() {
    try {
      const data = await apiGet("/api/accounts/branches");
      const el = $("waBranchName");
      if (!el) return;
      if (String(data.active_tenant_id) === String(data.home_tenant_id)) {
        el.textContent = data.home_name || "Головной офис";
      } else {
        const b = (data.branches || []).find(x => String(x.id) === String(data.active_tenant_id));
        el.textContent = b ? b.name : "Филиал";
      }
    } catch (_) { /* не owner/admin — оставим по умолчанию */ }
  }

  $("waRefreshStatus")?.addEventListener("click", loadStatus);

  // ═══════════════════════════════════════════════════
  // QR / Logout
  // ═══════════════════════════════════════════════════
  $("waGetQrBtn")?.addEventListener("click", async () => {
    const box = $("waQrBox");
    box.innerHTML = '<div class="text-muted small">Загрузка QR…</div>';
    try {
      const data = await apiGet("/api/whatsapp/qr");
      if (data.qr) {
        box.innerHTML = `<img src="${data.qr}" style="width:220px;height:220px;border-radius:8px;border:1px solid var(--border)">`;
      } else {
        box.innerHTML = '<div class="text-warning small">QR недоступен — возможно, WhatsApp уже подключён.</div>';
        loadStatus();
      }
    } catch (e) {
      box.innerHTML = '<div class="text-danger small">Ошибка получения QR. Проверьте WA-сервис.</div>';
    }
  });

  $("waLogoutBtn")?.addEventListener("click", async () => {
    if (!confirm("Отключить WhatsApp-сессию этого филиала?")) return;
    try {
      await apiPost("/api/whatsapp/logout", {});
      $("waQrBox").innerHTML = '<div class="text-muted small">Сессия отключена. Получите новый QR для подключения.</div>';
      loadStatus();
    } catch (e) {
      uiToast("Ошибка при отключении", "error");
    }
  });

  // ═══════════════════════════════════════════════════
  // Одиночная отправка
  // ═══════════════════════════════════════════════════
  $("waSendBtn")?.addEventListener("click", async () => {
    const phone = ($("waPhone")?.value || "").trim();
    const message = ($("waMessage")?.value || "").trim();
    const errEl = $("waSendErr"), okEl = $("waSendOk");
    errEl?.classList.add("d-none"); okEl?.classList.add("d-none");
    if (!phone || !message) {
      if (errEl) { errEl.textContent = "Укажите телефон и текст"; errEl.classList.remove("d-none"); }
      return;
    }
    const btn = $("waSendBtn"); btn.disabled = true;
    try {
      await apiPost("/api/whatsapp/send", { phone, message });
      if (okEl) { okEl.textContent = "✓ Отправлено"; okEl.classList.remove("d-none"); }
      if ($("waMessage")) $("waMessage").value = "";
    } catch (e) {
      if (errEl) { errEl.textContent = `✗ ${e.message}`; errEl.classList.remove("d-none"); }
    } finally {
      btn.disabled = false;
    }
  });

  // ═══════════════════════════════════════════════════
  // Аудитория
  // ═══════════════════════════════════════════════════
  function audienceKind() {
    return document.querySelector('input[name="bcAudience"]:checked')?.value || "all";
  }

  function collectAudience() {
    const kind = audienceKind();
    const params = {};
    if (kind === "bonus_gt_zero") params.min_bonus = parseInt($("bcMinBonus")?.value || "1", 10) || 1;
    if (kind === "inactive_days") {
      params.days = parseInt($("bcInactiveDays")?.value || "30", 10) || 30;
      const dmax = parseInt($("bcInactiveDaysMax")?.value || "", 10);
      if (dmax > 0) params.days_max = dmax;
    }
    if (kind === "tier") params.tier = $("bcTier")?.value || "Gold";
    if (kind === "segment") params.segment = $("bcSegment")?.value || "risk";
    if (kind === "campaign") params.campaign_id = parseInt($("bcCampaign")?.value || "0", 10) || 0;
    if (kind === "manual") params.user_ids = [...manualSelected.keys()];
    return {
      audience_kind: kind,
      audience_params: params,
      exclude_recent_days: parseInt($("bcExcludeDays")?.value || "7", 10) || 0,
    };
  }

  let countTimer = null;
  function scheduleCount() {
    clearTimeout(countTimer);
    countTimer = setTimeout(runEstimate, 600);
  }

  async function runEstimate() {
    const kind = audienceKind();
    if (kind === "campaign" && !(parseInt($("bcCampaign")?.value || "0", 10))) {
      $("bcCount").textContent = "—";
      return;
    }
    $("bcCount").textContent = "…";
    try {
      lastEstimate = await apiPost(`${API}/preview`, collectAudience());
      $("bcCount").textContent = lastEstimate.count;
      const ex = lastEstimate.excluded || {};
      const parts = [];
      if (ex.opt_out) parts.push(`отписаны: ${ex.opt_out}`);
      if (ex.recent) parts.push(`недавно получали: ${ex.recent}`);
      if (ex.no_phone) parts.push(`без телефона: ${ex.no_phone}`);
      if (ex.duplicate) parts.push(`дубли: ${ex.duplicate}`);
      $("bcExcludedInfo").textContent = parts.length ? `исключено — ${parts.join(", ")}` : "";
      renderWarnings(lastEstimate.warnings || []);
      renderPreview();
      renderSummary();
      bbUpdateTtlHint();
    } catch (e) {
      $("bcCount").textContent = "—";
      $("bcExcludedInfo").textContent = e.message;
    }
  }

  $("bcCountBtn")?.addEventListener("click", runEstimate);
  document.querySelectorAll('input[name="bcAudience"]').forEach(r => {
    r.addEventListener("change", () => {
      $("bcManualBox")?.classList.toggle("d-none", audienceKind() !== "manual");
      if (audienceKind() === "manual" && allClients === null) loadClientsForManual();
      scheduleCount();
    });
  });
  ["bcMinBonus", "bcInactiveDays", "bcInactiveDaysMax", "bcTier", "bcSegment", "bcCampaign", "bcExcludeDays"].forEach(id => {
    $(id)?.addEventListener("change", scheduleCount);
    $(id)?.addEventListener("input", scheduleCount);
  });

  // Пресеты волн для «Давно не были»: заполняют обе границы разом
  document.querySelectorAll("[data-wave]").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const [from, to] = btn.dataset.wave.split(",");
      if ($("bcInactiveDays")) $("bcInactiveDays").value = from;
      if ($("bcInactiveDaysMax")) $("bcInactiveDaysMax").value = to || "";
      const radio = document.querySelector('input[name="bcAudience"][value="inactive_days"]');
      if (radio && !radio.checked) { radio.checked = true; radio.dispatchEvent(new Event("change")); }
      else scheduleCount();
    });
  });

  // ── Ручной выбор клиентов ──────────────────────────
  async function loadClientsForManual() {
    const list = $("bcManualList");
    if (list) list.innerHTML = '<div class="text-muted small p-1">Загрузка базы…</div>';
    try {
      allClients = await apiGet("/api/users/");
      renderManualList("");
    } catch (e) {
      if (list) list.innerHTML = `<div class="text-danger small p-1">${e.message}</div>`;
    }
  }

  function renderManualList(query) {
    const list = $("bcManualList");
    if (!list || allClients === null) return;
    const q = (query || "").toLowerCase().trim();
    const items = allClients
      .filter(u => !q
        || (u.full_name || "").toLowerCase().includes(q)
        || String(u.phone || "").includes(q))
      .slice(0, 60);
    if (!items.length) {
      list.innerHTML = '<div class="text-muted small p-1">Ничего не найдено</div>';
      return;
    }
    list.innerHTML = items.map(u => `
      <label class="wa-manual-item">
        <input type="checkbox" data-uid="${u.id}"
               data-name="${(u.full_name || "").replace(/"/g, "&quot;")}"
               ${manualSelected.has(u.id) ? "checked" : ""}>
        <span class="flex-grow-1">${u.full_name || "Без имени"}
          <span class="text-muted small">· ${u.phone || "—"} · ${u.bonus_balance || 0} бон.</span></span>
      </label>
    `).join("");
    list.querySelectorAll("input[type=checkbox]").forEach(cb => {
      cb.addEventListener("change", () => {
        const uid = parseInt(cb.dataset.uid, 10);
        if (cb.checked) manualSelected.set(uid, { name: cb.dataset.name });
        else manualSelected.delete(uid);
        $("bcManualCount").textContent = manualSelected.size;
        scheduleCount();
      });
    });
  }

  let manualSearchTimer = null;
  $("bcManualSearch")?.addEventListener("input", (e) => {
    clearTimeout(manualSearchTimer);
    manualSearchTimer = setTimeout(() => renderManualList(e.target.value), 250);
  });

  // ═══════════════════════════════════════════════════
  // Сообщение: переменные, шаблоны, предпросмотр, тест
  // ═══════════════════════════════════════════════════
  function insertVar(text) {
    const ta = $("bcMessage");
    if (!ta) return;
    const start = ta.selectionStart ?? ta.value.length;
    const end = ta.selectionEnd ?? ta.value.length;
    ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
    ta.focus();
    ta.selectionStart = ta.selectionEnd = start + text.length;
    onMessageChange();
  }

  document.querySelectorAll("[data-var]").forEach(btn => {
    btn.addEventListener("click", () => insertVar(btn.dataset.var));
  });

  function renderLocal(template, vars) {
    let t = String(template || "");
    const map = {
      "имя": vars.name, "name": vars.name,
      "бонусы": vars.bonus, "бонус": vars.bonus, "bonus": vars.bonus,
      "уровень": vars.tier, "tier": vars.tier,
      "телефон": vars.phone, "phone": vars.phone,
    };
    for (const [k, v] of Object.entries(map)) {
      t = t.split("{" + k + "}").join(String(v ?? ""));
    }
    return t;
  }

  const TIER_RU_MAP = { Bronze: "Бронза", Silver: "Серебро", Gold: "Золото" };

  function renderPreview() {
    const box = $("bcPreviewBox");
    if (!box) return;
    const msg = ($("bcMessage")?.value || "").trim();
    if (!msg) {
      box.innerHTML = '<div class="text-muted small">Напишите текст сообщения</div>';
      return;
    }
    const sample = (lastEstimate?.sample || [])[0];
    const vars = sample
      ? { name: sample.name || "Клиент", bonus: sample.bonus ?? 0, tier: TIER_RU_MAP[sample.tier] || sample.tier || "", phone: sample.phone || "" }
      : { name: "Айгуль", bonus: 3000, tier: "Золото", phone: "77001234567" };
    box.textContent = renderLocal(msg, vars);
  }

  function onMessageChange() {
    const msg = $("bcMessage")?.value || "";
    if ($("bcCharCount")) $("bcCharCount").textContent = msg.length;
    renderPreview();
    renderSummary();
  }
  $("bcMessage")?.addEventListener("input", onMessageChange);

  $("bcTestBtn")?.addEventListener("click", async () => {
    const phone = ($("bcTestPhone")?.value || "").trim();
    const msg = ($("bcMessage")?.value || "").trim();
    if (!phone) { uiToast("Укажите номер для теста", "warning"); return; }
    if (!msg) { uiToast("Напишите текст сообщения", "warning"); return; }
    const btn = $("bcTestBtn"); btn.disabled = true;
    try {
      await apiPost(`${API}/test-send`, { phone, message_template: msg });
      uiToast("Тестовое сообщение отправлено", "success");
    } catch (e) {
      uiToast(`Ошибка теста: ${e.message}`, "error");
    } finally {
      btn.disabled = false;
    }
  });

  // ── Шаблоны ────────────────────────────────────────
  async function loadTemplates() {
    try {
      const data = await apiGet("/api/whatsapp/templates");
      templatesCache = data.templates || [];
      const sel = $("bcTemplateSelect");
      if (sel) {
        sel.innerHTML = '<option value="">Вставить шаблон…</option>' +
          templatesCache.map((t, i) =>
            `<option value="${i}">${t.custom ? "★ " : ""}${t.title}</option>`).join("");
      }
      renderTemplatesTab();
    } catch (_) {}
  }

  $("bcTemplateSelect")?.addEventListener("change", (e) => {
    const idx = e.target.value;
    if (idx === "") return;
    const t = templatesCache[parseInt(idx, 10)];
    if (t && $("bcMessage")) {
      $("bcMessage").value = t.text;
      onMessageChange();
    }
    e.target.value = "";
  });

  $("bcSaveTplBtn")?.addEventListener("click", async () => {
    const text = ($("bcMessage")?.value || "").trim();
    if (!text) { uiToast("Сначала напишите текст", "warning"); return; }
    const title = prompt("Название шаблона:", "Мой шаблон");
    if (!title) return;
    try {
      await apiPost("/api/whatsapp/templates", { title, text });
      uiToast("Шаблон сохранён", "success");
      loadTemplates();
    } catch (e) {
      uiToast(`Ошибка: ${e.message}`, "error");
    }
  });

  function renderTemplatesTab() {
    const box = $("tplList");
    if (!box) return;
    if (!templatesCache.length) {
      box.innerHTML = '<div class="text-muted small">Шаблонов нет</div>';
      return;
    }
    box.innerHTML = templatesCache.map((t, i) => `
      <div class="wa-bc-item">
        <div class="d-flex align-items-center justify-content-between">
          <b>${t.custom ? "★ " : ""}${t.title}</b>
          <div class="d-flex gap-1">
            <button class="btn btn-sm btn-outline-primary" data-tpl-use="${i}" title="Использовать">
              <i class="bi bi-box-arrow-in-down"></i>
            </button>
            ${t.custom ? `<button class="btn btn-sm btn-outline-danger" data-tpl-del="${t.id}" title="Удалить">
              <i class="bi bi-trash"></i></button>` : ""}
          </div>
        </div>
        <div class="text-muted small mt-1" style="white-space:pre-wrap">${t.text}</div>
      </div>
    `).join("");

    box.querySelectorAll("[data-tpl-use]").forEach(b => b.addEventListener("click", () => {
      const t = templatesCache[parseInt(b.dataset.tplUse, 10)];
      if (t && $("bcMessage")) {
        $("bcMessage").value = t.text;
        onMessageChange();
        document.querySelector('[data-bs-target="#waTabNew"]')?.click();
        uiToast("Шаблон вставлен в рассылку", "success");
      }
    }));
    box.querySelectorAll("[data-tpl-del]").forEach(b => b.addEventListener("click", async () => {
      if (!confirm("Удалить шаблон?")) return;
      try {
        await apiDelete(`/api/whatsapp/templates/${b.dataset.tplDel}`);
        uiToast("Шаблон удалён", "success");
        loadTemplates();
      } catch (e) { uiToast(`Ошибка: ${e.message}`, "error"); }
    }));
  }

  $("tplCreateBtn")?.addEventListener("click", async () => {
    const title = ($("tplTitle")?.value || "").trim();
    const text = ($("tplText")?.value || "").trim();
    if (!title || !text) { uiToast("Заполните название и текст", "warning"); return; }
    try {
      await apiPost("/api/whatsapp/templates", { title, text });
      $("tplTitle").value = ""; $("tplText").value = "";
      uiToast("Шаблон сохранён", "success");
      loadTemplates();
    } catch (e) { uiToast(`Ошибка: ${e.message}`, "error"); }
  });

  // ═══════════════════════════════════════════════════
  // Сводка и запуск
  // ═══════════════════════════════════════════════════
  function fmtEta(sec) {
    if (!sec || sec <= 0) return "";
    const m = Math.round(sec / 60);
    if (m < 1) return "меньше минуты";
    if (m < 60) return `≈ ${m} мин`;
    return `≈ ${Math.floor(m / 60)} ч ${m % 60} мин`;
  }

  function estimateEtaSec(count) {
    const speed = $("bcSpeed")?.value || "safe";
    const cfg = { safe: [7, 14, 25, 90], slow: [12, 20, 20, 120], fast: [4, 8, 30, 60] }[speed];
    const avg = (cfg[0] + cfg[1]) / 2 + cfg[3] / cfg[2];
    return Math.round(count * avg);
  }

  function renderSummary() {
    const box = $("bcSummary");
    if (!box) return;
    const count = lastEstimate?.count || 0;
    const msg = ($("bcMessage")?.value || "").trim();
    if (!count || !msg) { box.classList.add("d-none"); return; }
    const eta = estimateEtaSec(count);
    const finish = new Date(Date.now() + eta * 1000);
    box.classList.remove("d-none");
    box.innerHTML = `
      <div><i class="bi bi-people me-1"></i>Получателей: <b>${count}</b></div>
      <div><i class="bi bi-clock me-1"></i>Займёт ${fmtEta(eta)} — закончится к
        <b>${finish.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</b>
        (если в окне 09:00–21:00)</div>
      <div class="text-muted small mt-1">Задержки случайные, каждые ~25 сообщений — длинная пауза.</div>
      ${renderBonusLine()}
    `;
  }

  // Строка о бонусах в сводке запуска: рассылка про бонусы, отправленная
  // до самого начисления, придёт клиентам с пустым балансом.
  function renderBonusLine() {
    if (!$("bbEnabled")?.checked) return "";
    if (bbGranted) {
      return `<div class="text-success small mt-1"><i class="bi bi-check-circle me-1"></i>
        Бонусы начислены: ${fmtNum(bbGranted.granted)} клиентам по ${fmtNum(bbGranted.amount)} ₸,
        сгорят через ${bbGranted.ttl_days} дней (метка «${bbGranted.tag}»)</div>`;
    }
    return `<div class="text-warning small mt-1"><i class="bi bi-exclamation-triangle me-1"></i>
      Бонусы ещё не начислены — сделайте это в шаге 2, иначе клиенты получат
      сообщение о бонусах с пустым балансом.</div>`;
  }
  $("bcSpeed")?.addEventListener("change", renderSummary);

  function renderWarnings(warnings) {
    const box = $("bcWarnings");
    if (!box) return;
    box.innerHTML = (warnings || []).map(w =>
      `<div class="alert alert-warning py-2 mb-1 small"><i class="bi bi-exclamation-triangle me-1"></i>${w}</div>`
    ).join("");
  }

  $("bcStartBtn")?.addEventListener("click", async () => {
    const errEl = $("bcStartErr");
    errEl?.classList.add("d-none");
    const msg = ($("bcMessage")?.value || "").trim();
    if (!msg) { uiToast("Напишите текст сообщения", "warning"); return; }

    if (!lastEstimate) await runEstimate();
    const count = lastEstimate?.count || 0;
    if (!count) { uiToast("В аудитории нет получателей", "warning"); return; }

    if (!confirm(`Запустить рассылку на ${count} получателей?\nОтправка пойдёт в фоне с безопасными задержками.`)) return;

    const btn = $("bcStartBtn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Запускаем…';
    try {
      const aud = collectAudience();
      const created = await apiPost(API, {
        ...aud,
        message_template: msg,
        speed: $("bcSpeed")?.value || "safe",
        daily_cap: parseInt($("bcDailyCap")?.value || "250", 10) || 250,
      });
      await apiPost(`${API}/${created.id}/start`, {});
      uiToast("Рассылка запущена 🚀", "success");
      document.querySelector('[data-bs-target="#waTabHistory"]')?.click();
      loadHistory();
    } catch (e) {
      if (errEl) { errEl.textContent = `✗ ${e.message}`; errEl.classList.remove("d-none"); }
      uiToast(`Не удалось запустить: ${e.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-whatsapp me-1"></i> Запустить рассылку';
    }
  });

  // ═══════════════════════════════════════════════════
  // Массовое начисление бонусов аудитории
  // ═══════════════════════════════════════════════════
  let bbCheckedPayload = null;   // payload последней успешной проверки
  let bbGranted = null;          // {tag, amount, ttl_days, granted} после реального начисления

  const fmtNum = (n) => Number(n || 0).toLocaleString("ru-RU");

  function bbCollect(dryRun) {
    return {
      ...collectAudience(),
      amount: parseInt($("bbAmount")?.value || "0", 10) || 0,
      ttl_days: parseInt($("bbTtl")?.value || "30", 10) || 30,
      tag: ($("bbTag")?.value || "").trim(),
      dry_run: !!dryRun,
    };
  }

  // Аудитория без учёта dry_run — по ней сверяем, не изменились ли настройки
  // между проверкой и начислением. Списки обязаны совпадать один в один.
  function bbFingerprint(p) {
    return JSON.stringify({
      audience_kind: p.audience_kind,
      audience_params: p.audience_params,
      exclude_recent_days: p.exclude_recent_days,
      amount: p.amount,
      ttl_days: p.ttl_days,
      tag: p.tag,
    });
  }

  function bbLock(reason) {
    bbCheckedPayload = null;
    // Прошлое начисление больше не описывает текущие настройки —
    // сводка запуска не должна утверждать, что бонусы уже начислены.
    bbGranted = null;
    const btn = $("bbGrantBtn");
    if (btn) btn.disabled = true;
    if (reason && $("bbResult") && !$("bbResult").classList.contains("d-none")) {
      $("bbResult").insertAdjacentHTML("beforeend",
        `<div class="text-warning small mt-1"><i class="bi bi-exclamation-triangle me-1"></i>${reason}</div>`);
    }
  }

  function bbError(msg) {
    const el = $("bbErr");
    if (!el) return;
    el.textContent = `✗ ${msg}`;
    el.classList.remove("d-none");
  }

  function bbRenderResult(res) {
    const box = $("bbResult");
    if (!box) return;
    box.classList.remove("d-none");
    const granted = res.dry_run ? res.to_grant : res.granted;
    const sum = (res.dry_run ? res.to_grant : res.granted) * (res.amount_per_client || 0);
    box.innerHTML = `
      <div><i class="bi bi-people me-1"></i>В аудитории: <b>${fmtNum(res.audience_total)}</b>
        ${res.already_granted ? `<span class="text-muted small">· уже получили по этой метке: ${fmtNum(res.already_granted)}</span>` : ""}</div>
      <div><i class="bi bi-gift me-1"></i>${res.dry_run ? "Начислим" : "Начислено"}:
        <b>${fmtNum(granted)}</b> клиентам по ${fmtNum(res.amount_per_client)} бонусов</div>
      <div><i class="bi bi-cash-stack me-1"></i>Обязательств на сумму: <b>${fmtNum(sum)} ₸</b>
        <span class="text-muted small">· сгорят через ${res.ttl_days} дней</span></div>
      ${res.balance_cache_fixed ? `<div class="text-muted small mt-1">
        <i class="bi bi-wrench me-1"></i>Попутно исправлен фиктивный баланс в карточках:
        ${fmtNum(res.balance_cache_fixed)} клиентов${res.balance_cache_delta > 0
          ? ` — в сумме ${fmtNum(res.balance_cache_delta)} ₸ бонусов, которых на самом деле уже нет.
              Эти клиенты увидят падение суммы, о нём стоит написать в тексте рассылки.` : ""}</div>` : ""}
      ${res.note ? `<div class="text-muted small mt-1">${res.note}</div>` : ""}
      ${(res.errors || []).length ? `<div class="text-danger small mt-1">Ошибки: ${res.errors.join("; ")}</div>` : ""}
    `;
  }

  $("bbEnabled")?.addEventListener("change", (e) => {
    $("bbBox")?.classList.toggle("d-none", !e.target.checked);
    renderSummary();
  });

  // ── Пресеты суммы и срока ──────────────────────────
  // Селект — источник значения, число под ним открывается только для «своё».
  function bindPreset(selId, inputId) {
    const sel = $(selId), inp = $(inputId);
    if (!sel || !inp) return;
    sel.addEventListener("change", () => {
      const custom = sel.value === "custom";
      inp.classList.toggle("d-none", !custom);
      if (custom) inp.focus();
      else inp.value = sel.value;
      bbLock("Настройки изменились — проверьте ещё раз.");
      bbUpdateTtlHint();
      renderSummary();
    });
  }
  bindPreset("bbAmountSel", "bbAmount");
  bindPreset("bbTtlSel", "bbTtl");

  // Срок жизни бонуса должен переживать саму отправку: последние в очереди
  // получают сообщение через count/daily_cap дней после начисления.
  function bbUpdateTtlHint() {
    const hint = $("bbTtlHint");
    if (!hint) return;
    const count = lastEstimate?.count || 0;
    const cap = parseInt($("bcDailyCap")?.value || "250", 10) || 250;
    const ttl = parseInt($("bbTtl")?.value || "0", 10) || 0;
    if (!count || !ttl) { hint.textContent = ""; return; }

    const sendDays = Math.ceil(count / cap);
    if (sendDays <= 1) {
      hint.innerHTML = `<i class="bi bi-check2 me-1"></i>Рассылка уйдёт за день — весь срок достанется клиенту целиком.`;
      hint.className = "text-muted small";
      return;
    }
    const lostPct = Math.round(sendDays / ttl * 100);
    if (lostPct >= 20) {
      hint.innerHTML = `<i class="bi bi-exclamation-triangle me-1"></i>Отправка займёт ~${sendDays} дн.
        Последние в очереди получат сообщение, когда ${lostPct}% срока уже прошло —
        стоит поднять срок хотя бы до ${Math.max(ttl, sendDays * 6)} дней.`;
      hint.className = "text-warning small";
    } else {
      hint.innerHTML = `<i class="bi bi-check2 me-1"></i>Отправка займёт ~${sendDays} дн. —
        последние в очереди потеряют всего ${lostPct}% срока.`;
      hint.className = "text-muted small";
    }
  }
  $("bcDailyCap")?.addEventListener("input", bbUpdateTtlHint);

  // Любое изменение аудитории или параметров бонуса сбрасывает проверку
  ["bcMinBonus", "bcInactiveDays", "bcInactiveDaysMax", "bcTier", "bcSegment",
   "bcCampaign", "bcExcludeDays", "bbAmount", "bbTtl", "bbTag"].forEach(id => {
    $(id)?.addEventListener("input", () => bbLock("Настройки изменились — проверьте ещё раз."));
  });
  document.querySelectorAll('input[name="bcAudience"]').forEach(r => {
    r.addEventListener("change", () => bbLock("Аудитория изменилась — проверьте ещё раз."));
  });

  $("bbDryBtn")?.addEventListener("click", async () => {
    $("bbErr")?.classList.add("d-none");
    const payload = bbCollect(true);
    if (!payload.amount) { uiToast("Укажите сумму бонуса", "warning"); return; }
    if (payload.tag.length < 2) { uiToast("Укажите метку акции (минимум 2 символа)", "warning"); return; }

    const btn = $("bbDryBtn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Считаем…';
    try {
      const res = await apiPost(`${API}/bulk-bonus`, payload);
      bbRenderResult(res);
      if (res.to_grant > 0) {
        bbCheckedPayload = payload;
        if ($("bbGrantBtn")) $("bbGrantBtn").disabled = false;
      } else {
        bbLock(null);
      }
    } catch (e) {
      bbError(e.message);
      bbLock(null);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-calculator me-1"></i>Проверить';
    }
  });

  $("bbGrantBtn")?.addEventListener("click", async () => {
    $("bbErr")?.classList.add("d-none");
    if (!bbCheckedPayload) { uiToast("Сначала нажмите «Проверить»", "warning"); return; }

    const now = bbCollect(false);
    if (bbFingerprint(now) !== bbFingerprint(bbCheckedPayload)) {
      bbLock("Настройки изменились после проверки — проверьте ещё раз.");
      uiToast("Настройки изменились — проверьте ещё раз", "warning");
      return;
    }

    const total = fmtNum(bbCheckedPayload.amount);
    if (!confirm(
      `Начислить по ${total} бонусов каждому клиенту сегмента?\n\n` +
      `Метка акции: ${bbCheckedPayload.tag}\n` +
      `Срок жизни: ${bbCheckedPayload.ttl_days} дней\n\n` +
      `Отменить начисление одной кнопкой нельзя.`
    )) return;

    const btn = $("bbGrantBtn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Начисляем…';
    try {
      const res = await apiPost(`${API}/bulk-bonus`, { ...bbCheckedPayload, dry_run: false });
      bbRenderResult(res);
      uiToast(`Начислено ${fmtNum(res.granted)} клиентам 🎁`, "success");
      bbGranted = {
        tag: bbCheckedPayload.tag,
        amount: bbCheckedPayload.amount,
        ttl_days: bbCheckedPayload.ttl_days,
        granted: res.granted,
      };
      bbCheckedPayload = null;
      renderSummary();
      loadBonusReport();
    } catch (e) {
      bbError(e.message);
      uiToast(`Не удалось начислить: ${e.message}`, "error");
    } finally {
      btn.innerHTML = '<i class="bi bi-gift me-1"></i>Начислить';
      btn.disabled = true;   // после начисления нужна новая проверка
    }
  });

  // ── Отчёт по акциям ────────────────────────────────
  async function loadBonusReport() {
    const box = $("bbReportList");
    if (!box) return;
    try {
      const data = await apiGet(`${API}/bulk-bonus`);
      const items = data.items || [];
      if (!items.length) {
        box.innerHTML = '<div class="text-muted small">Массовых начислений ещё не было. ' +
          'Сделайте первое в шаге 2 вкладки «Новая рассылка».</div>';
        return;
      }
      box.innerHTML = items.map(it => {
        const dt = it.granted_at
          ? new Date(it.granted_at).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" })
          : "—";
        const exp = it.expires_at
          ? new Date(it.expires_at).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" })
          : "—";
        return `
        <div class="wa-bc-item">
          <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-2">
            <div><b>${it.tag}</b>
              <span class="text-muted small ms-1">· начислено ${dt} · сгорает ${exp}</span></div>
            <span class="badge ${it.activation_percent >= 10 ? "text-bg-success" : "text-bg-secondary"}">
              дошли до покупки: ${it.activation_percent}%
            </span>
          </div>
          <div class="row g-2">
            <div class="col-6 col-md-3"><div class="bb-metric">
              <b>${fmtNum(it.clients)}</b><small>клиентов</small></div></div>
            <div class="col-6 col-md-3"><div class="bb-metric">
              <b>${fmtNum(it.clients_activated)}</b><small>потратили бонус</small></div></div>
            <div class="col-6 col-md-3"><div class="bb-metric">
              <b>${fmtNum(it.issued)} ₸</b><small>выдано бонусов</small></div></div>
            <div class="col-6 col-md-3"><div class="bb-metric">
              <b>${fmtNum(it.used)} ₸</b><small>списано (${it.used_percent}%)</small></div></div>
          </div>
          ${it.expired ? `<div class="text-muted small mt-2">Сгорело не потраченными: ${fmtNum(it.expired)} начислений</div>` : ""}
        </div>`;
      }).join("");
    } catch (e) {
      box.innerHTML = `<div class="text-danger small">Ошибка: ${e.message}</div>`;
    }
  }

  $("bbReportRefresh")?.addEventListener("click", loadBonusReport);
  $("waBonusTabBtn")?.addEventListener("click", loadBonusReport);

  // ═══════════════════════════════════════════════════
  // История
  // ═══════════════════════════════════════════════════
  const STATUS_BADGE = {
    running:   ["text-bg-success", "Идёт отправка"],
    paused:    ["text-bg-warning text-dark", "Пауза"],
    done:      ["text-bg-primary", "Завершена"],
    cancelled: ["text-bg-secondary", "Отменена"],
    draft:     ["text-bg-light text-dark", "Черновик"],
    failed:    ["text-bg-danger", "Ошибка"],
  };

  async function loadHistory() {
    const box = $("waHistoryList");
    if (!box) return;
    try {
      const data = await apiGet(`${API}?limit=30`);
      const items = data.items || [];
      const anyRunning = items.some(b => b.status === "running");
      $("waRunningDot")?.classList.toggle("d-none", !anyRunning);

      if (!items.length) {
        box.innerHTML = '<div class="text-muted small">Рассылок ещё не было. Создайте первую во вкладке «Новая рассылка».</div>';
        return;
      }

      box.innerHTML = items.map(b => {
        const [cls, label] = STATUS_BADGE[b.status] || ["text-bg-secondary", b.status];
        const done = (b.sent || 0) + (b.failed || 0) + (b.skipped || 0);
        const pct = b.total ? Math.round(done / b.total * 100) : 0;
        const dt = b.created_at ? new Date(b.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
        return `
        <div class="wa-bc-item" data-bid="${b.id}">
          <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
            <div>
              <b>${b.name}</b>
              <span class="badge ${cls} ms-1">${label}</span>
              ${b.sender_name ? `<span class="text-muted small ms-1">· ${b.sender_name}</span>` : ""}
              <span class="text-muted small ms-1">· ${dt}</span>
            </div>
            <div class="d-flex gap-1">
              ${b.status === "running" ? `
                <button class="btn btn-sm btn-outline-warning" data-act="pause" title="Пауза"><i class="bi bi-pause-fill"></i></button>
                <button class="btn btn-sm btn-outline-danger" data-act="cancel" title="Отменить"><i class="bi bi-x-lg"></i></button>` : ""}
              ${b.status === "paused" ? `
                <button class="btn btn-sm btn-outline-success" data-act="resume" title="Продолжить"><i class="bi bi-play-fill"></i></button>
                <button class="btn btn-sm btn-outline-danger" data-act="cancel" title="Отменить"><i class="bi bi-x-lg"></i></button>` : ""}
              ${b.status === "draft" ? `
                <button class="btn btn-sm btn-outline-success" data-act="start" title="Запустить"><i class="bi bi-play-fill"></i></button>
                <button class="btn btn-sm btn-outline-danger" data-act="cancel" title="Отменить"><i class="bi bi-x-lg"></i></button>` : ""}
              <button class="btn btn-sm btn-outline-secondary" data-act="details" title="Подробнее"><i class="bi bi-list-ul"></i></button>
            </div>
          </div>
          <div class="d-flex align-items-center gap-2 mt-2">
            <div class="progress flex-grow-1"><div class="progress-bar ${b.status === "running" ? "progress-bar-striped progress-bar-animated" : ""} bg-success" style="width:${pct}%"></div></div>
            <span class="text-muted small" style="white-space:nowrap">${done} / ${b.total}</span>
          </div>
          <div class="text-muted small mt-1">
            ✓ ${b.sent} отправлено · ✗ ${b.failed} ошибок · ⤼ ${b.skipped} пропущено
            ${b.status === "running" && b.eta_seconds ? ` · осталось ${fmtEta(b.eta_seconds)}` : ""}
          </div>
          ${b.last_error ? `<div class="alert alert-warning py-1 px-2 small mt-2 mb-0">${b.last_error}</div>` : ""}
          <div class="wa-bc-details d-none mt-2" id="bcDetails${b.id}"></div>
        </div>`;
      }).join("");

      box.querySelectorAll("[data-act]").forEach(btn => {
        btn.addEventListener("click", async () => {
          const bid = btn.closest("[data-bid]")?.dataset.bid;
          const act = btn.dataset.act;
          if (!bid) return;
          if (act === "details") return toggleDetails(bid);
          if (act === "cancel" && !confirm("Отменить рассылку? Неотправленные сообщения не уйдут.")) return;
          try {
            await apiPost(`${API}/${bid}/${act}`, {});
            uiToast({ pause: "Пауза", resume: "Продолжаем", cancel: "Отменено", start: "Запущено" }[act] || "Ок", "success");
            loadHistory();
          } catch (e) {
            uiToast(`Ошибка: ${e.message}`, "error");
          }
        });
      });

      // Автообновление, пока что-то идёт
      clearTimeout(historyTimer);
      if (anyRunning) historyTimer = setTimeout(loadHistory, 4000);
    } catch (e) {
      box.innerHTML = `<div class="text-danger small">Ошибка: ${e.message}</div>`;
    }
  }

  async function toggleDetails(bid) {
    const box = $(`bcDetails${bid}`);
    if (!box) return;
    if (!box.classList.contains("d-none")) {
      box.classList.add("d-none");
      return;
    }
    box.classList.remove("d-none");
    box.innerHTML = '<div class="text-muted small">Загрузка…</div>';
    try {
      const data = await apiGet(`${API}/${bid}/messages?limit=200`);
      const items = data.items || [];
      if (!items.length) {
        box.innerHTML = '<div class="text-muted small">Пока нет записей</div>';
        return;
      }
      const stIcon = { sent: "✓", failed: "✗", pending: "…", skipped: "⤼" };
      const stCls = { sent: "text-success", failed: "text-danger", pending: "text-muted", skipped: "text-warning" };
      box.innerHTML = `
        <div class="table-responsive" style="max-height:260px;overflow-y:auto">
          <table class="table table-sm small mb-0">
            <thead><tr class="text-muted"><th></th><th>Клиент</th><th>Телефон</th><th>Время</th><th>Ошибка</th></tr></thead>
            <tbody>
              ${items.map(m => `
                <tr>
                  <td class="${stCls[m.status] || ""}">${stIcon[m.status] || m.status}</td>
                  <td>${m.name || "—"}</td>
                  <td class="text-muted">${m.phone}</td>
                  <td class="text-muted">${m.sent_at ? new Date(m.sent_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                  <td class="text-danger">${m.error || ""}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    } catch (e) {
      box.innerHTML = `<div class="text-danger small">${e.message}</div>`;
    }
  }

  $("waHistoryRefresh")?.addEventListener("click", loadHistory);
  $("waHistoryTabBtn")?.addEventListener("click", loadHistory);

  // ═══════════════════════════════════════════════════
  // Кампании (для аудитории «Из кампании»)
  // ═══════════════════════════════════════════════════
  async function loadCampaigns() {
    try {
      const data = await apiGet("/api/campaigns/");
      campaignsCache = Array.isArray(data) ? data : (data.items || []);
      const sel = $("bcCampaign");
      if (sel) {
        sel.innerHTML = '<option value="">— выберите кампанию —</option>' +
          campaignsCache.map(c =>
            `<option value="${c.id}">${c.name} (${c.recipients_total || 0} получателей)</option>`).join("");
      }
      // ?campaign_id=N — предвыбор из страницы кампании
      const cid = new URLSearchParams(location.search).get("campaign_id");
      if (cid && sel) {
        const radio = document.querySelector('input[name="bcAudience"][value="campaign"]');
        if (radio) { radio.checked = true; radio.dispatchEvent(new Event("change")); }
        sel.value = cid;
        scheduleCount();
      }
    } catch (_) {}
  }

  // ═══════════════════════════════════════════════════
  // Init
  // ═══════════════════════════════════════════════════
  loadStatus();
  loadBranchName();
  loadTemplates();
  loadCampaigns();
  loadHistory();
  runEstimate();
}

// Подстраховка: если диспетчер admin.js не вызвал initWhatsappPage —
// инициализируемся сами (функция идемпотентна).
document.addEventListener("DOMContentLoaded", () => {
  if (window.__ADMIN_PAGE__ === "whatsapp") initWhatsappPage();
});
