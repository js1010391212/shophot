document.addEventListener('DOMContentLoaded',()=>{
  const panel=document.querySelector('[data-progress-url]');
  if(!panel || panel.dataset.active!=='true')return;
  let attempts=0;
  async function poll(){
    try{
      const response=await fetch(panel.dataset.progressUrl,{headers:{Accept:'application/json'},cache:'no-store'});
      if(!response.ok || response.redirected)throw new Error('Unavailable');
      const data=await response.json();
      document.getElementById('workflow-title').textContent=data.title;
      document.getElementById('workflow-message').textContent=data.message;
      if(data.redirect_url && data.redirect_url.startsWith('/') && !data.redirect_url.startsWith('//')){
        window.location.replace(data.redirect_url);return;
      }
      if(!data.active){window.location.reload();return;}
    }catch(error){document.getElementById('workflow-message').textContent='暂时无法获取进度，可点击“刷新进度”重试。';}
    if(++attempts<240)setTimeout(poll,2500);
    else document.getElementById('workflow-message').textContent='分析耗时较长，请刷新进度查看结果。';
  }
  setTimeout(poll,1500);
});
