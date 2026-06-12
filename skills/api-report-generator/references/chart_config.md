# Chart.js 图表配置参考

## 通用配置

所有图表共享以下基础配置：

```javascript
Chart.defaults.font.family = "'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#5f6368';
Chart.defaults.plugins.legend.position = 'bottom';
Chart.defaults.responsive = true;
Chart.defaults.maintainAspectRatio = false;
```

## 通过率趋势折线图

```javascript
{
  type: 'line',
  data: {
    labels: ['第1次', '第2次', ...],  // 最近10次执行
    datasets: [{
      label: '通过率(%)',
      data: [25.3, 48.2, 78.0, 97.5, ...],
      borderColor: '#1a73e8',
      backgroundColor: 'rgba(26,115,232,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: 5,
      pointHoverRadius: 7,
    }]
  },
  options: {
    scales: {
      y: { min: 0, max: 100, ticks: { callback: v => v + '%' } }
    },
    plugins: {
      tooltip: { callbacks: { label: ctx => `通过率: ${ctx.parsed.y}%` } }
    }
  }
}
```

## 模块分布饼图

```javascript
{
  type: 'doughnut',
  data: {
    labels: ['auth', 'order', 'cart', 'product', 'admin', ...],
    datasets: [{
      data: [12, 15, 8, 6, 20, ...],
      backgroundColor: [
        '#1a73e8', '#34a853', '#ea4335', '#fbbc04',
        '#9aa0a6', '#7baaf7', '#ce6ae0', '#00bcd4'
      ],
      borderWidth: 2,
      borderColor: '#ffffff',
    }]
  },
  options: {
    cutout: '60%',
    plugins: {
      tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed} 条` } }
    }
  }
}
```

## 优先级柱状图

```javascript
{
  type: 'bar',
  data: {
    labels: ['P0', 'P1', 'P2', 'P3'],
    datasets: [
      {
        label: '通过',
        data: [77, 45, 30, 10],
        backgroundColor: '#34a853',
      },
      {
        label: '失败',
        data: [0, 2, 3, 1],
        backgroundColor: '#ea4335',
      },
      {
        label: '跳过',
        data: [1, 0, 0, 0],
        backgroundColor: '#9aa0a6',
      }
    ]
  },
  options: {
    scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } }
  }
}
```

## 模块通过率横向柱状图

```javascript
{
  type: 'bar',
  data: {
    labels: ['auth', 'order', 'cart', 'product', 'admin', 'search'],
    datasets: [{
      label: '通过率(%)',
      data: [95, 88, 100, 92, 85, 100],
      backgroundColor: data.map(v => v >= 90 ? '#34a853' : v >= 70 ? '#fbbc04' : '#ea4335'),
    }]
  },
  options: {
    indexAxis: 'y',
    scales: { x: { min: 0, max: 100, ticks: { callback: v => v + '%' } } }
  }
}
```

## CDN 地址

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

## 离线降级方案

当 Chart.js CDN 加载失败时，显示纯数据表格：

```javascript
window.addEventListener('load', function() {
  if (typeof Chart === 'undefined') {
    document.querySelectorAll('canvas').forEach(c => {
      const table = createFallbackTable(c.dataset);
      c.parentNode.replaceChild(table, c);
    });
  }
});
```
