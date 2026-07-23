"use strict";
/* Weiss Schwarz card DB — static query app (NO BACKEND — everything runs in the browser).
 *
 * END-TO-END FLOW (see boot() below):
 *   1. fetch("ws.sqlite.gz")  — download the gzipped SQLite file that build_db.py produced.
 *   2. pako.inflate(...)      — gunzip the bytes to a raw SQLite image, in-browser (pako = a JS zlib).
 *   3. new SQL.Database(...)  — hand those bytes to sql.js (SQLite compiled to WebAssembly), which
 *                               holds the ENTIRE db in memory. No server, no network per query.
 *   4. query("SELECT …")      — every filter/search/detail view is just an in-memory SQL query.
 *
 * Both pako and sql.js are loaded from a CDN by <script> tags in index.html (see that file). The
 * data (~40k cards) lives entirely in RAM once loaded, so we paginate the render (never draw 40k
 * rows) and let SQLite's indexes do the filtering work.
 */

// Official card-image bases. EN images come straight from the dataset (cards.image_en); for JP-only
// cards we build the URL from the `picture` path stored in the DB. The app falls back to a
// placeholder <div> (via the <img onerror> in showDetail) if an image URL fails to load.
const IMG_BASE_JP = "https://ws-tcg.com/wordpress/wp-content/images/cardlist/";
let page = 0, pageSize = 100;   // pagination state: current 0-based page index + rows per page (0 = "all")

// $ = terse querySelector helper (optional 2nd arg = root to search within, defaults to document).
const $ = (s, r = document) => r.querySelector(s);
const status = $("#status");   // the header status line: shows "Loading…", the card counts, or an error
let db = null;   // the sql.js Database handle, populated by boot() once the .gz is fetched + inflated
// NEO_MAP: lowercased neo-standard name (EITHER the JP or the EN spelling) -> { codes:[set codes],
// en_only } for that deck-construction group. Built in initFilters(); lets the Title filter resolve a
// typed franchise name (in either language) to the exact set codes to match. See buildWhere().
let NEO_MAP = {};

const escHtml = s => (s == null ? "" : String(s).replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
// accent/case-insensitive search key: NFKD splits accents into base + combining mark; we drop the
// Latin combining marks (U+0300-036F) and lowercase. Japanese is preserved (dakuten U+3099/309A are
// outside that range). Mirrors fold() in build_db.py.
const fold = s => [...(s == null ? "" : String(s)).normalize("NFKD")]
  .filter(ch => ch.charCodeAt(0) < 0x300 || ch.charCodeAt(0) > 0x36f).join("").toLowerCase();

// query(): run one SQL statement against the in-memory sql.js db and return an array of plain row
// objects. sql.js has a cursor-style API: prepare -> bind params -> step() advances one row at a time
// -> getAsObject() reads the current row as {col: value}. free() releases the compiled statement
// (sql.js is WASM with manual memory management, so leaking statements would leak WASM heap).
function query(sql, params) {
  const stmt = db.prepare(sql);
  if (params) stmt.bind(params);   // params fill the "?" placeholders — parameterized, so no SQL injection
  const rows = [];
  while (stmt.step()) rows.push(stmt.getAsObject());   // step() returns false when rows are exhausted
  stmt.free();
  return rows;
}

// boot(): the app's entry point (called at the very bottom of this file). Loads the database and
// wires up the UI. Runs the two slow independent startup tasks in PARALLEL via Promise.all:
//   (a) initSqlJs — fetch + instantiate the sql.js WASM engine (locateFile tells it where the .wasm
//       binary lives on the CDN; the version in this URL must match the sql-wasm.js <script> in index.html).
//   (b) fetch the gzipped DB as an ArrayBuffer. The "?v=…" is a CONTENT-HASH cache-buster that
//       build_db.py stamps in automatically on every rebuild (see the cache-busting note in WEBAPP.md),
//       so browsers never serve a stale DB after the data changes.
async function boot() {
  try {
    const [SQL, gz] = await Promise.all([
      initSqlJs({ locateFile: f => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${f}` }),
      fetch("ws.sqlite.gz?v=bb4bd17f42").then(r => { if (!r.ok) throw new Error("ws.sqlite.gz " + r.status); return r.arrayBuffer(); }),
    ]);
    status.textContent = "Decompressing…";
    const bytes = pako.inflate(new Uint8Array(gz));   // gunzip: gz ArrayBuffer -> raw SQLite bytes (Uint8Array)
    db = new SQL.Database(bytes);                      // load the whole SQLite image into the in-memory engine
    // meta table = a tiny key/value row set of build stats (card/ability counts, validation %, note).
    // Fold it into a plain object so we can show a one-line summary in the header.
    const meta = {};
    query("SELECT key,value FROM meta").forEach(r => { meta[r.key] = r.value; });
    status.innerHTML = `${(+meta.cards).toLocaleString()} cards · ${(+meta.abilities).toLocaleString()} abilities ` +
      `· <span title="${escHtml(meta.note)}">cost model: ${escHtml(meta.validation)}</span>`;
    initFilters();          // populate the filter dropdowns from the data + attach all event listeners
    $("#app").hidden = false;   // reveal the UI (index.html starts it hidden until the DB is ready)
    run();                  // draw the first (unfiltered) page of results
  } catch (e) {
    // Any failure in the chain above (CDN unreachable, fetch 404, corrupt gz) lands here and is shown
    // to the user instead of a blank page. The most likely real-world cause is a CDN outage.
    status.className = "status err";
    status.textContent = "Could not load the database: " + e.message;
    console.error(e);
  }
}

// ---- filters ----
// fillSelect(): replace a <select>'s options with one <option> per value. `fmt` optionally maps a raw
// value to its display label. Every value passes through escHtml so data can't inject markup.
function fillSelect(id, values, fmt) {
  const sel = $(id);
  sel.innerHTML = values.map(v => `<option value="${escHtml(v)}">${escHtml(fmt ? fmt(v) : v)}</option>`).join("");
}
// distinct(): the sorted set of non-empty values a text column actually takes across all cards —
// used to populate a dropdown with exactly the choices that exist in the data (no hardcoded lists).
// NOTE: `col` is interpolated into SQL, so it must only ever be a trusted literal column name (it is).
function distinct(col) {
  return query(`SELECT DISTINCT ${col} v FROM cards WHERE ${col} IS NOT NULL AND ${col}<>'' ORDER BY ${col}`).map(r => r.v);
}
// initFilters(): runs once after the DB loads. Populates every dropdown from the data and attaches
// all the event listeners that drive the app (search input, filter changes, pagination, detail modal).
function initFilters() {
  fillSelect("#f-type", distinct("type"));
  fillSelect("#f-color", distinct("color"));
  fillSelect("#f-side", distinct("side"));
  // trigger is stored as a joined string per card ("soul", or "soul / soul" for a double trigger).
  // Split every card's value on " / " and collect the DISTINCT individual tokens for the dropdown.
  const trig = new Set();
  query("SELECT DISTINCT trigger v FROM cards WHERE trigger<>''").forEach(r =>
    r.v.split(" / ").forEach(t => t && trig.add(t)));
  fillSelect("#f-trigger", [...trig].sort());
  // numeric columns (level/cost/soul): distinct values in ascending numeric order for their dropdowns.
  const ints = c => query(`SELECT DISTINCT ${c} v FROM cards WHERE ${c} IS NOT NULL ORDER BY ${c}`).map(r => r.v);
  fillSelect("#f-level", ints("level"));
  fillSelect("#f-cost", ints("cost"));
  fillSelect("#f-soul", ints("soul"));

  // neo-standard autocomplete (the "Title" filter). A neo = an official deck-construction group with
  // its own set of series codes. We do TWO things from the neos table in one pass:
  //   1. Build NEO_MAP: index EACH name (both JP and EN spellings) -> its {codes, en_only}, so a user
  //      typing in either language resolves to the same set codes when buildWhere() runs.
  //   2. Build `items`: ONE display entry per neo (English preferred), de-duplicated by lowercased name.
  const items = [], seen = new Set();
  query("SELECT jp_name, en_name, codes, en_only FROM neos").forEach(n => {
    const v = { codes: (n.codes || "").split(" ").filter(Boolean), en_only: n.en_only };
    if (n.jp_name) NEO_MAP[n.jp_name.toLowerCase()] = v;       // typing the JP name resolves here
    if (n.en_name) NEO_MAP[n.en_name.toLowerCase()] = v;       // typing the EN name resolves here
    const disp = n.en_name || n.jp_name;                       // one visible name per neo (English preferred)
    if (disp && !seen.has(disp.toLowerCase())) { seen.add(disp.toLowerCase()); items.push({ v: disp, jp: n.jp_name || "" }); }
  });
  items.sort((a, b) => a.v.localeCompare(b.v));
  // Build a <datalist> so the #f-neo text input gets native autocomplete suggestions.
  // Firefox/Waterfox filter datalist options by the option's VISIBLE TEXT, not its value, so the
  // English title must be the option's VALUE with no extra label text — otherwise typing English
  // matches nothing in FF. JP search still works because it goes through NEO_MAP, not the datalist.
  const dl = document.createElement("datalist"); dl.id = "neo-list";
  dl.innerHTML = items.map(o => `<option value="${escHtml(o.v)}"></option>`).join("");
  document.body.appendChild(dl);
  $("#f-neo").setAttribute("list", "neo-list");

  // ---- event wiring (all delegated off #app so it survives dropdown re-population) ----
  const deb = debounce(run, 250);   // typing fires run() at most every 250ms (avoids a query per keystroke)
  // Text inputs (search box, numeric ranges, trait/title/series) re-run the query on every keystroke,
  // debounced. Selects change instantly (see below) so they are excluded here via the matches() guard.
  $("#app").addEventListener("input", e => { if (e.target.matches("input")) deb(); });
  // Any <select> change re-runs immediately — EXCEPT the page-size select, which has its own handler
  // (it must also update pageSize, not just re-query).
  $("#app").addEventListener("change", e => { if (e.target.matches("select") && e.target.id !== "page-size") run(); });
  $("#page-size").addEventListener("change", e => { pageSize = +e.target.value; run(); });
  // Pager buttons pass run(false) so the page index is NOT reset to 0 (a normal filter change resets it).
  $("#prev").addEventListener("click", () => { page -= 1; run(false); });
  $("#next").addEventListener("click", () => { page += 1; run(false); });
  // per-filter clear: the ✕ button next to each control. Delegated off #filters; data-clear names the
  // target control's id. Multi-selects clear by de-selecting every option; others clear their .value.
  $("#filters").addEventListener("click", e => {
    const b = e.target.closest(".clr"); if (!b) return;
    e.preventDefault();
    const el = document.getElementById(b.dataset.clear);
    if (el.multiple) Array.from(el.options).forEach(o => o.selected = false);
    else el.value = "";
    run();
  });
  // "Reset all filters": blank every input and de-select every option in one shot, then re-query.
  $("#reset").addEventListener("click", () => {
    $("#filters").querySelectorAll("input").forEach(i => i.value = "");
    $("#filters").querySelectorAll("select").forEach(s => [...s.options].forEach(o => o.selected = false));
    run();
  });
  // detail modal: close via its × button, via clicking the dark backdrop (target IS #detail itself,
  // not a child), or via the Escape key.
  $("#detail-close").addEventListener("click", closeDetail);
  $("#detail").addEventListener("click", e => { if (e.target.id === "detail") closeDetail(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeDetail(); });
}
// multi(): the array of selected values from a multi-select (empty array = no filter on that field).
const multi = id => Array.from($(id).selectedOptions).map(o => o.value);
// debounce(): wrap fn so rapid calls collapse into one call, ms after the last invocation. Each call
// clears the pending timer and starts a new one — classic trailing-edge debounce for the search box.
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// ---- build WHERE from filters ----
// buildWhere(): read the current state of every filter control and assemble ONE parameterized SQL
// WHERE clause. Returns { where, params } consumed by run(). Design rules:
//   - `w` = array of SQL fragments AND-ed together; `p` = the matching "?" bind values, in order.
//     Every fragment pushes its own placeholders, so w and p stay aligned positionally.
//   - values are ALWAYS bound as params (never string-concatenated) -> no SQL injection, and the
//     query plan is reusable.
//   - a control that is empty/unselected adds nothing, so an untouched filter simply doesn't constrain.
function buildWhere() {
  const w = [], p = [];
  // inClause: "col IN (?,?,…)" for a multi-select; skipped entirely when nothing is selected.
  const inClause = (col, vals) => { if (vals.length) { w.push(`${col} IN (${vals.map(() => "?").join(",")})`); p.push(...vals); } };

  // free-text search box: matches the folded name/title blob (accent- & case-insensitive) OR any card
  // whose ability text (EN or JP) contains the term. search_fold is the precomputed folded blob;
  // fold(q) applies the same NFKD accent-stripping to the query so "deja vu" matches "Déjà Vu".
  const q = $("#q").value.trim();
  if (q) {
    const like = "%" + q + "%";              // raw term, for the ability-text columns (kept as typed)
    const flike = "%" + fold(q) + "%";       // folded term, for the accent-insensitive name/title blob
    w.push(`(search_fold LIKE ?
            OR card_number IN (SELECT card_number FROM abilities WHERE en_text LIKE ? OR jp_text LIKE ?))`);
    p.push(flike, like, like);
  }
  // straightforward equality filters (multi-select -> IN list). Numeric ones map to Number first
  // because option values are strings and the columns are INTEGER.
  inClause("type", multi("#f-type"));
  inClause("color", multi("#f-color"));
  inClause("side", multi("#f-side"));
  inClause("level", multi("#f-level").map(Number));
  inClause("cost", multi("#f-cost").map(Number));
  inClause("soul", multi("#f-soul").map(Number));

  // trigger is stored joined ("soul / soul"), so an exact match won't do — LIKE each selected token
  // and OR them together (a card matches if it carries ANY of the chosen triggers).
  const trig = multi("#f-trigger");
  if (trig.length) { w.push("(" + trig.map(() => "trigger LIKE ?").join(" OR ") + ")"); p.push(...trig.map(t => "%" + t + "%")); }

  // printed-power numeric range (either bound optional).
  const pmin = $("#f-power-min").value, pmax = $("#f-power-max").value;
  if (pmin !== "") { w.push("power >= ?"); p.push(+pmin); }
  if (pmax !== "") { w.push("power <= ?"); p.push(+pmax); }

  // likeFld: substring match on a single text column (used for the free-text Series box).
  const likeFld = (id, col) => { const v = $(id).value.trim(); if (v) { w.push(`${col} LIKE ?`); p.push("%" + v + "%"); } };
  // trait: match either the JP traits column (魔法) OR the EN traits column (Magic), so either language works.
  const trv = $("#f-trait").value.trim();
  if (trv) { w.push("(traits LIKE ? OR traits_en LIKE ?)"); p.push("%" + trv + "%", "%" + trv + "%"); }
  // Title (Neo-Standard): if the typed text EXACTLY names a neo (via NEO_MAP, either language), filter
  // by that neo's precise set codes — much sharper than a text match. en_only disambiguates the edition:
  //   en_only === 2 -> the title spans JP cards + EN variants, so match the series codes alone.
  //   otherwise     -> also pin en_exclusive to the neo's edition flag (0 = JP-side, 1 = EN-exclusive),
  //                    so e.g. Cardcaptor Sakura JP and CCS-EN don't bleed into each other.
  // If the text is NOT an exact neo name (partial typing), fall back to a substring match on the hidden
  // title_search blob (JP name + kana + codes + EN franchise), lowercased.
  const neov = $("#f-neo").value.trim();
  if (neov) {
    const m = NEO_MAP[neov.toLowerCase()];
    if (m && m.codes.length) {
      const ph = m.codes.map(() => "?").join(",");
      if (m.en_only === 2) { w.push(`series IN (${ph})`); p.push(...m.codes); }
      else { w.push(`(series IN (${ph}) AND en_exclusive = ?)`); p.push(...m.codes, m.en_only); }
    } else { w.push("title_search LIKE ?"); p.push("%" + neov.toLowerCase() + "%"); }
  }
  likeFld("#f-series", "series");

  // ability power cost: keep cards that have AT LEAST ONE ability whose cost is in [min,max] and whose
  // confidence is among the selected ones. Expressed as a correlated subquery over the abilities table
  // (card_number IN (SELECT … WHERE <sub>)). We build the inner conditions in `sub`/`sp` first:
  //   - if only a confidence is picked (no range), still require power_cost IS NOT NULL so "n/a"
  //     abilities don't count as a match.
  const amin = $("#f-ac-min").value, amax = $("#f-ac-max").value, confs = multi("#f-conf");
  if (amin !== "" || amax !== "" || confs.length) {
    const sub = [], sp = [];
    if (amin !== "") { sub.push("power_cost >= ?"); sp.push(+amin); }
    if (amax !== "") { sub.push("power_cost <= ?"); sp.push(+amax); }
    if (amin === "" && amax === "") sub.push("power_cost IS NOT NULL");
    if (confs.length) { sub.push(`confidence IN (${confs.map(() => "?").join(",")})`); sp.push(...confs); }
    w.push(`card_number IN (SELECT card_number FROM abilities WHERE ${sub.join(" AND ")})`);
    p.push(...sp);
  }
  // no filters set -> empty WHERE (the query returns every card).
  return { where: w.length ? "WHERE " + w.join(" AND ") : "", params: p };
}

// ---- run query + render list ----
// run(): the core render cycle — rebuild the WHERE clause, count matches, fetch ONE page of rows, and
// paint the results table. Called on every filter/search change and on pagination.
//   reset: defaults to truthy -> jump back to page 0 (a filter changed). The pager buttons pass
//   `false` to keep the current page while stepping through it.
function run(reset) {
  if (reset !== false) page = 0;
  const { where, params } = buildWhere();
  // COUNT(*) first: needed for the page count and the "N cards" label. Uses the same where/params.
  const total = query(`SELECT COUNT(*) n FROM cards ${where}`, params)[0].n;
  const pages = pageSize === 0 ? 1 : Math.max(1, Math.ceil(total / pageSize));   // pageSize 0 = "all" on one page
  page = Math.min(Math.max(0, page), pages - 1);   // clamp: results may have shrunk below the old page index
  // LIMIT/OFFSET = the pagination window. We only ever fetch+render ONE page of rows (never all ~40k),
  // which is what keeps the render cheap even though the whole DB is in memory.
  const lim = pageSize === 0 ? "" : `LIMIT ${pageSize} OFFSET ${page * pageSize}`;
  const rows = query(
    `SELECT card_number,name,name_en,type,color,level,cost,power,soul,model_cost_total
     FROM cards ${where} ORDER BY series, card_number ${lim}`, params);
  $("#count").textContent = `${total.toLocaleString()} card${total === 1 ? "" : "s"}`;
  $("#pageinfo").textContent = total ? `page ${page + 1} / ${pages}` : "";
  $("#prev").disabled = page <= 0;              // grey out pager buttons at the ends
  $("#next").disabled = page >= pages - 1;
  const dot = c => `<span class="dot c-${escHtml(c)}"></span>`;   // the small colored circle before a color name
  // Build the whole tbody as one HTML string (one innerHTML write is far cheaper than per-row DOM ops).
  // Each <tr> carries data-cn=card_number so the click handler below knows which card to open.
  // Name cell shows EN on top and JP underneath only when BOTH exist. escHtml guards every field.
  $("#results tbody").innerHTML = rows.map(r => `
    <tr data-cn="${escHtml(r.card_number)}">
      <td>${escHtml(r.card_number)}</td>
      <td class="name"><span class="en">${escHtml(r.name_en || r.name || "")}</span>
        ${r.name_en && r.name ? `<br><span class="jp">${escHtml(r.name)}</span>` : ""}</td>
      <td>${escHtml(r.type)}</td>
      <td>${r.color ? dot(r.color) + escHtml(r.color) : ""}</td>
      <td>${r.level == null ? "" : r.level}</td><td>${r.cost == null ? "" : r.cost}</td>
      <td>${r.power == null ? "" : r.power}</td><td>${r.soul == null ? "" : r.soul}</td>
      <td class="cost-cell">${fmtCost(r.model_cost_total)}</td>
    </tr>`).join("");
  // Attach the row-click -> open detail modal. Delegating would also work, but the page is small (one
  // page of rows), so a listener per row is fine and keeps the handler trivially simple.
  $("#results tbody").querySelectorAll("tr").forEach(tr =>
    tr.addEventListener("click", () => showDetail(tr.dataset.cn)));
}

// fmtCost(): format a power cost for display, resolving its SIGN. The model stores cost as power
// SUBTRACTED from base, so a positive number is power PAID -> shown as "−N"; a negative number is a
// drawback that GIVES power back -> shown as "+N" (we print the sign ourselves, never a doubled "−−N");
// exactly 0 -> "0"; null (non-Character / no cost) -> an em dash.
function fmtCost(v) { return v == null ? "—" : v < 0 ? "+" + (-v) : v > 0 ? "−" + v : "0"; }

// ---- detail ----
// showDetail(): open the modal for one card. Pulls the full card row + all its abilities, then builds
// three sections: the header (image + stats chips), the power BUDGET breakdown, and the per-ability
// cost list. `cn` is the card_number captured from the clicked row's data-cn.
function showDetail(cn) {
  const c = query("SELECT * FROM cards WHERE card_number=?", [cn])[0];
  if (!c) return;   // defensive: row vanished (can't normally happen)
  const abs = query("SELECT * FROM abilities WHERE card_number=? ORDER BY idx", [cn]);   // idx = printed order
  // chip: a small "Key: value" pill, or nothing when the value is empty/null (so blank fields vanish).
  const chip = (k, v) => v == null || v === "" ? "" : `<span class="chip">${escHtml(k)}: ${escHtml(v)}</span>`;
  // image URL: prefer the official EN image; else build the JP image URL from the stored `picture` path.
  const imgUrl = c.image_en || (c.picture ? IMG_BASE_JP + c.picture : "");

  // --- power BUDGET breakdown. Only Characters get a cost model, signalled by a non-null power_base. ---
  let budget = "";
  if (c.power_base != null) {
    const residual = c.residual == null ? 0 : c.residual;
    const sgn = residual > 0 ? "+" : "";   // show an explicit "+" on positive residuals (negatives carry their own "−")
    // verdict line: residual = real budget − Σ standard costs = the designer's UNEXPLAINED adjustment.
    // is_suspect (|residual| ≥ 500) is the "off the standard rate" case; otherwise on-budget or a small tweak.
    const verdict = c.is_suspect
      ? `<span class="warn">designer adjustment <b>${sgn}${residual}</b> — over/under the standard rate</span>`
      : residual === 0
        ? `<span class="ok">on-budget — every effect priced at its standard</span>`
        : `<span class="ok">designer adjustment <b>${sgn}${residual}</b> (within ±500)</span>`;
    // The narrative: vanilla base power -> what the effects actually spend (real_delta) -> printed power;
    // then how much of that spend the standard costs explain, leaving the residual as the designer's call.
    budget = `<div class="budget">
      ${c.is_suspect ? `<span class="badge-suspect" title="|residual| ≥ 500: spent off the standard rate">SUSPECT</span> ` : ""}
      Vanilla <b>power_base ${c.power_base}</b>
      → effects actually spend <b>${fmtCost(c.real_delta)}</b> → printed power ${c.power}.<br>
      Of that, <b>${fmtCost(c.model_cost_total || 0)}</b> is explained by standard effect costs;
      the rest is the designer's adjustment → <b class="residual">residual ${sgn}${residual}</b>.<br>${verdict}</div>`;
  } else {
    budget = `<div class="budget"><span class="na">The power-cost model applies to Characters only.</span></div>`;
  }

  // --- per-ability list: one card per ability, showing its type/family, cost, evidence, and text. ---
  const abHtml = abs.map(a => {
    // Headline cost = the package's STANDARD cost (what this effect "should" cost across all cards).
    // Fall back to this card's own power_cost when no pooled standard was derived.
    const std = a.standard_cost != null ? a.standard_cost : a.power_cost;
    // Evidence badges (sample count, mode share, method) explain HOW confident that standard is; they
    // only make sense when there IS a cost, so skip them for n/a rows (e.g. non-Character abilities).
    const ev = [];
    if (std != null) {
      if (a.n_samples) ev.push(`${a.n_samples} sample${a.n_samples === 1 ? "" : "s"}`);
      if (a.mode_share != null) ev.push(`${Math.round(a.mode_share)}% mode`);
      if (a.method) ev.push(a.method);
    }
    const evTitle = ev.length ? ` title="${escHtml(ev.join(" · "))}"` : "";   // hover tooltip on the cost figure
    return `
    <div class="ab">
      <div class="ab-top">
        <span><span class="ab-type">${escHtml(a.ability_type)}</span>
          <span class="fam">${escHtml(a.family || "")}</span></span>
        <span class="ab-cost"${evTitle}>${std == null ? '<span class="na">n/a</span>'
          : fmtCost(std)}${a.confidence ? `<span class="conf ${a.confidence}">${a.confidence}</span>` : ""}</span>
      </div>
      ${ev.length ? `<div class="ab-evidence">standard cost · ${escHtml(ev.join(" · "))}</div>` : ""}
      <div class="txt">${escHtml(a.en_text || "") || '<span class="na">(no English text)</span>'}</div>
      ${a.jp_text ? `<div class="jp">${escHtml(a.jp_text)}</div>` : ""}
    </div>`;
  }).join("") || `<p class="na">No abilities.</p>`;   // fall back to a note when the card has no abilities

  // Assemble the full modal body: header (image + title + two stat-chip lines), the budget block,
  // the optional full official-EN text, then the abilities list. The <img onerror> swaps a broken
  // image URL for an inline "image not available" placeholder <div> without another round-trip.
  $("#detail-body").innerHTML = `
    <div class="d-head">
      ${imgUrl
        ? `<img class="d-img${c.type === 'Climax' ? ' climax' : ''}" src="${escHtml(imgUrl)}" alt=""
             onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'d-img placeholder',textContent:'image not available'}))">`
        : `<div class="d-img placeholder">no image</div>`}
      <div>
        <p class="d-title">${escHtml(c.name_en || c.name || c.card_number)}</p>
        <p class="d-sub">${escHtml(c.card_number)}${c.name_en && c.name ? " · " + escHtml(c.name) : ""}</p>
        <div class="statline">
          ${chip("Type", c.type)}${chip("Color", c.color)}${chip("Side", c.side)}
          ${chip("Level", c.level)}${chip("Cost", c.cost)}${chip("Power", c.power)}
          ${chip("Soul", c.soul)}${chip("Trigger", c.trigger)}${chip("Rare", c.rare)}
          ${chip("Released", c.release_date)}${chip("Era", c.era)}
        </div>
        <div class="statline">
          ${chip("Series", c.series)}${chip("Title", c.neo_titles)}
          ${chip("Traits", c.traits)}${chip("Traits (EN)", c.traits_en)}
        </div>
      </div>
    </div>
    ${budget}
    ${c.text_en ? `<div class="text-en"><b>Official English (full card text):</b><br>${escHtml(c.text_en)}</div>` : ""}
    <div class="abilities">${abHtml}</div>`;
  $("#detail").hidden = false;   // reveal the overlay (CSS .detail is display:flex; [hidden] wins to hide it)
}
// closeDetail(): just re-hide the overlay. Wired to the × button, backdrop click and Escape in initFilters().
function closeDetail() { $("#detail").hidden = true; }

boot();   // kick everything off (top-level: runs as soon as this script executes)
