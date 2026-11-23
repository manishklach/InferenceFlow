/* Observed quote comparisons. No interpolation or backfilled prices. */
const PriceTrends = (() => {
  const day = 86400000;
  const escape = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function index(rows, key) {
    const groups = new Map();
    for (const row of rows) {
      if (row.invalidated || !Number.isFinite(Date.parse(row.observed_at_utc))) continue;
      const id = key(row);
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push(row);
    }
    for (const group of groups.values()) group.sort((a,b) => Date.parse(a.observed_at_utc)-Date.parse(b.observed_at_utc));
    return groups;
  }
  function targetDate(timestamp, period) {
    const date = new Date(timestamp);
    if (period === 'WoW') return date.getTime() - 7 * day;
    const originalDay = date.getUTCDate();
    date.setUTCDate(1);
    date.setUTCMonth(date.getUTCMonth()-1);
    const lastDay = new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate();
    date.setUTCDate(Math.min(originalDay,lastDay));
    return date.getTime();
  }
  const valid = (row, field) => row && !row.invalidated && row.cloud_supported !== false && Number.isFinite(row[field]) && row[field] > 0;
  function compare(current, history, field, period) {
    if (!valid(current,field)) return {state:'unknown',text:'Unavailable',detail:'Current quote is unavailable.'};
    const target = targetDate(current.observed_at_utc,period);
    const baseline = [...(history || [])].reverse().find(row => {
      const time = Date.parse(row.observed_at_utc);
      return time <= target && time >= target - 2*day && valid(row,field);
    });
    if (!baseline) return {state:'unknown',text:'No baseline',detail:`No valid quote within 48 hours before ${new Date(target).toISOString()}.`};
    const percent = (current[field]-baseline[field])/baseline[field]*100;
    const state = Math.abs(percent)<1e-9 ? 'flat' : percent>0 ? 'up' : 'down';
    const magnitude = Math.abs(percent);
    const amount = magnitude>0 && magnitude<0.01 ? '<0.01' : magnitude.toFixed(2);
    const text = state==='flat' ? '→ 0.00%' : `${state==='up'?'↑ +':'↓ −'}${amount}%`;
    return {state,text,baseline,percent};
  }
  function cells(current, history, field, precision) {
    return ['WoW','MoM'].map(period => {
      const result = compare(current,history,field,period);
      const direction = {up:'Price increase',down:'Price decrease',flat:'Unchanged',unknown:result.text}[result.state];
      const detail = result.detail || `Baseline $${result.baseline[field].toFixed(precision)} at ${result.baseline.observed_at_utc}; latest $${current[field].toFixed(precision)} at ${current.observed_at_utc}.`;
      const label = `${period}: ${direction}. ${result.text}. ${detail}`;
      return `<td><span tabindex="0" class="price-change price-${result.state}" title="${escape(label)}" aria-label="${escape(label)}">${result.text}</span></td>`;
    }).join('');
  }
  return {index,targetDate,compare,cells};
})();
if (typeof module !== 'undefined') module.exports = PriceTrends;
