import os
import sqlite3
import hashlib
import secrets
import json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, g, abort
from functools import wraps
import time
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mazoun-hediye-default-key-change-me')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mazoun_hediye.db')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# ZarinPal Settings (TODO: Fill with your merchant ID)
ZARINPAL_MERCHANT_ID = os.environ.get('ZARINPAL_MERCHANT', 'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX')
ZARINPAL_SANDBOX = True  # Set to False in production

# ==================== DATABASE ====================
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT,
            phone TEXT,
            address TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_en TEXT,
            slug TEXT UNIQUE NOT NULL,
            icon TEXT
        );
        
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            old_price INTEGER,
            category_id INTEGER,
            image TEXT,
            sizes TEXT DEFAULT 'S,M,L,XL',
            colors TEXT,
            stock INTEGER DEFAULT 100,
            discount INTEGER DEFAULT 0,
            is_featured INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            rating REAL DEFAULT 4.5,
            reviews_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            city TEXT,
            total_amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            payment_status TEXT DEFAULT 'unpaid',
            tracking_code TEXT,
            authority TEXT,
            ref_id TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            size TEXT,
            color TEXT,
            quantity INTEGER NOT NULL,
            price INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT
        );
    ''')
    
    # Insert default categories
    categories = [
        ('شومیز', 'blouse', 'blouse', '👚'),
        ('مانتو', 'mantu', 'mantu', '🧥'),
        ('ست', 'set', 'set', '👗'),
        ('شلوار', 'pants', 'pants', '👖'),
    ]
    for name, name_en, slug, icon in categories:
        try:
            db.execute('INSERT INTO categories (name, name_en, slug, icon) VALUES (?, ?, ?, ?)',
                      (name, name_en, slug, icon))
        except sqlite3.IntegrityError:
            pass
    
    # Insert default admin user
    try:
        db.execute('INSERT INTO users (username, email, password, full_name, is_admin) VALUES (?, ?, ?, ?, ?)',
                  ('admin', 'admin@mezonehediye.ir',
                   generate_password_hash('admin123'), 'مدیر فروشگاه', 1))
    except sqlite3.IntegrityError:
        pass
    
    # Insert default settings
    defaults = {
        'shop_name': 'مزون هدیه',
        'shop_description': 'هر روز یک استایل تازه ✨',
        'shop_phone': '۰۹۱۲-XXX-XXXX',
        'shop_address': 'قم، ایران',
        'shop_email': 'info@mezonehediye.ir',
        'instagram': 'mezonehediye.qom',
        'shipping_cost': '30000',
        'free_shipping_min': '500000',
        'currency': 'تومان',
    }
    for key, value in defaults.items():
        try:
            db.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (key, value))
        except sqlite3.IntegrityError:
            pass
    
    # Insert sample products
    products = [
        ('شومیز سفید ابریشمی', 'شومیز زنانه ابریشمی با کیفیت بالا و طراحی شیک', 450000, 580000, 1, 'linear-gradient(135deg,#f5f5f5,#e0e0e0)', 'S,M,L,XL', 'سفید', 50, 22, 1, 4.5, 23),
        ('مانتو کلاسیک مشکی', 'مانتو زنانه کلاسیک مناسب استفاده روزمره', 890000, 1100000, 2, 'linear-gradient(135deg,#424242,#212121)', 'S,M,L,XL', 'مشکی', 30, 19, 1, 4.8, 45),
        ('ست مجلسی طلایی', 'ست مجلسی زنانه با طراحی خاص و شیک', 1200000, 1500000, 3, 'linear-gradient(135deg,#ffd700,#ff8f00)', 'S,M,L', 'طلایی', 20, 20, 1, 4.9, 67),
        ('شلوار مام استایل جین', 'شلوار جین زنانه مام استایل با کیفیت بالا', 380000, 450000, 4, 'linear-gradient(135deg,#1565c0,#0d47a1)', 'S,M,L,XL', 'آبی', 40, 16, 0, 4.3, 18),
        ('شومیز گلدار صورتی', 'شومیز زنانه گلدار با رنگ صورتی زیبا', 320000, 400000, 1, 'linear-gradient(135deg,#f48fb1,#ec407a)', 'S,M,L', 'صورتی', 35, 20, 0, 4.6, 31),
        ('مانتو اسپرت سبز', 'مانتو زنانه اسپرت مناسب استفاده روزمره', 750000, 950000, 2, 'linear-gradient(135deg,#66bb6a,#2e7d32)', 'M,L,XL', 'سبز', 25, 21, 0, 4.4, 28),
        ('ست راحتی خانگی', 'ست راحتی زنانه مناسب استفاده در منزل', 290000, 350000, 3, 'linear-gradient(135deg,#ffcc80,#ff9800)', 'S,M,L,XL', 'نارنجی', 60, 17, 0, 4.2, 15),
        ('شومیز حریر مشکی', 'شومیز زنانه حریر با طراحی مجلسی', 410000, 520000, 1, 'linear-gradient(135deg,#616161,#212121)', 'S,M,L', 'مشکی', 30, 21, 1, 4.7, 38),
        ('مانتو مجلسی سفید', 'مانتو زنانه مجلسی با طراحی شیک و خاص', 980000, 1250000, 2, 'linear-gradient(135deg,#fafafa,#e0e0e0)', 'S,M,L', 'سفید', 15, 22, 1, 4.9, 52),
        ('شلوار کتان کرم', 'شلوار زنانه کتان با رنگ کرم زیبا', 350000, 420000, 4, 'linear-gradient(135deg,#d7ccc8,#8d6e63)', 'M,L,XL', 'کرم', 45, 17, 0, 4.1, 12),
    ]
    
    for p in products:
        try:
            db.execute('''INSERT INTO products 
                (name, description, price, old_price, category_id, image, sizes, colors, 
                 stock, discount, is_featured, rating, reviews_count) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', p)
        except sqlite3.IntegrityError:
            pass
    
    db.commit()

# ==================== AUTH HELPERS ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('لطفاً ابتدا وارد شوید', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('لطفاً ابتدا وارد شوید', 'warning')
            return redirect(url_for('login'))
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user or not user['is_admin']:
            flash('دسترسی غیرمجاز', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== RATE LIMITING ====================
login_attempts = {}

def rate_limit(max_attempts=5, window=300):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            ip = request.remote_addr
            now = time.time()
            if ip not in login_attempts:
                login_attempts[ip] = []
            login_attempts[ip] = [t for t in login_attempts[ip] if now - t < window]
            if len(login_attempts[ip]) >= max_attempts:
                flash('تعداد تلاش‌های ورود بیش از حد مجاز است. لطفاً ۵ دقیقه صبر کنید.', 'danger')
                return redirect(url_for('login'))
            login_attempts[ip].append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(e):
    return render_template('index.html', categories=[], featured=[], products=[], settings={}), 404

@app.errorhandler(500)
def server_error(e):
    return 'خطای سرور', 500

# ==================== SECURITY MIDDLEWARE ====================
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response



# ==================== SMS SERVICE ====================
def send_welcome_sms(phone, name):
    """Send welcome SMS to new users - integrate with SMS provider"""
    # TODO: Integrate with SMS provider (e.g., Kavenegar, SMS.ir, etc.)
    # Example with Kavenegar:
    # import requests
    # api_key = os.environ.get('KAVE_NEGAR_API', '')
    # sender = os.environ.get('SMS_SENDER', '')
    # if api_key and sender and phone:
    #     url = f"https://api.kavenegar.com/v1/{api_key}/send.json"
    #     data = {'receptor': phone, 'sender': sender, 'message': f'خوش آمدید {name}!\nفروشگاه مزون هدیه\nwww.mezonehediye.ir'}
    #     requests.post(url, data=data)
    print(f"[SMS] Welcome message sent to {phone} for {name}")
    return True


# ==================== MAIN ROUTES ====================
@app.route('/')
def home():
    db = get_db()
    categories = db.execute('SELECT * FROM categories').fetchall()
    featured = db.execute('SELECT * FROM products WHERE is_featured = 1 AND is_active = 1 LIMIT 6').fetchall()
    products = db.execute('SELECT * FROM products WHERE is_active = 1 ORDER BY created_at DESC LIMIT 12').fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('index.html', categories=categories, featured=featured, 
                         products=products, settings=settings)

@app.route('/products')
def products_page():
    db = get_db()
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'default')
    min_price = request.args.get('min_price', 0, type=int)
    max_price = request.args.get('max_price', 999999999, type=int)
    
    query = 'SELECT * FROM products WHERE is_active = 1'
    params = []
    
    if category:
        query += ' AND category_id = (SELECT id FROM categories WHERE slug = ?)'
        params.append(category)
    
    if search:
        query += ' AND name LIKE ?'
        params.append(f'%{search}%')
    
    if min_price > 0:
        query += ' AND price >= ?'
        params.append(min_price)
    
    if max_price < 999999999:
        query += ' AND price <= ?'
        params.append(max_price)
    
    if sort == 'cheapest':
        query += ' ORDER BY price ASC'
    elif sort == 'expensive':
        query += ' ORDER BY price DESC'
    elif sort == 'popular':
        query += ' ORDER BY reviews_count DESC'
    else:
        query += ' ORDER BY created_at DESC'
    
    products = db.execute(query, params).fetchall()
    categories = db.execute('SELECT * FROM categories').fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    
    return render_template('products.html', products=products, categories=categories,
                         settings=settings, current_category=category, current_search=search)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product:
        flash('محصول یافت نشد', 'warning')
        return redirect(url_for('home'))
    
    category = db.execute('SELECT * FROM categories WHERE id = ?', (product['category_id'],)).fetchone()
    related = db.execute('SELECT * FROM products WHERE category_id = ? AND id != ? LIMIT 4',
                        (product['category_id'], product_id)).fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    
    return render_template('product_detail.html', product=product, category=category,
                         related=related, settings=settings)

# ==================== CART ====================
@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    db = get_db()
    items = []
    total = 0
    
    for item in cart_items:
        product = db.execute('SELECT * FROM products WHERE id = ?', (item['product_id'],)).fetchone()
        if product:
            item_total = product['price'] * item['quantity']
            total += item_total
            items.append({
                'product': product,
                'size': item.get('size', ''),
                'color': item.get('color', ''),
                'quantity': item['quantity'],
                'total': item_total
            })
    
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    shipping = int(settings.get('shipping_cost', 30000))
    free_min = int(settings.get('free_shipping_min', 500000))
    
    if total >= free_min:
        shipping = 0
    
    return render_template('cart.html', items=items, total=total, shipping=shipping, settings=settings)

@app.route('/cart/add', methods=['POST'])
def cart_add():
    data = request.get_json()
    cart = session.get('cart', [])
    
    # Check if item already exists
    for item in cart:
        if (item['product_id'] == data['product_id'] and 
            item.get('size') == data.get('size') and
            item.get('color') == data.get('color')):
            item['quantity'] += data.get('quantity', 1)
            session['cart'] = cart
            return jsonify({'success': True, 'message': 'محصول به سبد اضافه شد ✓'})
    
    cart.append({
        'product_id': data['product_id'],
        'size': data.get('size', ''),
        'color': data.get('color', ''),
        'quantity': data.get('quantity', 1)
    })
    
    session['cart'] = cart
    return jsonify({'success': True, 'message': 'محصول به سبد اضافه شد ✓'})

@app.route('/cart/update', methods=['POST'])
def cart_update():
    data = request.get_json()
    cart = session.get('cart', [])
    
    if data['action'] == 'increase':
        for item in cart:
            if item['product_id'] == data['product_id']:
                item['quantity'] += 1
                break
    elif data['action'] == 'decrease':
        for i, item in enumerate(cart):
            if item['product_id'] == data['product_id']:
                if item['quantity'] > 1:
                    item['quantity'] -= 1
                else:
                    cart.pop(i)
                break
    elif data['action'] == 'remove':
        cart = [item for item in cart if item['product_id'] != data['product_id']]
    
    session['cart'] = cart
    return jsonify({'success': True})

@app.route('/cart/count')
def cart_count():
    cart = session.get('cart', [])
    count = sum(item['quantity'] for item in cart)
    return jsonify({'count': count})

# ==================== CHECKOUT & PAYMENT ====================
@app.route('/checkout')
@login_required
def checkout():
    cart_items = session.get('cart', [])
    if not cart_items:
        flash('سبد خرید شما خالی است', 'warning')
        return redirect(url_for('home'))
    
    db = get_db()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    items = []
    total = 0
    for item in cart_items:
        product = db.execute('SELECT * FROM products WHERE id = ?', (item['product_id'],)).fetchone()
        if product:
            item_total = product['price'] * item['quantity']
            total += item_total
            items.append({
                'product': product,
                'size': item.get('size', ''),
                'quantity': item['quantity'],
                'total': item_total
            })
    
    shipping = int(settings.get('shipping_cost', 30000))
    free_min = int(settings.get('free_shipping_min', 500000))
    if total >= free_min:
        shipping = 0
    
    return render_template('checkout.html', items=items, total=total, 
                         shipping=shipping, user=user, settings=settings)

@app.route('/checkout/confirm', methods=['POST'])
@login_required
def checkout_confirm():
    cart_items = session.get('cart', [])
    if not cart_items:
        return redirect(url_for('home'))
    
    db = get_db()
    
    # Get form data
    full_name = request.form.get('full_name', '')
    phone = request.form.get('phone', '')
    address = request.form.get('address', '')
    city = request.form.get('city', '')
    
    # Calculate total
    total = 0
    for item in cart_items:
        product = db.execute('SELECT * FROM products WHERE id = ?', (item['product_id'],)).fetchone()
        if product:
            total += product['price'] * item['quantity']
    
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    shipping = int(settings.get('shipping_cost', 30000))
    free_min = int(settings.get('free_shipping_min', 500000))
    if total >= free_min:
        shipping = 0
    
    total += shipping
    
    # Create order
    cursor = db.execute('''INSERT INTO orders 
        (user_id, full_name, phone, address, city, total_amount, status, payment_status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', 'unpaid')''',
        (session['user_id'], full_name, phone, address, city, total))
    
    order_id = cursor.lastrowid
    
    # Create order items
    for item in cart_items:
        product = db.execute('SELECT * FROM products WHERE id = ?', (item['product_id'],)).fetchone()
        if product:
            db.execute('''INSERT INTO order_items 
                (order_id, product_id, product_name, size, quantity, price)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (order_id, product['id'], product['name'], 
                 item.get('size', ''), item['quantity'], product['price']))
    
    db.commit()
    
    # Clear cart
    session['cart'] = []
    
    # Redirect to payment (ZarinPal)
    # For now, just show order confirmation
    flash(f'سفارش شما با شماره {order_id} ثبت شد! 🎉', 'success')
    return redirect(url_for('order_detail', order_id=order_id))

@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id = ? AND user_id = ?',
                      (order_id, session['user_id'])).fetchone()
    if not order:
        flash('سفارش یافت نشد', 'warning')
        return redirect(url_for('home'))
    
    items = db.execute('''SELECT oi.*, p.image FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?''', (order_id,)).fetchall()
    
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('order_detail.html', order=order, items=items, settings=settings)

@app.route('/orders')
@login_required
def orders():
    db = get_db()
    orders = db.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC',
                       (session['user_id'],)).fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('orders.html', orders=orders, settings=settings)

# ==================== AUTH ====================
@app.route('/login', methods=['GET', 'POST'])
@rate_limit(max_attempts=5, window=300)
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            flash(f'خوش آمدید {user["full_name"] or user["username"]}! 👋', 'success')
            
            if user['is_admin']:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('home'))
        
        flash('نام کاربری یا رمز عبور اشتباه است', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '')
        phone = request.form.get('phone', '')
        
        if not username or not email or not password:
            flash('لطفاً تمام فیلدها را پر کنید', 'warning')
        elif len(password) < 6:
            flash('رمز عبور باید حداقل ۶ کاراکتر باشد', 'warning')
            return render_template('register.html')
        
        db = get_db()
        try:
            db.execute('''INSERT INTO users (username, email, password, full_name, phone)
                VALUES (?, ?, ?, ?, ?)''',
                (username, email, generate_password_hash(password), full_name, phone))
            db.commit()
            flash('ثبت‌نام موفقیت‌آمیز بود! 🎉', 'success')
            # Send welcome SMS
            if phone:
                send_welcome_sms(phone, full_name or username)
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('نام کاربری یا ایمیل قبلاً استفاده شده', 'danger')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('با موفقیت خارج شدید', 'info')
    return redirect(url_for('home'))

@app.route('/profile')
@login_required
def profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('profile.html', user=user, settings=settings)

@app.route('/profile/update', methods=['POST'])
@login_required
def profile_update():
    db = get_db()
    full_name = request.form.get('full_name', '')
    phone = request.form.get('phone', '')
    address = request.form.get('address', '')
    
    db.execute('''UPDATE users SET full_name = ?, phone = ?, address = ? WHERE id = ?''',
              (full_name, phone, address, session['user_id']))
    db.commit()
    flash('پروفایل بروزرسانی شد ✓', 'success')
    return redirect(url_for('profile'))

# ==================== ADMIN PANEL ====================
@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        'total_orders': db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
        'pending_orders': db.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0],
        'total_products': db.execute('SELECT COUNT(*) FROM products').fetchone()[0],
        'total_users': db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'total_revenue': db.execute("SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE payment_status = 'paid'").fetchone()[0],
    }
    recent_orders = db.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT 10').fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('admin/dashboard.html', stats=stats, recent_orders=recent_orders, settings=settings)

@app.route('/admin/products')
@admin_required
def admin_products():
    db = get_db()
    products = db.execute('''SELECT p.*, c.name as category_name 
        FROM products p LEFT JOIN categories c ON p.category_id = c.id
        ORDER BY p.created_at DESC''').fetchall()
    categories = db.execute('SELECT * FROM categories').fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('admin/products.html', products=products, categories=categories, settings=settings)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_product_add():
    db = get_db()
    categories = db.execute('SELECT * FROM categories').fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    
    if request.method == 'POST':
        name = request.form.get('name', '')
        description = request.form.get('description', '')
        price = request.form.get('price', 0, type=int)
        old_price = request.form.get('old_price', 0, type=int)
        category_id = request.form.get('category_id', 0, type=int)
        sizes = request.form.get('sizes', '36,38,40,42,44,46')
        colors = request.form.get('colors', '')
        stock = request.form.get('stock', 100, type=int)
        is_featured = 1 if request.form.get('is_featured') else 0
        
        # Handle image upload
        image_url = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
                if ext in ALLOWED_EXTENSIONS:
                    import base64 as b64
                    file_data = file.read()
                    b64_string = b64.b64encode(file_data).decode('utf-8')
                    image_url = f'data:image/{ext};base64,{b64_string}'
        
        discount = 0
        if old_price > 0 and price > 0:
            discount = round((old_price - price) / old_price * 100)
        
        db.execute('''INSERT INTO products 
            (name, description, price, old_price, category_id, sizes, colors, stock, discount, is_featured, image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, description, price, old_price, category_id, sizes, colors, stock, discount, is_featured, image_url))
        db.commit()
        
        flash('محصول اضافه شد ✓', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin/product_form.html', product=None, categories=categories, settings=settings)

@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_product_edit(product_id):
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    categories = db.execute('SELECT * FROM categories').fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    
    if request.method == 'POST':
        name = request.form.get('name', '')
        description = request.form.get('description', '')
        price = request.form.get('price', 0, type=int)
        old_price = request.form.get('old_price', 0, type=int)
        category_id = request.form.get('category_id', 0, type=int)
        sizes = request.form.get('sizes', '36,38,40,42,44,46')
        colors = request.form.get('colors', '')
        stock = request.form.get('stock', 100, type=int)
        is_featured = 1 if request.form.get('is_featured') else 0
        is_active = 1 if request.form.get('is_active') else 0
        
        # Handle image upload
        image_url = product['image'] if product else ''
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
                if ext in ALLOWED_EXTENSIONS:
                    import base64 as b64
                    file_data = file.read()
                    b64_string = b64.b64encode(file_data).decode('utf-8')
                    image_url = f'data:image/{ext};base64,{b64_string}'
        
        discount = 0
        if old_price > 0 and price > 0:
            discount = round((old_price - price) / old_price * 100)
        
        db.execute('''UPDATE products SET 
            name=?, description=?, price=?, old_price=?, category_id=?, 
            sizes=?, colors=?, stock=?, discount=?, is_featured=?, is_active=?, image=?
            WHERE id=?''',
            (name, description, price, old_price, category_id, sizes, colors,
             stock, discount, is_featured, is_active, image_url, product_id))
        db.commit()
        
        flash('محصول بروزرسانی شد ✓', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin/product_form.html', product=product, categories=categories, settings=settings)

@app.route('/admin/products/delete/<int:product_id>', methods=['POST'])
@admin_required
def admin_product_delete(product_id):
    db = get_db()
    db.execute('DELETE FROM products WHERE id = ?', (product_id,))
    db.commit()
    flash('محصول حذف شد ✓', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    db = get_db()
    status = request.args.get('status', '')
    query = 'SELECT * FROM orders'
    params = []
    
    if status:
        query += ' WHERE status = ?'
        params.append(status)
    
    query += ' ORDER BY created_at DESC'
    orders = db.execute(query, params).fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('admin/orders.html', orders=orders, settings=settings, current_status=status)

@app.route('/admin/orders/<int:order_id>')
@admin_required
def admin_order_detail(order_id):
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    items = db.execute('''SELECT oi.*, p.image FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?''', (order_id,)).fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('admin/order_detail.html', order=order, items=items, settings=settings)

@app.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@admin_required
def admin_order_status(order_id):
    db = get_db()
    status = request.form.get('status', '')
    tracking = request.form.get('tracking_code', '')
    note = request.form.get('note', '')
    
    db.execute('UPDATE orders SET status=?, tracking_code=?, note=? WHERE id=?',
              (status, tracking, note, order_id))
    db.commit()
    flash('وضعیت سفارش بروزرسانی شد ✓', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    db = get_db()
    if request.method == 'POST':
        for key in request.form:
            db.execute('UPDATE settings SET value = ? WHERE key = ?', (request.form[key], key))
        db.commit()
        flash('تنظیمات بروزرسانی شد ✓', 'success')
        return redirect(url_for('admin_settings'))
    
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('admin/settings.html', settings=settings)

@app.route('/admin/users')
@admin_required
def admin_users():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    return render_template('admin/users.html', users=users, settings=settings)


@app.route('/admin/upload-image', methods=['POST'])
@admin_required
def admin_upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'فایلی انتخاب نشد'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'فایلی انتخاب نشد'}), 400
    
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': 'فرمت فایل مجاز نیست'}), 400
    
    filename = f"{secrets.token_hex(8)}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(filepath)
    
    return jsonify({'success': True, 'url': f'/uploads/{filename}', 'filename': filename})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/admin/change-password', methods=['POST'])
@admin_required
def admin_change_password():
    current = request.form.get('current_password', '')
    new_pass = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    
    if not current or not new_pass:
        flash('لطفاً تمام فیلدها را پر کنید', 'warning')
        return redirect(url_for('admin_settings'))
    
    if new_pass != confirm:
        flash('رمز جدید و تکرار آن مطابقت ندارند', 'danger')
        return redirect(url_for('admin_settings'))
    
    if len(new_pass) < 6:
        flash('رمز عبور باید حداقل ۶ کاراکتر باشد', 'warning')
        return redirect(url_for('admin_settings'))
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if not check_password_hash(user['password'], current):
        flash('رمز فعلی اشتباه است', 'danger')
        return redirect(url_for('admin_settings'))
    
    db.execute('UPDATE users SET password = ? WHERE id = ?', 
               (generate_password_hash(new_pass), session['user_id']))
    db.commit()
    flash('رمز عبور با موفقیت تغییر کرد ✓', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/change-username', methods=['POST'])
@admin_required
def admin_change_username():
    new_username = request.form.get('new_username', '').strip()
    
    if not new_username:
        flash('نام کاربری جدید را وارد کنید', 'warning')
        return redirect(url_for('admin_settings'))
    
    if len(new_username) < 3:
        flash('نام کاربری باید حداقل ۳ کاراکتر باشد', 'warning')
        return redirect(url_for('admin_settings'))
    
    db = get_db()
    existing = db.execute('SELECT id FROM users WHERE username = ? AND id != ?', 
                         (new_username, session['user_id'])).fetchone()
    if existing:
        flash('این نام کاربری قبلاً استفاده شده', 'danger')
        return redirect(url_for('admin_settings'))
    
    db.execute('UPDATE users SET username = ? WHERE id = ?', 
               (new_username, session['user_id']))
    db.commit()
    session['username'] = new_username
    flash('نام کاربری با موفقیت تغییر کرد ✓', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/add-category', methods=['POST'])
@admin_required
def admin_add_category():
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', '📁').strip()
    
    if not name:
        flash('نام دسته‌بندی را وارد کنید', 'warning')
        return redirect(url_for('admin_settings'))
    
    db = get_db()
    db.execute('INSERT INTO categories (name, icon, is_active) VALUES (?, ?, 1)', (name, icon))
    db.commit()
    flash(f'دسته‌بندی "{name}" اضافه شد ✓', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/delete-category/<int:cat_id>', methods=['POST'])
@admin_required
def admin_delete_category(cat_id):
    db = get_db()
    db.execute('DELETE FROM categories WHERE id = ?', (cat_id,))
    db.commit()
    flash('دسته‌بندی حذف شد ✓', 'success')
    return redirect(url_for('admin_settings'))


@app.route('/admin/shipping-methods', methods=['POST'])
@admin_required
def admin_shipping_methods():
    db = get_db()
    
    # Get all shipping method data
    methods = [
        {'key': 'shipping_tipax', 'name': 'تیپاکس'},
        {'key': 'shipping_post', 'name': 'پست پیشتاز'},
        {'key': 'shipping_tnt', 'name': 'TNT'},
        {'key': 'shipping_collect', 'name': 'پس کرایه'},
    ]
    
    for method in methods:
        enabled = request.form.get(f"{method['key']}_enabled", '0')
        cost = request.form.get(f"{method['key']}_cost", '0')
        
        # Check if exists
        existing = db.execute('SELECT key FROM settings WHERE key = ?', (f"{method['key']}_enabled",)).fetchone()
        if existing:
            db.execute('UPDATE settings SET value = ? WHERE key = ?', (enabled, f"{method['key']}_enabled"))
            db.execute('UPDATE settings SET value = ? WHERE key = ?', (cost, f"{method['key']}_cost"))
        else:
            db.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (f"{method['key']}_enabled", enabled))
            db.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (f"{method['key']}_cost", cost))
    
    db.commit()
    flash('روش‌های ارسال بروزرسانی شد ✓', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/payment-gateways', methods=['POST'])
@admin_required
def admin_payment_gateways():
    db = get_db()
    
    gateways = [
        {'key': 'gateway_zarinpal', 'name': 'زرین‌پال'},
        {'key': 'gateway_snapp', 'name': 'اسنپ‌پی'},
        {'key': 'gateway_digipay', 'name': 'دیجی‌پی'},
        {'key': 'gateway_idpay', 'name': 'آیدی‌پی'},
        {'key': 'gateway_nextpay', 'name': 'نکست‌پی'},
        {'key': 'gateway_cod', 'name': 'پرداخت درب منزل'},
    ]
    
    for gw in gateways:
        enabled = request.form.get(f"{gw['key']}_enabled", '0')
        merchant = request.form.get(f"{gw['key']}_merchant", '')
        
        existing = db.execute('SELECT key FROM settings WHERE key = ?', (f"{gw['key']}_enabled",)).fetchone()
        if existing:
            db.execute('UPDATE settings SET value = ? WHERE key = ?', (enabled, f"{gw['key']}_enabled"))
            db.execute('UPDATE settings SET value = ? WHERE key = ?', (merchant, f"{gw['key']}_merchant"))
        else:
            db.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (f"{gw['key']}_enabled", enabled))
            db.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (f"{gw['key']}_merchant", merchant))
    
    db.commit()
    flash('درگاه‌های پرداخت بروزرسانی شد ✓', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/cover', methods=['POST'])
@admin_required
def admin_cover():
    if 'cover_image' not in request.files:
        flash('فایلی انتخاب نشد', 'warning')
        return redirect(url_for('admin_settings'))
    
    file = request.files['cover_image']
    if file.filename == '':
        flash('فایلی انتخاب نشد', 'warning')
        return redirect(url_for('admin_settings'))
    
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        flash('فرمت فایل مجاز نیست', 'danger')
        return redirect(url_for('admin_settings'))
    
    filename = f"cover_{secrets.token_hex(8)}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(filepath)
    
    db = get_db()
    existing = db.execute('SELECT key FROM settings WHERE key = ?', ('cover_image',)).fetchone()
    if existing:
        db.execute('UPDATE settings SET value = ? WHERE key = ?', (f'/uploads/{filename}', 'cover_image'))
    else:
        db.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ('cover_image', f'/uploads/{filename}'))
    db.commit()
    
    flash('کاور صفحه اصلی بروزرسانی شد ✓', 'success')
    return redirect(url_for('admin_settings'))


@app.route('/tryon/<int:product_id>')
def virtual_tryon(product_id):
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product:
        flash('محصول یافت نشد', 'warning')
        return redirect(url_for('home'))
    
    settings = {row['key']: row['value'] for row in db.execute('SELECT * FROM settings').fetchall()}
    
    # Get available colors
    colors = []
    if product['colors']:
        colors = [c.strip() for c in product['colors'].split(',')]
    
    # Default mannequin colors
    mannequin_colors = [
        {'name': 'سفید', 'hex': '#FFFFFF'},
        {'name': 'کرم', 'hex': '#F5F5DC'},
        {'name': 'صورتی', 'hex': '#FFB6C1'},
        {'name': 'طوسی', 'hex': '#808080'},
        {'name': 'مشکی', 'hex': '#000000'},
    ]
    
    return render_template('tryon.html', product=product, colors=colors, 
                         mannequin_colors=mannequin_colors, settings=settings)

# ==================== API ====================
@app.route('/api/cart/add', methods=['POST'])
def api_cart_add():
    data = request.get_json()
    cart = session.get('cart', [])
    
    for item in cart:
        if (item['product_id'] == data['product_id'] and 
            item.get('size') == data.get('size')):
            item['quantity'] += data.get('quantity', 1)
            session['cart'] = cart
            return jsonify({'success': True, 'count': sum(i['quantity'] for i in cart)})
    
    cart.append({
        'product_id': data['product_id'],
        'size': data.get('size', ''),
        'quantity': data.get('quantity', 1)
    })
    session['cart'] = cart
    return jsonify({'success': True, 'count': sum(i['quantity'] for i in cart)})

# ==================== INIT DB ON STARTUP ====================
with app.app_context():
    init_db()

# ==================== MAIN ====================
import os

@app.route('/admin/setup-demo-images')
def setup_demo_images():
    """Setup demo images for products - run once"""
    from flask import session as sess
    if not sess.get('user_id'):
        return redirect(url_for('login'))
    
    db = get_db()
    demo_images = {
        1: 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=600&h=800&fit=crop',
        2: 'https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=600&h=800&fit=crop',
        3: 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=600&h=800&fit=crop',
        4: 'https://images.unsplash.com/photo-1582552938357-32b906df40cb?w=600&h=800&fit=crop',
        5: 'https://images.unsplash.com/photo-1583846783214-0a5e3c8a8f8c?w=600&h=800&fit=crop',
        6: 'https://images.unsplash.com/photo-1551803091-e20673f15770?w=600&h=800&fit=crop',
        7: 'https://images.unsplash.com/photo-1434389677669-e08b4cda3a43?w=600&h=800&fit=crop',
        8: 'https://images.unsplash.com/photo-1596783074918-c44d8a39e0d2?w=600&h=800&fit=crop',
        9: 'https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=600&h=800&fit=crop',
        10: 'https://images.unsplash.com/photo-1506629082955-511b1aa562c8?w=600&h=800&fit=crop',
    }
    
    for pid, url in demo_images.items():
        db.execute('UPDATE products SET image = ? WHERE id = ?', (url, pid))
    db.commit()
    
    flash('عکس‌های نمونه اضافه شد ✓', 'success')
    return redirect(url_for('admin_products'))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
