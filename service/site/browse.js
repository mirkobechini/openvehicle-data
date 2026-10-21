(() => {
  const { $, nf, node, show, msg, get, variants, footer, disp } = window.OVD;

  const catalogItems = async (brandId) => {
    const [fams, mods] = await Promise.all([get("/families", { brand_id: brandId, sort: "registrations", limit: 12 }), get("/models", { brand_id: brandId, sort: "registrations", limit: 12 })]);
    return [...mods.items, ...fams.items.filter((f) => !mods.items.some((m) => m.family_id === f.id))];
  };

  const modelCard = (it, resultBox) => {
    const b = node("button", undefined, "mcard");
    b.type = "button";
    b.setAttribute("aria-pressed", "false");
    b.append(node("div", disp(it.name), "mname"));
    if (it.registrations) b.append(node("div", `${nf.format(it.registrations)} registered`, "mreg"));
    b.addEventListener("click", () => {
      for (const x of b.parentElement.querySelectorAll("button")) x.setAttribute("aria-pressed", "false");
      b.setAttribute("aria-pressed", "true");
      show(resultBox, msg("Loading versions…"));
      variants(resultBox, it.id.startsWith("family_") ? { family_id: it.id } : { model_id: it.id }, `${disp(it.name)}: `).catch((err) => show(resultBox, msg(err.message, true)));
    });
    return b;
  };

  const pickBrand = async (b, rail) => {
    const box = $("r-models");
    for (const x of rail.querySelectorAll("button")) x.setAttribute("aria-pressed", "false");
    b.btn.setAttribute("aria-pressed", "true");
    show(box, msg("Loading models…"));
    try {
      const items = await catalogItems(b.id);
      if (!items.length) {
        show(box, msg(`${disp(b.name)} has no model with versions yet.`));
        return;
      }
      const grid = node("div", undefined, "models");
      const resultBox = node("div");
      for (const it of items) grid.append(modelCard(it, resultBox));
      show(box, node("p", `${disp(b.name)} — choose a model to see its versions.`, "msg"), grid, resultBox);
    } catch (err) {
      show(box, msg(err.message, true));
    }
  };

  get("/brands", { limit: 200 })
    .then((page) => {
      const rail = $("rail");
      show(rail);
      for (const b of page.items) {
        const li = node("li");
        const btn = node("button", disp(b.name));
        btn.type = "button";
        btn.setAttribute("aria-pressed", "false");
        const entry = { ...b, btn };
        btn.addEventListener("click", () => pickBrand(entry, rail));
        li.append(btn);
        rail.append(li);
      }
      if (page.items.length) pickBrand({ ...page.items[0], btn: rail.querySelector("button") }, rail);
    })
    .catch((err) => show($("r-models"), msg(err.message, true)));

  footer();
})();
