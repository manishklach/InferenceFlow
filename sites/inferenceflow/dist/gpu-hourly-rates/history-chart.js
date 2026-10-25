// Shared GPU/CPU chart: proportional UTC time, accessible observation details.
window.drawRateHistory = function (element, records, priceKey, unit, digits) {
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const data = records.filter(r => Number.isFinite(Date.parse(r.observed_at_utc)) && Number.isFinite(r[priceKey])).sort((a,b) => Date.parse(a.observed_at_utc)-Date.parse(b.observed_at_utc));
  if (!data.length) { element.innerHTML = '<text x="40" y="60">No recorded quotes for this selection.</text>'; return; }
  const first = Date.parse(data[0].observed_at_utc), last = Date.parse(data.at(-1).observed_at_utc);
  const start = first === last ? first-1800000 : first, end = first === last ? last+1800000 : last;
  const max = Math.max(...data.map(r=>r[priceKey]))*1.15 || 1;
  const x = t => 88+800*(t-start)/(end-start), y = p => 254-202*p/max;
  const money = p => '$'+p.toFixed(digits);
  let html = '<text x="88" y="22" fill="#606c5b" font-size="13">'+esc(unit)+'</text>';
  for(let i=0;i<=4;i++) html += `<path d="M88 ${y(max*i/4)}H888" stroke="#e0e6d8"/><text x="72" y="${y(max*i/4)+4}" text-anchor="end" font-size="12" fill="#606c5b">${money(max*i/4)}</text>`;
  for(let i=0;i<=4;i++) {
    const time=start+(end-start)*i/4, date=new Date(time), xx=x(time);
    html += `<path d="M${xx} 52V260" stroke="#e9ede3" stroke-dasharray="3 5"/><text x="${xx}" y="282" text-anchor="middle" font-size="12" fill="#394936">${date.toISOString().slice(11,16)}</text><text x="${xx}" y="300" text-anchor="middle" font-size="11" fill="#606c5b">${date.toISOString().slice(5,10)}</text>`;
  }
  html += '<text x="488" y="327" text-anchor="middle" font-size="12" fill="#606c5b">Observation time · UTC (month-day)</text>';
  const clouds=[...new Set(data.map(r=>r.cloud))];
  clouds.forEach((cloud,i)=>{
    const series=data.filter(r=>r.cloud===cloud), color=cloud==='COMMUNITY'?'#b57128':'#2f5841';
    html+=`<polyline fill="none" stroke="${color}" stroke-width="2" points="${series.map(r=>x(Date.parse(r.observed_at_utc))+','+y(r[priceKey])).join(' ')}"/>`;
    html+=`<circle cx="${310+i*200}" cy="355" r="4" fill="${color}"/><text x="${322+i*200}" y="359" font-size="12" fill="${color}">${esc(cloud)}</text>`;
  });
  data.forEach((r,i)=>{
    const color=r.cloud==='COMMUNITY'?'#b57128':'#2f5841', xx=x(Date.parse(r.observed_at_utc)), yy=y(r[priceKey]);
    const description=`${r.gpu || r.cpu_name} · ${r.cloud} · ${money(r[priceKey])} ${unit} · ${r.observed_at_utc} · Stock: ${r.availability}`;
    html+=`<g class="rate-point" tabindex="0" role="button" aria-label="${esc(description)}" data-index="${i}"><title>${esc(description)}</title><circle cx="${xx}" cy="${yy}" r="12" fill="transparent"/><circle cx="${xx}" cy="${yy}" r="4.5" stroke="${color}" stroke-width="2" fill="${r.availability==='NONE'?'white':color}"/></g>`;
  });
  element.setAttribute('viewBox','0 0 960 380'); element.innerHTML=html;
  const container=element.parentElement; container.classList.add('history-chart-wrap');
  let tooltip=container.querySelector('.rate-tooltip');
  if(!tooltip){tooltip=document.createElement('div');tooltip.className='rate-tooltip';tooltip.setAttribute('role','status');container.append(tooltip);}
  tooltip.hidden=true;
  const show=target=>{
    const r=data[Number(target.dataset.index)];
    tooltip.innerHTML=`<strong>${esc(r.gpu || r.cpu_name)} · ${esc(r.cloud)}</strong><span class="tooltip-price">${money(r[priceKey])} <small>${esc(unit)}</small></span><span>${esc(new Date(r.observed_at_utc).toISOString().replace('T',' ').replace('Z',' UTC'))}</span><span>Stock: ${esc(r.availability)}</span>`;
    tooltip.hidden=false;
    const point=target.getBoundingClientRect(), box=container.getBoundingClientRect();
    tooltip.style.left=Math.max(8,Math.min(point.left-box.left+container.scrollLeft-110,container.scrollLeft+container.clientWidth-tooltip.offsetWidth-8))+'px';
    tooltip.style.top=Math.max(8,point.top-box.top-tooltip.offsetHeight-12)+'px';
  };
  element.querySelectorAll('.rate-point').forEach(point=>{
    point.addEventListener('pointerenter',()=>show(point)); point.addEventListener('focus',()=>show(point));
    point.addEventListener('click',()=>show(point)); point.addEventListener('pointerleave',()=>{tooltip.hidden=true;});
    point.addEventListener('blur',()=>{tooltip.hidden=true;}); point.addEventListener('keydown',event=>{if(event.key==='Escape')tooltip.hidden=true;});
  });
};
