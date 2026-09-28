const PulseWatch = {
  drawTrends(root) {
    if (!root) return;
    let series = [];
    try {
      series = JSON.parse(root.getAttribute("data-series") || "[]");
    } catch (e) {
      return;
    }
    root.innerHTML = "";
    series.forEach((item) => {
      const wrap = document.createElement("div");
      wrap.className = "trend-block";
      const title = document.createElement("h3");
      title.textContent = item.name + " — response time";
      wrap.appendChild(title);
      const points = (item.points || []).filter((p) => p.ms != null);
      if (!points.length) {
        const empty = document.createElement("p");
        empty.className = "muted";
        empty.textContent = "No response-time samples yet.";
        wrap.appendChild(empty);
        root.appendChild(wrap);
        return;
      }
      const w = 640;
      const h = 90;
      const max = Math.max(...points.map((p) => p.ms), 1);
      const step = points.length === 1 ? 0 : (w - 16) / (points.length - 1);
      const coords = points.map((p, i) => {
        const x = 8 + i * step;
        const y = h - 10 - (p.ms / max) * (h - 20);
        return x + "," + y;
      });
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 " + w + " " + h);
      svg.setAttribute("preserveAspectRatio", "none");
      const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      poly.setAttribute("fill", "none");
      poly.setAttribute("stroke", "#5cd6ff");
      poly.setAttribute("stroke-width", "2");
      poly.setAttribute("points", coords.join(" "));
      svg.appendChild(poly);
      wrap.appendChild(svg);
      root.appendChild(wrap);
    });
  },
};

window.PulseWatch = PulseWatch;
