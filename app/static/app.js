'use strict';
const $ = id => document.getElementById(id);
const numeric = value => typeof value === 'number' && Number.isFinite(value);
const format = (value, places = 1, unit = '') => numeric(value) ? `${value.toFixed(places)}${unit}` : 'Not available';
let devices = [];
let timer;

function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
}
function metric(card, label, value) {
    const line = element('p');
    line.append(element('strong', `${label}: `), document.createTextNode(value));
    card.append(line);
}
async function api(path) {
    const response = await fetch(path, {cache: 'no-store'});
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || body.message || `Request failed (${response.status})`);
    }
    return response.json();
}
function renderThermostats(rows) {
    const container = $('thermostat-list'); container.replaceChildren();
    if (!rows.length) { container.append(element('p', 'No thermostat readings yet. Connect Google Nest to begin.', 'loading')); return; }
    rows.forEach(t => {
        const card = element('article', undefined, 'card');
        card.append(element('h3', t.device_name || 'Nest thermostat'));
        card.append(element('div', format(t.ambient_temperature, 1, ' °C'), 'temperature'));
        const target = t.mode === 'HEATCOOL' ? `${format(t.target_heat_temperature, 1, ' °C')} – ${format(t.target_cool_temperature, 1, ' °C')}` : format(t.target_temperature, 1, ' °C');
        metric(card, 'Target', target); metric(card, 'Humidity', format(t.humidity, 1, '%'));
        metric(card, 'Mode', t.mode || 'Unknown'); metric(card, 'HVAC', t.hvac_status || 'Unknown');
        metric(card, 'Eco', t.eco_state || 'Unknown'); metric(card, 'Connectivity', t.connectivity || 'Unknown');
        metric(card, 'Reading', new Date(t.timestamp).toLocaleString());
        const age = Date.now() - new Date(t.timestamp).getTime();
        if (age > 15 * 60 * 1000) card.append(element('p', 'This reading is more than 15 minutes old.', 'stale'));
        container.append(card);
    });
}
function renderSolar(rows) {
    const container = $('solar-list'); container.replaceChildren();
    if (!rows.length) { container.append(element('p', 'Solar readings will appear after the Sungrow integration is configured.', 'loading')); return; }
    rows.forEach(s => {
        const card = element('article', undefined, 'card');
        card.append(element('h3', s.installation_name || `Installation ${s.installation_id}`));

        metric(card, 'Power', format(numeric(s.instantaneous_power) ? s.instantaneous_power / 1000 : null, 2, ' kW'));
        metric(card, 'Today', format(s.daily_generation, 2, ' kWh'));
        metric(card, 'Imported today', format(s.grid_import_daily, 2, ' kWh'));
        metric(card, 'Exported today', format(s.grid_export_daily, 2, ' kWh'));
        metric(card, 'Grid import', format(s.grid_import_power, 0, ' W'));
        metric(card, 'Grid export', format(s.grid_export_power, 0, ' W'));
        metric(card, 'Battery power', format(s.battery_power, 0, ' W'));
        metric(card, 'Battery charge', format(s.battery_soc, 1, '%'));
        metric(card, 'Provider reading (plant local time)', s.provider_time || 'Not available');
        metric(card, 'Last retrieved', new Date(s.timestamp).toLocaleString());
        card.append(element('p', 'Unavailable fields are not reported or not yet verified for this installation.', 'legend'));
        container.append(card);
    });
}
function updateDeviceList(data) {
    const selected = $('history-device').value;
    devices = [...data.thermostats.map(t => ({kind:'thermostats', id:t.device_id, label:t.device_name})), ...data.solar.map(s => ({kind:'solar', id:s.installation_id, label:`Solar ${s.installation_id}`}))];
    $('history-device').replaceChildren();
    if (!devices.length) $('history-device').append(element('option', 'No devices connected'));
    devices.forEach((d, i) => { const option = element('option', d.label || d.id); option.value = String(i); $('history-device').append(option); });
    if ([...$('history-device').options].some(o => o.value === selected)) $('history-device').value = selected;
}
async function refresh() {
    try {
        const [data, status] = await Promise.all([api('/api/current'), api('/api/status')]);
        renderThermostats(data.thermostats); renderSolar(data.solar); updateDeviceList(data);
        const g = status.google;
        $('google-status').textContent = !g.configured ? 'Google credentials and Device Access project ID are required in Railway.' : !g.encryption_ready ? 'The token encryption key needs configuration in Railway.' : !g.connected ? 'Ready to connect your Nest account.' : g.polling.state === 'error' ? 'Connected, but the latest poll failed. Check the Railway logs.' : 'Google Nest connected. Polling every ' + Math.round(status.polling_interval_seconds / 60) + ' minutes.';
        $('pubsub-status').textContent = g.pubsub.state === 'listening' ? 'Live events: listening' : g.pubsub.state === 'error' ? 'Live events: reconnecting; polling remains active.' : 'Live events: Pub/Sub service account and subscription setup required.';
        $('google-auth').disabled = !g.configured || !g.encryption_ready;
        $('google-auth').textContent = g.connected ? 'Reconnect Google Nest' : 'Connect Google Nest';
        const sg = status.sungrow;
        $('sungrow-status').textContent = !sg.configured ? 'Sungrow credentials need configuration in Railway.' : !sg.connected ? 'Ready to connect your iSolarCloud installation.' : sg.polling.state === 'error' ? 'Connected, but the latest reading failed. Check Railway logs.' : 'Sungrow connected. Readings update every five minutes or the configured longer interval.';
        $('sungrow-auth').disabled = !sg.configured || !sg.encryption_ready;
        $('sungrow-auth').textContent = sg.connected ? 'Reconnect Sungrow' : 'Connect Sungrow';
        $('last-update').textContent = new Date().toLocaleString(); $('error').hidden = true;
        clearTimeout(timer); timer = setTimeout(refresh, 30000);
    } catch (error) { $('error').textContent = error.message; $('error').hidden = false; clearTimeout(timer); timer = setTimeout(refresh, 30000); }
}

function drawChart(container, rows, series, title, unit) {
    const card = element('article', undefined, 'chart-card'); card.append(element('h3', title));
    const valid = rows.flatMap(row => series.filter(s => numeric(row[s.key])).map(s => row[s.key]));
    if (!valid.length) { card.append(element('p', 'No readings available for this metric.')); container.append(card); return; }
    const canvas = element('canvas'); canvas.width = 900; canvas.height = 290;
    canvas.setAttribute('role','img'); canvas.setAttribute('aria-label', `${title}, ${rows.length} readings; range ${Math.min(...valid).toFixed(1)} to ${Math.max(...valid).toFixed(1)} ${unit}.`);
    const ctx = canvas.getContext('2d'); const pad = {left:65,right:20,top:20,bottom:45};
    const minTime = new Date(rows[0].timestamp).getTime(), maxTime = new Date(rows[rows.length-1].timestamp).getTime();
    let low = Math.min(...valid), high = Math.max(...valid); const margin = (high-low)*0.1 || 1; low-=margin; high+=margin;
    const x = time => pad.left + (time-minTime)/(maxTime-minTime || 1)*(canvas.width-pad.left-pad.right);
    const y = value => canvas.height-pad.bottom-(value-low)/(high-low)*(canvas.height-pad.top-pad.bottom);
    ctx.font = '13px sans-serif'; ctx.lineWidth=1;
    for (let i=0;i<=4;i++) { const v=low+(high-low)*i/4; const yy=y(v); ctx.strokeStyle='#e1e8e5';ctx.beginPath();ctx.moveTo(pad.left,yy);ctx.lineTo(canvas.width-pad.right,yy);ctx.stroke();ctx.fillStyle='#50635b';ctx.fillText(v.toFixed(1),8,yy+4); }
    series.forEach(s => {
        ctx.strokeStyle=s.color;ctx.fillStyle=s.color;ctx.lineWidth=2;ctx.beginPath();let started=false;
        rows.forEach(row => { if (!numeric(row[s.key])) {started=false;return;} const xx=x(new Date(row.timestamp).getTime()), yy=y(row[s.key]);if(started)ctx.lineTo(xx,yy);else ctx.moveTo(xx,yy);started=true; });ctx.stroke();
        if(rows.length===1 && numeric(rows[0][s.key])) {ctx.beginPath();ctx.arc(x(minTime),y(rows[0][s.key]),4,0,2*Math.PI);ctx.fill();}
    });
    ctx.fillStyle='#50635b';ctx.fillText(new Date(minTime).toLocaleString(),pad.left,canvas.height-12);ctx.textAlign='right';ctx.fillText(new Date(maxTime).toLocaleString(),canvas.width-pad.right,canvas.height-12);
    card.append(canvas,element('p',series.map(s=>s.label).join(' · ') + ' ('+unit+')','legend'));container.append(card);
}
async function loadHistory() {
    const device = devices[Number($('history-device').value)];
    if (!device) { $('history-status').textContent = 'Connect a device first.'; return; }
    $('history-status').textContent = 'Loading history…';
    try {
        const params = new URLSearchParams({hours:$('hours').value});params.set(device.kind==='thermostats'?'device_id':'installation_id',device.id);
        const data = await api('/api/history?'+params);const rows=data[device.kind]||[];const charts=$('history-charts');charts.replaceChildren();
        $('history-status').textContent = rows.length ? `${rows.length} readings · ${device.label || device.id}${data[device.kind+'_limit_reached']?' · Showing latest 10,000 readings':''}` : 'No readings in this period yet.';
        if (!rows.length) return;
        if(device.kind==='thermostats') {
            drawChart(charts,rows,[{key:'ambient_temperature',label:'Room',color:'#137b60'},{key:'target_heat_temperature',label:'Heat target',color:'#d98235'},{key:'target_cool_temperature',label:'Cool target',color:'#397fc4'}],'Temperature','°C');
            drawChart(charts,rows,[{key:'humidity',label:'Humidity',color:'#397fc4'}],'Humidity','%');
        } else {
            drawChart(charts,rows,[{key:'instantaneous_power',label:'Solar',color:'#d98235'},{key:'grid_import_power',label:'Import',color:'#bf5252'},{key:'grid_export_power',label:'Export',color:'#137b60'}],'Solar & grid power','W');
            drawChart(charts,rows,[{key:'daily_generation',label:'Daily generation',color:'#137b60'}],'Daily generation','kWh');
            drawChart(charts,rows,[{key:'battery_soc',label:'Battery charge',color:'#397fc4'}],'Battery charge','%');
        }
    } catch(error) { $('history-status').textContent=error.message; }
}
$('google-auth').addEventListener('click', async () => {try {const data=await api('/auth/google');window.location.assign(data.auth_url);} catch(error) {$('error').textContent=error.message;$('error').hidden=false;}});
$('load-history').addEventListener('click',loadHistory);
refresh().then(() => {if(devices.length) loadHistory();});

$('sungrow-auth').addEventListener('click', async () => {try {const data=await api('/auth/sungrow');window.location.assign(data.auth_url);} catch(error) {$('error').textContent=error.message;$('error').hidden=false;}});

const dubaiTime = value => new Date(value).toLocaleTimeString('en-GB',{timeZone:'Asia/Dubai',hour:'2-digit',minute:'2-digit'});
function parseReference(text, withTarget) {
    const rows = text.split('\n').map(x=>x.trim()).filter(Boolean).map(line=>{
        const match=line.match(withTarget ? /^(\d{2}):(\d{2})-(\d{2}):(\d{2})\s+(-?\d+(?:\.\d+)?)$/ : /^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/);
        if(!match) throw new Error('Use HH:MM-HH:MM'+(withTarget?' followed by temperature in °C.':'.'));
        const a=Number(match[1])*60+Number(match[2]), b=Number(match[3])*60+Number(match[4]);
        if(Number(match[2])>59 || Number(match[4])>59 || a>=1440 || b>1440 || b<=a) throw new Error('Use valid times within one day. Split overnight periods at midnight.');
        return {a,b,target:withTarget?Number(match[5]):null};
    }).sort((a,b)=>a.a-b.a);
    if(rows.some((r,i)=>i && rows[i-1].b>r.a)) throw new Error('Reference periods cannot overlap.');
    return rows;
}
function minutesText(value) {return `${Math.floor(value/60)}h ${Math.round(value%60)}m`;}
function renderRuntime(data) {
    const container=$('runtime-list');container.replaceChildren();
    const start=Date.parse(data.start), end=Date.parse(data.end), span=end-start;
    $('runtime-status').textContent=`${data.day} · Dubai time · ${data.devices.length} rooms · More than ${data.gap_minutes} minutes without a reading is unknown. History begins when monitoring was connected.`;
    data.devices.forEach(device=>{
        const card=element('article',undefined,'runtime-row');card.append(element('h3',device.device_name));
        const totals=device.minutes;
        card.append(element('p',`Estimated cooling ${minutesText(totals.COOLING)} · Off ${minutesText(totals.OFF)} · Eco reported ${minutesText(totals.ECO)} · Unknown ${minutesText(totals.UNKNOWN)}`));
        const detail=element('p','Select a coloured period to see times and the recorded target.','runtime-details');
        const axis=element('div',undefined,'runtime-axis');axis.append(element('span',dubaiTime(start)),element('span',dubaiTime(end)));card.append(axis);
        for(const kind of ['hvac','eco']) {
            card.append(element('p',kind==='hvac'?'AC activity':'Eco reported by Nest','legend'));
            const track=element('div',undefined,'runtime-track'+(kind==='eco'?' eco-track':''));
            device.segments.forEach(s=>{
                const state=kind==='hvac'?s.hvac:s.eco;
                const color=state==='MANUAL_ECO'?'eco':state.toLowerCase();
                const button=element('button',undefined,'runtime-segment runtime-'+color);
                button.type='button';button.style.width=((Date.parse(s.end)-Date.parse(s.start))/span*100)+'%';
                const label=`${dubaiTime(s.start)}–${dubaiTime(s.end)} · ${state==='MANUAL_ECO'?'Eco reported':state.toLowerCase()} · Cooling target ${format(s.target_cool_temperature,1,' °C')} · ${s.source==='gap'?'No recent reading':'Estimated from recorded states'}`;
                button.title=label;button.setAttribute('aria-label',label);button.addEventListener('click',()=>{detail.textContent=label;});track.append(button);
            });card.append(track);
        }
        card.append(detail);
        const comparison=element('details');comparison.append(element('summary','Schedule and away comparison for this date'));
        const key='villa28-reference:'+device.device_id+':'+data.day;
        let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}');}catch{}
        const scheduleLabel=element('label','Reference cooling targets · one period per line, e.g. 08:00-18:00 24');
        const schedule=element('textarea');schedule.value=saved.schedule||'';scheduleLabel.append(schedule);
        const awayLabel=element('label','Known away periods · one period per line, e.g. 09:00-17:00. Entered manually, not sensed.');
        const away=element('textarea');away.value=saved.away||'';awayLabel.append(away);
        const apply=element('button','Save comparison in this browser','btn');apply.type='button';
        const message=element('p','No reference supplied. Complete the schedule workbook or enter periods here.','notice');
        function compare(save) {
            try {
                const plan=parseReference(schedule.value,true), absent=parseReference(away.value,false);
                if(save)localStorage.setItem(key,JSON.stringify({schedule:schedule.value,away:away.value}));
                let mismatch=0,compared=0,ecoAway=0,offAway=0,unknownAway=0;
                for(const s of device.segments) {
                    const a=(Date.parse(s.start)-start)/60000,b=(Date.parse(s.end)-start)/60000;
                    for(const p of plan) {const overlap=Math.max(0,Math.min(b,p.b)-Math.max(a,p.a));if(numeric(s.target_cool_temperature)){compared+=overlap;if(Math.abs(s.target_cool_temperature-p.target)>0.15)mismatch+=overlap;}}
                    for(const p of absent){const overlap=Math.max(0,Math.min(b,p.b)-Math.max(a,p.a));if(s.eco==='MANUAL_ECO')ecoAway+=overlap;else if(s.eco==='OFF')offAway+=overlap;else unknownAway+=overlap;}
                }
                const parts=[];
                if(plan.length)parts.push(`Reference target differs for about ${minutesText(mismatch)} of ${minutesText(compared)} with known targets. This does not prove a schedule fault.`);
                if(absent.length)parts.push(`During entered away periods so far: Eco reported ${minutesText(ecoAway)}, Eco off ${minutesText(offAway)}, unknown ${minutesText(unknownAway)}. This cannot establish what triggered Eco.`);
                message.textContent=parts.join(' ')||'No reference supplied. Complete the schedule workbook or enter periods here.';
            }catch(error){message.textContent=error.message;}
        }
        apply.addEventListener('click',()=>compare(true));comparison.append(scheduleLabel,awayLabel,apply,message);card.append(comparison);container.append(card);compare(false);
    });
}
async function loadRuntime() {
    $('runtime-status').textContent='Loading recorded activity…';
    try {renderRuntime(await api('/api/thermostat-timeline?day='+encodeURIComponent($('runtime-day').value)));}
    catch(error){$('runtime-status').textContent=error.message;}
}
$('runtime-day').value=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Dubai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
$('runtime-load').addEventListener('click',loadRuntime);
loadRuntime();
