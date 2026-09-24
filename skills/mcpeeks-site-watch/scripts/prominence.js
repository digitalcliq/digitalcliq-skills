// Run via browser javascript_tool on a VDP. Returns every visible element whose
// text is a dollar amount, with computed font size/weight and viewport position.
// Deterministic input for check C03 (all-in price must be the single most
// prominent price). Compact output — safe to read directly.
(() => {
  const out = [];
  const seen = new Set();
  document.querySelectorAll("body *").forEach(el => {
    if (el.children.length > 0) return;
    const t = (el.textContent || "").trim();
    const m = t.match(/^\$?\s?([\d,]{4,9})(\.\d{2})?$/);
    if (!m) return;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const cs = getComputedStyle(el);
    const key = t + "|" + Math.round(r.top);
    if (seen.has(key)) return;
    seen.add(key);
    const label = (el.closest("[class]")?.className || "").toString().slice(0, 60);
    out.push({ amount: t, px: parseFloat(cs.fontSize), weight: cs.fontWeight,
               top: Math.round(r.top + scrollY), cls: label,
               struck: cs.textDecorationLine.includes("line-through") });
  });
  out.sort((a, b) => b.px - a.px || b.weight - a.weight);
  return JSON.stringify(out.slice(0, 12));
})();
