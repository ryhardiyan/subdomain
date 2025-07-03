from flask import Flask, render_template, request, jsonify
import json
import requests
import os

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('7086103182:AAF3btwgLddx25KCmkW0K74WmXWphYPJjZU')
TELEGRAM_CHAT_ID = os.getenv('6673195444')

def load_zones():
    try:
        with open('zones.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed loading zones.json: {e}")
        return {}

def subdomain_exists(zone_id, api_key, email, name):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?name={name}"
    headers = {
        'X-Auth-Key': api_key,
        'X-Auth-Email': email,
        'Content-Type': 'application/json'
    }
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        return data.get('success', False) and len(data.get('result', [])) > 0
    except Exception as e:
        print(f"[ERROR] Subdomain check failed: {e}")
        return False

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown'
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[ERROR] Telegram notification failed: {e}")

@app.route('/')
def index():
    zones = load_zones()
    domains = list(zones.keys())
    return render_template('index.html', domains=domains)

@app.route('/check_subdomain', methods=['POST'])
def check_subdomain():
    try:
        data = request.get_json()
        subdomain = data['subdomain'].strip().lower()
        domain = data['domain'].strip().lower()
        full_subdomain = f"{subdomain}.{domain}"

        zones = load_zones()
        if domain not in zones:
            return jsonify({'exists': False, 'message': 'Domain not found'}), 400

        zone_id = zones[domain]['zone_id']
        api_key = zones[domain]['api_key']
        email = zones[domain]['email']

        exists = subdomain_exists(zone_id, api_key, email, full_subdomain)
        return jsonify({'exists': exists})
    except Exception as e:
        return jsonify({'exists': False, 'error': str(e)}), 500

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
        email = zones[domain]['email']

        if subdomain_exists(zone_id, api_key, email, full_subdomain):
            return jsonify({
                'success': False,
                'message': f'Subdomain {full_subdomain} already exists'
            }), 400

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
            send_telegram_message(f"✅ *Subdomain Created*\n`{full_subdomain}` → `{content}`\nType: `{record_type}`\nProxy: `{proxied}`")
            return jsonify({
                'success': True,
                'message': 'Subdomain created successfully'
            })
        else:
            error_msg = 'Cloudflare error'
            if cf_result.get('errors'):
                error_msg = cf_result['errors'][0].get('message', error_msg)
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400

    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
