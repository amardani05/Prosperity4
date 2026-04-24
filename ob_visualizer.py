"""
Prosperity Order Book Visualizer v3
====================================
Usage:
    python ob_visualizer.py ROUND_3/
    python ob_visualizer.py prices.csv trades.csv
    python ob_visualizer.py

Tabs: Price | Smile.  Smile tab fits BS implied vol per strike/tick and
overlays a quadratic vol-smile fit.  Drop CSVs on the page to reload.
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
:root{--bg:#ffffff;--s1:#f6f7fa;--s2:#eceff5;--brd:#d6dbe5;--grd:#e7ebf2;--t1:#3a4050;--t2:#6b7285;--t3:#a5abbb;--w:#14161e;
--bid:#0ea572;--ask:#dc3e50;--mid:#3b7edb;--trd:#c78a1c;--acc:#6b5de0}
body{font-family:'IBM Plex Mono',monospace;background:var(--bg);color:var(--t1);overflow:hidden;height:100vh}
.app{display:grid;grid-template-rows:40px 1fr;height:100vh}
.hdr{display:flex;align-items:center;gap:10px;padding:0 12px;background:var(--s1);border-bottom:1px solid var(--brd);font-size:11px;overflow-x:auto}
.hdr h1{font-family:'DM Sans',sans-serif;font-size:13px;font-weight:700;color:var(--w);letter-spacing:.3px;white-space:nowrap}
.hdr .sep{width:1px;height:20px;background:var(--brd);flex-shrink:0}
.hdr label.file{cursor:pointer;color:var(--acc);border:1px solid var(--acc);padding:2px 8px;border-radius:3px;font-size:10px;white-space:nowrap;background:var(--bg)}
.hdr label.file:hover{background:var(--acc);color:#fff}
.hdr input[type=file]{display:none}
.hdr select,.hdr input[type=number]{background:var(--bg);color:var(--t1);border:1px solid var(--brd);padding:3px 6px;border-radius:3px;font-family:inherit;font-size:10px}
.hdr .lbl{color:var(--t2);font-size:10px;white-space:nowrap}
.hdr .info{color:var(--t2);white-space:nowrap;font-size:10px;margin-left:auto}
.hdr .info b{color:var(--w);font-weight:600}
.tabs{display:flex;gap:2px}
.tab{background:var(--s2);border:1px solid var(--brd);color:var(--t2);font-family:inherit;font-size:11px;padding:4px 12px;border-radius:3px;cursor:pointer;font-weight:500}
.tab:hover{color:var(--t1)}
.tab.active{color:var(--acc);border-color:var(--acc);background:var(--bg)}
.ctrl{display:flex;align-items:center;gap:8px}
.main{display:grid;grid-template-columns:1fr 240px;grid-template-rows:1fr 110px;overflow:hidden}
.chart{position:relative;background:var(--bg);border-right:1px solid var(--brd);border-bottom:1px solid var(--brd);cursor:crosshair}
.chart canvas{position:absolute;top:0;left:0}
.layers{position:absolute;top:6px;left:8px;z-index:10;display:flex;gap:3px}
.layers button{background:var(--s1);border:1px solid var(--brd);color:var(--t2);font-family:inherit;font-size:9px;padding:3px 8px;border-radius:3px;cursor:pointer;transition:.1s}
.layers button:hover{color:var(--t1)}
.layers button.on{border-color:var(--t1);color:var(--w);background:var(--bg)}
.layers button .dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:3px;vertical-align:middle}
.modes{position:absolute;top:6px;right:8px;z-index:10;display:flex;gap:3px}
.modes button{background:var(--s1);border:1px solid var(--brd);color:var(--t2);font-family:inherit;font-size:9px;padding:3px 8px;border-radius:3px;cursor:pointer}
.modes button.active{color:var(--acc);border-color:var(--acc);background:var(--bg)}
.sld{position:absolute;bottom:0;left:0;right:0;height:22px;background:rgba(246,247,250,.95);display:flex;align-items:center;padding:0 8px;z-index:10;border-top:1px solid var(--brd)}
.sld input{flex:1;-webkit-appearance:none;height:2px;background:var(--brd);border-radius:1px;outline:none}
.sld input::-webkit-slider-thumb{-webkit-appearance:none;width:10px;height:10px;background:var(--acc);border-radius:50%;cursor:pointer}
.sld span{font-size:9px;color:var(--t2);min-width:64px;text-align:center}
.ob{background:var(--s1);border-bottom:1px solid var(--brd);padding:10px;overflow-y:auto;font-size:10px}
.ob h2{font-family:'DM Sans',sans-serif;font-size:10px;font-weight:600;color:var(--t2);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px}
.ob-stats{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:10px}
.ob-stat .lbl{font-size:8px;color:var(--t3);text-transform:uppercase;letter-spacing:.5px}
.ob-stat .val{font-size:12px;font-weight:500;color:var(--t1)}
.ob-stat .val.g{color:var(--bid)}.ob-stat .val.r{color:var(--ask)}.ob-stat .val.b{color:var(--mid)}.ob-stat .val.y{color:var(--trd)}
.ob-level{display:flex;align-items:center;height:18px;position:relative;margin:1px 0}
.ob-level .bar{position:absolute;top:1px;bottom:1px;border-radius:2px;opacity:.18}
.ob-level .bar.b{background:var(--bid);right:0}.ob-level .bar.a{background:var(--ask);right:0}
.ob-level .price{position:relative;z-index:1;width:55%;text-align:right;padding-right:6px;font-size:10px;font-weight:500}
.ob-level .price.b{color:var(--bid)}.ob-level .price.a{color:var(--ask)}
.ob-level .vol{position:relative;z-index:1;width:45%;font-size:10px;color:var(--t2)}
.ob-sep{height:1px;background:var(--brd);margin:4px 0}
.ob-mid-lbl{text-align:center;font-size:11px;color:var(--mid);font-weight:600;padding:2px 0}
.ob-trades{margin-top:10px;border-top:1px solid var(--brd);padding-top:8px}
.ob-trades .tr-title{font-size:8px;color:var(--t3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.ob-trade{display:flex;gap:6px;font-size:9px;padding:1px 0;color:var(--t2)}
.ob-trade .tp{min-width:42px}.ob-trade .tprice{font-weight:500}
.ob-trade .tprice.up{color:var(--bid)}.ob-trade .tprice.dn{color:var(--ask)}
.ob-trade .tq{color:var(--trd)}
.btm{grid-column:1/-1;background:var(--s1);position:relative;border-top:1px solid var(--brd)}
.btm canvas{position:absolute;top:0;left:0}
.smile{display:grid;grid-template-rows:1fr;height:100%;overflow:hidden;background:var(--s1)}
.smile-chart{position:relative;background:var(--bg);overflow:hidden;margin:12px;border:1px solid var(--brd);border-radius:4px}
.smile-chart canvas{position:absolute;top:0;left:0;cursor:crosshair}
.legend{position:absolute;top:12px;right:16px;background:rgba(255,255,255,0.92);border:1px solid var(--brd);padding:8px 12px;border-radius:3px;font-size:10px;z-index:5;max-height:calc(100% - 24px);overflow-y:auto;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.legend .lg-title{font-family:'DM Sans',sans-serif;font-weight:600;font-size:10px;color:var(--t2);text-transform:uppercase;letter-spacing:.6px;margin-bottom:5px}
.legend .lg-row{display:flex;align-items:center;gap:6px;padding:2px 0;color:var(--t1)}
.legend .lg-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.legend .lg-fit{margin-top:8px;padding-top:6px;border-top:1px solid var(--brd);font-size:9px;color:var(--t2);font-family:'IBM Plex Mono',monospace}
.smile-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--t3);font-size:12px;font-family:'DM Sans',sans-serif}
.tip{position:fixed;background:var(--bg);border:1px solid var(--brd);padding:6px 10px;font-size:9px;border-radius:3px;pointer-events:none;z-index:100;display:none;line-height:1.6;box-shadow:0 2px 6px rgba(0,0,0,.08)}
.tip .r{display:flex;gap:8px}.tip .l{color:var(--t3)}.tip .v{color:var(--t1);font-weight:500}
.drop{position:fixed;inset:0;background:rgba(255,255,255,.88);display:none;align-items:center;justify-content:center;z-index:200;font-family:'DM Sans',sans-serif;font-size:18px;color:var(--acc);border:3px dashed var(--acc)}
</style></head><body>
<div class="app">
<div class="hdr">
  <h1>OB VIEWER</h1><div class="sep"></div>
  <div class="tabs" id="tabs">
    <button class="tab active" data-tab="price">Price</button>
    <button class="tab" data-tab="smile">Smile</button>
  </div>
  <div class="sep"></div>
  <label class="file">Prices<input type="file" id="pf" accept=".csv" multiple></label>
  <label class="file">Trades<input type="file" id="tf" accept=".csv" multiple></label>
  <div class="sep"></div>
  <div class="ctrl ctrl-price">
    <span class="lbl">Product</span>
    <select id="prodSel"><option>—</option></select>
  </div>
  <div class="ctrl ctrl-smile" style="display:none">
    <span class="lbl">Underlying</span>
    <select id="undSel"></select>
    <span class="lbl">TTE (days)</span>
    <input type="number" id="tteIn" value="7" min="0.1" step="0.5" style="width:60px">
    <span class="lbl">Sample</span>
    <input type="number" id="sampIn" value="50" min="1" step="1" style="width:60px">
  </div>
  <div class="info" id="hdrInfo">Drop or load CSVs</div>
</div>
<div class="main" id="priceView">
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
<div class="smile" id="smileView" style="display:none">
  <div class="smile-chart" id="smileChart">
    <canvas id="sc"></canvas>
    <div class="legend" id="sLegend"></div>
    <div class="smile-empty" id="sEmpty">Load data containing options (e.g. VEV_XXXX) and an underlying.</div>
  </div>
</div>
</div>
<div class="tip" id="tip"></div>
<div class="drop" id="dz">Drop CSV files</div>

<script>
let P={},T={},prod=null,mode='price',vS=0,vE=1,hI=-1,oI=0,tab='price';
let layers={mid:true,ba:true,trades:false,fill:false};

function parseP(t){const ls=t.trim().split('\n'),d={};for(let i=1;i<ls.length;i++){const c=ls[i].split(';'),p=c[2];if(!d[p])d[p]=[];d[p].push({t:+c[1],b1:+c[3]||0,bv1:+c[4]||0,b2:+c[5]||0,bv2:+c[6]||0,b3:+c[7]||0,bv3:+c[8]||0,a1:+c[9]||0,av1:+c[10]||0,a2:+c[11]||0,av2:+c[12]||0,a3:+c[13]||0,av3:+c[14]||0,mid:+c[15]})}return d}
function parseT(t){const ls=t.trim().split('\n'),d={};for(let i=1;i<ls.length;i++){const c=ls[i].split(';'),p=c[3];if(!d[p])d[p]=[];d[p].push({t:+c[0],buyer:c[1],seller:c[2],p:+c[5],q:+c[6]})}return d}
function merge(e,n){for(const k in n){if(!e[k])e[k]=[];e[k]=e[k].concat(n[k]);e[k].sort((a,b)=>a.t-b.t)}}
function load(txt){if(txt.includes('mid_price'))merge(P,parseP(txt));else if(txt.includes('buyer')||txt.includes('symbol'))merge(T,parseT(txt));upProd();upUnd();R()}

document.getElementById('pf').onchange=e=>{for(const f of e.target.files)f.text().then(load)};
document.getElementById('tf').onchange=e=>{for(const f of e.target.files)f.text().then(load)};
const dz=document.getElementById('dz');
document.body.addEventListener('dragover',e=>{e.preventDefault();dz.style.display='flex'});
dz.addEventListener('dragleave',()=>dz.style.display='none');
dz.addEventListener('drop',e=>{e.preventDefault();dz.style.display='none';for(const f of e.dataTransfer.files)f.text().then(load)});

// ── tab switching ────────────────────────────────────────────────
document.getElementById('tabs').addEventListener('click',e=>{const b=e.target.closest('.tab');if(!b)return;tab=b.dataset.tab;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));document.getElementById('priceView').style.display=tab==='price'?'grid':'none';document.getElementById('smileView').style.display=tab==='smile'?'grid':'none';document.querySelector('.ctrl-price').style.display=tab==='price'?'flex':'none';document.querySelector('.ctrl-smile').style.display=tab==='smile'?'flex':'none';R()});

// ── selectors ───────────────────────────────────────────────────
function upProd(){const s=document.getElementById('prodSel');const keep=prod;s.innerHTML='';Object.keys(P).sort().forEach(p=>{const o=document.createElement('option');o.value=p;o.textContent=p;s.appendChild(o)});if(!keep||!P[keep])prod=Object.keys(P)[0]||null;else prod=keep;s.value=prod;vS=0;vE=1}
function upUnd(){const s=document.getElementById('undSel'),keep=s.value;s.innerHTML='';const nonOpt=Object.keys(P).filter(p=>!/^[A-Z]+_\d+$/.test(p)).sort();nonOpt.forEach(p=>{const o=document.createElement('option');o.value=p;o.textContent=p;s.appendChild(o)});if(keep&&P[keep])s.value=keep;else if(P['VELVETFRUIT_EXTRACT'])s.value='VELVETFRUIT_EXTRACT';else if(nonOpt.length)s.value=nonOpt[0]}
document.getElementById('prodSel').onchange=e=>{prod=e.target.value;vS=0;vE=1;R()};
document.getElementById('undSel').onchange=R;
document.getElementById('tteIn').onchange=R;
document.getElementById('sampIn').onchange=R;
document.getElementById('layerBtns').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const l=b.dataset.layer;layers[l]=!layers[l];b.classList.toggle('on',layers[l]);R()});
document.getElementById('modeBtns').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;document.querySelectorAll('.modes button').forEach(x=>x.classList.remove('active'));b.classList.add('active');mode=b.dataset.mode;R()});

function gV(){if(!prod||!P[prod])return{d:[],tr:[]};const d=P[prod],s=Math.floor(vS*d.length),e=Math.ceil(vE*d.length),vis=d.slice(s,e);if(!vis.length)return{d:[],tr:[]};const t0=vis[0].t,t1=vis[vis.length-1].t;return{d:vis,tr:(T[prod]||[]).filter(tr=>tr.t>=t0&&tr.t<=t1)}}

function R(){if(tab==='price'){rC();rB();rO()}else{rS()}rH()}

// ── price chart ─────────────────────────────────────────────────
function rC(){
  const el=document.getElementById('chart'),cv=document.getElementById('cc'),W=el.clientWidth,H=el.clientHeight-22;
  cv.width=W;cv.height=H;const c=cv.getContext('2d');c.clearRect(0,0,W,H);
  const{d,tr}=gV();if(!d.length)return;
  const p={t:16,r:56,b:16,l:10},cw=W-p.l-p.r,ch=H-p.t-p.b;
  let vals,mn,mx;
  if(mode==='price'){const ap=[];d.forEach(v=>{ap.push(v.mid);if(layers.ba){if(v.b1)ap.push(v.b1);if(v.a1)ap.push(v.a1)}});if(layers.trades)tr.forEach(t=>ap.push(t.p));mn=Math.min(...ap)-1;mx=Math.max(...ap)+1}
  else if(mode==='spread'){vals=d.map(v=>v.a1&&v.b1?v.a1-v.b1:0);mn=Math.min(...vals)-1;mx=Math.max(...vals)+1}
  else{vals=d.map(v=>{const b=v.bv1+v.bv2+v.bv3,a=v.av1+v.av2+v.av3;return b+a>0?(b-a)/(b+a):0});mn=-0.35;mx=0.35}
  const rng=mx-mn||1,X=i=>p.l+cw*i/(d.length-1||1),Y=v=>p.t+ch*(1-(v-mn)/rng);

  c.strokeStyle='#e8ecf2';c.lineWidth=1;
  for(let i=0;i<5;i++){const gy=p.t+ch*i/4;c.beginPath();c.moveTo(p.l,gy);c.lineTo(W-p.r,gy);c.stroke();c.fillStyle='#8c95a8';c.font='9px IBM Plex Mono';c.textAlign='right';c.fillText(mode==='imbalance'?(mx-rng*i/4).toFixed(2):(mx-rng*i/4).toFixed(1),W-4,gy+3)}

  if(mode==='price'){
    if(layers.fill&&layers.ba){c.fillStyle='rgba(59,126,219,0.05)';c.beginPath();d.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v.b1||v.mid)):c.lineTo(X(i),Y(v.b1||v.mid))});for(let i=d.length-1;i>=0;i--)c.lineTo(X(i),Y(d[i].a1||d[i].mid));c.closePath();c.fill()}
    if(layers.ba){c.strokeStyle='rgba(14,165,114,0.55)';c.lineWidth=0.9;c.beginPath();d.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v.b1||v.mid)):c.lineTo(X(i),Y(v.b1||v.mid))});c.stroke();c.strokeStyle='rgba(220,62,80,0.55)';c.beginPath();d.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v.a1||v.mid)):c.lineTo(X(i),Y(v.a1||v.mid))});c.stroke()}
    if(layers.mid){c.strokeStyle='rgba(59,126,219,0.85)';c.lineWidth=1.4;c.beginPath();let started=false;d.forEach((v,i)=>{if(i%50!==0&&i!==d.length-1)return;if(!started){c.moveTo(X(i),Y(v.mid));started=true}else c.lineTo(X(i),Y(v.mid))});c.stroke()}
    if(layers.trades&&tr.length){const t0=d[0].t,t1=d[d.length-1].t,ts=t1-t0||1;tr.forEach(t=>{const tx=p.l+cw*(t.t-t0)/ts,ty=Y(t.p);if(ty<p.t||ty>H-p.b)return;const r=Math.min(1.5+t.q*0.5,6);c.beginPath();c.arc(tx,ty,r,0,Math.PI*2);c.fillStyle='rgba(199,138,28,0.65)';c.fill()})}
  }else{const col=mode==='spread'?'rgba(107,93,224,0.75)':'rgba(199,138,28,0.75)';c.strokeStyle=col;c.lineWidth=1.2;c.beginPath();vals.forEach((v,i)=>{i===0?c.moveTo(X(i),Y(v)):c.lineTo(X(i),Y(v))});c.stroke();if(mode==='imbalance'){c.strokeStyle='#c8cdd7';c.lineWidth=1;c.setLineDash([3,3]);c.beginPath();c.moveTo(p.l,Y(0));c.lineTo(W-p.r,Y(0));c.stroke();c.setLineDash([])}}

  if(hI>=0&&hI<d.length){const hx=X(hI);c.strokeStyle='rgba(20,22,30,0.12)';c.lineWidth=1;c.beginPath();c.moveTo(hx,p.t);c.lineTo(hx,H-p.b);c.stroke();if(mode==='price'){const v=d[hI];c.beginPath();c.moveTo(p.l,Y(v.mid));c.lineTo(W-p.r,Y(v.mid));c.stroke();c.fillStyle='#f0f2f7';c.fillRect(W-p.r,Y(v.mid)-8,p.r,16);c.fillStyle='#3b7edb';c.font='10px IBM Plex Mono';c.textAlign='right';c.fillText(v.mid.toFixed(1),W-4,Y(v.mid)+3)}}
  document.getElementById('sL').textContent='t='+d[0].t;document.getElementById('sR').textContent='t='+d[d.length-1].t;
}

// ── bottom spread strip ─────────────────────────────────────────
function rB(){const el=document.getElementById('btm'),cv=document.getElementById('bc'),W=el.clientWidth,H=el.clientHeight;cv.width=W;cv.height=H;const c=cv.getContext('2d');c.clearRect(0,0,W,H);const{d}=gV();if(!d.length)return;const p={t:14,r:56,b:4,l:10},cw=W-p.l-p.r,ch=H-p.t-p.b;c.fillStyle='#8c95a8';c.font='9px IBM Plex Mono';c.fillText('SPREAD',p.l,10);const sp=d.map(v=>v.a1&&v.b1?v.a1-v.b1:0),smn=Math.min(...sp),smx=Math.max(...sp),sr=smx-smn||1;c.strokeStyle='rgba(107,93,224,0.65)';c.lineWidth=1;c.beginPath();sp.forEach((s,i)=>{const sx=p.l+cw*i/(sp.length-1||1),sy=p.t+ch*(1-(s-smn)/sr);i===0?c.moveTo(sx,sy):c.lineTo(sx,sy)});c.stroke();if(hI>=0&&hI<d.length){const hx=p.l+cw*hI/(d.length-1||1);c.strokeStyle='rgba(20,22,30,0.12)';c.lineWidth=1;c.beginPath();c.moveTo(hx,p.t);c.lineTo(hx,H-p.b);c.stroke()}}

// ── order book side panel ──────────────────────────────────────
function rO(){const{d}=gV();const el=document.getElementById('obC');if(!d.length){el.innerHTML='<div style="color:var(--t3);padding:20px;text-align:center">Load data</div>';return}const idx=Math.min(oI,d.length-1),v=d[idx];const bids=[[v.b1,v.bv1],[v.b2,v.bv2],[v.b3,v.bv3]].filter(x=>x[0]>0),asks=[[v.a1,v.av1],[v.a2,v.av2],[v.a3,v.av3]].filter(x=>x[0]>0),mxV=Math.max(...bids.map(b=>b[1]),...asks.map(a=>a[1]),1),spr=v.a1&&v.b1?(v.a1-v.b1):0,bvT=v.bv1+v.bv2+v.bv3,avT=v.av1+v.av2+v.av3,imb=bvT+avT>0?((bvT-avT)/(bvT+avT)*100).toFixed(1):'0';
let h=`<div class="ob-stats"><div class="ob-stat"><div class="lbl">Time</div><div class="val">${v.t}</div></div><div class="ob-stat"><div class="lbl">Mid</div><div class="val b">${v.mid}</div></div><div class="ob-stat"><div class="lbl">Spread</div><div class="val">${spr}</div></div><div class="ob-stat"><div class="lbl">Imbalance</div><div class="val y">${imb}%</div></div></div>`;
asks.slice().reverse().forEach(([p,vol])=>{h+=`<div class="ob-level"><div class="bar a" style="width:${vol/mxV*85}%"></div><div class="price a">${p}</div><div class="vol">${vol}</div></div>`});
h+=`<div class="ob-sep"></div><div class="ob-mid-lbl">${v.mid.toFixed(1)}</div><div class="ob-sep"></div>`;
bids.forEach(([p,vol])=>{h+=`<div class="ob-level"><div class="bar b" style="width:${vol/mxV*85}%"></div><div class="price b">${p}</div><div class="vol">${vol}</div></div>`});
const near=(T[prod]||[]).filter(t=>Math.abs(t.t-v.t)<300).slice(0,6);
if(near.length){h+='<div class="ob-trades"><div class="tr-title">Trades</div>';near.forEach(t=>{const cls=t.p>=v.mid?'up':'dn';h+=`<div class="ob-trade"><span class="tp">t=${t.t}</span><span class="tprice ${cls}">${t.p}</span><span class="tq">×${t.q}</span></div>`});h+='</div>'}
el.innerHTML=h}

// ── header info strip ──────────────────────────────────────────
function rH(){const info=document.getElementById('hdrInfo');if(!Object.keys(P).length){info.innerHTML='Drop or load CSVs';return}if(tab==='price'){if(!prod||!P[prod])return;const d=P[prod],t=T[prod]||[];info.innerHTML=`<b>${prod}</b> · ${d.length.toLocaleString()} ticks · ${t.length} trades`}else{const und=document.getElementById('undSel').value,nOpt=Object.keys(P).filter(p=>/^[A-Z]+_\d+$/.test(p)).length;info.innerHTML=`Underlying <b>${und||'—'}</b> · ${nOpt} strikes`}}

// ── Black-Scholes IV + parabola fit (for Smile tab) ─────────────
function normCdf(x){const a1=0.254829592,a2=-0.284496736,a3=1.421413741,a4=-1.453152027,a5=1.061405429,p=0.3275911,s=x<0?-1:1;x=Math.abs(x)/Math.sqrt(2);const t=1/(1+p*x);return 0.5*(1+s*(1-((((a5*t+a4)*t+a3)*t+a2)*t+a1)*t*Math.exp(-x*x)))}
function normPdf(x){return Math.exp(-x*x/2)/Math.sqrt(2*Math.PI)}
function bsCall(S,K,T,sig){if(T<=0||sig<=0)return Math.max(S-K,0);const q=sig*Math.sqrt(T),d1=(Math.log(S/K)+0.5*sig*sig*T)/q,d2=d1-q;return S*normCdf(d1)-K*normCdf(d2)}
function bsVega(S,K,T,sig){const q=sig*Math.sqrt(T),d1=(Math.log(S/K)+0.5*sig*sig*T)/q;return S*normPdf(d1)*Math.sqrt(T)}
function implVol(price,S,K,T){if(T<=0||S<=0||K<=0)return null;const intr=Math.max(S-K,0);if(price<intr-1e-6||price>S+1e-6)return null;if(price<=intr+1e-10)return 1e-6;let sig=0.3;for(let i=0;i<100;i++){const diff=bsCall(S,K,T,sig)-price;if(Math.abs(diff)<1e-6)return sig;const v=bsVega(S,K,T,sig);if(v<1e-12)break;let ns=sig-diff/v;if(ns<=1e-6)ns=1e-6;else if(ns>=5)ns=5;if(Math.abs(ns-sig)<1e-12)return ns;sig=ns}let lo=1e-6,hi=5,fLo=bsCall(S,K,T,lo)-price,fHi=bsCall(S,K,T,hi)-price;if(fLo*fHi>0)return null;for(let i=0;i<200;i++){const mid=0.5*(lo+hi),diff=bsCall(S,K,T,mid)-price;if(Math.abs(diff)<1e-6||(hi-lo)<1e-10)return mid;if(diff*fLo<0){hi=mid;fHi=diff}else{lo=mid;fLo=diff}}return 0.5*(lo+hi)}
function fitParabola(xs,ys){const n=xs.length;if(n<3)return null;let sx=0,sy=0,sxx=0,sxxx=0,sxxxx=0,sxy=0,sxxy=0;for(let i=0;i<n;i++){const x=xs[i],y=ys[i];sx+=x;sy+=y;sxx+=x*x;sxxx+=x*x*x;sxxxx+=x*x*x*x;sxy+=x*y;sxxy+=x*x*y}const A=[[n,sx,sxx,sy],[sx,sxx,sxxx,sxy],[sxx,sxxx,sxxxx,sxxy]];for(let i=0;i<3;i++){let mr=i;for(let k=i+1;k<3;k++)if(Math.abs(A[k][i])>Math.abs(A[mr][i]))mr=k;[A[i],A[mr]]=[A[mr],A[i]];if(Math.abs(A[i][i])<1e-14)return null;for(let k=i+1;k<3;k++){const f=A[k][i]/A[i][i];for(let j=i;j<4;j++)A[k][j]-=f*A[i][j]}}const x=[0,0,0];for(let i=2;i>=0;i--){let s=A[i][3];for(let j=i+1;j<3;j++)s-=A[i][j]*x[j];x[i]=s/A[i][i]}return{c:x[0],b:x[1],a:x[2]}}

let smileCache=null,smileKey='';
function computeSmile(){const und=document.getElementById('undSel').value;if(!P[und])return{points:[],fit:null,strikes:[]};const ttd=+document.getElementById('tteIn').value,samp=Math.max(1,+document.getElementById('sampIn').value|0);const key=und+'|'+ttd+'|'+samp+'|'+Object.keys(P).length;if(smileCache&&smileKey===key)return smileCache;const T=ttd/365,U=P[und],Um=new Map();U.forEach(v=>Um.set(v.t,v.mid));const opts=[];Object.keys(P).forEach(p=>{const m=p.match(/^([A-Z]+)_(\d+)$/);if(m)opts.push({prod:p,K:+m[2]})});opts.sort((a,b)=>a.K-b.K);const pts=[];opts.forEach(({prod,K})=>{const rows=P[prod];for(let i=0;i<rows.length;i+=samp){const r=rows[i];if(!r.mid||r.mid<=0)continue;const S=Um.get(r.t);if(!S||S<=0)continue;const iv=implVol(r.mid,S,K,T);if(iv===null||iv<0.01||iv>3)continue;const mt=K/S;pts.push({m:mt,v:iv,K,t:r.t})}});const fit=fitParabola(pts.map(p=>p.m),pts.map(p=>p.v));smileCache={points:pts,fit,strikes:opts.map(o=>o.K)};smileKey=key;return smileCache}

const STRIKE_PALETTE=['#7c6ff7','#e8434f','#1ba870','#b264d9','#e89d3e','#3b7edb','#d4a62a','#4aaecc','#a86a3d','#b02e8a','#4f5d75','#1d7a52'];
function colorOfStrike(K,strikes){const idx=strikes.indexOf(K);if(idx<0)return '#888';if(strikes.length<=STRIKE_PALETTE.length)return STRIKE_PALETTE[idx];const hue=(idx/strikes.length)*300;return `hsl(${hue},58%,50%)`}

// ── smile chart ─────────────────────────────────────────────────
let smileHover=null;
function rS(){
  const el=document.getElementById('smileChart'),cv=document.getElementById('sc'),W=el.clientWidth,H=el.clientHeight;
  if(!W||!H)return;cv.width=W;cv.height=H;const c=cv.getContext('2d');c.clearRect(0,0,W,H);
  const{points,fit,strikes}=computeSmile();const empty=document.getElementById('sEmpty');
  if(!points.length){empty.style.display='flex';document.getElementById('sLegend').innerHTML='';return}
  empty.style.display='none';
  const p={t:28,r:24,b:44,l:64},cw=W-p.l-p.r,ch=H-p.t-p.b;
  let mMin=Infinity,mMax=-Infinity,vMin=Infinity,vMax=-Infinity;
  for(const pt of points){if(pt.m<mMin)mMin=pt.m;if(pt.m>mMax)mMax=pt.m;if(pt.v<vMin)vMin=pt.v;if(pt.v>vMax)vMax=pt.v}
  const mPad=(mMax-mMin)*0.06||0.1,vPad=(vMax-vMin)*0.08||0.02;
  const mLo=mMin-mPad,mHi=mMax+mPad,vLo=Math.max(0,vMin-vPad),vHi=vMax+vPad;
  const X=m=>p.l+cw*(m-mLo)/(mHi-mLo),Y=v=>p.t+ch*(1-(v-vLo)/(vHi-vLo));

  // grid + axes
  c.strokeStyle='#e5e9f0';c.lineWidth=1;c.fillStyle='#8c95a8';c.font='10px IBM Plex Mono';
  for(let i=0;i<=6;i++){const gy=p.t+ch*i/6;c.beginPath();c.moveTo(p.l,gy);c.lineTo(W-p.r,gy);c.stroke();const yv=vHi-(vHi-vLo)*i/6;c.textAlign='right';c.fillText(yv.toFixed(3),p.l-6,gy+3)}
  for(let i=0;i<=8;i++){const gx=p.l+cw*i/8;c.beginPath();c.moveTo(gx,p.t);c.lineTo(gx,H-p.b);c.stroke();const xv=mLo+(mHi-mLo)*i/8;c.textAlign='center';c.fillText(xv.toFixed(2),gx,H-p.b+16)}
  c.strokeStyle='#c8cdd7';c.lineWidth=1;c.beginPath();c.moveTo(p.l,H-p.b);c.lineTo(W-p.r,H-p.b);c.stroke();c.beginPath();c.moveTo(p.l,p.t);c.lineTo(p.l,H-p.b);c.stroke();
  // axis titles
  c.fillStyle='#3a4050';c.font='600 12px DM Sans';c.textAlign='center';c.fillText('K / S',p.l+cw/2,H-10);c.save();c.translate(18,p.t+ch/2);c.rotate(-Math.PI/2);c.fillText('IV',0,0);c.restore();

  // scatter
  c.globalAlpha=0.45;
  for(const pt of points){c.fillStyle=colorOfStrike(pt.K,strikes);c.beginPath();c.arc(X(pt.m),Y(pt.v),2.5,0,Math.PI*2);c.fill()}
  c.globalAlpha=1;

  // fit
  if(fit){c.strokeStyle='#14161e';c.lineWidth=2.8;c.beginPath();const N=240;for(let i=0;i<=N;i++){const m=mLo+(mHi-mLo)*i/N,v=fit.a*m*m+fit.b*m+fit.c;if(v<vLo||v>vHi)continue;if(i===0)c.moveTo(X(m),Y(v));else c.lineTo(X(m),Y(v))}c.stroke()}

  // hover
  if(smileHover){const{m,v,K,t}=smileHover;c.strokeStyle='rgba(20,22,30,0.18)';c.lineWidth=1;c.setLineDash([4,4]);c.beginPath();c.moveTo(X(m),p.t);c.lineTo(X(m),H-p.b);c.stroke();c.beginPath();c.moveTo(p.l,Y(v));c.lineTo(W-p.r,Y(v));c.stroke();c.setLineDash([]);c.fillStyle=colorOfStrike(K,strikes);c.strokeStyle='#14161e';c.lineWidth=1.5;c.beginPath();c.arc(X(m),Y(v),5,0,Math.PI*2);c.fill();c.stroke()}

  // legend
  const leg=document.getElementById('sLegend');let h='<div class="lg-title">Strikes</div>';for(const K of strikes)h+=`<div class="lg-row"><span class="lg-dot" style="background:${colorOfStrike(K,strikes)}"></span>K=${K}</div>`;if(fit)h+=`<div class="lg-row" style="margin-top:6px"><span class="lg-dot" style="background:#14161e"></span>fitted parabola</div><div class="lg-fit">IV = ${fit.a.toFixed(4)}·x² ${fit.b>=0?'+':''}${fit.b.toFixed(4)}·x ${fit.c>=0?'+':''}${fit.c.toFixed(4)}<br>x = K/S,  n = ${points.length.toLocaleString()}</div>`;leg.innerHTML=h;
}

// ── hover on price chart ────────────────────────────────────────
const chart=document.getElementById('chart'),tip=document.getElementById('tip');
chart.addEventListener('mousemove',e=>{if(tab!=='price'||!prod||!P[prod])return;const{d}=gV();if(!d.length)return;const rect=chart.getBoundingClientRect(),mx=e.clientX-rect.left,pl=10,pr=56,cw=rect.width-pl-pr,idx=Math.round((mx-pl)/cw*(d.length-1));if(idx<0||idx>=d.length){tip.style.display='none';return}hI=idx;oI=idx;rC();rB();rO();const v=d[idx],spr=v.a1&&v.b1?v.a1-v.b1:0,bv=v.bv1+v.bv2+v.bv3,av=v.av1+v.av2+v.av3,imb=bv+av>0?((bv-av)/(bv+av)*100).toFixed(1):'0';
tip.innerHTML=`<div class="r"><span class="l">t</span><span class="v">${v.t}</span></div><div class="r"><span class="l">mid</span><span class="v" style="color:var(--mid)">${v.mid}</span></div><div class="r"><span class="l">bid</span><span class="v" style="color:var(--bid)">${v.b1}×${v.bv1}</span></div><div class="r"><span class="l">ask</span><span class="v" style="color:var(--ask)">${v.a1}×${v.av1}</span></div><div class="r"><span class="l">spr</span><span class="v">${spr}</span></div><div class="r"><span class="l">imb</span><span class="v" style="color:var(--trd)">${imb}%</span></div>`;
tip.style.display='block';tip.style.left=Math.min(e.clientX+10,window.innerWidth-220)+'px';tip.style.top=(e.clientY-50)+'px'});
chart.addEventListener('mouseleave',()=>{tip.style.display='none';hI=-1;if(tab==='price'){rC();rB()}});
chart.addEventListener('wheel',e=>{e.preventDefault();if(tab!=='price'||!prod||!P[prod])return;const rect=chart.getBoundingClientRect(),mx=(e.clientX-rect.left)/rect.width,ctr=vS+(vE-vS)*mx,z=e.deltaY>0?1.15:0.87;let half=(vE-vS)/2*z;half=Math.max(0.003,Math.min(0.5,half));vS=Math.max(0,ctr-half);vE=Math.min(1,ctr+half);if(vE-vS<0.003)vE=vS+0.003;R()},{passive:false});
let drag=false,dX=0,dVS=0,dVE=0;
chart.addEventListener('mousedown',e=>{if(tab==='price'&&e.button===0){drag=true;dX=e.clientX;dVS=vS;dVE=vE}});
window.addEventListener('mousemove',e=>{if(!drag)return;const rect=chart.getBoundingClientRect(),dx=(e.clientX-dX)/rect.width,span=dVE-dVS,shift=-dx*span;vS=Math.max(0,Math.min(1-span,dVS+shift));vE=vS+span;R()});
window.addEventListener('mouseup',()=>{drag=false});
document.getElementById('tSlider').addEventListener('input',e=>{const{d}=gV();oI=Math.round(e.target.value/1000*(d.length-1));rO();hI=oI;rC();rB()});

// ── hover on smile chart ───────────────────────────────────────
const sChart=document.getElementById('smileChart'),sCv=document.getElementById('sc');
sChart.addEventListener('mousemove',e=>{if(tab!=='smile')return;const{points,strikes}=computeSmile();if(!points.length)return;const rect=sCv.getBoundingClientRect(),mx=e.clientX-rect.left,my=e.clientY-rect.top;let best=null,bestD=400;for(const pt of points){const dx=mx-(sCv.width*((pt.m-sMinMax.mLo)/(sMinMax.mHi-sMinMax.mLo)*sMinMax.cw/sCv.width+sMinMax.pl/sCv.width)),dy=my-(sCv.height*((1-(pt.v-sMinMax.vLo)/(sMinMax.vHi-sMinMax.vLo))*sMinMax.ch/sCv.height+sMinMax.pt/sCv.height));const d2=dx*dx+dy*dy;if(d2<bestD){bestD=d2;best=pt}}if(best){smileHover=best;rS();tip.innerHTML=`<div class="r"><span class="l">K</span><span class="v" style="color:${colorOfStrike(best.K,strikes)}">${best.K}</span></div><div class="r"><span class="l">t</span><span class="v">${best.t}</span></div><div class="r"><span class="l">K/S</span><span class="v">${best.m.toFixed(4)}</span></div><div class="r"><span class="l">IV</span><span class="v">${best.v.toFixed(4)}</span></div>`;tip.style.display='block';tip.style.left=Math.min(e.clientX+12,window.innerWidth-220)+'px';tip.style.top=(e.clientY-50)+'px'}else{if(smileHover){smileHover=null;rS()}tip.style.display='none'}});
sChart.addEventListener('mouseleave',()=>{if(smileHover){smileHover=null;rS()}tip.style.display='none'});
let sMinMax={mLo:0,mHi:1,vLo:0,vHi:1,pl:64,pt:28,cw:0,ch:0};
// We re-derive sMinMax inside rS for hover consistency; override rS to capture
const _rS=rS;rS=function(){const el=document.getElementById('smileChart'),cv=document.getElementById('sc'),W=el.clientWidth,H=el.clientHeight;if(!W||!H){_rS();return}const{points}=computeSmile();if(points.length){let mMin=Infinity,mMax=-Infinity,vMin=Infinity,vMax=-Infinity;for(const pt of points){if(pt.m<mMin)mMin=pt.m;if(pt.m>mMax)mMax=pt.m;if(pt.v<vMin)vMin=pt.v;if(pt.v>vMax)vMax=pt.v}const mPad=(mMax-mMin)*0.06||0.1,vPad=(vMax-vMin)*0.08||0.02;sMinMax={mLo:mMin-mPad,mHi:mMax+mPad,vLo:Math.max(0,vMin-vPad),vHi:vMax+vPad,pl:64,pt:28,cw:W-64-24,ch:H-28-44,W,H}}_rS()};

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
