import requests

# Login to admin
session = requests.Session()
login_data = {'username': 'admin', 'password': 'admin123'}
session.post('https://mezonehediye.ir/login', data=login_data)

# Demo images from picsum (free placeholder images)
demo_images = {
    1: 'https://picsum.photos/seed/shomiz1/600/800',
    2: 'https://picsum.photos/seed/manto2/600/800', 
    3: 'https://picsum.photos/seed/set3/600/800',
    4: 'https://picsum.photos/seed/shalvar4/600/800',
    5: 'https://picsum.photos/seed/shomiz5/600/800',
    6: 'https://picsum.photos/seed/manto6/600/800',
    7: 'https://picsum.photos/seed/set7/600/800',
    8: 'https://picsum.photos/seed/shomiz8/600/800',
    9: 'https://picsum.photos/seed/manto9/600/800',
    10: 'https://picsum.photos/seed/shalvar10/600/800',
}

print("Demo images ready. Use admin panel to upload real images.")
print("Or add this route to app.py to auto-update:")
