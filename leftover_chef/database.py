import mysql.connector
from mysql.connector import Error
import bcrypt
from datetime import datetime, date
import json

class Database:
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        try:
            self.connection = mysql.connector.connect(
                host='localhost',
                port=8889,  # MAMP port
                database='leftover_chef',
                user='root',
                password='root'
            )
            if self.connection.is_connected():
                print("✅ Connected to MySQL database")
        except Error as e:
            print(f"❌ Connection failed: {e}")
    
    # ==================== USER AUTH ====================
    
    def get_user_by_email(self, email):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM USER WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        return user
    
    def get_user_by_id(self, user_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM USER WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        return user
    
    def create_user(self, name, email, password_hash):
        cursor = self.connection.cursor()
        cursor.execute("INSERT INTO USER (name, email, password_hash) VALUES (%s, %s, %s)", 
                      (name, email, password_hash))
        user_id = cursor.lastrowid
        
        # Create default fridge for user
        cursor.execute("INSERT INTO FRIDGE (user_id, name) VALUES (%s, 'My Fridge')", (user_id,))
        
        # Create default chef persona
        cursor.execute("""
            INSERT INTO CHEF_PERSONA (user_id, name, cuisine_style, spice_level, dietary_preference, cooking_skill) 
            VALUES (%s, 'Home Chef', 'International', 'Medium', 'Non-Veg', 'Intermediate')
        """, (user_id,))
        
        self.connection.commit()
        cursor.close()
        return user_id
    
    # ==================== FRIDGE OPERATIONS ====================
    
    def get_user_fridge(self, user_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM FRIDGE WHERE user_id = %s", (user_id,))
        fridge = cursor.fetchone()
        cursor.close()
        return fridge
    
    def get_fridge_items(self, user_id, status_filter='active'):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT fi.id, fi.fridge_id, fi.ingredient_id, fi.quantity, 
                   fi.expiry_date, fi.purchase_date, fi.status, fi.updated_at,
                   i.name as ingredient_name, i.unit, c.name as category_name, c.color_tag
            FROM FRIDGE_ITEM fi
            JOIN FRIDGE f ON fi.fridge_id = f.id
            JOIN INGREDIENT i ON fi.ingredient_id = i.id
            LEFT JOIN CATEGORY c ON i.category_id = c.id
            WHERE f.user_id = %s AND fi.status = %s AND fi.quantity > 0
            ORDER BY fi.expiry_date ASC
        """, (user_id, status_filter))
        items = cursor.fetchall()
        cursor.close()
        return items
    
    def add_fridge_item(self, user_id, ingredient_id, quantity, expiry_date):
        cursor = self.connection.cursor()
        
        # Get fridge
        cursor.execute("SELECT id FROM FRIDGE WHERE user_id = %s", (user_id,))
        fridge_id = cursor.fetchone()[0]
        
        # Check if item already exists
        cursor.execute("""
            SELECT id, quantity FROM FRIDGE_ITEM 
            WHERE fridge_id = %s AND ingredient_id = %s AND status = 'active'
        """, (fridge_id, ingredient_id))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing item
            new_quantity = existing[1] + quantity
            cursor.execute("""
                UPDATE FRIDGE_ITEM 
                SET quantity = %s, updated_at = NOW()
                WHERE id = %s
            """, (new_quantity, existing[0]))
            fridge_item_id = existing[0]
        else:
            # Create new item
            cursor.execute("""
                INSERT INTO FRIDGE_ITEM (fridge_id, ingredient_id, quantity, expiry_date, purchase_date, status)
                VALUES (%s, %s, %s, %s, CURDATE(), 'active')
            """, (fridge_id, ingredient_id, quantity, expiry_date))
            fridge_item_id = cursor.lastrowid
        
        # Log the action
        cursor.execute("""
            INSERT INTO STOCK_LOG (fridge_item_id, action, quantity_change, note)
            VALUES (%s, 'added', %s, 'Item added to fridge')
        """, (fridge_item_id, quantity))
        
        self.connection.commit()
        cursor.close()
        return fridge_item_id
    
    def consume_fridge_item(self, fridge_item_id, quantity_used, recipe_id=None):
        cursor = self.connection.cursor()
        
        # Get current item
        cursor.execute("SELECT quantity FROM FRIDGE_ITEM WHERE id = %s", (fridge_item_id,))
        current_qty = cursor.fetchone()[0]
        
        new_qty = current_qty - quantity_used
        
        if new_qty <= 0:
            # Item fully consumed
            cursor.execute("""
                UPDATE FRIDGE_ITEM 
                SET quantity = 0, status = 'consumed', updated_at = NOW()
                WHERE id = %s
            """, (fridge_item_id,))
        else:
            # Partial consumption
            cursor.execute("""
                UPDATE FRIDGE_ITEM 
                SET quantity = %s, updated_at = NOW()
                WHERE id = %s
            """, (new_qty, fridge_item_id))
        
        # Log consumption
        note = f"Used in recipe #{recipe_id}" if recipe_id else "Consumed"
        cursor.execute("""
            INSERT INTO STOCK_LOG (fridge_item_id, action, quantity_change, note)
            VALUES (%s, 'consumed', %s, %s)
        """, (fridge_item_id, -quantity_used, note))
        
        self.connection.commit()
        cursor.close()
    
    # ==================== INGREDIENT MANAGEMENT ====================
    
    def search_ingredients(self, query):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT i.id, i.name, i.unit, c.name as category_name
            FROM INGREDIENT i
            LEFT JOIN CATEGORY c ON i.category_id = c.id
            WHERE i.name LIKE %s
            LIMIT 10
        """, (f'%{query}%',))
        results = cursor.fetchall()
        cursor.close()
        return results
    
    def get_all_ingredients(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT i.id, i.name, i.unit, c.name as category_name, c.color_tag
            FROM INGREDIENT i
            LEFT JOIN CATEGORY c ON i.category_id = c.id
            ORDER BY c.name, i.name
        """)
        results = cursor.fetchall()
        cursor.close()
        return results
    
    # ==================== RECIPE MATCHING ENGINE ====================
    
    # Pantry staples that don't count as "missing"
    PANTRY_STAPLES = ['salt', 'pepper', 'black pepper', 'oil', 'olive oil', 
                      'vegetable oil', 'butter', 'sugar', 'water', 'ice', 'bread', 'chips',
                      'turmeric', 'turmeric powder', 'red chilli powder', 'cumin seeds', 
                      'coriander powder', 'garam masala', 'ginger garlic paste']
    
    def get_recipe_suggestions(self, user_id, selected_fridge_item_ids, persona_id=None):
        """
        STRICT matching: Recipe is ONLY shown if selected ingredient is EXPLICITLY in its ingredient list
        """
        if not selected_fridge_item_ids:
            return []
        
        cursor = self.connection.cursor(dictionary=True)
        
        # Get selected ingredients with their IDs and quantities
        placeholders = ','.join(['%s'] * len(selected_fridge_item_ids))
        cursor.execute(f"""
            SELECT DISTINCT i.id as ingredient_id, i.name as ingredient_name, fi.quantity, fi.id as fridge_item_id
            FROM FRIDGE_ITEM fi
            JOIN INGREDIENT i ON fi.ingredient_id = i.id
            WHERE fi.id IN ({placeholders}) AND fi.status = 'active' AND fi.quantity > 0
        """, selected_fridge_item_ids)
        selected_ingredients = cursor.fetchall()
        
        selected_ingredient_ids = [ing['ingredient_id'] for ing in selected_ingredients]
        selected_ingredients_map = {ing['ingredient_id']: ing for ing in selected_ingredients}
        
        if not selected_ingredient_ids:
            cursor.close()
            return []
        
        # Get user's persona for filtering
        persona = None
        if persona_id:
            cursor.execute("SELECT * FROM CHEF_PERSONA WHERE id = %s AND user_id = %s", (persona_id, user_id))
            persona = cursor.fetchone()
        else:
            cursor.execute("SELECT * FROM CHEF_PERSONA WHERE user_id = %s LIMIT 1", (user_id,))
            persona = cursor.fetchone()
        
        # Get ALL recipes
        cursor.execute("SELECT * FROM RECIPE ORDER BY title")
        all_recipes = cursor.fetchall()
        
        suggestions = []
        
        for recipe in all_recipes:
            # Get recipe's required ingredients (non-optional)
            cursor.execute("""
                SELECT ri.*, i.name as ingredient_name, i.unit
                FROM RECIPE_INGREDIENT ri
                JOIN INGREDIENT i ON ri.ingredient_id = i.id
                WHERE ri.recipe_id = %s AND (ri.is_optional = 0 OR ri.is_optional IS NULL)
            """, (recipe['id'],))
            recipe_ingredients = cursor.fetchall()
            
            if not recipe_ingredients:
                continue
            
            # Check which selected ingredients are ACTUALLY in this recipe
            matched_ingredients = []
            insufficient_quantity = False
            
            for selected_ing in selected_ingredients:
                for recipe_ing in recipe_ingredients:
                    if selected_ing['ingredient_id'] == recipe_ing['ingredient_id']:
                        required_qty = float(recipe_ing['quantity']) if recipe_ing['quantity'] else 1
                        available_qty = float(selected_ing['quantity'])
                        
                        if available_qty >= required_qty:
                            matched_ingredients.append({
                                'id': selected_ing['ingredient_id'],
                                'name': recipe_ing['ingredient_name'],
                                'required': required_qty,
                                'available': available_qty,
                                'unit': recipe_ing['unit'] or '',
                                'fridge_item_id': selected_ing['fridge_item_id']
                            })
                        else:
                            # Have the ingredient but not enough quantity
                            insufficient_quantity = True
                            matched_ingredients.append({
                                'id': selected_ing['ingredient_id'],
                                'name': recipe_ing['ingredient_name'],
                                'required': required_qty,
                                'available': available_qty,
                                'unit': recipe_ing['unit'] or '',
                                'fridge_item_id': selected_ing['fridge_item_id'],
                                'insufficient': True
                            })
                        break
            
            # CRITICAL FIX: Skip recipes with ZERO matching ingredients
            if len(matched_ingredients) == 0:
                continue
            
            # Skip if any matched ingredient has insufficient quantity
            if insufficient_quantity:
                continue
            
            # Get missing ingredients (non-pantry, non-matched)
            missing_ingredients = []
            
            for recipe_ing in recipe_ingredients:
                is_matched = any(m['id'] == recipe_ing['ingredient_id'] for m in matched_ingredients)
                is_pantry = any(staple.lower() in recipe_ing['ingredient_name'].lower() for staple in self.PANTRY_STAPLES)
                
                if not is_matched and not is_pantry:
                    missing_ingredients.append({
                        'name': recipe_ing['ingredient_name'],
                        'required': float(recipe_ing['quantity']) if recipe_ing['quantity'] else 1,
                        'unit': recipe_ing['unit'] or ''
                    })
            
            # Calculate match score
            total_selected = len(selected_ingredient_ids)
            matched_count = len([m for m in matched_ingredients if not m.get('insufficient')])
            
            if matched_count == 0:
                continue
            
            # Calculate match percentage
            match_percentage = int((matched_count / total_selected) * 100) if total_selected > 0 else 0
            
            # Generate match reason and score
            matched_names = ', '.join([m['name'] for m in matched_ingredients[:3] if not m.get('insufficient')])
            
            if matched_count == total_selected and len(missing_ingredients) == 0:
                match_reason = f"🎉 Perfect match! Uses all your {matched_count} selected items: {matched_names}"
                match_score = 100
            elif matched_count == total_selected and len(missing_ingredients) > 0:
                match_reason = f"✅ Great match! Uses all your items! Just need: {', '.join([m['name'] for m in missing_ingredients[:3]])}"
                match_score = 90
            elif matched_count >= total_selected * 0.7:
                match_reason = f"👍 Good match! Uses {matched_count} of your {total_selected} items: {matched_names}"
                match_score = 75
            elif matched_count >= total_selected * 0.5:
                match_reason = f"📝 Uses {matched_count} of your {total_selected} items: {matched_names}"
                match_score = 60
            else:
                match_reason = f"📝 Uses {matched_count} of your {total_selected} items: {matched_names}"
                match_score = 50
            
            # Apply dietary filter
            if persona and persona.get('dietary_preference') == 'Vegetarian':
                # Check if recipe has non-veg ingredients
                non_veg_keywords = ['chicken', 'beef', 'pork', 'fish', 'mutton', 'prawn', 'shrimp', 'egg', 'meat', 'bacon', 'lamb', 'duck', 'turkey', 'crab', 'lobster']
                recipe_text = (recipe['title'] + ' ' + (recipe.get('description') or '')).lower()
                is_non_veg = any(keyword in recipe_text for keyword in non_veg_keywords)
                
                # Also check ingredients
                for ing in recipe_ingredients:
                    ing_name = ing['ingredient_name'].lower()
                    if any(keyword in ing_name for keyword in non_veg_keywords):
                        is_non_veg = True
                        break
                
                if is_non_veg:
                    continue
            
            # Apply cuisine style filter from persona
            if persona and persona.get('cuisine_style') and persona['cuisine_style'] != 'International':
                cuisine_pref = persona['cuisine_style'].lower()
                recipe_cuisine = (recipe.get('cuisine_type') or '').lower()
                if recipe_cuisine and cuisine_pref not in recipe_cuisine and 'international' not in recipe_cuisine:
                    # Don't skip, just note - still show but maybe lower score?
                    pass
            
            suggestions.append({
                'id': recipe['id'],
                'title': recipe['title'],
                'description': recipe.get('description', ''),
                'cuisine_type': recipe.get('cuisine_type', ''),
                'difficulty': recipe.get('difficulty', 'Easy'),
                'prep_time_mins': recipe.get('prep_time_mins', 0),
                'cook_time_mins': recipe.get('cook_time_mins', 0),
                'servings': recipe.get('servings', 2),
                'instructions': recipe.get('instructions', ''),
                'match_score': match_score,
                'match_reason': match_reason,
                'used_items': matched_ingredients,
                'missing_items': missing_ingredients,
                'total_items': len(recipe_ingredients),
                'matched_count': matched_count,
                'total_selected': total_selected
            })
        
        # Sort by match score descending
        suggestions.sort(key=lambda x: x['match_score'], reverse=True)
        
        # Store top suggestions in RECIPE_SUGGESTION table for logging
        for i, sug in enumerate(suggestions[:10]):
            try:
                cursor.execute("""
                    INSERT INTO RECIPE_SUGGESTION (user_id, recipe_id, persona_id, match_score, missing_ingredients, match_reason)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    user_id, sug['id'], persona['id'] if persona else None,
                    sug['match_score'], json.dumps(sug['missing_items']), sug['match_reason']
                ))
            except:
                pass  # Skip if table doesn't exist or error
        
        self.connection.commit()
        cursor.close()
        
        return suggestions[:20]
    
    def mark_recipe_cooked(self, user_id, recipe_id, selected_fridge_item_ids):
        """Mark that user cooked a recipe - deduct quantities"""
        cursor = self.connection.cursor(dictionary=True)
        
        # Get recipe ingredients
        cursor.execute("""
            SELECT ri.ingredient_id, ri.quantity
            FROM RECIPE_INGREDIENT ri
            WHERE ri.recipe_id = %s AND (ri.is_optional = 0 OR ri.is_optional IS NULL)
        """, (recipe_id,))
        recipe_ingredients = cursor.fetchall()
        
        # Get selected fridge items
        placeholders = ','.join(['%s'] * len(selected_fridge_item_ids))
        cursor.execute(f"""
            SELECT fi.id, fi.ingredient_id, fi.quantity
            FROM FRIDGE_ITEM fi
            WHERE fi.id IN ({placeholders}) AND fi.status = 'active'
        """, selected_fridge_item_ids)
        fridge_items = {item['ingredient_id']: item for item in cursor.fetchall()}
        
        # Deduct quantities
        for req in recipe_ingredients:
            if req['ingredient_id'] in fridge_items:
                fridge_item = fridge_items[req['ingredient_id']]
                self.consume_fridge_item(fridge_item['id'], float(req['quantity']), recipe_id)
        
        cursor.close()
    
    # ==================== CHEF PERSONA ====================
    
    def get_user_personas(self, user_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM CHEF_PERSONA WHERE user_id = %s", (user_id,))
        personas = cursor.fetchall()
        cursor.close()
        return personas
    
    def create_persona(self, user_id, name, cuisine_style, spice_level, dietary_preference, cooking_skill):
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO CHEF_PERSONA (user_id, name, cuisine_style, spice_level, dietary_preference, cooking_skill)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, name, cuisine_style, spice_level, dietary_preference, cooking_skill))
        self.connection.commit()
        persona_id = cursor.lastrowid
        cursor.close()
        return persona_id
    
    def get_ingredient_id_by_name(self, name):
        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM INGREDIENT WHERE LOWER(name) = LOWER(%s)", (name,))
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result else None

    def close(self):
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("Database connection closed")