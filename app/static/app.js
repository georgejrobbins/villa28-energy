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
        metric(card, 'Mode', t.mode || 'Unknown'); metric(card, 'AC activity', t.hvac_status === 'COOLING' ? 'Cooling' : t.hvac_status === 'OFF' ? 'Idle' : t.hvac_status || 'Unknown');
        metric(card, 'Connectivity', t.connectivity || 'Unknown');
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

        metric(card, 'Solar power now', format(numeric(s.instantaneous_power) ? s.instantaneous_power / 1000 : null, 2, ' kW'));
        metric(card, 'Solar produced today', format(s.daily_generation, 2, ' kWh'));
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
        const data = await api('/api/current');
        renderThermostats(data.thermostats); renderSolar(data.solar); updateDeviceList(data);
        loadPresence();
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
        ctx.strokeStyle=s.color;ctx.fillStyle=s.color;ctx.lineWidth=2;ctx.beginPath();let started=false,previous=null;
        rows.forEach(row => { if (!numeric(row[s.key])) {started=false;return;} const xx=x(new Date(row.timestamp).getTime()), yy=y(row[s.key]);const gap=previous && new Date(row.timestamp)-new Date(previous.timestamp)>660000; const reset=previous && s.daily && dubaiDay(previous.timestamp)!==dubaiDay(row.timestamp);if(started && !gap && !reset)ctx.lineTo(xx,yy);else ctx.moveTo(xx,yy);started=true;previous=row; });ctx.stroke();
        if(rows.length===1 && numeric(rows[0][s.key])) {ctx.beginPath();ctx.arc(x(minTime),y(rows[0][s.key]),4,0,2*Math.PI);ctx.fill();}
    });
    ctx.fillStyle='#50635b';ctx.fillText(new Date(minTime).toLocaleString('en-GB',{timeZone:'Asia/Dubai'}),pad.left,canvas.height-12);ctx.textAlign='right';ctx.fillText(new Date(maxTime).toLocaleString('en-GB',{timeZone:'Asia/Dubai'}),canvas.width-pad.right,canvas.height-12);
    const legend=element('div',undefined,'chart-legend'); for(const s of series){const item=element('span');const swatch=element('span',undefined,'legend-swatch');swatch.style.backgroundColor=s.color;item.append(swatch,document.createTextNode(s.label+' ('+unit+')'));legend.append(item);} card.append(canvas,legend);container.append(card);
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

$('load-history').addEventListener('click',loadHistory);
refresh().then(() => {if(devices.length) loadHistory();});



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
function minutesText(value) {const minutes=Math.round(value);return `${Math.floor(minutes/60)}h ${minutes%60}m`;}
function renderRuntime(data) {
    const container=$('runtime-list');container.replaceChildren();
    const start=Date.parse(data.start), end=Date.parse(data.end), span=end-start;
    $('runtime-status').textContent=`${data.day} · Dubai time · ${data.devices.length} rooms · More than ${data.gap_minutes} minutes without a reading is unknown. History begins when monitoring was connected.`;
    data.devices.forEach(device=>{
        const card=element('article',undefined,'runtime-row');card.append(element('h3',device.device_name));
        const totals=device.minutes;
        card.append(element('p',`Estimated cooling ${minutesText(totals.COOLING)} · Idle ${minutesText(totals.OFF)} · Unknown ${minutesText(totals.UNKNOWN)}`));
        const detail=element('p','Select a coloured period to see times and the recorded target.','runtime-details');
        const axis=element('div',undefined,'runtime-axis');axis.append(element('span',dubaiTime(start)),element('span',dubaiTime(end)));card.append(axis);
        for(const kind of ['hvac']) {
            card.append(element('p',kind==='hvac'?'AC activity':'Nest manual Eco flag','legend'));
            const track=element('div',undefined,'runtime-track'+(kind==='eco'?' eco-track':''));
            device.segments.forEach(s=>{
                const state=kind==='hvac'?s.hvac:s.eco;
                const color=state==='MANUAL_ECO'?'eco':state.toLowerCase();
                const button=element('button',undefined,'runtime-segment runtime-'+color);
                button.type='button';button.style.width=((Date.parse(s.end)-Date.parse(s.start))/span*100)+'%';
                const label=`${dubaiTime(s.start)}–${dubaiTime(s.end)} · ${state==='MANUAL_ECO'?'Manual Eco reported':state==='OFF'?(kind==='hvac'?'Idle':'Manual Eco not reported'):state.toLowerCase()} · Cooling target ${format(s.target_cool_temperature,1,' °C')} · ${s.source==='gap'?'No recent reading':'Estimated from recorded states'}`;
                button.title=label;button.setAttribute('aria-label',label);button.addEventListener('click',()=>{detail.textContent=label;});track.append(button);
            });card.append(track);
        }
        card.append(detail);
        const comparison=element('details');comparison.append(element('summary','Schedule comparison for this date'));
        const key='villa28-reference:'+device.device_id+':'+data.day;
        let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}');}catch{}
        const scheduleLabel=element('label','Reference cooling targets · one period per line, e.g. 08:00-18:00 24');
        const schedule=element('textarea');schedule.value=saved.schedule||'';scheduleLabel.append(schedule);
        const apply=element('button','Save comparison in this browser','btn');apply.type='button';
        const message=element('p','No reference supplied. Complete the schedule workbook or enter periods here.','notice');
        function compare(save) {
            try {
                const plan=parseReference(schedule.value,true);
                if(save)localStorage.setItem(key,JSON.stringify({schedule:schedule.value}));
                let mismatch=0,compared=0;
                for(const s of device.segments) {
                    const a=(Date.parse(s.start)-start)/60000,b=(Date.parse(s.end)-start)/60000;
                    for(const p of plan) {const overlap=Math.max(0,Math.min(b,p.b)-Math.max(a,p.a));if(numeric(s.target_cool_temperature)){compared+=overlap;if(Math.abs(s.target_cool_temperature-p.target)>0.15)mismatch+=overlap;}}
                }
                const parts=[];
                if(plan.length)parts.push(`Reference target differs for about ${minutesText(mismatch)} of ${minutesText(compared)} with known targets. This does not prove a schedule fault.`);
                message.textContent=parts.join(' ')||'No reference supplied. Complete the schedule workbook or enter periods here.';
            }catch(error){message.textContent=error.message;}
        }
        apply.addEventListener('click',()=>compare(true));comparison.append(scheduleLabel,apply,message);card.append(comparison);container.append(card);compare(false);
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

async function loadSolarHistory() {
    const container=$('solar-history-charts');
    $('solar-history-status').textContent='Loading solar history…';
    try {
        const data=await api('/api/solar-timeline?hours='+$('solar-hours').value);container.replaceChildren();
        let count=0;
        for(const plant of data.installations){
            const rows=plant.readings;count+=rows.length;if(!rows.length)continue;
            container.append(element('h3',plant.name||`Installation ${plant.installation_id}`));
            renderSolarReview(container,rows);
            drawChart(container,rows.map(r=>({...r,power_kw:numeric(r.instantaneous_power)?r.instantaneous_power/1000:null})),[{key:'power_kw',label:'Solar power',color:'#d98235'}],'Solar output throughout the day','kW');
            const intervals=element('details',undefined,'interval-details');intervals.append(element('summary','Five-minute energy detail'));
            intervals.append(element('p','Energy added during each reading interval: orange is solar generated, red is electricity bought from the grid, green is electricity exported. For example, 0.5 kWh in five minutes is an average of 6 kW. This helps locate short periods of grid demand; it is not a running daily total. Intervals can vary; missing readings and counter resets are omitted.','notice'));
            drawChart(intervals,rows,[{key:'generation_kwh',label:'Produced',color:'#d98235'},{key:'import_kwh',label:'Imported',color:'#bf5252'},{key:'export_kwh',label:'Exported',color:'#137b60'}],'Energy per reading interval','kWh');
            container.append(intervals);
            drawChart(container,rows,[{key:'daily_generation',daily:true,label:'Produced today',color:'#d98235'},{key:'grid_import_daily',daily:true,label:'Imported today',color:'#bf5252'},{key:'grid_export_daily',daily:true,label:'Exported today',color:'#137b60'}],'Energy accumulated since midnight','kWh');
        }
        $('solar-history-status').textContent=count?`${count} provider readings. ${data.note}`:'Waiting for solar readings. Charts appear after collection; interval energy requires two readings.';
    }catch(error){$('solar-history-status').textContent=error.message;}
}
$('solar-load').addEventListener('click',loadSolarHistory);
loadSolarHistory();

async function loadPresence() {
    const box=$('presence-history');
    try {
        const data=await api('/api/presence?day='+encodeURIComponent($('runtime-day').value));
        $('presence-current').textContent=!data.connected?'Home/Away not linked':data.state==='UNKNOWN'?'Home/Away unknown — waiting for first update':data.state==='AWAY'?'Away from property':'At home';
        $('presence-note').textContent=(data.last_received?'Last signal: '+new Date(data.last_received).toLocaleString('en-GB',{timeZone:'Asia/Dubai'})+' Dubai time. ':'')+data.note;
        box.replaceChildren();
        const track=element('div',undefined,'runtime-track presence-track');
        const width=new Date(data.end)-new Date(data.start);
        const detail=element('p','Select a period for its recorded times.','runtime-details');
        for(const segment of data.segments) {
            const name=segment.state==='AWAY'?'Away from property':segment.state==='HOME'?'At home':'Unknown';
            const label=`${dubaiTime(segment.start)}–${dubaiTime(segment.end)} · ${name}`;
            const button=element('button',name,'presence-segment presence-'+segment.state.toLowerCase());
            button.style.width=((new Date(segment.end)-new Date(segment.start))/width*100)+'%';
            button.title=label; button.setAttribute('aria-label',label);
            button.addEventListener('click',()=>{detail.textContent=label;}); track.append(button);
        }
        box.append(track,detail);
        const events=element('ul');
        data.events.forEach(event=>events.append(element('li',`${dubaiTime(event.timestamp)} · ${event.state==='AWAY'?'Away from property':event.state==='HOME'?'At home':'Connection removed / unknown'}`)));
        if(data.events.length) box.append(events);
        else box.append(element('p','No Home/Away updates recorded on this day.'));
    } catch(error) { $('presence-note').textContent='Could not load Home/Away: '+error.message; }
}
$('runtime-load').addEventListener('click',loadPresence);
loadPresence();

function dubaiDay(value) {
    return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Dubai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
}
function solarDailyRows(rows) {
    const days=new Map();
    for(const row of rows) {
        const day=dubaiDay(row.timestamp);
        let item=days.get(day);
        if(!item){item={day,first:row.timestamp,last:row.timestamp,peak:null,generation:null,imported:null,exported:null,count:0};days.set(day,item);}
        item.last=row.timestamp;item.count++;
        item.generation=numeric(row.daily_generation)?row.daily_generation:null;
        item.imported=numeric(row.grid_import_daily)?row.grid_import_daily:null;
        item.exported=numeric(row.grid_export_daily)?row.grid_export_daily:null;
        if(numeric(row.instantaneous_power))item.peak=Math.max(item.peak??0,row.instantaneous_power/1000);
    }
    return [...days.values()];
}
function renderSolarReview(container,rows) {
    const card=element('article',undefined,'chart-card');card.append(element('h3','Daily solar review'));
    card.append(element('p','Compare dates below. Energy figures are the provider’s daily counters at the last reading, not a sum of the running totals. Today is still in progress; other dates may also be incomplete. Peak power is the highest recorded sample.','notice'));
    const wrap=element('div',undefined,'table-scroll');const table=element('table');
    const head=element('thead'),tr=element('tr');
    ['Date · Dubai','Solar produced','Grid imported','Grid exported','Peak solar','Last reading'].forEach(label=>tr.append(element('th',label)));
    head.append(tr);table.append(head);const body=element('tbody');
    for(const day of solarDailyRows(rows)) {
        const row=element('tr');
        [day.day+(day.day===dubaiDay(new Date())?' · today':''),format(day.generation,1,' kWh'),format(day.imported,1,' kWh'),format(day.exported,1,' kWh'),format(day.peak,2,' kW'),dubaiTime(day.last)+(dubaiTime(day.last)<'23:45'?' · partial day':'')].forEach(value=>row.append(element('td',value)));
        body.append(row);
    }
    table.append(body);wrap.append(table);card.append(wrap);
    card.append(element('p','Look for repeatable patterns: daytime imports identify times to compare against AC demand; exports show when solar is being sent to the grid. Exported energy is not necessarily wasted—it may earn credit. These readings do not measure electricity used by each AC unit.','notice'));
    container.append(card);
}
