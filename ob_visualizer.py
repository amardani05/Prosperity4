"""
Prosperity Order Book Visualizer v2
====================================
Usage:
    python ob_visualizer.py training_capsule/
    python ob_visualizer.py prices.csv trades.csv
    python ob_visualizer.py
 
Ctrl+C to stop. Scroll to zoom, drag to pan, hover for details.
"""
import http.server, json, os, sys, threading, webbrowser, glob
 
PORT = 8847
 
def read_csv_files(args):
    price_data, trade_data = [], []
    paths = []
    for arg in args:
        if os.path.isdir(arg): paths.extend(glob.glob(os.path.join(arg, '*.csv')))
        elif os.path.isfile(arg): paths.append(arg)
    for path in paths:
        try:
            with open(path,'r') as f: content = f.read()
            if 'mid_price' in content: price_data.append(content); print(f"  prices: {path}")
            elif 'buyer' in content or 'symbol' in content: trade_data.append(content); print(f"  trades: {path}")
        except Exception as e: print(f"  skip {path}: {e}")
    return price_data, trade_data
 
HTML = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Prosperity OB</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=DM+Sans:wght@400;500;600;700&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0b0d12;--s1:#10131a;--s2:#161a24;--brd:#1e222e;--t1:#9aa5b8;--t2:#5c6478;--t3:#3a3f50;--w:#dce3ee;
--bid:#2dd4a0;--ask:#ef5565;--mid:#5ba4f5;--trd:#e8b84a;--acc:#7c6ff7}
body{font-family:'IBM Plex Mono',monospace;background:var(--bg);color:var(--t1);overflow:hidden;height:100vh}
.app{display:grid;grid-template-rows:38px 1fr;height:100vh}
.hdr{display:flex;align-items:center;gap:10px;padding:0 12px;background:var(--s1);border-bottom:1px solid var(--brd);font-size:11px;overflow-x:auto}
.hdr h1{font-family:'DM Sans',sans-serif;font-size:13px;font-weight:700;color:var(--w);letter-spacing:.3px;white-space:nowrap}
.hdr .sep{width:1px;height:18px;background:var(--brd);flex-shrink:0}
.hdr label{cursor:pointer;color:var(--acc);border:1px solid var(--acc);padding:2px 8px;border-radius:3px;font-size:10px;white-space:nowrap}
.hdr label:hover{background:var(--acc);color:#fff}
.hdr input[type=file]{display:none}
.hdr select{background:var(--bg);color:var(--t1);border:1px solid var(--brd);padding:2px 6px;border-radius:3px;font-family:inherit;font-size:10px}
.hdr .info{color:var(--t2);white-space:nowrap;font-size:10px}
.hdr .info b{color:var(--w);font-weight:500}
.main{display:grid;grid-template-columns:1fr 240px;grid-template-rows:1fr 100px;overflow:hidden}
.chart{position:relative;background:var(--bg);border-right:1px solid var(--brd);border-bottom:1px solid var(--brd);cursor:crosshair}
.chart canvas{position:absolute;top:0;left:0}
.layers{position:absolute;top:6px;left:8px;z-index:10;display:flex;gap:3px}
.layers button{background:var(--s2);border:1px solid var(--brd);color:var(--t2);font-family:inherit;font-size:9px;padding:2px 7px;border-radius:3px;cursor:pointer;transition:.1s}
.layers button:hover{color:var(--t1)}
.layers button.on{border-color:var(--t2);color:var(--w)}
.layers button .dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:3px;vertical-align:middle}
.modes{position:absolute;top:6px;right:8px;z-index:10;display:flex;gap:3px}
.modes button{background:var(--s2);border:1px solid var(--brd);color:var(--t2);font-family:inherit;font-size:9px;padding:2px 7px;border-radius:3px;cursor:pointer}
.modes button.active{color:var(--acc);border-color:var(--acc)}
.sld{position:absolute;bottom:0;left:0;right:0;height:20px;background:rgba(16,19,26,.95);display:flex;align-items:center;padding:0 8px;z-index:10}
.sld input{flex:1;-webkit-appearance:none;height:2px;background:var(--brd);border-radius:1px;outline:none}
.sld input::-webkit-slider-thumb{-webkit-appearance:none;width:8px;height:8px;background:var(--acc);border-radius:50%;cursor:pointer}
.sld span{font-size:8px;color:var(--t3);min-width:60px;text-align:center}
.ob{background:var(--s1);border-bottom:1px solid var(--brd);padding:8px;overflow-y:auto;font-size:10px}
.ob h2{font-family:'DM Sans',sans-serif;font-size:10px;font-weight:600;color:var(--t2);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}
.ob-stats{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:8px}
.ob-stat .lbl{font-size:8px;color:var(--t3);text-transform:uppercase;letter-spacing:.5px}
.ob-stat .val{font-size:12px;font-weight:500}
.ob-stat .val.g{color:var(--bid)}.ob-stat .val.r{color:var(--ask)}.ob-stat .val.b{color:var(--mid)}.ob-stat .val.y{color:var(--trd)}
.ob-level{display:flex;align-items:center;height:18px;position:relative;margin:1px 0}
.ob-level .bar{position:absolute;top:1px;bottom:1px;border-radius:2px;opacity:.15}
.ob-level .bar.b{background:var(--bid);right:0}.ob-level .bar.a{background:var(--ask);right:0}
.ob-level .price{position:relative;z-index:1;width:55%;text-align:right;padding-right:6px;font-size:10px}
.ob-level .price.b{color:var(--bid)}.ob-level .price.a{color:var(--ask)}
.ob-level .vol{position:relative;z-index:1;width:45%;font-size:10px;color:var(--t2)}
.ob-sep{height:1px;background:var(--brd);margin:3px 0}
.ob-mid-lbl{text-align:center;font-size:10px;color:var(--mid);font-weight:600;padding:1px 0}
.ob-trades{margin-top:8px;border-top:1px solid var(--brd);padding-top:6px}
.ob-trades .tr-title{font-size:8px;color:var(--t3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.ob-trade{display:flex;gap:6px;font-size:9px;padding:1px 0;color:var(--t2)}
.ob-trade .tp{min-width:36px}.ob-trade .tprice{font-weight:500}
.ob-trade .tprice.up{color:var(--bid)}.ob-trade .tprice.dn{color:var(--ask)}
.ob-trade .tq{color:var(--trd)}
.btm{grid-column:1/-1;background:var(--s1);position:relative;border-top:1px solid var(--brd)}
.btm canvas{position:absolute;top:0;left:0}
.tip{position:fixed;background:var(--s2);border:1px solid var(--brd);padding:5px 8px;font-size:9px;border-radius:3px;pointer-events:none;z-index:100;display:none;line-height:1.5}
.tip .r{display:flex;gap:6px}.tip .l{color:var(--t3)}.tip .v{color:var(--w);font-weight:500}
.drop{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:200;font-family:'DM Sans',sans-serif;font-size:18px;color:var(--acc);border:2px dashed var(--acc)}
</style></head><body>
<div class="app">
<div class="hdr">
  <h1>OB VIEWER</h1><div class="sep"></div>
  <label>Prices<input type="file" id="pf" accept=".csv"></label>
  <label>Trades<input type="file" id="tf" accept=".csv"></label>
  <div class="sep"></div>
  <select id="prodSel"><option>—</option></select>
  <div class="sep"></div>
  <div class="info" id="hdrInfo">Drop or load CSVs</div>
</div>
<div class="main">
  <div class="chart" id="chart">
    <canvas id="cc"></canvas>
    <div class="layers" id="layerBtns">
      <button class="on" data-layer="mid"><span class="dot" style="background:var(--mid)"></span>Mid</button>
      <button class="on" data-layer="ba"><span class="dot" style="background:var(--bid)"></span>Bid/Ask</button>
      <button data-layer="trades"><span class="dot" style="background:var(--trd)"></span>Trades</button>
      <button data-layer="fill">Fill</button>
    </div>
    <div class="modes" id="modeBtns">
      <button class="active" data-mode="price">Price</button>
      <button data-mode="spread">Spread</button>
      <button data-mode="imbalance">Imb</button>
    </div>
    <div class="sld"><span id="sL">—</span><input type="range" id="tSlider" min="0" max="1000" value="0"><span id="sR">—</span></div>
  </div>
  <div class="ob" id="obPanel">
    <h2>Order Book</h2>
    <div id="obC"></div>
  </div>
  <div class="btm" id="btm"><canvas id="bc"></canvas></div>
</div>
</div>
<div class="tip" id="tip"></div>
<div class="drop" id="dz">Drop CSV files</div>
 
<script>
let P={},T={},prod=null,mode='price',vS=0,vE=1,hI=-1,oI=0;
let layers={mid:true,ba:true,trades:false,fill:false};
 
function parseP(t){const ls=t.trim().split('\n'),d={};for(let i=1;i<ls.length;i++){const c=ls[i].split(';'),p=c[2];if(!d[p])d[p]=[];d[p].push({t:+c[1],b1:+c[3]||0,bv1:+c[4]||0,b2:+c[5]||0,bv2:+c[6]||0,b3:+c[7]||0,bv3:+c[8]||0,a1:+c[9]||0,av1:+c[10]||0,a2:+c[11]||0,av2:+c[12]||0,a3:+c[13]||0,av3:+c[14]||0,mid:+c[15]})}return d}
function parseT(t){const ls=t.trim().split('\n'),d={};for(let i=1;i<ls.length;i++){const c=ls[i].split(';'),p=c[3];if(!d[p])d[p]=[];d[p].push({t:+c[0],buyer:c[1],seller:c[2],p:+c[5],q:+c[6]})}return d}
function merge(e,n){for(const k in n){if(!e[k])e[k]=[];e[k]=e[k].concat(n[k]);e[k].sort((a,b)=>a.t-b.t)}}
function load(txt){if(txt.includes('mid_price'))merge(P,parseP(txt));else if(txt.includes('buyer')||txt.includes('symbol'))merge(T,parseT(txt));upProd()}
 
document.getElementById('pf').onchange=e=>{const f=e.target.files[0];if(f)f.text().then(load)};
document.getElementById('tf').onchange=e=>{const f=e.target.files[0];if(f)f.text().then(load)};
const dz=document.getElementById('dz');
document.body.addEventListener('dragover',e=>{e.preventDefault();dz.style.display='flex'});
dz.addEventListener('dragleave',()=>dz.style.display='none');
dz.addEventListener('drop',e=>{e.preventDefault();dz.style.display='none';for(const f of e.dataTransfer.files)f.text().then(load)});
 
function upProd(){const s=document.getElementById('prodSel');s.innerHTML='';Object.keys(P).forEach(p=>{const o=document.createElement('option');o.value=p;o.textContent=p;s.appendChild(o)});if(!prod||!P[prod])prod=Object.keys(P)[0]||null;s.value=prod;vS=0;vE=1;R()}
document.getElementById('prodSel').onchange=e=>{prod=e.target.value;vS=0;vE=1;R()};
document.getElementById('layerBtns').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const l=b.dataset.layer;layers[l]=!layers[l];b.classList.toggle('on',layers[l]);R()});
document.getElementById('modeBtns').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;document.querySelectorAll('.modes button').forEach(x=>x.classList.remove('active'));b.classList.add('active');mode=b.dataset.mode;R()});
 
function gV(){if(!prod||!P[prod])return{d:[],tr:[]};const d=P[prod],s=Math.floor(vS*d.length),e=Math.ceil(vE*d.length),vis=d.slice(s,e);if(!vis.length)return{d:[],tr:[]};const t0=vis[0].t,t1=vis[vis.length-1].t;return{d:vis,tr:(T[prod]||[]).filter(tr=>tr.t>=t0&&tr.t<=t1)}}
 
function R(){rC();rB();rO();rH()}
 
function rC(){
  const el=document.getElementById('chart'),cv=document.getElementById('cc'),W=el.clientWidth,H=el.clientHeight-20;
  cv.width=W;cv.height=H;const c=cv.getContext('2d');c.clearRect(0,0,W,H);
  const{d,tr}=gV();if(!d.length)return;
  const p={t:16,r:52,b:16,l:8},cw=W-p.l-p.r,ch=H-p.t-p.b;
  let vals,mn,mx;
  if(mode==='price'){const ap=[];d.forEach(v=>{ap.push(v.mid);if(layers.ba){if(v.b1)ap.push(v.b1);if(v.a1)ap.push(v.a1)}});if(layers.trades)tr.forEach(t=>ap.push(t.p));mn=Math.min(...ap)-1;mx=Math.max(...ap)+1}
  else if(mode==='spread'){vals=d.map(v=>v.a1&&v.b1?v.a1-v.b1:0);mn=Math.min(...vals)-1;mx=Math.max(...vals)+1}
  else{vals=d.map(v=>{const b=v.bv1+v.bv2+v.bv3,a=v.av1+v.av2+v.av3;return b+a>0?(b-a)/(b+a):0});mn=-0.35;mx=0.35}
  const rng=mx-mn||1,X=i=>p.l+cw*i/(d.length-1||1),Y=v=>p.t+ch*(1-(v-mn)/rng);
 
  c.strokeStyle='#141720';c.lineWidth=1;
  for(let i=0;i<5;i++){const gy=p.t+ch*i/4;c.beginPath();c.moveTo(p.l,gy);c.lineTo(W-p.r,gy);c.stroke();c.fillStyle='#2d3344';c.font='8px IBM Plex Mono';c.textAlign='right';c.fillText(mode==='imbalance'?(mx-rng*i/4).toFixed(2):(mx-rng*i/4).toFixed(1),W-2,gy+3)}
 
  if(mode==='price'){
    if(layers.fill&&layers.ba){c.fillStyle='rgba(91,164,245,0.03)';c.beginPath();d.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v.b1||v.mid)):c.lineTo(X(i),Y(v.b1||v.mid))});for(let i=d.length-1;i>=0;i--)c.lineTo(X(i),Y(d[i].a1||d[i].mid));c.closePath();c.fill()}
    if(layers.ba){c.strokeStyle='rgba(45,212,160,0.25)';c.lineWidth=0.8;c.beginPath();d.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v.b1||v.mid)):c.lineTo(X(i),Y(v.b1||v.mid))});c.stroke();c.strokeStyle='rgba(239,85,101,0.25)';c.beginPath();d.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v.a1||v.mid)):c.lineTo(X(i),Y(v.a1||v.mid))});c.stroke()}
    if(layers.mid){c.strokeStyle='rgba(91,164,245,0.7)';c.lineWidth=1.2;c.beginPath();d.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v.mid)):c.lineTo(X(i),Y(v.mid))});c.stroke()}
    if(layers.trades&&tr.length){const t0=d[0].t,t1=d[d.length-1].t,ts=t1-t0||1;tr.forEach(t=>{const tx=p.l+cw*(t.t-t0)/ts,ty=Y(t.p);if(ty<p.t||ty>H-p.b)return;const r=Math.min(1.5+t.q*0.5,6);c.beginPath();c.arc(tx,ty,r,0,Math.PI*2);c.fillStyle='rgba(232,184,74,0.5)';c.fill()})}
  }else{const col=mode==='spread'?'rgba(124,111,247,0.7)':'rgba(232,184,74,0.7)';c.strokeStyle=col;c.lineWidth=1;c.beginPath();vals.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v)):c.lineTo(X(i),Y(v))});c.stroke();if(mode==='imbalance'){c.strokeStyle='#1e222e';c.lineWidth=1;c.setLineDash([3,3]);c.beginPath();c.moveTo(p.l,Y(0));c.lineTo(W-p.r,Y(0));c.stroke();c.setLineDash([])}}
 
  if(hI>=0&&hI<d.length){const hx=X(hI);c.strokeStyle='rgba(255,255,255,0.08)';c.lineWidth=1;c.beginPath();c.moveTo(hx,p.t);c.lineTo(hx,H-p.b);c.stroke();if(mode==='price'){const v=d[hI];c.beginPath();c.moveTo(p.l,Y(v.mid));c.lineTo(W-p.r,Y(v.mid));c.stroke();c.fillStyle='#161a24';c.fillRect(W-p.r,Y(v.mid)-7,p.r,14);c.fillStyle='#5ba4f5';c.font='9px IBM Plex Mono';c.textAlign='right';c.fillText(v.mid.toFixed(1),W-2,Y(v.mid)+3)}}
  document.getElementById('sL').textContent='t='+d[0].t;document.getElementById('sR').textContent='t='+d[d.length-1].t;
}
 
function rB(){const el=document.getElementById('btm'),cv=document.getElementById('bc'),W=el.clientWidth,H=el.clientHeight;cv.width=W;cv.height=H;const c=cv.getContext('2d');c.clearRect(0,0,W,H);const{d}=gV();if(!d.length)return;const p={t:14,r:52,b:4,l:8},cw=W-p.l-p.r,ch=H-p.t-p.b;c.fillStyle='#2d3344';c.font='8px IBM Plex Mono';c.fillText('SPREAD',p.l,10);const sp=d.map(v=>v.a1&&v.b1?v.a1-v.b1:0),smn=Math.min(...sp),smx=Math.max(...sp),sr=smx-smn||1;c.strokeStyle='rgba(124,111,247,0.5)';c.lineWidth=1;c.beginPath();sp.forEach((s,i)=>{const sx=p.l+cw*i/(sp.length-1||1),sy=p.t+ch*(1-(s-smn)/sr);i===0?c.moveTo(sx,sy):c.lineTo(sx,sy)});c.stroke();if(hI>=0&&hI<d.length){const hx=p.l+cw*hI/(d.length-1||1);c.strokeStyle='rgba(255,255,255,0.08)';c.lineWidth=1;c.beginPath();c.moveTo(hx,p.t);c.lineTo(hx,H-p.b);c.stroke()}}
 
function rO(){const{d,tr}=gV();const el=document.getElementById('obC');if(!d.length){el.innerHTML='<div style="color:var(--t3);padding:20px;text-align:center">Load data</div>';return}const idx=Math.min(oI,d.length-1),v=d[idx];const bids=[[v.b1,v.bv1],[v.b2,v.bv2],[v.b3,v.bv3]].filter(x=>x[0]>0),asks=[[v.a1,v.av1],[v.a2,v.av2],[v.a3,v.av3]].filter(x=>x[0]>0),mxV=Math.max(...bids.map(b=>b[1]),...asks.map(a=>a[1]),1),spr=v.a1&&v.b1?(v.a1-v.b1):0,bvT=v.bv1+v.bv2+v.bv3,avT=v.av1+v.av2+v.av3,imb=bvT+avT>0?((bvT-avT)/(bvT+avT)*100).toFixed(1):'0';
let h=`<div class="ob-stats"><div class="ob-stat"><div class="lbl">Time</div><div class="val">${v.t}</div></div><div class="ob-stat"><div class="lbl">Mid</div><div class="val b">${v.mid}</div></div><div class="ob-stat"><div class="lbl">Spread</div><div class="val">${spr}</div></div><div class="ob-stat"><div class="lbl">Imbalance</div><div class="val y">${imb}%</div></div></div>`;
asks.slice().reverse().forEach(([p,vol])=>{h+=`<div class="ob-level"><div class="bar a" style="width:${vol/mxV*85}%"></div><div class="price a">${p}</div><div class="vol">${vol}</div></div>`});
h+=`<div class="ob-sep"></div><div class="ob-mid-lbl">${v.mid.toFixed(1)}</div><div class="ob-sep"></div>`;
bids.forEach(([p,vol])=>{h+=`<div class="ob-level"><div class="bar b" style="width:${vol/mxV*85}%"></div><div class="price b">${p}</div><div class="vol">${vol}</div></div>`});
const near=(T[prod]||[]).filter(t=>Math.abs(t.t-v.t)<300).slice(0,6);
if(near.length){h+='<div class="ob-trades"><div class="tr-title">Trades</div>';near.forEach(t=>{const cls=t.p>=v.mid?'up':'dn';h+=`<div class="ob-trade"><span class="tp">t=${t.t}</span><span class="tprice ${cls}">${t.p}</span><span class="tq">\u00d7${t.q}</span></div>`});h+='</div>'}
el.innerHTML=h}
 
function rH(){const info=document.getElementById('hdrInfo');if(!prod||!P[prod]){info.innerHTML='Drop or load CSVs';return}const d=P[prod],t=T[prod]||[];info.innerHTML=`<b>${prod}</b> \u00b7 ${d.length.toLocaleString()} ticks \u00b7 ${t.length} trades`}
 
const chart=document.getElementById('chart'),tip=document.getElementById('tip');
chart.addEventListener('mousemove',e=>{if(!prod||!P[prod])return;const{d}=gV();if(!d.length)return;const rect=chart.getBoundingClientRect(),mx=e.clientX-rect.left,pl=8,pr=52,cw=rect.width-pl-pr,idx=Math.round((mx-pl)/cw*(d.length-1));if(idx<0||idx>=d.length){tip.style.display='none';return}hI=idx;oI=idx;rC();rB();rO();const v=d[idx],spr=v.a1&&v.b1?v.a1-v.b1:0,bv=v.bv1+v.bv2+v.bv3,av=v.av1+v.av2+v.av3,imb=bv+av>0?((bv-av)/(bv+av)*100).toFixed(1):'0';
tip.innerHTML=`<div class="r"><span class="l">t</span><span class="v">${v.t}</span></div><div class="r"><span class="l">mid</span><span class="v" style="color:var(--mid)">${v.mid}</span></div><div class="r"><span class="l">bid</span><span class="v" style="color:var(--bid)">${v.b1}\u00d7${v.bv1}</span></div><div class="r"><span class="l">ask</span><span class="v" style="color:var(--ask)">${v.a1}\u00d7${v.av1}</span></div><div class="r"><span class="l">spr</span><span class="v">${spr}</span></div><div class="r"><span class="l">imb</span><span class="v" style="color:var(--trd)">${imb}%</span></div>`;
tip.style.display='block';tip.style.left=Math.min(e.clientX+10,window.innerWidth-220)+'px';tip.style.top=(e.clientY-50)+'px'});
chart.addEventListener('mouseleave',()=>{tip.style.display='none';hI=-1;rC();rB()});
chart.addEventListener('wheel',e=>{e.preventDefault();if(!prod||!P[prod])return;const rect=chart.getBoundingClientRect(),mx=(e.clientX-rect.left)/rect.width,ctr=vS+(vE-vS)*mx,z=e.deltaY>0?1.15:0.87;let half=(vE-vS)/2*z;half=Math.max(0.003,Math.min(0.5,half));vS=Math.max(0,ctr-half);vE=Math.min(1,ctr+half);if(vE-vS<0.003)vE=vS+0.003;R()},{passive:false});
let drag=false,dX=0,dVS=0,dVE=0;
chart.addEventListener('mousedown',e=>{if(e.button===0){drag=true;dX=e.clientX;dVS=vS;dVE=vE}});
window.addEventListener('mousemove',e=>{if(!drag)return;const rect=chart.getBoundingClientRect(),dx=(e.clientX-dX)/rect.width,span=dVE-dVS,shift=-dx*span;vS=Math.max(0,Math.min(1-span,dVS+shift));vE=vS+span;R()});
window.addEventListener('mouseup',()=>{drag=false});
document.getElementById('tSlider').addEventListener('input',e=>{const{d}=gV();oI=Math.round(e.target.value/1000*(d.length-1));rO();hI=oI;rC();rB()});
window.addEventListener('resize',R);
 
const EP=__PRICES_DATA__,ET=__TRADES_DATA__;
if(EP.length)EP.forEach(t=>load(t));if(ET.length)ET.forEach(t=>load(t));
</script></body></html>'''
 
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s,*a,html=None,**k):s.html=html;super().__init__(*a,**k)
    def do_GET(s):
        if s.path in('/','index.html'):s.send_response(200);s.send_header('Content-Type','text/html;charset=utf-8');s.end_headers();s.wfile.write(s.html.encode('utf-8'))
        else:super().do_GET()
    def log_message(s,*a):pass
 
def main():
    pt,tt=[],[]
    if len(sys.argv)>1:print("Loading...");pt,tt=read_csv_files(sys.argv[1:])
    html=HTML.replace('__PRICES_DATA__',json.dumps(pt)).replace('__TRADES_DATA__',json.dumps(tt))
    def hf(*a,**k):return H(*a,html=html,**k)
    srv=http.server.HTTPServer(('127.0.0.1',PORT),hf)
    url=f'http://127.0.0.1:{PORT}'
    print(f"\n  OB Viewer -> {url}\n  Ctrl+C to stop\n")
    threading.Timer(0.5,lambda:webbrowser.open(url)).start()
    try:srv.serve_forever()
    except KeyboardInterrupt:print("\n  Stopped.");srv.shutdown()
 
if __name__=='__main__':main()
 