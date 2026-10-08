document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('a[href^="#"]').forEach(link=>link.addEventListener('click',()=>{
    const target=document.getElementById(link.getAttribute('href').slice(1));
    if(target)for(let parent=target.parentElement;parent;parent=parent.parentElement){
      if(parent.tagName==='DETAILS')parent.open=true;
    }
  }));
  const button=document.querySelector('.nav-toggle');
  if(button)button.addEventListener('click',()=>{
    const open=button.getAttribute('aria-expanded')!=='true';
    button.setAttribute('aria-expanded',String(open));
    document.querySelector('.topbar').classList.toggle('nav-open',open);
  });
  document.addEventListener('toggle',event=>{
    if(event.target.tagName==='DETAILS' && event.target.open)requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
  },true);
  // 折叠筛选中藏有错误时展开，让键盘和屏幕阅读器都能找到需要修正的字段。
  document.querySelectorAll('details:has(.errorlist)').forEach(details=>details.open=true);
});
