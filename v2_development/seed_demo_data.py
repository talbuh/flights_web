#!/usr/bin/env python3
"""
Seed demo data for testing the dashboard
"""
import sqlite3
from datetime import datetime, timedelta
import random
import uuid

def seed_demo_data():
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    
    print("🌱 Seeding demo data...")
    
    # Generate demo users over the last 30 days
    demo_users = []
    tiers = ['free', 'free', 'free', 'free', 'pro', 'premium', 'unlimited']
    
    for i in range(30):
        days_ago = 30 - i
        users_that_day = random.randint(1, 5)
        
        for _ in range(users_that_day):
            user_id = str(uuid.uuid4())
            email = f"demo{random.randint(1000, 9999)}@example.com"
            tier = random.choice(tiers)
            created_at = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Insert user
            c.execute('''INSERT INTO users (id, email, name, is_admin, is_blocked, created_at) 
                         VALUES (?, ?, ?, 0, 0, ?)''',
                      (user_id, email, f"Demo User {i}", created_at))
            
            # Insert quota
            if tier == 'free':
                monthly_limit = 10
                searches_used = random.randint(0, 12)  # Some hit limit
            elif tier == 'pro':
                monthly_limit = 50
                searches_used = random.randint(5, 30)
            elif tier == 'premium':
                monthly_limit = 200
                searches_used = random.randint(10, 100)
            else:  # unlimited
                monthly_limit = 999999
                searches_used = random.randint(0, 50)
            
            c.execute('''INSERT INTO user_quota (user_id, tier, monthly_limit, searches_used) 
                         VALUES (?, ?, ?, ?)''',
                      (user_id, tier, monthly_limit, searches_used))
            
            demo_users.append((user_id, searches_used, created_at))
    
    print(f"   ✅ Created {len(demo_users)} demo users")
    
    # Generate search history for last 7 days
    search_types = ['round-trip', 'one-way', 'multi-city']
    for days_ago in range(7):
        searches_that_day = random.randint(10, 50)
        
        for _ in range(searches_that_day):
            user_id, max_searches, _ = random.choice(demo_users)
            if random.random() < 0.8:  # 80% chance to add search
                search_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
                search_type = random.choice(search_types)
                results_count = random.randint(5, 50)
                
                c.execute('''INSERT INTO search_history 
                             (user_id, search_type, search_params, results_count, created_at) 
                             VALUES (?, ?, ?, ?, ?)''',
                          (user_id, search_type, '{}', results_count, search_date))
    
    print(f"   ✅ Created search history for last 7 days")
    
    conn.commit()
    conn.close()
    
    print("🎉 Demo data seeded successfully!")
    print("\n💡 Now visit http://127.0.0.1:5000/admin to see the dashboard with data!")

if __name__ == '__main__':
    seed_demo_data()


