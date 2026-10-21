(() => {
  const { $, nf, node, show, msg, get, footer, disp } = window.OVD;

  const FIELDS = [
    ["type_approval", "Type-approval", "K"],
    ["seats", "Seats", "S.1"],
    ["max_mass_kg", "F.2 mass", "F.2"],
    ["environmental_class", "Emission class", "V.9"],
  ];

  const pct = (x) => `${Math.round(x * 100)}%`;
  const bar = (share, cls) => {
    const track = node("div", undefined, "bar-track" + (cls ? ` ${cls}` : ""));
    const fill = node("div", undefined, "bar-fill");
    fill.style.width = pct(share);
    track.append(fill);
    return track;
  };

  const meter = ([key, label, tag], f) => {
    const t = node("div", undefined, "meter");
    const h = node("div", undefined, "mhead");
    h.append(node("span", label), node("span", tag, "tag"));
    t.append(h);
    const big = node("div", undefined, "mbig");
    big.append(node("span", pct(f.share), "mnum"), node("span", "of versions", "msuf"));
    t.append(big, bar(f.share), node("div", `${pct(f.weighted)} weighted by registrations`, "mfoot"));
    return t;
  };

  const renderOverall = (overall) => {
    const grid = node("div", undefined, "meters-grid");
    for (const f of FIELDS) grid.append(meter(f, overall.fields[f[0]]));
    show($("r-overall"), grid);
  };

  const row = (b) => {
    const r = node("div", undefined, "trow");
    r.append(node("div", disp(b.name), "tname"));
    r.append(node("div", nf.format(b.variants), "tvariants"));
    for (const [key] of FIELDS) {
      const cell = node("div", undefined, "tcell");
      const f = b.fields[key];
      cell.append(bar(f.share), node("span", pct(f.share), "tpct"));
      r.append(cell);
    }
    return r;
  };

  const renderTable = (brands, sort) => {
    const sorted = [...brands].sort((a, b) => (sort === "variants" ? b.variants - a.variants : a.name.localeCompare(b.name)));
    const table = node("div", undefined, "table");
    const head = node("div", undefined, "trow thead");
    head.append(node("div", "Make"), node("div", "Versions"));
    for (const [, label, tag] of FIELDS) {
      const h = node("div");
      h.append(label, " ", node("span", tag, "tag"));
      head.append(h);
    }
    table.append(head);
    for (const b of sorted) table.append(row(b));
    show($("r-table"), table);
  };

  const sorterButton = (key, label, state, onPick) => {
    const b = node("button", label);
    b.type = "button";
    b.setAttribute("aria-pressed", String(state.sort === key));
    b.addEventListener("click", () => onPick(key));
    return b;
  };

  get("/coverage")
    .then((c) => {
      renderOverall(c.overall);
      const state = { sort: "name" };
      const sorters = $("sorters");
      const paint = () => {
        show(sorters, sorterButton("name", "Name", state, pick), sorterButton("variants", "Versions", state, pick));
        renderTable(c.brands, state.sort);
      };
      const pick = (key) => {
        state.sort = key;
        paint();
      };
      paint();
    })
    .catch((err) => {
      show($("r-overall"), msg(err.message, true));
      show($("r-table"));
    });

  footer();
})();
