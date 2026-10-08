const status=document.querySelector('#status'), button=document.querySelector('#capture');
const labels={
  idle:'还没有采集记录。先打开 ShopHot 并登录，再从正常商品页点击采集。',waiting:'已打开本地接收页，等待校验。此步骤不等于保存，请前往接收页查看进度或具体错误。',
  submitted:'观测已发送，等待本地预览。此步骤不等于保存，请前往接收页核对。',preview:'本地已显示预览。请在该预览页核对并点击确认才保存；此提示不是保存结果。',
  challenge:'当前页面是访问验证。请正常完成登录或验证，进入商品页后再点击采集。',
  login_external:'当前是登录页。请正常登录并进入商品页后再点击采集。',
  catalog:'当前 eBay 商品目录链接没有唯一有效的卖家刊登编号。请打开卖家的 /itm 商品页，或带唯一 iid 的 /p/目录ID 链接再采集。观测未发送。',
  unsupported:'当前不是已支持的 HTTPS 单商品链接。AliExpress /item、OTTO /p、eBay /itm 或 /p/目录ID?iid=唯一刊登编号可识别。AliExpress 未实站验收，eBay 仅单刊登链路通过；范围见安装说明。',
  identity:'无法明确确认当前商品身份。未采集，请等待完整商品页显示。',
  variant:'无法确认所选规格与当前报价一致。请选择规格、等待页面更新后再采集。',
  price:'当前报价不明确、属于区间/划线价，或页面尚未更新。未采集。',
  currency:'无法确认报价币种；仅有 $ 符号不足以确定。未采集。',
  unavailable:'当前商品不可售或库存状态无法确认。未采集。',
  evidence:'标题、报价条件或证据不完整，未采集。',page:'无法读取当前商品页。请回到正常商品页重试。',
  permission:'无法读取此标签页。请刷新正常商品页，重新点击扩展；浏览器内置页无法采集。',
  login_local:'点击“打开 ShopHot / 登录”完成本地登录，再回到商品页重新点击采集。此次未确认保存。',
  offline:'上次本地接收页无法打开。请启动 127.0.0.1:8000 的 ShopHot，打开并登录，再回商品页重新采集。',
  no_response:'尚未收到本地响应。先打开 ShopHot 检查服务和登录，再查看原接收页；若有预览请先核对，若无预览再回商品页重试。此提示不能确认是否保存。',
  bridge_error:'本地未显示有效预览。请查看页面错误，更新 ShopHot 后重新采集。',
  expired:'观测超过10分钟已清除，请回到商品页重新采集。',closed:'本地接收页已关闭，请重新采集。',
  pending_limit:'已有3个待处理接收页。请关闭或完成预览后再采集。',
  extension:'扩展连接失效。请重新加载扩展和商品页后再采集。',
};
const version=document.querySelector('#version');
try {
  const installed=chrome.runtime.getManifest().version;
  version.textContent=typeof installed === 'string' && installed ? `已安装版本 ${installed}` : '无法读取安装版本，请重新加载扩展';
} catch {version.textContent='无法读取安装版本，请重新加载扩展';}
const render=r=>{status.textContent=labels[r?.code] || labels.extension;};
// An older status response must not overwrite the result of a newer user click.
let request=0;
button.addEventListener('click',async()=>{
  if (button.disabled) return;
  const current=++request;
  button.disabled=true;status.textContent='正在读取当前明确报价…';
  try {const result=await chrome.runtime.sendMessage({type:'capture'});if(current === request) render(result);} catch {if(current === request) render({code:'extension'});}
  finally {button.disabled=false;}
});
const initial=request;
try {const result=await chrome.runtime.sendMessage({type:'status'});if(initial === request) render(result);} catch {if(initial === request) render({code:'extension'});}
