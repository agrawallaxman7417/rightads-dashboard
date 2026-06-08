from flask import Flask, jsonify, request, abort, Response
from flask_cors import CORS
import json, os, re
from datetime import datetime

app = Flask(__name__)
CORS(app)

BASE       = os.path.dirname(os.path.abspath(__file__))
CLEAN_FILE = os.path.join(BASE, 'clean_data.json')
RAW_FILE   = os.path.join(BASE, 'raw_data.json')
HTML_FILE  = os.path.join(BASE, 'index.html')

def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    return Response(content, mimetype='text/html')

@app.route('/api/leads', methods=['GET'])
def get_leads():
    data   = load(CLEAN_FILE)
    status = request.args.get('status')
    search = request.args.get('q', '').lower()
    limit  = int(request.args.get('limit', 99999))
    page   = int(request.args.get('page', 1))
    if status and status != 'All':
        data = [d for d in data if d.get('Status') == status]
    if search:
        data = [d for d in data if
                search in (d.get('Name') or '').lower() or
                search in (d.get('Phone') or '') or
                search in (d.get('Address') or '').lower()]
    total = len(data)
    start = (page - 1) * limit
    return jsonify({'total': total, 'page': page, 'limit': limit, 'data': data[start:start+limit]})

@app.route('/api/leads/<int:lead_id>', methods=['GET'])
def get_lead(lead_id):
    data = load(CLEAN_FILE)
    lead = next((d for d in data if d['id'] == lead_id), None)
    if not lead: abort(404, description=f'Lead {lead_id} not found')
    return jsonify(lead)

@app.route('/api/leads', methods=['POST'])
def create_lead():
    body  = request.get_json() or {}
    name  = (body.get('Name') or '').strip()
    phone = re.sub(r'\D', '', body.get('Phone') or '')[-10:]
    if not name: abort(400, description='Business Name is required')
    if len(phone) < 10: abort(400, description='Valid 10-digit phone required')
    clean = load(CLEAN_FILE)
    raw   = load(RAW_FILE)
    dup = next((d for d in clean if d.get('Phone') == phone), None)
    if dup: abort(409, description=f'Phone already exists: {dup["Name"]}')
    new_id = max((d['id'] for d in clean), default=0) + 1
    record = {
        'id': new_id, 'Name': name, 'Phone': phone,
        'Address': (body.get('Address') or '').strip(),
        'Pin_Code': (body.get('Pin_Code') or '').strip(),
        'Status': body.get('Status', 'Not Called'),
        'Call_Status': body.get('Status', 'Not Called'),
        'notes': (body.get('notes') or '').strip(),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        '_new': True, '_dup': False,
    }
    clean.insert(0, record)
    raw.insert(0, {**record})
    save(CLEAN_FILE, clean)
    save(RAW_FILE, raw)
    return jsonify({'message': f'Lead "{name}" added!', 'lead': record}), 201

@app.route('/api/leads/<int:lead_id>', methods=['PUT'])
def update_lead(lead_id):
    body  = request.get_json() or {}
    clean = load(CLEAN_FILE)
    raw   = load(RAW_FILE)
    rec   = next((d for d in clean if d['id'] == lead_id), None)
    if not rec: abort(404, description=f'Lead {lead_id} not found')
    for k in ['Name', 'Phone', 'Address', 'Pin_Code', 'Status', 'notes']:
        if k in body: rec[k] = body[k]
    if 'Status' in body: rec['Call_Status'] = body['Status']
    rec['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    for d in raw:
        if d['id'] == lead_id:
            d.update({k: rec[k] for k in rec})
            break
    save(CLEAN_FILE, clean)
    save(RAW_FILE, raw)
    return jsonify({'message': 'Updated!', 'lead': rec})

@app.route('/api/leads/<int:lead_id>', methods=['DELETE'])
def delete_lead(lead_id):
    clean = load(CLEAN_FILE)
    raw   = load(RAW_FILE)
    c_before = len(clean)
    clean = [d for d in clean if d['id'] != lead_id]
    if len(clean) == c_before: abort(404, description=f'Lead {lead_id} not found')
    raw = [d for d in raw if d['id'] != lead_id]
    save(CLEAN_FILE, clean)
    save(RAW_FILE, raw)
    return jsonify({'message': f'Lead {lead_id} deleted!'})

@app.route('/api/raw', methods=['GET'])
def get_raw():
    data   = load(RAW_FILE)
    page   = int(request.args.get('page', 1))
    limit  = int(request.args.get('limit', 99999))
    status = request.args.get('status')
    search = request.args.get('q', '').lower()
    if status and status != 'All':
        data = [d for d in data if d.get('Status') == status]
    if search:
        data = [d for d in data if
                search in (d.get('Name') or '').lower() or
                search in (d.get('Phone') or '') or
                search in (d.get('Address') or '').lower()]
    total = len(data)
    start = (page - 1) * limit
    return jsonify({'total': total, 'page': page, 'data': data[start:start+limit]})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    ds   = request.args.get('dataset', 'clean')
    data = load(CLEAN_FILE if ds == 'clean' else RAW_FILE)
    sc, pins = {}, {}
    for d in data:
        sc[d.get('Status','Other')] = sc.get(d.get('Status','Other'),0)+1
        if d.get('Pin_Code'): pins[d['Pin_Code']] = pins.get(d['Pin_Code'],0)+1
    return jsonify({
        'total': len(data), 'status_counts': sc,
        'top_pins': sorted(pins.items(), key=lambda x:-x[1])[:10],
        'with_notes': sum(1 for d in data if (d.get('notes') or '').strip()),
        'duplicates': sum(1 for d in data if d.get('_dup')),
    })

@app.errorhandler(400)
def bad_req(e): return jsonify({'error': str(e.description)}), 400
@app.errorhandler(404)
def not_found(e): return jsonify({'error': str(e.description)}), 404
@app.errorhandler(409)
def conflict(e): return jsonify({'error': str(e.description)}), 409

if __name__ == '__main__':
    print("Right Ads → http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
