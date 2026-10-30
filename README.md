# CuisineHub — Complete Mini Project

CuisineHub is a Flask + MySQL full-stack recipe and nutrition platform based on the supplied synopsis.

## Stack
- Frontend: HTML5, CSS3, JavaScript
- Backend: Python Flask
- Database: MySQL
- Authentication: Flask session + Werkzeug password hashing
- UI: responsive custom CSS

## Project structure
```text
CuisineHub/
├── frontend/
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── recipes.html
│   ├── recipe.html
│   ├── profile.html
│   ├── favorites.html
│   ├── subscription.html
│   ├── css/style.css
│   └── js/app.js
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   ├── .env.example
│   └── setup.sql
└── START_CUISINEHUB.bat
```

## Run on Windows
1. Install **Python 3.11+**.
2. Install/start **MySQL**. XAMPP users only need to start MySQL from the XAMPP Control Panel.
3. Double-click `START_CUISINEHUB.bat`.
4. It installs Python packages and opens `http://127.0.0.1:5000`.
5. You do **not** need to run the frontend separately.

The Flask backend serves all frontend pages.

## MySQL credentials
The default connection is:
- host: `127.0.0.1`
- port: `3306`
- user: `root`
- password: empty
- database: `cuisinehub`

If your MySQL password is different, edit `backend/.env` after the first run (the BAT creates it from `.env.example`).

The Flask app automatically creates the database, tables and sample recipes. You can also run `backend/setup.sql` manually if your MySQL user does not have CREATE DATABASE permission.

## Features implemented
- User registration/login/logout/profile
- 2 free premium recipe unlocks for new accounts
- Recipe search and filters
- Cuisine, meal type, preparation time and dietary filters
- High-protein recommendation filter
- Recipe details with ingredients/instructions
- Embedded cooking videos
- Calories, protein, carbs and fats
- Favorites/saved recipes
- Reviews and 1–5 star ratings
- Premium monthly plan for all cuisines
- Normal monthly plan for one selected cuisine
- Locked premium recipes and upgrade flow
- Responsive UI
- MySQL persistence

## Demo subscription
This is a college mini-project demo. Subscription activation is simulated; no real payment gateway is connected.
