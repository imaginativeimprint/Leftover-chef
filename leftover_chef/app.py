from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from database import Database
import bcrypt
from functools import wraps
from datetime import datetime, timedelta
from decimal import Decimal  # <-- ADDED FOR PRECISION MATCHING WITH DB

app = Flask(__name__)
app.secret_key = 'leftover-chef-secret-key-2024'

db = Database()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function for recipe images
def get_recipe_image(recipe_id):
    image_map = {
        1: 'cucumber_salad.jpg', 2: 'tomato_sabzi.jpg', 3: 'cabbage_sabzi.jpg',
        4: 'cauliflower_stirfry.jpg', 5: 'bhindi_masala.jpg', 6: 'baingan_bharta.jpg',
        7: 'mixed_veg_curry.jpg', 8: 'cucumber_onion_salad.jpg', 9: 'tomato_cucumber_salad.jpg',
        10: 'cabbage_carrot_slaw.jpg', 11: 'lemon_rice.jpg', 12: 'tomato_rice.jpg',
        13: 'curd_rice.jpg', 14: 'vegetable_pulao.jpg', 15: 'egg_fried_rice.jpg',
        16: 'bread_upma.jpg', 17: 'bread_omelette.jpg', 18: 'roti_pizza.jpg',
        19: 'roti_chivda.jpg', 20: 'dal_tadka.jpg', 21: 'dal_paratha.jpg',
        22: 'dal_chawal.jpg', 23: 'egg_bhurji.jpg', 24: 'omelette.jpg',
        25: 'boiled_egg_curry.jpg', 26: 'banana_smoothie.jpg', 27: 'banana_bread.jpg',
        28: 'fruit_raita.jpg', 29: 'fruit_salad.jpg', 30: 'coriander_chutney.jpg',
        31: 'mint_chutney.jpg', 32: 'cucumber_raita.jpg', 33: 'tomato_soup.jpg',
        34: 'vegetable_soup.jpg', 35: 'chicken_soup.jpg'
    }
    filename = image_map.get(recipe_id, 'default.jpg')
    return url_for('static', filename=f'images/recipes/{filename}')

app.jinja_env.globals.update(get_recipe_image=get_recipe_image)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        
        try:
            user_id = db.create_user(name, email, password_hash)
            session['user_id'] = user_id
            session['user_name'] = name
            return redirect(url_for('dashboard'))
        except Exception as e:
            return render_template('register.html', error="Email already exists")
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = db.get_user_by_email(email)
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid email or password")
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    fridge_items = db.get_fridge_items(session['user_id'])
    ingredients = db.get_all_ingredients()
    personas = db.get_user_personas(session['user_id'])
    return render_template('dashboard.html', 
                         user_name=session['user_name'], 
                         fridge_items=fridge_items,
                         ingredients=ingredients,
                         personas=personas,
                         today=datetime.now().date())

@app.route('/add_fridge_item', methods=['POST'])
@login_required
def add_fridge_item():
    ingredient_id = request.form['ingredient_id']
    # CHANGED: Parsing as Decimal instead of float to fix line 103 crash in database.py
    quantity = Decimal(request.form.get('quantity', '0'))
    expiry_date = request.form['expiry_date']
    
    db.add_fridge_item(session['user_id'], ingredient_id, quantity, expiry_date)
    return redirect(url_for('dashboard'))

@app.route('/delete_fridge_item', methods=['POST'])
@login_required
def delete_fridge_item():
    item_id = request.form.get('item_id')
    cursor = db.connection.cursor()
    cursor.execute("DELETE FROM FRIDGE_ITEM WHERE id = %s AND fridge_id IN (SELECT id FROM FRIDGE WHERE user_id = %s)", 
                   (item_id, session['user_id']))
    db.connection.commit()
    cursor.close()
    return '', 200

# Update persona preference
@app.route('/update_persona', methods=['POST'])
@login_required
def update_persona():
    persona_id = request.form.get('persona_id')
    spice_level = request.form.get('spice_level')
    cuisine_style = request.form.get('cuisine_style')
    dietary_preference = request.form.get('dietary_preference')
    cooking_skill = request.form.get('cooking_skill')
    
    cursor = db.connection.cursor()
    cursor.execute("""
        UPDATE CHEF_PERSONA 
        SET spice_level = %s, cuisine_style = %s, dietary_preference = %s, cooking_skill = %s
        WHERE id = %s AND user_id = %s
    """, (spice_level, cuisine_style, dietary_preference, cooking_skill, persona_id, session['user_id']))
    db.connection.commit()
    cursor.close()
    
    return '', 200

@app.route('/get_suggestions', methods=['POST'])
@login_required
def get_suggestions():
    selected_items = request.form.getlist('selected_items')
    persona_id = request.form.get('persona_id')
    
    if not selected_items:
        return redirect(url_for('dashboard'))
    
    # Get suggestions based on ingredients AND persona
    suggestions = db.get_recipe_suggestions(session['user_id'], selected_items, persona_id)
    
    session['selected_items'] = ','.join(selected_items)
    
    return render_template('results.html', 
                         suggestions=suggestions,
                         selected_count=len(selected_items),
                         selected_items=','.join(selected_items))

@app.route('/cook_recipe', methods=['POST'])
@login_required
def cook_recipe():
    try:
        recipe_id = request.form.get('recipe_id')
        selected_items = request.form.get('selected_items', '')
        
        if selected_items:
            selected_items_list = selected_items.split(',')
            selected_items_list = [item for item in selected_items_list if item]
        else:
            selected_items_list = []
        
        db.mark_recipe_cooked(session['user_id'], recipe_id, selected_items_list)
        
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        print(f"ERROR in cook_recipe: {e}")
        return redirect(url_for('dashboard'))

@app.route('/discover')
@login_required
def discover():
    return render_template('discover.html')

@app.route('/stats')
@login_required
def stats():
    return render_template('stats.html')

@app.route('/cookbook')
@login_required
def cookbook():
    return render_template('cookbook.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)