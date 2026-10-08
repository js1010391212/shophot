document.addEventListener('DOMContentLoaded',()=>{
  const source=document.getElementById('review-analysis-data');
  if(!source || !window.echarts) return;
  const data=JSON.parse(source.textContent), charts=[];
  const rating=echarts.init(document.getElementById('review-rating-chart'),null,{renderer:'svg'});
  rating.setOption({animation:false,tooltip:{trigger:'axis',renderMode:'richText'},grid:{left:45,right:15,bottom:55,top:25},
    xAxis:{type:'category',data:data.labels,axisLabel:{fontSize:11}},yAxis:{type:'value',minInterval:1,name:'评论数'},
    series:[{type:'bar',data:data.counts,barMaxWidth:60,itemStyle:{color:'#6366f1'},label:{show:true,position:'top'}}]});
  charts.push(rating);
  const element=document.getElementById('review-keyword-chart');
  if(element){
    element.style.height=Math.max(160,data.words.length*32+50)+'px';
    const keyword=echarts.init(element,null,{renderer:'svg'});
    keyword.setOption({animation:false,tooltip:{trigger:'axis',renderMode:'richText'},grid:{left:90,right:35,top:15,bottom:30},
      xAxis:{type:'value',minInterval:1,name:'评论数'},yAxis:{type:'category',data:data.words,inverse:true,axisLabel:{width:75,overflow:'truncate'}},
      series:[{type:'bar',data:data.frequencies,barMaxWidth:25,itemStyle:{color:'#818cf8'},label:{show:true,position:'right'}}]});
    keyword.on('click',p=>{
      document.querySelectorAll('.product-review.tree-highlight').forEach(row=>row.classList.remove('tree-highlight'));
      const indices=data.evidence[p.dataIndex] || [];
      const rows=indices.map(index=>document.getElementById('review-sample-'+index)).filter(Boolean);
      rows.forEach(row=>row.classList.add('tree-highlight'));
      if(rows[0]){rows[0].scrollIntoView({behavior:'smooth',block:'center'});rows[0].focus();}
    });
    charts.push(keyword);
  }
  window.addEventListener('resize',()=>charts.forEach(chart=>chart.resize()));
});
