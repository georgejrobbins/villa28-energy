'use strict';
const $ = id => document.getElementById(id);
async function api(path) {
    const response = await fetch(path, {cache: 'no-store'});
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || body.message || `Request failed (${response.status})`);
    }
    return response.json();
}

async function refreshAdmin(){try {const status=await api('/api/status');
        const g = status.google;
        $('google-status').textContent = !g.configured ? 'Google credentials and Device Access project ID are required in Railway.' : !g.encryption_ready ? 'The token encryption key needs configuration in Railway.' : !g.connected ? 'Ready to connect your Nest account.' : g.polling.state === 'error' ? 'Connected, but the latest poll failed. Check the Railway logs.' : 'Google Nest connected. Polling every ' + Math.round(status.polling_interval_seconds / 60) + ' minutes.';
        $('pubsub-status').textContent = g.pubsub.state === 'listening' ? 'Live events: listening' : g.pubsub.state === 'error' ? 'Live events: reconnecting; polling remains active.' : 'Live events: Pub/Sub service account and subscription setup required.';
        $('google-auth').disabled = !g.configured || !g.encryption_ready;
        $('google-auth').textContent = g.connected ? 'Reconnect Google Nest' : 'Connect Google Nest';
        const sg = status.sungrow;
        $('sungrow-status').textContent = !sg.configured ? 'Sungrow credentials need configuration in Railway.' : !sg.connected ? 'Ready to connect your iSolarCloud installation.' : sg.polling.state === 'error' ? 'Connected, but the latest reading failed. Check Railway logs.' : 'Sungrow connected. Readings update every five minutes or the configured longer interval.';
        $('sungrow-auth').disabled = !sg.configured || !sg.encryption_ready;
        $('sungrow-auth').textContent = sg.connected ? 'Reconnect Sungrow' : 'Connect Sungrow';

const presence=await api('/api/presence'); $('home-status').textContent=presence.connected?'Connected. Home/Away updates are recorded by the virtual indicator.':presence.configured?'Ready to link Villa28 Presence in Google Home.':'Google Home presence is not configured.'; }catch(error){$('error').textContent=error.message;$('error').hidden=false;}}
$('google-auth').addEventListener('click', async () => {try {const data=await api('/auth/google');window.location.assign(data.auth_url);} catch(error) {$('error').textContent=error.message;$('error').hidden=false;}});
$('sungrow-auth').addEventListener('click', async () => {try {const data=await api('/auth/sungrow');window.location.assign(data.auth_url);} catch(error) {$('error').textContent=error.message;$('error').hidden=false;}});
refreshAdmin();
