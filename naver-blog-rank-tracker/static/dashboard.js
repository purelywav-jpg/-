// Draws a small rank-over-time line chart on <canvas class="rank-canvas">
// elements, fetching data from /api/graph. No external chart library
// required. Smaller rank = better, so the y-axis is drawn inverted
// (rank 1 near the top), matching a normal "rank graph" convention.
(function () {
  function drawChart(canvas, points) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const padL = 40, padR = 16, padT = 16, padB = 28;
    ctx.clearRect(0, 0, w, h);

    const ranked = points.filter((p) => p.status === "RANKED" && p.rank !== null);
    if (ranked.length === 0) {
      ctx.fillStyle = "#999";
      ctx.font = "13px sans-serif";
      ctx.fillText("이번 달 측정된 순위 데이터가 없습니다.", padL, h / 2);
      return;
    }

    const ranks = ranked.map((p) => p.rank);
    const minRank = Math.max(1, Math.min(...ranks) - 2);
    const maxRank = Math.max(...ranks) + 2;

    const days = points.map((p) => parseInt(p.date.slice(8, 10), 10));
    const minDay = Math.min(...days);
    const maxDay = Math.max(...days);

    function x(day) {
      if (maxDay === minDay) return padL;
      return padL + ((day - minDay) / (maxDay - minDay)) * (w - padL - padR);
    }
    function y(rank) {
      // inverted: rank 1 (best) near top
      return padT + ((rank - minRank) / (maxRank - minRank)) * (h - padT - padB);
    }

    // axes
    ctx.strokeStyle = "#e4e4e4";
    ctx.beginPath();
    ctx.moveTo(padL, padT);
    ctx.lineTo(padL, h - padB);
    ctx.lineTo(w - padR, h - padB);
    ctx.stroke();

    ctx.fillStyle = "#999";
    ctx.font = "10px sans-serif";
    ctx.fillText(minRank + "위", 4, y(minRank) + 3);
    ctx.fillText(maxRank + "위", 4, y(maxRank) + 3);

    // line through ranked points only (gaps at NOT_FOUND days)
    ctx.strokeStyle = "#1a73e8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    let started = false;
    points.forEach((p) => {
      if (p.status !== "RANKED" || p.rank === null) {
        started = false;
        return;
      }
      const px = x(parseInt(p.date.slice(8, 10), 10));
      const py = y(p.rank);
      if (!started) {
        ctx.moveTo(px, py);
        started = true;
      } else {
        ctx.lineTo(px, py);
      }
    });
    ctx.stroke();

    // dots
    ctx.fillStyle = "#1a73e8";
    points.forEach((p) => {
      if (p.status !== "RANKED" || p.rank === null) return;
      const px = x(parseInt(p.date.slice(8, 10), 10));
      const py = y(p.rank);
      ctx.beginPath();
      ctx.arc(px, py, 3, 0, Math.PI * 2);
      ctx.fill();
    });

    // day labels (every ~5 days)
    ctx.fillStyle = "#999";
    for (let d = minDay; d <= maxDay; d += Math.max(1, Math.round((maxDay - minDay) / 6))) {
      ctx.fillText(d + "일", x(d) - 6, h - 8);
    }
  }

  document.querySelectorAll("canvas.rank-canvas").forEach((canvas) => {
    const postId = canvas.dataset.postId;
    const keywordId = canvas.dataset.keywordId;
    const month = canvas.dataset.month;
    fetch(`/api/graph?post_id=${postId}&keyword_id=${keywordId}&month=${month}`)
      .then((r) => r.json())
      .then((points) => drawChart(canvas, points))
      .catch(() => {});
  });
})();
