import requests
import redis

r = redis.from_url('redis://localhost:6379/0')
API = 'http://127.0.0.1:8000/api'

def get_token(email):
    requests.post(f'{API}/auth/send-otp', json={'email': email})
    otp = r.get(f'otp:{email}')
    otp_str = otp.decode() if isinstance(otp, bytes) else otp
    res = requests.post(f'{API}/auth/verify-otp', json={'email': email, 'otp': otp_str})
    return res.json()['access_token']

admin_token = get_token('admin@getground.com')
owner_token = get_token('owner@getground.com')
owner_headers = {'Authorization': f'Bearer {owner_token}'}

# Get current grounds
grounds = requests.get(f'{API}/grounds').json()
print('Grounds:', [(g['id'], g['name']) for g in grounds] if isinstance(grounds, list) else grounds)

if isinstance(grounds, list) and len(grounds) > 0:
    for ground in grounds:
        gid = ground['id']
        print(f"\nUpdating ground {gid}: {ground['name']}")
        print('Current pricing:', ground.get('pricing'))

        # Add more 1hr slots
        new_slots = [
            ('06:00:00', '07:00:00'),
            ('07:00:00', '08:00:00'),
            ('09:00:00', '10:00:00'),
            ('10:00:00', '11:00:00'),
            ('11:00:00', '12:00:00'),
            ('12:00:00', '13:00:00'),
            ('17:00:00', '18:00:00'),
            ('19:00:00', '20:00:00'),
            ('20:00:00', '21:00:00'),
        ]
        for start, end in new_slots:
            res = requests.post(f'{API}/owner/grounds/{gid}/slots',
                                json={'start_time': start, 'end_time': end},
                                headers=owner_headers)
            print(f'  Add slot {start}-{end}: {res.status_code} {res.text[:60]}')

        # Add pricing for all categories
        existing_cats = {p['category'] for p in ground.get('pricing', [])}
        category_prices = [
            ('Match', 1800),
            ('Tournament', 2500),
            ('Corporate', 3000),
        ]
        for cat, price in category_prices:
            res = requests.post(f'{API}/owner/grounds/{gid}/pricing',
                                json={'category': cat, 'price': price},
                                headers=owner_headers)
            print(f'  Pricing {cat} @ {price}: {res.status_code} {res.text[:60]}')

print('\nDone! Check /api/grounds for updated data.')
