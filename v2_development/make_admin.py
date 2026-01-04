#!/usr/bin/env python3
"""
Script to make talbuh@gmail.com an admin with unlimited quota
"""
import sqlite3

def make_admin():
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    
    # Update user to be admin
    c.execute('''UPDATE users SET is_admin = 1 WHERE email = 'talbuh@gmail.com' ''')
    rows_affected = c.rowcount
    
    # Update quota to unlimited
    c.execute('''UPDATE user_quota 
                 SET monthly_limit = 999999, tier = 'admin' 
                 WHERE user_id IN (SELECT id FROM users WHERE email = 'talbuh@gmail.com')''')
    
    conn.commit()
    
    # Verify
    c.execute('SELECT id, email, is_admin FROM users WHERE email = ?', ('talbuh@gmail.com',))
    user = c.fetchone()
    
    if user:
        print(f"✅ User updated successfully!")
        print(f"   User ID: {user[0]}")
        print(f"   Email: {user[1]}")
        print(f"   Is Admin: {user[2]}")
        
        c.execute('SELECT monthly_limit, searches_used, tier FROM user_quota WHERE user_id = ?', (user[0],))
        quota = c.fetchone()
        if quota:
            print(f"   Quota: {quota[1]}/{quota[0]} (Tier: {quota[2]})")
    else:
        print(f"⚠️  User talbuh@gmail.com not found in database yet.")
        print(f"   They will be set as admin on first login.")
    
    conn.close()

if __name__ == '__main__':
    make_admin()

