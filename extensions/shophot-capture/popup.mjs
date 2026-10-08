const status=document.querySelector('#status'), button=document.querySelector('#capture');
const labels={
  idle:'准备采集。支持范围和未验收平台见安装说明。',waiting:'已打开本地接收页，等待校验。尚未保存。',
  submitted:'观测已发送，等待本地预览。尚未保存。',preview:'本地已显示预览。核对后点击确认才保存。',
  challenge:'当前页面是访问验证。请正常完成登录或验证，进入商品页后再点击采集。',
  login_external:'当前是登录页。请正常登录并进入商品页后再点击采集。',
  catalog:'当前 eBay 商品目录链接没有唯一有效的卖家刊登编号。请打开卖家的商品详情页再采集。观测未发送。',
  unsupported:'当前不是已支持的 HTTPS 单商品链接。AliExpress /item、OTTO /p、eBay /itm 可识别；各平台实站状态见说明。',
  identity:'无法明确确认当前商品身份。未采集，请等待完整商品页显示。',
  variant:'无法确认所选规格与当前报价一致。请选择规格、等待页面更新后再采集。',
  price:'当前报价不明确、属于区间/划线价，或页面尚未更新。未采集。',
  currency:'无法确认报价币种；仅有 $ 符号不足以确定。未采集。',
  unavailable:'当前商品不可售或库存状态无法确认。未采集。',
  evidence:'标题、报价条件或证据不完整，未采集。',page:'无法读取当前商品页。请回到正常商品页重试。',
  permission:'无法读取此标签页。请刷新正常商品页，重新点击扩展；浏览器内置页无法采集。',
  login_local:'请先登录本地 ShopHot，再回到商品页重新点击采集。',
  offline:'本地接收页无法打开。请确认 ShopHot 在 127.0.0.1:8000 运行，然后重新采集。',
  no_response:'尚未收到本地响应。请检查 ShopHot 服务和登录状态；此次没有确认保存。',
  bridge_error:'本地未显示有效预览。请查看页面错误，更新 ShopHot 后重新采集。',
  expired:'观测超过10分钟已清除，请回到商品页重新采集。',closed:'本地接收页已关闭，请重新采集。',
  pending_limit:'已有3个待处理接收页。请关闭或完成预览后再采集。',
  extension:'扩展连接失效。请重新加载扩展和商品页后再采集。',
};
const render=r=>{status.textContent=labels[r?.code] || labels.extension;};
button.addEventListener('click',async()=>{
  button.disabled=true;status.textContent='正在读取当前明确报价…';
  try {render(await chrome.runtime.sendMessage({type:'capture'}));} catch {render({code:'extension'});}
  finally {button.disabled=false;}
});
try {render(await chrome.runtime.sendMessage({type:'status'}));} catch {render({code:'extension'});}
