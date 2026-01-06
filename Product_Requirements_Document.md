# Flight Search Application - Ultra-MVP Plan

**Version**: 2.0 (Lean Edition)  
**Date**: January 4, 2026  
**Philosophy**: KISS - Keep It Simple, Stupid!

---

## 🎯 TL;DR - Executive Summary

**What you have:**
- Working flight search tool (Flask + SQLite on PythonAnywhere)
- 1,840 lines Python, 3,187 lines HTML/JS
- Free, open-access, works perfectly

**What you want:**
- Add user accounts + paid plans
- Free: 10 searches/month | Paid: $9/mo for 50 searches

**The Plan: Ultra-MVP**
- $0/month cost
- Stay on PythonAnywhere
- Add Flask-Login + Stripe
- NO new infrastructure

---

## 💰 Ultra-MVP Shopping List

### What You Need (Total: ~$500)
1. **Descope account**: Free tier (7,500 users), Google login built-in (Free)
2. **Stripe account**: Test mode, only pay 2.9% per transaction (Free)
3. **Lawyer consultation**: $300-500 (one-time, REQUIRED before charging money)
4. **Domain** (optional): $1-12/year

### What You DON'T Need
- ❌ PostgreSQL (SQLite handles 100+ users fine)
- ❌ Render/Railway (stay on PythonAnywhere)
- ❌ Sentry (use console logs)
- ❌ SendGrid (use Gmail SMTP)
- ❌ React (keep HTML/JS)
- ❌ Custom auth system (Descope does it all)

**Monthly cost: $0** 🎉

---

## 📊 The Only Comparison That Matters

| | **Ultra-MVP** 🏆 | "Fancy" MVP | Full Rewrite |
|---|---|---|---|
| **Monthly Cost** | **$0** | $165 | $1,000+ |
| **New Services** | **0** | 4-6 | 10+ |
| **Hosting** | **PythonAnywhere (free)** | Render ($25/mo) | AWS ($100+/mo) |
| **Tech Changes** | **+Descope (Google login), +3 SQLite tables** | New DB, new auth, new hosting | Rebuild everything |
| **Risk** | **Minimal** | Low | High |
| **KISS** | **✅ Maximum** | ❌ Medium | ❌ Minimal |

**Winner:** Ultra-MVP - Same features, $0 cost, maximum simplicity!

---

## ⚠️ Critical Warnings (READ BEFORE STARTING)

### 1. Legal Risk - Google Scraping
- `fast-flights` is **NOT** an official API - it's web scraping
- **High risk** of breaking if Google changes HTML
- **Potential legal issues** - violates Google ToS
- **REQUIRED:** Consult IP lawyer ($300-500) before charging money
- **Backup plan:** Budget $500-2K/month for official APIs (Amadeus, Kiwi.com) if forced to migrate

### 2. Realistic Expectations
- **Conversion rate:** 3-5% (NOT 25%)
- **Revenue potential:** $1.5K-6K annually (NOT $135K)
- **Growth:** Slow and organic
- This is **learning experience**, not get-rich-quick

### 3. Work-Life Balance
- This is a **side project** - don't let it consume you
- Thesis and job search come FIRST
- It's okay to pause or stop anytime

---

## 🛠️ Ultra-MVP Implementation

### Phase 1: Authentication (Descope - Google Login)

**Why Descope instead of custom auth:**
- ✅ **"Login with Google"** - users expect this today
- ✅ **Professional UI** - not DIY amateur look
- ✅ **Free tier:** 7,500 users (more than enough)
- ✅ **20 lines of code** instead of 150
- ✅ **No password management** headaches
- ✅ **Mobile-ready** automatically

**Setup:**

1. **Sign up:** https://www.descope.com/ (free)
2. **Create project** → Get Project ID
3. **Enable Google login** in dashboard (1 click)
4. **Install:**
```bash
pip install descope
```

**Add to jobs.db:**
```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,                 -- Descope user ID
  email TEXT UNIQUE NOT NULL,
  name TEXT,                           -- From Google profile
  is_blocked INTEGER DEFAULT 0,        -- 1 = blocked user (abuse, fraud)
  is_admin INTEGER DEFAULT 0,          -- 1 = admin access (you!)
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_quota (
  user_id TEXT PRIMARY KEY,            -- References users.id
  tier TEXT DEFAULT 'free',
  monthly_limit INTEGER DEFAULT 10,
  searches_used INTEGER DEFAULT 0,
  reset_date DATE,
  stripe_customer_id TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE search_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  search_type TEXT,
  search_params TEXT,
  results_count INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**Key change:** `user_id` is now TEXT (Descope provides unique ID), no more `password_hash`!

**Code (much simpler with Descope):**
```python
from descope import DescopeClient, AuthException
from flask import session

# Initialize Descope
descope = DescopeClient(project_id="YOUR_PROJECT_ID")  # Get from dashboard

def require_auth(f):
    """Decorator to protect routes"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check session
        token = session.get('descope_token')
        if not token:
            return redirect('/login')
        
        try:
            # Validate token
            user_info = descope.validate_session(token)
            user_id = user_info['userId']
            
            # Check if blocked
            conn = sqlite3.connect('jobs.db')
            c = conn.cursor()
            c.execute('SELECT is_blocked FROM users WHERE id = ?', (user_id,))
            row = c.fetchone()
            conn.close()
            
            if row and row[0] == 1:
                return 'Account blocked. Contact support.', 403
            
            # Pass user info to route
            kwargs['current_user_id'] = user_id
            return f(*args, **kwargs)
            
        except AuthException:
            return redirect('/login')
    
    return decorated_function

@app.route('/login')
def login():
    """Render login page with Descope widget"""
    return render_template('login.html', 
                         descope_project_id="YOUR_PROJECT_ID")

@app.route('/auth/callback')
def auth_callback():
    """Handle Descope callback after login"""
    code = request.args.get('code')
    
    try:
        # Exchange code for session
        auth_info = descope.exchange_token(code)
        user_info = auth_info['user']
        
        # Store session
        session['descope_token'] = auth_info['sessionJwt']
        
        # Create user in DB if new
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO users (id, email, name) 
                     VALUES (?, ?, ?)''',
                  (user_info['userId'], user_info['email'], user_info.get('name', '')))
        c.execute('INSERT OR IGNORE INTO user_quota (user_id) VALUES (?)',
                  (user_info['userId'],))
        conn.commit()
        conn.close()
        
        return redirect('/dashboard')
        
    except AuthException as e:
        return f'Auth failed: {e}', 401

@app.route('/logout')
def logout():
    session.pop('descope_token', None)
    return redirect('/')

@app.route('/search', methods=['POST'])
@require_auth
def search_flights(current_user_id):
    # Your existing search code
    # Use current_user_id for quota checks
    pass
```

**Create simple login page:**
`/templates/login.html`:
```html
<!DOCTYPE html>
<html>
<head>
    <title>Login - Flight Search</title>
    <script src="https://unpkg.com/@descope/web-component"></script>
</head>
<body>
    <h1>Login to Flight Search</h1>
    
    <!-- Descope login widget (Google button included!) -->
    <descope-wc
        project-id="{{ descope_project_id }}"
        flow-id="sign-up-or-in"
        redirect-url="{{ url_for('auth_callback', _external=True) }}"
    ></descope-wc>
</body>
</html>
```

**That's it!** Descope handles:
- ✅ Google "Sign in with Google" button (professional UI)
- ✅ Token validation
- ✅ Session management
- ✅ Mobile responsive
- ✅ Security (no passwords to store!)

**No more:**
- ❌ Password hashing
- ❌ Email verification
- ❌ Password reset flows
- ❌ Session security worries

---

### Phase 2: Quota System

**Add quota check:**
```python
@app.route('/search', methods=['POST'])
@login_required
def search_flights():
    # Check quota
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('SELECT monthly_limit, searches_used FROM user_quota WHERE user_id = ?', 
              (current_user.id,))
    quota = c.fetchone()
    
    if quota[1] >= quota[0]:  # searches_used >= monthly_limit
        return jsonify({'error': 'Quota exceeded. Please upgrade.'}), 429
    
    # Increment searches_used
    c.execute('UPDATE user_quota SET searches_used = searches_used + 1 WHERE user_id = ?',
              (current_user.id,))
    conn.commit()
    conn.close()
    
    # Run search
    result = search_engine.search(config, job_id=job_id)
    return jsonify(result)
```

**Show quota on homepage:**
```html
<div>
  You have used {{ searches_used }}/{{ monthly_limit }} searches this month.
  {% if searches_used >= monthly_limit %}
    <a href="/upgrade">Upgrade to continue searching</a>
  {% endif %}
</div>
```

**Monthly reset (cron job):**
```python
@app.route('/cron/reset_quotas')
def reset_quotas():
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('UPDATE user_quota SET searches_used = 0 WHERE reset_date <= date("now")')
    c.execute('UPDATE user_quota SET reset_date = date("now", "start of month", "+1 month")')
    conn.commit()
    conn.close()
    return 'OK'
```

Set up PythonAnywhere scheduled task: Run daily at 00:01

**Block abusive users (manual, via SQLite console):**
```sql
-- Block a user
UPDATE users SET is_blocked = 1 WHERE email = 'abuser@example.com';

-- Unblock a user
UPDATE users SET is_blocked = 0 WHERE email = 'user@example.com';

-- Make yourself admin (do this once!)
UPDATE users SET is_admin = 1 WHERE email = 'your-email@example.com';
```

Optional: Add `/admin` page to view/block users (build later if needed).

---

### Phase 3: Stripe Integration

**Sign up:** https://stripe.com (test mode)

**Create product in Stripe dashboard:**
- Name: "Basic Plan"
- Price: $9/month
- Copy the `price_xxxxx` ID

**Install:**
```bash
pip install stripe
```

**Checkout page:**
```python
import stripe
stripe.api_key = 'sk_test_...'  # From Stripe dashboard

@app.route('/upgrade')
@login_required
def upgrade():
    session = stripe.checkout.Session.create(
        customer_email=current_user.email,
        payment_method_types=['card'],
        line_items=[{'price': 'price_xxxxx', 'quantity': 1}],
        mode='subscription',
        success_url='https://yourdomain.pythonanywhere.com/payment_success',
        cancel_url='https://yourdomain.pythonanywhere.com/cancel',
    )
    return redirect(session.url, code=303)
```

**Webhook handler:**
```python
@app.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return 'Invalid payload', 400
    
    if event['type'] == 'invoice.payment_succeeded':
        customer_email = event['data']['object']['customer_email']
        
        # Upgrade user
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        c.execute('''UPDATE user_quota 
                     SET tier = 'paid', monthly_limit = 50, 
                         stripe_customer_id = ?
                     WHERE user_id = (SELECT id FROM users WHERE email = ?)''',
                  (event['data']['object']['customer'], customer_email))
        conn.commit()
        conn.close()
    
    elif event['type'] == 'customer.subscription.deleted':
        # Downgrade to free
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        c.execute('''UPDATE user_quota 
                     SET tier = 'free', monthly_limit = 10
                     WHERE stripe_customer_id = ?''',
                  (event['data']['object']['customer'],))
        conn.commit()
        conn.close()
    
    return 'Success', 200
```

**Configure webhook in Stripe dashboard:**
- URL: `https://yourdomain.pythonanywhere.com/webhooks/stripe`
- Events: `invoice.payment_succeeded`, `customer.subscription.deleted`

---

### Phase 4: Polish & Launch

**Dashboard page:**
```html
<h1>Dashboard</h1>
<p>Email: {{ current_user.email }}</p>
<p>Plan: {{ tier }}</p>
<p>Searches used: {{ searches_used }}/{{ monthly_limit }}</p>

{% if tier == 'free' %}
  <a href="/upgrade">Upgrade to Basic ($9/month for 50 searches)</a>
{% else %}
  <a href="https://billing.stripe.com/p/login/...">Manage Billing</a>
{% endif %}

<h2>Recent Searches</h2>
<ul>
  {% for search in recent_searches %}
    <li>{{ search.search_type }} - {{ search.created_at }}</li>
  {% endfor %}
</ul>
```

**Legal (use free templates):**
- Terms of Service: https://www.termsfeed.com/
- Privacy Policy: https://www.termsfeed.com/

**Testing checklist:**
- [ ] Register new user
- [ ] Login works
- [ ] Can search (decrement quota)
- [ ] Hit 10 search limit, blocked
- [ ] Upgrade via Stripe (use test card: 4242 4242 4242 4242)
- [ ] Quota increased to 50
- [ ] Search works again
- [ ] Cancel subscription in Stripe
- [ ] User downgraded to free tier (upon next billing cycle)

**Deploy:**
- Already on PythonAnywhere!
- Just reload web app after pushing code
- Optional: Buy domain and configure DNS

---

## 💰 Cost Reality Check

### Realistic Revenue Projection (3-5% Conversion)

**Scenario: 100 registered users**
- 3-5 paying customers
- Revenue: $27-45/month
- Costs: $0/month
- Setup cost: $500 (lawyer, one-time)

**What you'll actually earn:**
- First paying customer: ~$9/month
- After 100 users: ~$30-50/month
- After 300 users: ~$100-150/month

**But you'll learn:**
- ✅ User authentication
- ✅ Payment processing
- ✅ SaaS business model
- ✅ Real user feedback
- ✅ Portfolio project

**This is learning + side income, not a unicorn startup.**

---

## ⚠️ When to Stop

**Red flags:**
- Not enjoying the work
- Lawyer says "don't do this"
- No users after launch
- Thesis/job suffering

**It's OKAY to:**
- Pause anytime
- Stop completely
- Keep it free forever
- Treat it as learning project only

---

## 🚀 Upgrade Path (Future)

**Don't do ANY of this until you have 100+ paying customers:**

### When to upgrade to paid hosting ($5-25/mo):
- PythonAnywhere free tier limits hit
- Need more CPU/RAM
- Want faster response times

### When to upgrade to PostgreSQL:
- 500+ registered users
- Multiple servers needed
- Complex analytics required

### When to rewrite frontend (React):
- Users complaining about UX
- Clear feature requests that need SPA
- You have revenue to fund it

### When to add monitoring/analytics tools:
- Can't debug issues with console logs
- Need to understand user behavior
- Revenue > $500/month

**Rule:** Scale complexity ONLY when current system breaks.

---

## 📋 FAQ (Ultra-MVP Focused)

**Q: Why Descope instead of custom Flask-Login?**

A: **Professional appearance matters!** Users expect "Sign in with Google" in 2026:
- ✅ Looks professional (not amateur DIY)
- ✅ Free for 7,500 users
- ✅ 20 lines of code (vs 150)
- ✅ No password security headaches
- ✅ Works on PythonAnywhere perfectly

**Q: Won't SQLite be slow?**

A: No! SQLite handles:
- 100,000 reads/second
- Your traffic: ~1 search/hour
- GitHub used it for years
- Upgrade to PostgreSQL only at 500+ users

**Q: What if Google blocks fast-flights?**

A: High risk. Plan:
1. Monitor for failures
2. Email users immediately
3. Migrate to Amadeus API ($500-2K/mo)
4. Increase prices to cover API costs

**Q: Can I really charge $9/month?**

A: Test and see!
- Scott's Cheap Flights: $49/year (~$4/mo)
- Your differentiator: Flexible date range search, multi-city
- Start at $5/mo if $9 feels high
- Offer annual discount ($50/year)

**Q: How do I handle abusive users (quota cheaters)?**

A: Use `is_blocked` field:
1. Monitor search patterns in database
2. If user creates multiple accounts: `UPDATE users SET is_blocked = 1 WHERE email = '...'`
3. Blocked users can't login
4. Consider email verification later (not needed for Ultra-MVP)

Future: Add IP tracking, email verification, rate limiting.

**Q: How do I get first users?**

A: Start small:
1. Friends/family
2. Reddit r/travel (don't spam!)
3. Product Hunt launch
4. SEO blog posts
5. TikTok/Instagram demos

Expect slow, organic growth.

**Q: What if I build this and nobody pays?**

A: High probability! But you'll learn:
- User auth, payments, SaaS model
- Portfolio project for job search
- Only lost $500 + some time

**Q: Should I quit job search to focus on this?**

A: **NO!** Job search is priority #1. This is:
- Side project only
- Learning experience
- NOT a salary replacement

---

## ✅ Decision Checklist

**Proceed with Ultra-MVP IF:**
- [ ] You accept 3-5% conversion (not 25%)
- [ ] You have $500 for lawyer
- [ ] You have time for side project
- [ ] You're okay with slow growth
- [ ] Thesis/job comes first
- [ ] You want to learn, not get rich

**DON'T proceed if:**
- [ ] You need income soon
- [ ] You expect passive income without work
- [ ] You can't afford to "lose" $500
- [ ] You don't have time for side project

---

## 🎯 Next Steps

### Before Starting
1. ✅ Read this document
2. 📋 Research flight scraping legality
3. 💰 Confirm you have $500 budget
4. 🤔 Decide go/no-go

### If You Decide to Proceed
1. **Run setup script:** `python setup_v2_project.py`
2. **Sign up:** Descope.com (free tier)
3. **Sign up:** Stripe test mode
4. **Schedule:** Lawyer consultation ($300-500)
5. **Follow:** Implementation phases in v2_development/

### After Launch
- Soft launch to friends
- Gather feedback
- Iterate or pivot

---

## 📚 Resources

**Auth:**
- Descope docs: https://docs.descope.com/
- Descope quickstart: https://docs.descope.com/quickstart/

**Payments:**
- Stripe Checkout: https://stripe.com/docs/payments/checkout
- Stripe Testing: https://stripe.com/docs/testing

**Legal:**
- Terms generator: https://www.termsfeed.com/
- Find lawyer: https://www.avvo.com/ (filter by IP/tech law)

**Community:**
- r/SaaS - SaaS builder community
- r/entrepreneur - startup advice
- Indie Hackers - bootstrapped founders

**Deployment:**
- PythonAnywhere help: https://help.pythonanywhere.com/

---

## 🎯 Document Summary

**What this document covers:**
1. ✅ Ultra-MVP plan ($0/month)
2. ✅ Exact implementation steps with code
3. ✅ Cost/revenue projections (realistic)
4. ✅ Legal warnings (REQUIRED reading)
5. ✅ When to stop / when to scale

**What this document does NOT cover:**
- ❌ React/frontend rewrite (you don't need it)
- ❌ Microservices architecture (massive overkill)
- ❌ Advanced analytics (use SQLite queries)
- ❌ Mobile apps (web is enough)
- ❌ API for third parties (no demand yet)

**Philosophy:**
- KISS - Keep It Simple, Stupid
- Build minimum, validate fast
- Scale ONLY when needed
- $0/month until revenue

---

**Good luck! 🚀**

**Remember:** Most side projects fail. That's okay. You'll learn valuable skills regardless of outcome.

**Questions?** Re-read FAQ section or ask in r/SaaS.

---

**Document version:** 2.0 Lean Edition  
**Last updated:** January 4, 2026

