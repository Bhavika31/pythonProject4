from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import re
import bcrypt
import datetime
from collections import defaultdict
from urllib.parse import urlparse

app = Flask(__name__)

app.secret_key = '1'


@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    try:
        if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
            username = request.form['username']
            password = request.form['password']

            with sqlite3.connect('registration.db') as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
                account = cursor.fetchone()

            if not username or not password:
                msg = 'Please fill in all details!'
            elif account and bcrypt.checkpw(password.encode('utf-8'), account[2]):
                session['loggedin'] = True
                session['id'] = account[0]
                session['username'] = account[1]
                msg = 'Logged in successfully!'
                return redirect(url_for('home'))
            else:
                msg = 'Incorrect username / password!'

            conn.close()
        return render_template('login.html', msg=msg)
    except Exception as e:
        msg = 'Error: {}'.format(str(e))
        return render_template('login.html', msg=msg)

@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''
    try:
        if request.method == 'POST':
            username = request.form['username']
            raw_password = request.form['password']
            email = request.form['email']

            if not username or not raw_password or not email:
                msg = 'Please fill in all details!'
            else:
                hashed_password = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt())

                with sqlite3.connect('registration.db') as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
                    account = cursor.fetchone()

                if account:
                    msg = 'Account already exists!'
                elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
                    msg = 'Invalid email address!'
                elif not re.match(r'[A-Za-z0-9]+', username):
                    msg = 'Username must contain only characters and numbers!'
                else:
                    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    with sqlite3.connect('registration.db') as conn:
                        cursor = conn.cursor()
                        cursor.execute('INSERT INTO users (username, password, email, registration_date) VALUES (?, ?, ?, ?)',
                                       (username, hashed_password, email, current_time))
                        conn.commit()
                    msg = 'You have successfully registered!'
                conn.close()    
    except Exception as e:
        msg = 'Error: {}'.format(str(e))
    
    return render_template('registration_file.html', msg=msg)

@app.route('/logout')
def logout():
    # Clear the session data
    session.clear()
    return redirect(url_for('home'))

@app.route('/', methods=['GET', 'POST'])
def home():
    def is_valid_url(url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def search_recipes_by_ingredients(input_ingredients, category=None, area=None):
        try:
            # Connect to the database
            connection = sqlite3.connect('mealsdb')
            cursor = connection.cursor()

            # Convert the input ingredients to lowercase
            input_ingredients = [ingredient.strip().lower() for ingredient in input_ingredients]

            # Construct the SQL query with optional category and area filters
            query = """
            SELECT m.meal_name, m.category, m.area, m.instructions, 
                m.youtube_link, m.tags, m.meal_thumb, 
                i.ingredient_name, mi.measurement
            FROM meals m
            JOIN meal_ingredients mi ON m.meal_id = mi.meal_id
            JOIN ingredients i ON mi.ingredient_id = i.ingredient_id
            WHERE LOWER(i.ingredient_name) IN ({})
            {category_filter}
            {area_filter}
            ORDER BY m.meal_name
            """.format(
                ', '.join('?' for _ in input_ingredients),
                category_filter=f"AND m.category = '{category}'" if category else "",
                area_filter=f"AND m.area = '{area}'" if area else ""
            )

            # Execute the query with input ingredients and optional filters, and retrieve matching recipes
            recipes = cursor.execute(query, input_ingredients).fetchall()


            # Create a dictionary to store the recipe details and their ingredients
            recipe_details = defaultdict(lambda: {'name': '', 'category': '', 'area': '', 'instructions': '', 'youtube_link': '',
                                                'tags': '', 'meal_thumb': '', 'input_ingredients': [], 'remaining_ingredients': []})

            # Loop through the recipes and organize them in the 'recipe_details' dictionary
            for recipe in recipes:
                meal_name = recipe[0]
                if not recipe_details[meal_name]['name']:
                    # If recipe details are not already set for this recipe, update them
                    recipe_details[meal_name]['name'] = recipe[0]
                    recipe_details[meal_name]['category'] = recipe[1]
                    recipe_details[meal_name]['area'] = recipe[2]
                    recipe_details[meal_name]['instructions'] = recipe[3]
                    recipe_details[meal_name]['youtube_link'] = recipe[4] if is_valid_url(recipe[4]) else None
                    recipe_details[meal_name]['tags'] = recipe[5]
                    recipe_details[meal_name]['meal_thumb'] = recipe[6]

                # Append the ingredient and its measurement to the list of input ingredients for this recipe
                recipe_details[meal_name]['input_ingredients'].append((recipe[7], recipe[8]))

            # Create a dictionary to store the remaining ingredients for each recipe
            remaining_ingredients_dict = defaultdict(list)

            # Loop through the recipes and organize the remaining ingredients
            for recipe in recipes:
                meal_name = recipe[0]
                # Get the remaining ingredients for this recipe
                remaining_query = """
                SELECT i.ingredient_name, mi.measurement
                FROM meals m
                JOIN meal_ingredients mi ON m.meal_id = mi.meal_id
                JOIN ingredients i ON mi.ingredient_id = i.ingredient_id
                WHERE m.meal_name = ?
                AND i.ingredient_name NOT IN ({})
                """.format(', '.join('?' for _ in recipe_details[meal_name]['input_ingredients']))

                # Convert the zip object to a list before passing it to the execute function
                remaining_ingredients = cursor.execute(remaining_query, [meal_name, *list(zip(*recipe_details[meal_name]['input_ingredients']))[0]]).fetchall()

                # Add the remaining ingredients to the dictionary
                remaining_ingredients_dict[meal_name] = remaining_ingredients

            # Update the 'recipe_details' dictionary with remaining ingredients for each recipe
            for recipe_name, details in recipe_details.items():
                details['remaining_ingredients'] = remaining_ingredients_dict[recipe_name]

            # Close the database connection
            connection.close()

            # Return the recipe details as a list of dictionaries
            return list(recipe_details.values())
    
        except sqlite3.Error as e:
        # Handle database-related errors
            return f"Error accessing the database: {str(e)}"

        except Exception as e:
        # Handle other unexpected errors
            return f"An unexpected error occurred: {str(e)}"

    if request.method == 'POST':
        ingredients = request.form.get('ingredients').split(',')
        category = request.form.get('category')
        area = request.form.get('area')
        recipes = search_recipes_by_ingredients(ingredients, category, area)
        return render_template('index.html', recipes=recipes)
    return render_template('index.html', recipes=None)

@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == "__main__":
    app.run(host='127.0.0.1')
