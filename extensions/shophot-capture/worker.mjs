import {createController} from './controller.mjs';
import {readPublicPage} from './dom-reader.mjs';

const controller=createController(chrome,readPublicPage);
const initialized=chrome.storage.session.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
let queue=initialized;
const serial=fn => {
  const next=queue.then(fn); queue=next.catch(()=>{}); return next;
};
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  serial(()=>controller.handle(message,sender)).then(respond,()=>respond({ok:false,code:'extension'}));
  return true;
});
chrome.tabs.onRemoved.addListener(id=>{serial(()=>controller.removed(id));});
chrome.tabs.onUpdated.addListener((id,changes)=>{if(changes.url) serial(()=>controller.navigated(id,changes.url));});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='capture-expiry') serial(()=>controller.prune());});
chrome.runtime.onInstalled.addListener(()=>{chrome.alarms.create('capture-expiry',{periodInMinutes:1});});
chrome.runtime.onStartup.addListener(()=>{chrome.alarms.create('capture-expiry',{periodInMinutes:1});});
chrome.alarms.create('capture-expiry',{periodInMinutes:1});
serial(()=>controller.prune());
