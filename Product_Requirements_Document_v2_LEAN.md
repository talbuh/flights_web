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
- 4-8 weeks part-time
- $0/month cost
- Stay on PythonAnywhere
- Add Flask-Login + Stripe
- NO new infrastructure

---

## 💰 Ultra-MVP Shopping List

### What You Need (Total: ~$500)
1. **Flask-Login**: `pip install flask-login` (Free)
2. **Stripe account**: Test mode, only pay 2.9% per transaction (Free)
3. **Lawyer consultation**: $300-500 (one-time, REQUIRED before charging money)
4. **Domain** (optional): $1-12/year

### What You DON'T Need
- ❌ Descope/Auth0 (use Flask-Login instead)
- ❌ PostgreSQL (SQLite handles 100+ users fine)
- ❌ Render/Railway (stay on PythonAnywhere)
- ❌ Sentry (use console logs)
- ❌ SendGrid (use Gmail SMTP)
- ❌ React (keep HTML/JS)

**Monthly cost: $0** 🎉

---

## 📊 The Only Comparison That Matters

| | **Ultra-MVP** 🏆 | "Fancy" MVP | Full Rewrite |
|---|---|---|---|
| **Time** | **4-8 weeks** | 12-16 weeks | 26+ weeks |
| **Monthly Cost** | **$0** | $165 | $1,000+ |
| **New Services** | **0** | 4-6 | 10+ |
| **Hosting** | **PythonAnywhere (free)** | Render ($25/mo) | AWS ($100+/mo) |
| **Tech Changes** | **+Flask-Login, +3 SQLite tables** | New DB, new auth, new hosting | Rebuild everything |
| **Risk** | **Minimal** | Low | High |
| **KISS** | **✅ Maximum** | ❌ Medium | ❌ Minimal |

**Winner:** Ultra-MVP - Same features, $0 cost, half the time!

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
- **Year 1 revenue:** $1.5K-6K (NOT $135K)
- **Growth:** Slow (10 users/month is normal)
- This is **learning experience**, not get-rich-quick

### 3. Timeline Reality
- **With thesis + job search:** 12-16 weeks is realistic
- **Not 4-8 weeks** if you're busy with other priorities
- It's okay to pause or stop

---

## 🛠️ Ultra-MVP Implementation (4-8 Weeks)

### Week 1-2: Authentication (Flask-Login)

**Install:**
```bash
pip install flask-login
```

**Add to jobs.db:**
```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_quota (
  user_id INTEGER PRIMARY KEY,
  tier TEXT DEFAULT 'free',
  monthly_limit INTEGER DEFAULT 10,
  searches_used INTEGER DEFAULT 0,
  reset_date DATE,
  stripe_customer_id TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE search_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  search_type TEXT,
  search_params TEXT,
  results_count INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**Code (simplified):**
```python
from flask_login import LoginManager, UserMixin, login_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('SELECT id, email FROM users WHERE id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return User(row[0], row[1]) if row else None

@app.route('/register', methods=['POST'])
def register():
    email = request.form['email']
    password = request.form['password']
    pw_hash = generate_password_hash(password)
    
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)', (email, pw_hash))
    c.execute('INSERT INTO user_quota (user_id) VALUES (?)', (c.lastrowid,))
    conn.commit()
    conn.close()
    return redirect('/login')

@app.route('/login', methods=['POST'])
def login():
    # Check password, call login_user()
    pass

@app.route('/search', methods=['POST'])
@login_required  # ← This is the key!
def search_flights():
    # Your existing search code
    pass
```

**Create simple HTML forms:**
- `/templates/register.html` - email + password
- `/templates/login.html` - email + password

---

### Week 3-4: Quota System

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

---

### Week 5-6: Stripe Integration

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

### Week 7-8: Polish & Launch

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
- [ ] User downgraded to free tier next month

**Deploy:**
- Already on PythonAnywhere!
- Just reload web app after pushing code
- Optional: Buy domain and configure DNS

---

## 💰 Cost Reality Check

### Year 1 Projection (Realistic - 3-5% Conversion)

**Scenario: 100 registered users, 3-5 paying**

| Month | Users | Paying (3%) | Revenue | Costs | Profit |
|-------|-------|-------------|---------|-------|--------|
| 1-3 | 20 | 1 | $9 | $0 | +$9 |
| 4-6 | 50 | 2 | $18 | $0 | +$18 |
| 7-9 | 75 | 3 | $27 | $0 | +$27 |
| 10-12 | 100 | 4 | $36 | $0 | +$36 |

**Year 1 Total:**
- Revenue: ~$300
- Costs: $500 (lawyer, one-time)
- Net: **-$200 loss**

**BUT you learned:**
- ✅ User authentication
- ✅ Payment processing
- ✅ SaaS business model
- ✅ Real user feedback
- ✅ Portfolio project

**Year 2 (if it works):**
- 300 users × 5% = 15 paying = $135/month
- Annual: ~$1,620
- Costs: $0
- Net: **+$1,620 profit** ✅

This is **learning + side income**, not a unicorn startup.

---

## ⚠️ When to Stop

**Red flags:**
- Taking >20 hours/week consistently
- Not enjoying the work
- Lawyer says "don't do this"
- No users after 3 months
- Thesis/job suffering

**It's OKAY to:**
- Pause for 6 months
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

**Q: Why not use Descope/Auth0 instead of Flask-Login?**

A: For <100 users, Flask-Login is perfect:
- $0 forever (vs $240/mo at scale)
- No external dependency
- 150 lines of code
- Works on PythonAnywhere without config

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

**Q: How do I get first users?**

A: Start small:
1. Friends/family (10-20 users)
2. Reddit r/travel (don't spam!)
3. Product Hunt launch
4. SEO blog posts
5. TikTok/Instagram demos

Expect 10 users/month growth initially.

**Q: What if I build this and nobody pays?**

A: High probability! But you'll learn:
- User auth, payments, SaaS model
- Portfolio project for job search
- Only lost 2 months + $500

**Q: Should I quit job search to focus on this?**

A: **NO!** Job search is priority #1. This is:
- Side project (10-20h/week MAX)
- Learning experience
- Takes 12-18 months to replace salary even if successful

---

## ✅ Decision Checklist

**Proceed with Ultra-MVP IF:**
- [ ] You accept 3-5% conversion (not 25%)
- [ ] You have $500 for lawyer
- [ ] You can dedicate 10-20h/week for 2-3 months
- [ ] You're okay with slow growth
- [ ] Thesis/job comes first
- [ ] You want to learn, not get rich

**DON'T proceed if:**
- [ ] You need income in next 6 months
- [ ] You expect passive income without work
- [ ] You can't afford to "lose" $500
- [ ] You don't have time for side project

---

## 🎯 Immediate Next Steps

### This Week (Decision Phase)
1. ✅ Read this document (you did!)
2. 📋 Research flight scraping legality (2-3 hours)
3. 💰 Confirm you have $500 budget
4. ⏰ Block 10-20h/week in calendar
5. 🤔 Sleep on it, decide go/no-go

### Week 1 (If Go)
1. Install: `pip install flask-login`
2. Create 3 SQLite tables in `jobs.db`
3. Sign up: Stripe test mode
4. Schedule: Lawyer consultation ($300-500)
5. Plan: Print this doc, highlight sections

### Week 2-8
Follow implementation plan above

### Month 3
- Soft launch to 10-20 friends
- Gather feedback
- Iterate or pivot

---

## 📚 Resources

**Auth:**
- Flask-Login docs: https://flask-login.readthedocs.io/

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
1. ✅ Ultra-MVP plan (4-8 weeks, $0/month)
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
**Total length:** ~800 lines (vs 2,500 in original)  
**Reading time:** 15 minutes (vs 45 minutes)


