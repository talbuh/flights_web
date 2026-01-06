#!/usr/bin/env python3
"""
Quick script to grant unlimited access to a specific email
WITHOUT admin privileges
"""
import sqlite3
import sys

def grant_unlimited(email):
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    
    # Check if user exists
    c.execute('SELECT id, email FROM users WHERE email = ?', (email,))
    user = c.fetchone()
    
    if not user:
        print(f"❌ User {email} not found in database")
        print(f"   They need to login at least once first!")
        conn.close()
        return
    
    user_id = user[0]
    
    # Grant unlimited tier (NOT admin)
    c.execute('''UPDATE user_quota 
                 SET tier = 'unlimited', monthly_limit = 999999
                 WHERE user_id = ?''', (user_id,))
    
    # Make sure they're not blocked
    c.execute('UPDATE users SET is_blocked = 0 WHERE id = ?', (user_id,))
    
    conn.commit()
    
    # Verify
    c.execute('''SELECT u.email, u.is_admin, u.is_blocked, 
                        q.tier, q.monthly_limit, q.searches_used
                 FROM users u
                 LEFT JOIN user_quota q ON u.id = q.user_id
                 WHERE u.id = ?''', (user_id,))
    result = c.fetchone()
    
    print(f"✅ Unlimited access granted!")
    print(f"   Email: {result[0]}")
    print(f"   Is Admin: {'Yes' if result[1] else 'No'}")
    print(f"   Is Blocked: {'Yes' if result[2] else 'No'}")
    print(f"   Tier: {result[3]}")
    print(f"   Quota: {result[5]}/{result[4]}")
    print(f"\n💡 User can now search unlimited times (but has NO admin access)")
    
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python grant_unlimited.py <email>")
        print("Example: python grant_unlimited.py user@example.com")
        sys.exit(1)
    
    email = sys.argv[1]
    grant_unlimited(email)


