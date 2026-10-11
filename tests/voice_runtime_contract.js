/* Browserless contract for primary recognition and progressive transient STT. */
const fs = require("fs");
const vm = require("vm");

class Element {
  constructor() { this.value=""; this.hidden=true; this.disabled=false; this.textContent=""; this.title=""; this.dir=""; this.attrs={}; this.listeners={}; this.classList={add(){},remove(){}}; }
  setAttribute(name,value) { this.attrs[name]=String(value); }
  getAttribute(name) { return this.attrs[name]||""; }
  addEventListener(name,callback) { this.listeners[name]=callback; }
}
function assert(value,message) { if (!value) throw new Error(message); }
function result(text,isFinal) { return {0:{transcript:text},isFinal}; }

function makeRuntime(language, options={}) {
  const mic=new Element(), input=new Element(), status=new Element(), listeners={}, requests=[];
  input.value=options.initialText||"";
  let sends=0, streamStopped=0, sentMessages=[];
  const document={documentElement:{getAttribute:(name)=>name==="lang"?language:""},getElementById:(id)=>({voiceMicBtn:mic,chatInput:input,voiceStatusLine:status})[id]||null,addEventListener:(name,callback)=>{(listeners[name] ||= []).push(callback);},dispatchEvent:(event)=>(listeners[event.type]||[]).forEach((callback)=>callback(event))};
  class MockRecognition { constructor(){MockRecognition.instances.push(this);} start(){this.started=true;} abort(){this.aborted=true; if(this.onend)this.onend();} }
  MockRecognition.instances=[];
  class MockRecorder { constructor(stream,config){this.stream=stream;this.mimeType=(config&&config.mimeType)||"audio/webm";this.state="inactive";MockRecorder.instances.push(this);} start(timeslice){this.state="recording";this.timeslice=timeslice;} stop(){this.state="inactive"; if(this.onstop)this.onstop();} }
  MockRecorder.instances=[]; MockRecorder.isTypeSupported=(type)=>type.indexOf("webm")!==-1;
  const navigator={mediaDevices:{getUserMedia:()=>Promise.resolve({getTracks:()=>[{stop:()=>{streamStopped+=1;}}]})}};
  const window={SpeechRecognition:options.recognition===false?undefined:MockRecognition,webkitSpeechRecognition:undefined,MediaRecorder:options.recorder===false?undefined:MockRecorder,isSecureContext:true,location:{hostname:"localhost"},NeyanChatInput:{isReady:()=>true},NEYAN_VOICE_CONFIG:{partialIntervalMs:2000,maxRecordingMs:15000},sendMessage:()=>{sends+=1;sentMessages.push(input.value);input.value="";},addEventListener(){},setTimeout:()=>1,clearTimeout(){}};
  const Blob=class { constructor(parts,config){this.parts=parts;this.type=config.type;this.size=parts.reduce((size,part)=>size+(part.size||1),0);} };
  const FormData=class { constructor(){this.values=[];} append(...value){this.values.push(value);} };
  let resolveDeferredPartial;
  const fetch=(url,request)=>{requests.push({url,request});const partial=request.body.values.find((v)=>v[0]==="partial");const transcript=partial&&partial[1]==="1"?(language==="ar"?"نص جزئي":"partial text"):(language==="ar"?"أريد حجز رحلة":"book a trip");const response={ok:true,json:()=>Promise.resolve({transcript})};if(options.deferPartial&&partial&&partial[1]==="1")return new Promise((resolve)=>{resolveDeferredPartial=()=>resolve(response);});return Promise.resolve(response);};
  vm.runInNewContext(fs.readFileSync("frontend/static/js/voice.js","utf8"),{window,document,navigator,MediaRecorder:window.MediaRecorder,Blob,FormData,fetch,console},{filename:"voice.js"});
  return {mic,input,status,window,document,MockRecognition,MockRecorder,sends:()=>sends,sentMessages:()=>sentMessages,streamStopped:()=>streamStopped,requests,resolveDeferredPartial:()=>resolveDeferredPartial&&resolveDeferredPartial()};
}

(async function () {
  const merge=makeRuntime("en").window.NeyanVoiceInput.reconcileTranscript;
  assert(merge("I want", "I want to book")==="I want to book","English cumulative partials replace their stable prefix");
  assert(merge("I want", "I want I want to book")==="I want to book","English repeated prefix is collapsed");
  assert(merge("بدي رحلة", "بدي رحلة من عمان")==="بدي رحلة من عمان","Arabic cumulative partials replace their stable prefix");
  assert(merge("بدي رحلة", "رحلة من عمان")==="بدي رحلة من عمان","Arabic overlap is merged without duplication");

  const primary=makeRuntime("en");
  primary.window.NeyanVoiceInput.start();
  const recognition=primary.MockRecognition.instances[0];
  assert(primary.window.NeyanVoiceInput.getState()==="LISTENING_BROWSER","primary starts browser recognition");
  assert(recognition.lang==="en-US","English uses en-US");
  recognition.onresult({resultIndex:0,results:[result("book a trip",true)]}); recognition.onend();
  assert(primary.sends()===1,"final browser transcript enters normal Chat sender once");

  const fallback=makeRuntime("ar",{initialText:"من فضلك"});
  fallback.window.NeyanVoiceInput.start();
  fallback.MockRecognition.instances[0].onerror({error:"network"});
  await Promise.resolve();
  assert(fallback.window.NeyanVoiceInput.getState()==="FALLBACK_RECORDING","network failure switches to fallback recording");
  const recorder=fallback.MockRecorder.instances[0];
  recorder.ondataavailable({data:{size:4}});
  await new Promise((resolve)=>setImmediate(resolve));
  assert(recorder.timeslice===2000,"fallback uses bounded progressive cadence");
  assert(fallback.requests.length===1,"fallback begins with one partial transcription request");
  assert(fallback.input.value==="من فضلك نص جزئي","partial replaces only the voice suffix in the existing composer");
  assert(fallback.sends()===0,"partial transcript never sends Chat");
  recorder.stop();
  await new Promise((resolve)=>setImmediate(resolve));
  assert(fallback.requests.length===2,"fallback sends one partial and one final transcription request");
  assert(fallback.sends()===1,"partials do not send chat and final sends exactly once");
  assert(fallback.sentMessages()[0]==="من فضلك أريد حجز رحلة","final reconciliation preserves typed base text");
  assert(fallback.sends()===1,"fallback transcript enters the same sender exactly once");
  assert(fallback.streamStopped()>0,"fallback stops microphone tracks after transcription");

  const cancelled=makeRuntime("en",{initialText:"keep",deferPartial:true});
  cancelled.window.NeyanVoiceInput.start();
  cancelled.MockRecognition.instances[0].onerror({error:"network"});
  await Promise.resolve();
  cancelled.MockRecorder.instances[0].ondataavailable({data:{size:4}});
  cancelled.window.NeyanVoiceInput.cancel();
  cancelled.resolveDeferredPartial();
  await new Promise((resolve)=>setImmediate(resolve));
  assert(cancelled.input.value==="keep","a stale partial response cannot overwrite text after cancel");
  assert(cancelled.sends()===0,"cancelled partial input never sends Chat");

  const unsupported=makeRuntime("ar",{recognition:false,recorder:false});
  assert(unsupported.mic.disabled,"no recognition/recorder disables Voice without disabling text Chat");
  console.log("voice runtime contract passed");
}()).catch((error)=>{console.error(error);process.exitCode=1;});
