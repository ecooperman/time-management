let categories = [];
let categoriesById = {};
let activeTaskId = null;
let activeTaskScheduledDateKey = null; // "YYYY-MM-DD" of the open task's scheduled_date, if any - needed at save time to combine with the reminder time input into a full remind_at datetime
let activeTaskSeriesId = null; // the open task's origin task id, if it's a materialized occurrence of a recurring series - needed by the Stop repeating/Edit series buttons

// remind_at is stored/compared on the backend as a naive UTC datetime (same
// convention as created_at/completed_at, via datetime.utcnow()) - but the
// "Remind me at" field is a plain local <input type="time">, which knows
// nothing about timezones. These two helpers are the only place that
// conversion happens, in both directions, using the browser's own Date
// object so it picks up the real local offset (and DST) automatically
// rather than hardcoding one.
function localTimeToNaiveUTC(dateKey, timeStr) {
  const local = new Date(`${dateKey}T${timeStr}:00`); // parsed as local time
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${local.getUTCFullYear()}-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())}` +
    `T${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}:00`
  );
}

function naiveUTCToLocalTimeInput(naiveUTCString) {
  const utc = new Date(`${naiveUTCString}Z`); // "Z" tells Date this is UTC, not local
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(utc.getHours())}:${pad(utc.getMinutes())}`;
}

// Multi-column views don't fit a phone-width screen, and with the sidebar
// and calendar stacked (not side-by-side) below the 640px breakpoint,
// there's nowhere for a drag between them to land anyway - so mobile always
// starts in Day view, with tap-to-schedule buttons standing in for drag.
const mobileMediaQuery = window.matchMedia("(max-width: 639px)");

let currentView = mobileMediaQuery.matches ? "day" : "workWeek"; // 'day' | 'workWeek' | 'week' | 'month'
let anchorDate = new Date();
anchorDate.setHours(0, 0, 0, 0);

function minutesLabel(mins) {
  if (mins === null || mins === undefined) return null;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

// --- date helpers (all local-time, no UTC conversion) ---

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function startOfWeek(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - d.getDay());
  return d;
}

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function isoDateTime(date) {
  return `${toISODate(date)}T00:00:00`;
}

function getVisibleDays(view, anchor) {
  if (view === "day") return [new Date(anchor)];
  if (view === "twoDay") return [new Date(anchor), addDays(anchor, 1)];
  if (view === "workWeek") {
    const monday = addDays(startOfWeek(anchor), 1);
    return [0, 1, 2, 3, 4].map((i) => addDays(monday, i));
  }
  if (view === "week") {
    const sunday = startOfWeek(anchor);
    return [0, 1, 2, 3, 4, 5, 6].map((i) => addDays(sunday, i));
  }
  // month: pad to full weeks so the grid always shows complete rows
  const firstOfMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const lastOfMonth = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  const gridStart = startOfWeek(firstOfMonth);
  const gridEnd = addDays(startOfWeek(lastOfMonth), 6);
  const days = [];
  for (let d = new Date(gridStart); d <= gridEnd; d = addDays(d, 1)) {
    days.push(new Date(d));
  }
  return days;
}

function shiftAnchor(direction) {
  if (currentView === "day") {
    anchorDate = addDays(anchorDate, direction);
  } else if (currentView === "twoDay") {
    anchorDate = addDays(anchorDate, 2 * direction);
  } else if (currentView === "workWeek" || currentView === "week") {
    anchorDate = addDays(anchorDate, 7 * direction);
  } else {
    anchorDate = new Date(anchorDate.getFullYear(), anchorDate.getMonth() + direction, 1);
  }
  loadAndRenderCalendar();
}

function updateNavTitle(days) {
  const title = document.getElementById("nav-title");
  if (currentView === "day") {
    title.textContent = anchorDate.toLocaleDateString(undefined, {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  } else if (currentView === "month") {
    title.textContent = anchorDate.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  } else {
    const first = days[0];
    const last = days[days.length - 1];
    title.textContent = `${first.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${last.toLocaleDateString(
      undefined,
      { month: "short", day: "numeric", year: "numeric" }
    )}`;
  }
}

// --- categories ---

function populateCategorySelects() {
  const selects = [document.getElementById("task-category"), document.getElementById("modal-task-category")];
  for (const select of selects) {
    select.innerHTML = "";
    for (const cat of categories) {
      const opt = document.createElement("option");
      opt.value = cat.id;
      opt.textContent = cat.name;
      select.appendChild(opt);
    }
  }
}

async function loadCategories() {
  categories = await Global.fetchJSON("/api/categories");
  categoriesById = Object.fromEntries(categories.map((c) => [c.id, c]));
  populateCategorySelects();
}

// --- task card + sortable lists ---

// A task's plain link (for an apply task, the job posting), shown on its card; clicking it does not open the task.
function linkNode(task) {
  if (!task.link_url) return null;
  const link = document.createElement("a");
  link.href = task.link_url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "link";
  link.title = task.link_url;
  link.addEventListener("click", (e) => e.stopPropagation());
  return link;
}

function taskCardElement(task, { showDoneCheckbox = false } = {}) {
  const cat = categoriesById[task.category_id];
  const card = document.createElement("div");
  card.className = "task-card status-" + task.status + (task.is_important ? " important" : "");
  card.dataset.taskId = task.id;
  card.style.setProperty("--cat-color", cat ? cat.color : "#999");

  const title = document.createElement("div");
  title.className = "task-title";

  if (showDoneCheckbox) {
    const doneCheckbox = document.createElement("input");
    doneCheckbox.type = "checkbox";
    doneCheckbox.className = "task-done-checkbox";
    doneCheckbox.checked = task.status === "done";
    // Same status values the modal's Mark done/Reopen buttons already send
    // (see initModal below) - stays consistent with their side effects
    // (completed_at, reminder bookkeeping
    // reset), all of which only crud.update_task actually implements, so
    // this goes through the same PATCH + refreshAll() rather than just
    // toggling a class locally.
    doneCheckbox.addEventListener("click", (e) => e.stopPropagation());
    doneCheckbox.addEventListener("change", async () => {
      await Global.fetchJSON(`/api/tasks/${task.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: doneCheckbox.checked ? "done" : "open" }),
      });
      refreshAll();
    });
    title.appendChild(doneCheckbox);
  }

  if (task.is_important) {
    const star = document.createElement("span");
    star.className = "star";
    star.textContent = "★ ";
    title.appendChild(star);
  }
  if (task.repeat_daily || task.series_id) {
    const repeatIcon = document.createElement("span");
    repeatIcon.className = "repeat-icon";
    repeatIcon.textContent = "⟳ ";
    repeatIcon.title = "Repeats daily";
    title.appendChild(repeatIcon);
  }
  title.appendChild(document.createTextNode(task.title));
  card.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "task-meta";
  const metaParts = [document.createTextNode(cat ? cat.name : "Uncategorized")];
  const est = minutesLabel(task.estimate_minutes);
  if (est) metaParts.push(document.createTextNode(`est ${est}`));
  const link = linkNode(task);
  if (link) metaParts.push(link);
  if (task.status === "on_hold") metaParts.push(document.createTextNode("on hold"));
  metaParts.forEach((node, i) => {
    if (i > 0) meta.appendChild(document.createTextNode(" · "));
    meta.appendChild(node);
  });
  card.appendChild(meta);

  card.addEventListener("click", () => openModal(task));
  return card;
}

function attachSortable(el) {
  if (el._sortable) el._sortable.destroy();
  el._sortable = new Sortable(el, {
    group: { name: "tasks" },
    animation: 150,
    onEnd: handleSortEnd,
  });
}

async function handleSortEnd(evt) {
  const fromEl = evt.from;
  const toEl = evt.to;

  if (fromEl === toEl && evt.oldIndex === evt.newIndex) return;

  const updates = [];
  const collect = (containerEl) => {
    const date = containerEl.dataset.date || null;
    Array.from(containerEl.children).forEach((el, idx) => {
      if (!el.dataset.taskId) return;
      updates.push({
        id: Number(el.dataset.taskId),
        scheduled_date: date ? `${date}T00:00:00` : null,
        due_date: date ? `${date}T00:00:00` : null,
        sort_order: (idx + 1) * 10,
      });
    });
  };
  collect(toEl);
  if (fromEl !== toEl) collect(fromEl);

  await Global.fetchJSON("/api/tasks/reorder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });

  // Sortable.js already moved the dragged card's DOM node on its own, but
  // every card's click handler closes over the task object from the last
  // render pass - without a refresh here, opening a just-dragged task's
  // modal right away still sees its old scheduled_date (e.g. still null
  // right after a backlog->calendar drag), which wrongly disables the
  // repeat/remind fields until something else happens to trigger a
  // refresh.
  refreshAll();
}

function bucketTasksByDate(tasks) {
  const map = {};
  for (const task of tasks) {
    if (!task.scheduled_date) continue;
    const key = task.scheduled_date.slice(0, 10);
    (map[key] = map[key] || []).push(task);
  }
  return map;
}

function renderGrid(days, buckets) {
  const calendarEl = document.getElementById("calendar");
  calendarEl.className = currentView === "month" ? "grid-view" : "row-view";
  calendarEl.innerHTML = "";

  const grid = document.createElement("div");
  grid.className = "cal-grid";
  const todayKey = toISODate(new Date());

  for (const day of days) {
    const key = toISODate(day);
    const col = document.createElement("div");
    col.className =
      "day-col" + (currentView === "month" && day.getMonth() !== anchorDate.getMonth() ? " other-month" : "");

    const header = document.createElement("div");
    header.className = "day-col-header" + (key === todayKey ? " today" : "");
    const weekdayShort = day.toLocaleDateString(undefined, { weekday: "short" });
    const dateLabel = day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    header.innerHTML = `<span class="weekday">${weekdayShort}</span>${dateLabel}`;
    col.appendChild(header);

    const list = document.createElement("div");
    list.className = "task-list";
    list.dataset.date = key;
    for (const task of buckets[key] || []) {
      list.appendChild(taskCardElement(task, { showDoneCheckbox: true }));
    }
    col.appendChild(list);

    grid.appendChild(col);
    attachSortable(list);
  }

  calendarEl.appendChild(grid);
}

async function loadAndRenderCalendar() {
  const days = getVisibleDays(currentView, anchorDate);
  const start = isoDateTime(days[0]);
  const end = isoDateTime(addDays(days[days.length - 1], 1));
  const tasks = await Global.withLoading(
    document.getElementById("calendar"),
    Global.fetchJSON(`/api/tasks?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`)
  );
  renderGrid(days, bucketTasksByDate(tasks));
  updateNavTitle(days);
}

function renderBacklog(tasks) {
  const list = document.getElementById("backlog-list");
  list.innerHTML = "";
  const dateKey = toISODate(anchorDate);
  const dayLabel = anchorDate.toLocaleDateString(undefined, { weekday: "short" });
  for (const task of tasks) {
    const card = taskCardElement(task);
    // Hidden by CSS at 640px+ - drag-and-drop covers this on desktop.
    card.appendChild(scheduleButton(dateKey, dayLabel, (d) => scheduleTaskToDay(task.id, d)));
    list.appendChild(card);
  }
  attachSortable(list);
}

async function refreshBacklog() {
  const tasks = await Global.withLoading(document.getElementById("backlog-list"), Global.fetchJSON("/api/tasks/backlog"));
  renderBacklog(tasks);
}

// --- mobile tap-to-schedule (stands in for drag-and-drop below 640px,
// where the backlog list and the calendar day aren't visible at the
// same time) ---

function scheduleButton(dateKey, dayLabel, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "schedule-btn";
  btn.textContent = `+ Add to ${dayLabel}`;
  btn.dataset.btnIcon = "plus";
  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    btn.disabled = true;
    try {
      await onClick(dateKey);
    } finally {
      btn.disabled = false;
    }
  });
  return btn;
}

async function scheduleTaskToDay(taskId, dateKey) {
  await Global.fetchJSON(`/api/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scheduled_date: `${dateKey}T00:00:00`, due_date: `${dateKey}T00:00:00` }),
  });
  await refreshAll();
}

async function refreshAll() {
  await Promise.all([loadAndRenderCalendar(), refreshBacklog()]);
}

// --- view toggle + nav ---

function setActiveViewButton(view) {
  document.querySelectorAll("#view-toggle button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
}

function initViewToggle() {
  document.querySelectorAll("#view-toggle button").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentView = btn.dataset.view;
      setActiveViewButton(currentView);
      loadAndRenderCalendar();
    });
  });
  setActiveViewButton(currentView);

  // Crossing into mobile width (e.g. rotating a tablet, resizing a desktop
  // window) forces Day view, since Day and 2 Day are the only ones the
  // layout supports below 640px. Doesn't force the other direction - if you
  // resize back up you keep whatever view you're on and can pick a wider
  // one manually.
  mobileMediaQuery.addEventListener("change", (e) => {
    if (e.matches && currentView !== "day" && currentView !== "twoDay") {
      currentView = "day";
      setActiveViewButton(currentView);
      loadAndRenderCalendar();
    }
  });
}

function initNavControls() {
  document.getElementById("nav-prev").addEventListener("click", () => shiftAnchor(-1));
  document.getElementById("nav-next").addEventListener("click", () => shiftAnchor(1));
  document.getElementById("nav-today").addEventListener("click", () => {
    anchorDate = new Date();
    anchorDate.setHours(0, 0, 0, 0);
    loadAndRenderCalendar();
  });
}

// --- jump-to-date picker (self-contained, not a native <input type="date">
// - see the CSS comment on #nav-jump-btn for why) ---

let jumpModalMonth = new Date();

function renderJumpModalGrid() {
  const grid = document.getElementById("jump-modal-grid");
  grid.innerHTML = "";
  const days = getVisibleDays("month", jumpModalMonth);
  const todayKey = toISODate(new Date());
  for (const day of days) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = day.getDate();
    if (day.getMonth() !== jumpModalMonth.getMonth()) btn.classList.add("other-month");
    if (toISODate(day) === todayKey) btn.classList.add("today");
    btn.addEventListener("click", () => {
      anchorDate = new Date(day);
      closeJumpModal();
      loadAndRenderCalendar();
    });
    grid.appendChild(btn);
  }
  document.getElementById("jump-modal-title").textContent = jumpModalMonth.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function openJumpModal() {
  jumpModalMonth = new Date(anchorDate.getFullYear(), anchorDate.getMonth(), 1);
  renderJumpModalGrid();
  document.getElementById("jump-modal").classList.remove("hidden");
}

function closeJumpModal() {
  document.getElementById("jump-modal").classList.add("hidden");
}

function initJumpModal() {
  document.getElementById("nav-jump-btn").addEventListener("click", openJumpModal);
  document.getElementById("jump-modal-close").addEventListener("click", closeJumpModal);
  document.getElementById("jump-modal-prev").addEventListener("click", () => {
    jumpModalMonth = new Date(jumpModalMonth.getFullYear(), jumpModalMonth.getMonth() - 1, 1);
    renderJumpModalGrid();
  });
  document.getElementById("jump-modal-next").addEventListener("click", () => {
    jumpModalMonth = new Date(jumpModalMonth.getFullYear(), jumpModalMonth.getMonth() + 1, 1);
    renderJumpModalGrid();
  });
}

// --- modal ---

function openModal(task) {
  activeTaskId = task.id;
  document.getElementById("modal-title").textContent = task.title;
  document.getElementById("modal-task-title").value = task.title;
  document.getElementById("modal-task-category").value = task.category_id;
  document.getElementById("modal-task-description").value = task.description || "";
  document.getElementById("modal-task-estimate").value = task.estimate_minutes ?? "";
  document.getElementById("modal-task-actual").value = task.actual_minutes ?? "";
  document.getElementById("modal-task-important").checked = !!task.is_important;
  document.getElementById("modal-task-status").textContent = task.status;

  const repeatCheckbox = document.getElementById("modal-task-repeat");
  const repeatUntilRow = document.getElementById("modal-repeat-until-row");
  const isScheduled = !!task.scheduled_date;
  repeatCheckbox.disabled = !isScheduled;
  repeatCheckbox.checked = isScheduled && !!task.repeat_daily;
  document.getElementById("modal-task-repeat-until").value = task.repeat_until ? task.repeat_until.slice(0, 10) : "";
  repeatUntilRow.classList.toggle("hidden", !repeatCheckbox.checked);
  document.getElementById("modal-repeat-disabled-hint").classList.toggle("hidden", isScheduled);

  // A materialized occurrence's own repeat_daily is always false (only the
  // origin has it set) - series_id is what actually says "this belongs to
  // a series", and is the only thing shown for it. Not shown on the origin
  // itself, which already has the real repeat-daily controls right above.
  activeTaskSeriesId = task.series_id || null;
  document.getElementById("modal-series-info").classList.toggle("hidden", !task.series_id);

  activeTaskScheduledDateKey = isScheduled ? task.scheduled_date.slice(0, 10) : null;
  const remindCheckbox = document.getElementById("modal-task-remind");
  const remindFields = document.getElementById("modal-remind-fields");
  remindCheckbox.disabled = !isScheduled;
  remindCheckbox.checked = isScheduled && !!task.remind_at;
  document.getElementById("modal-task-remind-time").value = task.remind_at ? naiveUTCToLocalTimeInput(task.remind_at) : "";
  document.getElementById("modal-task-remind-snooze").value = task.remind_snooze_minutes || "";
  document.getElementById("modal-task-remind-max").value = task.remind_max_count ?? "";
  remindFields.classList.toggle("hidden", !remindCheckbox.checked);
  document.getElementById("modal-remind-disabled-hint").classList.toggle("hidden", isScheduled);

  const linkInput = document.getElementById("modal-task-link");
  linkInput.value = task.link_url || "";
  const showOpenLink = () => {
    const url = linkInput.value.trim();
    const open = document.getElementById("modal-link-open");
    open.classList.toggle("hidden", !/^https?:\/\//i.test(url));
    document.getElementById("modal-link-open-anchor").href = url;
  };
  linkInput.oninput = showOpenLink;
  showOpenLink();

  document.getElementById("modal-mark-done").classList.toggle("hidden", task.status === "done");
  document.getElementById("modal-reopen").classList.toggle("hidden", task.status !== "done");

  document.getElementById("task-modal").classList.remove("hidden");
}

function closeModal() {
  activeTaskId = null;
  activeTaskScheduledDateKey = null;
  activeTaskSeriesId = null;
  document.getElementById("task-modal").classList.add("hidden");
}

function initModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal);

  document.getElementById("modal-task-repeat").addEventListener("change", (e) => {
    document.getElementById("modal-repeat-until-row").classList.toggle("hidden", !e.target.checked);
  });

  document.getElementById("modal-task-remind").addEventListener("change", (e) => {
    document.getElementById("modal-remind-fields").classList.toggle("hidden", !e.target.checked);
  });

  document.getElementById("modal-stop-recurrence").addEventListener("click", async () => {
    if (
      !confirm(
        "Stop this recurring series as of this task? Not-yet-passed future occurrences will be removed; past ones stay as history."
      )
    ) {
      return;
    }
    try {
      await Global.fetchJSON(`/api/tasks/${activeTaskId}/stop-recurrence`, { method: "POST" });
      Global.showMessage("Recurrence stopped.", "success");
      closeModal();
      refreshAll();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  document.getElementById("modal-edit-series").addEventListener("click", async () => {
    try {
      const origin = await Global.fetchJSON(`/api/tasks/${activeTaskSeriesId}`);
      closeModal();
      openModal(origin);
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  document.getElementById("modal-save").addEventListener("click", async () => {
    const repeatUntil = document.getElementById("modal-task-repeat-until").value;

    const remindEnabled = document.getElementById("modal-task-remind").checked;
    const remindTime = document.getElementById("modal-task-remind-time").value;
    const remindSnooze = document.getElementById("modal-task-remind-snooze").value;
    const remindMax = document.getElementById("modal-task-remind-max").value;
    // remind_at needs a full datetime - combine the task's own scheduled
    // day with the time picked here, then convert from local wall-clock
    // time to naive UTC (see localTimeToNaiveUTC above) - the backend
    // compares this against datetime.utcnow(), so sending raw local digits
    // here would silently misfire by the browser's UTC offset. If the
    // checkbox is on but no time was actually chosen yet, treat it as
    // not-set rather than guessing one.
    const remindAt =
      remindEnabled && remindTime && activeTaskScheduledDateKey
        ? localTimeToNaiveUTC(activeTaskScheduledDateKey, remindTime)
        : null;

    await Global.fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: document.getElementById("modal-task-title").value,
        category_id: Number(document.getElementById("modal-task-category").value),
        description: document.getElementById("modal-task-description").value,
        estimate_minutes: document.getElementById("modal-task-estimate").value
          ? Number(document.getElementById("modal-task-estimate").value)
          : null,
        actual_minutes: document.getElementById("modal-task-actual").value
          ? Number(document.getElementById("modal-task-actual").value)
          : null,
        is_important: document.getElementById("modal-task-important").checked,
        link_url: document.getElementById("modal-task-link").value.trim() || null,
        repeat_daily: document.getElementById("modal-task-repeat").checked,
        repeat_until: repeatUntil ? `${repeatUntil}T00:00:00` : null,
        remind_at: remindAt,
        remind_snooze_minutes: remindAt && remindSnooze ? Number(remindSnooze) : null,
        remind_max_count: remindAt && remindMax ? Number(remindMax) : null,
      }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-mark-done").addEventListener("click", async () => {
    await Global.fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "done" }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-reopen").addEventListener("click", async () => {
    await Global.fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "open" }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-toggle-hold").addEventListener("click", async () => {
    await Global.fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "on_hold" }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-to-backlog").addEventListener("click", async () => {
    await Global.fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "open", scheduled_date: null }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-delete").addEventListener("click", async () => {
    await Global.fetchJSON(`/api/tasks/${activeTaskId}`, { method: "DELETE" });
    closeModal();
    refreshAll();
  });
}

function initAddTaskForm() {
  // Defaults the schedule-date field to today the first time it's touched,
  // rather than leaving it on a blank/placeholder date the user has to
  // fill in by hand for the common case of "add this for today". Only
  // fires once - if they then deliberately clear it back to blank (meaning
  // "backlog, no schedule"), leave it alone rather than fighting them.
  const scheduleDateInput = document.getElementById("task-schedule-date");
  scheduleDateInput.addEventListener(
    "focus",
    () => {
      if (!scheduleDateInput.value) scheduleDateInput.value = toISODate(new Date());
    },
    { once: true }
  );

  document.getElementById("add-task-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("task-title").value.trim();
    if (!title) return;
    const scheduleDate = scheduleDateInput.value;

    const task = await Global.fetchJSON("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        category_id: Number(document.getElementById("task-category").value),
        estimate_minutes: document.getElementById("task-estimate").value
          ? Number(document.getElementById("task-estimate").value)
          : null,
        description: document.getElementById("task-description").value,
        link_url: document.getElementById("task-link").value.trim() || null,
        is_important: document.getElementById("task-important").checked,
      }),
    });

    // TaskCreate doesn't take a schedule date directly (a plain backlog
    // task is the common case) - so it is a two-step create-then-PATCH.
    // scheduleDate is already a plain "YYYY-MM-DD" string straight
    // from the date input's own value - build the datetime string directly
    // rather than routing it through `new Date(scheduleDate)`, which
    // parses a date-only string as UTC midnight and would silently roll
    // back a day in any timezone behind UTC (the exact bug class just
    // fixed for reminders - see localTimeToNaiveUTC above).
    if (scheduleDate) {
      await Global.fetchJSON(`/api/tasks/${task.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scheduled_date: `${scheduleDate}T00:00:00`, due_date: `${scheduleDate}T00:00:00` }),
      });
    }

    e.target.reset();
    refreshAll();
    collapseSidebar();
  });
}

// --- mobile sidebar collapse (the toggle itself is CSS-hidden at 640px+,
// so this never runs there) ---

function collapseSidebar() {
  document.getElementById("sidebar-content").classList.remove("expanded");
  document.getElementById("sidebar-toggle").classList.remove("expanded");
}

function initSidebarToggle() {
  const toggle = document.getElementById("sidebar-toggle");
  const content = document.getElementById("sidebar-content");
  toggle.addEventListener("click", () => {
    const expanded = content.classList.toggle("expanded");
    toggle.classList.toggle("expanded", expanded);
    if (expanded) {
      document.getElementById("task-title").focus();
    }
  });
}

// A reminder push's "Open" tap links here as /?task=<id> (see
// app/reminders.py) so it lands straight in that task's modal instead of
// just the day view - the closest thing to one-tap "mark done" iOS allows,
// since it ignores the notification's actual action button entirely (see
// static/sw.js). Strips the query param afterward so a later manual
// refresh of this same tab doesn't keep reopening it.
async function openTaskFromQueryParam() {
  const params = new URLSearchParams(location.search);
  const taskId = params.get("task");
  if (!taskId) return;
  history.replaceState(null, "", location.pathname);
  try {
    const task = await Global.fetchJSON(`/api/tasks/${taskId}`);
    openModal(task);
  } catch (e) {
    // Task was deleted, or some other fetch failure - nothing sensible to
    // recover into, just land on the normal calendar view.
  }
}

async function init() {
  await loadCategories();
  initViewToggle();
  initNavControls();
  initModal();
  // The new look keeps Save and Mark done / Reopen in view; hold, back to
  // backlog and delete fold into a "..." menu (shared-assets' foldActions).
  Global.foldActions(document.getElementById("modal-save").parentElement, { keep: "#modal-save, #modal-mark-done, #modal-reopen" });
  initAddTaskForm();
  initJumpModal();
  initSidebarToggle();
  await refreshAll();
  await openTaskFromQueryParam();
}

init();
