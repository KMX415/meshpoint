const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const golden = require('./fixtures/packet_meshtastic_baseline.json');
function load(source) {
 const ctx = vm.createContext({window:{}});
 vm.runInContext(source,ctx);
 return ctx.window.PacketDetailModal;
}
const file = 'frontend/js/packet_detail_modal.js';
const current = load(fs.readFileSync(file,'utf8'));

test('Meshtastic RF, routing and payload rows match unchanged baseline',()=>{
 for (const type of ['nodeinfo','text','encrypted','telemetry']) {
  for (const hop_start of [0,7]) {
   const p = {protocol:'meshtastic',packet_type:type,hop_start,hop_limit:5,hop_count:2,
    signal:{frequency_mhz:906.875,spreading_factor:11,bandwidth_khz:250,coding_rate:'4/8',rssi:-80,snr:0},
    decoded_payload:{text:'fixture'},decrypted:type!=='encrypted'};
   for(const method of ['_rfRows','_meshRows','_payloadRows'])
    assert.equal(JSON.stringify(current[method](p)),JSON.stringify(golden.details[`${type}-${hop_start}`][method]));
  }
 }
});
test('MeshCore historical placeholders and decoded adverts are honest',()=>{
 const p={protocol:'meshcore',packet_type:'nodeinfo',decrypted:false,
 signal:{frequency_mhz:0,spreading_factor:0,bandwidth_khz:0,coding_rate:'4/8',rssi:-53,snr:11},
 decoded_payload:{advertisement:{}}};
 assert.equal(current._rfRows(p)[0].val,'Not reported');
 assert.equal(current._rfRows(p)[1].val,'Not reported');
 assert.equal(current._payloadRows(p)[1].val,'Advertisement received');
 assert.equal(current._meshRows(p)[4].val,'Not reported');
 p.decoded_payload.meshcore_hops=0;
 assert.equal(current._meshRows(p)[4].val,'0 hops');
 p.decoded_payload.meshcore_hops=255;
 assert.equal(current._meshRows(p)[4].val,'Not reported');
});

function feed(source) {
 const ctx=vm.createContext({window:{}});
 vm.runInContext(source+';window.feed=Object.create(SimplePacketFeed.prototype)',ctx);
 const f=ctx.window.feed;
 f._esc=s=>s;
 return f;
}
test('Meshtastic table including preset selection matches baseline',()=>{
 const file='frontend/js/simple_packet_feed.js';
 const now=feed(fs.readFileSync(file,'utf8'));

 for(const packet_type of ['nodeinfo','text','telemetry']) {
  const p={timestamp:'2026-01-01T00:00:00Z',protocol:'meshtastic',packet_type,
   hop_start:7,hop_limit:5,decoded_payload:{long_name:'Fixture'},
   signal:{frequency_mhz:906.875,spreading_factor:11,rssi:-80,snr:0}};
  assert.equal(now._rowHtml(p).replace(/<td>[^<]*<\/td>/,'<td>TIME</td>'),golden.tables[packet_type]);
 }
});

test('MeshCore captured radio and hops populate table and detail',()=>{
 const f=feed(fs.readFileSync('frontend/js/simple_packet_feed.js','utf8'));
 const p={timestamp:'2026-01-01T00:00:00Z',protocol:'meshcore',packet_type:'nodeinfo',
 signal:{frequency_mhz:910.525,spreading_factor:7,bandwidth_khz:62.5,coding_rate:'4/5',rssi:-55,snr:8},
 decoded_payload:{advertisement:{},meshcore_hops:2,meshcore_receiver:{coding_rate:'4/5'}}};
 const html=f._rowHtml(p);
 assert.ok(html.includes('910.5'));
 assert.ok(html.includes('SF7'));
 assert.ok(html.includes('<td>2</td>'));
 const rows=current._rfRows(p);
 assert.equal(rows[0].val,'Receiver settings at capture');
 assert.equal(rows[1].val,'910.525 MHz');
 assert.ok(rows[2].val.includes('CR 4/5'));
 assert.equal(current._meshRows(p)[4].val,'2 hops');
});
