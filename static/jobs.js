async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = `${url} -> ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (e) {
      // ignore, use default detail
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

function showMessage(text, kind) {
  const el = document.getElementById("admin-message");
  el.textContent = text;
  el.className = "admin-message " + kind;
  setTimeout(() => el.classList.add("hidden"), 4000);
}

function labeledInput(labelText, type, value) {
  const label = document.createElement("label");
  label.appendChild(document.createTextNode(labelText));
  const input = document.createElement("input");
  input.type = type;
  input.value = value || "";
  label.appendChild(input);
  return { label, input };
}

function tierBadge(tier) {
  if (!tier) return null;
  const badge = document.createElement("span");
  badge.className = "tier-badge tier-" + tier.toLowerCase();
  badge.textContent = tier;
  return badge;
}

function scoreDetailBlock(job) {
  if (!job.tier && !job.salary && !job.summary && !job.matched && !job.gaps && !job.strengths && !job.jd_text) {
    return null;
  }

  const block = document.createElement("div");
  block.className = "job-admin-score";

  if (job.salary) {
    const salary = document.createElement("p");
    salary.className = "job-admin-score-salary";
    salary.textContent = job.salary;
    block.appendChild(salary);
  }

  if (job.summary) {
    const p = document.createElement("p");
    p.className = "job-admin-score-summary";
    p.textContent = job.summary;
    block.appendChild(p);
  }

  for (const [label, value] of [
    ["Matched", job.matched],
    ["Strengths", job.strengths],
    ["Gaps", job.gaps],
  ]) {
    if (!value) continue;
    const section = document.createElement("div");
    section.className = "job-admin-score-section";
    const heading = document.createElement("div");
    heading.className = "job-admin-score-label";
    heading.textContent = label;
    section.appendChild(heading);
    const ul = document.createElement("ul");
    for (const item of value.split("|")) {
      if (!item.trim()) continue;
      const li = document.createElement("li");
      li.textContent = item.trim();
      ul.appendChild(li);
    }
    section.appendChild(ul);
    block.appendChild(section);
  }

  if (job.jd_text) {
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "job-admin-jd-toggle";
    toggle.textContent = "Show full job description";
    const jdText = document.createElement("pre");
    jdText.className = "job-admin-jd-text hidden";
    jdText.textContent = job.jd_text;
    toggle.addEventListener("click", () => {
      const showing = jdText.classList.toggle("hidden");
      toggle.textContent = showing ? "Show full job description" : "Hide full job description";
    });
    block.append(toggle, jdText);
  }

  return block;
}

function resumeActionsBlock(job) {
  const block = document.createElement("div");
  block.className = "job-admin-resume";

  const generateBtn = document.createElement("button");
  generateBtn.type = "button";
  generateBtn.className = "job-admin-resume-generate";
  const idleLabel = job.resume_generated_at ? "Regenerate Resume + Cover Letter" : "Generate Resume + Cover Letter";
  generateBtn.textContent = idleLabel;
  generateBtn.addEventListener("click", async () => {
    generateBtn.disabled = true;
    generateBtn.textContent = "Generating... (about a minute)";
    try {
      await fetchJSON(`/api/jobs/${job.id}/generate-resume`, { method: "POST" });
      showMessage(`Generated a resume for "${job.name}".`, "success");
      loadJobs();
    } catch (err) {
      showMessage(err.message, "error");
      generateBtn.disabled = false;
      generateBtn.textContent = idleLabel;
    }
  });
  block.appendChild(generateBtn);

  if (job.resume_generated_at) {
    const meta = document.createElement("p");
    meta.className = "job-admin-resume-meta";
    meta.textContent = `Generated ${new Date(job.resume_generated_at).toLocaleString()}`;
    block.appendChild(meta);

    const downloads = document.createElement("div");
    downloads.className = "job-admin-resume-downloads";
    const pdfLink = document.createElement("a");
    pdfLink.href = `/api/jobs/${job.id}/resume.pdf`;
    pdfLink.className = "job-admin-resume-download";
    pdfLink.textContent = "Download PDF";
    const docxLink = document.createElement("a");
    docxLink.href = `/api/jobs/${job.id}/resume.docx`;
    docxLink.className = "job-admin-resume-download";
    docxLink.textContent = "Download DOCX";
    downloads.append(pdfLink, docxLink);
    block.appendChild(downloads);

    if (job.generated_cover_letter) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "job-admin-jd-toggle";
      toggle.textContent = "Show cover letter";

      const letterBox = document.createElement("div");
      letterBox.className = "job-admin-cover-letter hidden";

      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "job-admin-cover-letter-copy";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", async () => {
        await navigator.clipboard.writeText(job.generated_cover_letter);
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
      });

      const letterText = document.createElement("pre");
      letterText.className = "job-admin-cover-letter-text";
      letterText.textContent = job.generated_cover_letter;

      letterBox.append(copyBtn, letterText);
      toggle.addEventListener("click", () => {
        const showing = letterBox.classList.toggle("hidden");
        toggle.textContent = showing ? "Show cover letter" : "Hide cover letter";
      });
      block.append(toggle, letterBox);
    }
  }

  return block;
}

function jobAdminCardElement(job) {
  const card = document.createElement("div");
  card.className = "job-admin-card" + (job.applied ? " applied" : "");
  card.dataset.jobId = job.id;

  // Collapsed by default - just enough to identify the job at a glance.
  // Client-side only for now; if this needs to survive a reload later, it
  // becomes a persisted field on the job and an API call here instead.
  const summary = document.createElement("button");
  summary.type = "button";
  summary.className = "job-admin-summary";
  summary.setAttribute("aria-expanded", "false");

  const title = document.createElement("span");
  title.className = "job-admin-summary-title";
  title.textContent = job.name;
  summary.appendChild(title);

  const owner = ownerTag(job);
  if (owner) summary.appendChild(owner);

  // The badge is reserved for tier (resume-fit strength) - "applied" is
  // shown by tinting the whole card green instead (see .job-admin-card.applied),
  // so the two signals don't compete for the same visual slot.
  const tier = tierBadge(job.tier);
  if (tier) summary.appendChild(tier);

  const chevron = document.createElement("span");
  chevron.className = "job-admin-chevron";
  chevron.textContent = "▸";
  chevron.setAttribute("aria-hidden", "true");
  summary.appendChild(chevron);

  const details = document.createElement("div");
  details.className = "job-admin-details hidden";

  summary.addEventListener("click", () => {
    const expanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !expanded);
    summary.setAttribute("aria-expanded", String(expanded));
  });

  card.append(summary, details);

  const scoreBlock = scoreDetailBlock(job);
  if (scoreBlock) details.appendChild(scoreBlock);

  details.appendChild(resumeActionsBlock(job));

  const fields = document.createElement("div");
  fields.className = "job-admin-fields";

  const name = labeledInput("Name", "text", job.name);
  const company = labeledInput("Company", "text", job.company);
  const url = labeledInput("URL", "url", job.url);
  const companyUrl = labeledInput("Company URL", "url", job.company_url);

  const ownerLabel = document.createElement("label");
  ownerLabel.appendChild(document.createTextNode("Owner"));
  const ownerSelect = document.createElement("select");
  populatePersonSelect(ownerSelect, "No owner");
  ownerSelect.value = job.owner_id != null ? String(job.owner_id) : "";
  ownerLabel.appendChild(ownerSelect);

  fields.append(name.label, company.label, url.label, companyUrl.label, ownerLabel);
  details.appendChild(fields);

  const actions = document.createElement("div");
  actions.className = "job-admin-actions";

  const appliedLabel = document.createElement("label");
  appliedLabel.className = "checkbox-label";
  const appliedInput = document.createElement("input");
  appliedInput.type = "checkbox";
  appliedInput.checked = !!job.applied;
  appliedLabel.append(appliedInput, document.createTextNode("Applied"));
  actions.appendChild(appliedLabel);

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", async () => {
    const nameVal = name.input.value.trim();
    const urlVal = url.input.value.trim();
    if (!nameVal || !urlVal) {
      showMessage("Name and URL are required.", "error");
      return;
    }
    try {
      await fetchJSON(`/api/jobs/${job.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: nameVal,
          url: urlVal,
          company: company.input.value.trim() || null,
          company_url: companyUrl.input.value.trim() || null,
          owner_id: ownerSelect.value ? Number(ownerSelect.value) : null,
          applied: appliedInput.checked,
        }),
      });
      showMessage(`Saved "${nameVal}".`, "success");
      loadJobs();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });
  actions.appendChild(saveBtn);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.textContent = "Delete";
  deleteBtn.className = "danger";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete "${job.name}"?`)) return;
    try {
      await fetchJSON(`/api/jobs/${job.id}`, { method: "DELETE" });
      showMessage(`Deleted "${job.name}".`, "success");
      loadJobs();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });
  actions.appendChild(deleteBtn);

  details.appendChild(actions);
  return card;
}

// --- filtering + sorting (client-side, over whatever /api/jobs last
// returned - no need to re-fetch just because the filter/sort changed) ---

const TIER_RANK = { Strong: 0, Good: 1, Possible: 2, Weak: 3 };

// First-time default: only Strong/Good shown. Once a visitor touches the
// filter buttons, their actual choice is what's stored from then on - this
// only applies before jobFilterHiddenTiers exists in localStorage at all.
const DEFAULT_HIDDEN_TIERS = ["Possible", "Weak", "Unscored", "Unclear"];

let allJobs = [];
let allPeople = [];

function personById(id) {
  return allPeople.find((p) => p.id === id) || null;
}

function populatePersonSelect(select, blankLabel) {
  const previousValue = select.value;
  select.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = blankLabel;
  select.appendChild(blank);
  for (const person of allPeople) {
    const option = document.createElement("option");
    option.value = String(person.id);
    option.textContent = person.name;
    select.appendChild(option);
  }
  if ([...select.options].some((o) => o.value === previousValue)) {
    select.value = previousValue;
  }
}

async function loadPeople() {
  allPeople = await fetchJSON("/api/people");
  populatePersonSelect(document.getElementById("new-job-owner"), "No owner");

  const importSelect = document.getElementById("import-owner-select");
  populatePersonSelect(importSelect, "No owner");
  const savedOwner = localStorage.getItem("jobImportOwnerId");
  if (savedOwner && [...importSelect.options].some((o) => o.value === savedOwner)) {
    importSelect.value = savedOwner;
  }

  renderOwnerFilterButtons();
}

// Unlike tiers, owners are a dynamic, user-managed list (see admin.html) -
// the filter buttons for them can't be static HTML, they're built here once
// people are loaded. "Unassigned" stands in for jobs with no owner_id, same
// idea as tiers' "Unscored".
const UNASSIGNED_OWNER_KEY = "unassigned";

function jobOwnerKey(job) {
  return job.owner_id != null ? String(job.owner_id) : UNASSIGNED_OWNER_KEY;
}

function renderOwnerFilterButtons() {
  const container = document.getElementById("job-owner-filters");
  container.innerHTML = "";
  if (allPeople.length === 0) return; // nobody configured yet - nothing to filter by

  const entries = [...allPeople.map((p) => ({ key: String(p.id), label: p.name, color: p.color }))];
  entries.push({ key: UNASSIGNED_OWNER_KEY, label: "Unassigned", color: null });

  for (const entry of entries) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "owner-filter-btn";
    btn.dataset.owner = entry.key;
    if (entry.color) {
      const dot = document.createElement("span");
      dot.className = "owner-filter-dot";
      dot.style.background = entry.color;
      btn.appendChild(dot);
    }
    btn.appendChild(document.createTextNode(entry.label));
    btn.classList.toggle("inactive", jobFilterState.hiddenOwners.has(entry.key));
    btn.addEventListener("click", () => {
      if (jobFilterState.hiddenOwners.has(entry.key)) {
        jobFilterState.hiddenOwners.delete(entry.key);
      } else {
        jobFilterState.hiddenOwners.add(entry.key);
      }
      btn.classList.toggle("inactive", jobFilterState.hiddenOwners.has(entry.key));
      saveJobFilterState();
      renderJobList();
    });
    container.appendChild(btn);
  }
}

function ownerTag(job) {
  const person = job.owner_id != null ? personById(job.owner_id) : null;
  if (!person) return null;
  const tag = document.createElement("span");
  tag.className = "owner-tag";
  const dot = document.createElement("span");
  dot.className = "owner-filter-dot";
  dot.style.background = person.color;
  tag.append(dot, document.createTextNode(person.name));
  return tag;
}

function loadJobFilterState() {
  let hiddenTiers = DEFAULT_HIDDEN_TIERS;
  let hiddenOwners = [];
  let sort = "tier";
  try {
    const storedTiers = localStorage.getItem("jobFilterHiddenTiers");
    hiddenTiers = storedTiers === null ? DEFAULT_HIDDEN_TIERS : JSON.parse(storedTiers);
    hiddenOwners = JSON.parse(localStorage.getItem("jobFilterHiddenOwners") || "[]");
    sort = localStorage.getItem("jobFilterSort") || "tier";
  } catch (e) {
    // ignore malformed/unavailable localStorage, fall back to defaults
  }
  return { hiddenTiers: new Set(hiddenTiers), hiddenOwners: new Set(hiddenOwners), sort };
}

const jobFilterState = loadJobFilterState();

function saveJobFilterState() {
  localStorage.setItem("jobFilterHiddenTiers", JSON.stringify(Array.from(jobFilterState.hiddenTiers)));
  localStorage.setItem("jobFilterHiddenOwners", JSON.stringify(Array.from(jobFilterState.hiddenOwners)));
  localStorage.setItem("jobFilterSort", jobFilterState.sort);
}

function jobTierKey(job) {
  return job.tier || "Unscored";
}

function visibleSortedJobs() {
  const visible = allJobs.filter(
    (j) => !jobFilterState.hiddenTiers.has(jobTierKey(j)) && !jobFilterState.hiddenOwners.has(jobOwnerKey(j))
  );
  if (jobFilterState.sort === "tier") {
    // Best fit first, then newest first within each tier - explicit on the
    // created_at tie-break rather than leaning on server order, so this
    // stays correct even if the server's default ordering ever changes.
    visible.sort((a, b) => {
      if (a.applied !== b.applied) return a.applied ? 1 : -1;
      const rankA = a.tier in TIER_RANK ? TIER_RANK[a.tier] : 4;
      const rankB = b.tier in TIER_RANK ? TIER_RANK[b.tier] : 4;
      if (rankA !== rankB) return rankA - rankB;
      return new Date(b.created_at) - new Date(a.created_at);
    });
  }
  // "newest" keeps server order as-is (already applied-last, newest-first).
  return visible;
}

function renderJobList() {
  const container = document.getElementById("job-rows");
  container.innerHTML = "";
  const visible = visibleSortedJobs();

  const countEl = document.getElementById("job-filter-count");
  countEl.textContent =
    visible.length === allJobs.length
      ? `${allJobs.length} job${allJobs.length === 1 ? "" : "s"}`
      : `Showing ${visible.length} of ${allJobs.length} jobs`;

  if (allJobs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "note";
    empty.textContent = "No jobs yet - add one above to get started.";
    container.appendChild(empty);
    return;
  }
  if (visible.length === 0) {
    const empty = document.createElement("p");
    empty.className = "note";
    empty.textContent = "No jobs match the current filter.";
    container.appendChild(empty);
    return;
  }
  for (const job of visible) {
    container.appendChild(jobAdminCardElement(job));
  }
}

async function loadJobs() {
  allJobs = await fetchJSON("/api/jobs");
  renderJobList();
}

function initJobFilters() {
  for (const btn of document.querySelectorAll(".tier-filter-btn")) {
    const tier = btn.dataset.tier;
    btn.classList.toggle("inactive", jobFilterState.hiddenTiers.has(tier));
    btn.addEventListener("click", () => {
      if (jobFilterState.hiddenTiers.has(tier)) {
        jobFilterState.hiddenTiers.delete(tier);
      } else {
        jobFilterState.hiddenTiers.add(tier);
      }
      btn.classList.toggle("inactive", jobFilterState.hiddenTiers.has(tier));
      saveJobFilterState();
      renderJobList();
    });
  }

  const sortSelect = document.getElementById("job-sort-select");
  sortSelect.value = jobFilterState.sort;
  sortSelect.addEventListener("change", () => {
    jobFilterState.sort = sortSelect.value;
    saveJobFilterState();
    renderJobList();
  });
}

function initAddJobForm() {
  const form = document.getElementById("add-job-form");
  const showBtn = document.getElementById("show-add-job");
  const cancelBtn = document.getElementById("cancel-add-job");

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    document.getElementById("new-job-name").focus();
  });

  cancelBtn.addEventListener("click", () => {
    form.reset();
    form.classList.add("hidden");
    showBtn.classList.remove("hidden");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("new-job-name").value.trim();
    const url = document.getElementById("new-job-url").value.trim();
    const company = document.getElementById("new-job-company").value.trim();
    const companyUrl = document.getElementById("new-job-company-url").value.trim();
    const ownerId = document.getElementById("new-job-owner").value;
    if (!name || !url) return;
    try {
      await fetchJSON("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          url,
          company: company || null,
          company_url: companyUrl || null,
          owner_id: ownerId ? Number(ownerId) : null,
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      showMessage("Job added.", "success");
      loadJobs();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });
}

function initImportJobs() {
  document.getElementById("import-jobs-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const ownerId = document.getElementById("import-owner-select").value;
    localStorage.setItem("jobImportOwnerId", ownerId);
    const formData = new FormData();
    formData.append("file", file);
    if (ownerId) formData.append("owner_id", ownerId);
    try {
      // No Content-Type header here on purpose - the browser sets the
      // multipart boundary itself from the FormData body; setting it
      // manually would break the upload.
      const result = await fetchJSON("/api/jobs/import", { method: "POST", body: formData });
      const parts = [`${result.created} new`, `${result.updated} updated`];
      if (result.skipped) parts.push(`${result.skipped} skipped`);
      showMessage(`Import complete: ${parts.join(", ")}.`, "success");
      loadJobs();
    } catch (err) {
      showMessage(err.message, "error");
    } finally {
      e.target.value = "";
    }
  });
}

function initBulkResumeGeneration() {
  const openBtn = document.getElementById("bulk-generate-btn");
  const modal = document.getElementById("bulk-resume-modal");
  const closeBtn = document.getElementById("bulk-resume-modal-close");
  const cancelBtn = document.getElementById("bulk-resume-cancel");
  const confirmBtn = document.getElementById("bulk-resume-confirm");
  const countEl = document.getElementById("bulk-resume-modal-count");
  const listEl = document.getElementById("bulk-resume-job-list");
  const progressEl = document.getElementById("bulk-resume-progress");
  const progressText = document.getElementById("bulk-resume-progress-text");
  const progressFill = document.getElementById("bulk-resume-progress-fill");
  const resultsEl = document.getElementById("bulk-resume-results");

  function resetModal() {
    progressEl.classList.add("hidden");
    progressFill.style.width = "0%";
    resultsEl.innerHTML = "";
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Generate";
    cancelBtn.classList.remove("hidden");
    cancelBtn.textContent = "Cancel";
  }

  function closeModal() {
    modal.classList.add("hidden");
    resetModal();
  }

  openBtn.addEventListener("click", () => {
    const visible = visibleSortedJobs();
    if (visible.length === 0) {
      showMessage("No jobs match the current filter - nothing to generate.", "error");
      return;
    }
    resetModal();
    listEl.innerHTML = "";
    for (const job of visible) {
      const li = document.createElement("li");
      li.textContent = job.company ? `${job.name} - ${job.company}` : job.name;
      listEl.appendChild(li);
    }
    const already = visible.filter((j) => j.resume_generated_at).length;
    countEl.textContent =
      `This will generate a resume + cover letter for ${visible.length} job${visible.length === 1 ? "" : "s"}` +
      (already ? `, overwriting ${already} that already ${already === 1 ? "has" : "have"} one.` : ".");
    modal.classList.remove("hidden");
  });

  closeBtn.addEventListener("click", closeModal);
  cancelBtn.addEventListener("click", closeModal);

  async function pollBulkStatus(batchId) {
    let status;
    try {
      status = await fetchJSON(`/api/jobs/generate-resumes-bulk/${batchId}`);
    } catch (err) {
      showMessage(err.message, "error");
      return;
    }

    const pct = status.total ? Math.round((status.done / status.total) * 100) : 0;
    progressFill.style.width = `${pct}%`;
    progressText.textContent = `${status.done} of ${status.total} done`;
    resultsEl.innerHTML = "";
    for (const r of status.results) {
      const li = document.createElement("li");
      li.className = r.ok ? "bulk-resume-result-ok" : "bulk-resume-result-error";
      li.textContent = r.ok ? `✓ ${r.name}` : `✗ ${r.name}: ${r.error}`;
      resultsEl.appendChild(li);
    }

    if (status.status === "done") {
      confirmBtn.textContent = "Done";
      cancelBtn.textContent = "Close";
      cancelBtn.classList.remove("hidden");
      loadJobs();
    } else {
      setTimeout(() => pollBulkStatus(batchId), 2000);
    }
  }

  confirmBtn.addEventListener("click", async () => {
    const jobIds = visibleSortedJobs().map((j) => j.id);
    confirmBtn.disabled = true;
    confirmBtn.textContent = "Starting...";
    cancelBtn.classList.add("hidden");
    try {
      const { batch_id } = await fetchJSON("/api/jobs/generate-resumes-bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_ids: jobIds }),
      });
      progressEl.classList.remove("hidden");
      pollBulkStatus(batch_id);
    } catch (err) {
      showMessage(err.message, "error");
      closeModal();
    }
  });
}

initAddJobForm();
initImportJobs();
initJobFilters();
initBulkResumeGeneration();
loadPeople();
loadJobs();
