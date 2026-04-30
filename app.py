from flask import Flask, render_template, request, jsonify, Response
import threading
import time
import queue
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import urllib.parse

app = Flask(__name__)

# ─── GLOBAL STATE ────────────────────────────────────────────────────────────
results_store  = {}   # task_id -> list of result dicts
progress_store = {}   # task_id -> {status, found, message, country, city, category, windows}
task_queues    = {}   # task_id -> Queue
stop_flags     = {}   # task_id -> threading.Event  (set = stop requested)
active_drivers = {}   # task_id -> list of WebDriver instances
CURRENT_TASK   = {"id": None}   # last started task — survives page refresh

# ─── LOCATION DATA ───────────────────────────────────────────────────────────
EUROPE_COUNTRIES = {
    "Albania": ["Tirana", "Durres", "Vlore"],
    "Austria": ["Vienna", "Graz", "Linz", "Salzburg", "Innsbruck"],
    "Belgium": ["Brussels", "Antwerp", "Ghent", "Bruges", "Liege"],
    "Bosnia": ["Sarajevo", "Banja Luka", "Mostar"],
    "Bulgaria": ["Sofia", "Plovdiv", "Varna", "Burgas"],
    "Croatia": ["Zagreb", "Split", "Rijeka", "Osijek", "Dubrovnik"],
    "Czech Republic": ["Prague", "Brno", "Ostrava", "Plzen"],
    "Denmark": ["Copenhagen", "Aarhus", "Odense", "Aalborg"],
    "Estonia": ["Tallinn", "Tartu", "Narva"],
    "Finland": ["Helsinki", "Espoo", "Tampere", "Vantaa", "Oulu"],
    "France": ["Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Strasbourg", "Bordeaux"],
    "Germany": ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart", "Dusseldorf", "Leipzig"],
    "Greece": ["Athens", "Thessaloniki", "Patras", "Heraklion", "Rhodes"],
    "Hungary": ["Budapest", "Debrecen", "Miskolc", "Pecs", "Gyor"],
    "Iceland": ["Reykjavik", "Akureyri"],
    "Ireland": ["Dublin", "Cork", "Limerick", "Galway", "Waterford"],
    "Italy": ["Rome", "Milan", "Naples", "Turin", "Palermo", "Genoa", "Bologna", "Florence", "Venice"],
    "Latvia": ["Riga", "Daugavpils", "Jelgava"],
    "Lithuania": ["Vilnius", "Kaunas", "Klaipeda"],
    "Luxembourg": ["Luxembourg City", "Esch-sur-Alzette"],
    "Malta": ["Valletta", "Birkirkara", "Sliema"],
    "Netherlands": ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven"],
    "Norway": ["Oslo", "Bergen", "Trondheim", "Stavanger"],
    "Poland": ["Warsaw", "Krakow", "Lodz", "Wroclaw", "Poznan", "Gdansk"],
    "Portugal": ["Lisbon", "Porto", "Braga", "Coimbra", "Faro"],
    "Romania": ["Bucharest", "Cluj-Napoca", "Timisoara", "Iasi", "Constanta"],
    "Serbia": ["Belgrade", "Novi Sad", "Nis", "Kragujevac"],
    "Slovakia": ["Bratislava", "Kosice", "Presov", "Zilina"],
    "Slovenia": ["Ljubljana", "Maribor", "Celje"],
    "Spain": ["Madrid", "Barcelona", "Valencia", "Seville", "Zaragoza", "Malaga", "Murcia", "Palma"],
    "Sweden": ["Stockholm", "Gothenburg", "Malmo", "Uppsala", "Vasteras"],
    "Switzerland": ["Zurich", "Geneva", "Basel", "Bern", "Lausanne"],
    "Ukraine": ["Kyiv", "Kharkiv", "Odessa", "Dnipro", "Lviv"],
    "United Kingdom": ["London", "Birmingham", "Manchester", "Glasgow", "Liverpool", "Bristol", "Edinburgh", "Leeds"]
}

BUSINESS_CATEGORIES = [
    "Restaurant", "Hotel", "Cafe", "Bar", "Gym", "Spa", "Salon", "Dentist",
    "Doctor", "Lawyer", "Accountant", "Real Estate", "Car Dealer", "Mechanic",
    "Plumber", "Electrician", "Photographer", "Wedding Planner", "Travel Agency",
    "Clothing Store", "Jewelry Store", "Bakery", "Pharmacy", "Supermarket",
    "Electronics Store", "Furniture Store", "Florist", "Pet Shop", "Yoga Studio",
    "Dance Studio", "Music School", "Language School", "Marketing Agency",
    "IT Company", "Cleaning Service", "Security Company", "Interior Designer",
    "Architecture Firm", "Construction Company", "Moving Company", "Event Planner"
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def extract_emails(text):
    found = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', text)
    bad = ['google','schema','example','sentry','wix','squarespace','wordpress','jquery','png','jpg','svg','gif']
    return list({e for e in found if not any(b in e.lower() for b in bad)})

def extract_phones(text):
    raw = re.findall(r'(\+?[\d][\d\s\-\(\)]{8,18}[\d])', text)
    return list({re.sub(r'[\s\-\(\)]','',p) for p in raw if len(re.sub(r'\D','',p)) >= 9})

def check_whatsapp(phone):
    try:
        clean = re.sub(r'\D','', phone)
        if len(clean) < 9: return False
        r = requests.head(f"https://wa.me/{clean}", timeout=5, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def make_driver():
    opts = Options()
    opts.add_argument("--incognito")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=en-US")
    opts.add_argument("--window-size=1366,768")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})
    svc = Service(ChromeDriverManager().install())
    drv = webdriver.Chrome(service=svc, options=opts)
    drv.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return drv

def get_email_from_website(driver, url, stop_flag):
    try:
        if stop_flag.is_set(): return None
        driver.get(url)
        time.sleep(2)
        emails = extract_emails(driver.page_source)
        if emails: return emails[0]
        # Try contact page
        for link in driver.find_elements(By.TAG_NAME, 'a')[:25]:
            if stop_flag.is_set(): return None
            href = (link.get_attribute('href') or '').lower()
            txt  = link.text.lower()
            if any(w in href+txt for w in ['contact','kontakt','about','impressum','info']):
                try:
                    driver.get(link.get_attribute('href'))
                    time.sleep(1.5)
                    emails = extract_emails(driver.page_source)
                    if emails: return emails[0]
                except: pass
    except: pass
    return None

# ─── CORE SCRAPER ────────────────────────────────────────────────────────────
def get_business_links(driver, query, task_id, stop_flag):
    driver.get(f"https://www.google.com/maps/search/{urllib.parse.quote(query)}")
    time.sleep(4)
    # dismiss cookie popup
    try:
        for btn in driver.find_elements(By.XPATH, '//button'):
            if any(w in btn.text.lower() for w in ['accept','agree','ok','reject all']):
                btn.click(); time.sleep(1); break
    except: pass

    seen = set()
    links = []
    for scroll in range(20):
        if stop_flag.is_set(): break
        try:
            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[role="feed"]')))
        except: break
        for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]'):
            href = a.get_attribute('href') or ''
            if href and href not in seen:
                seen.add(href)
                links.append(href)
        progress_store[task_id]["message"] = f"{len(links)} businesses mile — scroll {scroll+1}/20"
        try:
            panel = driver.find_element(By.CSS_SELECTOR, '[role="feed"]')
            driver.execute_script("arguments[0].scrollTop += 900", panel)
        except:
            driver.execute_script("window.scrollBy(0,900)")
        time.sleep(1.8)
        # end of list check
        try:
            if driver.find_elements(By.XPATH, '//*[contains(text(),"end of results") or contains(text(),"You\'ve reached")]'):
                break
        except: pass
    return links[:60]

def scrape_one(driver, url, idx, task_id, stop_flag):
    result = {
        'id': idx, 'name': 'Unknown', 'email': None,
        'phone': None, 'whatsapp': False, 'website': None,
        'address': None, 'rating': None,
        'total_reviews': None, 'negative_reviews': None
    }
    try:
        if stop_flag.is_set(): return result
        driver.get(url)
        time.sleep(3)

        # NAME
        for sel in ['h1.fontHeadlineLarge','h1[class*="fontHeadline"]','.DUwDvf','h1']:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip(): result['name'] = el.text.strip(); break
            except: pass

        progress_store[task_id]["message"] = f"Processing: {result['name']}"
        src = driver.page_source

        # RATING
        for sel in ['.fontDisplayLarge','span[aria-label*="stars"]','span[class*="fontDisplay"]']:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                t = el.text.strip()
                if t and re.match(r'[\d\.]+', t): result['rating'] = t; break
            except: pass

        # TOTAL REVIEWS — aria-label approach
        try:
            for el in driver.find_elements(By.XPATH, '//*[@aria-label]'):
                lbl = el.get_attribute('aria-label') or ''
                if 'review' in lbl.lower():
                    nums = re.findall(r'[\d,]+', lbl)
                    if nums:
                        result['total_reviews'] = nums[0].replace(',','')
                        break
        except: pass

        # TOTAL REVIEWS — page source fallback
        if not result['total_reviews']:
            m = re.search(r'"(\d[\d,]+)"\s*reviews?', src, re.I)
            if not m: m = re.search(r'\((\d[\d,]+)\)\s*·', src)
            if m: result['total_reviews'] = m.group(1).replace(',','')

        # NEGATIVE REVIEWS — 1-star + 2-star from histogram aria-labels
        try:
            neg = 0
            for el in driver.find_elements(By.XPATH, '//*[@aria-label]'):
                lbl = (el.get_attribute('aria-label') or '').lower()
                if ('1 star' in lbl or '2 star' in lbl or '1-star' in lbl or '2-star' in lbl):
                    nums = re.findall(r'[\d,]+', lbl)
                    if nums: neg += int(nums[0].replace(',',''))
            if neg > 0: result['negative_reviews'] = neg
        except: pass

        # NEGATIVE — page source histogram fallback
        if not result['negative_reviews']:
            try:
                # JSON-like array of 5 numbers = [5star,4star,3star,2star,1star]
                m = re.search(r'\[(\d+),(\d+),(\d+),(\d+),(\d+)\]', src)
                if m:
                    vals = [int(x) for x in m.groups()]
                    if sum(vals) > 0:
                        result['negative_reviews'] = vals[3] + vals[4]  # 2-star + 1-star
            except: pass

        # PHONE
        for pat in [r'tel:([\+\d][\d\s\-\(\)]{7,18})', r'"phoneNumbers":\["([^"]+)"']:
            ms = re.findall(pat, src)
            if ms:
                result['phone'] = ms[0].strip()
                result['whatsapp'] = check_whatsapp(ms[0])
                break
        if not result['phone']:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, '[data-item-id*="phone"]'):
                    phones = extract_phones(el.text or el.get_attribute('aria-label') or '')
                    if phones:
                        result['phone'] = phones[0]
                        result['whatsapp'] = check_whatsapp(phones[0])
                        break
            except: pass

        # ADDRESS
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, '[data-item-id="address"], button[data-item-id*="address"]'):
                if el.text.strip(): result['address'] = el.text.strip(); break
        except: pass
        if not result['address']:
            try:
                for el in driver.find_elements(By.XPATH, '//*[contains(@aria-label,"Address")]'):
                    lbl = el.get_attribute('aria-label') or ''
                    if 'Address:' in lbl: result['address'] = lbl.replace('Address:','').strip(); break
            except: pass

        # WEBSITE
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, 'a[data-item-id*="authority"], a[aria-label*="ebsite"]'):
                href = el.get_attribute('href') or ''
                if href.startswith('http') and 'google' not in href and 'maps' not in href:
                    result['website'] = href; break
        except: pass

        # EMAIL from website
        if result['website'] and not stop_flag.is_set():
            result['email'] = get_email_from_website(driver, result['website'], stop_flag)

        # EMAIL fallback from page source
        if not result['email']:
            emails = extract_emails(src)
            if emails: result['email'] = emails[0]

    except Exception as e:
        pass
    return result

# ─── WORKER THREAD ───────────────────────────────────────────────────────────
def scrape_worker(task_id):
    p   = progress_store[task_id]
    q   = task_queues[task_id]
    sf  = stop_flags[task_id]
    num = p['windows']

    drivers = []
    try:
        p['status'] = 'running'
        p['message'] = 'Chrome windows khul rahi hain...'

        for i in range(num):
            if sf.is_set(): break
            try:
                d = make_driver()
                drivers.append(d)
                p['message'] = f"Window {i+1}/{num} ready..."
            except Exception as e:
                p['message'] = f"Driver error: {e}"

        active_drivers[task_id] = drivers

        if not drivers:
            raise Exception("Koi Chrome window nahi khuli!")

        p['message'] = 'Google Maps pe search ho rahi hai...'
        query = f"{p['category']} in {p['city']} {p['country']}"
        links = get_business_links(drivers[0], query, task_id, sf)

        if not links:
            p['status'] = 'done'
            p['message'] = 'Koi business nahi mila. Alag search try karo.'
            return

        p['total'] = len(links)
        p['message'] = f"{len(links)} businesses mile! Details nikal raha hoon..."

        lock = threading.Lock()
        didx = [0]

        def do_one(url, idx):
            if sf.is_set(): return
            with lock:
                drv = drivers[didx[0] % len(drivers)]
                didx[0] += 1
            res = scrape_one(drv, url, idx, task_id, sf)
            q.put(res)
            with lock:
                p['found'] += 1
                p['message'] = f"({p['found']}/{p['total']}) {res['name']}"

        threads = []
        for i, link in enumerate(links):
            if sf.is_set(): break
            t = threading.Thread(target=do_one, args=(link, i), daemon=True)
            threads.append(t)
            t.start()
            active = [x for x in threads if x.is_alive()]
            while len(active) >= num and not sf.is_set():
                time.sleep(0.8)
                active = [x for x in threads if x.is_alive()]

        for t in threads:
            t.join(timeout=60)

        if sf.is_set():
            p['status'] = 'stopped'
            p['message'] = f"⛔ Stopped — {p['found']} results mile"
        else:
            p['status'] = 'done'
            p['message'] = f"✅ Complete! {p['found']}/{p['total']} businesses scraped!"

    except Exception as e:
        p['status'] = 'error'
        p['message'] = f"Error: {str(e)}"
    finally:
        for drv in drivers:
            try: drv.quit()
            except: pass
        active_drivers.pop(task_id, None)

# ─── ROUTES ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html',
                           countries=EUROPE_COUNTRIES,
                           categories=BUSINESS_CATEGORIES)

@app.route('/get_cities', methods=['POST'])
def get_cities():
    return jsonify(EUROPE_COUNTRIES.get(request.json.get('country',''), []))

@app.route('/current_task')
def current_task():
    tid = CURRENT_TASK['id']
    if not tid:
        return jsonify({'task_id': None})
    p = progress_store.get(tid, {})
    return jsonify({
        'task_id': tid,
        'country': p.get('country',''),
        'city':    p.get('city',''),
        'category':p.get('category',''),
        'windows': p.get('windows', 2),
        'status':  p.get('status',''),
        'found':   p.get('found', 0),
        'total':   p.get('total', 0),
        'message': p.get('message','')
    })

@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    data     = request.json
    country  = data.get('country')
    city     = data.get('city')
    category = data.get('category')
    windows  = int(data.get('num_windows', 2))

    task_id = f"{country}_{city}_{category}_{int(time.time())}"
    CURRENT_TASK['id'] = task_id

    results_store[task_id]  = []
    task_queues[task_id]    = queue.Queue()
    stop_flags[task_id]     = threading.Event()
    progress_store[task_id] = {
        'status': 'starting', 'found': 0, 'total': 0,
        'message': 'Starting...',
        'country': country, 'city': city,
        'category': category, 'windows': windows
    }

    t = threading.Thread(target=scrape_worker, args=(task_id,), daemon=True)
    t.start()
    return jsonify({'task_id': task_id})

@app.route('/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    if task_id in stop_flags:
        stop_flags[task_id].set()
        progress_store[task_id]['status']  = 'stopping'
        progress_store[task_id]['message'] = '⛔ Stop signal bheja — ruk raha hai...'
    return jsonify({'ok': True})

@app.route('/reset_task/<task_id>', methods=['POST'])
def reset_task(task_id):
    # Stop if running
    if task_id in stop_flags:
        stop_flags[task_id].set()
    # Clear stored results
    results_store.pop(task_id, None)
    progress_store.pop(task_id, None)
    task_queues.pop(task_id, None)
    stop_flags.pop(task_id, None)
    CURRENT_TASK['id'] = None
    return jsonify({'ok': True})

@app.route('/get_results/<task_id>')
def get_results(task_id):
    new_results = []
    if task_id in task_queues:
        q = task_queues[task_id]
        while not q.empty():
            try:
                r = q.get_nowait()
                results_store[task_id].append(r)
                new_results.append(r)
            except: break
    return jsonify({
        'results':     results_store.get(task_id, []),
        'progress':    progress_store.get(task_id, {}),
        'new_results': new_results
    })

@app.route('/export_csv/<task_id>')
def export_csv(task_id):
    rows = results_store.get(task_id, [])
    csv  = "Name,Email,Phone,WhatsApp,Website,Address,Rating,Total Reviews,Negative Reviews\n"
    for r in rows:
        csv += ','.join([
            f'"{r.get("name","")}"', f'"{r.get("email","")}"',
            f'"{r.get("phone","")}"', f'"{"Yes" if r.get("whatsapp") else "No"}"',
            f'"{r.get("website","")}"', f'"{r.get("address","")}"',
            f'"{r.get("rating","")}"', f'"{r.get("total_reviews","")}"',
            f'"{r.get("negative_reviews","")}"'
        ]) + "\n"
    return Response(csv, mimetype="text/csv",
                    headers={"Content-disposition": f"attachment; filename=leads_{task_id}.csv"})

if __name__ == '__main__':
    app.run(debug=False, port=8080, threaded=True)
