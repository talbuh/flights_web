#!/usr/bin/env python3

# Configure stdout for proper Unicode handling
import sys
try:
    # Force UTF-8 encoding for stdout to handle Unicode properly
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass  # Fallback if reconfigure not available

print("Starting app.py...")
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
import json
print("Flask imported successfully")
import sys
import subprocess
from datetime import datetime, timedelta
import logging
import webbrowser
import threading
import time
import os
import sqlite3
import uuid
from functools import wraps

# Descope authentication
try:
    from descope import DescopeClient, AuthException
    descope_client = DescopeClient(project_id="P37mczF1NShERSaYoouYUx4SNocu")
    print("Descope client initialized")
except ImportError:
    print("Warning: Descope not installed. Run: pip install descope")
    descope_client = None

logging.basicConfig(level=logging.WARNING)

# Initialize SQLite database for job tracking
def init_db():
    """Initialize the jobs database"""
    conn = sqlite3.connect('jobs.db', check_same_thread=False)
    c = conn.cursor()
    
    # Jobs table (existing)
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT,
            current INTEGER,
            total INTEGER,
            current_dates TEXT,
            flights_found INTEGER,
            percentage REAL,
            result TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Users table (for auth)
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
    
    # User quota table
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

def update_job_progress(job_id, current, total, current_dates, status, flights_found=0):
    """Update job progress in database"""
    try:
        conn = sqlite3.connect('jobs.db', check_same_thread=False)
        c = conn.cursor()
        percentage = round((current / total) * 100, 1) if total > 0 else 0
        now = datetime.now().isoformat()
        c.execute('''
            INSERT OR REPLACE INTO jobs 
            (job_id, status, current, total, current_dates, flights_found, percentage, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM jobs WHERE job_id = ?), ?))
        ''', (job_id, status, current, total, current_dates, flights_found, percentage, now, job_id, now))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating job progress: {e}")

def get_job_progress(job_id):
    """Get job progress from database"""
    try:
        conn = sqlite3.connect('jobs.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT status, current, total, current_dates, flights_found, percentage FROM jobs WHERE job_id = ?', (job_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return {
                'status': row[0],
                'current': row[1],
                'total': row[2],
                'current_dates': row[3],
                'flights_found': row[4],
                'percentage': row[5]
            }
        return None
    except Exception as e:
        print(f"Error getting job progress: {e}")
        return None

def save_job_result(job_id, result_data):
    """Save job result to database"""
    try:
        conn = sqlite3.connect('jobs.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('UPDATE jobs SET result = ?, status = ? WHERE job_id = ?', 
                  (json.dumps(result_data), 'completed', job_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving job result: {e}")

def get_job_result(job_id):
    """Get job result from database"""
    try:
        conn = sqlite3.connect('jobs.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT result FROM jobs WHERE job_id = ?', (job_id,))
        row = c.fetchone()
        conn.close()
        
        if row and row[0]:
            return json.loads(row[0])
        return None
    except Exception as e:
        print(f"Error getting job result: {e}")
        return None

# Initialize database on startup
init_db()
print("Database initialized")

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Authentication decorator
def require_auth(f):
    """Decorator to require Descope authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not descope_client:
            # Descope not available, skip auth for development
            kwargs['current_user_id'] = 'dev_user'
            kwargs['current_user_email'] = 'dev@example.com'
            return f(*args, **kwargs)
        
        # Try to get session token from Flask session or cookies
        session_token = session.get('descope_token') or request.cookies.get('DS')
        
        if not session_token:
            return jsonify({'error': 'Authentication required', 'redirect': '/login'}), 401
        
        try:
            # Validate with Descope
            jwt_response = descope_client.validate_session(session_token=session_token)
            user_id = jwt_response.get('sub') or jwt_response.get('userId')
            user_email = jwt_response.get('email')
            
            # Check if user is blocked and get admin status
            conn = sqlite3.connect('jobs.db')
            c = conn.cursor()
            c.execute('SELECT is_blocked, is_admin FROM users WHERE id = ?', (user_id,))
            row = c.fetchone()
            conn.close()
            
            if row and row[0] == 1:
                return jsonify({'error': 'Account blocked. Contact support.'}), 403
            
            # Pass user info to the route (including admin status)
            kwargs['current_user_id'] = user_id
            kwargs['current_user_email'] = user_email
            kwargs['is_admin'] = row[1] if row else 0
            return f(*args, **kwargs)
            
        except Exception as e:
            print(f"Auth error: {e}")
            return jsonify({'error': 'Invalid session', 'redirect': '/login'}), 401
    
    return decorated_function

class FlightSearchEngine:
    def __init__(self):
        self.setup_dependencies()
        
    def setup_dependencies(self):
        try:
            from fast_flights.flights_impl import FlightData, Passengers, TFSData
            from fast_flights.core import get_flights, get_flights_from_filter
            from fast_flights.schema import Result
            self.FlightData = FlightData
            self.Passengers = Passengers
            self.TFSData = TFSData
            self.get_flights = get_flights
            self.get_flights_from_filter = get_flights_from_filter
            self.Result = Result
            print("Flight search engine initialized")
        except ImportError as e:
            print(f"Installing dependencies: {e}")
            self.install_dependencies()
            # After installation, try to import again
            try:
                from fast_flights.flights_impl import FlightData, Passengers, TFSData
                from fast_flights.core import get_flights, get_flights_from_filter
                from fast_flights.schema import Result
                self.FlightData = FlightData
                self.Passengers = Passengers
                self.TFSData = TFSData
                self.get_flights = get_flights
                self.get_flights_from_filter = get_flights_from_filter
                self.Result = Result
                print("Flight search engine initialized after installation")
            except ImportError as e2:
                print(f"Failed to initialize after installation: {e2}")
    
    def install_dependencies(self):
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
            subprocess.check_call([sys.executable, "-m", "pip", "install", "fast-flights"])
        except subprocess.CalledProcessError:
            print("Failed to install dependencies")
    
    def search_date_range(self, config, job_id=None):
        """Advanced search across date ranges"""
        from datetime import datetime, timedelta
        import itertools
        
        try:
            passengers = self.Passengers(
                adults=config.get('adults', 1),
                children=config.get('children', 0),
                infants_in_seat=config.get('infants_seat', 0),
                infants_on_lap=config.get('infants_lap', 0)
            )
            
            max_stops = config.get('max_stops')
            if max_stops == -1:
                max_stops = None
            
            # Parse date ranges
            start_period = datetime.strptime(config['start_period'], '%Y-%m-%d')
            end_period = datetime.strptime(config['end_period'], '%Y-%m-%d')
            min_days = int(config.get('min_vacation_days', 7))
            max_days = int(config.get('max_vacation_days', 21))
            
            # Generate date combinations
            all_combinations = []
            current_date = start_period
            
            print(f"Searching period: {start_period.date()} to {end_period.date()}")
            print(f"Vacation length: {min_days}-{max_days} days")
            
            while current_date <= end_period:
                for vacation_days in range(min_days, max_days + 1):
                    return_date = current_date + timedelta(days=vacation_days)
                    if return_date <= end_period:
                        all_combinations.append((current_date.strftime('%Y-%m-%d'), 
                                              return_date.strftime('%Y-%m-%d'), 
                                              vacation_days))
                current_date += timedelta(days=3)  # Check every 3 days
            
            total_combinations = len(all_combinations)
            print(f"Generated {total_combinations} date combinations to test")
            print(f"Will search ALL combinations (no limit applied)")
            
            # No more limiting - we'll test all combinations!
            
            all_results = []
            
            for i, (dep_date, ret_date, days) in enumerate(all_combinations):
                # Progress bar calculation
                progress_percent = ((i + 1) / total_combinations) * 100
                progress_bar_length = 30
                filled_length = int(progress_bar_length * (i + 1) // total_combinations)
                bar = '=' * filled_length + '-' * (progress_bar_length - filled_length)
                
                # Only print progress in local environment
                if os.environ.get('PORT') is None:  # Local environment
                    print(f"[{bar}] {progress_percent:.1f}% ({i+1}/{total_combinations})")
                    print(f"Testing: {dep_date} -> {ret_date} ({days} days)")
                
                # Send real-time progress update
                send_progress_update(
                    current=i + 1,
                    total=total_combinations,
                    current_dates=f"{dep_date} -> {ret_date} ({days} days)",
                    status="searching",
                    flights_found=len(all_results)
                )
                
                try:
                    flight_data = [
                        self.FlightData(
                            date=dep_date,
                            from_airport=config['from_airport'],
                            to_airport=config['to_airport'],
                            max_stops=max_stops
                        ),
                        self.FlightData(
                            date=ret_date,
                            from_airport=config['to_airport'],
                            to_airport=config['from_airport'],
                            max_stops=max_stops
                        )
                    ]
                    
                    # Convert currency for API
                    api_currency = config.get('currency', 'ILS')
                    
                    # Use get_flights_from_filter to pass currency
                    filter_data = self.TFSData.from_interface(
                        flight_data=flight_data,
                        trip="round-trip",
                        passengers=passengers,
                        seat=config['seat_class'],
                        max_stops=max_stops
                    )
                    
                    result = self.get_flights_from_filter(
                        filter_data,
                        currency=api_currency,
                        mode="common"
                    )
                    
                    if hasattr(result, 'flights') and result.flights:
                        # Process TOP 10 flights from this combination (cheapest first)
                        top_flights = result.flights[:10]  # Take only top 10 cheapest
                        for flight_idx, flight in enumerate(top_flights):
                            # Generate booking URL
                            booking_url = self.generate_booking_url(config['from_airport'], 
                                                                  config['to_airport'], 
                                                                  dep_date, ret_date,
                                                                  config.get('adults', 1),
                                                                  config['seat_class'],
                                                                  config.get('currency', 'ILS'))
                            
                            # Parse flight details for round-trip
                            flight_details = self.parse_round_trip_details(flight, dep_date, ret_date)
                            
                            flight_info = {
                                'departure_date': dep_date,
                                'return_date': ret_date,
                                'vacation_days': days,
                                'airline': getattr(flight, 'name', 'Unknown'),
                                'price': getattr(flight, 'price', 'N/A'),
                                'duration': getattr(flight, 'duration', 'N/A'),
                                'stops': getattr(flight, 'stops', 'N/A'),
                                'departure': getattr(flight, 'departure', 'N/A'),
                                'arrival': getattr(flight, 'arrival', 'N/A'),
                                'is_best': getattr(flight, 'is_best', False),
                                'price_level': getattr(result, 'current_price', 'typical'),
                                'booking_url': booking_url,
                                'combination_rank': flight_idx + 1,  # Rank within this combination
                                'total_options_in_combination': len(result.flights),
                                'outbound_details': flight_details['outbound'],
                                'return_details': flight_details['return']
                            }
                            all_results.append(flight_info)
                        
                        # Only print in local environment
                        if os.environ.get('PORT') is None:
                            print(f"  [OK] Found {len(result.flights)} flights, took top {len(top_flights)} for this combination")
                        
                        # Update progress with found flights
                        send_progress_update(
                            current=i + 1,
                            total=total_combinations,
                            current_dates=f"{dep_date} -> {ret_date} ({days} days)",
                            status="found_flights",
                            flights_found=len(all_results)
                        )
                        
                except Exception as e:
                    # Only print errors in local environment
                    if os.environ.get('PORT') is None:
                        print(f"  [ERROR] {e}")
                    
                    # Update progress with error
                    send_progress_update(
                        current=i + 1,
                        total=total_combinations,
                        current_dates=f"{dep_date} -> {ret_date} ({days} days)",
                        status="error",
                        flights_found=len(all_results)
                    )
                    continue
                
                # Small delay to allow UI updates
                import time
                time.sleep(0.2)  # 200ms delay
            
            # Sort by price (extract numeric value)
            def extract_price(price_str):
                try:
                    import re
                    numbers = re.findall(r'[\d,]+', price_str)
                    if numbers:
                        return int(numbers[0].replace(',', ''))
                    return float('inf')
                except:
                    return float('inf')
            
            all_results.sort(key=lambda x: extract_price(x['price']))
            
            # Only print final results in local environment
            if os.environ.get('PORT') is None:
                print("\nSearch completed.")
                print(f"Total combinations tested: {total_combinations}")
                print(f"Flights found: {len(all_results)}")
                print(f"Returning all {len(all_results)} results to frontend")
            
            # Send completion update
            send_progress_update(
                current=total_combinations,
                total=total_combinations,
                current_dates="Search completed!",
                status="completed",
                flights_found=len(all_results)
            )
            
            return {
                'success': True,
                'flights': all_results,  # Return ALL results to frontend
                'total_found': len(all_results),
                'total_combinations_tested': total_combinations,
                'search_type': 'date_range'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'flights': [],
                'total_found': 0,
                'search_type': 'date_range'
            }
    
    def parse_round_trip_details(self, flight, dep_date, ret_date):
        """Parse round-trip flight details into outbound and return segments"""
        try:
            # Get all available attributes from the flight object
            flight_name = getattr(flight, 'name', 'Unknown')
            duration = getattr(flight, 'duration', 'N/A')
            stops = getattr(flight, 'stops', 'N/A')
            departure_time = getattr(flight, 'departure', 'N/A')
            arrival_time = getattr(flight, 'arrival', 'N/A')
            
            # Debug: Print what we actually get from the API (safe for ASCII consoles)
            if os.environ.get('PORT') is None:  # Only in local environment
                def safe_repr(value):
                    try:
                        return repr(value)
                    except UnicodeEncodeError:
                        # Convert problematic characters
                        if isinstance(value, str):
                            return repr(value.encode('ascii', 'replace').decode('ascii'))
                        else:
                            return str(value).encode('ascii', 'replace').decode('ascii')

                print("DEBUG - Flight object attributes:")
                print(f"  name: {repr(flight_name)}")
                print(f"  duration: {repr(duration)}")
                print(f"  stops: {repr(stops)}")
                print(f"  departure: {repr(departure_time)}")
                print(f"  arrival: {repr(arrival_time)}")

                # Try to get all attributes
                all_attrs = [attr for attr in dir(flight) if not attr.startswith('_')]
                print(f"  All flight attributes: {repr(all_attrs)}")
            
            # Convert to strings for parsing
            departure_time_str = str(departure_time)
            arrival_time_str = str(arrival_time)
            
            from datetime import datetime
            
            try:
                dep_dt = datetime.strptime(dep_date, '%Y-%m-%d')
                ret_dt = datetime.strptime(ret_date, '%Y-%m-%d')
                
                dep_formatted = dep_dt.strftime('%b %d')
                ret_formatted = ret_dt.strftime('%b %d')
            except:
                dep_formatted = dep_date
                ret_formatted = ret_date
            
            # Parse the airline name - handle multiple airlines
            airlines = []
            if ',' in flight_name:
                airlines = [airline.strip() for airline in flight_name.split(',')]
            else:
                airlines = [flight_name.strip()]
            
            outbound_airline = airlines[0] if airlines else 'Unknown'
            return_airline = airlines[1] if len(airlines) > 1 else outbound_airline
            
            # Parse stops
            stops_value = stops
            if isinstance(stops, str):
                if 'nonstop' in stops.lower() or 'direct' in stops.lower():
                    stops_value = 0
                elif 'stop' in stops.lower():
                    try:
                        # Extract number from strings like "1 stop", "2 stops"
                        import re
                        numbers = re.findall(r'\d+', stops)
                        stops_value = int(numbers[0]) if numbers else 1
                    except:
                        stops_value = 1
            
            # Better time extraction - handle various formats
            def extract_time(time_str):
                if not time_str or time_str == 'N/A':
                    return 'Not available'
                
                time_str = str(time_str)
                
                # Handle formats like "7:00 AM on Tue, Dec 30" or "7:00 AM"
                if " on " in time_str:
                    return time_str.split(" on ")[0].strip()
                
                # Handle formats like "07:00" or "7:00 AM"
                import re
                time_match = re.search(r'\d{1,2}:\d{2}\s*(?:AM|PM)?', time_str, re.IGNORECASE)
                if time_match:
                    return time_match.group().strip()
                
                # If we can't parse it, return as is (might still be useful)
                return time_str.strip() if len(time_str.strip()) < 20 else 'Not available'
            
            outbound_departure_time = extract_time(departure_time_str)
            outbound_arrival_time = extract_time(arrival_time_str)
            
            # Try to extract return flight info from the flight name or other attributes
            # Sometimes Google includes return info in the name or other fields
            return_departure_time = 'Not available'
            return_arrival_time = 'Not available'
            return_duration = 'Not available'
            return_stops = 'Not available'
            
            # Check if we have any return flight data in the flight object
            # Some APIs might have return_departure, return_arrival, etc.
            for attr_name in dir(flight):
                if not attr_name.startswith('_'):
                    attr_value = getattr(flight, attr_name, None)
                    if attr_value and 'return' in attr_name.lower():
                        if os.environ.get('PORT') is None:  # Only in local environment
                            print(f"  Found return attribute: {attr_name} = {attr_value}")
            
            # Outbound details (what we have from the API)
            outbound_details = {
                'airline': outbound_airline,
                'date': dep_formatted,
                'departure_time': outbound_departure_time,
                'arrival_time': outbound_arrival_time,
                'duration': str(duration),
                'stops': stops_value
            }
            
            # Return flight details - try to be more intelligent about estimates
            return_details = {
                'airline': return_airline,
                'date': ret_formatted,
                'departure_time': return_departure_time,
                'arrival_time': return_arrival_time,
                'duration': return_duration,
                'stops': return_stops
            }
            
            return {
                'outbound': outbound_details,
                'return': return_details
            }
            
        except Exception as e:
            # Simple fallback - be honest about what we don't know
            from datetime import datetime
            
            try:
                dep_dt = datetime.strptime(dep_date, '%Y-%m-%d')
                ret_dt = datetime.strptime(ret_date, '%Y-%m-%d')
                dep_formatted = dep_dt.strftime('%b %d')
                ret_formatted = ret_dt.strftime('%b %d')
            except:
                dep_formatted = dep_date
                ret_formatted = ret_date
            
            base_airline = getattr(flight, 'name', 'Unknown').split(',')[0].strip()
            
            return {
                'outbound': {
                    'airline': base_airline,
                    'date': dep_formatted,
                    'departure_time': 'Not available',
                    'arrival_time': 'Not available',
                    'duration': str(getattr(flight, 'duration', 'N/A')),
                    'stops': getattr(flight, 'stops', 'N/A')
                },
                'return': {
                    'airline': base_airline,
                    'date': ret_formatted,
                    'departure_time': 'Not available',
                    'arrival_time': 'Not available', 
                    'duration': 'Not available',
                    'stops': 'Not available'
                }
            }

    def generate_booking_url(self, from_airport, to_airport, dep_date, ret_date, adults, seat_class, currency='ILS', is_one_way=False):
        """Generate Google Flights search URL for the specific route and dates"""
        
        # Convert currency for Google
        currency_map = {
            'ILS': 'ILS',
            'USD': 'USD', 
            'EUR': 'EUR',
            'GBP': 'GBP'
        }
        
        google_currency = currency_map.get(currency, 'ILS')
        
        # Format dates for Google Flights URL (YYYY-MM-DD)
        from datetime import datetime, timedelta
        
        try:
            dep_dt = datetime.strptime(dep_date, '%Y-%m-%d')
            dep_formatted = dep_dt.strftime('%Y-%m-%d')
        except Exception:
            dep_formatted = dep_date

        try:
            ret_dt = datetime.strptime(ret_date, '%Y-%m-%d')
            ret_formatted = ret_dt.strftime('%Y-%m-%d')
        except Exception:
            ret_formatted = ret_date
        
        # Create Google Flights search URL with specific parameters
        # This creates a direct search URL that will show results for the exact route and dates
        
        search_params = [
            f"f={1 if is_one_way else 0}",
            "source=flightsfromhome",
            "hl=en",
            "gl=IL",
            f"curr={google_currency}",
        ]
 
        query = (
            f"hl=en&gl=IL&curr={google_currency}&"
            f"q=flights+from+{from_airport}+to+{to_airport}+{dep_formatted}"
        )
        if not is_one_way:
            query += f"+{ret_formatted}"
        
        # Add seat class
        seat_class_map = {
            'economy': 'c:e',
            'premium-economy': 'c:p', 
            'business': 'c:b',
            'first': 'c:f'
        }
        if seat_class in seat_class_map:
            search_params.append(seat_class_map[seat_class])
        
        # Add number of adults
        if adults > 1:
            search_params.append(f"adults={adults}")
        
        final_url = f"https://www.google.com/travel/flights?{'&'.join(search_params)}&{query}"
        
        if os.environ.get('PORT') is None:  # Only in local environment
            print(f"Generated booking URL: {final_url}")
        
        return final_url

    def _parse_price_value(self, price):
        """Convert price representation to a float."""
        if price is None:
            return None
        if isinstance(price, (int, float)):
            return float(price)
        try:
            import re
            price_str = str(price)
            matches = re.findall(r'[\d.,]+', price_str)
            if not matches:
                return None
            numeric = matches[0].replace(',', '')
            return float(numeric)
        except Exception:
            return None

    def search(self, config, job_id=None):
        """Regular single-date search"""
        try:
            passengers = self.Passengers(
                adults=config.get('adults', 1),
                children=config.get('children', 0),
                infants_in_seat=config.get('infants_seat', 0),
                infants_on_lap=config.get('infants_lap', 0)
            )
            
            max_stops = config.get('max_stops')
            if max_stops == -1:
                max_stops = None
            
            if config['trip_type'] == 'round-trip':
                flight_data = [
                    self.FlightData(
                        date=config['departure_date'],
                        from_airport=config['from_airport'],
                        to_airport=config['to_airport'],
                        max_stops=max_stops
                    ),
                    self.FlightData(
                        date=config['return_date'],
                        from_airport=config['to_airport'],
                        to_airport=config['from_airport'],
                        max_stops=max_stops
                    )
                ]
                trip_type = "round-trip"
                
                # Generate booking URL
                booking_url = self.generate_booking_url(config['from_airport'], 
                                                      config['to_airport'], 
                                                      config['departure_date'], 
                                                      config['return_date'],
                                                      config.get('adults', 1),
                                                      config['seat_class'],
                                                      config.get('currency', 'ILS'))
            else:
                flight_data = [
                    self.FlightData(
                        date=config['departure_date'],
                        from_airport=config['from_airport'],
                        to_airport=config['to_airport'],
                        max_stops=max_stops
                    )
                ]
                trip_type = "one-way"
                booking_url = self.generate_booking_url(
                    config['from_airport'],
                    config['to_airport'],
                    config['departure_date'],
                    config['departure_date'],
                    config.get('adults', 1),
                    config['seat_class'],
                    config.get('currency', 'ILS'),
                    is_one_way=True
                )
            
            # Use get_flights_from_filter to pass currency
            api_currency = config.get('currency', 'ILS')
            
            filter_data = self.TFSData.from_interface(
                flight_data=flight_data,
                trip=trip_type,
                passengers=passengers,
                seat=config['seat_class'],
                max_stops=max_stops
            )
            
            result = self.get_flights_from_filter(
                filter_data,
                currency=api_currency,
                mode="common"
            )
            
            flights = []
            price_level = getattr(result, 'current_price', 'typical')
            
            if hasattr(result, 'flights') and result.flights:
                flights = []
                for i, flight in enumerate(result.flights):  # Return ALL flights
                    flight_info = {
                        'rank': i + 1,
                        'airline': getattr(flight, 'name', 'Unknown'),
                        'price': getattr(flight, 'price', 'N/A'),
                        'duration': getattr(flight, 'duration', 'N/A'),
                        'stops': getattr(flight, 'stops', 'N/A'),
                        'departure': getattr(flight, 'departure', 'N/A'),
                        'arrival': getattr(flight, 'arrival', 'N/A'),
                        'arrival_time_ahead': getattr(flight, 'arrival_time_ahead', 'N/A'),
                        'delay': getattr(flight, 'delay', None),
                        'is_best': getattr(flight, 'is_best', False),
                        'booking_url': booking_url
                    }
                    
                    # Add detailed breakdown for round-trip
                    if trip_type == "round-trip":
                        flight_details = self.parse_round_trip_details(flight, config['departure_date'], config['return_date'])
                        flight_info['outbound_details'] = flight_details['outbound']
                        flight_info['return_details'] = flight_details['return']
                    
                    flights.append(flight_info)
            
            return {
                'success': True,
                'flights': flights,
                'price_level': price_level,
                'total_found': len(flights),
                'search_type': 'regular'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'flights': [],
                'price_level': 'unknown',
                'total_found': 0,
                'search_type': 'regular'
            }

    def search_multi_city(self, config, job_id=None):
        """Dispatch multi-city search based on the requested mode."""
        mode = config.get('multi_city_mode', 'multi-city-range')
        if mode == 'multi-city-open-jaw':
            return self._search_multi_city_open_jaw(config, job_id=job_id)
        if mode == 'multi-city-range' or (config.get('start_period') and config.get('end_period')):
            return self._search_multi_city_range(config, job_id=job_id)
        return self._search_multi_city_specific(config, job_id=job_id)

    def _search_multi_city_specific(self, config, job_id=None):
        """Handle multi-city search when exact dates are provided."""
        from datetime import datetime

        try:
            leg1_from = config['leg1_from']
            leg1_to = config['leg1_to'] 
            leg1_date = config['leg1_date']
            
            leg2_from = config['leg2_from']
            leg2_to = config['leg2_to']
            leg2_date = config['leg2_date']
            leg2_flexibility = int(config.get('leg2_flexibility', 1))
            
            leg3_from = config['leg3_from']
            leg3_to = config['leg3_to']
            leg3_date = config['leg3_date']
            
            adults = int(config.get('adults', 1))
            children = int(config.get('children', 0))
            seat_class = config.get('seat_class', 'economy')
            max_stops = int(config.get('max_stops', -1))
            currency = config.get('currency', 'ILS')
            
            if max_stops == -1:
                max_stops = 2
                
            passengers = self.Passengers(
                adults=adults,
                children=children,
            )
            
            api_currency_map = {
                'ILS': 'ILS',
                'USD': 'USD', 
                'EUR': 'EUR',
                'GBP': 'GBP'
            }
            api_currency = api_currency_map.get(currency, 'ILS')
            
            currency_symbol_map = {
                'ILS': 'ILS',
                'USD': 'USD',
                'EUR': 'EUR',
                'GBP': 'GBP'
            }
            currency_symbol = currency_symbol_map.get(currency, currency)

            print("Multi-City Specific Search:")
            print(f"   Leg 1: {leg1_from} -> {leg1_to} on {leg1_date}")
            print(f"   Leg 2: {leg2_from} -> {leg2_to} on {leg2_date} (+/-{leg2_flexibility} days)")
            print(f"   Leg 3: {leg3_from} -> {leg3_to} on {leg3_date}")
            
            try:
                datetime.strptime(leg1_date, '%Y-%m-%d')
                datetime.strptime(leg2_date, '%Y-%m-%d')
                datetime.strptime(leg3_date, '%Y-%m-%d')
            except Exception as date_error:
                return {
                    'success': False,
                    'error': f'Invalid date format provided: {date_error}',
                    'flights': [],
                    'total_found': 0,
                    'search_type': 'multi_city'
                }

            all_combinations = []
            base_leg2_date = datetime.strptime(leg2_date, '%Y-%m-%d')
            leg2_dates = [
                (base_leg2_date + timedelta(days=offset)).strftime('%Y-%m-%d')
                for offset in range(-leg2_flexibility, leg2_flexibility + 1)
            ]
            
            total_combinations = len(leg2_dates)

            if total_combinations == 0:
                send_progress_update(
                    current=0,
                    total=0,
                    current_dates="No valid midpoint dates",
                    status="completed",
                    flights_found=0,
                    job_id=job_id
                )
                return {
                    'success': True,
                    'flights': [],
                    'total_found': 0,
                    'total_combinations_tested': 0,
                    'search_type': 'multi_city',
                    'currency': currency
                }

            print(f"   Testing {total_combinations} date combinations for leg 2...")
            
            for idx, leg2_date_option in enumerate(leg2_dates):
                try:
                    combination_label = f"{leg1_date} -> {leg2_date_option} -> {leg3_date}"
                    send_progress_update(
                        current=idx + 1,
                        total=total_combinations,
                        current_dates=combination_label,
                        status="searching",
                        flights_found=len(all_combinations),
                        job_id=job_id
                    )

                    leg1_flights = self._fetch_one_way_flights(
                        leg1_from,
                        leg1_to,
                        leg1_date,
                        passengers,
                        seat_class,
                        max_stops,
                        api_currency
                    )

                    if not leg1_flights:
                        continue

                    leg2_flights = self._fetch_one_way_flights(
                        leg2_from,
                        leg2_to,
                        leg2_date_option,
                        passengers,
                        seat_class,
                        max_stops,
                        api_currency
                    )

                    if not leg2_flights:
                        continue

                    leg3_flights = self._fetch_one_way_flights(
                        leg3_from,
                        leg3_to,
                        leg3_date,
                        passengers,
                        seat_class,
                        max_stops,
                        api_currency
                    )

                    if not leg3_flights:
                        continue

                    for leg1_flight in leg1_flights[:5]:
                        for leg2_flight in leg2_flights[:5]:
                            for leg3_flight in leg3_flights[:5]:
                                price1 = self._parse_price_value(getattr(leg1_flight, 'price', None))
                                price2 = self._parse_price_value(getattr(leg2_flight, 'price', None))
                                price3 = self._parse_price_value(getattr(leg3_flight, 'price', None))

                                if any(price is None for price in (price1, price2, price3)):
                                    continue

                                combination = {
                                    'total_price': price1 + price2 + price3,
                                    'currency_symbol': currency_symbol,
                                    'leg1': self._build_leg_details(leg1_from, leg1_to, leg1_date, leg1_flight, price1),
                                    'leg2': self._build_leg_details(leg2_from, leg2_to, leg2_date_option, leg2_flight, price2),
                                    'leg3': self._build_leg_details(leg3_from, leg3_to, leg3_date, leg3_flight, price3),
                                    'trip_summary': {
                                        'start_date': leg1_date,
                                        'mid_date': leg2_date_option,
                                        'return_date': leg3_date
                                    }
                                }
                                all_combinations.append(combination)

                        if all_combinations:
                            send_progress_update(
                                current=idx + 1,
                                total=total_combinations,
                                current_dates=combination_label,
                                status="found_flights",
                                flights_found=len(all_combinations),
                                job_id=job_id
                            )

                except Exception as e:
                    print(f"   Error processing leg 2 date {leg2_date_option}: {e}")
                    send_progress_update(
                        current=idx + 1,
                        total=total_combinations,
                        current_dates=f"{leg1_date} -> {leg2_date_option} -> {leg3_date}",
                        status="error",
                        flights_found=len(all_combinations),
                        job_id=job_id
                    )
                    continue

            all_combinations.sort(key=lambda x: x['total_price'])

            print(f"[OK] Found {len(all_combinations)} multi-city combinations (specific dates)")

            send_progress_update(
                current=total_combinations,
                total=total_combinations,
                current_dates="Search completed!",
                status="completed",
                flights_found=len(all_combinations),
                job_id=job_id
            )

            return {
                'success': True,
                'flights': all_combinations,
                'total_found': len(all_combinations),
                'total_combinations_tested': total_combinations,
                'search_type': 'multi_city',
                'currency': currency
            }

        except Exception as e:
            print(f"[ERROR] Multi-city specific search error: {e}")
            return {
                'success': False,
                'error': str(e),
                'flights': [],
                'total_found': 0,
                'search_type': 'multi_city'
            }

    def _search_multi_city_range(self, config, job_id=None):
        """Handle multi-city search over a date range with flexible mid-point."""
        from datetime import datetime, timedelta

        try:
            leg1_from = config['leg1_from']
            leg1_to = config['leg1_to']
            leg2_from = config['leg2_from']
            leg2_to = config['leg2_to']
            leg3_from = config['leg3_from']
            leg3_to = config['leg3_to']

            adults = int(config.get('adults', 1))
            children = int(config.get('children', 0))
            seat_class = config.get('seat_class', 'economy')
            max_stops = int(config.get('max_stops', -1))
            currency = config.get('currency', 'ILS')

            if max_stops == -1:
                max_stops = 2

            passengers = self.Passengers(
                adults=adults,
                children=children,
            )

            start_period = config.get('start_period')
            end_period = config.get('end_period')

            if not start_period or not end_period:
                return {
                    'success': False,
                    'error': 'Missing date range for multi-city search',
                    'flights': [],
                    'total_found': 0,
                    'search_type': 'multi_city'
                }

            try:
                start_date = datetime.strptime(start_period, '%Y-%m-%d')
                end_date = datetime.strptime(end_period, '%Y-%m-%d')
            except Exception as date_error:
                return {
                    'success': False,
                    'error': f'Invalid range dates: {date_error}',
                    'flights': [],
                    'total_found': 0,
                    'search_type': 'multi_city'
                }

            min_days = max(3, int(config.get('min_vacation_days', 7)))
            max_days = max(min_days, int(config.get('max_vacation_days', min_days)))
            leg2_target_day = max(2, int(config.get('leg2_target_day', 8)))
            leg2_flexibility = max(0, int(config.get('leg2_flexibility', 1)))

            api_currency_map = {
                'ILS': 'ILS',
                'USD': 'USD',
                'EUR': 'EUR',
                'GBP': 'GBP'
            }
            api_currency = api_currency_map.get(currency, 'ILS')

            currency_symbol_map = {
                'ILS': 'ILS',
                'USD': 'USD',
                'EUR': 'EUR',
                'GBP': 'GBP'
            }
            currency_symbol = currency_symbol_map.get(currency, currency)

            print("Multi-City Range Search:")
            print(f"   Start period: {start_period} -> {end_period}")
            print(f"   Trip length: {min_days}-{max_days} days")
            print(f"   Mid-trip target day: {leg2_target_day} +/- {leg2_flexibility}")

            combinations_to_test = []
            current_date = start_date
            while current_date <= end_date:
                for total_days in range(min_days, max_days + 1):
                    return_date = current_date + timedelta(days=total_days)
                    if return_date > end_date:
                        continue
                        
                    mid_options = []
                    for offset in range(-leg2_flexibility, leg2_flexibility + 1):
                        mid_day = leg2_target_day + offset
                        if mid_day < 2 or mid_day >= total_days:
                            continue
                        mid_date = current_date + timedelta(days=mid_day - 1)
                        if mid_date >= return_date:
                            continue
                        mid_options.append((mid_day, mid_date))

                    if mid_options:
                        combinations_to_test.append({
                            'start': current_date,
                            'return': return_date,
                            'total_days': total_days,
                            'mid_options': mid_options
                        })

                current_date += timedelta(days=1)

            total_combinations = sum(len(item['mid_options']) for item in combinations_to_test)

            if total_combinations == 0:
                send_progress_update(
                    current=0,
                    total=0,
                    current_dates="No valid multi-city combinations",
                    status="completed",
                    flights_found=0,
                    job_id=job_id
                )
                return {
                    'success': True,
                    'flights': [],
                    'total_found': 0,
                    'total_combinations_tested': 0,
                    'search_type': 'multi_city',
                    'currency': currency
                }

            send_progress_update(
                current=0,
                total=total_combinations,
                current_dates="Preparing multi-city combinations...",
                status="preparing",
                flights_found=0,
                job_id=job_id
            )

            print(f"   Total combinations to test: {total_combinations}")

            all_combinations = []
            processed = 0

            for combo in combinations_to_test:
                start_dt = combo['start']
                return_dt = combo['return']

                for mid_day, mid_dt in combo['mid_options']:
                    processed += 1

                    leg1_date = start_dt.strftime('%Y-%m-%d')
                    leg2_date = mid_dt.strftime('%Y-%m-%d')
                    leg3_date = return_dt.strftime('%Y-%m-%d')

                    if os.environ.get('PORT') is None:
                        print(f"   Combination {processed}/{total_combinations}: {leg1_date} -> {leg2_date} -> {leg3_date}")

                    combination_label = f"{leg1_date} -> {leg2_date} -> {leg3_date}"
                    send_progress_update(
                        current=processed,
                        total=total_combinations,
                        current_dates=combination_label,
                        status="searching",
                        flights_found=len(all_combinations),
                        job_id=job_id
                    )

                    try:
                        leg1_flights = self._fetch_one_way_flights(
                            leg1_from,
                            leg1_to,
                            leg1_date,
                            passengers,
                            seat_class,
                            max_stops,
                            api_currency
                        )

                        if not leg1_flights:
                            continue

                        leg2_flights = self._fetch_one_way_flights(
                            leg2_from,
                            leg2_to,
                            leg2_date,
                            passengers,
                            seat_class,
                            max_stops,
                            api_currency
                        )

                        if not leg2_flights:
                            continue

                        leg3_flights = self._fetch_one_way_flights(
                            leg3_from,
                            leg3_to,
                            leg3_date,
                            passengers,
                            seat_class,
                            max_stops,
                            api_currency
                        )

                        if not leg3_flights:
                            continue

                        for leg1_flight in leg1_flights[:5]:
                            for leg2_flight in leg2_flights[:5]:
                                for leg3_flight in leg3_flights[:5]:
                                    price1 = self._parse_price_value(getattr(leg1_flight, 'price', None))
                                    price2 = self._parse_price_value(getattr(leg2_flight, 'price', None))
                                    price3 = self._parse_price_value(getattr(leg3_flight, 'price', None))

                                    if any(price is None for price in (price1, price2, price3)):
                                        continue

                                    combination = {
                                        'total_price': price1 + price2 + price3,
                                        'currency_symbol': currency_symbol,
                                        'leg1': self._build_leg_details(leg1_from, leg1_to, leg1_date, leg1_flight, price1),
                                        'leg2': self._build_leg_details(leg2_from, leg2_to, leg2_date, leg2_flight, price2),
                                        'leg3': self._build_leg_details(leg3_from, leg3_to, leg3_date, leg3_flight, price3),
                                        'trip_summary': {
                                            'start_date': leg1_date,
                                            'mid_date': leg2_date,
                                            'return_date': leg3_date,
                                            'total_days': combo['total_days'],
                                            'mid_trip_day': mid_day
                                        }
                                    }
                                    all_combinations.append(combination)

                        if all_combinations:
                            send_progress_update(
                                current=processed,
                                total=total_combinations,
                                current_dates=combination_label,
                                status="found_flights",
                                flights_found=len(all_combinations),
                                job_id=job_id
                            )

                    except Exception as leg_error:
                        print(f"   Error computing combination: {leg_error}")
                        send_progress_update(
                            current=processed,
                            total=total_combinations,
                            current_dates=combination_label,
                            status="error",
                            flights_found=len(all_combinations),
                            job_id=job_id
                        )
                        continue
            
            all_combinations.sort(key=lambda x: x['total_price'])
            
            print(f"[OK] Found {len(all_combinations)} multi-city combinations (range mode)")
            
            send_progress_update(
                current=total_combinations,
                total=total_combinations,
                current_dates="Search completed!",
                status="completed",
                flights_found=len(all_combinations),
                job_id=job_id
            )
            
            return {
                'success': True,
                'flights': all_combinations,
                'total_found': len(all_combinations),
                'total_combinations_tested': total_combinations,
                'search_type': 'multi_city',
                'currency': currency
            }
            
        except Exception as e:
            print(f"[ERROR] Multi-city range search error: {e}")
            return {
                'success': False,
                'error': str(e),
                'flights': [],
                'total_found': 0,
                'search_type': 'multi_city'
            }

    def _search_multi_city_open_jaw(self, config, job_id=None):
        """Handle open-jaw (two-leg) multi-city search."""
        from datetime import datetime, timedelta

        try:
            leg1_from = config['leg1_from']
            leg1_to = config['leg1_to']
            leg2_from = config['leg3_from']
            leg2_to = config['leg3_to']

            adults = int(config.get('adults', 1))
            children = int(config.get('children', 0))
            seat_class = config.get('seat_class', 'economy')
            max_stops = int(config.get('max_stops', -1))
            currency = config.get('currency', 'ILS')

            if max_stops == -1:
                max_stops = 2

            passengers = self.Passengers(
                adults=adults,
                children=children,
            )

            start_period = config.get('start_period')
            end_period = config.get('end_period')

            if not start_period or not end_period:
                return {
                    'success': False,
                    'error': 'Missing date range for open-jaw search',
                    'flights': [],
                    'total_found': 0,
                    'search_type': 'multi_city'
                }

            try:
                start_date = datetime.strptime(start_period, '%Y-%m-%d')
                end_date = datetime.strptime(end_period, '%Y-%m-%d')
            except Exception as date_error:
                return {
                    'success': False,
                    'error': f'Invalid range dates: {date_error}',
                    'flights': [],
                    'total_found': 0,
                    'search_type': 'multi_city'
                }

            min_days = max(2, int(config.get('min_vacation_days', 7)))
            max_days = max(min_days, int(config.get('max_vacation_days', min_days)))

            api_currency_map = {
                'ILS': 'ILS',
                'USD': 'USD',
                'EUR': 'EUR',
                'GBP': 'GBP'
            }
            api_currency = api_currency_map.get(currency, 'ILS')

            currency_symbol_map = {
                'ILS': 'ILS',
                'USD': 'USD',
                'EUR': 'EUR',
                'GBP': 'GBP'
            }
            currency_symbol = currency_symbol_map.get(currency, currency)

            print("Open-Jaw Multi-City Search:")
            print(f"   Start period: {start_period} -> {end_period}")
            print(f"   Trip length: {min_days}-{max_days} days")

            combinations_to_test = []
            current_date = start_date

            while current_date <= end_date:
                for total_days in range(min_days, max_days + 1):
                    return_date = current_date + timedelta(days=total_days)
                    if return_date > end_date:
                        continue
                    combinations_to_test.append({
                        'start': current_date,
                        'return': return_date,
                        'total_days': total_days
                    })
                current_date += timedelta(days=1)

            total_combinations = len(combinations_to_test)

            if total_combinations == 0:
                send_progress_update(
                    current=0,
                    total=0,
                    current_dates="No valid open-jaw combinations",
                    status="completed",
                    flights_found=0,
                    job_id=job_id
                )
                return {
                    'success': True,
                    'flights': [],
                    'total_found': 0,
                    'total_combinations_tested': 0,
                    'search_type': 'multi_city',
                    'currency': currency
                }

            send_progress_update(
                current=0,
                total=total_combinations,
                current_dates="Preparing open-jaw combinations...",
                status="preparing",
                flights_found=0,
                job_id=job_id
            )

            print(f"   Total combinations to test: {total_combinations}")

            all_combinations = []

            for idx, combo in enumerate(combinations_to_test, start=1):
                leg1_date = combo['start'].strftime('%Y-%m-%d')
                leg2_date = combo['return'].strftime('%Y-%m-%d')
                combination_label = f"{leg1_date} -> {leg2_date}"

                send_progress_update(
                    current=idx,
                    total=total_combinations,
                    current_dates=combination_label,
                    status="searching",
                    flights_found=len(all_combinations),
                    job_id=job_id
                )

                try:
                    leg1_flights = self._fetch_one_way_flights(
                        leg1_from,
                        leg1_to,
                        leg1_date,
                        passengers,
                        seat_class,
                        max_stops,
                        api_currency
                    )

                    if not leg1_flights:
                        continue

                    leg2_flights = self._fetch_one_way_flights(
                        leg2_from,
                        leg2_to,
                        leg2_date,
                        passengers,
                        seat_class,
                        max_stops,
                        api_currency
                    )

                    if not leg2_flights:
                        continue

                    for flight_a in leg1_flights[:5]:
                        for flight_b in leg2_flights[:5]:
                            price_a = self._parse_price_value(getattr(flight_a, 'price', None))
                            price_b = self._parse_price_value(getattr(flight_b, 'price', None))

                            if price_a is None or price_b is None:
                                continue

                            combination = {
                                'total_price': price_a + price_b,
                                'currency_symbol': currency_symbol,
                                'leg1': self._build_leg_details(leg1_from, leg1_to, leg1_date, flight_a, price_a),
                                'leg2': self._build_leg_details(leg2_from, leg2_to, leg2_date, flight_b, price_b),
                                'trip_summary': {
                                    'start_date': leg1_date,
                                    'return_date': leg2_date,
                                    'total_days': combo['total_days']
                                }
                            }
                            all_combinations.append(combination)

                    if all_combinations:
                        send_progress_update(
                            current=idx,
                            total=total_combinations,
                            current_dates=combination_label,
                            status="found_flights",
                            flights_found=len(all_combinations),
                            job_id=job_id
                        )

                except Exception as combo_error:
                    print(f"   Error computing open-jaw combination {combination_label}: {combo_error}")
                    send_progress_update(
                        current=idx,
                        total=total_combinations,
                        current_dates=combination_label,
                        status="error",
                        flights_found=len(all_combinations),
                        job_id=job_id
                    )
                    continue

            all_combinations.sort(key=lambda x: x['total_price'])

            print(f"[OK] Found {len(all_combinations)} open-jaw combinations")

            send_progress_update(
                current=total_combinations,
                total=total_combinations,
                current_dates="Search completed!",
                status="completed",
                flights_found=len(all_combinations),
                job_id=job_id
            )

            return {
                'success': True,
                'flights': all_combinations,
                'total_found': len(all_combinations),
                'total_combinations_tested': total_combinations,
                'search_type': 'multi_city',
                'currency': currency
            }

        except Exception as e:
            print(f"[ERROR] Open-jaw multi-city search error: {e}")
            return {
                'success': False,
                'error': str(e),
                'flights': [],
                'total_found': 0,
                'search_type': 'multi_city'
            }

    def _fetch_one_way_flights(self, origin, destination, date_str, passengers, seat_class, max_stops, api_currency):
        flight_data = self.FlightData(
            date=date_str,
            from_airport=origin,
            to_airport=destination,
            max_stops=max_stops
        )

        filter_data = self.TFSData.from_interface(
            flight_data=[flight_data],
            trip="one-way",
            passengers=passengers,
            seat=seat_class,
            max_stops=max_stops
        )

        result = self.get_flights_from_filter(filter_data, currency=api_currency)
        return result.flights if hasattr(result, 'flights') and result.flights else []

    def _build_leg_details(self, origin, destination, date_str, flight, price):
        return {
            'from': origin,
            'to': destination,
            'date': date_str,
            'airline': getattr(flight, 'name', 'Unknown'),
            'price': price,
            'duration': getattr(flight, 'duration', 'N/A'),
            'stops': getattr(flight, 'stops', 'N/A'),
            'departure': getattr(flight, 'departure', 'N/A'),
            'arrival': getattr(flight, 'arrival', 'N/A')
            }

# Initialize search engine
print("Initializing search engine...")
try:
    search_engine = FlightSearchEngine()
    print("Search engine initialized successfully")
except Exception as e:
    print(f"Failed to initialize search engine: {e}")
    import traceback
    traceback.print_exc()

# Global variable to store progress updates
progress_updates = []

# Global variable to store last search result
last_search_result = None

def send_progress_update(current, total, current_dates, status, flights_found=0, job_id=None):
    """Send progress update to database (if job_id provided) or global variable"""
    if job_id:
        # Update database for persistent storage
        update_job_progress(job_id, current, total, current_dates, status, flights_found)
    else:
        # Fallback to global variable (for backward compatibility)
        global progress_updates
        update = {
            'current': current,
            'total': total,
            'current_dates': current_dates,
            'status': status,
            'flights_found': flights_found,
            'percentage': round((current / total) * 100, 1) if total > 0 else 0
        }
        progress_updates.append(update)
        # Keep only last 100 updates
        if len(progress_updates) > 100:
            progress_updates = progress_updates[-100:]

@app.route('/')
def index():
    print("DEBUG: index() called")
    try:
        print("DEBUG: About to render template")
        result = render_template('index.html')
        print(f"DEBUG: Template rendered, length: {len(result)}")
        print(f"DEBUG: First 100 chars: {repr(result[:100])}")
        return result
    except Exception as e:
        print(f"DEBUG: Template error: {e}")
        import traceback
        print("DEBUG: Full traceback:")
        traceback.print_exc()
        return f"Template error: {e}", 500

@app.route('/test')
def test():
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Multi-City Test</title></head>
    <body>
        <h1>Multi-City Test Page</h1>
        <select id="trip_type">
            <option value="round-trip">Round Trip</option>
            <option value="one-way">One Way</option>
            <option value="multi-city">Multi-City (3 destinations)</option>
        </select>
        <div id="multi-city-fields" style="display: none; background: yellow; padding: 20px;">
            <h3>Multi-City Fields Visible!</h3>
        </div>
        <script>
            document.getElementById('trip_type').addEventListener('change', function() {
                const fields = document.getElementById('multi-city-fields');
                if (this.value === 'multi-city') {
                    fields.style.display = 'block';
                } else {
                    fields.style.display = 'none';
                }
            });
        </script>
    </body>
    </html>
    '''

@app.route('/login')
def login():
    """Login page with Descope widget"""
    return render_template('login.html', 
                         descope_project_id="P37mczF1NShERSaYoouYUx4SNocu")

@app.route('/auth/callback')
def auth_callback():
    """Handle Descope callback after login"""
    if not descope_client:
        return 'Descope not configured', 500
    
    # Get session token from query parameter or cookie
    session_token = request.args.get('token') or request.cookies.get('DS')
    
    if not session_token:
        return 'No session token found. Please try logging in again.', 401
    
    try:
        # Validate and get user info
        jwt_response = descope_client.validate_session(session_token=session_token)
        user_id = jwt_response.get('sub') or jwt_response.get('userId')
        user_email = jwt_response.get('email')
        user_name = jwt_response.get('name', '')
        
        # Store in Flask session
        session['descope_token'] = session_token
        session['user_id'] = user_id
        session['user_email'] = user_email
        
        # Create user in database if new
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        
        # Check if admin email
        is_admin = 1 if user_email == 'talbuh@gmail.com' else 0
        
        c.execute('''INSERT OR IGNORE INTO users (id, email, name, is_admin) 
                     VALUES (?, ?, ?, ?)''',
                  (user_id, user_email, user_name, is_admin))
        
        # If admin, set unlimited quota (999999)
        if is_admin:
            c.execute('''INSERT INTO user_quota (user_id, monthly_limit, tier) 
                         VALUES (?, 999999, 'admin')
                         ON CONFLICT(user_id) DO UPDATE SET monthly_limit=999999, tier='admin' ''',
                      (user_id,))
        else:
            c.execute('INSERT OR IGNORE INTO user_quota (user_id) VALUES (?)',
                      (user_id,))
        
        conn.commit()
        conn.close()
        
        print(f"User logged in: {user_email}")
        return redirect('/')
        
    except Exception as e:
        print(f"Auth callback error: {e}")
        return f'Auth failed: {e}', 401

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect('/')

@app.route('/admin')
@require_auth
def admin_dashboard(current_user_id, current_user_email, is_admin=0):
    """Admin dashboard - only accessible to admins"""
    if not is_admin:
        return 'Forbidden - Admin access required', 403
    
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    
    # Get basic stats
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM search_history')
    total_searches = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(*) FROM search_history 
                 WHERE DATE(created_at) = DATE('now')''')
    searches_today = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(DISTINCT user_id) FROM search_history 
                 WHERE created_at >= DATE('now', '-30 days')''')
    active_users = c.fetchone()[0]
    
    # Advanced analytics
    # Users who hit the limit (10 searches)
    c.execute('''SELECT COUNT(*) FROM user_quota 
                 WHERE searches_used >= 10 AND tier = 'free' ''')
    users_hit_limit = c.fetchone()[0]
    
    # Paid users (pro, premium, unlimited - excluding admin tier)
    c.execute('''SELECT COUNT(*) FROM user_quota 
                 WHERE tier IN ('pro', 'premium', 'unlimited') AND tier != 'admin' ''')
    paid_users = c.fetchone()[0]
    
    # Conversion rate calculation
    conversion_rate = round((paid_users / users_hit_limit * 100) if users_hit_limit > 0 else 0, 1)
    
    # Average searches per user
    avg_searches = round(total_searches / total_users, 1) if total_users > 0 else 0
    
    # Monthly revenue (estimated based on tiers)
    tier_prices = {'pro': 9.99, 'premium': 29.99, 'unlimited': 19.99}
    c.execute('''SELECT tier, COUNT(*) FROM user_quota 
                 WHERE tier IN ('pro', 'premium', 'unlimited') 
                 GROUP BY tier''')
    monthly_revenue = sum(tier_prices.get(row[0], 0) * row[1] for row in c.fetchall())
    
    # Chart data: Users timeline (last 30 days)
    c.execute('''SELECT DATE(created_at) as day, COUNT(*) as count
                 FROM users
                 WHERE created_at >= DATE('now', '-30 days')
                 GROUP BY DATE(created_at)
                 ORDER BY day''')
    users_timeline = c.fetchall()
    users_timeline_labels = [row[0] for row in users_timeline] if users_timeline else []
    users_timeline_data = [row[1] for row in users_timeline] if users_timeline else []
    
    # Chart data: Tiers distribution
    c.execute('''SELECT tier, COUNT(*) FROM user_quota GROUP BY tier''')
    tiers_data_raw = c.fetchall()
    tiers_dict = {tier: count for tier, count in tiers_data_raw}
    tiers_labels = ['Free', 'Pro', 'Premium', 'Unlimited']
    tiers_data = [
        tiers_dict.get('free', 0),
        tiers_dict.get('pro', 0),
        tiers_dict.get('premium', 0),
        tiers_dict.get('unlimited', 0) + tiers_dict.get('admin', 0)
    ]
    
    # Chart data: Search activity (last 7 days)
    c.execute('''SELECT DATE(created_at) as day, COUNT(*) as count
                 FROM search_history
                 WHERE created_at >= DATE('now', '-7 days')
                 GROUP BY DATE(created_at)
                 ORDER BY day''')
    activity_data_raw = c.fetchall()
    activity_labels = [row[0] for row in activity_data_raw] if activity_data_raw else []
    activity_data = [row[1] for row in activity_data_raw] if activity_data_raw else []
    
    # Chart data: Conversion funnel
    c.execute('SELECT COUNT(*) FROM users')
    funnel_all_users = c.fetchone()[0]
    
    c.execute('SELECT COUNT(DISTINCT user_id) FROM search_history')
    funnel_used_service = c.fetchone()[0]
    
    funnel_hit_limit = users_hit_limit
    funnel_converted = paid_users
    
    funnel_data = [funnel_all_users, funnel_used_service, funnel_hit_limit, funnel_converted]
    
    # Get all users with their quota
    c.execute('''SELECT u.id, u.email, u.is_admin, u.is_blocked, u.created_at,
                        q.tier, q.monthly_limit, q.searches_used
                 FROM users u
                 LEFT JOIN user_quota q ON u.id = q.user_id
                 ORDER BY u.created_at DESC''')
    users = []
    for row in c.fetchall():
        users.append({
            'id': row[0],
            'email': row[1],
            'is_admin': row[2],
            'is_blocked': row[3],
            'created_at': row[4],
            'tier': row[5] or 'free',
            'monthly_limit': row[6] or 10,
            'searches_used': row[7] or 0
        })
    
    conn.close()
    
    stats = {
        'total_users': total_users,
        'total_searches': total_searches,
        'searches_today': searches_today,
        'active_users': active_users
    }
    
    analytics = {
        'users_hit_limit': users_hit_limit,
        'conversion_rate': conversion_rate,
        'avg_searches_per_user': avg_searches,
        'monthly_revenue': monthly_revenue,
        'paid_users': paid_users
    }
    
    chart_data = {
        'users_timeline_labels': users_timeline_labels,
        'users_timeline_data': users_timeline_data,
        'tiers_labels': tiers_labels,
        'tiers_data': tiers_data,
        'activity_labels': activity_labels,
        'activity_data': activity_data,
        'funnel_data': funnel_data
    }
    
    return render_template('admin_dashboard.html', 
                         stats=stats, 
                         analytics=analytics,
                         chart_data=chart_data,
                         users=users)

@app.route('/admin/update_quota', methods=['POST'])
@require_auth
def admin_update_quota(current_user_id, current_user_email, is_admin=0):
    """Update user quota - admin only"""
    if not is_admin:
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    user_id = data.get('user_id')
    tier = data.get('tier')
    monthly_limit = data.get('monthly_limit')
    
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('''UPDATE user_quota 
                 SET tier = ?, monthly_limit = ? 
                 WHERE user_id = ?''',
              (tier, monthly_limit, user_id))
    conn.commit()
    conn.close()
    
    print(f"Admin {current_user_email} updated quota for user {user_id}: {tier}, {monthly_limit}")
    return jsonify({'success': True})

@app.route('/admin/block_user', methods=['POST'])
@require_auth
def admin_block_user(current_user_id, current_user_email, is_admin=0):
    """Block/unblock user - admin only"""
    if not is_admin:
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    user_id = data.get('user_id')
    blocked = data.get('blocked', True)
    
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('UPDATE users SET is_blocked = ? WHERE id = ?',
              (1 if blocked else 0, user_id))
    conn.commit()
    conn.close()
    
    action = 'blocked' if blocked else 'unblocked'
    print(f"Admin {current_user_email} {action} user {user_id}")
    return jsonify({'success': True})

@app.route('/api/user_info')
def user_info():
    """Get current user info (for frontend)"""
    session_token = session.get('descope_token') or request.cookies.get('DS')
    
    if not session_token or not descope_client:
        return jsonify({'logged_in': False})
    
    try:
        jwt_response = descope_client.validate_session(session_token=session_token)
        user_id = jwt_response.get('sub') or jwt_response.get('userId')
        user_email = jwt_response.get('email')
        
        # Get quota and admin status
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        c.execute('SELECT tier, monthly_limit, searches_used FROM user_quota WHERE user_id = ?', 
                  (user_id,))
        quota = c.fetchone()
        
        c.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,))
        admin_row = c.fetchone()
        is_admin = admin_row[0] if admin_row else 0
        
        conn.close()
        
        if not quota:
            quota = ('free', 10, 0)
        
        tier = quota[0] or 'free'
        monthly_limit = quota[1] or 10
        searches_used = quota[2] or 0
        
        # Check if unlimited
        is_unlimited = tier == 'unlimited' or monthly_limit >= 999999
        
        return jsonify({
            'logged_in': True,
            'email': user_email,
            'is_admin': is_admin,
            'tier': tier,
            'monthly_limit': monthly_limit,
            'searches_used': searches_used,
            'searches_remaining': 'Unlimited' if (is_admin or is_unlimited) else (monthly_limit - searches_used)
        })
    except:
        return jsonify({'logged_in': False})

@app.route('/progress_status')
def progress_status():
    """Get current progress status by job_id"""
    job_id = request.args.get('job_id')
    
    if not job_id:
        # Fallback to old behavior for backward compatibility
        global progress_updates
        if progress_updates:
            return jsonify(progress_updates[-1])
        else:
            return jsonify({
                'current': 0,
                'total': 0,
                'current_dates': 'Preparing...',
                'status': 'preparing',
                'flights_found': 0,
                'percentage': 0
            })
    
    # Get progress from database
    progress = get_job_progress(job_id)
    
    if progress:
        return jsonify(progress)
    else:
        return jsonify({
            'current': 0,
            'total': 0,
            'current_dates': 'Preparing...',
            'status': 'preparing',
            'flights_found': 0,
            'percentage': 0
        })

@app.route('/search_results')
def get_search_results():
    """Get the results of a specific job"""
    job_id = request.args.get('job_id')
    
    if not job_id:
        # Fallback to old behavior
        global last_search_result
        if last_search_result is not None:
            return jsonify(last_search_result)
        else:
            return jsonify({'status': 'no_results'})
    
    # Get result from database
    result = get_job_result(job_id)
    
    if result:
        return jsonify(result)
    else:
        return jsonify({'status': 'no_results'})

@app.route('/search', methods=['POST'])
@require_auth
def search_flights(current_user_id, current_user_email, is_admin=0):
    try:
        # Check quota and tier
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        c.execute('SELECT tier, monthly_limit, searches_used FROM user_quota WHERE user_id = ?', 
                  (current_user_id,))
        quota = c.fetchone()
        
        if not quota:
            # First time user - create quota entry
            c.execute('INSERT INTO user_quota (user_id) VALUES (?)', (current_user_id,))
            conn.commit()
            quota = ('free', 10, 0)
        
        tier = quota[0] or 'free'
        monthly_limit = quota[1] or 10
        searches_used = quota[2] or 0
        
        # Skip quota check for admins or unlimited tier users
        skip_quota = is_admin or tier == 'unlimited' or monthly_limit >= 999999
        
        if not skip_quota:
            # Check if quota exceeded
            if searches_used >= monthly_limit:
                conn.close()
                return jsonify({
                    'error': 'Quota exceeded',
                    'message': f'You have used all {monthly_limit} searches. Please upgrade to continue.',
                    'searches_used': searches_used,
                    'monthly_limit': monthly_limit
                }), 429
            
            # Increment quota
            c.execute('UPDATE user_quota SET searches_used = searches_used + 1 WHERE user_id = ?',
                      (current_user_id,))
            conn.commit()
        else:
            print(f"Unlimited access for {current_user_email} (admin={is_admin}, tier={tier})")
        
        conn.close()
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        config = {
            'from_airport': request.form.get('from_airport', 'TLV').upper(),
            'to_airport': request.form.get('to_airport', 'BKK').upper(),
            'departure_date': request.form.get('departure_date'),
            'return_date': request.form.get('return_date'),
            'trip_type': request.form.get('trip_type', 'round-trip'),
            'adults': int(request.form.get('adults', 1)),
            'children': int(request.form.get('children', 0)),
            'infants_seat': int(request.form.get('infants_seat', 0)),
            'infants_lap': int(request.form.get('infants_lap', 0)),
            'seat_class': request.form.get('seat_class', 'economy'),
            'max_stops': int(request.form.get('max_stops', -1)),
            'currency': request.form.get('currency', 'ILS')
        }

        # Initialize job in database
        update_job_progress(job_id, 0, 0, 'Initializing...', 'preparing', 0)

        # Start search in background thread
        import threading
        def background_search():
            try:
                result = search_engine.search(config, job_id=job_id)
                # Store result in database
                save_job_result(job_id, {'result': result, 'config': config})
                
                # Save search history
                conn = sqlite3.connect('jobs.db')
                c = conn.cursor()
                c.execute('''INSERT INTO search_history 
                             (user_id, search_type, search_params, results_count) 
                             VALUES (?, ?, ?, ?)''',
                          (current_user_id, 
                           config.get('trip_type', 'round-trip'),
                           json.dumps(config),
                           len(result.get('flights', []))))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Background search error: {e}")
                update_job_progress(job_id, 0, 0, f'Error: {str(e)}', 'error', 0)
                save_job_result(job_id, {'error': str(e)})

        thread = threading.Thread(target=background_search)
        thread.daemon = True
        thread.start()

        # Return job_id to client
        return jsonify({
            'status': 'search_started',
            'job_id': job_id,
            'message': 'Search started in background'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'flights': [],
            'price_level': 'unknown',
            'total_found': 0
        })

@app.route('/search_range', methods=['POST'])
@require_auth
def search_flights_range(current_user_id, current_user_email, is_admin=0):
    try:
        # Check quota and tier
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        c.execute('SELECT tier, monthly_limit, searches_used FROM user_quota WHERE user_id = ?', 
                  (current_user_id,))
        quota = c.fetchone()
        
        if not quota:
            c.execute('INSERT INTO user_quota (user_id) VALUES (?)', (current_user_id,))
            conn.commit()
            quota = ('free', 10, 0)
        
        tier = quota[0] or 'free'
        monthly_limit = quota[1] or 10
        searches_used = quota[2] or 0
        
        skip_quota = is_admin or tier == 'unlimited' or monthly_limit >= 999999
        
        if not skip_quota:
            if searches_used >= monthly_limit:
                conn.close()
                return jsonify({
                    'error': 'Quota exceeded',
                    'message': f'You have used all {monthly_limit} searches.',
                    'searches_used': searches_used,
                    'monthly_limit': monthly_limit
                }), 429
            
            c.execute('UPDATE user_quota SET searches_used = searches_used + 1 WHERE user_id = ?',
                      (current_user_id,))
            conn.commit()
        
        conn.close()
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        config = {
            'from_airport': request.form.get('from_airport', 'TLV').upper(),
            'to_airport': request.form.get('to_airport', 'BKK').upper(),
            'start_period': request.form.get('start_period'),
            'end_period': request.form.get('end_period'),
            'min_vacation_days': int(request.form.get('min_vacation_days', 7)),
            'max_vacation_days': int(request.form.get('max_vacation_days', 21)),
            'adults': int(request.form.get('adults', 1)),
            'children': int(request.form.get('children', 0)),
            'infants_seat': int(request.form.get('infants_seat', 0)),
            'infants_lap': int(request.form.get('infants_lap', 0)),
            'seat_class': request.form.get('seat_class', 'economy'),
            'max_stops': int(request.form.get('max_stops', -1)),
            'currency': request.form.get('currency', 'ILS')
        }
        
        # Initialize job in database
        update_job_progress(job_id, 0, 0, 'Initializing...', 'preparing', 0)
        
        # Start search in background thread
        def background_search():
            try:
                result = search_engine.search_date_range(config, job_id=job_id)
                save_job_result(job_id, {'result': result, 'config': config})
                
                # Save search history
                conn = sqlite3.connect('jobs.db')
                c = conn.cursor()
                c.execute('''INSERT INTO search_history 
                             (user_id, search_type, search_params, results_count) 
                             VALUES (?, ?, ?, ?)''',
                          (current_user_id, 'date_range', json.dumps(config),
                           len(result.get('flights', []))))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Background search error: {e}")
                update_job_progress(job_id, 0, 0, f'Error: {str(e)}', 'error', 0)
                save_job_result(job_id, {'error': str(e)})
        
        thread = threading.Thread(target=background_search)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'search_started',
            'job_id': job_id,
            'message': 'Search started in background'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'flights': [],
            'total_found': 0,
            'search_type': 'date_range'
        })

@app.route('/search_multi_city', methods=['POST'])
@require_auth
def search_multi_city(current_user_id, current_user_email, is_admin=0):
    try:
        # Check quota and tier
        conn = sqlite3.connect('jobs.db')
        c = conn.cursor()
        c.execute('SELECT tier, monthly_limit, searches_used FROM user_quota WHERE user_id = ?', 
                  (current_user_id,))
        quota = c.fetchone()
        
        if not quota:
            c.execute('INSERT INTO user_quota (user_id) VALUES (?)', (current_user_id,))
            conn.commit()
            quota = ('free', 10, 0)
        
        tier = quota[0] or 'free'
        monthly_limit = quota[1] or 10
        searches_used = quota[2] or 0
        
        skip_quota = is_admin or tier == 'unlimited' or monthly_limit >= 999999
        
        if not skip_quota:
            if searches_used >= monthly_limit:
                conn.close()
                return jsonify({
                    'error': 'Quota exceeded',
                    'message': f'You have used all {monthly_limit} searches.',
                    'searches_used': searches_used,
                    'monthly_limit': monthly_limit
                }), 429
            
            c.execute('UPDATE user_quota SET searches_used = searches_used + 1 WHERE user_id = ?',
                      (current_user_id,))
            conn.commit()
        
        conn.close()
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())

        config = {
            'leg1_from': request.form.get('leg1_from', 'TLV').upper(),
            'leg1_to': request.form.get('leg1_to', 'HKT').upper(),
            'leg2_from': request.form.get('leg2_from', 'HKT').upper(),
            'leg2_to': request.form.get('leg2_to', 'BKK').upper(),
            'leg2_date': request.form.get('leg2_date'),
            'leg2_target_day': int(request.form.get('leg2_target_day', 8) or 8),
            'leg2_flexibility': int(request.form.get('leg2_flexibility', 1) or 1),
            'leg3_from': request.form.get('leg3_from', 'BKK').upper(),
            'leg3_to': request.form.get('leg3_to', 'TLV').upper(),
            'leg3_date': request.form.get('leg3_date'),
            'leg1_date': request.form.get('leg1_date'),
            'adults': int(request.form.get('adults', 1) or 1),
            'children': int(request.form.get('children', 0) or 0),
            'infants_seat': int(request.form.get('infants_seat', 0) or 0),
            'infants_lap': int(request.form.get('infants_lap', 0) or 0),
            'seat_class': request.form.get('seat_class', 'economy'),
            'max_stops': int(request.form.get('max_stops', -1) or -1),
            'currency': request.form.get('currency', 'ILS'),
            'start_period': request.form.get('start_period'),
            'end_period': request.form.get('end_period'),
            'min_vacation_days': int(request.form.get('min_vacation_days', 7) or 7),
            'max_vacation_days': int(request.form.get('max_vacation_days', 21) or 21),
            'multi_city_mode': request.form.get('multi_city_mode', 'multi-city-range')
        }
        
        # Initialize job in database
        update_job_progress(job_id, 0, 0, 'Initializing...', 'preparing', 0)
        
        # Start search in background thread
        def background_search():
            try:
                result = search_engine.search_multi_city(config, job_id=job_id)
                save_job_result(job_id, {'result': result, 'config': config})
                
                # Save search history
                conn = sqlite3.connect('jobs.db')
                c = conn.cursor()
                c.execute('''INSERT INTO search_history 
                             (user_id, search_type, search_params, results_count) 
                             VALUES (?, ?, ?, ?)''',
                          (current_user_id, 'multi_city', json.dumps(config),
                           len(result.get('flights', []))))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Background search error: {e}")
                update_job_progress(job_id, 0, 0, f'Error: {str(e)}', 'error', 0)
                save_job_result(job_id, {'error': str(e)})
        
        thread = threading.Thread(target=background_search)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'search_started',
            'job_id': job_id,
            'message': 'Search started in background'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'flights': [],
            'total_found': 0,
            'search_type': 'multi_city'
        })

def open_browser(port):
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{port}')

if __name__ == '__main__':
    import os
    
    # Get port from environment variable (for deployment) or use 5000 for local
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if 'PORT' in os.environ else '127.0.0.1'
    
    # Only show local messages and open browser if running locally
    if host == '127.0.0.1':
        print("Starting Flight Search Web App...")
        print(f"Access the app at: http://127.0.0.1:{port}")
        
        # Open browser automatically only on first run (not on auto-reload)
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            print("Opening browser in 1.5 seconds...")
            threading.Timer(1.5, open_browser, args=(port,)).start()
    else:
        print(f"Starting Flight Search Web App on port {port}...")
        # Disable verbose logging in production
        import logging
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    try:
        # Run Flask app
        print(f"About to run app on {host}:{port}")
        # Force debug for local development
        debug_mode = True if host == '127.0.0.1' else False
        app.run(debug=debug_mode, host=host, port=port)
    except Exception as e:
        print(f"Error running app: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"Error starting app: {e}")
        if host == '127.0.0.1':  # Only wait for input if running locally
            input("Press Enter to exit...")
