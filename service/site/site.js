(() => {
  const { $, show, msg, get, busy, nf, variants, footer, disp } = window.OVD;

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
    const { node } = window.OVD;
    const ul = node("ul", undefined, "list");
    for (const m of items) {
      const li = node("li");
      const b = node("button", `${disp(m.name)}${m.registrations ? ` · ${nf.format(m.registrations)} registered` : ""}`);
      b.type = "button";
      b.addEventListener("click", async () => {
        show(box, msg("Loading versions…"));
        try {
          await variants(box, m.id.startsWith("family_") ? { family_id: m.id } : { model_id: m.id }, `${disp(m.name)}: `);
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
        show(box, msg(`Makes found: ${r.brands.map((b) => disp(b.name)).join(", ")}. Add a model name, for example “${disp(r.brands[0].name)} …”.`));
      } else if (r.did_you_mean.length) {
        show(box, msg(`Nothing found. Did you mean: ${r.did_you_mean.map(disp).join(", ")}?`));
      } else {
        show(box, msg("Nothing found."));
      }
    } catch (err) {
      show(box, msg(err.message, true));
    } finally {
      busy(f, false);
    }
  });

  footer();
})();
