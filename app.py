# app.py
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key")

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

ZONES_PATH = 'zones.json'
RECORDS_PATH = 'records.json'

def load_zones():
    try:
        with open(ZONES_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}

def load_records():
    try:
        with open(RECORDS_PATH, 'r') as f:
            return json.load(f)
    except:
        return []

def save_records(records):
    with open(RECORDS_PATH, 'w') as f:
        json.dump(records, f, indent=2)

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return {'sent': False, 'error': 'Missing token or chat_id'}

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown'
    }

    try:
        response = requests.post(url, json=payload)
        return {
            'sent': True,
            'status': response.status_code,
            'response': response.text
        }
    except Exception as e:
        return {'sent': False, 'error': str(e)}

@app.route('/')
def index():
    zones = load_zones()
    domains = list(zones.keys())
    return render_template('index.html', domains=domains)

@app.route('/login', methods=['POST'])
def login():
    content = request.form.get('content')
    if not content:
        return redirect(url_for('index'))

    records = load_records()
    owned = [r for r in records if r.get('owner') == content]
    if owned:
        session['user'] = content
        return redirect(url_for('dashboard'))
    return "Unauthorized", 401

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('index'))

    user_ip = session['user']
    records = load_records()
    user_records = [r for r in records if r.get('owner') == user_ip]
    return render_template('dashboard.html', records=user_records, user=user_ip)

@app.route('/update_record', methods=['POST'])
def update_record():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json()
    records = load_records()
    found = False
    for r in records:
        if r['name'] == data['old_name'] and r['owner'] == session['user']:
            r['name'] = data['name']
            r['content'] = data['content']
            r['type'] = data['type']
            r['proxied'] = data['proxied']
            found = True
            break

    if found:
        save_records(records)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Record not found'})

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/create_subdomain', methods=['POST'])
def create_subdomain():
    try:
        data = request.get_json()
        subdomain = data['subdomain'].strip().lower()
        domain = data['domain'].strip().lower()
        record_type = data['type']
        content = data['content'].strip()
        proxied = data['proxied']
        full_subdomain = f"{subdomain}.{domain}"

        zones = load_zones()
        if domain not in zones:
            return jsonify({'success': False, 'message': 'Domain not found'}), 400

        zone_id = zones[domain]['zone_id']
        api_key = zones[domain]['api_key']
        email = zones[domain].get('email', 'admin@example.com')

        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
        headers = {
            'X-Auth-Key': api_key,
            'X-Auth-Email': email,
            'Content-Type': 'application/json'
        }

        dns_record = {
            'type': record_type,
            'name': full_subdomain,
            'content': content,
            'proxied': proxied
        }

        response = requests.post(url, headers=headers, json=dns_record)
        cf_result = response.json()

        if cf_result.get('success'):
            # Save to records.json
            records = load_records()
            records.append({
                'name': full_subdomain,
                'content': content,
                'type': record_type,
                'proxied': proxied,
                'owner': content
            })
            save_records(records)

            # Telegram notif
            send_telegram_message(
                f"✅ *Subdomain Created*\n`{full_subdomain}` → `{content}`\nType: `{record_type}`\nProxy: `{proxied}`"
            )

            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Cloudflare error'}), 400

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
