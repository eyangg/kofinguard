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
  .wrap { max-width: 820px; margin: 0 auto; }
  h1 { font-size: 18px; margin: 0 0 6px; color: #ff6b6b; }
  .sub { color: #8b98a5; font-size: 13px; margin: 0 0 18px; line-height: 1.6; }
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
</style>
</head>
<body>
  <div class="wrap">
    <h1>&#9888; 공격자 수집 서버 &mdash; 탈취된 고객 데이터</h1>
    <p class="sub">방어 OFF 상태에서 S2(문서 속 숨은 지시) 공격이 성공하면,<br/>
      고객 화면엔 아무 흔적 없이 이곳으로 데이터가 빠져나옵니다. (공격 성공 판정의 물증)</p>
    <div class="bar"><span class="dot"></span><span id="status">수신 대기 중&hellip;</span></div>
    <div id="view"></div>
  </div>
<script>
  var DATA_URL = "__DATA_URL__";
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function leaked(q){
    if(!q || q.d == null) return "-";
    try {
      var o = JSON.parse(q.d);
      return Object.keys(o).filter(function(k){return o[k];}).map(function(k){return k+": "+o[k];}).join("  ·  ") || String(q.d);
    } catch(e){ return String(q.d); }
  }
  function render(list){
    var view = document.getElementById("view");
    document.getElementById("status").textContent = "수신 " + list.length + "건 · 2초마다 자동 갱신";
    if(!list.length){
      view.innerHTML = '<div class="empty">아직 수신된 데이터가 없습니다.<br/>방어 OFF에서 S2 공격이 성공하면 여기에 쌓입니다.</div>';
      return;
    }
    var rows = list.slice().reverse().map(function(e){
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
    }).then(render).catch(function(err){
      document.getElementById("view").innerHTML =
        '<div class="err">기록을 불러오지 못했습니다: '+esc(err.message)+
        '<br/>(배포 콘솔은 같은 브라우저에서 YanggBank에 로그인한 상태여야 합니다)</div>';
    });
  }
  tick(); setInterval(tick, 2000);
</script>
</body>
</html>
"""


def console_html(data_url: str) -> str:
    """로그 JSON 엔드포인트(data_url)만 끼워 넣은 콘솔 페이지 HTML을 돌려준다."""
    return _CONSOLE_TEMPLATE.replace("__DATA_URL__", data_url)
