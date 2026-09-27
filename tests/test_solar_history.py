from datetime import datetime,timedelta
from types import SimpleNamespace
from app.solar_history import solar_intervals

def row(time,gen=10,imp=5,exp=2):
 return SimpleNamespace(timestamp=time,provider_time=None,instantaneous_power=7000,daily_generation=gen,grid_import_daily=imp,grid_export_daily=exp)

def test_deltas_resets_and_gaps():
 t=datetime(2026,9,27,6)
 data=solar_intervals([row(t),row(t+timedelta(minutes=5),11,6,2.2),row(t+timedelta(minutes=10),1,0,0),row(t+timedelta(hours=1),2,1,1)])
 assert data[0]['generation_kwh'] is None
 assert data[1]['generation_kwh']==1 and data[1]['import_kwh']==1 and data[1]['export_kwh']==0.2
 assert data[2]['generation_kwh'] is None and data[3]['generation_kwh'] is None

def test_duplicate_provider_timestamp_is_not_new_interval():
 t=datetime(2026,9,27,6);a=row(t);b=row(t+timedelta(minutes=5))
 a.provider_time=b.provider_time='20260927100000'
 assert len(solar_intervals([a,b]))==1

def test_day_reset_even_when_counter_increases():
 t=datetime(2026,9,27,19,59)
 assert solar_intervals([row(t),row(t+timedelta(minutes=5),11)])[1]['generation_kwh'] is None

def test_export_requires_auth(client):
 assert client.get('/api/export-history?provider=nest').status_code==200
 client.auth=None
 assert client.get('/api/export-history?provider=nest').status_code==401


def test_week_keeps_every_five_minute_sample_and_export(client):
 from app.database import SessionLocal
 from app.models import SolarReading,ThermostatReading
 import csv,io
 end=datetime.utcnow()-timedelta(minutes=1)
 times=[end-timedelta(minutes=5*i) for i in reversed(range(2016))]
 with SessionLocal.begin() as db:
  db.add_all(SolarReading(installation_id='plant',timestamp=t,instantaneous_power=7000,daily_generation=10) for t in times)
  db.add_all(ThermostatReading(device_id='zone',device_name='Zone',timestamp=t,hvac_status='COOLING',ambient_temperature=24) for t in times)
 history=client.get('/api/history?device_id=zone&installation_id=plant&hours=168').json()
 assert len(history['thermostats'])==len(history['solar'])==2016
 assert not history['thermostats_limit_reached']
 assert len(client.get('/api/solar-timeline?hours=168').json()['installations'][0]['readings'])==2016
 for provider in ['nest','solar']:
  exported=list(csv.DictReader(io.StringIO(client.get('/api/export-history?provider='+provider+'&days=7').text)))
  assert len(exported)==2016
  assert all((datetime.fromisoformat(b['timestamp'])-datetime.fromisoformat(a['timestamp'])).total_seconds()==300 for a,b in zip(exported,exported[1:]))
