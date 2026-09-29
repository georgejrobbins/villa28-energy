const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function node() {return {children:[],append(...children){this.children.push(...children);},replaceChildren(){this.children=[];},addEventListener(){},options:[]};}
function setup() {
  const nodes = new Map();
  const context = vm.createContext({document:{getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},createElement(){return node();},createTextNode(text){return {textContent:text};}},fetch:()=>new Promise(()=>{}),URLSearchParams,Date,console,setTimeout,clearTimeout});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/app.js'),'utf8'),context);
  return {context,nodes};
}
test('missing numeric readings render safely',()=>{const {context,nodes}=setup();vm.runInContext('renderThermostats([{device_name:"Zone", ambient_temperature:null,humidity:null,target_temperature:null,timestamp:new Date().toISOString()}]); renderSolar([{installation_id:"A",daily_generation:null}]);',context);assert.equal(nodes.get('thermostat-list').children.length,1);assert.equal(nodes.get('solar-list').children.length,1);assert.equal(vm.runInContext('format(null)',context),'Not available');assert.equal(vm.runInContext('format(0)',context),'0.0');});
test('device labels are text rather than HTML',()=>{const {context,nodes}=setup();vm.runInContext('renderThermostats([{device_name:"<img src=x onerror=alert(1)>",timestamp:new Date().toISOString()}]);',context);const heading=nodes.get('thermostat-list').children[0].children[0];assert.equal(heading.textContent,'<img src=x onerror=alert(1)>');assert.equal(heading.innerHTML,undefined);});
test('daily review keeps final counters rather than summing cumulative readings',()=>{const {context}=setup();const result=vm.runInContext(`solarDailyRows([{timestamp:'2026-09-28T19:50:00Z',daily_generation:50,grid_import_daily:20,grid_export_daily:10,instantaneous_power:0},{timestamp:'2026-09-28T19:55:00Z',daily_generation:50,grid_import_daily:21,grid_export_daily:10,instantaneous_power:0},{timestamp:'2026-09-28T20:05:00Z',daily_generation:0,grid_import_daily:null,grid_export_daily:0,instantaneous_power:0}])`,context);assert.equal(result.length,2);assert.equal(result[0].generation,50);assert.equal(result[0].imported,21);assert.equal(result[1].generation,0);assert.equal(result[1].imported,null);});
