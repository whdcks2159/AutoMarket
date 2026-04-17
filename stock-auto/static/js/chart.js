// 전략별 누적 손익 차트 유틸리티
export function buildPnlChart(ctx, labels, datasets) {
  const colors = ['#4f7cff', '#22c55e', '#f59e0b', '#ef4444', '#a78bfa'];
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: Object.entries(datasets).map(([key, values], i) => ({
        label: key,
        data: values,
        borderColor: colors[i % colors.length],
        backgroundColor: colors[i % colors.length] + '22',
        tension: 0.4,
        fill: true,
        pointRadius: 3,
      })),
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e2e8f0', font: { family: 'Inter' } } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ₩${ctx.parsed.y.toLocaleString()}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#94a3b8', maxTicksLimit: 10 },
          grid: { color: '#2e3350' },
        },
        y: {
          ticks: {
            color: '#94a3b8',
            callback: v => '₩' + v.toLocaleString(),
          },
          grid: { color: '#2e3350' },
        },
      },
    },
  });
}
