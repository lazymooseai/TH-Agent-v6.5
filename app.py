import streamlit as st
import datetime
import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import re
import time as time_module

st.set_page_config(page_title="🚕 TH Taktinen Tutka", page_icon="🚕", layout="wide")

# ==========================================
# 1. KIRJAUTUMINEN
# ==========================================
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "2026")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align: center; color: #5bc0de;'>🚕 TH Taktinen Tutka </h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaa;'>Kirjaudu sisään nähdäksesi datan.</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Salasana", type="password")
        if st.button("Kirjaudu", use_container_width=True):
            if pwd == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Väärä salasana.")
    st.stop()

# ==========================================
# 2. API-AVAIMET JA TYYLIT
# ==========================================
FINAVIA_API_KEY = st.secrets.get("FINAVIA_API_KEY", "c24ac18c01e44b6e9497a2a30341")

if "valittu_asema" not in st.session_state:
    st.session_state.valittu_asema = "Helsinki"
if "paiva_offset" not in st.session_state:
    st.session_state.paiva_offset = 0

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    main { background-color: #121212; }
    .header-container {
        display: flex; justify-content: space-between; align-items: flex-start;
        border-bottom: 1px solid #333; padding-bottom: 15px; margin-bottom: 20px;
    }
    .app-title { font-size: 32px; font-weight: bold; color: #ffffff; margin-bottom: 5px; }
    .time-display { font-size: 42px; font-weight: bold; color: #e0e0e0; line-height: 1.1; }
    .taksi-card {
        background-color: #1e1e2a; color: #e0e0e0; padding: 22px;
        border-radius: 12px; margin-bottom: 20px; font-size: 20px;
        border: 1px solid #3a3a50; box-shadow: 0 4px 8px rgba(0,0,0,0.3); line-height: 1.4;
    }
    .card-title {
        font-size: 24px; font-weight: bold; margin-bottom: 12px;
        color: #ffffff; border-bottom: 2px solid #444; padding-bottom: 8px;
    }
    .taksi-link {
        color: #5bc0de; text-decoration: none; font-size: 18px;
        display: inline-block; margin-top: 12px; font-weight: bold;
    }
    .badge-red { background: #7a1a1a; color: #ff9999; padding: 2px 8px; border-radius: 4px; }
    .badge-yellow { background: #5a4a00; color: #ffeb3b; padding: 2px 8px; border-radius: 4px; }
    .badge-green { background: #1a4a1a; color: #88d888; padding: 2px 8px; border-radius: 4px; }
    .badge-blue { background: #1a2a5a; color: #8ab4f8; padding: 2px 8px; border-radius: 4px; }
    .pax-good { color: #ffeb3b; font-weight: bold; }
    .pax-ok { color: #a3c2a3; }
    .section-header {
        color: #e0e0e0; font-size: 24px; font-weight: bold;
        margin-top: 28px; margin-bottom: 10px;
        border-left: 4px solid #5bc0de; padding-left: 12px;
    }
    .venue-name { color: #ffffff; font-weight: bold; }
    .venue-address { color: #aaaaaa; font-size: 16px; }
    .endtime { color: #ffeb3b; font-size: 15px; font-weight: bold; }
    .eventline { border-left: 3px solid #333; padding-left: 12px; margin-bottom: 16px; }
    .live-event { color: #88d888; font-weight: bold; }
    .no-event { color: #888888; font-style: italic; }
    .event-list-item { font-size: 17px; color: #d0d0d0; margin-bottom: 4px; line-height: 1.3;}
    .tomorrow-banner {
        background: #2a2a0a; border: 1px solid #666600;
        border-radius: 8px; padding: 8px 16px; margin-bottom: 16px; color: #ffeb3b;
        font-size: 16px; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. HEURISTIIKKAMOOTTORI
# ==========================================
def laske_kysyntakerroin(wb_status, klo_str):
    indeksi = 2.0
    if wb_status:
        indeksi += 5.0
    try:
        tunnit = int(klo_str.split(":")[0])
        if tunnit >= 22 or tunnit <= 4:
            indeksi += 2.5
        elif 15 <= tunnit <= 18:
            indeksi += 1.5
    except:
        pass
    indeksi = min(indeksi, 10.0)
    if indeksi >= 7:
        return f"<span style='color:#ff4b4b; font-weight:bold;'>Kysyntä: {indeksi}/10</span>"
    elif indeksi >= 4:
        return f"<span style='color:#ffeb3b;'>Kysyntä: {indeksi}/10</span>"
    else:
        return f"<span style='color:#a3c2a3;'>Kysyntä: {indeksi}/10</span>"

# ==========================================
# 4. HAKUFUNKTIOT: JUNAT
# ==========================================
@st.cache_data(ttl=86400)
def hae_juna_asemat():
    asemat = {
        "HKI": "Helsinki", "PSL": "Pasila", "TKL": "Tikkurila", "KRS": "Kerava",
        "TPE": "Tampere", "TKU": "Turku", "OUL": "Oulu", "ROV": "Rovaniemi",
        "KJA": "Kajaani", "KUO": "Kuopio", "JNS": "Joensuu", "ILO": "Iisalmi"
    }
    try:
        resp = requests.get("https://rata.digitraffic.fi/api/v1/metadata/stations", timeout=10)
        if resp.status_code == 200:
            for s in resp.json():
                asemat[s["stationShortCode"]] = s["stationName"].replace(" asema", "")
    except:
        pass
    return asemat

@st.cache_data(ttl=50)
def get_trains(asema_nimi):
    nykyhetki = datetime.datetime.now(ZoneInfo("Europe/Helsinki"))
    koodi = {"Helsinki": "HKI", "Pasila": "PSL", "Tikkurila": "TKL"}.get(asema_nimi, "HKI")
    asemat_dict = hae_juna_asemat()
    tulos = []

    try:
        resp = requests.get(
            f"https://rata.digitraffic.fi/api/v1/live-trains/station/{koodi}"
            f"?arriving_trains=40&include_nonstopping=false&train_categories=Long-distance",
            timeout=15
        )
        resp.raise_for_status()
        junat = resp.json()

        for juna in junat:
            if juna.get("cancelled") or juna.get("trainCategory") != "Long-distance":
                continue

            nimi = f"{juna.get('trainType', '')}{juna.get('trainNumber', '')}"
            lahto_koodi = next((r["stationShortCode"] for r in juna.get("timeTableRows", []) if r["type"] == "DEPARTURE"), None)

            if not lahto_koodi or lahto_koodi in ["HKI", "PSL", "TKL"]:
                continue

            aika_obj_hki = None
            aika_str = None
            viive = 0

            for rivi in juna.get("timeTableRows", []):
                if rivi["stationShortCode"] != koodi or rivi["type"] != "ARRIVAL":
                    continue

                raaka = rivi.get("liveEstimateTime") or rivi.get("scheduledTime", "")
                if not raaka:
                    continue

                try:
                    raaka_clean = raaka[:19]
                    if "T" in raaka_clean:
                        aika_utc = datetime.datetime.strptime(raaka_clean, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                        aika_obj_hki = aika_utc.astimezone(ZoneInfo("Europe/Helsinki"))

                        if aika_obj_hki < nykyhetki - datetime.timedelta(minutes=3):
                            continue

                        aika_str = aika_obj_hki.strftime("%H:%M")
                        viive = rivi.get("differenceInMinutes", 0) or 0
                        break
                except:
                    continue

            if aika_str and aika_obj_hki:
                tulos.append({
                    "train": nimi,
                    "origin": asemat_dict.get(lahto_koodi, lahto_koodi),
                    "time": aika_str,
                    "delay": viive,
                    "dt": aika_obj_hki
                })

        tulos.sort(key=lambda k: k["dt"])
        return tulos[:12]

    except Exception:
        return [{"train": "API-virhe", "origin": "Ei yhteyttä VR-rajapintaan.", "time": "", "delay": 0, "dt": nykyhetki}]

# ==========================================
# HAKUFUNKTIOT: LAIVAT
# ==========================================
def tunnista_terminaali(teksti, laiva_nimi="", aika=""):
    teksti = teksti.lower()
    laiva_nimi = laiva_nimi.lower()
    
    if aika == "00:30" or "finlandia" in laiva_nimi:
        return "Länsiterminaali T2"
        
    if "t2" in teksti or "lansisatama" in teksti or "länsisatama" in teksti:
        return "Länsiterminaali T2"
    if "t1" in teksti or "olympia" in teksti:
        return "Olympia T1"
    if "katajanokka" in teksti:
        return "Katajanokka"
    return "Tarkista Terminaali"

def pax_arvio(pax):
    if pax is None:
        return "Ei tietoa", "pax-ok"
    autoa = round(pax * 0.025)
    if pax >= 1500:
        return f"({pax} matkustajaa, ~{autoa} autoa, HYVÄ)", "pax-good"
    if pax >= 800:
        return f"({pax} matkustajaa, ~{autoa} autoa, NORMAALI)", "pax-ok"
    return f"({pax} matkustajaa, ~{autoa} autoa, HILJAINEN)", "pax-ok"

@st.cache_data(ttl=600)
def get_averio_ships():
    laivat = []
    try:
        resp = requests.get("https://averio.fi/laivat", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for taulu in soup.find_all("table"):
            for rivi in taulu.find_all("tr"):
                solut = [td.get_text(strip=True) for td in rivi.find_all(["td", "th"])]
                if len(solut) < 3:
                    continue
                rivi_teksti = " ".join(solut).lower()
                if any(h in rivi_teksti for h in ["alus", "laiva", "ship", "vessel"]):
                    continue
                
                pax = None
                for solu in solut:
                    puhdas = re.sub(r"[^\d]", "", solu)
                    if puhdas and 50 < int(puhdas) <= 9999:
                        pax = int(puhdas)
                        break
                        
                nimi_kandidaatit = [s for s in solut if re.search(r"[A-Za-zÄÖÅäöå]{3,}", s)]
                if not nimi_kandidaatit:
                    continue
                    
                nimi = max(nimi_kandidaatit, key=len)
                
                aika_str = ""
                for osa in solut:
                    m = re.search(r" ([0-2]?\d:[0-5]\d) ", str(osa))
                    if m:
                        aika_str = m.group(1)
                        break
                        
                laivat.append({
                    "ship": nimi,
                    "terminal": tunnista_terminaali(rivi_teksti, nimi, aika_str),
                    "time": aika_str,
                    "pax": pax
                })
        return laivat[:5] if laivat else [{"ship": "Ei saapuvia aluksia juuri nyt", "terminal": "", "time": "", "pax": None}]
    except Exception:
        return [{"ship": "Ei yhteyttä Averioon.", "terminal": "", "time": "", "pax": None}]

# ==========================================
# HAKUFUNKTIOT: LENNOT
# ==========================================
@st.cache_data(ttl=60)
def get_flights():
    laajarunko = ("359", "350", "333", "330", "340", "788", "789", "777", "77W", "380", "388", "748", "74H", "752", "753", "763", "764", "767", "772", "773", "77F", "32Q", "321", "322", "32A", "32B", "32N", "32S")

    for url, extra_headers in [
        (f"https://apigw.finavia.fi/flights/public/v0/flights/arr/HEL?subscription-key={FINAVIA_API_KEY}", {}),
        ("https://apigw.finavia.fi/flights/public/v0/flights/arr/HEL", {"Ocp-Apim-Subscription-Key": FINAVIA_API_KEY})
    ]:
        hdrs = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        hdrs.update(extra_headers)
        try:
            resp = requests.get(url, headers=hdrs, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                saapuvat = data if isinstance(data, list) else data.get("data", [])
                
                if saapuvat:
                    tulos = []
                    for lento in saapuvat:
                        actype = str(lento.get("actype") or lento.get("aircraftType", "")).upper()
                        status = str(lento.get("prt_f") or lento.get("flightStatusInfo", "")).upper()
                        aika_r = str(lento.get("sdt") or lento.get("scheduledTime", ""))
                        wb = any(c in actype for c in laajarunko)
                        
                        if not wb and "DELAY" not in status:
                            continue
                            
                        tulos.append({
                            "flight": lento.get("fltnr") or lento.get("flightNumber", "??"),
                            "origin": lento.get("route_n_1") or lento.get("airport", "Tuntematon"),
                            "time": aika_r[11:16] if "T" in aika_r else aika_r[:5],
                            "type": f"Laajarunko ({actype})" if wb else f"Kapearunko ({actype})",
                            "wb": wb,
                            "status": status or "Odottaa"
                        })
                    if tulos:
                        tulos.sort(key=lambda x: (not x["wb"], x["time"]))
                        return tulos[:8], None
        except:
            continue

    return [], "Datan haku epäonnistui. <a href='https://www.finavia.fi/fi/lentoasemat/helsinki-vantaa/lennot/saapuvat' target='_blank' style='color:#5bc0de;'>Avaa Finavian Live-taulu →</a>"

# ==========================================
# HAKUFUNKTIOT: TAPAHTUMAT
# ==========================================
def parse_hel_api_time(time_str):
    if not time_str:
        return None
    try:
        dt = datetime.datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        hki_dt = dt.astimezone(ZoneInfo("Europe/Helsinki"))
        return hki_dt.strftime("%H:%M")
    except:
        return None

@st.cache_data(ttl=86400)
def hae_paikka_id(hakusana: str) -> str:
    url = "https://api.hel.fi/linkedevents/v1/place/"
    try:
        r = requests.get(url, params={"text": hakusana, "format": "json"}, timeout=10)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return data[0]["id"]
    except:
        pass
    return ""

@st.cache_data(ttl=3600)
def hae_tapahtumat_api(paikka_id: str, pvm_iso: str) -> list:
    if not paikka_id:
        return []
    url = "https://api.hel.fi/linkedevents/v1/event/"
    params = {
        "location": paikka_id,
        "start": pvm_iso,
        "end": pvm_iso,
        "language": "fi",
        "sort": "start_time",
        "page_size": 20,
        "format": "json"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get("data", [])
            tulos = []
            for t in data:
                nimi = (t.get("name", {}) or {}).get("fi", "Esitys")
                
                alku_klo = parse_hel_api_time(t.get("start_time"))
                loppu_klo = parse_hel_api_time(t.get("end_time"))
                
                if alku_klo and loppu_klo:
                    aika_str = f"{alku_klo} - {loppu_klo}"
                elif alku_klo:
                    aika_str = f"{alku_klo} (alkaa)"
                else:
                    aika_str = "Aika ei tiedossa"
                
                tulos.append(f"<div class='event-list-item'>► <b>Klo {aika_str}</b>: {nimi}</div>")
            return tulos
    except:
        pass
    return []

def yhdista_kulttuuridata(paikat, pvm_iso: str):
    for p in paikat:
        hakusanat = p.get("hakusanat", [])
        tapahtumat = []
        
        if hakusanat:
            paikka_id = hae_paikka_id(hakusanat[0])
            if paikka_id:
                tapahtumat = hae_tapahtumat_api(paikka_id, pvm_iso)
        
        if tapahtumat:
            rivit = "".join(tapahtumat)
            p["lopetus_html"] = f"<div style='margin-top:10px;'><span class='live-event'>ESITYKSET TÄNÄÄN:</span><br>{rivit}</div>"
        else:
            p["lopetus_html"] = (
                f"<span class='no-event'>Ei havaittuja esityksiä kaupungin API:ssa.</span>"
                f"<br><span style='color:#777;'>Tyypillisesti: {p.get('huomio','')}</span>"
            )
    return paikat

@st.cache_data(ttl=3600)
def hae_liiga_pvm(pvm_iso: str):
    try:
        dt = datetime.datetime.strptime(pvm_iso, "%Y-%m-%d")
        kausi_alku = dt.year if dt.month > 6 else dt.year - 1
        kausi_str = f"{kausi_alku}-{kausi_alku + 1}"
        hdrs = {"User-Agent": "Mozilla/5.0"}
        url = f"https://liiga.fi/api/v2/games?tournament=runkosarja&season={kausi_str}"
        r = requests.get(url, headers=hdrs, timeout=8)
        if r.status_code == 200:
            pelit_lista = r.json()
            pelit = []
            for peli in pelit_lista:
                start = peli.get("start", "")
                if not start.startswith(pvm_iso):
                    continue
                koti = (peli.get("homeTeam") or {}).get("teamName", "")
                vieras = (peli.get("awayTeam") or {}).get("teamName", "")
                aika = start[11:16] if len(start) > 10 else ""
                pelit.append({"koti": koti, "vieras": vieras, "aika": aika})
            return pelit
    except:
        pass
    return []

def yhdista_urheiludata(paikat, pvm_iso: str):
    liiga_pelit = hae_liiga_pvm(pvm_iso)

    def etsi_kotipeli(hakusana):
        # Tallennetaan f-string variables ensin turvallisesti
        tulos = []
        for p in liiga_pelit:
            if hakusana.lower() in p["koti"].lower():
                klo = p['aika']
                koti = p['koti']
                vieras = p['vieras']
                tulos.append(f"<div class='event-list-item'>► <b>Klo {klo} (alkaa)</b>: {koti} - {vieras}</div>")
        return tulos

    for p in paikat:
        nimi = p.get("nimi", "").lower()
        tapahtumat = []
        
        if "hifk" in nimi:
            tapahtumat = etsi_kotipeli("hifk") or etsi_kotipeli("ifk")
        elif "kiekko-espoo" in nimi or "k-espoo" in nimi:
            tapahtumat = etsi_kotipeli("k-espoo") or etsi_kotipeli("kiekko")
        elif "jokerit" in nimi:
            p["lopetus_html"] = "<span class='no-event'>Mestis ei tuettu suorassa haussa. <a href='https://jokerit.fi/ottelut' target='_blank' style='color:#5bc0de;'>Tarkista Jokereiden sivuilta →</a></span>"
            continue

        if tapahtumat:
            rivit = "".join(tapahtumat)
            p["lopetus_html"] = (
                f"<div style='margin-top:10px;'><span class='live-event'>PELI TÄNÄÄN:</span><br>{rivit}"
                f"<span style='color:#ccc;font-size:15px;display:block;margin-top:4px;'>ℹ️ Kesto n. 2,5h aloitusajasta</span></div>"
            )
        else:
            p["lopetus_html"] = "<span class='no-event'>Ei havaittua kotiottelua.</span>"
    return paikat

def venue_card(p):
    lopetus_naytto = p.get("lopetus_html", f"<span class='endtime'>Tyypillinen rytmi: {p.get('huomio','')}</span>")
    badge_color = p.get("badge", "badge-blue")
    nimi = p.get('nimi','')
    kap = p.get('kap','')
    
    html = (
        f"<div class='eventline'>"
        f"<span class='{badge_color}'></span> "
        f"<span class='venue-name'>{nimi}</span><br>"
        f"<span class='venue-address'>Max pax: <b>{kap}</b></span><br>"
        f"{lopetus_naytto}<br>"
    )
    if "linkki" in p:
        linkki_url = p['linkki']
        html += f"<a href='{linkki_url}' class='taksi-link' target='_blank' style='font-size:14px;'>Sivut</a>"
    return html + "</div>"

def venue_html(paikat):
    return "".join(venue_card(p) for p in paikat)

# ==========================================
# 5. DASHBOARD
# ==========================================
@st.fragment(run_every=300)
def render_dashboard():
    suomen_aika = datetime.datetime.now(ZoneInfo("Europe/Helsinki"))
    klo = suomen_aika.strftime("%H:%M")
    paiva = suomen_aika.strftime("%A %d.%m.%Y").capitalize()
    HSL_LINKKI = "https://www.hsl.fi/matkustaminen/liikenne?language=fi"

    st.markdown(f"""
    <div class='header-container'>
        <div>
            <div class='app-title'>🚕 TH Taktinen Tutka</div>
            <div class='time-display'>{klo} <span style='font-size:16px;color:#888;'>{paiva}</span></div>
        </div>
        <div style='text-align:right;'>
            <a href='https://www.ilmatieteenlaitos.fi/sade-ja-pilvialueet?area=etela-suomi' class='taksi-link' target='_blank'>Säätutka</a> | 
            <a href='https://liikennetilanne.fintraffic.fi/' class='taksi-link' target='_blank'>Liikenne</a> | 
            <a href='{HSL_LINKKI}' class='taksi-link' target='_blank'>HSL</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Pakota päivitys (Tyhjennä muisti)", type="secondary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # --- LOHKO 1: JUNAT ---
    st.markdown("<div class='section-header'>🚆 SAAPUVAT KAUKOJUNAT</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    
    if c1.button("Helsinki (HKI)", use_container_width=True):
        st.session_state.valittu_asema = "Helsinki"
    if c2.button("Pasila (PSL)", use_container_width=True):
        st.session_state.valittu_asema = "Pasila"
    if c3.button("Tikkurila (TKL)", use_container_width=True):
        st.session_state.valittu_asema = "Tikkurila"

    valittu = st.session_state.valittu_asema
    junat = get_trains(valittu)
    vr_linkit = {
        "Helsinki": "https://www.vr.fi/radalla?station=HKI",
        "Pasila": "https://www.vr.fi/radalla?station=PSL",
        "Tikkurila": "https://www.vr.fi/radalla?station=TKL"
    }

    juna_html = f"<span style='color:#aaa; font-size:17px;'>Asema: <b>{valittu}</b></span><br><br>"

    if junat and junat[0].get("train") != "API-virhe":
        for j in junat:
            pohjoinen = j["origin"] in ["Rovaniemi", "Kolari", "Kemi", "Oulu", "Kajaani", "Iisalmi", "Ylivieska"]
            merkki = "❄️" if pohjoinen else ""
            
            # Turvalliset muuttujat ennen f-stringiä
            j_time = j['time']
            j_train = j['train']
            j_origin = j['origin']
            j_delay = j['delay']
            
            delay_str = f"<span class='badge-red'>+{j_delay} min</span>" if j_delay > 0 else "<span class='badge-green'>Aikataulussa</span>"
            juna_html += (
                f"<b>{j_time}</b> {j_train} "
                f"<span style='color:#aaa;'>(lähtö: {j_origin} {merkki})</span> "
                f"{delay_str}<br><br>"
            )
    else:
        virhe_origin = junat[0].get('
