(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = { status: null, cases: [], runs: [], report: null, tab: "findings", running: false, poll: null, request: 0 };
  const icons = {
    chevron: '<svg class="chevron" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m4 6 4 4 4-4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    change: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 6h11m-3-3 3 3-3 3M16 14H5m3-3-3 3 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    warning: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m10 3 8 14H2L10 3Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M10 8v4m0 2v.1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    check: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5 10 3.5 3.5L15 7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    evidence: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M5 3h7l4 4v10H5V3Zm7 0v5h4M8 11h5m-5 3h4" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
    info: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.4"/><path d="M10 9v5m0-8v.1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    error: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.4"/><path d="m7.5 7.5 5 5m0-5-5 5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    clock: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.4"/><path d="M10 6v4l3 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>'
  };
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const json = (value) => typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "Not captured";
  const list = (value) => Array.isArray(value) ? value : value ? [value] : [];
  const titleCase = (value) => String(value ?? "").replace(/[_-]/g, " ").replace(/^./, (c) => c.toUpperCase());
  const count = (value) => Array.isArray(value) ? value.length : (typeof value === "number" ? value : value === true ? 1 : 0);
  const safeUrl = (value) => { try { const url = new URL(String(value), location.origin); return ["https:", "http:"].includes(url.protocol) ? esc(url.href) : ""; } catch { return ""; } };
  const date = (value, short = false) => { if (!value) return "Time unavailable"; const parsed = new Date(value); return Number.isNaN(parsed.valueOf()) ? String(value) : parsed.toLocaleString(undefined, short ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" } : { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" }); };
  const packageVersion = (manifest, name) => { const packages = manifest?.packages ?? manifest?.versions ?? {}; if (Array.isArray(packages)) { const entry = packages.find((p) => p.name === name); return entry?.version ?? "—"; } return packages[name] ?? manifest?.[name] ?? "—"; };
  const pythonVersion = (manifest) => String(manifest?.python ?? manifest?.python_version ?? "Unavailable").split("\n")[0];
  const getSummary = (report) => report?.summary ?? {};
  const isActive = (status) => ["queued", "running", "pending", "created", "executing", "preparing"].includes(String(status).toLowerCase());
  const typeIs = (finding, text) => String(finding.type ?? "").includes(text);
  const accepted = (finding) => Boolean(finding.accepted);
  const pill = (label, color = "") => `<span class="pill ${esc(color)}">${esc(label)}</span>`;
  const codeBlock = (code, extra = "") => `<pre class="code-block ${extra}"><code>${esc(json(code))}</code></pre>`;
  const empty = (title, description) => `<div class="empty-panel"><strong>${esc(title)}</strong>${esc(description)}</div>`;
  const announce = (message) => { $("live-status").textContent = message; };
  const eventText = (event) => {
    if (typeof event === "string") return event;
    if (event.message || event.description) return event.message ?? event.description;
    const detail = event.payload?.environment ?? event.payload?.probe_id;
    return `${titleCase(event.kind ?? event.status ?? "Recorded event")}${detail ? ` · ${detail}` : ""}`;
  };

  async function api(path, options = {}) {
    const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers ?? {}) }, ...options });
    let body;
    try { body = await response.json(); } catch { body = null; }
    if (!response.ok) { const detail = body?.detail ?? body?.error ?? `Request failed (${response.status})`; throw new Error(typeof detail === "string" ? detail : json(detail)); }
    if (body === null) throw new Error("The local API returned an unreadable response.");
    return body;
  }

  function showError(message, retry = false) {
    $("app-alert").innerHTML = `${icons.error}<span>${esc(message)}</span>${retry ? '<button class="button secondary" id="retry-load">Retry connection</button>' : ""}`;
    $("app-alert").hidden = false;
    $("retry-load")?.addEventListener("click", initialize);
  }

  function renderStatus() {
    const status = state.status ?? {};
    const before = status.environments?.before ?? {};
    const after = status.environments?.after ?? {};
    $("before-version").textContent = packageVersion(before, "pandas");
    $("after-version").textContent = packageVersion(after, "pandas");
    $("before-python").textContent = `Python ${pythonVersion(before)}`;
    $("after-python").textContent = `Python ${pythonVersion(after)}`;
    $("mode-label").innerHTML = `<span class="status-dot"></span>${esc(status.mode === "trusted-fixtures" || status.mode === "trusted_fixtures" ? "Trusted examples only" : titleCase(status.mode ?? "Local mode"))}`;
    $("provider-label").textContent = status.provider === "deterministic-rules" || status.provider === "deterministic_rules" ? "Deterministic rules · No model calls" : `Provider: ${status.provider ?? "Not disclosed"}`;
    $("upload-reason").textContent = status.upload_reason ?? "Arbitrary uploads are disabled. Only reviewed repository examples can run until execution isolation is available.";
    const corpus = status.corpus ?? {};
    const documents = corpus.source_count ?? corpus.documents ?? corpus.document_count ?? corpus.count;
    $("corpus-summary").textContent = documents !== undefined ? `${Array.isArray(documents) ? documents.length : documents} evidence sources` : "";
  }

  function renderCases() {
    const previous = $("case-select").value;
    const groups = new Map();
    state.cases.forEach((entry) => { const category = titleCase(entry.category ?? "Repository examples"); if (!groups.has(category)) groups.set(category, []); groups.get(category).push(entry); });
    $("case-select").innerHTML = state.cases.length ? [...groups].map(([category, entries]) => `<optgroup label="${esc(category)}">${entries.map((entry) => `<option value="${esc(entry.id)}">${esc(entry.title)}</option>`).join("")}</optgroup>`).join("") : '<option value="">No reviewed examples available</option>';
    if (state.cases.some((entry) => entry.id === previous)) $("case-select").value = previous;
    $("case-select").disabled = !state.cases.length || state.running;
    $("run-button").disabled = !state.cases.length || !state.status || state.running;
    renderCaseDescription();
  }

  function renderCaseDescription() {
    const entry = state.cases.find((item) => item.id === $("case-select").value);
    $("case-description").textContent = entry?.description ?? "Choose a reviewed repository transformation to compare identical inputs in both environments.";
  }

  function runState(run) {
    const summary = getSummary(run);
    if (isActive(run.status)) return { color: "blue", label: titleCase(run.status), dot: "" };
    if (count(summary.errors) || ["failed", "error"].includes(run.status)) return { color: "red", label: "Execution error", dot: "red" };
    if (count(summary.insufficient_evidence)) return { color: "blue", label: "Insufficient evidence", dot: "" };
    if (summary.equivalent === true) return { color: "teal", label: "Equivalent outputs", dot: "teal" };
    if (count(summary.accepted) && summary.unaccepted_changes === 0) return { color: "teal", label: "Accepted intended change", dot: "teal" };
    if (count(summary.observed_differences)) return { color: "amber", label: `${count(summary.observed_differences)} observed ${count(summary.observed_differences) === 1 ? "difference" : "differences"}`, dot: "amber" };
    if (count(summary.expected_changes)) return { color: "teal", label: "Expected change", dot: "teal" };
    return { color: "", label: titleCase(run.status ?? "Recorded"), dot: "" };
  }

  function renderHistory() {
    $("history-count").textContent = state.runs.length;
    $("sidebar-runs").innerHTML = state.runs.length ? state.runs.slice(0, 5).map((run) => { const label = runState(run); return `<button class="recent-run ${state.report?.id === run.id ? "selected" : ""}" data-run="${esc(run.id)}" title="${esc(run.title)}"><span class="run-dot ${label.dot}"></span><span><span class="recent-title">${esc(run.title ?? run.case_id)}</span><span class="recent-subtitle">${esc(label.label)}</span></span></button>`; }).join("") : '<p class="muted tiny">Your runs will appear here.</p>';
    $("history-list").innerHTML = state.runs.length ? state.runs.slice(0, 8).map((run) => { const label = runState(run); return `<button class="history-row ${state.report?.id === run.id ? "selected" : ""}" data-run="${esc(run.id)}"><span class="history-icon">${icons.change}</span><span><span class="history-title">${esc(run.title ?? run.case_id)}</span><span class="history-detail">${esc(run.case_id)} · ${esc(String(run.id).slice(0, 8))}</span></span>${pill(label.label, label.color)}<span class="history-time">${esc(date(run.created_at, true))}</span>${icons.chevron}</button>`; }).join("") : '<p class="loading-copy">No previous runs. Select an example to start your first preflight.</p>';
    document.querySelectorAll("[data-run]").forEach((button) => button.addEventListener("click", () => selectRun(button.dataset.run, true)));
  }

  function renderSummary(report) {
    const summary = getSummary(report);
    const metrics = [
      { value: count(summary.observed_differences), label: "Observed differences", description: "Executed output changes", tone: count(summary.observed_differences) ? "amber" : "", icon: "change" },
      { value: count(summary.contract_violations), label: "Contract violations", description: "Against declared expectations", tone: count(summary.contract_violations) ? "red" : "", icon: "warning" },
      { value: count(summary.expected_changes), label: "Expected changes", description: "Documented migration behavior", tone: count(summary.expected_changes) ? "teal" : "", icon: "check" },
      { value: count(summary.errors), label: "Execution errors", description: "Environment or probe failures", tone: count(summary.errors) ? "red" : "", icon: "clock" }
    ];
    $("summary-grid").innerHTML = metrics.map((metric) => `<div class="summary-card ${metric.tone}"><div class="summary-card-icon">${icons[metric.icon]}</div><div class="summary-number">${metric.value}</div><div class="summary-label">${metric.label}</div><div class="summary-description">${metric.description}</div></div>`).join("");
    const notices = [];
    if (count(summary.insufficient_evidence)) notices.push(`<div class="notice info-notice">${icons.info}<span><strong>${count(summary.insufficient_evidence)} insufficient-evidence ${count(summary.insufficient_evidence) === 1 ? "finding" : "findings"}.</strong> The available execution or documentation cannot support a definitive conclusion.</span></div>`);
    if (list(report.findings).some((finding) => finding.rule === "determinism")) notices.push(`<div class="notice warning-notice">${icons.warning}<span><strong>Repeatability check failed.</strong> Outputs varied across repeated execution. Review stochastic behavior before attributing a difference to the upgrade.</span></div>`);
    if (count(summary.errors)) notices.push(`<div class="notice error-notice">${icons.error}<span><strong>Execution is incomplete.</strong> Environment or probe failures are recorded separately from observed semantic changes.</span></div>`);
    $("report-notice").innerHTML = notices.join("");
    $("report-notice").hidden = !notices.length;
  }

  function evidenceLink(evidence) {
    const url = safeUrl(evidence.url ?? evidence.source_url);
    const title = evidence.title ?? evidence.source_title ?? "Documentation source";
    return url ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${esc(title)} ↗</a>` : esc(title);
  }

  function renderFinding(finding, index, report) {
    const isError = typeIs(finding, "error") || typeIs(finding, "failure");
    const isInsufficient = typeIs(finding, "insufficient");
    const isAccepted = accepted(finding);
    const evidence = list(finding.evidence);
    const before = packageVersion(report.environments?.before, "pandas");
    const after = packageVersion(report.environments?.after, "pandas");
    const labels = [pill(titleCase(finding.type ?? "Observed change"), isError ? "red" : isInsufficient ? "blue" : "amber")];
    if (isAccepted) labels.push(pill("Accepted as intended", "teal"));
    if (finding.probe_id) labels.push(pill(`Probe ${finding.probe_id}`));
    const acceptance = typeof finding.accepted === "object" ? finding.accepted : {};
    const acceptanceReason = acceptance.reason ?? finding.acceptance_reason ?? finding.accepted_reason ?? finding.reason;
    const acceptanceDate = acceptance.accepted_at ?? acceptance.at ?? finding.accepted_at;
    const affected = typeof finding.location === "object" && finding.location ? `${finding.location.path ?? "Source"}${finding.location.line ? `:${finding.location.line}` : ""}` : finding.location;
    const canAccept = !isAccepted && !isError && !isInsufficient;
    return `<details class="finding ${isError ? "finding-error" : ""} ${isAccepted ? "finding-accepted" : ""}" ${index === 0 ? "open" : ""}>
      <summary class="finding-summary"><span class="finding-type-icon">${icons[isAccepted ? "check" : isError ? "error" : isInsufficient ? "info" : "change"]}</span><span class="finding-title-wrap"><span class="finding-title">${esc(finding.title ?? titleCase(finding.type))}</span><span class="finding-labels">${labels.join("")}${affected ? `<span class="finding-location">${esc(affected)}</span>` : ""}</span></span>${icons.chevron}</summary>
      <div class="finding-body"><p class="finding-description">${esc(finding.description ?? "")}</p>
      <div class="finding-compare"><div class="output-box"><div class="output-box-header"><strong>BEFORE</strong><span>pandas ${esc(before)}</span></div><pre><code>${esc(json(finding.before))}</code></pre></div><div class="output-box after"><div class="output-box-header"><strong>AFTER</strong><span>pandas ${esc(after)}</span></div><pre><code>${esc(json(finding.after))}</code></pre></div></div>
      ${finding.rule ? `<div class="finding-rule"><strong>Comparison rule</strong><code>${esc(typeof finding.rule === "object" ? json(finding.rule) : finding.rule)}</code></div>` : ""}
      ${finding.impact ? `<div class="impact-note">${icons.info}<p><strong>Potential impact:</strong> ${esc(finding.impact)}</p></div>` : ""}
      ${evidence.slice(0, 2).map((item) => `<div class="evidence-inline">${icons.evidence}<div><div class="evidence-inline-title">${evidenceLink(item)}</div>${item.passage ? `<p>${esc(String(item.passage).length > 270 ? String(item.passage).slice(0, 270) + "…" : item.passage)}</p>` : ""}</div>${item.source_version || item.version_scope ? `<span class="evidence-inline-version">${esc(item.source_version ?? item.version_scope)}</span>` : ""}</div>`).join("")}
      ${finding.affected_code ? `<details class="finding-patch"><summary>Affected code${affected ? ` · ${esc(affected)}` : ""}</summary><pre><code>${esc(finding.affected_code)}</code></pre></details>` : ""}
      ${isAccepted ? `<div class="accepted-audit"><div class="accepted-note">${icons.check}<span><strong>Accepted as an intentional change.</strong> This finding remains in the audit record.${acceptanceDate ? ` Reviewed ${esc(date(acceptanceDate))}.` : ""}${acceptanceReason ? `<br>${esc(acceptanceReason)}` : ""}</span></div></div>` : ""}
      <div class="finding-actions"><details class="reproduce-details"><summary>View reproducible command</summary><pre><code>${esc(finding.reproduce ?? report.reproduce ?? "No reproducible command was recorded for this finding.")}</code></pre></details>${canAccept ? `<button class="button quiet accept-toggle" data-finding-index="${index}">${icons.check}Accept intended change</button>` : `<span class="tiny muted">${isAccepted ? "Audit retained" : "Review execution & evidence"}</span>`}</div>
      ${canAccept ? `<form class="accept-box" data-accept-index="${index}" hidden><label for="accept-reason-${index}">Why is this change intended?</label><textarea id="accept-reason-${index}" name="reason" required minlength="3" maxlength="2000" placeholder="Record the expectation and why the new behavior is acceptable."></textarea><div class="accept-form-buttons"><span class="accept-error" role="alert"></span><button type="button" class="button secondary cancel-accept">Cancel</button><button type="submit" class="button primary">Save review</button></div></form>` : ""}
      </div></details>`;
  }

  function renderFindings(report) {
    const findings = list(report.findings);
    const summary = getSummary(report);
    $("finding-count").textContent = findings.length;
    if (!findings.length) {
      $("panel-findings").innerHTML = summary.equivalent === true ? `<div class="equivalent-state"><span class="equivalent-icon">${icons.check}</span><div><h3>No observed differences in this fixture.</h3><p>The transformation produced equivalent normalized outputs in both environments under the declared comparison rules.</p><p class="subtle-note">This result applies to the executed fixture and probes. Review broader inputs before changing a production dependency.</p></div></div>` : empty("No findings recorded", isActive(report.status) ? "This preflight is still in progress." : "The report does not include enough findings to infer output equivalence.");
      return;
    }
    const heading = count(summary.observed_differences) ? "What changed in execution" : count(summary.errors) ? "Execution needs attention" : "Evidence needs review";
    const introduction = count(summary.observed_differences) ? "Review the output, supporting source, and impact for each finding." : "Review incomplete results and uncertainty before drawing an upgrade conclusion.";
    $("panel-findings").innerHTML = `<div class="panel-intro"><div><h3>${heading}</h3><p>${introduction}</p></div><span class="legend"><span></span> Findings require review</span></div>${findings.map((finding, index) => renderFinding(finding, index, report)).join("")}`;
    document.querySelectorAll(".accept-toggle").forEach((button) => button.addEventListener("click", () => { const form = document.querySelector(`[data-accept-index="${button.dataset.findingIndex}"]`); form.hidden = !form.hidden; if (!form.hidden) form.querySelector("textarea").focus(); }));
    document.querySelectorAll(".cancel-accept").forEach((button) => button.addEventListener("click", () => { const form = button.closest("form"); form.hidden = true; document.querySelector(`[data-finding-index="${form.dataset.acceptIndex}"]`)?.focus(); }));
    document.querySelectorAll("[data-accept-index]").forEach((form) => form.addEventListener("submit", (event) => acceptFinding(event, findings[Number(form.dataset.acceptIndex)])));
  }

  function renderManifest(manifest) {
    if (!manifest || !Object.keys(manifest).length) return '<p class="muted tiny">Environment manifest unavailable.</p>';
    const packages = manifest.packages ?? manifest.versions ?? {};
    const rows = Array.isArray(packages) ? packages.map((p) => [p.name, p.version]) : Object.entries(packages);
    const selected = rows.filter(([name]) => ["pandas", "numpy", "python-dateutil", "pytz", "tzdata"].includes(String(name))).slice(0, 8);
    return `<table class="package-table"><tbody><tr><td>Python</td><td>${esc(pythonVersion(manifest))}</td></tr>${selected.map(([name, version]) => `<tr><td>${esc(name)}</td><td>${esc(version)}</td></tr>`).join("")}</tbody></table><details class="manifest-details"><summary>Full resolved manifest</summary>${codeBlock(manifest)}</details>`;
  }

  function renderFrame(frame) {
    if (!frame) return '<p class="muted tiny execution-empty">No structured output captured.</p>';
    if (!Array.isArray(frame.columns) || !Array.isArray(frame.data)) return codeBlock(frame);
    const columns = frame.columns;
    if (!columns.length) return `<div class="dataframe-empty"><strong>No feature columns selected</strong><span>${esc(frame.row_count ?? frame.data.length)} rows · 0 columns</span></div>`;
    return `<div class="dataframe-wrap"><table class="dataframe"><thead><tr>${columns.map((column) => `<th scope="col">${esc(column.name ?? column)}<small>${esc(column.dtype ?? "")}</small></th>`).join("")}</tr></thead><tbody>${frame.data.slice(0, 12).map((row) => `<tr>${list(row).map((value) => `<td>${value && typeof value === "object" && value.$null ? `<span class="null-value">${esc(value.$null)}</span>` : esc(typeof value === "object" ? json(value) : value)}</td>`).join("")}</tr>`).join("")}</tbody></table></div><p class="dataframe-caption">${esc(frame.row_count ?? frame.data.length)} rows · ${columns.length} columns${frame.data.length > 12 ? " · Previewing first 12 rows; complete data in process record" : ""}</p>`;
  }

  function renderExecution(report) {
    const sides = ["before", "after"];
    const executions = report.executions ?? {};
    const environments = sides.map((side) => {
      const records = list(executions[side]);
      const runs = records.map((record, i) => {
        const exitCode = record.exit_code ?? record.returncode;
        const duration = record.duration_seconds ?? record.duration_s ?? record.duration;
        return `<details class="execution-record" ${i === 0 ? "open" : ""}><summary>${esc(record.label ?? record.probe_id ?? record.id ?? `Execution ${i + 1}`)}<span>${exitCode !== undefined ? `exit ${esc(exitCode)}` : esc(record.status ?? "captured")}${typeof duration === "number" ? ` · ${duration.toFixed(3)}s` : ""}</span></summary>${renderFrame(record.output)}<details class="manifest-details"><summary>Process record, stdout &amp; stderr</summary>${codeBlock(record)}</details></details>`;
      }).join("");
      return `<section class="environment-card"><div class="environment-header"><h3>${side === "before" ? "Current" : "Target"} environment</h3>${pill(`pandas ${packageVersion(report.environments?.[side], "pandas")}`, side === "after" ? "teal" : "")}</div><div class="environment-card-content">${renderManifest(report.environments?.[side])}${runs || '<p class="muted tiny">No execution records captured.</p>'}</div></section>`;
    }).join("");
    const tests = sides.filter((side) => report.existing_tests?.[side]).map((side) => {
      const test = report.existing_tests[side];
      return `<details class="probe-card"><summary><span>${side === "before" ? "Current" : "Target"} environment · Existing test</span>${pill(test.test_passed === true ? "Passed" : test.test_passed === false ? "Failed" : titleCase(test.status), test.test_passed === true ? "teal" : test.test_passed === false ? "red" : "")}</summary><div class="probe-body">${codeBlock(test)}</div></details>`;
    }).join("");
    const events = list(report.events).map((event) => `<li><time>${esc(event.created_at || event.at || event.timestamp ? date(event.created_at ?? event.at ?? event.timestamp, true) : "")}</time><span>${esc(eventText(event))}</span></li>`).join("");
    $("panel-execution").innerHTML = `<div class="panel-intro"><div><h3>Execution record</h3><p>Exact environments, repeat runs, process results, and captured output.</p></div>${pill(state.status?.mode === "trusted-fixtures" ? "Trusted subprocesses" : "Local execution")}</div><div class="execution-grid">${environments}</div>${tests ? `<h3 class="section-subheading">Existing-test baseline</h3>${tests}` : ""}${events ? `<h3 class="section-subheading">Run timeline</h3><ol class="event-log">${events}</ol>` : ""}`;
  }

  function collectEvidence(report) {
    const seen = new Set();
    return [...list(report.evidence), ...list(report.findings).flatMap((finding) => list(finding.evidence))].filter((evidence) => { const key = `${evidence.url}|${evidence.source_version}|${evidence.passage}`; if (seen.has(key)) return false; seen.add(key); return true; });
  }

  function renderEvidence(report) {
    const evidence = collectEvidence(report);
    $("panel-evidence").innerHTML = `<div class="panel-intro"><div><h3>Version-scoped evidence</h3><p>Sources retained with the report. Runtime observations and documentation are distinct evidence.</p></div>${pill(`${evidence.length} ${evidence.length === 1 ? "source" : "sources"}`)}</div>${evidence.length ? evidence.map((item) => `<article class="evidence-card"><div class="evidence-card-head"><h3>${evidenceLink(item)}</h3>${pill(item.source_version ?? item.version_scope ?? "Version not disclosed", item.source_version || item.version_scope ? "teal" : "blue")}</div><div class="evidence-url">${esc(item.url ?? item.source_url ?? "Source URL unavailable")}</div>${item.passage ? `<blockquote class="evidence-passage">${esc(item.passage)}</blockquote>` : '<p class="muted tiny">No cached passage included in this finding.</p>'}<div class="evidence-meta">${item.fetched_at ? `<span>Fetched ${esc(date(item.fetched_at))}</span>` : ""}${item.content_hash || item.sha256 ? `<span>SHA-256 <code>${esc(item.content_hash ?? item.sha256)}</code></span>` : ""}${item.passage_start !== undefined || item.offsets ? `<span>Passage offsets <code>${esc(item.offsets ? json(item.offsets) : `${item.passage_start}–${item.passage_end ?? "?"}`)}</code></span>` : ""}${item.conflict || item.version_match === false ? pill("Evidence conflict · Review required", "red") : ""}</div></article>`).join("") : empty("No supporting documentation recorded", "An unavailable or mismatched version source cannot support a definitive documentation claim.")}`;
    document.querySelectorAll("#panel-evidence .evidence-card").forEach((card, index) => {
      const item = evidence[index];
      const metadata = {
        source_version: item.source_version, applies_to: item.applies_to,
        source_commit: item.source_commit, fetched_at: item.fetched_at,
        content_hash: item.content_hash, passage_hash: item.passage_hash,
        passage_start: item.start ?? item.passage_start,
        passage_end: item.end ?? item.passage_end, offset_unit: item.offset_unit,
        source_validated: item.source_validated, supports_definitive: item.supports_definitive,
        conflict: item.conflict, conflict_reason: item.conflict_reason
      };
      card.insertAdjacentHTML("beforeend", `<details class="manifest-details"><summary>Source provenance &amp; passage offsets</summary>${codeBlock(metadata)}</details>`);
    });
  }

  function renderSource(report) {
    const source = report.source ?? {};
    const input = report.input ?? {};
    const probes = list(report.probes);
    const patches = list(report.patches);
    $("panel-source").innerHTML = `<div class="panel-intro"><div><h3>Transformation under review</h3><p>The same source and input are used for both environments.</p><div class="source-meta">${source.path ? pill(source.path) : ""}${source.entrypoint ? pill(`Entry point: ${source.entrypoint}`, "teal") : ""}</div></div></div>${source.code ? codeBlock(source.code, "source-code") : empty("Source unavailable", "No source snapshot is attached to this report.")}<div class="hash-details">${source.sha256 ? `<div><strong>Code SHA-256</strong> <code>${esc(source.sha256)}</code></div>` : ""}${input.path ? `<div><strong>Input fixture</strong> ${esc(input.path)}</div>` : ""}${input.sha256 ? `<div><strong>Input SHA-256</strong> <code>${esc(input.sha256)}</code></div>` : ""}</div><h3 class="section-subheading">Reviewable probes <span class="muted">(${probes.length})</span></h3>${probes.length ? probes.map((probe) => `<details class="probe-card"><summary><span>${esc(probe.title ?? probe.id)}</span>${pill(titleCase(probe.status ?? "Recorded"), ["passed", "validated", "completed"].includes(probe.status) ? "teal" : ["failed", "error", "timeout"].includes(probe.status) ? "red" : "")}</summary><div class="probe-body">${probe.reason ? `<p>${esc(probe.reason)}</p>` : ""}${codeBlock(probe.code ?? probe)}</div></details>`).join("") : '<p class="muted tiny">No generated probes recorded for this run.</p>'}${patches.length ? `<h3 class="section-subheading">Suggested patches · For review</h3>${patches.map((patch) => `<details class="probe-card patch-block"><summary><span>${esc(patch.title ?? "Suggested patch")}</span>${pill("Not applied")}</summary><div class="probe-body">${patch.description ? `<p>${esc(patch.description)}</p>` : ""}${codeBlock(patch.diff ?? patch.patch ?? patch)}</div></details>`).join("")}` : ""}`;
    if (report.configuration?.contract) {
      $("panel-source").insertAdjacentHTML("beforeend", `<h3 class="section-subheading">Declared output contract</h3><p class="muted tiny">These are the comparison tolerances, required outputs, and intentional changes used by this run.</p>${codeBlock(report.configuration.contract)}`);
    }
    document.querySelectorAll("#panel-source .probe-card:not(.patch-block)").forEach((card, index) => {
      const probe = probes[index];
      if (probe.validation || probe.executions || probe.syntax) card.querySelector(".probe-body").insertAdjacentHTML("beforeend", `<details class="manifest-details"><summary>Independent validation &amp; execution records</summary>${codeBlock({ syntax: probe.syntax, validation: probe.validation, executions: probe.executions })}</details>`);
    });
    document.querySelectorAll("#panel-source .patch-block").forEach((card, index) => {
      const patch = patches[index];
      const status = patch.fully_equivalent === true ? "Equivalent under the recorded comparison contract" : patch.fully_equivalent === false ? "Partial correction · Output differences remain" : "Patch equivalence has not been established";
      const tone = patch.fully_equivalent === true ? "info-notice" : "warning-notice";
      const body = card.querySelector(".probe-body");
      body.insertAdjacentHTML("afterbegin", `<div class="notice ${tone} patch-review-note">${icons.info}<span>${esc(status)}. Review the validation records before applying this suggestion.</span></div>${patch.justification && patch.justification !== patch.description ? `<p>${esc(patch.justification)}</p>` : ""}`);
      if (patch.remaining_differences || patch.validation) body.insertAdjacentHTML("beforeend", `<details class="manifest-details"><summary>Remaining differences &amp; patch validation</summary>${codeBlock({ fully_equivalent: patch.fully_equivalent, remaining_differences: patch.remaining_differences, validation: patch.validation })}</details>`);
    });
  }

  function renderReport(report) {
    state.report = report;
    $("report-section").hidden = false;
    $("empty-state").hidden = true;
    $("report-heading").textContent = report.title ?? report.case_id ?? "Preflight report";
    $("report-run-label").textContent = `RUN ${String(report.id).slice(0, 8)}`;
    const summary = getSummary(report);
    $("report-subtitle").textContent = `${date(report.created_at)} · ${titleCase(report.status ?? "Recorded")} · ${state.status?.provider === "deterministic-rules" ? "Deterministic rules" : state.status?.provider ?? "Local provider"}`;
    $("report-tabs-meta").innerHTML = summary.deterministic === true ? `<span class="status-dot"></span> ${count(summary.errors) ? "Captured output repeatable" : "Repeatable output"}` : summary.deterministic === false ? "Repeatability not established" : "";
    const prefix = `/api/runs/${encodeURIComponent(report.id)}`;
    $("download-options").innerHTML = `<a href="${prefix}/report.json" download>JSON report</a><a href="${prefix}/report.html" download>HTML report</a><a href="${prefix}/regression_test.py" download>Regression test · Python</a>`;
    renderSummary(report); renderFindings(report); renderExecution(report); renderEvidence(report); renderSource(report); renderHistory();
    setTab(state.tab, false);
  }

  function setTab(tab, focus = false) {
    if (!["findings", "execution", "evidence", "source"].includes(tab)) return;
    state.tab = tab;
    document.querySelectorAll("[data-tab]").forEach((button) => { const selected = button.dataset.tab === tab; button.classList.toggle("active", selected); button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1; $("panel-" + button.dataset.tab).hidden = !selected; });
    if (focus) $("tab-" + tab).focus();
  }

  async function selectRun(id, scroll = false) {
    const request = ++state.request;
    try {
      const report = await api(`/api/runs/${encodeURIComponent(id)}`);
      if (request !== state.request) return;
      renderReport(report);
      if (state.cases.some((entry) => entry.id === report.case_id)) { $("case-select").value = report.case_id; renderCaseDescription(); }
      if (scroll) $("report-section").scrollIntoView({ behavior: "smooth", block: "start" });
      if (isActive(report.status)) { setRunning(true); pollRun(id); }
    } catch (error) { showError(`Could not load this report. ${error.message}`); }
  }

  function setRunning(running) {
    state.running = running;
    $("run-progress").hidden = !running;
    $("run-button").disabled = running || !state.cases.length || !state.status;
    $("case-select").disabled = running || !state.cases.length;
    $("run-button").querySelector("span").textContent = running ? "Running preflight…" : "Run preflight";
    $("run-button").setAttribute("aria-busy", String(running));
  }

  async function refreshRuns() {
    const result = await api("/api/runs");
    state.runs = Array.isArray(result) ? result : result.runs ?? [];
    renderHistory();
  }

  async function pollRun(id) {
    clearTimeout(state.poll);
    try {
      const report = await api(`/api/runs/${encodeURIComponent(id)}`);
      const events = list(report.events);
      const latest = events[events.length - 1];
      $("progress-message").textContent = latest ? eventText(latest) : `${titleCase(report.status)} · Executing the selected repository example.`;
      if (isActive(report.status)) { state.poll = setTimeout(() => pollRun(id), 1000); return; }
      setRunning(false);
      renderReport(report);
      await refreshRuns();
      announce(`Preflight ${titleCase(report.status)}. ${count(report.summary?.observed_differences)} observed differences.`);
    } catch (error) {
      setRunning(false);
      showError(`The run status could not be retrieved. The saved run may still be processing. ${error.message}`);
      try { await refreshRuns(); } catch { /* Preserve the visible report if reconnect also fails. */ }
    }
  }

  async function runPreflight() {
    const caseId = $("case-select").value;
    if (!caseId || state.running) return;
    $("app-alert").hidden = true;
    setRunning(true);
    $("progress-message").textContent = "Submitting the selected reviewed example to the local worker…";
    announce("Preflight started.");
    try {
      const result = await api("/api/runs", { method: "POST", body: JSON.stringify({ case_id: caseId }) });
      if (!result.id) throw new Error("No run identifier was returned.");
      await pollRun(result.id);
    } catch (error) { setRunning(false); showError(`Could not start the preflight. ${error.message}`); }
  }

  async function acceptFinding(event, finding) {
    event.preventDefault();
    const form = event.currentTarget;
    const reason = form.querySelector("textarea").value.trim();
    if (reason.length < 3) { form.querySelector(".accept-error").textContent = "Add a short reason for the audit record."; return; }
    const button = form.querySelector('[type="submit"]');
    button.disabled = true; button.textContent = "Saving…";
    try {
      const result = await api(`/api/runs/${encodeURIComponent(state.report.id)}/accept`, { method: "POST", body: JSON.stringify({ finding_id: finding.id, reason }) });
      const report = result.report ?? result;
      renderReport(report);
      const findingIndex = list(report.findings).findIndex((entry) => entry.id === finding.id);
      document.querySelectorAll("#panel-findings .finding > summary")[findingIndex]?.focus();
      await refreshRuns();
      announce("The intended change was accepted. Its original finding and review reason remain in the audit record.");
    } catch (error) { form.querySelector(".accept-error").textContent = error.message; button.disabled = false; button.textContent = "Save review"; }
  }

  async function initialize() {
    $("app-alert").hidden = true;
    const results = await Promise.allSettled([api("/api/status"), api("/api/cases"), api("/api/runs")]);
    const failures = [];
    if (results[0].status === "fulfilled") { state.status = results[0].value; renderStatus(); } else { failures.push(`Environment status: ${results[0].reason.message}`); $("mode-label").textContent = "API unavailable"; $("provider-label").textContent = "Provider unavailable"; }
    if (results[1].status === "fulfilled") { const result = results[1].value; state.cases = Array.isArray(result) ? result : result.cases ?? []; } else failures.push(`Examples: ${results[1].reason.message}`);
    renderCases();
    if (results[2].status === "fulfilled") { const result = results[2].value; state.runs = Array.isArray(result) ? result : result.runs ?? []; } else failures.push(`Run history: ${results[2].reason.message}`);
    renderHistory();
    if (state.runs.length && !state.report) await selectRun(state.runs[0].id);
    if (!state.report) $("empty-state").hidden = false;
    if (failures.length) showError(`Some local data could not be loaded. ${failures.join(" · ")}`, true);
  }

  $("case-select").addEventListener("change", renderCaseDescription);
  $("run-button").addEventListener("click", runPreflight);
  $("nav-history").addEventListener("click", () => { $("history-section").scrollIntoView({ behavior: "smooth" }); $("history-list").querySelector("button")?.focus({ preventScroll: true }); });
  $("nav-evidence").addEventListener("click", () => { if (state.report) { setTab("evidence", true); $("report-section").scrollIntoView({ behavior: "smooth" }); } else { announce("Run a preflight to view version-scoped evidence in its report."); $("case-select").focus(); } });
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => setTab(button.dataset.tab));
    button.addEventListener("keydown", (event) => {
      const tabs = ["findings", "execution", "evidence", "source"];
      const index = tabs.indexOf(button.dataset.tab);
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); setTab(tabs[next], true); }
    });
  });
  document.addEventListener("click", (event) => { const menu = document.querySelector(".download-menu"); if (menu && !menu.contains(event.target)) menu.open = false; });
  initialize();
})();
