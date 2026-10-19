const assert=require('node:assert/strict'),fs=require('node:fs');
const {boot}=require('./test_dashboard.cjs');
const jd='招聘岗位：国际项目协调员。\n岗位职责：负责组织学术活动，协调会议并撰写研究报告。\n学历要求：须已取得考古学或相关专业博士学位。\n成果要求：至少已发表一篇CSSCI论文。\n语言要求：IELTS总分不低于7.0。\n申请截止日期：2026年10月10日。\n申请材料：CV、求职信及两封推荐信。\n待遇：提供生活津贴，国际旅行费用需自行核实。\n签证：是否提供work permit sponsorship请咨询招聘方。';
const profile={degree:'phd_candidate',field:'考古学',graduation:'2026-12',language:'雅思总分6.5，口语6.0',papers:'一篇CSSCI论文已录用待刊，尚未正式发表',experience:'组织过两场学术会议，负责日程协调。\n撰写文化遗产研究报告，使用史料与图像分析。',english:'',eligibility:'尚未获得目标国家工作许可',goal:'balanced',confirmed:true};
function enterProfile(t,p=profile){for(const [key,id] of Object.entries(t.run('PROFILE_FIELDS')))t.dom[id].value=p[key]||'';t.dom.profileConfirmed.checked=!!p.confirmed;t.run('saveApplicationProfile()')}
async function main(){
 const t=boot([]);t.ctx.fixtureJD=jd;t.ctx.fixtureProfile=profile;
 const report=t.run('buildApplicationAssessment({jd:fixtureJD},fixtureProfile)');
 assert.equal(report.rows.find(r=>r.key==='degree').status,'gap');
 assert.equal(report.rows.find(r=>r.key==='papers').status,'gap');
 assert.equal(report.rows.find(r=>r.key==='language').status,'gap');
 assert.equal(report.rows.find(r=>r.key==='deadline').status,'gap');
 assert.equal(report.closingDate,'2026-10-10');assert.ok(report.questions[0].startsWith('我的学历情况'));
 assert.ok(report.rows.find(r=>r.key==='degree').quotes[0].includes('须已取得'));
 const minimal=t.run('buildApplicationAssessment({jd:"岗位职责：组织研究活动，撰写报告。"},fixtureProfile)');
 assert.equal(minimal.rows.find(r=>r.key==='eligibility').status,'unknown');
 assert.equal(t.run('closingDateFromQuotes(["报名时间2026年9月1日至9月15日"])'),'');
 assert.equal(t.run('closingDateFromQuotes(["截止2026年2月31日"])'),'');
 t.dom.toolOrg.value='示例大学';t.dom.toolRole.value='国际项目协调员';t.dom.toolUrl.value='https://example.org/careers/123';t.dom.toolJD.value=jd;
 assert.equal(t.run('evaluateApplication()'),null);assert.equal(t.dom.profileDetails.open,true);
 enterProfile(t);t.run('evaluateApplication()');assert.ok(t.dom.applicationAssessment.innerHTML.includes('公告'));
 t.run('generateApplicationPack()');const draft=t.dom.packOutput.value;
 assert.ok(draft.includes('国际项目协调员'));assert.ok(draft.includes(profile.experience.split('\n')[0]));
 assert.ok(draft.includes('博士在读'));assert.ok(!draft.includes('我已取得博士'));assert.ok(!draft.includes('已发表一篇CSSCI论文，'));assert.ok(draft.includes('录用待刊'));
 assert.ok(draft.includes('推荐信'));assert.ok(draft.includes('是否仍开放'));assert.ok(draft.includes('【署名】'));
 t.run('savePreparation()');const id=t.run('toolActiveId');assert.ok(id);assert.equal(t.run('currentDraftKey===draftKey(captureToolWorkspace(),applicationProfile())'),true);assert.ok(t.run('extra.preparations[toolActiveId].draft').includes('国际项目协调员'));
 assert.equal(t.run('data[0].status'),'待核实');assert.equal(t.run('data[0].jd'),undefined);assert.equal(t.run('data[0].profile'),undefined);
 const saved=t.run('extra.applicationWorkspace');assert.ok(saved.assessment);assert.ok(saved.draftKey);
 t.dom.toolJD.value=jd+'\n请追加研究计划。';t.run('toolInputChanged()');assert.equal(t.run('currentAssessment'),null);assert.equal(t.run('currentDraftKey'),'');
 t.run('copyApplicationPack()');assert.ok(t.dom.toast.textContent.includes('变化'));
 t.run('generateApplicationPack()');assert.ok(t.dom.packOutput.value.includes('研究计划'));
 t.dom.packLanguage.value='en';t.run('markDraftStale();generateApplicationPack()');assert.ok(t.dom.packStatus.textContent.includes('英文简介'));
 const english={...profile,english:'I am a doctoral candidate in archaeology. I have coordinated academic events and prepared research reports.'};enterProfile(t,english);t.run('generateApplicationPack()');assert.ok(t.dom.packOutput.value.includes(english.english));assert.ok(!t.dom.packOutput.value.includes('Sun Yat-sen'));
 t.run('profileChanged();copyApplicationPack()');assert.ok(t.dom.toast.textContent.includes('变化'));
 // The link reader sends only the selected public URL, with credentials omitted.
 t.dom.toolJD.value='';t.dom.toolUrl.value='https://example.org/public/job';let calls=[];
 t.ctx.fetch=async (url,options)=>{calls.push({url,options});return{ok:true,headers:{get:name=>name==='content-type'?'text/html':''},text:async()=>'<html><title>项目协调岗位</title><script>alert("never run")</script><p>'+jd+'</p></html>'}};
 await t.run('readJobLink()');assert.ok(t.dom.toolJD.value.includes('学历要求'));assert.ok(!t.dom.toolJD.value.includes('alert('));assert.equal(calls[0].options.credentials,'omit');assert.equal(calls[0].options.body,undefined);assert.equal(calls[0].url,'https://example.org/public/job');
 const keep=t.dom.toolJD.value;t.ctx.fetch=async()=>{throw Error('CORS')};await t.run('readJobLink()');assert.equal(t.dom.toolJD.value,keep);assert.ok(t.dom.readerStatus.textContent.includes('未能读取'));
 t.dom.toolUrl.value='javascript:alert(1)';await t.run('readJobLink()');assert.ok(t.dom.readerStatus.textContent.includes('HTTPS'));
 assert.equal(t.run('readableJobText("<style>x</style><p>&lt;hello&gt;</p><script>bad()</script>")'),'<hello>');
 const allHTML=fs.readFileSync(__dirname+'/index.html','utf8');assert.ok(!allHTML.includes('尤悦'));assert.ok(!allHTML.includes('avatar">悦'));assert.ok(!fs.readFileSync(__dirname+'/README.md','utf8').includes('尤悦'));
 console.log('PASS: evidence and gap rules, deadlines, profile confirmation, non-fabricated drafts, material extraction, local persistence, stale-result blocking, English gating, link fetch privacy/failure, HTML stripping and name removal');
}
main().catch(e=>{console.error(e);process.exitCode=1});
