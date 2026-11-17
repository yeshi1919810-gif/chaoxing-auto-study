(function(){
  var se = document.scrollingElement || document.documentElement;
  var max = se.scrollHeight - se.clientHeight;
  var cur = se.scrollTop || window.pageYOffset || 0;
  // 也可以尝试内部滚动容器
  if (!max || max <= 0) {
    var cands = Array.from(document.querySelectorAll('div')).filter(function(e){ return e.scrollHeight > e.clientHeight + 100; });
    if (cands.length) {
      var el = cands.sort(function(a,b){ return b.scrollHeight - a.scrollHeight; })[0];
      el.scrollTop = el.scrollTop + Math.floor(el.clientHeight * 0.8);
      el.dispatchEvent(new Event('scroll', {bubbles: true}));
      return JSON.stringify({mode: 'div', cls: (el.className||'').toString().slice(0,30), top: Math.floor(el.scrollTop), sh: el.scrollHeight});
    }
  }
  var step = Math.floor(se.clientHeight * 0.8);
  var next = Math.min(max, cur + step);
  se.scrollTop = next;
  window.scrollTo(0, next);
  window.dispatchEvent(new Event('scroll'));
  document.dispatchEvent(new Event('scroll'));
  return JSON.stringify({mode: 'window', top: Math.floor(next), max: Math.floor(max), done: next >= max - 2});
})()
