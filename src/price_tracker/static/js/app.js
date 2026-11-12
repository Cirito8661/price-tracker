(function () {
  "use strict";

  if (window.htmx) {
    window.htmx.config.responseHandling = [
      { code: "204", swap: false },
      { code: "[23]..", swap: true },
      { code: "[45]..", swap: true, error: true },
    ];
  }

  function initPriceChart() {
    const canvas = document.getElementById("price-history-chart");
    if (!canvas || typeof window.Chart === "undefined") {
      return;
    }

    let labels;
    let values;
    try {
      labels = JSON.parse(canvas.dataset.labels || "[]");
      values = JSON.parse(canvas.dataset.values || "[]");
    } catch (error) {
      return;
    }

    if (!Array.isArray(labels) || !Array.isArray(values) || labels.length === 0) {
      return;
    }

    const numericValues = values.map((value) => Number(value));
    if (numericValues.some((value) => !Number.isFinite(value))) {
      return;
    }

    const currency = canvas.dataset.currency || "";
    const label = currency ? `Price (${currency})` : "Price";

    new window.Chart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: label,
            data: numericValues,
            borderColor: "#38bdf8",
            backgroundColor: "rgba(56, 189, 248, 0.12)",
            borderWidth: 2,
            pointBackgroundColor: "#a78bfa",
            pointBorderColor: "#a78bfa",
            pointRadius: 3,
            pointHoverRadius: 5,
            fill: true,
            tension: 0.35,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "#cbd5e1" } },
          tooltip: {
            backgroundColor: "#0f172a",
            borderColor: "#334155",
            borderWidth: 1,
          },
        },
        scales: {
          x: {
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(148, 163, 184, 0.12)" },
          },
          y: {
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(148, 163, 184, 0.12)" },
          },
        },
      },
    });
  }

  function initConfirmations() {
    document.querySelectorAll("form[data-confirm]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        if (!window.confirm(form.dataset.confirm)) {
          event.preventDefault();
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initPriceChart();
    initConfirmations();
  });
})();
