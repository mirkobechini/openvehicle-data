(() => {
  const API = "/api/v1";
  const PAGE = 5;
  const $ = (id) => document.getElementById(id);
  const nf = new Intl.NumberFormat("it-IT", { useGrouping: "always" });

  const node = (tag, text, cls) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  };

  const show = (box, ...kids) => box.replaceChildren(...kids);
  const msg = (text, err) => node("p", text, err ? "msg err" : "msg");

  const get = async (path, params) => {
    const u = new URL(API + path, location.origin);
    for (const [k, v] of Object.entries(params || {})) if (v) u.searchParams.set(k, v);
    let r;
    try {
      r = await fetch(u);
    } catch {
      throw new Error("The service cannot be reached. Try again in a moment.");
    }
    if (r.status === 429) throw new Error(`Too many requests. Wait ${r.headers.get("retry-after") || "a few"} seconds.`);
    if (r.status === 422) throw new Error("Some value has an unexpected format. Check what you typed.");
    if (!r.ok) throw new Error("Something went wrong. Try again.");
    return r.json();
  };

  const busy = (form, on) => {
    form.querySelector("button[type=submit]").disabled = on;
    form.setAttribute("aria-busy", String(on));
  };

  const FUELS = {
    petrol: "Petrol",
    diesel: "Diesel",
    hybrid: "Hybrid",
    phev: "Plug-in hybrid",
    electric: "Electric",
    lpg: "LPG",
    cng: "CNG / methane",
    hydrogen: "Hydrogen",
    other: "Other",
  };

  const has = (v) => v !== null && v !== undefined;
  const n = (v, unit) => (unit ? `${nf.format(v)} ${unit}` : nf.format(v));

  const years = (ys) => {
    if (!ys.length) return null;
    const run = ys.every((y, i) => i === 0 || y === ys[i - 1] + 1);
    return run && ys.length > 1 ? `${ys[0]}–${ys[ys.length - 1]}` : ys.join(", ");
  };

  const share = (v, total) => {
    if (!has(v) || !total) return "";
    const p = (100 * v) / total;
    return p < 1 ? " (under 1% of the model)" : ` (${Math.round(p)}% of the model)`;
  };

  const power = (kw) => (has(kw) ? `${n(kw, "kW")} · ${nf.format(Math.round(kw * 1.35962))} CV` : null);
  const litres = (cc) => (cc ? (cc / 1000).toFixed(1) : null);

  const summary = (e) => [FUELS[e.fuel] || e.fuel, litres(e.displacement_cc), has(e.power_kw) ? `${nf.format(Math.round(e.power_kw))} kW (${nf.format(Math.round(e.power_kw * 1.35962))} CV)` : null].filter(Boolean).join(" · ");

  const row = (dl, label, tag, value) => {
    const dt = node("dt", label);
    if (tag) dt.append(" ", node("span", tag, "tag"));
    dl.append(dt, has(value) ? node("dd", value) : node("dd", "not known", "unk"));
  };

  const section = (card, title, rows) => {
    if (rows.every((r) => !has(r[2]))) return;
    const s = node("section", undefined, "part");
    s.append(node("h4", title));
    const dl = node("dl");
    for (const [label, tag, value] of rows) row(dl, label, tag, value);
    s.append(dl);
    card.append(s);
  };

  const copy = (text) => {
    if (!navigator.clipboard) return null;
    const wrap = node("span", undefined, "copy");
    const b = node("button", "Copy codes", "ghost");
    b.type = "button";
    const st = node("span", "", "sr");
    st.setAttribute("role", "status");
    b.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text);
        st.textContent = "Copied";
        b.textContent = "Copied";
      } catch {
        st.textContent = "Copy failed";
      }
      setTimeout(() => {
        b.textContent = "Copy codes";
        st.textContent = "";
      }, 2000);
    });
    wrap.append(b, st);
    return wrap;
  };

  const card = (v) => {
    const c = node("article", undefined, "card");
    const h = node("header");
    h.append(node("h3", `${v.brand.name} ${v.model.name}`));
    h.append(node("p", summary(v.engine), "sum"));
    const codes = [v.type_code, v.variant_code, v.version_code];
    if (codes.every(Boolean)) {
      const p = node("p", undefined, "codes");
      p.append(node("span", "Type "), node("strong", v.type_code), node("span", " · Variant "), node("strong", v.variant_code), node("span", " · Version "), node("strong", v.version_code));
      const cp = copy(codes.join(" "));
      if (cp) p.append(cp);
      h.append(p);
    } else {
      h.append(node("p", v.name, "codes"));
    }
    c.append(h);
    const e = v.engine;
    const zero = e.fuel === "electric" || e.fuel === "hydrogen";
    section(c, "Engine", [
      ["Fuel", "P.3", FUELS[e.fuel] || e.fuel],
      ...(zero ? [] : [["Displacement", "P.1", e.displacement_cc ? n(e.displacement_cc, "cc") : null]]),
      ["Power", "P.2", power(e.power_kw)],
    ]);
    section(c, "Mass and seats", [
      ["Seats", "S.1", v.seats],
      ["Maximum mass", "F.2", has(v.max_mass_kg) ? n(v.max_mass_kg, "kg") : null],
      ["Mass in running order", "≈ G", has(v.mass_kg) ? n(v.mass_kg, "kg") : null],
    ]);
    section(c, "Emissions", [
      ["Emission class", "V.9", v.environmental_class || (zero ? "Zero emission" : null)],
      ["CO2 (WLTP)", "V.7", has(v.co2_wltp_g_km) ? n(v.co2_wltp_g_km, "g/km") : null],
    ]);
    section(c, "Registration document and sales", [
      ["Type-approval number", "K", v.type_approval],
      ["Registered in", null, years(v.years)],
      ["Cars registered", null, has(v.registrations) ? `${n(v.registrations)}${share(v.registrations, v.model.registrations)}` : null],
    ]);
    return c;
  };

  const variants = async (box, params, label) => {
    const state = { fuel: "", shown: 0 };
    const head = node("p", "Loading…", "msg");
    const filter = node("div", undefined, "filter");
    const sel = node("select");
    sel.id = "fuel-filter";
    sel.append(new Option("All fuels", ""), ...Object.entries(FUELS).map(([k, t]) => new Option(t, k)));
    const lab = node("label", "Fuel");
    lab.htmlFor = sel.id;
    filter.append(lab, sel);
    const list = node("div");
    const more = node("button", "Show more", "more");
    more.type = "button";
    more.hidden = true;
    const note = node("p", undefined, "msg");
    note.setAttribute("role", "status");

    const load = async (reset) => {
      if (reset) {
        state.shown = 0;
        list.replaceChildren();
      }
      more.disabled = true;
      try {
        const page = await get("/variants", { ...params, fuel: state.fuel, sort: "registrations", limit: PAGE, offset: state.shown });
        const details = await Promise.all(page.items.map((v) => get(`/variants/${encodeURIComponent(v.id)}`)));
        list.append(...details.map(card));
        state.shown += page.count;
        head.textContent = !page.total
          ? "No version found. It may not be in the catalogue (cars registered in Italy 2019-2025, M1 category only)."
          : `${label}${page.total === 1 ? "1 version found." : `${nf.format(page.total)} versions found, showing ${state.shown}.`}`;
        if (page.total > PAGE || state.fuel) filter.hidden = false;
        more.hidden = !page.has_more;
        more.textContent = `Show more (${page.total - state.shown} left)`;
        note.textContent = "";
      } catch (err) {
        note.textContent = err.message;
        note.className = "msg err";
      } finally {
        more.disabled = false;
      }
    };

    sel.addEventListener("change", () => {
      state.fuel = sel.value;
      load(true);
    });
    more.addEventListener("click", () => load(false));

    show(box, head, filter, list, more, note);
    filter.hidden = true;
    await load(true);
  };

  $("f-doc").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const box = $("r-doc");
    const p = Object.fromEntries(new FormData(f));
    for (const k in p) p[k] = String(p[k]).trim();
    show(box, msg("Looking up…"));
    busy(f, true);
    try {
      const narrow = p.type_code || p.variant_code || p.version_code;
      await variants(box, p, narrow ? "" : "Only the approval number was given. ");
    } catch (err) {
      show(box, msg(err.message, true));
    } finally {
      busy(f, false);
    }
  });

  const models = (box, items) => {
    const ul = node("ul", undefined, "list");
    for (const m of items) {
      const li = node("li");
      const b = node("button", `${m.name}${m.registrations ? ` · ${nf.format(m.registrations)} registered` : ""}`);
      b.type = "button";
      b.addEventListener("click", async () => {
        show(box, msg("Loading versions…"));
        try {
          await variants(box, m.id.startsWith("family_") ? { family_id: m.id } : { model_id: m.id }, `${m.name}: `);
        } catch (err) {
          show(box, msg(err.message, true));
        }
      });
      li.append(b);
      ul.append(li);
    }
    return ul;
  };

  $("f-search").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const box = $("r-search");
    show(box, msg("Searching…"));
    busy(f, true);
    try {
      const r = await get("/search", { q: f.q.value.trim() });
      const found = [...r.models, ...r.families.filter((x) => !r.models.some((m) => m.family_id === x.id))];
      if (found.length) {
        show(box, msg(`${found.length} found. Choose one to see its versions.`), models(box, found));
      } else if (r.brands.length) {
        show(box, msg(`Makes found: ${r.brands.map((b) => b.name).join(", ")}. Add a model name, for example “${r.brands[0].name} …”.`));
      } else if (r.did_you_mean.length) {
        show(box, msg(`Nothing found. Did you mean: ${r.did_you_mean.join(", ")}?`));
      } else {
        show(box, msg("Nothing found."));
      }
    } catch (err) {
      show(box, msg(err.message, true));
    } finally {
      busy(f, false);
    }
  });

  get("/meta")
    .then((m) => {
      $("meta").textContent = `Dataset ${m.version} · ${nf.format(m.counts.Variant)} versions · ${m.counts.Brand} makes`;
    })
    .catch(() => {
      $("meta").textContent = "";
    });
})();
