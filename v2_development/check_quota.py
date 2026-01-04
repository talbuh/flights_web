#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick script to check current quota status
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3

def check_quota():
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    
    # Get all users and their quota
    c.execute('''SELECT u.email, u.is_admin, 
                        q.tier, q.monthly_limit, q.searches_used
                 FROM users u
                 LEFT JOIN user_quota q ON u.id = q.user_id
                 ORDER BY u.created_at DESC''')
    
    users = c.fetchall()
    
    if not users:
        print("❌ No users found in database")
        conn.close()
        return
    
    print("\n📊 Current Quota Status:\n")
    print(f"{'Email':<30} {'Admin':<8} {'Tier':<12} {'Used/Limit':<15}")
    print("-" * 70)
    
    for user in users:
        email, is_admin, tier, limit, used = user
        admin_badge = "👑 Yes" if is_admin else "No"
        tier_display = tier or 'free'
        used_display = used or 0
        limit_display = limit or 10
        
        if limit_display >= 999999:
            quota_str = f"{used_display}/∞"
        else:
            quota_str = f"{used_display}/{limit_display}"
        
        print(f"{email:<30} {admin_badge:<8} {tier_display:<12} {quota_str:<15}")
    
    conn.close()
    print()

if __name__ == '__main__':
    check_quota()

