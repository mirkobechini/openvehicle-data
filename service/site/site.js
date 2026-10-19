(() => {
  const API = "/api/v1";
  const $ = (id) => document.getElementById(id);

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

  const num = (v, unit) => (v === null || v === undefined ? "unknown" : unit ? `${v} ${unit}` : String(v));

  const card = (v) => {
    const c = node("article", undefined, "card");
    c.append(node("h3", v.name));
    const dl = node("dl");
    const e = v.engine;
    const rows = [
      ["Fuel", e.fuel],
      ["Engine", e.displacement_cc ? `${e.displacement_cc} cc, ${num(e.power_kw, "kW")}` : num(e.power_kw, "kW")],
      ["Seats", num(v.seats)],
      ["Max. mass (F.2)", num(v.max_mass_kg, "kg")],
      ["Mass in running order", num(v.mass_kg, "kg")],
      ["Emission class", num(v.environmental_class)],
      ["CO2 (WLTP)", num(v.co2_wltp_g_km, "g/km")],
      ["Registered in", v.years.length ? v.years.join(", ") : "unknown"],
      ["Cars registered", num(v.registrations)],
    ];
    for (const [k, val] of rows) {
      dl.append(node("dt", k), node("dd", val));
    }
    c.append(dl);
    return c;
  };

  const variants = async (box, params, label) => {
    const page = await get("/variants", { ...params, sort: "registrations", limit: 5 });
    if (!page.total) {
      show(box, msg("No version found. It may not be in the catalogue (cars registered in Italy 2019-2025, M1 category only)."));
      return;
    }
    const details = await Promise.all(page.items.map((v) => get(`/variants/${encodeURIComponent(v.id)}`)));
    const head = msg(page.total === 1 ? `${label}1 version found.` : `${label}${page.total} versions found${page.total > page.count ? `, showing the ${page.count} most registered` : ""}.`);
    show(box, head, ...details.map(card));
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
      const b = node("button", `${m.name}${m.registrations ? ` · ${m.registrations} registered` : ""}`);
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
      $("meta").textContent = `Dataset ${m.version} · ${m.counts.Variant} versions · ${m.counts.Brand} makes`;
    })
    .catch(() => {
      $("meta").textContent = "";
    });
})();
