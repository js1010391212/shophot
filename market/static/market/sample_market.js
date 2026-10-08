document.addEventListener('DOMContentLoaded',()=>{
  const source=document.getElementById('sample-market-data');
  if(!source || !window.echarts)return;
  const data=JSON.parse(source.textContent), charts=[];
  function draw(element,rows,horizontal=false){
    if(!element || !rows.length)return;
    const chart=echarts.init(element,null,{renderer:'svg'});charts.push(chart);
    const categories={type:'category',data:rows.map(row=>row.name),axisLabel:{hideOverlap:true,width:110,overflow:'truncate'}};
    const values={type:'value',minInterval:1,name:'商品数'};
    chart.setOption({animation:false,tooltip:{trigger:'axis',renderMode:'richText'},grid:{left:horizontal?125:45,right:25,top:30,bottom:45},
      xAxis:horizontal?values:categories,yAxis:horizontal?categories:values,
      series:[{type:'bar',data:rows.map(row=>row.count),barMaxWidth:45,itemStyle:{color:'#6557d5'}}]});
    chart.on('click',event=>{
      const url=new URL(rows[event.dataIndex].url,location.origin);
      if(url.origin===location.origin)location.assign(url.href);
    });
  }
  draw(document.getElementById('sample-brand-chart'),data.brands.slice().reverse(),true);
  document.querySelectorAll('.sample-price-chart').forEach(element=>draw(element,data.prices[Number(element.dataset.chartIndex)].bins));
  window.addEventListener('resize',()=>charts.forEach(chart=>chart.resize()));
});
