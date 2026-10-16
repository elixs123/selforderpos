// Povezuje ekrane sa Python serverom. Ekran samo prikazuje; svu logiku i
// cijene računa Python (server.py / korpa.py).

const km = (feninga) => (feninga / 100).toFixed(2).replace(".", ",") + " KM";

const escapeHtml = (t) =>
  t.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function posalji(url, tijelo) {
  const odgovor = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tijelo ?? {}),
  });
  if (!odgovor.ok) throw new Error(String(odgovor.status));
  return odgovor.json();
}

const GUMB = "width:56px;height:56px;border-radius:28px;border:2px solid #C3CBC0;background:#fff;display:flex;align-items:center;justify-content:center;padding:0;cursor:pointer";

function redStavke(s) {
  return `
  <div style="background:#fff;border-radius:30px;height:100px;flex:none;box-sizing:border-box;padding:0 24px;display:flex;align-items:center;gap:18px">
    <div style="flex:1;min-width:0">
      <div style="font-size:28px;font-weight:700">${escapeHtml(s.naziv)}</div>
      <div style="font-size:22px;color:#55625A;margin-top:2px">${km(s.cijena)} po komadu</div>
    </div>
    <div style="display:flex;align-items:center;gap:10px">
      <button type="button" aria-label="Smanji količinu" data-sifra="${s.sifra}" data-razlika="-1" style="${GUMB}"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#16211A" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14"/></svg></button>
      <span style="width:44px;text-align:center;font-size:30px;font-weight:800">${s.kolicina}</span>
      <button type="button" aria-label="Povećaj količinu" data-sifra="${s.sifra}" data-razlika="1" style="${GUMB}"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#16211A" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button>
    </div>
    <div style="width:120px;text-align:right;font-size:30px;font-weight:800">${(s.iznos / 100).toFixed(2).replace(".", ",")}</div>
  </div>`;
}

function prikazi(korpa) {
  document.querySelectorAll("[data-ukupno]").forEach((e) => (e.textContent = km(korpa.ukupno)));
  document.querySelectorAll("[data-broj]").forEach((e) => (e.textContent = korpa.broj_artikala + " artikala"));
  document.querySelectorAll("[data-broj-num]").forEach((e) => (e.textContent = korpa.broj_artikala));

  const broj = document.getElementById("broj");
  if (broj) broj.textContent = korpa.broj_artikala + " artikala";

  const lista = document.getElementById("stavke");
  if (lista) {
    lista.innerHTML = korpa.stavke.length
      ? korpa.stavke.map(redStavke).join("")
      : `<p style="margin:40px 24px;text-align:center;font-size:28px;line-height:1.4;color:#55625A">Korpa je prazna.<br>Skenirajte artikal da počnete.</p>`;
  }
}

async function osvjezi() {
  try {
    prikazi(await (await fetch("/api/korpa")).json());
  } catch (e) {
    console.error("Server nije dostupan", e);
  }
}

// ----- ekran skeniranja -----
const polje = document.getElementById("barkod");
if (polje) {
  polje.addEventListener("keydown", async (dogadjaj) => {
    if (dogadjaj.key !== "Enter" || !polje.value.trim()) return;
    const barkod = polje.value.trim();
    polje.value = "";
    try {
      const korpa = await posalji("/api/skeniraj", { barkod });
      prikazi(korpa);
      document.getElementById("zadnje-naziv").textContent = korpa.zadnji;
      document.getElementById("zadnje-baner").style.display = "flex";
      polje.style.borderColor = "";
    } catch (e) {
      polje.style.borderColor = "#D5182A";
      polje.placeholder = "Artikal nije pronađen, pokušajte ponovo";
    }
  });
}

const lista = document.getElementById("stavke");
if (lista) {
  lista.addEventListener("click", async (dogadjaj) => {
    const gumb = dogadjaj.target.closest("button[data-sifra]");
    if (!gumb) return;
    prikazi(await posalji(`/api/korpa/${gumb.dataset.sifra}/promjena`, { razlika: Number(gumb.dataset.razlika) }));
  });
}

const ponisti = document.getElementById("ponisti");
if (ponisti) {
  ponisti.addEventListener("click", async () => prikazi(await posalji("/api/korpa/isprazni")));
}

// ----- ekran računa: "Gotovo" prazni korpu prije povratka na početak -----
if (location.pathname.endsWith("Racun.html")) {
  const gotovo = document.querySelector('a[href="index.html"]');
  gotovo?.addEventListener("click", async (dogadjaj) => {
    dogadjaj.preventDefault();
    await posalji("/api/korpa/isprazni");
    location.href = "index.html";
  });
}

osvjezi();
