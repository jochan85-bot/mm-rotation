// test_groups.py 가 호출: 입력 JSON {rows:{티커:행}, tickers:[...]} → 엔진 dayScores 결과 JSON 출력
const fs = require('fs'), path = require('path');
const G = require(path.resolve(__dirname, '..', 'docs', 'assets', 'groups.js'));
const inp = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')), tset = {}; inp.tickers.forEach(t => tset[t] = 1);
console.log(JSON.stringify(G.dayScores(inp.rows, tset).map(x => ({ t: x.t, p: x.p, M: x.M, rank: x.rank }))));
