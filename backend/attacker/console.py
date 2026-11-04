"""공격자 수집 서버의 '탈취 데이터' 콘솔 페이지 (로컬 공격자 서버 / 배포 백엔드 공용).

고객 챗봇 화면 밖에서, 방어 OFF일 때 S2 공격으로 빠져나온 데이터를 별도로 보여 준다.
data_url만 환경에 따라 다르다: 로컬=/log.json(공격자 서버), 배포=/api/demo/attacker-log(백엔드).
"""

_CONSOLE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>공격자 수집 서버 · 탈취 데이터</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px;
    background: #0b0f14; color: #e6edf3;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    min-height: 100vh;
  }
  .wrap { width: 100%; max-width: 860px; margin: 0 auto; }
  h1 { font-size: clamp(17px, 1.1rem + 0.7vw, 23px); margin: 0 0 10px; color: #ff6b6b; line-height: 1.3; }
  .sub { color: #8b98a5; font-size: clamp(13px, 0.8rem + 0.35vw, 15px); margin: 0 0 16px; line-height: 1.75; }
  .bar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; font-size: 12px; color: #8b98a5; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #2ea043; box-shadow: 0 0 8px #2ea043; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: #8b98a5; font-weight: 600; font-size: 11px; padding: 8px 10px;
       border-bottom: 1px solid #222b36; text-transform: uppercase; letter-spacing: .04em; }
  td { padding: 10px; border-bottom: 1px solid #161b22; vertical-align: top; }
  .time { color: #8b98a5; white-space: nowrap; }
  .path { color: #58a6ff; white-space: nowrap; }
  .data { color: #ff7b72; font-weight: 700; word-break: break-all; }
  .empty { color: #8b98a5; padding: 36px; text-align: center; border: 1px dashed #222b36; border-radius: 10px; }
  .err { color: #ffa198; padding: 14px; border: 1px solid #3c1618; background: #1a0f10; border-radius: 10px; line-height: 1.6; }
  .whatbox { border: 1px solid #222b36; background: #11161d; border-radius: 10px; padding: 14px 16px; margin: 0 0 18px; font-size: clamp(13px, 0.8rem + 0.35vw, 15px); line-height: 1.8; color: #c9d4df; }
  .whatbox p { margin: 0 0 9px; }
  .whatbox p:last-child { margin-bottom: 0; }
  .whatbox b { color: #ff7b72; }
  .whatbox code { background: #0b0f14; border: 1px solid #222b36; border-radius: 4px; padding: 1px 5px; color: #58a6ff; word-break: break-all; }
  .controls { margin-left: auto; display: flex; align-items: center; gap: 6px; color: #8b98a5; }
  .controls select { background: #11161d; color: #e6edf3; border: 1px solid #222b36; border-radius: 6px; padding: 4px 8px; font-family: inherit; font-size: 12px; }
</style>
</head>
<body>
  <div class="wrap">
    <h1>&#9888; 공격자 수집 서버 &mdash; 탈취된 고객 데이터</h1>
    <p class="sub">공격자가 외부에 운영하는 데이터 수집 서버입니다. 방어 OFF일 때 S2(문서 속 숨은 지시) 공격이 성공하면, 피해 고객의 브라우저가 <b style="color:#ff7b72">고객 화면엔 아무 흔적도 남기지 않고</b> 이곳으로 개인정보를 몰래 전송합니다.</p>
    <div class="whatbox">
      <p><b>빠져나오는 데이터</b> &mdash; 로그인한 고객의 <b>이름 · 이메일 · 전화번호 · 계좌번호 · 잔액</b>.</p>
      <p>청구서 PDF 속 숨은 지시로 답변에 삽입된 코드가, 피해자 브라우저에서 세션 쿠키로 <code>/api/me</code>와 <code>/api/accounts/me</code>를 대신 조회해 긁어낸 뒤 이 서버(<code>/c?d=…</code>)로 흘려보냅니다.</p>
    </div>
    <div class="bar">
      <span class="dot"></span><span id="status">수신 대기 중&hellip;</span>
      <span class="controls">정렬
        <select id="order"><option value="newest">최신순</option><option value="oldest">오래된순</option></select>
      </span>
    </div>
    <div id="view"></div>
  </div>
<script>
  var DATA_URL = "__DATA_URL__";
  var cache = [];              // 마지막으로 받은 기록
  var order = "newest";        // 정렬: 최신순 / 오래된순
  var LABELS = {name:"이름", email:"이메일", phone:"전화번호", account_no:"계좌번호", balance:"잔액"};
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function leaked(q){
    if(!q || q.d == null) return "-";
    try {
      var o = JSON.parse(q.d);
      return Object.keys(o).filter(function(k){return o[k]!=null && o[k]!=="";}).map(function(k){
        var v = (k==="balance" && typeof o[k]==="number") ? o[k].toLocaleString()+"원" : o[k];
        return (LABELS[k]||k)+": "+v;
      }).join("  ·  ") || String(q.d);
    } catch(e){ return String(q.d); }
  }
  function render(){
    var view = document.getElementById("view");
    document.getElementById("status").textContent = "수신 " + cache.length + "건 · 2초마다 자동 갱신";
    if(!cache.length){
      view.innerHTML = '<div class="empty">아직 수신된 데이터가 없습니다.<br/>방어 OFF에서 S2 공격이 성공하면 여기에 쌓입니다.</div>';
      return;
    }
    // time은 ISO 문자열이라 문자열 비교로 시간순 정렬이 된다.
    var list = cache.slice().sort(function(a,b){
      var c = String(a.time).localeCompare(String(b.time));
      return order === "newest" ? -c : c;
    });
    var rows = list.map(function(e){
      var t = (e.time||"").slice(11,19);
      return '<tr><td class="time">'+esc(t)+'</td><td class="path">'+esc(e.path||"")+'</td><td class="data">'+esc(leaked(e.query))+'</td></tr>';
    }).join("");
    view.innerHTML = '<table><thead><tr><th>시각(UTC)</th><th>경로</th><th>빼간 데이터</th></tr></thead><tbody>'+rows+'</tbody></table>';
  }
  function tick(){
    fetch(DATA_URL, {credentials:'include'}).then(function(r){
      if(r.status===401){ throw new Error('로그인 필요'); }
      if(!r.ok){ throw new Error('HTTP '+r.status); }
      return r.json();
    }).then(function(data){ cache = data; render(); }).catch(function(err){
      document.getElementById("view").innerHTML =
        '<div class="err">기록을 불러오지 못했습니다: '+esc(err.message)+
        '<br/>(배포 콘솔은 같은 브라우저에서 YanggBank에 로그인한 상태여야 합니다)</div>';
    });
  }
  document.getElementById("order").addEventListener("change", function(){ order = this.value; render(); });
  tick(); setInterval(tick, 2000);
</script>
</body>
</html>
"""


def console_html(data_url: str) -> str:
    """로그 JSON 엔드포인트(data_url)만 끼워 넣은 콘솔 페이지 HTML을 돌려준다."""
    return _CONSOLE_TEMPLATE.replace("__DATA_URL__", data_url)
