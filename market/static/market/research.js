document.addEventListener('DOMContentLoaded', () => {
  const element = document.getElementById('keyword-tree');
  if (!element || !window.echarts) return;
  const data = JSON.parse(document.getElementById('keyword-tree-data').textContent);
  const chart = echarts.init(element, null, {renderer: 'svg'});
  chart.setOption({tooltip: {trigger: 'item', renderMode: 'richText'}, series: [{type: 'tree', data: [data],
    top: 20, bottom: 20, left: 100, right: 160, symbolSize: 12, roam: true, initialTreeDepth: -1,
    expandAndCollapse: false, animationDuration: 300,
    label: {position: 'left', fontSize: 12, color: '#334155', formatter: p => p.name.length > 30 ? p.name.slice(0, 30) + '…' : p.name},
    leaves: {label: {position: 'right', width: 145, overflow: 'truncate'}}, lineStyle: {color: '#c7d2fe', curveness: 0.45},
    itemStyle: {color: '#6366f1', borderColor: '#6366f1'}}]});
  chart.on('click', params => {
    if (params.data.kind === 'term' && params.data.term) {
      const url = new URL(window.location.href);
      url.searchParams.set('term', params.data.term);
      window.location.assign(url.toString());
    } else if (params.data.kind === 'product') {
      const row = document.getElementById(params.data.rowId);
      if (row) { row.scrollIntoView({behavior: 'smooth', block: 'center'}); row.focus();
        document.querySelectorAll('.tree-highlight').forEach(el => el.classList.remove('tree-highlight'));
        row.classList.add('tree-highlight'); }
    }
  });
  window.addEventListener('resize', () => chart.resize());
});

document.addEventListener('DOMContentLoaded', () => {
  const source = document.getElementById('price-distribution-data');
  if (!source || !window.echarts) return;
  const groups = JSON.parse(source.textContent);
  const charts = [];
  document.querySelectorAll('.price-distribution-chart').forEach(element => {
    const data = groups[Number(element.dataset.chartIndex)];
    const chart = echarts.init(element, null, {renderer:'svg'});
    chart.setOption({tooltip:{trigger:'axis',renderMode:'richText'},
      grid:{left:45,right:20,top:25,bottom:80},
      xAxis:{type:'category',data:data.labels,axisLabel:{fontSize:11,interval:0,rotate:18}},
      yAxis:{type:'value',minInterval:1,name:'商品数'},
      series:[{type:'bar',name:data.currency+' 商品数',data:data.counts,barMaxWidth:65,
        itemStyle:{color:'#6366f1',borderRadius:[5,5,0,0]},label:{show:true,position:'top'}}]});
    charts.push(chart);
  });
  window.addEventListener('resize',()=>charts.forEach(chart=>chart.resize()));
});
