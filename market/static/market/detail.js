/* 图表数据通过 Django json_script 注入，避免标题或数据成为可执行脚本。 */
document.addEventListener("DOMContentLoaded", () => {
  const element = document.getElementById("price-chart");
  if (element && window.echarts) {
    const data = JSON.parse(document.getElementById("price-data").textContent);
    const chart = echarts.init(element);
    chart.setOption({
      color: ["#2563eb"],
      tooltip: {trigger: "axis", renderMode: "richText"},
      grid: {left: 65, right: 25, top: 25, bottom: 65},
      xAxis: {type: "category", data: data.dates.map(date => new Date(date).toLocaleString("zh-CN"))},
      yAxis: {type: "value", scale: true},
      dataZoom: [{type: "inside"}, {type: "slider", height: 20, bottom: 5}],
      series: [{name: "观测价格", type: "line", data: data.prices.map(Number),
                showSymbol: true, areaStyle: {opacity: 0.08}}]
    });
    window.addEventListener("resize", () => chart.resize());
  }
  const poll = document.getElementById("job-poll");
  if (poll) {
    const timer = setInterval(async () => {
      try {
        const response = await fetch(poll.dataset.statusUrl, {headers: {"Accept": "application/json"}});
        if (!response.ok || response.redirected) { clearInterval(timer); return; }
        const status = await response.json();
        if (!status.active) { clearInterval(timer); window.location.reload(); }
      } catch (_) {
        poll.textContent = "暂时无法检查任务状态，请刷新页面。";
        clearInterval(timer);
      }
    }, 3000);
  }
});
