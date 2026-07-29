import os
import re
import sys
import base64
import email
import hmac
import hashlib
from urllib.parse import parse_qs, quote

# Add root folder to Python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import app as crm_app

_db_initialized = False

def ensure_db():
    global _db_initialized
    if not _db_initialized:
        crm_app.init_db()
        _db_initialized = True

def parse_multipart_payload(content_type, body_bytes):
    try:
        msg_input = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body_bytes
        msg = email.message_from_bytes(msg_input)
        for part in msg.walk():
            if part.get_content_disposition() == 'form-data' and part.get_param('name') == 'file':
                filename = part.get_filename()
                file_payload = part.get_payload(decode=True)
                return file_payload, filename
    except Exception:
        pass
    return None, None

def application(environ, start_response):
    # 1. Extract Path, Method and Query Parameters
    path = environ.get('PATH_INFO', '/')
    if path == '/api/index.py':
        path = '/'
    elif path.startswith('/api/index.py/'):
        path = path[len('/api/index.py'):]
    method = environ.get('REQUEST_METHOD', 'GET').upper()
    query_string = environ.get('QUERY_STRING', '')
    params = parse_qs(query_string)

    # 2. Read POST Body
    try:
        content_length = int(environ.get('CONTENT_LENGTH', 0))
    except ValueError:
        content_length = 0
    body_bytes = environ['wsgi.input'].read(content_length)

    def form_params(body):
        return parse_qs(body.decode('utf-8', errors='ignore'), keep_blank_values=True)
    def form_dict(body):
        return {k: v[0] for k, v in form_params(body).items()}

    # Helper response generators
    def html_response(html_content, status_code='200 OK'):
        data = html_content.encode('utf-8')
        start_response(status_code, [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Content-Length', str(len(data))),
            ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        ])
        return [data]

    def redirect_response(location, extra_headers=None):
        headers = [
            ('Location', location),
            ('Content-Length', '0')
        ]
        if extra_headers:
            headers.extend(extra_headers)
        start_response('303 See Other', headers)
        return [b'']

    def binary_response(filename, data, content_type):
        start_response('200 OK', [
            ('Content-Type', content_type),
            ('Content-Disposition', f'attachment; filename="{filename}"'),
            ('Content-Length', str(len(data)))
        ])
        return [data]

    def login_page(message=''):
        notice = f'<div class="error">{crm_app.esc(message)}</div>' if message else ''
        return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CRM Login</title><style>{crm_app.CSS}</style></head><body><main style="min-height:100vh;display:grid;place-items:center;padding:24px;background:#f4f7fb"><form method="post" action="/login" class="card" style="width:min(430px,100%);border-radius:18px"><h1 style="margin:0 0 8px;font-size:30px">Smart Export CRM</h1><p class="hint" style="margin-top:0">Sign in to continue.</p>{notice}<label>Email<input name="email" type="email" autocomplete="username" required autofocus></label><label style="display:block;margin-top:12px">Password<input name="password" type="password" autocomplete="current-password" required></label><button class="btn" type="submit" style="width:100%;margin-top:16px">Login</button></form></main></body></html>'''

    def expected_credentials():
        return (
            os.environ.get('CRM_USERNAME', 'info@sheshaanglobal.com'),
            os.environ.get('CRM_PASSWORD', 'Sana@200908'),
        )

    def session_token(username):
        secret = os.environ.get('CRM_SESSION_SECRET') or expected_credentials()[1]
        return hmac.new(secret.encode('utf-8'), username.encode('utf-8'), hashlib.sha256).hexdigest()

    def cookie_value(name):
        for item in environ.get('HTTP_COOKIE', '').split(';'):
            if '=' in item:
                key, value = item.strip().split('=', 1)
                if key == name:
                    return value
        return ''

    def is_authenticated():
        username, password = expected_credentials()
        auth_header = environ.get('HTTP_AUTHORIZATION', '')
        expected = "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
        if hmac.compare_digest(auth_header, expected):
            return True
        return hmac.compare_digest(cookie_value('crm_session'), session_token(username))

    if path == '/login' and method == 'GET':
        return html_response(login_page())
    if path == '/login' and method == 'POST':
        data = form_dict(body_bytes)
        username, password = expected_credentials()
        if hmac.compare_digest(data.get('email', ''), username) and hmac.compare_digest(data.get('password', ''), password):
            cookie = f"crm_session={session_token(username)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800"
            return redirect_response('/', [('Set-Cookie', cookie)])
        return html_response(login_page('Invalid email or password.'), '401 Unauthorized')
    if path == '/logout':
        return redirect_response('/login', [('Set-Cookie', 'crm_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0')])

    if not is_authenticated():
        return redirect_response('/login?next=' + quote(path or '/'))

    try:
        ensure_db()

        if method == 'GET':
            if path == '/':
                return html_response(crm_app.dashboard_page())
            elif path == '/version':
                version_content = crm_app.layout('Outlook Desktop Active', crm_app.top('Outlook Desktop Active', f'You are running Smart Export CRM V7.2 on Vercel.', '<a class="btn" href="/">Dashboard</a>') + '<div class="card good"><h2>Outlook desktop integration is active</h2><p>Email buttons now use the Windows MAILTO protocol to open the installed Outlook app with To, Subject and Message pre-filled. Outlook Web is not used.</p><p class="hint">If another mail app opens, set Microsoft Outlook as the Windows default for MAILTO.</p></div>', '')
                return html_response(version_content)
            elif path == '/smart-followups':
                return html_response(crm_app.smart_followups_page())
            elif path == '/buyers':
                return html_response(crm_app.buyers_page(params))
            elif path == '/buyer/new':
                return html_response(crm_app.buyer_form_page())
            elif re.match(r'^/buyer/\d+$', path):
                return html_response(crm_app.buyer_detail_page(int(path.split('/')[2])))
            elif re.match(r'^/buyer/\d+/edit$', path):
                return html_response(crm_app.buyer_form_page(crm_app.get_buyer(int(path.split('/')[2]))))
            elif path == '/templates':
                return html_response(crm_app.templates_page())
            elif path == '/template/new':
                return html_response(crm_app.template_form_page())
            elif re.match(r'^/template/\d+/edit$', path):
                return html_response(crm_app.template_form_page(crm_app.get_template(int(path.split('/')[2]))))
            elif path == '/outlook-compose':
                to, subject, body_txt, _ = crm_app.email_draft_from_params(params)
                recipient = crm_app.quote(to, safe='@,;:+')
                query = crm_app.urlencode({'subject': subject, 'body': body_txt}, quote_via=crm_app.quote)
                return redirect_response('mailto:' + recipient + ('?' + query if query else ''))
            elif path == '/titan-compose':
                to, subject, body_txt, _ = crm_app.email_draft_from_params(params)
                body_txt = body_txt.replace('\r', '')
                body_txt = re.sub(r'\n{3,}', '\n\n', body_txt)
                recipient = crm_app.quote(to, safe='@,;:+')
                query = crm_app.urlencode({'subject': subject, 'body': body_txt}, quote_via=crm_app.quote)
                return redirect_response('mailto:' + recipient + ('?' + query if query else ''))
            elif path == '/campaigns':
                return html_response(crm_app.campaigns_page())
            elif path == '/campaign/new':
                return html_response(crm_app.campaign_new_page(params))
            elif re.match(r'^/campaign/\d+$', path):
                return html_response(crm_app.campaign_detail_page(int(path.split('/')[2])))
            elif path == '/kanban':
                return html_response(crm_app.kanban_page())
            elif path == '/data-quality':
                return html_response(crm_app.data_quality_page())
            elif path == '/import':
                return html_response(crm_app.import_page())
            elif path == '/backup-restore':
                return html_response(crm_app.backup_restore_page())
            elif path == '/export/csv':
                return binary_response('export_import_buyers.csv', crm_app.csv_bytes(crm_app.EXPORT_HEADERS, crm_app.buyer_rows()), 'text/csv; charset=utf-8')
            elif path == '/export/valid-csv':
                return binary_response('valid_verified_leads.csv', crm_app.csv_bytes(crm_app.EXPORT_HEADERS, crm_app.buyer_rows(valid_only=True)), 'text/csv; charset=utf-8')
            elif path == '/export/followups-csv':
                return binary_response('followup_tasks.csv', crm_app.csv_bytes(crm_app.EXPORT_HEADERS, crm_app.buyer_rows(followups=True)), 'text/csv; charset=utf-8')
            elif path == '/export/xlsx':
                return binary_response('export_import_buyers.xlsx', crm_app.write_xlsx(crm_app.EXPORT_HEADERS, crm_app.buyer_rows()), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            elif path == '/report/pdf':
                return binary_response('export_import_crm_report.pdf', crm_app.report_pdf(), 'application/pdf')
            elif path == '/backup.zip':
                return binary_response('smart_export_crm_v7_backup.zip', crm_app.backup_zip(), 'application/zip')
            elif path == '/sample-template.csv':
                return binary_response('sample_import_template.csv', crm_app.csv_bytes(crm_app.IMPORT_FIELDS, crm_app.sample_rows()), 'text/csv; charset=utf-8')
            elif path == '/sample-template.xlsx':
                return binary_response('sample_import_template.xlsx', crm_app.write_xlsx(crm_app.IMPORT_FIELDS, crm_app.sample_rows()), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            else:
                return html_response(crm_app.error_page('Page not found'), '404 Not Found')

        elif method == 'POST':
            if path == '/buyer/new':
                data = form_dict(body_bytes)
                crm_app.insert_buyer(data)
                return redirect_response('/buyers')
            elif re.match(r'^/buyer/\d+/edit$', path):
                bid = int(path.split('/')[2])
                data = form_dict(body_bytes)
                crm_app.update_buyer(bid, data)
                return redirect_response(f'/buyer/{bid}')
            elif re.match(r'^/buyer/\d+/action$', path):
                bid = int(path.split('/')[2])
                data = form_dict(body_bytes)
                crm_app.add_activity(bid, data.get('action'), data.get('activity_date') or crm_app.today(), data.get('notes', ''), data.get('next_followup_date', ''))
                return redirect_response(f'/buyer/{bid}')
            elif path == '/bulk-action':
                params = form_params(body_bytes)
                crm_app.bulk_apply(params)
                return redirect_response('/buyers#bulk-editor')
            elif path == '/template/new':
                data = form_dict(body_bytes)
                n = crm_app.now()
                with crm_app.conn() as c:
                    c.execute('INSERT INTO email_templates(name,subject,body,category,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', (crm_app.clean(data.get('name')), crm_app.clean(data.get('subject')), crm_app.clean(data.get('body')), crm_app.clean(data.get('category')) or 'General', 0, n, n))
                    c.commit()
                return redirect_response('/templates')
            elif re.match(r'^/template/\d+/edit$', path):
                tid = int(path.split('/')[2])
                data = form_dict(body_bytes)
                with crm_app.conn() as c:
                    c.execute('UPDATE email_templates SET name=?, subject=?, body=?, category=?, updated_at=? WHERE id=?', (crm_app.clean(data.get('name')), crm_app.clean(data.get('subject')), crm_app.clean(data.get('body')), crm_app.clean(data.get('category')) or 'General', crm_app.now(), tid))
                    c.commit()
                return redirect_response('/templates')
            elif path == '/campaign/new':
                data = form_dict(body_bytes)
                cid, count = crm_app.create_campaign(data)
                if not cid:
                    return html_response(crm_app.campaign_new_page({}, 'Could not create campaign. Please add buyers and choose a template.'))
                else:
                    return redirect_response(f'/campaign/{cid}')
            elif re.match(r'^/campaign/\d+/mark-sent$', path):
                cid = int(path.split('/')[2])
                params = form_params(body_bytes)
                count = crm_app.mark_campaign_sent(cid, params)
                return html_response(crm_app.campaign_detail_page(cid, f'{count} recipients marked as sent. Buyer follow-up dates updated.'))
            elif re.match(r'^/campaign/\d+/delete$', path):
                cid = int(path.split('/')[2])
                with crm_app.conn() as c:
                    c.execute('DELETE FROM campaigns WHERE id=?', (cid,))
                    c.execute('DELETE FROM campaign_recipients WHERE campaign_id=?', (cid,))
                    c.commit()
                return redirect_response('/campaigns')
            elif path == '/import':
                content_type = environ.get('CONTENT_TYPE', '')
                file_payload, filename = parse_multipart_payload(content_type, body_bytes)
                if not file_payload:
                    return html_response(crm_app.import_page('No file received.'))
                save_path = os.path.join("/tmp", filename)
                with open(save_path, 'wb') as f:
                    f.write(file_payload)
                if filename.lower().endswith('.csv'):
                    rows = crm_app.parse_csv_file(save_path)
                elif filename.lower().endswith('.xlsx'):
                    rows = crm_app.parse_xlsx_file(save_path)
                else:
                    return html_response(crm_app.import_page('Only CSV and XLSX files are supported.'))
                counts = crm_app.import_rows(rows)
                msg = f"Import complete: {counts.get('inserted',0)} inserted, {counts.get('updated',0)} updated, {counts.get('duplicate',0)} duplicates skipped, {counts.get('skipped',0)} empty rows skipped, {counts.get('validation_updated',0)} rows carried validation status."
                return html_response(crm_app.import_page(msg))
            elif path == '/restore':
                content_type = environ.get('CONTENT_TYPE', '')
                file_payload, filename = parse_multipart_payload(content_type, body_bytes)
                if not file_payload:
                    return html_response(crm_app.backup_restore_page('No file received.'))
                save_path = os.path.join("/tmp", filename)
                with open(save_path, 'wb') as f:
                    f.write(file_payload)
                msg = crm_app.restore_backup(save_path)
                return html_response(crm_app.backup_restore_page(msg))
            else:
                return html_response(crm_app.error_page('Page not found'), '404 Not Found')

    except Exception as e:
        return html_response(crm_app.error_page(str(e)), '500 Internal Server Error')

# Vercel WSGI entry point
app = application

