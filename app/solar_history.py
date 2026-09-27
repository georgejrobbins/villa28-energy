"""Counter differences, preserving resets, missing samples and provider timestamps."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import math

FIELDS = {'generation_kwh':'daily_generation','import_kwh':'grid_import_daily','export_kwh':'grid_export_daily'}

def solar_intervals(rows, gap_seconds=660):
    result=[]
    previous=None
    for row in rows:
        stamp=row.timestamp
        if row.provider_time:
            try:
                stamp=datetime.strptime(row.provider_time,'%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo('Asia/Dubai')).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                pass
        item={'timestamp':stamp.isoformat()+'Z','instantaneous_power':row.instantaneous_power,
              'daily_generation':row.daily_generation,'grid_import_daily':row.grid_import_daily,
              'grid_export_daily':row.grid_export_daily, **{key:None for key in FIELDS}}
        if previous:
            prev_row,prev_stamp=previous
            elapsed=(stamp-prev_stamp).total_seconds()
            # Duplicate/stale provider data must not look like a new zero-energy interval.
            if elapsed <= 0:
                continue
            same_day=(stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Dubai')).date()==prev_stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Dubai')).date())
            if same_day and elapsed <= gap_seconds:
                for target,source in FIELDS.items():
                    a,b=getattr(prev_row,source),getattr(row,source)
                    if isinstance(a,(int,float)) and isinstance(b,(int,float)) and math.isfinite(a) and math.isfinite(b) and b>=a:
                        item[target]=round(b-a,6)
            item['interval_minutes']=round(elapsed/60,2)
        previous=(row,stamp)
        result.append(item)
    return result
