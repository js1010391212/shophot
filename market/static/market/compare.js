/* 用时间轴对齐各商品观测；不补齐缺失数据，不跨币种换算。 */
document.addEventListener("DOMContentLoaded", () => {
  const target = document.getElementById("compare-chart");
  if (!target || !window.echarts) return;
  const data = JSON.parse(document.getElementById("compare-data").textContent);
  const chart = echarts.init(target);
  const formatTime = value => new Date(value).toLocaleString("zh-CN", {timeZone: data.timezone});
  chart.setOption({
    tooltip: {trigger: "item", renderMode: "richText", formatter: item => `${item.seriesName}\n${formatTime(item.value[0])}\n价格：${item.value[1]}`},
    legend: {type: "scroll", top: 0},
    grid: {left: 65, right: 25, top: 55, bottom: 65},
    xAxis: {type: "time", axisLabel: {formatter: value => new Date(value).toLocaleDateString("zh-CN", {timeZone: data.timezone})}},
    yAxis: {type: "value", scale: true},
    dataZoom: [{type: "inside"}, {type: "slider", height: 20, bottom: 5}],
    series: data.series.map(series => ({name: series.name, type: "line", showSymbol: true,
      data: series.points.map(point => [point[0], Number(point[1])])}))
  });
  window.addEventListener("resize", () => chart.resize());
});
