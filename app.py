import os, re, csv, io, html, sqlite3, zipfile, webbrowser, threading, shutil, base64
from datetime import datetime, date, timedelta
from collections import Counter
from urllib.parse import parse_qs, urlparse, quote, urlencode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import xml.etree.ElementTree as ET

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SERVERLESS = os.environ.get("VERCEL") or os.environ.get("NETLIFY") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
DATA_DIR = "/data" if os.environ.get("RENDER") else ("/tmp" if SERVERLESS else BASE_DIR)

DB_PATH = os.path.join(DATA_DIR, "export_import_crm.sqlite")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
REPORT_DIR = os.path.join(DATA_DIR, "reports")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
for d in (UPLOAD_DIR, EXPORT_DIR, REPORT_DIR, BACKUP_DIR):
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass

HOST = "0.0.0.0"
# Use a different port so an older Titan version still running on 5000 cannot hide this update.
PORT = int(os.environ.get("PORT", os.environ.get("CRM_PORT", "5050")))
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

COUNTRIES = {
    "india":"India","bharat":"India",".in":"India",
    "uae":"United Arab Emirates","dubai":"United Arab Emirates","abu dhabi":"United Arab Emirates","united arab emirates":"United Arab Emirates",".ae":"United Arab Emirates",
    "saudi":"Saudi Arabia","ksa":"Saudi Arabia","riyadh":"Saudi Arabia","jeddah":"Saudi Arabia",".sa":"Saudi Arabia",
    "qatar":"Qatar","doha":"Qatar",".qa":"Qatar","kuwait":"Kuwait",".kw":"Kuwait","oman":"Oman","muscat":"Oman",".om":"Oman","bahrain":"Bahrain",".bh":"Bahrain",
    "usa":"United States","america":"United States","united states":"United States",".us":"United States","canada":"Canada",".ca":"Canada",
    "uk":"United Kingdom","united kingdom":"United Kingdom","england":"United Kingdom",".uk":"United Kingdom",
    "germany":"Germany",".de":"Germany","france":"France",".fr":"France","italy":"Italy",".it":"Italy","spain":"Spain",".es":"Spain","netherlands":"Netherlands","holland":"Netherlands",".nl":"Netherlands","belgium":"Belgium",".be":"Belgium",
    "australia":"Australia",".au":"Australia","new zealand":"New Zealand",".nz":"New Zealand",
    "singapore":"Singapore",".sg":"Singapore","malaysia":"Malaysia",".my":"Malaysia","thailand":"Thailand",".th":"Thailand","indonesia":"Indonesia",".id":"Indonesia","vietnam":"Vietnam","viet nam":"Vietnam",".vn":"Vietnam","philippines":"Philippines",".ph":"Philippines",
    "bangladesh":"Bangladesh",".bd":"Bangladesh","sri lanka":"Sri Lanka",".lk":"Sri Lanka","nepal":"Nepal",".np":"Nepal","pakistan":"Pakistan",".pk":"Pakistan",
    "china":"China",".cn":"China","hong kong":"Hong Kong",".hk":"Hong Kong","japan":"Japan",".jp":"Japan","south korea":"South Korea","korea":"South Korea",".kr":"South Korea",
    "south africa":"South Africa",".za":"South Africa","kenya":"Kenya",".ke":"Kenya","nigeria":"Nigeria",".ng":"Nigeria","ghana":"Ghana",".gh":"Ghana","egypt":"Egypt",".eg":"Egypt","morocco":"Morocco",".ma":"Morocco",
    "turkey":"Turkey","turkiye":"Turkey",".tr":"Turkey","russia":"Russia",".ru":"Russia","brazil":"Brazil",".br":"Brazil","mexico":"Mexico",".mx":"Mexico","chile":"Chile",".cl":"Chile","peru":"Peru",".pe":"Peru",
}
PHONE_COUNTRY = {"+91":"India","+971":"United Arab Emirates","+966":"Saudi Arabia","+974":"Qatar","+965":"Kuwait","+968":"Oman","+973":"Bahrain","+1":"United States","+44":"United Kingdom","+49":"Germany","+33":"France","+39":"Italy","+34":"Spain","+31":"Netherlands","+61":"Australia","+64":"New Zealand","+65":"Singapore","+60":"Malaysia","+66":"Thailand","+62":"Indonesia","+84":"Vietnam","+880":"Bangladesh","+94":"Sri Lanka","+977":"Nepal","+92":"Pakistan","+86":"China","+81":"Japan","+82":"South Korea","+27":"South Africa","+254":"Kenya","+234":"Nigeria","+233":"Ghana","+20":"Egypt","+212":"Morocco","+90":"Turkey","+55":"Brazil","+52":"Mexico"}
REGION = {"India":"South Asia","Bangladesh":"South Asia","Sri Lanka":"South Asia","Nepal":"South Asia","Pakistan":"South Asia","United Arab Emirates":"GCC","Saudi Arabia":"GCC","Qatar":"GCC","Kuwait":"GCC","Oman":"GCC","Bahrain":"GCC","United States":"North America","Canada":"North America","Mexico":"North America","United Kingdom":"Europe","Germany":"Europe","France":"Europe","Italy":"Europe","Spain":"Europe","Netherlands":"Europe","Belgium":"Europe","Australia":"Oceania","New Zealand":"Oceania","Singapore":"Southeast Asia","Malaysia":"Southeast Asia","Thailand":"Southeast Asia","Indonesia":"Southeast Asia","Vietnam":"Southeast Asia","Philippines":"Southeast Asia","China":"East Asia","Hong Kong":"East Asia","Japan":"East Asia","South Korea":"East Asia","South Africa":"Africa","Kenya":"Africa","Nigeria":"Africa","Ghana":"Africa","Egypt":"Africa","Morocco":"Africa","Turkey":"Middle East","Russia":"Eurasia","Brazil":"South America","Chile":"South America","Peru":"South America"}
PRODUCTS = {
    "Rice":["rice","basmati","sella","sona masoori","ir64","parboiled","broken rice"],
    "Spices":["spice","spices","chilli","chili","turmeric","cumin","pepper","masala","cardamom","coriander"],
    "Fresh Vegetables":["vegetable","onion","okra","drumstick","potato","brinjal","aubergine","cauliflower"],
    "Fruits":["fruit","banana","mango","grapes","pomegranate","cavendish","apple"],
    "Pulses & Grains":["pulse","pulses","lentil","dal","gram","wheat","grain","maize"],
    "Coconut & Oilseeds":["coconut","groundnut","peanut","oilseed","sesame"],
    "Tea & Coffee":["tea","coffee"],
    "Sugar":["sugar","jaggery"],
}
STAGES = ["New","Verified","Contacted","Follow-up","Replied","Quotation","Negotiation","Closed Won","Closed Lost","Not Interested"]
PRIORITIES = ["High","Medium","Low"]
EMAIL_STATUSES = ["Valid Format","Invalid Format","Risky/Needs Verification","Verified by Tool","Bounced","Unsubscribed"]
IMPORT_FIELDS = ["Company Name","Contact Person","Email","Phone","Website","Country","Product","Source","Address","Buyer Type","Email Status","Notes"]
EXPORT_HEADERS = ["ID","Company Name","Contact Person","Email","Phone","Website","Country","Market Category","Product","Product Category","Buyer Type","Source","Email Status","Priority","Stage","Lead Score","Next Action","First Email Sent On","Last Email Sent On","Response Received","Response Date","Follow-up 1 Done","Follow-up 1 Date","Follow-up 2 Done","Follow-up 2 Date","Follow-up 3 Done","Follow-up 3 Date","Next Follow-up Date","Notes","Created At","Updated At"]

HEADER_MAP = {
    "company_name":["company","company name","buyer","buyer name","importer","importer name","organization","organisation"],
    "contact_person":["contact person","contact","person","name","procurement manager","decision maker"],
    "email":["email","email id","e-mail","e mail","mail","mail id","email address"],
    "phone":["phone","mobile","whatsapp","contact number","telephone","tel"],
    "website":["website","web","url","site"],
    "country":["country","market","location country"],
    "product":["product","products","commodity","item","category","interested product"],
    "source":["source","data source","embassy","lead source"],
    "address":["address","city","location","full address"],
    "buyer_type":["buyer type","type","business type","segment"],
    "notes":["notes","remarks","comment","comments"],
    "email_status":["email status","email validation","validation","verification","zerobounce status","neverbounce status","hunter status","deliverability","smtp status","validity"],
}

CSS = r'''
:root{--bg:#f4f7fb;--card:#fff;--ink:#101828;--muted:#667085;--line:#e5e9f2;--brand:#0f766e;--brand2:#134e4a;--green:#ecfdf5;--blue:#eff6ff;--warn:#fff7ed;--red:#fef2f2;--shadow:0 14px 40px rgba(15,23,42,.07)}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif} a{text-decoration:none;color:var(--brand)}
.shell{display:flex;min-height:100vh}.side{width:272px;position:fixed;top:0;bottom:0;overflow:auto;background:#07111f;color:#fff;padding:24px 18px}.brand{font-size:22px;font-weight:900;letter-spacing:-.04em}.tag{color:#b9c4d4;font-size:12px;line-height:1.45;margin:8px 0 20px}.version{display:inline-block;padding:5px 9px;border-radius:999px;background:#064e3b;color:#d1fae5;font-weight:800;font-size:11px;margin-top:8px}.nav a{display:block;color:#dbe4f0;font-weight:750;margin:6px 0;padding:11px 13px;border-radius:14px}.nav a:hover,.nav .active{background:#16233a;color:#fff}.main{margin-left:272px;flex:1;padding:26px}.top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.title h1{font-size:31px;margin:0;letter-spacing:-.045em}.title p{margin:6px 0 0;color:var(--muted)}.actions{display:flex;gap:10px;flex-wrap:wrap}.btn{border:0;border-radius:13px;padding:10px 14px;background:var(--brand);color:#fff;font-weight:850;display:inline-block;cursor:pointer}.btn:hover{filter:brightness(.97);transform:translateY(-1px)}.btn.secondary{background:#e9eef7;color:#132033}.btn.ghost{background:#fff;color:#132033;border:1px solid var(--line)}.btn.danger{background:#dc2626}.btn.small{padding:7px 10px;font-size:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:18px;box-shadow:var(--shadow)}.grid{display:grid;gap:16px}.stats{grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:16px}.two{grid-template-columns:1.2fr .8fr}.three{grid-template-columns:repeat(3,minmax(0,1fr))}.stat .label{font-size:13px;color:var(--muted)}.stat .num{font-size:32px;font-weight:900;letter-spacing:-.04em;margin-top:8px}.good{background:var(--green)}.blue{background:var(--blue)}.warn{background:var(--warn)}.bad{background:var(--red)}
.filters,.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.filters{grid-template-columns:2fr 1fr 1fr 1fr auto;margin-bottom:14px}.full{grid-column:1/-1}input,select,textarea{width:100%;border:1px solid var(--line);border-radius:13px;padding:11px 12px;background:#fff;color:#111827;font:inherit}textarea{min-height:140px}.hint,.mini{color:var(--muted);font-size:13px;line-height:1.5}.mini{font-size:12px}.success{background:#ecfdf5;border:1px solid #bbf7d0;color:#065f46;border-radius:14px;padding:12px 14px;margin-bottom:14px}.error{background:#fef2f2;border:1px solid #fecaca;color:#991b1b;border-radius:14px;padding:12px 14px;margin-bottom:14px}.table-wrap{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:17px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}th{text-align:left;background:#f8fafc;color:#475467;text-transform:uppercase;font-size:12px;letter-spacing:.045em}tr:hover td{background:#fbfcff}.pill{display:inline-block;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:850;background:#edf2f7;color:#344054}.pill.green{background:#d1fae5;color:#065f46}.pill.red{background:#fee2e2;color:#991b1b}.pill.yellow{background:#fef3c7;color:#92400e}.pill.blue{background:#dbeafe;color:#1e3a8a}.kbd{background:#111827;color:#fff;border-radius:7px;padding:2px 6px;font-size:12px}.hero{background:linear-gradient(135deg,#0f766e,#12213c);color:#fff}.hero p{color:#d9fff9}.template-box{white-space:pre-wrap;background:#0b1220;color:#e7edf8;border-radius:16px;padding:14px;line-height:1.55;font-size:13px}.bulk-topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;background:#0f766e;color:#fff;border-radius:16px;padding:13px 15px;margin-bottom:12px;box-shadow:0 12px 28px rgba(15,118,110,.18)}.bulk-panel{border:2px solid #0f766e;background:linear-gradient(180deg,#ecfdf5,#fff)}.selectedCount,.score{display:inline-block;background:#0f766e;color:#fff;border-radius:999px;padding:6px 10px;font-weight:850;font-size:12px}.score{background:#1d4ed8}.big-checkbox{width:18px!important;height:18px}.bulk-steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.bulk-step{background:#fff;border:1px solid var(--line);border-radius:13px;padding:10px}.kanban{display:grid;grid-template-columns:repeat(5,minmax(220px,1fr));gap:14px;overflow:auto}.lane{background:#f8fafc;border:1px solid var(--line);border-radius:18px;padding:12px}.lead-card{background:#fff;border:1px solid var(--line);border-radius:15px;padding:12px;margin:10px 0}.footer{margin-top:28px;color:var(--muted);font-size:12px}@media(max-width:1000px){.side{position:relative;width:100%;height:auto;padding:16px}.shell{display:block}.main{margin-left:0;padding:16px}.stats,.two,.three,.filters,.form-grid,.bulk-steps{grid-template-columns:1fr}.kanban{grid-template-columns:1fr}.top{flex-direction:column;align-items:flex-start}.actions{width:100%;justify-content:flex-start}table{white-space:nowrap}.bulk-topbar{flex-direction:column;align-items:flex-start}}
'''
JS = r'''
function selectedBuyerCount(){return Array.from(document.querySelectorAll('input[name="buyer_ids"]')).filter(x=>x.checked).length}
function updateSelectedCount(){let c=selectedBuyerCount();document.querySelectorAll('.selectedCount').forEach(e=>e.innerText=c+(c===1?' buyer selected':' buyers selected'))}
function toggleAll(src){document.querySelectorAll('input[name="buyer_ids"]').forEach(cb=>cb.checked=src.checked);updateSelectedCount()}
function ensureBulkSelection(){if(selectedBuyerCount()===0){alert('Please select at least one buyer first.');return false}return true}
function setBulkOpen(open){let b=document.getElementById('bulkPanelBody'),btn=document.getElementById('bulkToggleBtn'),mini=document.getElementById('bulkMiniText');if(!b||!btn)return;b.style.display=open?'block':'none';btn.innerText=open?'− Minimize Bulk Edit':'+ Open Bulk Edit';if(mini)mini.style.display=open?'none':'block'}
function toggleBulkPanel(){let b=document.getElementById('bulkPanelBody');setBulkOpen(!(b&&b.style.display==='block'))}
function openBulkPanel(){setBulkOpen(true);let p=document.getElementById('bulk-editor');if(p)p.scrollIntoView({behavior:'smooth',block:'start'})}
function copyText(id){let el=document.getElementById(id);if(el){navigator.clipboard&&navigator.clipboard.writeText(el.innerText);alert('Copied')}}
document.addEventListener('DOMContentLoaded',()=>{updateSelectedCount();document.querySelectorAll('input[name="buyer_ids"]').forEach(cb=>cb.addEventListener('change',updateSelectedCount));setBulkOpen(location.hash==='#bulk-editor')})
'''

def esc(x): return html.escape("" if x is None else str(x), quote=True)
def clean(x): return str(x or "").replace("\x00","").strip()
def today(): return date.today().isoformat()
def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def valid_email(e): return bool(clean(e) and EMAIL_RE.match(clean(e).lower()))
def norm_header(h): return re.sub(r"[^a-z0-9]+"," ",str(h).lower()).strip()
import pg8000
from urllib.parse import urlparse

DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("POSTGRES_URL_NON_POOLING")
    or os.environ.get("SUPABASE_DB_URL")
    or ""
)

def parse_pg_url(url):
    parsed = urlparse(url)
    return {
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip('/')
    }

class RowWrapper:
    def __init__(self, cols, vals):
        self.cols = cols
        self.vals = vals
        self.map = {col: val for col, val in zip(cols, vals)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.vals[key]
        return self.map[key]

    def keys(self):
        return self.cols

    def __iter__(self):
        return iter(self.vals)

class CursorWrapper:
    def __init__(self, cursor, conn_wrapper):
        self.cursor = cursor
        self.conn_wrapper = conn_wrapper
        self._mock_val = None

    def execute(self, sql, params=None):
        if "PRAGMA" in sql:
            self._mock_val = None
            return self
        
        if "CREATE TABLE" in sql:
            sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            sql = sql.replace("AUTOINCREMENT", "")
        
        if "INSERT OR IGNORE" in sql:
            sql = sql.replace("INSERT OR IGNORE INTO campaign_recipients", "INSERT INTO campaign_recipients")
            if "VALUES" in sql:
                sql += " ON CONFLICT (campaign_id, buyer_id) DO NOTHING"
            sql = sql.replace("INSERT OR IGNORE INTO buyers", "INSERT INTO buyers")
            if "buyers" in sql and "VALUES" in sql:
                sql += " ON CONFLICT (email) DO NOTHING"

        if "SELECT last_insert_rowid()" in sql:
            self._mock_val = (self.conn_wrapper._last_id,)
            return self

        self._mock_val = None
        sql = sql.replace("?", "%s")

        is_insert = sql.strip().upper().startswith("INSERT INTO")
        if is_insert and "RETURNING" not in sql.upper():
            sql += " RETURNING id"

        try:
            if params is not None:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
        except Exception as e:
            err_msg = str(e).lower()
            if "unique" in err_msg or "duplicate" in err_msg or "integrity" in err_msg:
                try:
                    self.conn_wrapper.conn.rollback()
                except Exception:
                    pass
                import sqlite3
                raise sqlite3.IntegrityError(str(e))
            raise e

        if is_insert:
            try:
                row = self.cursor.fetchone()
                if row:
                    self.conn_wrapper._last_id = row[0]
            except Exception:
                pass
        return self

    def _wrap_row(self, row):
        if row is None:
            return None
        if isinstance(row, RowWrapper):
            return row
        if not self.cursor.description:
            return row
        cols = [desc[0] for desc in self.cursor.description]
        return RowWrapper(cols, row)

    def fetchone(self):
        if self._mock_val is not None:
            val = self._mock_val
            self._mock_val = None
            return val
        try:
            return self._wrap_row(self.cursor.fetchone())
        except Exception:
            return None

    def fetchall(self):
        if self._mock_val is not None:
            val = [self._mock_val]
            self._mock_val = None
            return [self._wrap_row(v) for v in val]
        try:
            rows = self.cursor.fetchall()
            return [self._wrap_row(r) for r in rows]
        except Exception:
            return []

    def __iter__(self):
        return iter(self.fetchall())


class PostgresConnWrapper:
    def __init__(self, conn):
        self.conn = conn
        self._last_id = None
        self.row_factory = None

    def cursor(self):
        return CursorWrapper(self.conn.cursor(), self)

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            try:
                self.conn.rollback()
            except Exception:
                pass
        else:
            try:
                self.conn.commit()
            except Exception:
                pass
        try:
            self.conn.close()
        except Exception:
            pass


def conn():
    import ssl
    if not DATABASE_URL:
        raise RuntimeError("Database connection is not set. Add DATABASE_URL or POSTGRES_URL in Vercel Environment Variables.")
    kwargs = parse_pg_url(DATABASE_URL)
    try:
        ssl_context = ssl.create_default_context()
        # Supabase requires SSL, so we pass the context
        raw_conn = pg8000.dbapi.connect(**kwargs, ssl_context=ssl_context)
    except Exception:
        # Fallback to non-SSL if SSL is not configured/supported locally
        raw_conn = pg8000.dbapi.connect(**kwargs)
    return PostgresConnWrapper(raw_conn)



def default_templates():
    return [
        ("First Cold Email","Indian {{product}} supply for {{country}} market","Hi {{buyer_name}},\n\nI am Saksham, working with an Indian export company that supplies {{product}} to international buyers.\n\nWe are currently connecting with importers and distributors in {{country}}. We can share available grades, packaging, MOQ, certifications, and pricing.\n\nAre you currently importing {{product}}, or should I contact the right person in your procurement team?\n\nRegards,\nSaksham Singh\n\nTo stop receiving these emails, reply unsubscribe.","Cold Outreach"),
        ("Follow-up 1","Following up: {{product}} supply from India","Hi {{buyer_name}},\n\nI wanted to follow up on my previous email regarding {{product}} supply from India for {{country}}.\n\nAre you currently importing this product, or should I contact someone else in your procurement team?\n\nRegards,\nSaksham Singh","Follow-up"),
        ("Breakup / Close File","Should I close this file?","Hi {{buyer_name}},\n\nI wanted to check once before closing this from my side.\n\nAre you the right person for {{product}} imports at {{company_name}}, or should I contact someone else in your procurement/import department?\n\nRegards,\nSaksham Singh","Follow-up"),
        ("Requirement Collection","Requirement details for {{product}}","Hi {{buyer_name}},\n\nThank you for your interest in {{product}}. Please share your required quantity, packaging preference, destination port, target specification, and expected buying timeline.\n\nOnce we have these details, we can send the correct quotation.\n\nRegards,\nSaksham Singh","Quotation"),
        ("Quotation Follow-up","Checking quotation for {{product}}","Hi {{buyer_name}},\n\nI wanted to check if you had a chance to review the quotation/details for {{product}}.\n\nPlease let me know if you need revised quantity, packaging, port, or payment terms.\n\nRegards,\nSaksham Singh","Quotation"),
    ]

def init_db():
    with conn() as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("""CREATE TABLE IF NOT EXISTS buyers(
          id INTEGER PRIMARY KEY AUTOINCREMENT, company_name TEXT, contact_person TEXT, email TEXT UNIQUE, phone TEXT, website TEXT, country TEXT, market_category TEXT, product TEXT, product_category TEXT, buyer_type TEXT, source TEXT, email_status TEXT, priority TEXT DEFAULT 'Medium', stage TEXT DEFAULT 'New', first_email_sent_on TEXT, last_email_sent_on TEXT, response_received INTEGER DEFAULT 0, response_date TEXT, followup1_done INTEGER DEFAULT 0, followup1_date TEXT, followup2_done INTEGER DEFAULT 0, followup2_date TEXT, followup3_done INTEGER DEFAULT 0, followup3_date TEXT, next_followup_date TEXT, notes TEXT, created_at TEXT, updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS activities(id INTEGER PRIMARY KEY AUTOINCREMENT,buyer_id INTEGER,activity_type TEXT,activity_date TEXT,notes TEXT,created_at TEXT,FOREIGN KEY(buyer_id) REFERENCES buyers(id) ON DELETE CASCADE)""")
        c.execute("""CREATE TABLE IF NOT EXISTS email_templates(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,category TEXT DEFAULT 'General',is_default INTEGER DEFAULT 0,created_at TEXT,updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS campaigns(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,template_id INTEGER,segment_note TEXT,created_at TEXT,updated_at TEXT,FOREIGN KEY(template_id) REFERENCES email_templates(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS campaign_recipients(id INTEGER PRIMARY KEY AUTOINCREMENT,campaign_id INTEGER,buyer_id INTEGER,email TEXT,subject_snapshot TEXT,body_snapshot TEXT,sent INTEGER DEFAULT 0,sent_on TEXT,reply_received INTEGER DEFAULT 0,reply_on TEXT,notes TEXT,created_at TEXT,FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,FOREIGN KEY(buyer_id) REFERENCES buyers(id) ON DELETE CASCADE,UNIQUE(campaign_id,buyer_id))""")
        if c.execute("SELECT COUNT(*) FROM email_templates").fetchone()[0]==0:
            n=now()
            for name,sub,body,cat in default_templates(): c.execute("INSERT INTO email_templates(name,subject,body,category,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(name,sub,body,cat,1,n,n))
        c.commit()

def recognize_country(d):
    explicit=clean(d.get('country'))
    if explicit:
        low=explicit.lower()
        for k,v in COUNTRIES.items():
            if k==low or k in low: return v
        return explicit.title()
    phone=clean(d.get('phone')).replace(' ','').replace('-','')
    for pre,c in sorted(PHONE_COUNTRY.items(), key=lambda x:len(x[0]), reverse=True):
        if phone.startswith(pre): return c
    text=' '.join(clean(d.get(k)) for k in ['address','company_name','website','email','source','notes']).lower()
    for k,v in COUNTRIES.items():
        if k.startswith('.'):
            if k in text: return v
        elif re.search(r'\b'+re.escape(k)+r'\b', text): return v
    return 'Unknown'

def market_cat(country): return REGION.get(clean(country),'Other / Unknown')
def product_cat(product, notes=''):
    t=(clean(product)+' '+clean(notes)).lower()
    for cat,keys in PRODUCTS.items():
        if any(k in t for k in keys): return cat
    return 'General Importer'

def normalize_email_status(v):
    x=clean(v).lower()
    if not x: return ''
    if any(k in x for k in ['unsubscribe','opt out','do not email','suppressed']): return 'Unsubscribed'
    if any(k in x for k in ['bounce','bounced','hard bounce']): return 'Bounced'
    if any(k in x for k in ['invalid','undeliverable','failed','bad','reject']): return 'Invalid Format'
    if any(k in x for k in ['valid','deliverable','verified','ok','success','pass']) and not any(k in x for k in ['not valid','invalid','undeliverable']): return 'Verified by Tool'
    if any(k in x for k in ['risky','risk','catch','catch-all','unknown','accept all','accept-all']): return 'Risky/Needs Verification'
    if x in [e.lower() for e in EMAIL_STATUSES]: return next(e for e in EMAIL_STATUSES if e.lower()==x)
    return 'Risky/Needs Verification'

def email_status_from_email(email):
    if not clean(email): return 'Risky/Needs Verification'
    return 'Valid Format' if valid_email(email) else 'Invalid Format'

def safe_date(v):
    try: return date.fromisoformat(clean(v)[:10]) if clean(v) else None
    except Exception: return None

def lead_score(b):
    b=dict(b) if not isinstance(b,dict) else b
    score=0; es=clean(b.get('email_status')); st=clean(b.get('stage')) or 'New'; country=clean(b.get('country')); pc=clean(b.get('product_category')); market=clean(b.get('market_category'))
    if clean(b.get('company_name')): score+=10
    if clean(b.get('contact_person')): score+=8
    if valid_email(b.get('email')): score+=10
    if es=='Verified by Tool': score+=18
    elif es=='Valid Format': score+=12
    elif es=='Risky/Needs Verification': score+=2
    if clean(b.get('phone')): score+=6
    if clean(b.get('website')): score+=7
    if country and country!='Unknown': score+=10
    if market in ['GCC','Europe','North America','Southeast Asia','Africa']: score+=5
    if pc and pc!='General Importer': score+=13
    if clean(b.get('buyer_type')): score+=5
    if clean(b.get('source')): score+=4
    if clean(b.get('last_email_sent_on')): score+=5
    if b.get('response_received') or st in ['Replied','Quotation','Negotiation','Closed Won']: score+=20
    if st=='Quotation': score+=12
    elif st=='Negotiation': score+=18
    elif st=='Closed Won': score+=25
    elif st in ['Contacted','Follow-up']: score+=5
    gap=None
    d=safe_date(b.get('next_followup_date'))
    if d: gap=(d-date.today()).days
    if gap is not None and gap<=0 and st not in ['Closed Won','Closed Lost','Not Interested']: score+=5
    if sum(1 for k in ['followup1_done','followup2_done','followup3_done'] if b.get(k))>=3 and not b.get('response_received'): score-=12
    if es in ['Invalid Format','Bounced','Unsubscribed']: score-=45
    if st in ['Closed Lost','Not Interested']: score-=35
    if country=='Unknown': score-=5
    if pc=='General Importer': score-=5
    return max(0,min(100,int(score)))

def smart_priority(b):
    s=lead_score(b)
    return 'High' if s>=75 else 'Low' if s<=35 else 'Medium'

def next_action(b):
    b=dict(b) if not isinstance(b,dict) else b
    if b.get('email_status') in ['Invalid Format','Bounced']: return 'Fix/verify email before sending'
    if b.get('email_status')=='Unsubscribed': return 'Do not email'
    if not clean(b.get('country')) or b.get('country')=='Unknown': return 'Identify country/category'
    if not clean(b.get('product')) or b.get('product_category')=='General Importer': return 'Add product interest'
    if b.get('response_received') and b.get('stage') in ['Replied','Quotation','Negotiation']: return 'Prepare quotation / ask requirement'
    d=safe_date(b.get('next_followup_date'))
    if d and d<=date.today(): return 'Follow up today'
    if not clean(b.get('last_email_sent_on')): return 'Send first email'
    return 'Wait until next follow-up'

def tag_stage(x):
    cls='green' if x in ['Replied','Quotation','Negotiation','Closed Won'] else 'red' if x in ['Closed Lost','Not Interested'] else 'yellow' if x in ['Contacted','Follow-up'] else 'blue'
    return f'<span class="pill {cls}">{esc(x or "New")}</span>'
def tag_email(x):
    cls='green' if x in ['Valid Format','Verified by Tool'] else 'red' if x in ['Invalid Format','Bounced','Unsubscribed'] else 'yellow'
    return f'<span class="pill {cls}">{esc(x)}</span>'
def tag_score(b): return f'<span class="score">Score {lead_score(b)}</span>'

def build_buyer(raw):
    d={k:clean(raw.get(k)) for k in ['company_name','contact_person','email','phone','website','country','product','source','address','buyer_type','notes']}
    d['email']=d['email'].lower()
    country=recognize_country(d); pc=product_cat(d.get('product'),d.get('notes'))
    es=normalize_email_status(raw.get('email_status')) or email_status_from_email(d.get('email'))
    base={k:d[k] for k in ['company_name','contact_person','email','phone','website','product','source','buyer_type','notes']}
    b={**base,'country':country,'market_category':market_cat(country),'product_category':pc,'email_status':es,'stage':raw.get('stage') or 'New','priority':raw.get('priority') or 'Medium','first_email_sent_on':raw.get('first_email_sent_on') or '','last_email_sent_on':raw.get('last_email_sent_on') or '','response_received':1 if str(raw.get('response_received','')).lower() in ['1','yes','true','on'] else 0,'response_date':raw.get('response_date') or '','followup1_done':1 if str(raw.get('followup1_done','')).lower() in ['1','yes','true','on'] else 0,'followup1_date':raw.get('followup1_date') or '','followup2_done':1 if str(raw.get('followup2_done','')).lower() in ['1','yes','true','on'] else 0,'followup2_date':raw.get('followup2_date') or '','followup3_done':1 if str(raw.get('followup3_done','')).lower() in ['1','yes','true','on'] else 0,'followup3_date':raw.get('followup3_date') or '','next_followup_date':raw.get('next_followup_date') or ''}
    b['priority']=raw.get('priority') or smart_priority(b)
    return b

def insert_buyer(raw):
    b=build_buyer(raw); n=now(); b['created_at']=n; b['updated_at']=n
    fields=list(b.keys()); vals=[b[f] for f in fields]
    with conn() as c:
        try:
            c.execute(f"INSERT INTO buyers({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",vals); bid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT INTO activities(buyer_id,activity_type,activity_date,notes,created_at) VALUES(?,?,?,?,?)',(bid,'Created',today(),'Buyer added/imported',n)); c.commit(); return 'inserted'
        except sqlite3.IntegrityError:
            existing=c.execute('SELECT * FROM buyers WHERE email=?',(b.get('email'),)).fetchone()
            if existing:
                updates={'updated_at':n}
                # validation imports can update existing status without overwriting other fields
                if b.get('email_status') in EMAIL_STATUSES and b.get('email_status')!=existing['email_status']: updates['email_status']=b.get('email_status')
                if b.get('notes') and not existing['notes']: updates['notes']=b.get('notes')
                if len(updates)>1:
                    sets=', '.join(f'{k}=?' for k in updates); c.execute(f'UPDATE buyers SET {sets} WHERE id=?',list(updates.values())+[existing['id']])
                    c.execute('INSERT INTO activities(buyer_id,activity_type,activity_date,notes,created_at) VALUES(?,?,?,?,?)',(existing['id'],'Duplicate updated',today(),'Duplicate email found; validation/missing data updated',n)); c.commit(); return 'updated'
            return 'duplicate'

def update_buyer(buyer_id, raw):
    b=build_buyer(raw); b['updated_at']=now(); fields=list(b.keys())
    with conn() as c:
        c.execute(f"UPDATE buyers SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", [b[f] for f in fields]+[buyer_id])
        c.execute('INSERT INTO activities(buyer_id,activity_type,activity_date,notes,created_at) VALUES(?,?,?,?,?)',(buyer_id,'Updated',today(),'Buyer details edited',now())); c.commit()

def get_buyer(bid):
    with conn() as c: return c.execute('SELECT * FROM buyers WHERE id=?',(bid,)).fetchone()

def all_buyers():
    with conn() as c: return c.execute('SELECT * FROM buyers ORDER BY updated_at DESC,id DESC').fetchall()

def add_activity(bid, action, activity_date, notes='', next_follow=''):
    b=get_buyer(bid); n=now(); updates={'updated_at':n}
    base=safe_date(activity_date) or date.today()
    if action=='Email Sent':
        updates.update({'stage':'Contacted','last_email_sent_on':activity_date,'next_followup_date':next_follow or (base+timedelta(days=3)).isoformat()})
        if b and not b['first_email_sent_on']: updates['first_email_sent_on']=activity_date
    elif action=='Follow-up 1 Done': updates.update({'stage':'Follow-up','followup1_done':1,'followup1_date':activity_date,'next_followup_date':next_follow or (base+timedelta(days=4)).isoformat()})
    elif action=='Follow-up 2 Done': updates.update({'stage':'Follow-up','followup2_done':1,'followup2_date':activity_date,'next_followup_date':next_follow or (base+timedelta(days=5)).isoformat()})
    elif action=='Follow-up 3 Done': updates.update({'stage':'Follow-up','followup3_done':1,'followup3_date':activity_date,'next_followup_date':next_follow or (base+timedelta(days=7)).isoformat()})
    elif action=='Response Received': updates.update({'stage':'Replied','response_received':1,'response_date':activity_date})
    elif action=='Quotation Sent': updates.update({'stage':'Quotation','next_followup_date':next_follow or (base+timedelta(days=3)).isoformat()})
    elif action=='Negotiation Started': updates['stage']='Negotiation'
    elif action in ['Closed Won','Closed Lost','Not Interested']: updates.update({'stage':action,'next_followup_date':''})
    elif action=='Verified by Tool': updates['email_status']='Verified by Tool'
    elif action=='Bounced': updates.update({'email_status':'Bounced','priority':'Low'})
    elif action=='Unsubscribed': updates.update({'email_status':'Unsubscribed','priority':'Low','next_followup_date':''})
    sets=', '.join(f'{k}=?' for k in updates)
    with conn() as c:
        c.execute(f'UPDATE buyers SET {sets} WHERE id=?',list(updates.values())+[bid])
        c.execute('INSERT INTO activities(buyer_id,activity_type,activity_date,notes,created_at) VALUES(?,?,?,?,?)',(bid,action,activity_date,notes,n)); c.commit()

def list_buyers(params):
    q=clean(params.get('q',[''])[0]); country=clean(params.get('country',[''])[0]); stage=clean(params.get('stage',[''])[0]); cat=clean(params.get('category',[''])[0]); due=clean(params.get('due',[''])[0])
    sql='SELECT * FROM buyers WHERE 1=1'; vals=[]
    if q: sql+=' AND (company_name LIKE ? OR contact_person LIKE ? OR email LIKE ? OR product LIKE ? OR notes LIKE ?)'; vals+=['%'+q+'%']*5
    if country: sql+=' AND country=?'; vals.append(country)
    if stage: sql+=' AND stage=?'; vals.append(stage)
    if cat: sql+=' AND product_category=?'; vals.append(cat)
    if due: sql+=" AND next_followup_date!='' AND next_followup_date<=? AND stage NOT IN ('Closed Won','Closed Lost','Not Interested')"; vals.append(today())
    sql+=" ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, updated_at DESC, id DESC LIMIT 1500"
    with conn() as c:
        rows=c.execute(sql,vals).fetchall(); countries=[r[0] for r in c.execute("SELECT DISTINCT country FROM buyers WHERE country!='' ORDER BY country")]; cats=[r[0] for r in c.execute("SELECT DISTINCT product_category FROM buyers WHERE product_category!='' ORDER BY product_category")]
    return rows,countries,cats

def stats():
    with conn() as c:
        total=c.execute('SELECT COUNT(*) FROM buyers').fetchone()[0]
        contacted=c.execute("SELECT COUNT(*) FROM buyers WHERE last_email_sent_on!='' OR stage IN ('Contacted','Follow-up','Replied','Quotation','Negotiation','Closed Won','Closed Lost')").fetchone()[0]
        replied=c.execute("SELECT COUNT(*) FROM buyers WHERE response_received=1 OR stage IN ('Replied','Quotation','Negotiation','Closed Won')").fetchone()[0]
        due=c.execute("SELECT COUNT(*) FROM buyers WHERE next_followup_date!='' AND next_followup_date<=? AND stage NOT IN ('Closed Won','Closed Lost','Not Interested')",(today(),)).fetchone()[0]
        due_buyers=c.execute("SELECT * FROM buyers WHERE next_followup_date!='' AND next_followup_date<=? AND stage NOT IN ('Closed Won','Closed Lost','Not Interested') ORDER BY next_followup_date ASC LIMIT 500",(today(),)).fetchall()
        invalid=c.execute("SELECT COUNT(*) FROM buyers WHERE email_status IN ('Invalid Format','Bounced','Unsubscribed')").fetchone()[0]
        campaigns=c.execute('SELECT COUNT(*) FROM campaigns').fetchone()[0]
        recent=c.execute('SELECT * FROM buyers ORDER BY updated_at DESC,id DESC LIMIT 8').fetchall()
        stages=c.execute('SELECT stage,COUNT(*) c FROM buyers GROUP BY stage ORDER BY c DESC').fetchall()
        countries=c.execute('SELECT country,COUNT(*) c FROM buyers GROUP BY country ORDER BY c DESC LIMIT 8').fetchall()
    return locals()

def select_options(opts, selected=''):
    return ''.join(f'<option value="{esc(o)}" {"selected" if clean(selected)==o else ""}>{esc(o)}</option>' for o in opts)

def layout(title, body, active='dashboard'):
    nav=[('/','Dashboard','dashboard'),('/smart-followups','🔥 Smart Follow-ups','smart'),('/campaigns','Email Campaigns','campaigns'),('/templates','Email Templates','templates'),('/buyers#bulk-editor','⚡ Bulk Edit','bulk'),('/buyers','Buyer Pipeline','buyers'),('/kanban','Kanban Board','kanban'),('/data-quality','Data Quality','quality'),('/buyer/new','Add Buyer','add'),('/import','Import Data','import'),('/backup-restore','Backup & Restore','backup'),('/export/xlsx','Export Excel','export'),('/report/pdf','PDF Report','report')]
    navhtml=''.join(f'<a class="{"active" if active==key else ""}" href="{href}">{label}</a>' for href,label,key in nav)
    return f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · Smart Export CRM V7.2 Outlook Desktop</title><style>{CSS}</style><script>{JS}</script></head><body><div class="shell"><aside class="side"><div class="brand">Smart Export CRM V7.2</div><div class="tag">Local buyer CRM with campaigns, editable templates, validation import, smart follow-ups, bulk edit, backup and restore.<br><span class="version">OUTLOOK DESKTOP APP · PORT {PORT}</span></div><div class="nav">{navhtml}</div><div class="tag" style="margin-top:24px">Database: <span class="kbd">export_import_crm.sqlite</span><br>Saved in this same folder.</div></aside><main class="main">{body}<div class="footer">V7.2 Outlook Desktop is active on port {PORT}. Email buttons open the installed Outlook app through Windows MAILTO with recipient, subject, and message pre-filled; they never open Outlook Web.</div></main></div></body></html>'

def top(title, subtitle='', actions=''): return f'<div class="top"><div class="title"><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div><div class="actions">{actions}</div></div>'

def rows_table(rows, compact=False, selectable=False):
    if not rows: return '<p class="hint">No buyers found.</p>'
    trs=[]
    for r in rows:
        company=esc(r['company_name'] or 'Unnamed Company'); email=esc(r['email'] or 'No email'); prod=esc(r['product'] or '-'); country=esc(r['country'] or 'Unknown')
        if compact:
            trs.append(f'<tr><td><a href="/buyer/{r["id"]}"><strong>{company}</strong></a><br><span class="mini">{email}</span><br>{tag_score(r)}</td><td>{country}<br><span class="mini">{prod}</span></td><td>{tag_stage(r["stage"] or "New")}</td><td>{esc(r["next_followup_date"] or "-")}<br><span class="mini">{esc(next_action(r))}</span></td></tr>')
        else:
            sel=f'<td><input class="big-checkbox" type="checkbox" name="buyer_ids" value="{r["id"]}"></td>' if selectable else ''
            trs.append(f'<tr>{sel}<td><a href="/buyer/{r["id"]}"><strong>{company}</strong></a><br><span class="mini">{email}</span><br>{tag_score(r)}</td><td>{country}<br><span class="mini">{esc(r["market_category"] or "")}</span></td><td>{prod}<br><span class="mini">{esc(r["product_category"] or "")}</span></td><td>{tag_email(r["email_status"] or "")}</td><td>{tag_stage(r["stage"] or "New")}</td><td>{esc(r["priority"] or "Medium")}</td><td>{esc(r["next_followup_date"] or "-")}<br><span class="mini">{esc(next_action(r))}</span></td><td><a class="btn small secondary" href="/buyer/{r["id"]}">Open</a></td></tr>')
    head_select='<th>Select<br><input class="big-checkbox" type="checkbox" onclick="toggleAll(this)"></th>' if selectable else ''
    headers='<tr>'+head_select+'<th>Buyer</th><th>Country</th><th>Product</th><th>Email Status</th><th>Stage</th><th>Priority</th><th>Next Action</th><th>Action</th></tr>' if not compact else '<tr><th>Buyer</th><th>Market</th><th>Stage</th><th>Next Follow-up</th></tr>'
    return f'<div class="table-wrap"><table>{headers}{"".join(trs)}</table></div>'

def dashboard_page():
    with conn() as c: templates=c.execute('SELECT * FROM email_templates ORDER BY updated_at DESC').fetchall()
    s=stats(); rr=round(s['replied']/s['contacted']*100,1) if s['contacted'] else 0
    stage_html=''.join(f'<tr><td>{tag_stage(r["stage"] or "New")}</td><td><strong>{r["c"]}</strong></td></tr>' for r in s['stages']) or '<tr><td colspan="2">No data</td></tr>'
    country_html=''.join(f'<tr><td>{esc(r["country"] or "Unknown")}</td><td><strong>{r["c"]}</strong></td></tr>' for r in s['countries']) or '<tr><td colspan="2">No data</td></tr>'
    due_html = ''
    for r in s['due_buyers']:
        btn_html = ''
        if templates:
            target_name = 'Follow-up 3' if r['followup2_done'] else ('Follow-up 2' if r['followup1_done'] else 'Follow-up 1')
            t = next((x for x in templates if x['name'] == target_name), None)
            if not t: t = next((x for x in templates if 'follow' in str(x['category']).lower() or 'follow' in str(x['name']).lower()), None)
            if not t: t = templates[0]
            url = titan_compose_url({'buyer_id':[str(r['id'])], 'template_id':[str(t['id'])]})
            post_body = f"action={target_name} Done&activity_date={today()}"
            onclick_js = f"fetch('/buyer/{r['id']}/action', {{method:'POST', headers:{{'Content-Type':'application/x-www-form-urlencoded'}}, body:'{post_body}'}}).then(()=>setTimeout(()=>location.reload(), 1000));"
            btn_html = f'<a class="btn small secondary" title="Using template: {esc(t["name"])}" href="{esc(url)}" onclick="{onclick_js}">Follow-up</a>'
        due_html += f'<tr><td><a href="/buyer/{r["id"]}"><strong>{esc(r["company_name"])}</strong></a><br><span class="mini">{esc(r["email"])}</span></td><td>{esc(r["next_followup_date"])}</td><td>{btn_html} <a class="btn small ghost" href="/buyer/{r["id"]}">Open</a></td></tr>'
    if not due_html:
        due_html = '<tr><td colspan="3" class="hint">No followups due. Great job!</td></tr>'
    body=top('Dashboard','Campaigns, buyer pipeline, replies, invalid emails, and follow-up tasks.','<a class="btn" href="/campaign/new">+ New Campaign</a><a class="btn secondary" href="/import">Import Excel/CSV</a>')
    body+=f'<div class="card hero"><h2 style="margin-top:0">Saksham\'s smarter export CRM</h2><p>Use this as your master system: import embassy data, validate email status columns, create personalized campaign emails, bulk mark sent, and show client-ready reporting.</p></div><div class="grid stats"><div class="card stat"><div class="label">Total Buyers</div><div class="num">{s["total"]}</div></div><div class="card stat blue"><div class="label">Campaigns</div><div class="num">{s["campaigns"]}</div></div><div class="card stat good"><div class="label">Replies</div><div class="num">{s["replied"]}</div><div class="mini">{rr}% reply rate after contact</div></div><div class="card stat warn"><div class="label">Follow-ups Due</div><div class="num">{s["due"]}</div><div class="mini">Invalid/Bounced/Unsub: {s["invalid"]}</div></div></div>'
    body+=f'<div class="card" style="margin-top:16px; margin-bottom:16px; border:1px solid #f59e0b; background:#fffbf1;"><h3>🔥 Follow-ups Due Today ({len(s["due_buyers"])})</h3><div class="table-wrap"><table><tr><th>Buyer</th><th>Follow-up Date</th><th>Action</th></tr>{due_html}</table></div></div>'
    body+=f'<div class="grid two"><div class="card"><h3>Recent Buyers</h3>{rows_table(s["recent"],compact=True)}</div><div class="card"><h3>Pipeline by Stage</h3><div class="table-wrap"><table><tr><th>Stage</th><th>Count</th></tr>{stage_html}</table></div></div></div><div class="card" style="margin-top:16px"><h3>Top Countries</h3><div class="table-wrap"><table><tr><th>Country</th><th>Count</th></tr>{country_html}</table></div></div>'
    return layout('Dashboard',body,'dashboard')

def buyers_page(params):
    rows,countries,cats=list_buyers(params); q=clean(params.get('q',[''])[0]); country=clean(params.get('country',[''])[0]); stage=clean(params.get('stage',[''])[0]); cat=clean(params.get('category',[''])[0]); due=clean(params.get('due',[''])[0])
    body=top('Buyer Pipeline',f'Showing {len(rows)} buyer records with bulk edit and smart scores.','<a class="btn" href="/buyer/new">+ Add Buyer</a><button class="btn secondary" type="button" onclick="openBulkPanel()">⚡ Open Bulk Edit</button><a class="btn secondary" href="/export/xlsx">Export Excel</a>')
    body+=f'<form method="get" class="filters"><input name="q" placeholder="Search company, email, product, notes" value="{esc(q)}"><select name="country"><option value="">All countries</option>{select_options(countries,country)}</select><select name="stage"><option value="">All stages</option>{select_options(STAGES,stage)}</select><select name="category"><option value="">All products</option>{select_options(cats,cat)}</select><button class="btn" type="submit">Filter</button><label class="hint"><input style="width:auto" type="checkbox" name="due" value="1" {"checked" if due else ""}> Follow-ups due only</label></form>'
    body+=f'<div class="bulk-topbar"><div><strong>⚡ Bulk Edit Shortcut</strong><div class="hint" style="color:#dcfffa">Select buyers from table, then open bulk editor.</div></div><div><span class="selectedCount">0 buyers selected</span> <button class="btn ghost" type="button" onclick="openBulkPanel()">+ Open Bulk Edit</button></div></div><form method="post" action="/bulk-action" onsubmit="return ensureBulkSelection()"><div id="bulk-editor" class="card bulk-panel" style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap"><div><h2 style="margin:0">Bulk Actions & Bulk Edit</h2><div id="bulkMiniText" class="hint">Bulk editor is minimized. Click Open Bulk Edit.</div></div><div><span class="selectedCount">0 buyers selected</span> <button id="bulkToggleBtn" class="btn" type="button" onclick="toggleBulkPanel()">+ Open Bulk Edit</button></div></div><div id="bulkPanelBody" style="display:none;margin-top:12px"><div class="bulk-steps"><div class="bulk-step"><strong>Step 1</strong><br>Select buyers below</div><div class="bulk-step"><strong>Step 2</strong><br>Choose quick action or field edit</div><div class="bulk-step"><strong>Step 3</strong><br>Apply to selected buyers</div></div><div class="form-grid" style="margin-top:12px"><label>Quick Action<select name="bulk_action"><option>Bulk Edit Selected Fields</option><option>Email Sent</option><option>Follow-up 1 Done</option><option>Follow-up 2 Done</option><option>Follow-up 3 Done</option><option>Response Received</option><option>Quotation Sent</option><option>Negotiation Started</option><option>Closed Won</option><option>Closed Lost</option><option>Not Interested</option><option>Verified by Tool</option><option>Bounced</option><option>Unsubscribed</option></select></label><label>Activity Date<input type="date" name="activity_date" value="{today()}"></label><label>Next Follow-up<input type="date" name="next_followup_date" value="{(date.today()+timedelta(days=3)).isoformat()}"></label><label>Set Stage<select name="stage"><option value="">No change</option>{select_options(STAGES)}</select></label><label>Set Email Status<select name="email_status"><option value="">No change</option>{select_options(EMAIL_STATUSES)}</select></label><label>Set Priority<select name="priority"><option value="">Auto/no change</option>{select_options(PRIORITIES)}</select></label><label>Set Country<input name="country" placeholder="United Arab Emirates"></label><label>Set Product<input name="product" placeholder="Basmati Rice"></label><label>Set Buyer Type<input name="buyer_type" placeholder="Importer / Distributor"></label><label class="full">Notes<textarea name="notes" placeholder="Bulk notes/activity"></textarea></label></div><button class="btn" type="submit">Apply to Selected Buyers</button> <button class="btn secondary" type="button" onclick="toggleBulkPanel()">Minimize</button></div></div>{rows_table(rows,selectable=True)}</form>'
    return layout('Buyers',body,'buyers')

def buyer_form_page(b=None):
    b=dict(b) if b else {}; isedit=bool(b); action=f'/buyer/{b.get("id")}/edit' if isedit else '/buyer/new'; title='Edit Buyer' if isedit else 'Add Buyer'
    body=top(title,'Country, market, product category, email status and score are calculated after saving.','<a class="btn secondary" href="/buyers">Back</a>')
    def val(k): return esc(b.get(k,''))
    body+=f'<div class="card"><form method="post" action="{action}"><div class="form-grid"><label>Company Name<input name="company_name" required value="{val("company_name")}"></label><label>Contact Person<input name="contact_person" value="{val("contact_person")}"></label><label>Email<input name="email" type="email" value="{val("email")}"></label><label>Phone / WhatsApp<input name="phone" value="{val("phone")}"></label><label>Website<input name="website" value="{val("website")}"></label><label>Country<input name="country" placeholder="Leave blank to auto-detect" value="{val("country")}"></label><label>Product<input name="product" value="{val("product")}"></label><label>Buyer Type<input name="buyer_type" value="{val("buyer_type")}"></label><label>Source<input name="source" value="{val("source")}"></label><label>Email Status<select name="email_status"><option value="">Auto from email</option>{select_options(EMAIL_STATUSES,b.get("email_status",""))}</select></label><label>Stage<select name="stage">{select_options(STAGES,b.get("stage","New"))}</select></label><label>Priority<select name="priority"><option value="">Auto</option>{select_options(PRIORITIES,b.get("priority",""))}</select></label><label>Next Follow-up<input type="date" name="next_followup_date" value="{val("next_followup_date")}"></label><label class="full">Notes<textarea name="notes">{val("notes")}</textarea></label></div><button class="btn" type="submit">Save Buyer</button></form></div>'
    return layout(title,body,'add')

def buyer_detail_page(bid):
    b=get_buyer(bid)
    if not b: return error_page('Buyer not found')
    with conn() as c: acts=c.execute('SELECT * FROM activities WHERE buyer_id=? ORDER BY created_at DESC,id DESC LIMIT 30',(bid,)).fetchall(); templates=c.execute('SELECT * FROM email_templates ORDER BY updated_at DESC').fetchall()
    act_html=''.join(f'<div style="border-left:3px solid #e5e9f2;padding:8px 0 8px 12px"><strong>{esc(a["activity_type"])}</strong><br><span class="mini">{esc(a["activity_date"])} · {esc(a["created_at"])}</span><p class="hint">{esc(a["notes"])}</p></div>' for a in acts) or '<p class="hint">No activity yet.</p>'
    tpl_options=select_options([(str(t['id'])) for t in templates])
    email_buttons=[]
    for t in templates[:5]:
        url = outlook_compose_url({'buyer_id':[str(bid)], 'template_id':[str(t['id'])]})
        t_url = titan_compose_url({'buyer_id':[str(bid)], 'template_id':[str(t['id'])]})
        email_buttons.append(f'<span style="display:inline-block;margin-right:8px;margin-bottom:8px;border:1px solid #e5e9f2;padding:4px;border-radius:12px;background:#f8fafc"><a class="btn small secondary" href="{esc(url)}">Outlook · {esc(t["name"][:20])}</a> <a class="btn small ghost" href="{esc(t_url)}">Titan</a></span>')
    body=top(b['company_name'] or 'Buyer Detail',f'{b["email"] or "No email"} · {b["country"] or "Unknown"} · Score {lead_score(b)}','<a class="btn secondary" href="/buyers">Back</a><a class="btn" href="/buyer/%d/edit">Edit</a>'%bid)
    body+=f'<div class="grid two"><div class="card"><h3>Buyer Profile</h3><p>{tag_email(b["email_status"])} {tag_stage(b["stage"])} {tag_score(b)}</p><div class="table-wrap"><table><tr><th>Field</th><th>Value</th></tr><tr><td>Contact</td><td>{esc(b["contact_person"])}</td></tr><tr><td>Phone</td><td>{esc(b["phone"])}</td></tr><tr><td>Website</td><td>{esc(b["website"])}</td></tr><tr><td>Product</td><td>{esc(b["product"])} / {esc(b["product_category"])}</td></tr><tr><td>Market</td><td>{esc(b["country"])} / {esc(b["market_category"])}</td></tr><tr><td>Next Action</td><td>{esc(next_action(b))}</td></tr><tr><td>Notes</td><td>{esc(b["notes"])}</td></tr></table></div><h3>Email Templates</h3><p class="hint">Open a buyer-ready Outlook draft with recipient, subject, and message already filled in.</p><p>{" ".join(email_buttons) if email_buttons else "No templates"}</p></div><div class="card"><h3>Add Activity</h3><form method="post" action="/buyer/{bid}/action"><label>Action<select name="action">{select_options(["Email Sent","Follow-up 1 Done","Follow-up 2 Done","Follow-up 3 Done","Response Received","Quotation Sent","Negotiation Started","Closed Won","Closed Lost","Not Interested","Verified by Tool","Bounced","Unsubscribed"])}</select></label><label>Date<input type="date" name="activity_date" value="{today()}"></label><label>Next Follow-up<input type="date" name="next_followup_date" value="{(date.today()+timedelta(days=3)).isoformat()}"></label><label>Notes<textarea name="notes"></textarea></label><button class="btn" type="submit">Save Activity</button></form></div></div><div class="card" style="margin-top:16px"><h3>Activity Timeline</h3>{act_html}</div>'
    return layout('Buyer Detail',body,'buyers')


def email_draft_from_params(params):
    """Resolve a personalized email draft from a campaign recipient or buyer template."""
    to=clean(params.get('to',[''])[0])
    subject=clean(params.get('subject',[''])[0])
    body_txt=clean(params.get('body',[''])[0])
    buyer_label='Manual email'
    rid=clean(params.get('recipient_id',[''])[0])
    bid=clean(params.get('buyer_id',[''])[0])
    tid=clean(params.get('template_id',[''])[0])
    with conn() as c:
        if rid.isdigit():
            r=c.execute("""SELECT cr.*,b.company_name,b.contact_person,b.country,b.product FROM campaign_recipients cr LEFT JOIN buyers b ON b.id=cr.buyer_id WHERE cr.id=?""",(int(rid),)).fetchone()
            if r:
                to=clean(r['email'])
                subject=clean(r['subject_snapshot'])
                body_txt=clean(r['body_snapshot'])
                buyer_label=clean(r['company_name']) or clean(r['contact_person']) or to
        elif bid.isdigit() and tid.isdigit():
            b=c.execute('SELECT * FROM buyers WHERE id=?',(int(bid),)).fetchone()
            t=c.execute('SELECT * FROM email_templates WHERE id=?',(int(tid),)).fetchone()
            if b and t:
                to=clean(b['email'])
                subject=render_template(t['subject'],b)
                body_txt=render_template(t['body'],b)
                buyer_label=clean(b['company_name']) or clean(b['contact_person']) or to
    return to, subject, body_txt, buyer_label


def outlook_compose_url(params):
    """Build a MAILTO URL for the installed desktop email app (Outlook on Windows)."""
    to, subject, body_txt, _ = email_draft_from_params(params)
    # Keep the recipient in the MAILTO path and encode subject/body independently.
    # Windows sends this URI to the app registered for the MAILTO protocol.
    recipient = quote(to, safe='@,;:+')
    query = urlencode({'subject': subject, 'body': body_txt}, quote_via=quote)
    return 'mailto:' + recipient + ('?' + query if query else '')

def titan_compose_url(params):
    """Build a MAILTO URL formatted specifically for Titan email app to avoid huge gaps."""
    to, subject, body_txt, _ = email_draft_from_params(params)
    # Titan mailto handler has a bug where it interprets both \r and \n as separate HTML <br> tags.
    # To fix this, we strip \r completely and use only \n, so \n\n becomes exactly one empty line.
    body_txt = body_txt.replace('\r', '')
    body_txt = re.sub(r'\n{3,}', '\n\n', body_txt)
    recipient = quote(to, safe='@,;:+')
    query = urlencode({'subject': subject, 'body': body_txt}, quote_via=quote)
    return 'mailto:' + recipient + ('?' + query if query else '')

def render_template(text,b):
    b=dict(b) if not isinstance(b,dict) else b
    vals={'buyer_name':clean(b.get('contact_person')) or clean(b.get('company_name')) or 'there','contact_person':clean(b.get('contact_person')) or 'there','company_name':clean(b.get('company_name')) or 'your company','email':clean(b.get('email')),'country':clean(b.get('country')) if clean(b.get('country'))!='Unknown' else 'your market','market_category':clean(b.get('market_category')),'product':clean(b.get('product')) or clean(b.get('product_category')) or 'our products','product_category':clean(b.get('product_category')),'buyer_type':clean(b.get('buyer_type')) or 'importer/distributor','source':clean(b.get('source')),'today':today()}
    out=clean(text)
    for k,v in vals.items(): out=out.replace('{{'+k+'}}',v).replace('['+k+']',v)
    return out.replace('[Name]',vals['buyer_name']).replace('[Product]',vals['product']).replace('[Country]',vals['country']).replace('[Company]',vals['company_name'])

def templates_page(msg=''):
    with conn() as c: rows=c.execute('SELECT * FROM email_templates ORDER BY updated_at DESC,id DESC').fetchall()
    notice=f'<div class="success">{esc(msg)}</div>' if msg else ''
    trs=''.join(f'<tr><td><strong>{esc(r["name"])}</strong><br><span class="mini">{esc(r["category"])} · {esc(r["updated_at"])}</span></td><td>{esc(r["subject"])}</td><td><a class="btn small secondary" href="/template/{r["id"]}/edit">Edit</a> <a class="btn small ghost" href="/campaign/new?template_id={r["id"]}">Use</a></td></tr>' for r in rows)
    body=top('Email Template System','Edit templates with placeholders: {{buyer_name}}, {{company_name}}, {{product}}, {{country}}, {{today}}.','<a class="btn" href="/template/new">+ New Template</a><a class="btn secondary" href="/campaigns">Campaigns</a>')+notice+f'<div class="card"><div class="table-wrap"><table><tr><th>Template</th><th>Subject</th><th>Action</th></tr>{trs or "<tr><td colspan=3>No templates</td></tr>"}</table></div></div><div class="card" style="margin-top:16px"><h3>Placeholders</h3><p class="hint"><span class="kbd">{{buyer_name}}</span> <span class="kbd">{{company_name}}</span> <span class="kbd">{{product}}</span> <span class="kbd">{{country}}</span> <span class="kbd">{{buyer_type}}</span> <span class="kbd">{{today}}</span></p></div>'
    return layout('Templates',body,'templates')

def get_template(tid):
    with conn() as c: return c.execute('SELECT * FROM email_templates WHERE id=?',(tid,)).fetchone()

def template_form_page(t=None):
    t=dict(t) if t else {}; title='Edit Template' if t else 'New Template'; action=f'/template/{t.get("id")}/edit' if t else '/template/new'
    sample={'company_name':'ABC Imports LLC','contact_person':'Ahmed','email':'buyer@example.com','country':'United Arab Emirates','product':'Basmati Rice','product_category':'Rice','buyer_type':'Importer','source':'Embassy'}
    preview=render_template(t.get('body','Hi {{buyer_name}},\n\nWe supply {{product}} from India for {{country}}.\n\nRegards,\nSaksham'),sample)
    body=top(title,'Create/edit reusable campaign templates.','<a class="btn secondary" href="/templates">Back</a>')+f'<div class="grid two"><div class="card"><form method="post" action="{action}"><label>Name<input name="name" required value="{esc(t.get("name",""))}"></label><label>Category<input name="category" value="{esc(t.get("category","General"))}"></label><label>Subject<input name="subject" required value="{esc(t.get("subject",""))}"></label><label>Body<textarea name="body" required style="min-height:300px">{esc(t.get("body",""))}</textarea></label><button class="btn" type="submit">Save Template</button></form></div><div class="card"><h3>Sample Preview</h3><div class="template-box">{esc(preview)}</div></div></div>'
    return layout(title,body,'templates')

def campaigns_page():
    with conn() as c:
        rows=c.execute("""SELECT ca.*,et.name template_name,COUNT(cr.id) recipients,SUM(CASE WHEN cr.sent=1 THEN 1 ELSE 0 END) sent_count,SUM(CASE WHEN cr.reply_received=1 THEN 1 ELSE 0 END) reply_count FROM campaigns ca LEFT JOIN email_templates et ON et.id=ca.template_id LEFT JOIN campaign_recipients cr ON cr.campaign_id=ca.id GROUP BY ca.id ORDER BY ca.created_at DESC""").fetchall()
    trs=''.join(f'<tr><td><a href="/campaign/{r["id"]}"><strong>{esc(r["name"])}</strong></a><br><span class="mini">{esc(r["created_at"])}</span></td><td>{esc(r["template_name"] or "-")}</td><td>{r["recipients"] or 0}</td><td>{r["sent_count"] or 0}</td><td>{r["reply_count"] or 0}</td><td><a class="btn small secondary" href="/campaign/{r["id"]}">Open</a> <form method="post" action="/campaign/{r["id"]}/delete" style="display:inline" onsubmit="return confirm(\'Delete this campaign forever?\')"><button type="submit" class="btn small ghost" style="color:#dc2626;border-color:#fca5a5">Delete</button></form></td></tr>' for r in rows)
    body=top('Email Campaign Tracking','Create campaign batches, personalize each message and track sent status.','<a class="btn" href="/campaign/new">+ New Campaign</a><a class="btn secondary" href="/templates">Templates</a>')+f'<div class="card"><div class="table-wrap"><table><tr><th>Campaign</th><th>Template</th><th>Recipients</th><th>Sent</th><th>Replies</th><th>Action</th></tr>{trs or "<tr><td colspan=6>No campaigns yet.</td></tr>"}</table></div></div>'
    return layout('Campaigns',body,'campaigns')

def campaign_new_page(params=None,msg=''):
    params=params or {}; selected=clean(params.get('template_id',[''])[0]) if isinstance(params,dict) else ''
    with conn() as c:
        templates=c.execute('SELECT * FROM email_templates ORDER BY updated_at DESC').fetchall(); countries=[r[0] for r in c.execute("SELECT DISTINCT country FROM buyers WHERE country!='' ORDER BY country")]; cats=[r[0] for r in c.execute("SELECT DISTINCT product_category FROM buyers WHERE product_category!='' ORDER BY product_category")]
    tplopts=''.join(f'<option value="{t["id"]}" {"selected" if str(t["id"])==selected else ""}>{esc(t["name"])} — {esc(t["category"])}</option>' for t in templates)
    notice=f'<div class="error">{esc(msg)}</div>' if msg else ''
    body=top('Create Email Campaign','Filter verified buyers and choose template.','<a class="btn secondary" href="/campaigns">Back</a>')+notice+f'<div class="grid two"><div class="card"><form method="post" action="/campaign/new"><label>Campaign Name<input name="name" required placeholder="UAE Rice Buyers - First Email"></label><label>Template<select name="template_id" required>{tplopts}</select></label><label>Country<select name="country"><option value="">Any country</option>{select_options(countries)}</select></label><label>Product Category<select name="product_category"><option value="">Any product</option>{select_options(cats)}</select></label><label>Stage<select name="stage"><option value="">Any stage</option>{select_options(STAGES)}</select></label><label><input style="width:auto" type="checkbox" name="valid_only" value="1" checked> Only Valid/Verified emails</label><label>Maximum Recipients<input type="number" name="limit" min="1" max="5000" value="200"></label><button class="btn" type="submit">Create Campaign</button></form></div><div class="card"><h3>How it works</h3><ol class="hint"><li>CRM creates recipient list from your filters.</li><li>Subject/body are personalized by buyer.</li><li>Click Open Outlook App or Copy Message.</li><li>After sending, bulk mark as sent to update follow-ups.</li></ol></div></div>'
    return layout('New Campaign',body,'campaigns')

def create_campaign(data):
    name=clean(data.get('name')); tid=int(data.get('template_id') or 0); tpl=get_template(tid); limit=max(1,min(5000,int(data.get('limit') or 200)))
    if not name or not tpl: return None,0
    country=clean(data.get('country')); cat=clean(data.get('product_category')); stage=clean(data.get('stage')); valid_only=clean(data.get('valid_only'))=='1'
    sql="SELECT * FROM buyers WHERE email IS NOT NULL AND email!=''"; vals=[]
    if valid_only: sql+=" AND email_status IN ('Valid Format','Verified by Tool')"
    if country: sql+=' AND country=?'; vals.append(country)
    if cat: sql+=' AND product_category=?'; vals.append(cat)
    if stage: sql+=' AND stage=?'; vals.append(stage)
    sql+=" AND stage NOT IN ('Closed Lost','Not Interested') ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, updated_at DESC LIMIT ?"; vals.append(limit)
    n=now(); seg=f"country={country or 'Any'}, product={cat or 'Any'}, stage={stage or 'Any'}, valid_only={valid_only}"
    with conn() as c:
        buyers=c.execute(sql,vals).fetchall(); c.execute('INSERT INTO campaigns(name,template_id,segment_note,created_at,updated_at) VALUES(?,?,?,?,?)',(name,tid,seg,n,n)); cid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
        for b in buyers: c.execute('INSERT OR IGNORE INTO campaign_recipients(campaign_id,buyer_id,email,subject_snapshot,body_snapshot,created_at) VALUES(?,?,?,?,?,?)',(cid,b['id'],b['email'],render_template(tpl['subject'],b),render_template(tpl['body'],b),n))
        c.commit()
    return cid,len(buyers)

def campaign_detail_page(cid,msg=''):
    with conn() as c:
        camp=c.execute('SELECT ca.*,et.name template_name FROM campaigns ca LEFT JOIN email_templates et ON et.id=ca.template_id WHERE ca.id=?',(cid,)).fetchone()
        if not camp: return error_page('Campaign not found')
        recs=c.execute('SELECT cr.*,b.company_name,b.contact_person,b.country,b.product,b.stage,b.email_status,b.priority FROM campaign_recipients cr JOIN buyers b ON b.id=cr.buyer_id WHERE cr.campaign_id=? ORDER BY cr.sent ASC,b.priority ASC,cr.id DESC',(cid,)).fetchall()
    notice=f'<div class="success">{esc(msg)}</div>' if msg else ''; sent=sum(1 for r in recs if r['sent']); trs=[]
    for r in recs:
        mid=f'msg{r["id"]}'
        mail = outlook_compose_url({'recipient_id':[str(r['id'])]})
        t_mail = titan_compose_url({'recipient_id':[str(r['id'])]})
        status_badge = '<span class=pill>Pending</span>' if not r["sent"] else '<span class="pill green">Sent</span>'
        trs.append(f'<tr><td><input class="big-checkbox" type="checkbox" name="recipient_ids" value="{r["id"]}"></td><td><strong>{esc(r["company_name"])}</strong><br><span class="mini">{esc(r["contact_person"])} - {esc(r["email"])}</span><br>{status_badge}</td><td>{esc(r["country"])}<br><span class="mini">{esc(r["product"])}</span></td><td><strong>{esc(r["subject_snapshot"])}</strong><details><summary class="mini">Preview message</summary><div id="{mid}" class="template-box" style="margin-top:8px">{esc(r["body_snapshot"])}</div><button class="btn small secondary" type="button" onclick="copyText(\'{mid}\')">Copy Message</button></details></td><td><a class="btn small secondary" href="{esc(mail)}" style="margin-bottom:4px;display:block;text-align:center">Outlook</a><a class="btn small ghost" href="{esc(t_mail)}" style="display:block;text-align:center">Titan</a><br><span class="mini">Sent on: {esc(r["sent_on"] or "-")}</span></td></tr>')
    body=top('Campaign: '+camp['name'],f'Template: {camp["template_name"] or "-"} · Recipients: {len(recs)} · Sent: {sent} · {camp["segment_note"] or ""}','<a class="btn secondary" href="/campaigns">Campaigns</a>')+notice+f'<div class="grid stats"><div class="card stat"><div class="label">Recipients</div><div class="num">{len(recs)}</div></div><div class="card stat good"><div class="label">Sent</div><div class="num">{sent}</div></div><div class="card stat warn"><div class="label">Pending</div><div class="num">{len(recs)-sent}</div></div><div class="card stat blue"><div class="label">Campaign ID</div><div class="num">#{cid}</div></div></div><form method="post" action="/campaign/{cid}/mark-sent"><div class="card" style="margin-bottom:12px"><div class="form-grid"><label>Activity Date<input type="date" name="activity_date" value="{today()}"></label><label>Next Follow-up<input type="date" name="next_followup_date" value="{(date.today()+timedelta(days=3)).isoformat()}"></label><label class="full">Notes<textarea name="notes" placeholder="Campaign email sent from Outlook desktop app"></textarea></label></div><button class="btn" type="submit">Mark Selected Sent</button> <button class="btn secondary" name="mark_all_pending" value="1" type="submit">Mark All Pending Sent</button></div><div class="table-wrap"><table><tr><th>Select<br><input class="big-checkbox" type="checkbox" onclick="document.querySelectorAll(\'input[name=recipient_ids]\').forEach(cb=>cb.checked=this.checked)"></th><th>Buyer</th><th>Segment</th><th>Personalized Email</th><th>Action</th></tr>{"".join(trs) or "<tr><td colspan=5>No recipients</td></tr>"}</table></div></form>'
    return layout('Campaign Detail',body,'campaigns')

def mark_campaign_sent(cid, params):
    ids=params.get('recipient_ids',[]); mark_all=clean(params.get('mark_all_pending',[''])[0])=='1'; activity_date=clean(params.get('activity_date',[''])[0]) or today(); nextf=clean(params.get('next_followup_date',[''])[0]); notes=clean(params.get('notes',[''])[0]) or 'Campaign email marked sent'
    with conn() as c:
        if mark_all or not ids: recs=c.execute('SELECT * FROM campaign_recipients WHERE campaign_id=? AND sent=0',(cid,)).fetchall()
        else:
            clean_ids=[int(x) for x in ids if str(x).isdigit()]
            if not clean_ids: return 0
            recs=c.execute(f'SELECT * FROM campaign_recipients WHERE campaign_id=? AND id IN ({",".join("?" for _ in clean_ids)})',[cid]+clean_ids).fetchall()
        count=0
        for r in recs:
            c.execute('UPDATE campaign_recipients SET sent=1,sent_on=?,notes=? WHERE id=?',(activity_date,notes,r['id']))
            bid=r['buyer_id']; b=c.execute('SELECT * FROM buyers WHERE id=?',(bid,)).fetchone(); n=now(); base=safe_date(activity_date) or date.today()
            updates={'stage':'Contacted','last_email_sent_on':activity_date,'next_followup_date':nextf or (base+timedelta(days=3)).isoformat(),'updated_at':n}
            if b and not b['first_email_sent_on']: updates['first_email_sent_on']=activity_date
            c.execute(f"UPDATE buyers SET {', '.join(k+'=?' for k in updates)} WHERE id=?",list(updates.values())+[bid])
            c.execute('INSERT INTO activities(buyer_id,activity_type,activity_date,notes,created_at) VALUES(?,?,?,?,?)',(bid,'Email Sent',activity_date,'Campaign #'+str(cid)+': '+notes,n)); count+=1
        c.execute('UPDATE campaigns SET updated_at=? WHERE id=?',(now(),cid)); c.commit(); return count

def smart_followups_page():
    t=today(); seven=(date.today()-timedelta(days=7)).isoformat()
    with conn() as c:
        overdue=c.execute("SELECT * FROM buyers WHERE next_followup_date!='' AND next_followup_date<? AND stage NOT IN ('Closed Won','Closed Lost','Not Interested') ORDER BY next_followup_date ASC LIMIT 100",(t,)).fetchall()
        due=c.execute("SELECT * FROM buyers WHERE next_followup_date=? AND stage NOT IN ('Closed Won','Closed Lost','Not Interested') ORDER BY priority ASC LIMIT 100",(t,)).fetchall()
        no_reply=c.execute("SELECT * FROM buyers WHERE last_email_sent_on!='' AND last_email_sent_on<=? AND response_received=0 AND stage NOT IN ('Closed Won','Closed Lost','Not Interested') ORDER BY last_email_sent_on ASC LIMIT 100",(seven,)).fetchall()
        quotation=c.execute("SELECT * FROM buyers WHERE stage='Quotation' ORDER BY updated_at ASC LIMIT 100").fetchall(); openrows=c.execute("SELECT * FROM buyers WHERE stage NOT IN ('Closed Lost','Not Interested')").fetchall()
    hot=sorted([r for r in openrows if lead_score(r)>=75], key=lambda r:lead_score(r), reverse=True)[:50]
    body=top('Smart Follow-up Reminder Dashboard','Daily work mode: overdue, due today, hot leads, no-reply, and quotation waiting.','<a class="btn" href="/buyers?due=1">Open Due Buyers</a><a class="btn secondary" href="/export/followups-csv">Export Tasks</a>')+f'<div class="grid stats"><div class="card stat warn"><div class="label">Overdue</div><div class="num">{len(overdue)}</div></div><div class="card stat blue"><div class="label">Due Today</div><div class="num">{len(due)}</div></div><div class="card stat good"><div class="label">Hot Leads 75+</div><div class="num">{len(hot)}</div></div><div class="card stat"><div class="label">No Reply 7+ Days</div><div class="num">{len(no_reply)}</div></div></div><div class="grid two"><div class="card"><h3>Overdue</h3>{rows_table(overdue,compact=True)}</div><div class="card"><h3>Due Today</h3>{rows_table(due,compact=True)}</div></div><div class="grid two" style="margin-top:16px"><div class="card"><h3>Hot Leads</h3>{rows_table(hot,compact=True)}</div><div class="card"><h3>No Reply After 7 Days</h3>{rows_table(no_reply,compact=True)}</div></div><div class="card" style="margin-top:16px"><h3>Quotation Waiting</h3>{rows_table(quotation,compact=True)}</div>'
    return layout('Smart Follow-ups',body,'smart')

def kanban_page():
    with conn() as c: rows=c.execute('SELECT * FROM buyers ORDER BY updated_at DESC').fetchall()
    lanes=[]
    for st in STAGES:
        cards=''
        for b in rows:
            if (b['stage'] or 'New')==st: cards+=f'<div class="lead-card"><strong>{esc(b["company_name"] or "Unnamed")}</strong><br><span class="mini">{esc(b["country"])} · {esc(b["product"])} · Score {lead_score(b)}</span><br><a href="/buyer/{b["id"]}">Open</a></div>'
        lanes.append(f'<div class="lane"><h3>{esc(st)}</h3>{cards or "<p class=hint>No leads</p>"}</div>')
    return layout('Kanban', top('Kanban Board','Visual pipeline stages.','<a class="btn secondary" href="/buyers">Table View</a>')+'<div class="kanban">'+''.join(lanes)+'</div>','kanban')

def data_quality_page():
    with conn() as c:
        total=c.execute('SELECT COUNT(*) FROM buyers').fetchone()[0]; invalid=c.execute("SELECT COUNT(*) FROM buyers WHERE email_status IN ('Invalid Format','Bounced') OR email='' OR email IS NULL").fetchone()[0]; unknown=c.execute("SELECT COUNT(*) FROM buyers WHERE country='' OR country='Unknown' OR country IS NULL").fetchone()[0]; missing=c.execute("SELECT COUNT(*) FROM buyers WHERE product='' OR product IS NULL OR product_category='General Importer'").fetchone()[0]
        problem=c.execute("SELECT * FROM buyers WHERE email_status IN ('Invalid Format','Bounced','Risky/Needs Verification') OR country='Unknown' OR product_category='General Importer' OR email='' OR email IS NULL ORDER BY updated_at DESC LIMIT 100").fetchall()
    clean_score=round(((total-invalid-unknown-missing)/total*100),1) if total else 0
    body=top('Data Quality Center','Clean data before campaigns.','<a class="btn secondary" href="/export/valid-csv">Export Valid Leads</a><a class="btn secondary" href="/backup.zip">Backup ZIP</a>')+f'<div class="grid stats"><div class="card stat"><div class="label">Clean Score</div><div class="num">{clean_score}%</div></div><div class="card stat warn"><div class="label">Invalid/Risky</div><div class="num">{invalid}</div></div><div class="card stat blue"><div class="label">Unknown Country</div><div class="num">{unknown}</div></div><div class="card stat"><div class="label">Missing Product</div><div class="num">{missing}</div></div></div><div class="card"><h3>Problem Records</h3>{rows_table(problem)}</div>'
    return layout('Data Quality',body,'quality')

def import_page(msg=''):
    notice=f'<div class="success">{esc(msg)}</div>' if msg else ''
    body=top('Import Buyer Data','Upload CSV/XLSX. CRM auto-maps columns, country/product, and email validation status.','<a class="btn secondary" href="/sample-template.csv">CSV Template</a><a class="btn secondary" href="/sample-template.xlsx">Excel Template</a>')+notice+f'<div class="card"><form method="post" action="/import" enctype="multipart/form-data"><label>Upload file<input type="file" name="file" accept=".csv,.xlsx" required></label><p class="hint">Supported validation headers: Email Status, Email Validation, Verification, ZeroBounce Status, NeverBounce Status, Deliverability, SMTP Status.</p><button class="btn" type="submit">Import Data</button></form></div><div class="grid two" style="margin-top:16px"><div class="card"><h3>Email Validation Import</h3><p class="hint">Valid/Deliverable/Verified becomes Verified by Tool. Invalid/Undeliverable becomes Invalid Format. Catch-all/Unknown/Risky becomes Risky/Needs Verification. Bounced/Unsubscribed are recognized too.</p></div><div class="card"><h3>Smart Import</h3><p class="hint">Duplicate email rows are skipped safely; imported verifier status can update existing leads.</p></div></div>'
    return layout('Import',body,'import')

def map_columns(headers):
    n={norm_header(h):h for h in headers}; out={}
    for target,aliases in HEADER_MAP.items():
        for a in aliases:
            if a in n: out[target]=n[a]; break
        if target not in out:
            for nh,orig in n.items():
                if any(a in nh for a in aliases): out[target]=orig; break
    return out

def parse_csv_file(path):
    with open(path,'r',encoding='utf-8-sig',newline='') as f: return [{clean(k):clean(v) for k,v in r.items()} for r in csv.DictReader(f)]

def col_num(ref):
    letters=''.join(ch for ch in ref if ch.isalpha()); n=0
    for ch in letters: n=n*26+ord(ch.upper())-64
    return n

def parse_xlsx_file(path):
    ns={'a':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','rel':'http://schemas.openxmlformats.org/package/2006/relationships'}
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall('a:si',ns): shared.append(''.join(t.text or '' for t in si.findall('.//a:t',ns)))
        sheet='xl/worksheets/sheet1.xml'; root=ET.fromstring(z.read(sheet)); grid=[]
        for row in root.findall('.//a:sheetData/a:row',ns):
            vals={}
            for cell in row.findall('a:c',ns):
                ref=cell.attrib.get('r',''); col=col_num(ref) if ref else len(vals)+1; typ=cell.attrib.get('t'); val=''
                if typ=='inlineStr': val=''.join(t.text or '' for t in cell.findall('.//a:t',ns))
                else:
                    v=cell.find('a:v',ns)
                    if v is not None and v.text is not None:
                        val=v.text
                        if typ=='s':
                            try: val=shared[int(val)]
                            except Exception: pass
                vals[col]=val
            if vals: grid.append([vals.get(i,'') for i in range(1,max(vals)+1)])
    if not grid: return []
    headers=[clean(x) for x in grid[0]]; rows=[]
    for r in grid[1:]:
        if any(clean(x) for x in r): rows.append({headers[i]:clean(r[i]) if i<len(r) else '' for i in range(len(headers))})
    return rows

def import_rows(rows):
    if not rows: return Counter({'inserted':0,'duplicate':0,'skipped':0,'updated':0,'validation_updated':0})
    mapped=map_columns(list(rows[0].keys())); counts=Counter()
    for r in rows:
        norm={target:r.get(src,'') for target,src in mapped.items()}
        for h,v in r.items():
            nh=norm_header(h)
            if not norm.get('email_status') and any(k in nh for k in ['validation','verification','zerobounce','neverbounce','hunter','deliverability','smtp status','status']): norm['email_status']=normalize_email_status(v)
        if norm.get('email_status'): norm['email_status']=normalize_email_status(norm.get('email_status')); counts['validation_updated']+=1
        if not (clean(norm.get('company_name')) or clean(norm.get('email'))): counts['skipped']+=1; continue
        counts[insert_buyer(norm)]+=1
    return counts

def form_params(body): return parse_qs(body.decode('utf-8',errors='ignore'),keep_blank_values=True)
def form_dict(body): return {k:v[0] for k,v in form_params(body).items()}

def parse_multipart(handler):
    ctype=handler.headers.get('Content-Type',''); m=re.search(r'boundary=(?:"([^"]+)"|([^;]+))',ctype)
    if 'multipart/form-data' not in ctype or not m: return None,None
    boundary=(m.group(1) or m.group(2)).encode(); body=handler.rfile.read(int(handler.headers.get('Content-Length',0)))
    for part in body.split(b'--'+boundary):
        part=part.strip(b'\r\n')
        if not part or part==b'--' or b'\r\n\r\n' not in part: continue
        head,content=part.split(b'\r\n\r\n',1); head=head.decode('utf-8',errors='ignore')
        if 'name="file"' not in head: continue
        fm=re.search(r'filename="([^"]*)"',head)
        if not fm or not fm.group(1): return None,None
        filename=os.path.basename(fm.group(1)).replace(' ','_')
        if content.endswith(b'\r\n'): content=content[:-2]
        save=os.path.join(UPLOAD_DIR,datetime.now().strftime('%Y%m%d_%H%M%S_')+filename)
        with open(save,'wb') as f: f.write(content)
        return save,filename
    return None,None

def bulk_apply(params):
    ids=[int(x) for x in params.get('buyer_ids',[]) if str(x).isdigit()]; action=params.get('bulk_action',[''])[0]; activity_date=params.get('activity_date',[today()])[0] or today(); nextf=params.get('next_followup_date',[''])[0]; notes=params.get('notes',[''])[0]; count=0
    for bid in ids:
        if action and action!='Bulk Edit Selected Fields': add_activity(bid,action,activity_date,notes or 'Bulk action: '+action,nextf); count+=1
        updates={}
        for key in ['stage','email_status','priority','buyer_type']:
            val=clean(params.get(key,[''])[0])
            if val: updates[key]=val
        country=clean(params.get('country',[''])[0]); product=clean(params.get('product',[''])[0])
        b=get_buyer(bid)
        if country: ctry=recognize_country({'country':country}); updates['country']=ctry; updates['market_category']=market_cat(ctry)
        if product: updates['product']=product; updates['product_category']=product_cat(product, b['notes'] if b else '')
        if notes and action=='Bulk Edit Selected Fields': updates['notes']=((b['notes'] or '')+'\n'+notes).strip() if b else notes
        if nextf and action=='Bulk Edit Selected Fields': updates['next_followup_date']=nextf
        if updates:
            updates['updated_at']=now()
            with conn() as c:
                c.execute(f"UPDATE buyers SET {', '.join(k+'=?' for k in updates)} WHERE id=?",list(updates.values())+[bid]); c.execute('INSERT INTO activities(buyer_id,activity_type,activity_date,notes,created_at) VALUES(?,?,?,?,?)',(bid,'Bulk Edited',activity_date,notes or 'Bulk fields updated',now())); c.commit(); count+=1
    return count

def send_bytes(h,filename,data,ctype):
    h.send_response(200); h.send_header('Content-Type',ctype); h.send_header('Content-Disposition',f'attachment; filename="{filename}"'); h.send_header('Content-Length',str(len(data))); h.end_headers(); h.wfile.write(data)

def csv_bytes(headers, rows):
    out=io.StringIO(); w=csv.writer(out); w.writerow(headers); [w.writerow(r) for r in rows]; return out.getvalue().encode('utf-8-sig')

def col_letters(n):
    s=''
    while n: n,rem=divmod(n-1,26); s=chr(65+rem)+s
    return s

def write_xlsx(headers, rows):
    def xe(v): return html.escape('' if v is None else str(v), quote=False)
    sr=[]
    for ri,row in enumerate([headers]+rows,1):
        cells=''.join(f'<c r="{col_letters(ci)}{ri}" t="inlineStr"><is><t>{xe(v)}</t></is></c>' for ci,v in enumerate(row,1)); sr.append(f'<row r="{ri}">{cells}</row>')
    sheet=f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sr)}</sheetData></worksheet>'
    files={'[Content_Types].xml':'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>','_rels/.rels':'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>','xl/workbook.xml':'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Buyers" sheetId="1" r:id="rId1"/></sheets></workbook>','xl/_rels/workbook.xml.rels':'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>','xl/worksheets/sheet1.xml':sheet}
    bio=io.BytesIO();
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        for n,c in files.items(): z.writestr(n,c)
    return bio.getvalue()

def buyer_rows(valid_only=False, followups=False):
    rows=[]
    for b in all_buyers():
        if valid_only and not (b['email_status'] in ['Valid Format','Verified by Tool'] and b['email'] and b['stage'] not in ['Closed Lost','Not Interested']): continue
        if followups and not b['next_followup_date']: continue
        rows.append([b['id'],b['company_name'],b['contact_person'],b['email'],b['phone'],b['website'],b['country'],b['market_category'],b['product'],b['product_category'],b['buyer_type'],b['source'],b['email_status'],b['priority'],b['stage'],lead_score(b),next_action(b),b['first_email_sent_on'],b['last_email_sent_on'],'Yes' if b['response_received'] else 'No',b['response_date'],'Yes' if b['followup1_done'] else 'No',b['followup1_date'],'Yes' if b['followup2_done'] else 'No',b['followup2_date'],'Yes' if b['followup3_done'] else 'No',b['followup3_date'],b['next_followup_date'],b['notes'],b['created_at'],b['updated_at']])
    return rows

def make_pdf(title, lines):
    objs=[]
    def add(o): objs.append(o); return len(objs)
    cat=add(''); pages=add(''); font=add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'); pids=[]
    chunks=[lines[i:i+42] for i in range(0,len(lines),42)] or [['No data']]
    for chunk in chunks:
        cmds=[f'BT /F1 18 Tf 50 790 Td ({pdfesc(title[:80])}) Tj ET']; y=760
        for line in chunk: cmds.append(f'BT /F1 10 Tf 50 {y} Td ({pdfesc(str(line)[:115])}) Tj ET'); y-=16
        stream='\n'.join(cmds); cont=add(f'<< /Length {len(stream.encode("latin-1",errors="ignore"))} >>\nstream\n{stream}\nendstream'); pid=add(f'<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {cont} 0 R >>'); pids.append(pid)
    objs[cat-1]=f'<< /Type /Catalog /Pages {pages} 0 R >>'; objs[pages-1]=f'<< /Type /Pages /Kids [{" ".join(str(x)+" 0 R" for x in pids)}] /Count {len(pids)} >>'
    data=b'%PDF-1.4\n'; offs=[0]
    for i,o in enumerate(objs,1): offs.append(len(data)); data+=f'{i} 0 obj\n{o}\nendobj\n'.encode('latin-1',errors='ignore')
    xref=len(data); data+=f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n'.encode();
    for off in offs[1:]: data+=f'{off:010d} 00000 n \n'.encode()
    data+=f'trailer\n<< /Size {len(objs)+1} /Root {cat} 0 R >>\nstartxref\n{xref}\n%%EOF'.encode(); return data

def pdfesc(t): return str(t).replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
def report_pdf():
    s=stats(); lines=[f'Generated on: {now()}',f'Total buyers: {s["total"]}',f'Campaigns: {s["campaigns"]}',f'Contacted: {s["contacted"]}',f'Replies: {s["replied"]}',f'Follow-ups due: {s["due"]}',f'Invalid/Bounced/Unsubscribed: {s["invalid"]}','','Pipeline by stage:']
    for r in s['stages']: lines.append(f'- {r["stage"] or "New"}: {r["c"]}')
    lines.append(''); lines.append('Top countries:')
    for r in s['countries']: lines.append(f'- {r["country"] or "Unknown"}: {r["c"]}')
    return make_pdf('Export Import CRM Report', lines)

def backup_zip():
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DB_PATH): z.write(DB_PATH,'export_import_crm.sqlite')
        z.writestr('exports/export_import_buyers.csv', csv_bytes(EXPORT_HEADERS,buyer_rows()))
        z.writestr('exports/valid_leads.csv', csv_bytes(EXPORT_HEADERS,buyer_rows(valid_only=True)))
        z.writestr('reports/export_import_crm_report.pdf', report_pdf())
        z.writestr('README_BACKUP.txt','Smart Export CRM V7 backup: includes SQLite database, exports, report, templates and campaigns. Restore using Backup & Restore page.')
    return bio.getvalue()

def backup_restore_page(msg=''):
    notice=f'<div class="success">{esc(msg)}</div>' if msg else ''
    body=top('Backup & Restore','Download backup ZIP or restore previous SQLite CRM database safely.','<a class="btn" href="/backup.zip">Download Backup ZIP</a>')+notice+f'<div class="grid two"><div class="card"><h3>Backup</h3><p class="hint">Backup includes database, buyer CSV, valid leads CSV and PDF report.</p><a class="btn" href="/backup.zip">Download Backup ZIP</a></div><div class="card"><h3>Restore</h3><form method="post" action="/restore" enctype="multipart/form-data"><label>Backup ZIP<input type="file" name="file" accept=".zip" required></label><button class="btn danger" onclick="return confirm(\'This will replace current database after a safety copy. Continue?\')">Restore Backup</button></form><p class="hint">A safety copy is saved inside backups folder before restore.</p></div></div>'
    return layout('Backup Restore',body,'backup')

def restore_backup(path):
    if not path or not path.lower().endswith('.zip'): return 'Please upload a ZIP backup file.'
    try:
        with zipfile.ZipFile(path) as z:
            dbname=next((n for n in z.namelist() if os.path.basename(n)=='export_import_crm.sqlite'),None)
            if not dbname: return 'Backup ZIP does not contain export_import_crm.sqlite.'
            tmp=os.path.join(BACKUP_DIR,'restore_check_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite')
            with open(tmp,'wb') as f: f.write(z.read(dbname))
        t=sqlite3.connect(tmp); t.execute('SELECT COUNT(*) FROM buyers').fetchone(); t.close()
        if os.path.exists(DB_PATH): shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR,'safety_before_restore_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite'))
        shutil.copy2(tmp,DB_PATH); init_db(); return 'Restore complete. Restart app if old data still appears.'
    except Exception as e: return 'Restore failed: '+str(e)

def sample_rows(): return [['ABC Imports LLC','Ahmed Khan','buyer@example.com','+971500000000','https://example.com','UAE','Basmati Rice','Embassy UAE','Dubai','Importer','Valid','Sample row']]
def error_page(msg): return layout('Error', top('Something went wrong', msg)+f'<div class="error">{esc(msg)}</div>','')

class CRMHandler(BaseHTTPRequestHandler):
    def check_auth(self):
        auth_header = self.headers.get('Authorization')
        expected = "Basic " + base64.b64encode(b"info@sheshaanglobal.com:Sana@200908").decode("utf-8")
        if auth_header == expected:
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="CRM Login"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Unauthorized. Please login with your credentials.')
        return False

    def send_html(self, content, code=200):
        data = content.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, path):
        self.send_response(303)
        self.send_header('Location', path)
        self.end_headers()

    def do_GET(self):
        if not self.check_auth():
            return
        p = urlparse(self.path)
        path = p.path
        params = parse_qs(p.query)
        try:
            if path == '/': self.send_html(dashboard_page())
            elif path == '/version': self.send_html(layout('Outlook Desktop Active', top('Outlook Desktop Active', f'You are running Smart Export CRM V7.2 on port {PORT}.', '<a class="btn" href="/">Dashboard</a>') + '<div class="card good"><h2>Outlook desktop integration is active</h2><p>Email buttons now use the Windows MAILTO protocol to open the installed Outlook app with To, Subject and Message pre-filled. Outlook Web is not used.</p><p class="hint">If another mail app opens, set Microsoft Outlook as the Windows default for MAILTO.</p></div>', ''))
            elif path == '/smart-followups': self.send_html(smart_followups_page())
            elif path == '/buyers': self.send_html(buyers_page(params))
            elif path == '/buyer/new': self.send_html(buyer_form_page())
            elif re.match(r'^/buyer/\d+$', path): self.send_html(buyer_detail_page(int(path.split('/')[2])))
            elif re.match(r'^/buyer/\d+/edit$', path): self.send_html(buyer_form_page(get_buyer(int(path.split('/')[2]))))
            elif path == '/templates': self.send_html(templates_page())
            elif path == '/template/new': self.send_html(template_form_page())
            elif re.match(r'^/template/\d+/edit$', path): self.send_html(template_form_page(get_template(int(path.split('/')[2]))))
            elif path == '/outlook-compose': self.redirect(outlook_compose_url(params))
            elif path == '/titan-compose': self.redirect(titan_compose_url(params))
            elif path == '/campaigns': self.send_html(campaigns_page())
            elif path == '/campaign/new': self.send_html(campaign_new_page(params))
            elif re.match(r'^/campaign/\d+$', path): self.send_html(campaign_detail_page(int(path.split('/')[2])))
            elif path == '/kanban': self.send_html(kanban_page())
            elif path == '/data-quality': self.send_html(data_quality_page())
            elif path == '/import': self.send_html(import_page())
            elif path == '/backup-restore': self.send_html(backup_restore_page())
            elif path == '/export/csv': send_bytes(self, 'export_import_buyers.csv', csv_bytes(EXPORT_HEADERS, buyer_rows()), 'text/csv; charset=utf-8')
            elif path == '/export/valid-csv': send_bytes(self, 'valid_verified_leads.csv', csv_bytes(EXPORT_HEADERS, buyer_rows(valid_only=True)), 'text/csv; charset=utf-8')
            elif path == '/export/followups-csv': send_bytes(self, 'followup_tasks.csv', csv_bytes(EXPORT_HEADERS, buyer_rows(followups=True)), 'text/csv; charset=utf-8')
            elif path == '/export/xlsx': send_bytes(self, 'export_import_buyers.xlsx', write_xlsx(EXPORT_HEADERS, buyer_rows()), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            elif path == '/report/pdf': send_bytes(self, 'export_import_crm_report.pdf', report_pdf(), 'application/pdf')
            elif path == '/backup.zip': send_bytes(self, 'smart_export_crm_v7_backup.zip', backup_zip(), 'application/zip')
            elif path == '/sample-template.csv': send_bytes(self, 'sample_import_template.csv', csv_bytes(IMPORT_FIELDS, sample_rows()), 'text/csv; charset=utf-8')
            elif path == '/sample-template.xlsx': send_bytes(self, 'sample_import_template.xlsx', write_xlsx(IMPORT_FIELDS, sample_rows()), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            else: self.send_html(error_page('Page not found'), 404)
        except Exception as e:
            self.send_html(error_page(str(e)), 500)

    def do_POST(self):
        if not self.check_auth():
            return
        p = urlparse(self.path)
        path = p.path
        try:
            if path == '/buyer/new':
                data = form_dict(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                insert_buyer(data)
                self.redirect('/buyers')
            elif re.match(r'^/buyer/\d+/edit$', path):
                bid = int(path.split('/')[2])
                data = form_dict(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                update_buyer(bid, data)
                self.redirect(f'/buyer/{bid}')
            elif re.match(r'^/buyer/\d+/action$', path):
                bid = int(path.split('/')[2])
                data = form_dict(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                add_activity(bid, data.get('action'), data.get('activity_date') or today(), data.get('notes', ''), data.get('next_followup_date', ''))
                self.redirect(f'/buyer/{bid}')
            elif path == '/bulk-action':
                params = form_params(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                bulk_apply(params)
                self.redirect('/buyers#bulk-editor')
            elif path == '/template/new':
                data = form_dict(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                n = now()
                with conn() as c:
                    c.execute('INSERT INTO email_templates(name,subject,body,category,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', (clean(data.get('name')), clean(data.get('subject')), clean(data.get('body')), clean(data.get('category')) or 'General', 0, n, n))
                    c.commit()
                self.redirect('/templates')
            elif re.match(r'^/template/\d+/edit$', path):
                tid = int(path.split('/')[2])
                data = form_dict(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                with conn() as c:
                    c.execute('UPDATE email_templates SET name=?, subject=?, body=?, category=?, updated_at=? WHERE id=?', (clean(data.get('name')), clean(data.get('subject')), clean(data.get('body')), clean(data.get('category')) or 'General', now(), tid))
                    c.commit()
                self.redirect('/templates')
            elif path == '/campaign/new':
                data = form_dict(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                cid, count = create_campaign(data)
                if not cid:
                    self.send_html(campaign_new_page({}, 'Could not create campaign. Please add buyers and choose a template.'))
                else:
                    self.redirect(f'/campaign/{cid}')
            elif re.match(r'^/campaign/\d+/mark-sent$', path):
                cid = int(path.split('/')[2])
                params = form_params(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                count = mark_campaign_sent(cid, params)
                self.send_html(campaign_detail_page(cid, f'{count} recipients marked as sent. Buyer follow-up dates updated.'))
            elif re.match(r'^/campaign/\d+/delete$', path):
                cid = int(path.split('/')[2])
                with conn() as c:
                    c.execute('DELETE FROM campaigns WHERE id=?', (cid,))
                    c.execute('DELETE FROM campaign_recipients WHERE campaign_id=?', (cid,))
                    c.commit()
                self.redirect('/campaigns')
            elif path == '/import':
                save, filename = parse_multipart(self)
                if not save:
                    self.send_html(import_page('No file received.'))
                    return
                if save.lower().endswith('.csv'):
                    rows = parse_csv_file(save)
                elif save.lower().endswith('.xlsx'):
                    rows = parse_xlsx_file(save)
                else:
                    self.send_html(import_page('Only CSV and XLSX files are supported.'))
                    return
                counts = import_rows(rows)
                msg = f"Import complete: {counts.get('inserted',0)} inserted, {counts.get('updated',0)} updated, {counts.get('duplicate',0)} duplicates skipped, {counts.get('skipped',0)} empty rows skipped, {counts.get('validation_updated',0)} rows carried validation status."
                self.send_html(import_page(msg))
            elif path == '/restore':
                save, filename = parse_multipart(self)
                msg = restore_backup(save)
                self.send_html(backup_restore_page(msg))
            else:
                self.send_html(error_page('Page not found'), 404)
        except Exception as e:
            self.send_html(error_page(str(e)), 500)


def open_browser():
    try:
        display_host = "127.0.0.1" if HOST == "0.0.0.0" else HOST
        webbrowser.open(f'http://{display_host}:{PORT}')
    except Exception:
        pass


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), CRMHandler)
    display_host = "127.0.0.1" if HOST == "0.0.0.0" else HOST
    print('\nSmart Export CRM V7.2 - OUTLOOK DESKTOP APP is running')
    print(f'Open: http://{display_host}:{PORT}')
    print('Database file:', DB_PATH)
    print('Press CTRL+C to stop.\n')
    threading.Timer(1.0, open_browser).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nCRM stopped.')

if __name__ == '__main__':
    main()
