# Descope Integration Instructions for Cursor

---

## 🎯 Task: Integrate Descope authentication into Flask app

**Background:**
- I have a working Flask flight search app (v1)
- I want to add user authentication with Google login
- Users should be blocked from searching if not logged in
- After login, track their quota in SQLite

---

## 📋 What You Need to Do

### 1. Backend Integration

**File to modify:** `v2_development/app.py`

**Add these imports at the top:**
```python
from descope import DescopeClient, AuthException
```

**Initialize Descope client:**
```python
# Near the top of app.py, after app = Flask(__name__)
descope_client = DescopeClient(project_id="P37mczF1NShERSaYoouYUx4SNocu")
```

**Session validation code (from Descope docs):**
```python
# Use this to validate sessions
jwt_response = descope_client.validate_session(session_token=session_token)
```

**Create decorator to protect routes:**
```python
def require_auth(f):
    """Decorator to require authentication"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get session token from Flask session or cookie
        session_token = session.get('descope_token') or request.cookies.get('DS')
        
        if not session_token:
            return redirect('/login')
        
        try:
            # Validate with Descope
            jwt_response = descope_client.validate_session(session_token=session_token)
            user_id = jwt_response['userId']
            user_email = jwt_response.get('email')
            
            # Check if user is blocked in our database
            conn = sqlite3.connect('jobs.db')
            c = conn.cursor()
            c.execute('SELECT is_blocked FROM users WHERE id = ?', (user_id,))
            row = c.fetchone()
            conn.close()
            
            if row and row[0] == 1:
                return 'Account blocked. Contact support.', 403
            
            # Pass user info to the route
            kwargs['current_user_id'] = user_id
            kwargs['current_user_email'] = user_email
            return f(*args, **kwargs)
            
        except AuthException:
            return redirect('/login')
    
    return decorated_function
```

**Protect the /search routes:**
```python
# Find this function:
@app.route('/search', methods=['POST'])
def search_flights():
    # ...existing code...

# Change it to:
@app.route('/search', methods=['POST'])
@require_auth
def search_flights(current_user_id, current_user_email):
    # Check quota before searching
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('SELECT monthly_limit, searches_used FROM user_quota WHERE user_id = ?', 
              (current_user_id,))
    quota = c.fetchone()
    
    if not quota:
        # First time user - create quota entry
        c.execute('INSERT INTO user_quota (user_id) VALUES (?)', (current_user_id,))
        conn.commit()
        quota = (10, 0)  # default free tier
    
    if quota[1] >= quota[0]:
        conn.close()
        return jsonify({'error': 'Quota exceeded. Please upgrade.'}), 429
    
    # Increment quota
    c.execute('UPDATE user_quota SET searches_used = searches_used + 1 WHERE user_id = ?',
              (current_user_id,))
    conn.commit()
    conn.close()
    
    # Continue with existing search code...
```

**Add auth callback route:**
```python
@app.route('/auth/callback')
def auth_callback():
    """Handle Descope callback after login"""
    # Get session token from Descope
    session_token = request.cookies.get('DS')
    
    if not session_token:
        return 'No session token', 401
    
    try:
        # Validate and get user info
        jwt_response = descope_client.validate_session(session_token=session_token)
        user_id = jwt_response['userId']
        user_email = jwt_response.get('email')
        user_name = jwt_response.get('name', '')
        
        # Store in Flask session
        session['descope_token'] = session_token
        session['user_id'] = user_id
        
        # Create user in database if new
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO users (id, email, name) 
                     VALUES (?, ?, ?)''',
                  (user_id, user_email, user_name))
        c.execute('INSERT OR IGNORE INTO user_quota (user_id) VALUES (?)',
                  (user_id,))
        conn.commit()
        conn.close()
        
        return redirect('/')
        
    except AuthException as e:
        return f'Auth failed: {e}', 401

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect('/')
```

---

### 2. Frontend Integration

**File to modify:** `v2_development/templates/index.html`

**Add Descope script in `<head>`:**
```html
<head>
    <!-- Existing head content -->
    
    <!-- Descope Web Component -->
    <script src="https://unpkg.com/@descope/web-component@latest/dist/index.js"></script>
</head>
```

**Check if user is logged in at the top of `<body>`:**
```html
<body>
    {% if session.get('user_id') %}
        <!-- User is logged in -->
        <div style="position: absolute; top: 10px; right: 10px;">
            <span>Logged in</span>
            <a href="/logout">Logout</a>
        </div>
    {% else %}
        <!-- User NOT logged in - show login -->
        <div id="login-overlay" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
             background: rgba(0,0,0,0.8); z-index: 9999; display: flex; 
             align-items: center; justify-content: center;">
            <div style="background: white; padding: 40px; border-radius: 20px; max-width: 400px;">
                <h2>Login to Search Flights</h2>
                
                <!-- Descope login widget (includes Google button!) -->
                <descope-wc
                    project-id="P37mczF1NShERSaYoouYUx4SNocu"
                    flow-id="sign-up-or-in"
                    theme="light"
                />
                
                <script>
                    const wcElement = document.getElementsByTagName('descope-wc')[0];
                    
                    const onSuccess = (e) => {
                        console.log('Login success:', e.detail.user.name, e.detail.user.email);
                        // Redirect to callback to save session
                        window.location.href = '/auth/callback';
                    };
                    
                    const onError = (err) => {
                        console.error('Login error:', err);
                        alert('Login failed. Please try again.');
                    };
                    
                    wcElement.addEventListener('success', onSuccess);
                    wcElement.addEventListener('error', onError);
                </script>
            </div>
        </div>
    {% endif %}
    
    <!-- Rest of existing body content -->
```

---

### 3. Database Setup

**Create tables in `v2_development/jobs.db`:**

Run this Python script once:
```python
import sqlite3

conn = sqlite3.connect('v2_development/jobs.db')
c = conn.cursor()

# Users table (user_id is TEXT from Descope)
c.execute('''
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  is_blocked INTEGER DEFAULT 0,
  is_admin INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Quota table
c.execute('''
CREATE TABLE IF NOT EXISTS user_quota (
  user_id TEXT PRIMARY KEY,
  tier TEXT DEFAULT 'free',
  monthly_limit INTEGER DEFAULT 10,
  searches_used INTEGER DEFAULT 0,
  reset_date DATE,
  stripe_customer_id TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
)
''')

# Search history table
c.execute('''
CREATE TABLE IF NOT EXISTS search_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  search_type TEXT,
  search_params TEXT,
  results_count INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
)
''')

conn.commit()
conn.close()
print("✅ Database tables created!")
```

---

### 4. Requirements

**Add to `v2_development/requirements.txt`:**
```
descope>=1.0.0
```

---

## 🎯 Expected Result

After integration:

1. **User opens site** → Sees login overlay with "Sign in with Google" button
2. **User clicks Google login** → Descope handles OAuth
3. **After login** → User redirected to main page, can search flights
4. **Quota tracking** → Each search decrements their quota (10 free searches)
5. **Logout** → User can logout, next visit requires login again

---

## ✅ Testing Checklist

After integration, test:
- [ ] Can see login screen when not logged in
- [ ] Can login with Google
- [ ] After login, can search flights
- [ ] Quota decrements after each search
- [ ] Blocked at 10 searches (free tier)
- [ ] Logout works
- [ ] Login again works

---

## 🚨 Important Notes

1. **Keep v1 unchanged** - work only in `v2_development/`
2. **Session secret** - make sure Flask has `app.secret_key = 'your-secret-key'`
3. **HTTPS required** - Descope requires HTTPS in production (PythonAnywhere provides this)
4. **Test locally first** - run on `localhost:5001` before deploying

---

## 📞 If Stuck

Error messages to watch for:
- `"Invalid session"` → Token expired or invalid, redirect to login
- `"Project not found"` → Check Project ID is correct
- `"CORS error"` → Add domain to Descope dashboard settings

---

**Project ID:** P37mczF1NShERSaYoouYUx4SNocu  
**Docs:** https://docs.descope.com/


