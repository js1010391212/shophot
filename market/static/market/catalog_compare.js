document.addEventListener('DOMContentLoaded',()=>{
  const element=document.getElementById('catalog-compare-chart');
  if(!element || !window.echarts) return;
  const data=JSON.parse(document.getElementById('catalog-compare-data').textContent);
  const chart=echarts.init(element,null,{renderer:'svg'});
  chart.setOption({animation:false,tooltip:{trigger:'axis',renderMode:'richText'},legend:{data:['最低公开价','最高公开价']},
    grid:{left:190,right:60,top:50,bottom:40},xAxis:{type:'value',name:data.currency},
    yAxis:{type:'category',data:data.names,inverse:true,axisLabel:{width:165,overflow:'truncate'}},
    series:[{name:'最低公开价',type:'bar',data:data.low.map(Number),barMaxWidth:24,itemStyle:{color:'#6366f1'},label:{show:true,position:'right'}},
      {name:'最高公开价',type:'bar',data:data.high.map(Number),barMaxWidth:24,itemStyle:{color:'#a5b4fc'},label:{show:true,position:'right'}}]});
  window.addEventListener('resize',()=>chart.resize());
});
