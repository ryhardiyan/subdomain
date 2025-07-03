from flask import Flask, render_template, request, jsonify
import json
import requests
import os

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # Bot token
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')  # Admin chat ID

# === Load Zone Info ===
def load_zones():
    try:
        with open('zones.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Gagal load zones.json: {e}")
        return {}

# === Cek apakah subdomain sudah ada ===
def subdomain_exists(zone_id, api_key, name):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?name={name}"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        return data.get('success', False) and len(data.get('result', [])) > 0
    except Exception as e:
        print(f"[ERROR] Gagal cek subdomain: {e}")
        return False

# === Kirim Notif ke Telegram ===
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
        print(f"[ERROR] Gagal kirim notif Telegram: {e}")

# === ROUTES ===

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
            return jsonify({'exists': False, 'message': 'Domain tidak ditemukan'}), 400

        zone_id = zones[domain]['zone_id']
        api_key = zones[domain]['api_key']

        exists = subdomain_exists(zone_id, api_key, full_subdomain)
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
            return jsonify({'success': False, 'message': 'Domain tidak ditemukan'}), 400

        zone_id = zones[domain]['zone_id']
        api_key = zones[domain]['api_key']

        # Cek eksistensi dulu
        if subdomain_exists(zone_id, api_key, full_subdomain):
            return jsonify({
                'success': False,
                'message': f'Subdomain {full_subdomain} sudah ada di Cloudflare'
            }), 400

        # Buat subdomain baru
        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
        headers = {
            'Authorization': f'Bearer {api_key}',
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
                'message': 'Subdomain berhasil dibuat'
            })
        else:
            error_msg = 'Unknown error from Cloudflare'
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
