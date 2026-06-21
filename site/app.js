"use strict";
/* Weiss Schwarz card DB — static query app.
   Loads ws.sqlite.gz in the browser (pako -> sql.js) and queries it in memory. */

// Official card-image bases. EN images come straight from the dataset; for JP-only cards we
// build the URL from the `picture` path. TODO: confirm the JP base in a real browser; the app
// falls back to a placeholder if an image fails to load.
const IMG_BASE_JP = "https://ws-tcg.com/wordpress/wp-content/images/cardlist/";
let page = 0, pageSize = 100;   // pagination state

const $ = (s, r = document) => r.querySelector(s);
const status = $("#status");
let db = null;
let NEO_MAP = {};   // lowercased neo name (EN or JP) -> array of its set codes (deck-construction group)

const escHtml = s => (s == null ? "" : String(s).replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
// accent/case-insensitive search key: NFKD splits accents into base + combining mark; we drop the
// Latin combining marks (U+0300-036F) and lowercase. Japanese is preserved (dakuten U+3099/309A are
// outside that range). Mirrors fold() in build_db.py.
const fold = s => [...(s == null ? "" : String(s)).normalize("NFKD")]
  .filter(ch => ch.charCodeAt(0) < 0x300 || ch.charCodeAt(0) > 0x36f).join("").toLowerCase();

function query(sql, params) {
  const stmt = db.prepare(sql);
  if (params) stmt.bind(params);
  const rows = [];
  while (stmt.step()) rows.push(stmt.getAsObject());
  stmt.free();
  return rows;
}

async function boot() {
  try {
    const [SQL, gz] = await Promise.all([
      initSqlJs({ locateFile: f => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${f}` }),
      fetch("ws.sqlite.gz?v=d835e1333d").then(r => { if (!r.ok) throw new Error("ws.sqlite.gz " + r.status); return r.arrayBuffer(); }),
    ]);
    status.textContent = "Decompressing…";
    const bytes = pako.inflate(new Uint8Array(gz));
    db = new SQL.Database(bytes);
    const meta = {};
    query("SELECT key,value FROM meta").forEach(r => { meta[r.key] = r.value; });
    status.innerHTML = `${(+meta.cards).toLocaleString()} cards · ${(+meta.abilities).toLocaleString()} abilities ` +
      `· <span title="${escHtml(meta.note)}">cost model: ${escHtml(meta.validation)}</span>`;
    initFilters();
    $("#app").hidden = false;
    run();
  } catch (e) {
    status.className = "status err";
    status.textContent = "Could not load the database: " + e.message;
    console.error(e);
  }
}

// ---- filters ----
function fillSelect(id, values, fmt) {
  const sel = $(id);
  sel.innerHTML = values.map(v => `<option value="${escHtml(v)}">${escHtml(fmt ? fmt(v) : v)}</option>`).join("");
}
function distinct(col) {
  return query(`SELECT DISTINCT ${col} v FROM cards WHERE ${col} IS NOT NULL AND ${col}<>'' ORDER BY ${col}`).map(r => r.v);
}
function initFilters() {
  fillSelect("#f-type", distinct("type"));
  fillSelect("#f-color", distinct("color"));
  fillSelect("#f-side", distinct("side"));
  // trigger is stored joined ("soul" / "soul / soul"); split into distinct tokens
  const trig = new Set();
  query("SELECT DISTINCT trigger v FROM cards WHERE trigger<>''").forEach(r =>
    r.v.split(" / ").forEach(t => t && trig.add(t)));
  fillSelect("#f-trigger", [...trig].sort());
  const ints = c => query(`SELECT DISTINCT ${c} v FROM cards WHERE ${c} IS NOT NULL ORDER BY ${c}`).map(r => r.v);
  fillSelect("#f-level", ints("level"));
  fillSelect("#f-cost", ints("cost"));
  fillSelect("#f-soul", ints("soul"));

  // neo-standard autocomplete: ONE entry per official neo (deck-construction group), shown in
  // English (JP original as a hint). Search matches BOTH languages via NEO_MAP. No duplicates.
  const items = [], seen = new Set();
  query("SELECT jp_name, en_name, codes, en_only FROM neos").forEach(n => {
    const v = { codes: (n.codes || "").split(" ").filter(Boolean), en_only: n.en_only };
    if (n.jp_name) NEO_MAP[n.jp_name.toLowerCase()] = v;       // JP search
    if (n.en_name) NEO_MAP[n.en_name.toLowerCase()] = v;       // EN search
    const disp = n.en_name || n.jp_name;                       // one name per neo (English preferred)
    if (disp && !seen.has(disp.toLowerCase())) { seen.add(disp.toLowerCase()); items.push({ v: disp, jp: n.jp_name || "" }); }
  });
  items.sort((a, b) => a.v.localeCompare(b.v));
  // Firefox/Waterfox filters datalist options by the option's VISIBLE TEXT, not its value, so the
  // English title must be the text (no JP label) — otherwise typing English shows nothing in FF.
  // JP search still works via NEO_MAP (independent of the dropdown).
  const dl = document.createElement("datalist"); dl.id = "neo-list";
  dl.innerHTML = items.map(o => `<option value="${escHtml(o.v)}"></option>`).join("");
  document.body.appendChild(dl);
  $("#f-neo").setAttribute("list", "neo-list");

  const deb = debounce(run, 250);
  $("#app").addEventListener("input", e => { if (e.target.matches("input")) deb(); });
  $("#app").addEventListener("change", e => { if (e.target.matches("select") && e.target.id !== "page-size") run(); });
  $("#page-size").addEventListener("change", e => { pageSize = +e.target.value; run(); });
  $("#prev").addEventListener("click", () => { page -= 1; run(false); });
  $("#next").addEventListener("click", () => { page += 1; run(false); });
  // per-filter clear (the ✕ next to each control)
  $("#filters").addEventListener("click", e => {
    const b = e.target.closest(".clr"); if (!b) return;
    e.preventDefault();
    const el = document.getElementById(b.dataset.clear);
    if (el.multiple) Array.from(el.options).forEach(o => o.selected = false);
    else el.value = "";
    run();
  });
  $("#reset").addEventListener("click", () => {
    $("#filters").querySelectorAll("input").forEach(i => i.value = "");
    $("#filters").querySelectorAll("select").forEach(s => [...s.options].forEach(o => o.selected = false));
    run();
  });
  $("#detail-close").addEventListener("click", closeDetail);
  $("#detail").addEventListener("click", e => { if (e.target.id === "detail") closeDetail(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeDetail(); });
}
const multi = id => Array.from($(id).selectedOptions).map(o => o.value);
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// ---- build WHERE from filters ----
function buildWhere() {
  const w = [], p = [];
  const inClause = (col, vals) => { if (vals.length) { w.push(`${col} IN (${vals.map(() => "?").join(",")})`); p.push(...vals); } };

  const q = $("#q").value.trim();
  if (q) {
    const like = "%" + q + "%";
    const flike = "%" + fold(q) + "%";   // accent- & case-insensitive: "deja vu" matches "Déjà Vu"
    w.push(`(search_fold LIKE ?
            OR card_number IN (SELECT card_number FROM abilities WHERE en_text LIKE ? OR jp_text LIKE ?))`);
    p.push(flike, like, like);
  }
  inClause("type", multi("#f-type"));
  inClause("color", multi("#f-color"));
  inClause("side", multi("#f-side"));
  inClause("level", multi("#f-level").map(Number));
  inClause("cost", multi("#f-cost").map(Number));
  inClause("soul", multi("#f-soul").map(Number));

  const trig = multi("#f-trigger");
  if (trig.length) { w.push("(" + trig.map(() => "trigger LIKE ?").join(" OR ") + ")"); p.push(...trig.map(t => "%" + t + "%")); }

  const pmin = $("#f-power-min").value, pmax = $("#f-power-max").value;
  if (pmin !== "") { w.push("power >= ?"); p.push(+pmin); }
  if (pmax !== "") { w.push("power <= ?"); p.push(+pmax); }

  const likeFld = (id, col) => { const v = $(id).value.trim(); if (v) { w.push(`${col} LIKE ?`); p.push("%" + v + "%"); } };
  // trait: match JP (魔法) or EN (Magic); title: the search blob holds JP name + kana + codes + EN franchise
  const trv = $("#f-trait").value.trim();
  if (trv) { w.push("(traits LIKE ? OR traits_en LIKE ?)"); p.push("%" + trv + "%", "%" + trv + "%"); }
  const neov = $("#f-neo").value.trim();
  if (neov) {
    const m = NEO_MAP[neov.toLowerCase()];            // exact neo pick -> its set codes + JP/EN edition
    if (m && m.codes.length) {
      const ph = m.codes.map(() => "?").join(",");
      if (m.en_only === 2) { w.push(`series IN (${ph})`); p.push(...m.codes); }          // EN title incl. JP cards
      else { w.push(`(series IN (${ph}) AND en_exclusive = ?)`); p.push(...m.codes, m.en_only); }
    } else { w.push("title_search LIKE ?"); p.push("%" + neov.toLowerCase() + "%"); }
  }
  likeFld("#f-series", "series");

  // ability power cost: card has at least one effect in [min,max] (and matching confidence)
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
  return { where: w.length ? "WHERE " + w.join(" AND ") : "", params: p };
}

// ---- run query + render list ----
function run(reset) {
  if (reset !== false) page = 0;
  const { where, params } = buildWhere();
  const total = query(`SELECT COUNT(*) n FROM cards ${where}`, params)[0].n;
  const pages = pageSize === 0 ? 1 : Math.max(1, Math.ceil(total / pageSize));
  page = Math.min(Math.max(0, page), pages - 1);
  const lim = pageSize === 0 ? "" : `LIMIT ${pageSize} OFFSET ${page * pageSize}`;
  const rows = query(
    `SELECT card_number,name,name_en,type,color,level,cost,power,soul,model_cost_total
     FROM cards ${where} ORDER BY series, card_number ${lim}`, params);
  $("#count").textContent = `${total.toLocaleString()} card${total === 1 ? "" : "s"}`;
  $("#pageinfo").textContent = total ? `page ${page + 1} / ${pages}` : "";
  $("#prev").disabled = page <= 0;
  $("#next").disabled = page >= pages - 1;
  const dot = c => `<span class="dot c-${escHtml(c)}"></span>`;
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
  $("#results tbody").querySelectorAll("tr").forEach(tr =>
    tr.addEventListener("click", () => showDetail(tr.dataset.cn)));
}

// Resolve the sign of a power cost for display. Positive cost = power PAID (shown −N);
// negative cost = a DRAWBACK that gives power back (shown +N, sign resolved — never "−−N"); 0 = "0".
function fmtCost(v) { return v == null ? "—" : v < 0 ? "+" + (-v) : v > 0 ? "−" + v : "0"; }

// ---- detail ----
function showDetail(cn) {
  const c = query("SELECT * FROM cards WHERE card_number=?", [cn])[0];
  if (!c) return;
  const abs = query("SELECT * FROM abilities WHERE card_number=? ORDER BY idx", [cn]);
  const chip = (k, v) => v == null || v === "" ? "" : `<span class="chip">${escHtml(k)}: ${escHtml(v)}</span>`;
  const imgUrl = c.image_en || (c.picture ? IMG_BASE_JP + c.picture : "");

  let budget = "";
  if (c.power_base != null) {
    const residual = c.residual == null ? 0 : c.residual;
    const sgn = residual > 0 ? "+" : "";
    // residual = what the designer spent beyond (or below) the explained standards.
    const verdict = c.is_suspect
      ? `<span class="warn">designer adjustment <b>${sgn}${residual}</b> — over/under the standard rate</span>`
      : residual === 0
        ? `<span class="ok">on-budget — every effect priced at its standard</span>`
        : `<span class="ok">designer adjustment <b>${sgn}${residual}</b> (within ±500)</span>`;
    budget = `<div class="budget">
      ${c.is_suspect ? `<span class="badge-suspect" title="|residual| ≥ 500: spent off the standard rate">SUSPECT</span> ` : ""}
      Vanilla <b>power_base ${c.power_base}</b>
      → effects actually spend <b>${fmtCost(c.real_delta)}</b> → printed power ${c.power}.<br>
      Of that, <b>${fmtCost(c.model_cost_total || 0)}</b> is explained by standard effect costs;
      the rest is the designer's adjustment → <b class="residual">residual ${sgn}${residual}</b>.<br>${verdict}</div>`;
  } else {
    budget = `<div class="budget"><span class="na">The power-cost model applies to Characters only.</span></div>`;
  }

  const abHtml = abs.map(a => {
    // Headline = the package's STANDARD cost (what this effect "should" cost). Fall back to the
    // card-specific power_cost when no standard was derived. Evidence (samples / mode share) goes
    // in a tooltip on the cost.
    const std = a.standard_cost != null ? a.standard_cost : a.power_cost;
    // Evidence only matters when there is a measured cost; skip it for n/a (e.g. non-Character rows).
    const ev = [];
    if (std != null) {
      if (a.n_samples) ev.push(`${a.n_samples} sample${a.n_samples === 1 ? "" : "s"}`);
      if (a.mode_share != null) ev.push(`${Math.round(a.mode_share)}% mode`);
      if (a.method) ev.push(a.method);
    }
    const evTitle = ev.length ? ` title="${escHtml(ev.join(" · "))}"` : "";
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
  }).join("") || `<p class="na">No abilities.</p>`;

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
  $("#detail").hidden = false;
}
function closeDetail() { $("#detail").hidden = true; }

boot();
