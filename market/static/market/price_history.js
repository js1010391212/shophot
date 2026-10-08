document.addEventListener('DOMContentLoaded',()=>{
  const element=document.getElementById('price-history-chart'),source=document.getElementById('price-history-data');
  if(!element || !source || !window.echarts)return;
  const data=JSON.parse(source.textContent),chart=echarts.init(element,null,{renderer:'svg'});
  const series=[{name:'报价下限',type:'scatter',data:data.low,symbolSize:9,itemStyle:{color:'#5655d7'}},
                {name:'报价上限',type:'scatter',data:data.high,symbolSize:6,itemStyle:{color:'#14a38b'}}];
  data.segments.forEach(indices=>{
    for(const [name,values,color] of [['报价下限',data.low,'#5655d7'],['报价上限',data.high,'#14a38b']]){
      const positions=new Set(indices);
      series.push({name,type:'line',data:values.map((value,index)=>positions.has(index)?value:null),
        connectNulls:false,showSymbol:false,lineStyle:{color,width:2},itemStyle:{color}});
    }
  });
  chart.setOption({animation:false,legend:{data:['报价下限','报价上限']},tooltip:{trigger:'axis',renderMode:'richText'},
    grid:{left:65,right:25,top:45,bottom:70},xAxis:{type:'category',data:data.dates,axisLabel:{hideOverlap:true,fontSize:11}},
    yAxis:{type:'value',name:data.currency,scale:true},series});
  window.addEventListener('resize',()=>chart.resize());
});
