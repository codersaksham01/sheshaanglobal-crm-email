import os
import re
import sys
import base64
import email
from urllib.parse import parse_qs, urlparse

# Add current directory to path so we can import app.py
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import app

# Initialize Postgres Database
app.init_db()

def html_response(html_content, status_code=200):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
        },
        "body": html_content
    }

def redirect_response(location):
    return {
        "statusCode": 303,
        "headers": {
            "Location": location
        },
        "body": ""
    }

def binary_response(filename, data, content_type):
    # Encode binary data to base64 for Netlify Serverless Functions
    b64_data = base64.b64encode(data).decode('utf-8')
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": content_type,
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
        "body": b64_data,
        "isBase64Encoded": True
    }

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

def handler(event, context):
    # 1. Enforce Basic Authentication
    headers = event.get('headers', {})
    auth_header = headers.get('authorization') or headers.get('Authorization')
    expected = "Basic " + base64.b64encode(b"info@sheshaanglobal.com:Sana@200908").decode("utf-8")
    if auth_header != expected:
        return {
            "statusCode": 401,
            "headers": {
                "WWW-Authenticate": 'Basic realm="CRM Login"',
                "Content-Type": "text/html"
            },
            "body": "Unauthorized. Please login with your credentials."
        }

    # 2. Extract Path & Query parameters
    path = event.get('path', '/')
    # Strip function prefix if accessed directly
    prefix = "/.netlify/functions/crm"
    if path.startswith(prefix):
        path = path[len(prefix):]
    if not path:
        path = '/'

    method = event.get('httpMethod', 'GET').upper()
    query_params = event.get('queryStringParameters', {}) or {}
    params = {k: [v] for k, v in query_params.items()}

    # 3. Parse POST request bodies
    body_str = event.get('body', '')
    if event.get('isBase64Encoded', False):
        body_bytes = base64.b64decode(body_str)
    else:
        body_bytes = body_str.encode('utf-8')

    def form_params(body):
        return parse_qs(body.decode('utf-8', errors='ignore'), keep_blank_values=True)
    def form_dict(body):
        return {k: v[0] for k, v in form_params(body).items()}

    try:
        if method == 'GET':
            if path == '/':
                return html_response(app.dashboard_page())
            elif path == '/version':
                version_content = app.layout('Outlook Desktop Active', app.top('Outlook Desktop Active', f'You are running Smart Export CRM V7.2 on Netlify.', '<a class="btn" href="/">Dashboard</a>') + '<div class="card good"><h2>Outlook desktop integration is active</h2><p>Email buttons now use the Windows MAILTO protocol to open the installed Outlook app with To, Subject and Message pre-filled. Outlook Web is not used.</p><p class="hint">If another mail app opens, set Microsoft Outlook as the Windows default for MAILTO.</p></div>', '')
                return html_response(version_content)
            elif path == '/smart-followups':
                return html_response(app.smart_followups_page())
            elif path == '/buyers':
                return html_response(app.buyers_page(params))
            elif path == '/buyer/new':
                return html_response(app.buyer_form_page())
            elif re.match(r'^/buyer/\d+$', path):
                return html_response(app.buyer_detail_page(int(path.split('/')[2])))
            elif re.match(r'^/buyer/\d+/edit$', path):
                return html_response(app.buyer_form_page(app.get_buyer(int(path.split('/')[2]))))
            elif path == '/templates':
                return html_response(app.templates_page())
            elif path == '/template/new':
                return html_response(app.template_form_page())
            elif re.match(r'^/template/\d+/edit$', path):
                return html_response(app.template_form_page(app.get_template(int(path.split('/')[2]))))
            elif path == '/outlook-compose':
                to, subject, body_txt, _ = app.email_draft_from_params(params)
                recipient = app.quote(to, safe='@,;:+')
                query = app.urlencode({'subject': subject, 'body': body_txt}, quote_via=app.quote)
                return redirect_response('mailto:' + recipient + ('?' + query if query else ''))
            elif path == '/titan-compose':
                to, subject, body_txt, _ = app.email_draft_from_params(params)
                body_txt = body_txt.replace('\r', '')
                body_txt = re.sub(r'\n{3,}', '\n\n', body_txt)
                recipient = app.quote(to, safe='@,;:+')
                query = app.urlencode({'subject': subject, 'body': body_txt}, quote_via=app.quote)
                return redirect_response('mailto:' + recipient + ('?' + query if query else ''))
            elif path == '/campaigns':
                return html_response(app.campaigns_page())
            elif path == '/campaign/new':
                return html_response(app.campaign_new_page(params))
            elif re.match(r'^/campaign/\d+$', path):
                return html_response(app.campaign_detail_page(int(path.split('/')[2])))
            elif path == '/kanban':
                return html_response(app.kanban_page())
            elif path == '/data-quality':
                return html_response(app.data_quality_page())
            elif path == '/import':
                return html_response(app.import_page())
            elif path == '/backup-restore':
                return html_response(app.backup_restore_page())
            elif path == '/export/csv':
                return binary_response('export_import_buyers.csv', app.csv_bytes(app.EXPORT_HEADERS, app.buyer_rows()), 'text/csv; charset=utf-8')
            elif path == '/export/valid-csv':
                return binary_response('valid_verified_leads.csv', app.csv_bytes(app.EXPORT_HEADERS, app.buyer_rows(valid_only=True)), 'text/csv; charset=utf-8')
            elif path == '/export/followups-csv':
                return binary_response('followup_tasks.csv', app.csv_bytes(app.EXPORT_HEADERS, app.buyer_rows(followups=True)), 'text/csv; charset=utf-8')
            elif path == '/export/xlsx':
                return binary_response('export_import_buyers.xlsx', app.write_xlsx(app.EXPORT_HEADERS, app.buyer_rows()), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            elif path == '/report/pdf':
                return binary_response('export_import_crm_report.pdf', app.report_pdf(), 'application/pdf')
            elif path == '/backup.zip':
                return binary_response('smart_export_crm_v7_backup.zip', app.backup_zip(), 'application/zip')
            elif path == '/sample-template.csv':
                return binary_response('sample_import_template.csv', app.csv_bytes(app.IMPORT_FIELDS, app.sample_rows()), 'text/csv; charset=utf-8')
            elif path == '/sample-template.xlsx':
                return binary_response('sample_import_template.xlsx', app.write_xlsx(app.IMPORT_FIELDS, app.sample_rows()), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            else:
                return html_response(app.error_page('Page not found'), 404)

        elif method == 'POST':
            if path == '/buyer/new':
                data = form_dict(body_bytes)
                app.insert_buyer(data)
                return redirect_response('/buyers')
            elif re.match(r'^/buyer/\d+/edit$', path):
                bid = int(path.split('/')[2])
                data = form_dict(body_bytes)
                app.update_buyer(bid, data)
                return redirect_response(f'/buyer/{bid}')
            elif re.match(r'^/buyer/\d+/action$', path):
                bid = int(path.split('/')[2])
                data = form_dict(body_bytes)
                app.add_activity(bid, data.get('action'), data.get('activity_date') or app.today(), data.get('notes', ''), data.get('next_followup_date', ''))
                return redirect_response(f'/buyer/{bid}')
            elif path == '/bulk-action':
                params = form_params(body_bytes)
                app.bulk_apply(params)
                return redirect_response('/buyers#bulk-editor')
            elif path == '/template/new':
                data = form_dict(body_bytes)
                n = app.now()
                with app.conn() as c:
                    c.execute('INSERT INTO email_templates(name,subject,body,category,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', (app.clean(data.get('name')), app.clean(data.get('subject')), app.clean(data.get('body')), app.clean(data.get('category')) or 'General', 0, n, n))
                    c.commit()
                return redirect_response('/templates')
            elif re.match(r'^/template/\d+/edit$', path):
                tid = int(path.split('/')[2])
                data = form_dict(body_bytes)
                with app.conn() as c:
                    c.execute('UPDATE email_templates SET name=?, subject=?, body=?, category=?, updated_at=? WHERE id=?', (app.clean(data.get('name')), app.clean(data.get('subject')), app.clean(data.get('body')), app.clean(data.get('category')) or 'General', app.now(), tid))
                    c.commit()
                return redirect_response('/templates')
            elif path == '/campaign/new':
                data = form_dict(body_bytes)
                cid, count = app.create_campaign(data)
                if not cid:
                    return html_response(app.campaign_new_page({}, 'Could not create campaign. Please add buyers and choose a template.'))
                else:
                    return redirect_response(f'/campaign/{cid}')
            elif re.match(r'^/campaign/\d+/mark-sent$', path):
                cid = int(path.split('/')[2])
                params = form_params(body_bytes)
                count = app.mark_campaign_sent(cid, params)
                return html_response(app.campaign_detail_page(cid, f'{count} recipients marked as sent. Buyer follow-up dates updated.'))
            elif re.match(r'^/campaign/\d+/delete$', path):
                cid = int(path.split('/')[2])
                with app.conn() as c:
                    c.execute('DELETE FROM campaigns WHERE id=?', (cid,))
                    c.execute('DELETE FROM campaign_recipients WHERE campaign_id=?', (cid,))
                    c.commit()
                return redirect_response('/campaigns')
            elif path == '/import':
                content_type = headers.get('content-type') or headers.get('Content-Type') or ''
                file_payload, filename = parse_multipart_payload(content_type, body_bytes)
                if not file_payload:
                    return html_response(app.import_page('No file received.'))
                save_path = os.path.join("/tmp", filename)
                with open(save_path, 'wb') as f:
                    f.write(file_payload)
                if filename.lower().endswith('.csv'):
                    rows = app.parse_csv_file(save_path)
                elif filename.lower().endswith('.xlsx'):
                    rows = app.parse_xlsx_file(save_path)
                else:
                    return html_response(app.import_page('Only CSV and XLSX files are supported.'))
                counts = app.import_rows(rows)
                msg = f"Import complete: {counts.get('inserted',0)} inserted, {counts.get('updated',0)} updated, {counts.get('duplicate',0)} duplicates skipped, {counts.get('skipped',0)} empty rows skipped, {counts.get('validation_updated',0)} rows carried validation status."
                return html_response(app.import_page(msg))
            elif path == '/restore':
                content_type = headers.get('content-type') or headers.get('Content-Type') or ''
                file_payload, filename = parse_multipart_payload(content_type, body_bytes)
                if not file_payload:
                    return html_response(app.backup_restore_page('No file received.'))
                save_path = os.path.join("/tmp", filename)
                with open(save_path, 'wb') as f:
                    f.write(file_payload)
                msg = app.restore_backup(save_path)
                return html_response(app.backup_restore_page(msg))
            else:
                return html_response(app.error_page('Page not found'), 404)

    except Exception as e:
        return html_response(app.error_page(str(e)), 500)
