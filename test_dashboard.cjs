const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
function boot(jobs){
 const dom={};const store=new Map([['career_feed_autosync','0'],['youyue_career_dashboard_v2',JSON.stringify(jobs)]]);
 const elem=id=>dom[id]??={value:id==='poolFilter'?'inbox':'',innerHTML:'',textContent:'',style:{},hidden:false,open:false,showModal(){this.open=true},close(){this.open=false},scrollIntoView(){},setAttribute(){},classList:{toggle(){}}};
 const ctx={document:{getElementById:elem,querySelectorAll:()=>[]},localStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)},URL,Intl,console,setTimeout:()=>0,clearTimeout(){},location:{protocol:'http:'},alert(){},confirm:()=>true,window:{scrollTo(){}}};
 vm.createContext(ctx);for(const script of scripts)vm.runInContext(script,ctx);return{ctx,dom,store,run:s=>vm.runInContext(s,ctx)};
}
const legacy={id:'old',org:'手动单位',role:'旧岗位',country:'中国',track:'科研',url:'https://example.org/old',status:'已投递',notes:'私人备注',contact:'my contact'};
const lead={id:'new',org:'机构待核实',role:'Museum coordinator vacancy',track:'博物馆',url:'https://example.org/new',status:'待核实',verified:'2026-10-19',fit:99};
const {ctx,dom,run,store}=boot([legacy,lead]);
assert.equal(dom.nApplied.textContent,1);assert.equal(dom.nSaved.textContent,0);
assert.ok(!dom.todayActions.innerHTML.includes('Museum coordinator'));
assert.ok(dom.leadList.innerHTML.includes('Museum coordinator'));
assert.ok(!dom.leadList.innerHTML.includes('99/100'));assert.ok(!dom.leadList.innerHTML.includes('机构待核实'));
run('toggleSaved("new")');assert.equal(dom.nSaved.textContent,1);assert.ok(dom.applicationList.innerHTML.includes('Museum coordinator'));
assert.equal(run('data.find(j=>j.id==="old").notes'),'私人备注');
run('openOpportunity("new")');assert.equal(dom.detailDialog.open,true);assert.ok(dom.detailBody.innerHTML.includes('申请前还需确认'));
run('setStage("new","准备申请")');assert.equal(dom.nPreparing.textContent,1);assert.equal(dom.nSaved.textContent,0);
run('dismissLead("new")');assert.equal(dom.nPreparing.textContent,0);assert.equal(run('data.find(j=>j.id==="new").status'),'准备申请');
run('restoreLead("new")');assert.equal(dom.nPreparing.textContent,1);
run('importCandidateFeed({generated_at:"2026-10-19T00:00:00Z",jobs:[{url:"https://example.org/new",role:"overwrite",notes:"bad"},{url:"https://example.edu/jobs/1",role:"Programme Coordinator",track:"全球跨专业工作",source_kind:"official",source_id:"a",official_url:"https://example.edu/jobs/1"}]})');
assert.equal(run('data.length'),3);assert.equal(run('data.find(j=>j.id==="new").status'),'准备申请');assert.equal(run('data.at(-1).verification_status'),'lead');
assert.equal(run('data.at(-1).source_kind'),'official');assert.equal(dom.nPreparing.textContent,1);
assert.equal(run('isReading({role:"UNV Online Volunteer Opportunity",track:"资助志愿者"})'),true);
assert.equal(run('isReading({role:"Museum curator vacancy",track:"博物馆"})'),false);
run('showView("discover")');run('showView("applications")');
assert.ok(store.get('career_radar_workspace_v1'));console.log('PASS: startup, legacy storage, inbox separation, no fake relevance score, follow, prepare, archive/restore, source details, dedupe and progress preservation, reading classification, navigation');
