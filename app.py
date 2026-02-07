import os
import json
import io
import random  # <--- FIXED: Added missing import
import uuid 
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from sqlalchemy import func

# --- CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'baba_car_bazar_mega_key_2026_unbreakable') 

# --- DATABASE CONFIGURATION ---
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///babacarbazar_mega.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- PATH CONFIGURATION (For GitHub Images) ---
basedir = os.path.abspath(os.path.dirname(__file__))
upload_folder_path = os.path.join(basedir, 'static/uploads')
app.config['UPLOAD_FOLDER'] = upload_folder_path

# Ensure folder exists
if not os.path.exists(upload_folder_path):
    os.makedirs(upload_folder_path)

# --- EXTENSIONS ---
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    wishlist = db.relationship('Wishlist', backref='user', lazy=True)
    test_drives = db.relationship('TestDrive', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    brand = db.Column(db.String(50))
    category = db.Column(db.String(50))
    price = db.Column(db.Integer)
    year = db.Column(db.Integer)
    fuel = db.Column(db.String(20))
    transmission = db.Column(db.String(20))
    km_driven = db.Column(db.Integer)
    description = db.Column(db.Text)
    images = db.Column(db.Text, default='["default.jpg"]') 
    status = db.Column(db.String(20), default='Available')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviews = db.relationship('Review', backref='car', lazy=True)

class Enquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    message = db.Column(db.Text)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    date = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    car = db.relationship('Car')

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    car = db.relationship('Car')

class TestDrive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    date_booked = db.Column(db.String(50)) 
    time_slot = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Pending') 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    car = db.relationship('Car')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PromoCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True)
    discount_amount = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)

class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.Text) 
    title = db.Column(db.String(100))
    subtitle = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)

# --- MODEL: IMAGE STORAGE (DB) ---
class ImagePool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)
    data = db.Column(db.LargeBinary) 
    mimetype = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- HELPER: SAFE INT ---
def safe_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

# --- HELPER: SAVE IMAGE TO DB ---
def save_image_to_db(file, preserve_name=False):
    if not file or file.filename == '':
        return None
    
    file_data = file.read()
    
    if preserve_name:
        # About Us images: keep exact name
        unique_name = secure_filename(file.filename)
        existing = ImagePool.query.filter_by(name=unique_name).first()
        if existing:
            existing.data = file_data
            existing.mimetype = file.mimetype or 'image/jpeg'
            db.session.commit()
            return unique_name
    else:
        # Car/Banner images: unique ID
        ext = os.path.splitext(file.filename)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
    
    if not ImagePool.query.filter_by(name=unique_name).first():
        new_img = ImagePool(name=unique_name, data=file_data, mimetype=file.mimetype or 'image/jpeg')
        db.session.add(new_img)
        db.session.commit()
        
    return unique_name

# --- PUBLIC ROUTES ---

@app.route('/')
def home():
    featured = Car.query.filter_by(status='Available').order_by(Car.created_at.desc()).limit(6).all()
    suvs = Car.query.filter_by(category='SUV', status='Available').limit(3).all()
    sedans = Car.query.filter_by(category='Sedan', status='Available').limit(3).all()
    banners = Banner.query.filter_by(is_active=True).all()
    if not banners: banners = []
    latest_promo = PromoCode.query.filter_by(is_active=True).order_by(PromoCode.id.desc()).first()
    
    for c_list in [featured, suvs, sedans]:
        for car in c_list:
            try: car.img_list = json.loads(car.images)
            except: car.img_list = ['default.jpg']
            
    return render_template('index.html', page='home', cars=featured, suvs=suvs, sedans=sedans, banners=banners, latest_promo=latest_promo)

# --- HYBRID IMAGE ROUTE (DB FIRST, THEN DISK) ---
@app.route('/static/uploads/<path:filename>')
def custom_static(filename):
    # 1. Try DB (Best for new/recovered uploads)
    img_entry = ImagePool.query.filter_by(name=filename).first()
    if img_entry:
        return send_file(io.BytesIO(img_entry.data), mimetype=img_entry.mimetype)
    
    # 2. Try Physical File (For GitHub assets like naman.jpeg)
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except:
        return "Image not found", 404

@app.route('/inventory')
def inventory():
    query = Car.query
    brand_filter = request.args.get('brand')
    fuel_filter = request.args.get('fuel')
    min_price = request.args.get('min_price', type=int)
    max_price = request.args.get('max_price', type=int)

    if brand_filter: query = query.filter(Car.brand == brand_filter)
    if fuel_filter: query = query.filter(Car.fuel == fuel_filter)
    if min_price: query = query.filter(Car.price >= min_price)
    if max_price: query = query.filter(Car.price <= max_price)

    all_cars = query.order_by(Car.created_at.desc()).all()
    brands = [r.brand for r in db.session.query(Car.brand).distinct()]
    
    for car in all_cars:
        try: car.img_list = json.loads(car.images)
        except: car.img_list = ['default.jpg']
        ratings = [r.rating for r in car.reviews]
        car.avg_rating = sum(ratings)/len(ratings) if ratings else 0
        
    return render_template('index.html', page='inventory', cars=all_cars, brands=brands)

@app.route('/car/<int:car_id>')
def car_detail(car_id):
    car = Car.query.get_or_404(car_id)
    try: car.img_list = json.loads(car.images)
    except: car.img_list = ['default.jpg']
    
    if not isinstance(car.img_list, list): car.img_list = [car.img_list]

    similar = Car.query.filter(Car.category == car.category, Car.id != car.id).limit(3).all()
    for s in similar:
        try: s.img_list = json.loads(s.images)
        except: s.img_list = ['default.jpg']
        
    reviews = Review.query.filter_by(car_id=car.id).order_by(Review.created_at.desc()).all()
    avg_rating = 0
    if reviews:
        avg_rating = sum([r.rating for r in reviews]) / len(reviews)
        
    return render_template('index.html', page='detail', car=car, similar=similar, reviews=reviews, avg_rating=round(avg_rating, 1))

@app.route('/sell-car')
def sell_car():
    return render_template('index.html', page='sell')

@app.route('/about')
def about():
    return render_template('aboutus.html')

# --- USER ACTIONS ---

@app.route('/profile')
@login_required
def profile():
    w_items = Wishlist.query.filter_by(user_id=current_user.id).all()
    wishlist_cars = [item.car for item in w_items]
    for car in wishlist_cars:
        try: car.img_list = json.loads(car.images)
        except: car.img_list = ['default.jpg']
    my_drives = TestDrive.query.filter_by(user_id=current_user.id).order_by(TestDrive.created_at.desc()).all()
    return render_template('index.html', page='profile', wishlist=wishlist_cars, drives=my_drives)

@app.route('/wishlist/toggle/<int:car_id>')
@login_required
def toggle_wishlist(car_id):
    existing = Wishlist.query.filter_by(user_id=current_user.id, car_id=car_id).first()
    if existing: db.session.delete(existing)
    else: db.session.add(Wishlist(user_id=current_user.id, car_id=car_id))
    db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/book-test-drive', methods=['POST'])
@login_required
def book_test_drive():
    car_id = request.form.get('car_id')
    date = request.form.get('date')
    time = request.form.get('time')
    if not date or not time:
        flash("Please select both Date and Time.", "warning")
        return redirect(request.referrer)
    new_td = TestDrive(user_id=current_user.id, car_id=car_id, date_booked=date, time_slot=time)
    db.session.add(new_td)
    db.session.commit()
    flash("Test Drive Requested!", "success")
    return redirect(url_for('profile'))

@app.route('/add-review', methods=['POST'])
@login_required
def add_review():
    car_id = request.form.get('car_id')
    rating = safe_int(request.form.get('rating'))
    comment = request.form.get('comment')
    new_rev = Review(user_id=current_user.id, car_id=car_id, rating=rating, comment=comment)
    db.session.add(new_rev)
    db.session.commit()
    flash("Review Added!", "success")
    return redirect(url_for('car_detail', car_id=car_id))

@app.route('/apply-promo', methods=['POST'])
def apply_promo():
    code_input = request.json.get('code')
    promo = PromoCode.query.filter_by(code=code_input, is_active=True).first()
    if promo: return jsonify({'valid': True, 'discount': promo.discount_amount})
    else: return jsonify({'valid': False})

# --- AUTH ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin')) if user.is_admin else redirect(url_for('home'))
        else:
            flash("Invalid credentials", "danger")
    return render_template('index.html', page='login')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            flash("Email exists", "warning")
        else:
            hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(name=name, email=email, password=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            flash("Account created", "success")
            return redirect(url_for('login'))
    return render_template('index.html', page='signup')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- API ROUTES ---

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').lower()
    cars = Car.query.filter((Car.name.ilike(f'%{query}%')) | (Car.brand.ilike(f'%{query}%'))).all()
    results = []
    for car in cars:
        try: img = json.loads(car.images)[0]
        except: img = 'default.jpg'
        results.append({'id': car.id, 'name': car.name, 'price': car.price, 'image': img})
    return jsonify(results)

@app.route('/api/predict_price', methods=['POST'])
def predict_price():
    data = request.json
    try:
        year = int(data.get('year'))
        km = int(data.get('km'))
        base = 800000 
        age = 2026 - year
        price = base * (0.90 ** age) - (km * 1.5)
        price = price * random.uniform(0.95, 1.05)
        return jsonify({'price': int(max(price, 50000))})
    except:
        return jsonify({'price': 0})

@app.route('/enquire', methods=['POST'])
def enquire():
    car_id = request.form.get('car_id')
    new_enq = Enquiry(name=request.form.get('name'), phone=request.form.get('phone'), message=request.form.get('message'), car_id=car_id)
    db.session.add(new_enq)
    db.session.commit()
    flash("Message Sent Successfully!", "success")
    return redirect(url_for('car_detail', car_id=car_id))

# --- ADMIN ROUTES ---

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin: return redirect(url_for('home'))
    
    stats = {
        'total': Car.query.count(),
        'value': db.session.query(db.func.sum(Car.price)).scalar() or 0,
        'unread': Enquiry.query.filter_by(is_read=False).count(),
        'sold': Car.query.filter_by(status='Sold').count()
    }
    
    cars = Car.query.order_by(Car.created_at.desc()).all()
    for car in cars:
        try: car.img_list = json.loads(car.images)
        except: car.img_list = ['default.jpg']
        
    enquiries = Enquiry.query.order_by(Enquiry.date.desc()).all()
    test_drives = TestDrive.query.order_by(TestDrive.created_at.desc()).all()
    promos = PromoCode.query.all()
    banners = Banner.query.all() 
    
    status_counts = db.session.query(Car.status, func.count(Car.status)).group_by(Car.status).all()
    status_data = {s[0]: s[1] for s in status_counts}
    
    last_7_days = [(datetime.utcnow() - timedelta(days=i)).strftime('%d %b') for i in range(6, -1, -1)]
    # FIXED: Added import random, so this line will now work
    graph_data = [random.randint(1, 10) for _ in range(7)] 

    return render_template('index.html', page='admin', stats=stats, cars=cars, enquiries=enquiries, 
                           test_drives=test_drives, promos=promos, banners=banners, status_data=status_data, graph_labels=last_7_days, graph_data=graph_data)


@app.route('/admin/add', methods=['POST'])
@login_required
def add_car():
    if not current_user.is_admin: return redirect(url_for('home'))
    files = request.files.getlist('images')
    img_names = []
    
    for f in files:
        fname = save_image_to_db(f)
        if fname:
            img_names.append(fname)
            
    if not img_names: img_names = ['default.jpg']
    
    new_car = Car(
        name=request.form['name'],
        brand=request.form['brand'],
        category=request.form['category'],
        price=safe_int(request.form['price']),
        year=safe_int(request.form['year']),
        fuel=request.form['fuel'],
        transmission=request.form['transmission'],
        km_driven=safe_int(request.form['km_driven']),
        description=request.form['description'],
        images=json.dumps(img_names)
    )
    db.session.add(new_car)
    db.session.commit()
    flash("Vehicle Added (Images Saved to Database)", "success")
    return redirect(url_for('admin'))

@app.route('/admin/edit/<int:car_id>', methods=['POST'])
@login_required
def edit_car(car_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    car = Car.query.get(car_id)
    if car:
        car.name = request.form['name']
        car.price = safe_int(request.form['price'])
        car.status = request.form['status']
        db.session.commit()
        flash("Vehicle Updated", "success")
    return redirect(url_for('admin'))

@app.route('/admin/delete/<int:car_id>')
@login_required
def delete_car(car_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    car = Car.query.get(car_id)
    if car:
        Wishlist.query.filter_by(car_id=car.id).delete()
        Enquiry.query.filter_by(car_id=car.id).delete()
        TestDrive.query.filter_by(car_id=car.id).delete()
        Review.query.filter_by(car_id=car.id).delete()
        db.session.delete(car)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/enquiry/read/<int:enq_id>')
@login_required
def mark_read(enq_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    enq = Enquiry.query.get(enq_id)
    enq.is_read = True
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/enquiry/delete/<int:enq_id>')
@login_required
def delete_enquiry(enq_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    enq = Enquiry.query.get(enq_id)
    db.session.delete(enq)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/testdrive/update/<int:td_id>/<status>')
@login_required
def update_testdrive(td_id, status):
    if not current_user.is_admin: return redirect(url_for('home'))
    td = TestDrive.query.get(td_id)
    td.status = status
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/promo/create', methods=['POST'])
@login_required
def create_promo():
    if not current_user.is_admin: return redirect(url_for('home'))
    code = request.form.get('code')
    amount = safe_int(request.form.get('amount'))
    db.session.add(PromoCode(code=code, discount_amount=amount))
    db.session.commit()
    flash(f"Promo Code {code} Created", "success")
    return redirect(url_for('admin'))

@app.route('/admin/promo/delete/<int:p_id>')
@login_required
def delete_promo(p_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    p = PromoCode.query.get(p_id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/banner/add', methods=['POST'])
@login_required
def add_banner():
    if not current_user.is_admin: return redirect(url_for('home'))
    file = request.files.get('image')
    title = request.form.get('title')
    subtitle = request.form.get('subtitle')
    
    fname = save_image_to_db(file)
    if fname:
        db.session.add(Banner(image=fname, title=title, subtitle=subtitle, is_active=True))
        db.session.commit()
        flash("Banner Added", "success")
    else:
        flash("No file selected", "warning")
        
    return redirect(url_for('admin'))

@app.route('/admin/banner/delete/<int:b_id>')
@login_required
def delete_banner(b_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    b = Banner.query.get(b_id)
    db.session.delete(b)
    db.session.commit()
    return redirect(url_for('admin'))

# --- UPLOAD TOOL (FALLBACK) ---
@app.route('/admin/upload-site-images', methods=['GET', 'POST'])
@login_required
def upload_site_images():
    if not current_user.is_admin: return redirect(url_for('home'))
    if request.method == 'POST':
        files = request.files.getlist('files')
        uploaded = []
        for f in files:
            name = save_image_to_db(f, preserve_name=True)
            uploaded.append(name)
        return f"<h3>Uploaded: {', '.join(uploaded)}</h3><a href='/admin'>Back</a>"
    return """
    <html><body>
        <h2>Upload Site Assets (Owner Images)</h2>
        <form method="post" enctype="multipart/form-data">
            <input type="file" name="files" multiple>
            <input type="submit" value="Upload">
        </form>
    </body></html>
    """

# --- DB SETUP & FIX ---
with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='babaadmin@gmail.com').first():
        admin_pass = generate_password_hash('@namanadmin', method='pbkdf2:sha256')
        db.session.add(User(name='BABA-CAR_BAZAR', email='babaadmin@gmail.com', password=admin_pass, is_admin=True))
        db.session.commit()
        print("Admin Account Created.")

@app.route('/fix-db')
def fix_db():
    try:
        db.create_all()
        try:
            Banner.__table__.drop(db.engine)
            db.create_all()
        except: pass
        return "SUCCESS: Database Fixed & ImagePool Ready."
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
