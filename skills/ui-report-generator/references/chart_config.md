# Chart.js 4.4 配置参考

本技能通过 CDN 引入 Chart.js 4.4：
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

## 状态饼图（doughnut）

```javascript
new Chart(ctx, {
  type: "doughnut",
  data: {
    labels: ["通过", "失败", "跳过"],
    datasets: [{
      data: [passed, failed, skipped],
      backgroundColor: ["#34a853", "#ea4335", "#9aa0a6"]
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: "bottom" } }
  }
});
```

## 模块通过率柱图

```javascript
new Chart(ctx, {
  type: "bar",
  data: {
    labels: modules,
    datasets: [{
      label: "通过率%",
      data: passRates,
      backgroundColor: "#1a73e8"
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true, max: 100 } }
  }
});
```

## 历史趋势折线

```javascript
new Chart(ctx, {
  type: "line",
  data: {
    labels: timestamps,
    datasets: [{
      label: "通过率%",
      data: passRates,
      borderColor: "#1a73e8",
      backgroundColor: "rgba(26,115,232,0.1)",
      fill: true
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true, max: 100 } }
  }
});
```

## 离线降级

检测 `typeof Chart === "undefined"` 时隐藏 `<canvas>` 容器，显示同区域的 HTML `<table>`。
