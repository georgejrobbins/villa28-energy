"""Sample-based runtime estimates; gaps are unknown, never silently off."""
from datetime import timedelta


def build_timeline(rows, start, end, max_gap_seconds):
    segments = []
    def add(a, b, row=None):
        if b <= a:
            return
        online = row is not None and row.connectivity == 'ONLINE'
        hvac = row.hvac_status if online and row.hvac_status in {'COOLING', 'HEATING', 'OFF'} else 'UNKNOWN'
        eco = row.eco_state if online and row.eco_state in {'MANUAL_ECO', 'OFF'} else 'UNKNOWN'
        segment = {'start': a.isoformat()+'Z', 'end': b.isoformat()+'Z', 'hvac': hvac, 'eco': eco,
                   'target_cool_temperature': row.target_cool_temperature if online else None,
                   'source': row.source if row else 'gap'}
        if segments and all(segments[-1][k] == segment[k] for k in ('hvac','eco','target_cool_temperature','source')) and segments[-1]['end'] == segment['start']:
            segments[-1]['end'] = segment['end']
        else:
            segments.append(segment)
    cursor = start
    for index,row in enumerate(rows):
        next_time = rows[index+1].timestamp if index+1 < len(rows) else end
        a = max(start, row.timestamp)
        b = min(end, next_time, row.timestamp+timedelta(seconds=max_gap_seconds))
        if a > cursor:
            add(cursor, min(a,end))
        add(a,b,row)
        cursor = max(cursor,b)
        if cursor >= end:
            break
    add(cursor,end)
    totals = {k:0 for k in ['COOLING','HEATING','OFF','UNKNOWN','ECO']}
    from datetime import datetime
    for segment in segments:
        seconds = (datetime.fromisoformat(segment['end'])-datetime.fromisoformat(segment['start'])).total_seconds()
        totals[segment['hvac']] += seconds
        if segment['eco']=='MANUAL_ECO':
            totals['ECO'] += seconds
    return {'segments':segments,'minutes':{k:round(v/60,1) for k,v in totals.items()}}
