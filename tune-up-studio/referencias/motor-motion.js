    /* motor de motion do estudio (referencias/motion-js.md): cada quadro e uma funcao pura do tempo; o HyperFrames busca o tempo por window.__hfAnime */
    var M = (function () {
      var NUM = /-?\d*\.?\d+/g;
      var faixas = [];
      function bezier(x1, y1, x2, y2) {
        function c(a, b, s) { return 3 * a * s * (1 - s) * (1 - s) + 3 * b * s * s * (1 - s) + s * s * s; }
        return function (x) {
          var lo = 0, hi = 1, s = x, j;
          for (j = 0; j < 32; j++) { s = (lo + hi) / 2; if (c(x1, x2, s) < x) { lo = s; } else { hi = s; } }
          return c(y1, y2, s);
        };
      }
      var CURVA = { sai: bezier(.16, 1, .3, 1), mola: bezier(.34, 1.56, .64, 1), meio: bezier(.65, 0, .35, 1), entra: bezier(.7, 0, .84, 0), reta: function (x) { return x; } };
      function pega(id) { return document.getElementById(id); }
      function ini(id) { return Number(pega(id).getAttribute("data-start")); }
      function dur(id) { return Number(pega(id).getAttribute("data-duration")); }
      function mistura(a, b, k) {
        if (a.replace(NUM, "#") !== b.replace(NUM, "#")) { return k < 1 ? a : b; }
        var nb = b.match(NUM) || [], i = 0;
        return a.replace(NUM, function (n) { var v = Number(n) + (Number(nb[i]) - Number(n)) * k; i += 1; return String(Math.round(v * 1000) / 1000); });
      }
      function conta(b, k) {
        var ds = b.replace(/\D/g, ""), dec = (b.match(/[.,](\d+)\D*$/) || ["", ""])[1].length;
        var n = String(Math.round(Number(ds) * k)), out = "", j, i, c;
        while (n.length <= dec) { n = "0" + n; }
        j = n.length - 1;
        for (i = b.length - 1; i >= 0; i--) {
          c = b.charAt(i);
          if (c >= "0" && c <= "9") { out = (j >= 0 ? n.charAt(j) : "") + out; j -= 1; }
          else if (j >= 0 || (c !== "." && c !== ",")) { out = c + out; }
        }
        return out;
      }
      function valor(q, t, texto) {
        var i, k;
        if (t <= q[0][0]) { return texto ? conta(q[q.length - 1][1], 0) : q[0][1]; }
        for (i = 0; i < q.length - 1; i++) {
          if (t < q[i + 1][0]) {
            k = (CURVA[q[i][2]] || CURVA.sai)((t - q[i][0]) / (q[i + 1][0] - q[i][0]));
            return texto ? conta(q[q.length - 1][1], k) : mistura(q[i][1], q[i + 1][1], k);
          }
        }
        return q[q.length - 1][1];
      }
      function aplica(ms) {
        var t = ms / 1000, saida = [], i, j, achou;
        for (i = 0; i < faixas.length; i++) {
          var f = faixas[i], v = valor(f.q, t, f.prop === "texto");
          achou = false;
          for (j = 0; j < saida.length; j++) {
            if (saida[j].el === f.el && saida[j].prop === f.prop) { saida[j].v = f.prop === "transform" ? saida[j].v + " " + v : v; achou = true; }
          }
          if (!achou) { saida.push({ el: f.el, prop: f.prop, v: v }); }
        }
        for (j = 0; j < saida.length; j++) {
          if (saida[j].prop === "texto") { saida[j].el.textContent = saida[j].v; } else { saida[j].el.style[saida[j].prop] = saida[j].v; }
        }
      }
      function faixa(el, prop, q) { faixas.push({ el: typeof el === "string" ? pega(el) : el, prop: prop, q: q }); }
      function de_ate(el, prop, a, b, t0, t, curva) { faixa(el, prop, [[t0, a, curva || "sai"], [t0 + t, b]]); }
      var ENTRADA = {
        sobe: [["transform", "translateY(90px)", "translateY(0px)"], ["opacity", "0", "1"]],
        esquerda: [["transform", "translateX(-260px)", "translateX(0px)"], ["opacity", "0", "1"]],
        carimbo: [["transform", "scale(1.9) rotate(-9deg)", "scale(1) rotate(-2deg)"], ["opacity", "0", "1"]],
        barra: [["transform", "scaleX(0)", "scaleX(1)"]],
        painel: [["transform", "translateY(101%)", "translateY(0%)"]],
        gira: [["transform", "rotate(-90deg) scale(.4)", "rotate(0deg) scale(1)"], ["opacity", "0", "1"]]
      };
      var FENDA = { baixo: "inset(100% 0% 0% 0%)", cima: "inset(0% 0% 100% 0%)", esquerda: "inset(0% 100% 0% 0%)", direita: "inset(0% 0% 0% 100%)" };
      window.__hfAnime = (window.__hfAnime || []).concat([{ seek: aplica, pause: function () {}, play: function () {} }]);
      return {
        trilha: function (id, prop, q) { faixa(id, prop, q); },
        entra: function (id, atraso, t, tipo) {
          if (tipo === "barra") { pega(id).style.transformOrigin = "left center"; }
          ENTRADA[tipo].forEach(function (p) { de_ate(id, p[0], p[1], p[2], ini(id) + atraso, t, tipo === "carimbo" || tipo === "gira" ? "mola" : "sai"); });
        },
        palavras: function (id, atraso, passo, modo, t) {
          var el = pega(id), ws = el.textContent.split(" "), i, td = t || .6;
          el.textContent = "";
          for (i = 0; i < ws.length; i++) {
            var caixa = document.createElement("span"), w = document.createElement("span"), t0 = ini(id) + atraso + i * passo;
            caixa.className = "m-caixa";
            w.className = "m-palavra";
            w.textContent = ws[i];
            caixa.appendChild(w);
            el.appendChild(caixa);
            if (i < ws.length - 1) { el.appendChild(document.createTextNode(" ")); }
            if (modo === "onda") { faixa(w, "transform", [[t0, "translateY(0em)", "meio"], [t0 + .2, "translateY(-.14em)", "meio"], [t0 + .6, "translateY(0em)"]]); }
            else { de_ate(w, "transform", "translateY(.4em)", "translateY(0em)", t0, td, "sai"); de_ate(w, "opacity", "0", "1", t0, td * .6, "reta"); }
          }
        },
        contador: function (id, atraso, t) { faixa(id, "texto", [[ini(id) + atraso, "", "sai"], [ini(id) + atraso + t, pega(id).textContent]]); },
        mascara: function (id, atraso, t, lado) {
          if (lado === "centro") { de_ate(id, "clipPath", "circle(0% at 50% 50%)", "circle(75% at 50% 50%)", ini(id) + atraso, t, "sai"); }
          else { de_ate(id, "clipPath", FENDA[lado], "inset(0% 0% 0% 0%)", ini(id) + atraso, t, "sai"); }
        },
        camera: function (ids, de, ate, cx, cy) {
          ids.forEach(function (id) {
            var el = pega(id), cs = getComputedStyle(el);
            el.style.transformOrigin = (cx - parseFloat(cs.left)) + "px " + (cy - parseFloat(cs.top)) + "px";
            de_ate(id, "transform", "scale(" + de + ")", "scale(" + ate + ")", ini(id), dur(id), "reta");
          });
        },
        parallax: function (camadas) {
          camadas.forEach(function (c) { de_ate(c[0], "transform", "translate(0px, 0px)", "translate(" + c[1] + "px, " + c[2] + "px)", ini(c[0]), dur(c[0]), "reta"); });
        },
        pulso: function (id, atraso, periodo, escala) {
          var t0 = ini(id) + atraso, q = [], n = Math.max(1, Math.floor((dur(id) - atraso) / periodo)), i;
          for (i = 0; i < n; i++) { q.push([t0 + i * periodo, "scale(1)", "meio"], [t0 + i * periodo + periodo * .3, "scale(" + escala + ")", "meio"]); }
          q.push([t0 + n * periodo, "scale(1)"]);
          faixa(id, "transform", q);
        },
        onda: function (ids, t0, passo, escala) {
          ids.forEach(function (id, i) { faixa(id, "transform", [[t0 + i * passo, "scale(1)", "meio"], [t0 + i * passo + .2, "scale(" + escala + ")", "meio"], [t0 + i * passo + .5, "scale(1)"]]); });
        },
        vaivem: function (id, t0, t1, a, b, periodo) {
          var q = [], t = t0;
          while (t < t1 - 1e-6) { q.push([t, a, "meio"], [Math.min(t + periodo / 2, t1), b, "meio"]); t += periodo; }
          q.push([t1, a]);
          faixa(id, "transform", q);
        },
        traco: function (id, t0, t) { de_ate(id, "strokeDashoffset", "1", "0", t0, t, "meio"); },
        pronto: function () { aplica(0); }
      };
    })();
