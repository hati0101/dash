const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('docs/sched.js','utf8');
const status=source.slice(source.indexOf('const STATUS ='),source.indexOf('const PRI ='));
const fn=source.slice(source.indexOf('function discordText()'),source.indexOf('async function requestPublish'));
function render(tasks){return vm.runInNewContext(status+'\nconst S={tasks: '+JSON.stringify(tasks)+'};\n'+fn+'\ndiscordText()');}
const keys=['doing','review','todo','hold','done'];
const tasks=keys.map(status=>({status,public:true,title:'제목-'+status,detail:'PRIVATE DETAIL',log:['PRIVATE LOG']}));
tasks.push({status:'doing',public:false,title:'PRIVATE TITLE'},{status:'doing',public:'true',title:'INVALID PUBLIC'},{status:'removed',public:true,title:'INVALID STATUS'});
tasks[0].pubTitle='공개용 제목';
let r=render(tasks);assert.equal(r.count,5);for(const label of ['진행 중','검토','대기','보류','완료'])assert(r.text.includes('['+label+'] 1건'));for(const privateText of ['PRIVATE','INVALID','제목-doing','확인 대기'])assert(!r.text.includes(privateText));assert(r.text.includes('공개용 제목'));
assert.equal(render([]).count,0);
r=render(keys.flatMap(status=>Array.from({length:150},(_,i)=>({status,public:true,title:'가'.repeat(100)+i}))));assert.equal(r.count,750);assert(r.text.length<=2000);for(const label of ['진행 중','검토','대기','보류','완료'])assert(r.text.includes('['+label+'] 150건'));assert(r.text.includes('생략'));
console.log('PASS: five status groups, review label, private fields excluded, public title, empty state, 750-item length limit');
console.log(render(tasks).text);