#!/usr/bin/env python3

print("Starting app.py...")
from flask import Flask, render_template, request, jsonify, Response
import json
print("Flask imported successfully")
import sys
import subprocess
from datetime import datetime, timedelta
import logging
import webbrowser
import threading
import time

logging.basicConfig(level=logging.WARNING)

app = Flask(__name__)

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
            self.setup_dependencies()
    
    def install_dependencies(self):
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
            subprocess.check_call([sys.executable, "-m", "pip", "install", "fast-flights"])
        except subprocess.CalledProcessError:
            print("Failed to install dependencies")
    
    def search_date_range(self, config):
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
                bar = '█' * filled_length + '-' * (progress_bar_length - filled_length)
                
                # Only print progress in local environment
                if os.environ.get('PORT') is None:  # Local environment
                    print(f"[{bar}] {progress_percent:.1f}% ({i+1}/{total_combinations})")
                    print(f"Testing: {dep_date} -> {ret_date} ({days} days)")
                
                # Send real-time progress update
                send_progress_update(
                    current=i + 1,
                    total=total_combinations,
                    current_dates=f"{dep_date} → {ret_date} ({days} days)",
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
                            print(f"  ✅ Found {len(result.flights)} flights, took top {len(top_flights)} for this combination")
                        
                        # Update progress with found flights
                        send_progress_update(
                            current=i + 1,
                            total=total_combinations,
                            current_dates=f"{dep_date} → {ret_date} ({days} days)",
                            status="found_flights",
                            flights_found=len(all_results)
                        )
                        
                except Exception as e:
                    # Only print errors in local environment
                    if os.environ.get('PORT') is None:
                        print(f"  ❌ Error: {e}")
                    
                    # Update progress with error
                    send_progress_update(
                        current=i + 1,
                        total=total_combinations,
                        current_dates=f"{dep_date} → {ret_date} ({days} days)",
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
                print(f"\n🎉 Search completed!")
                print(f"📊 Total combinations tested: {total_combinations}")
                print(f"✈️ Flights found: {len(all_results)}")
                print(f"🏆 Returning all {len(all_results)} results to frontend")
            
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
            
            # Try to get more detailed attributes that might exist
            departure_time_str = str(departure_time)
            arrival_time_str = str(arrival_time)
            
            # Based on our analysis: round-trip search only returns outbound data
            # We need to create realistic estimates for the return flight
            
            from datetime import datetime
            
            try:
                dep_dt = datetime.strptime(dep_date, '%Y-%m-%d')
                ret_dt = datetime.strptime(ret_date, '%Y-%m-%d')
                
                dep_formatted = dep_dt.strftime('%b %d')
                ret_formatted = ret_dt.strftime('%b %d')
            except:
                dep_formatted = dep_date
                ret_formatted = ret_date
            
            # Since round-trip search only returns outbound data, we'll use that for outbound
            # and create realistic estimates for return
            
            # Parse the outbound data (what we actually have)
            outbound_airline = flight_name.split(',')[0].strip() if ',' in flight_name else flight_name
            outbound_duration = str(duration)
            outbound_departure = departure_time_str
            outbound_arrival = arrival_time_str
            
            # Parse stops
            stops_value = stops
            if isinstance(stops, str):
                if 'nonstop' in stops.lower():
                    stops_value = 0
                elif 'stop' in stops.lower():
                    try:
                        stops_value = int(''.join(filter(str.isdigit, stops)))
                    except:
                        stops_value = 'N/A'
            
            # Extract time from departure string (e.g., "7:00 AM on Tue, Dec 30" -> "7:00 AM")
            outbound_time = "TBD"
            if "on " in outbound_departure:
                outbound_time = outbound_departure.split(" on ")[0]
            
            # Extract time from arrival string
            outbound_arrival_time = "TBD"
            if "on " in outbound_arrival:
                outbound_arrival_time = outbound_arrival.split(" on ")[0]
            
            # Create return flight estimates
            return_airline = flight_name.split(',')[1].strip() if ',' in flight_name else outbound_airline
            
            # Outbound details (what we actually have from Google)
            outbound_details = {
                'airline': outbound_airline,
                'date': dep_formatted,
                'departure_time': outbound_time,
                'arrival_time': outbound_arrival_time,
                'duration': outbound_duration,
                'stops': stops_value
            }
            
            # Return flight - Google doesn't provide separate return details
            return_details = {
                'airline': return_airline,
                'date': ret_formatted,
                'departure_time': 'Not available',
                'arrival_time': 'Not available',
                'duration': 'Not available',
                'stops': 'Not available'
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

    def generate_booking_url(self, from_airport, to_airport, dep_date, ret_date, adults, seat_class, currency='ILS'):
        """Generate Google Flights search URL for the specific route and dates"""
        base_url = "https://www.google.com/travel/flights"
        
        # Convert currency for Google
        currency_map = {
            'ILS': 'ILS',
            'USD': 'USD', 
            'EUR': 'EUR',
            'GBP': 'GBP'
        }
        
        google_currency = currency_map.get(currency, 'ILS')
        
        # Create a more specific search URL using actual dates and route
        from urllib.parse import urlencode
        import base64
        
        # Try to create a more specific search by encoding the actual route and dates
        # Format dates for Google (YYYYMMDD)
        dep_formatted = dep_date.replace('-', '')
        ret_formatted = ret_date.replace('-', '')
        
        # Create URL with actual search parameters
        # Since we don't have flight numbers, we'll create the best possible search URL
        
        params = {
            'f': '0',  # Round trip
            'hl': 'en', 
            'gl': 'IL',
            'curr': google_currency,
            'adults': str(adults) if adults != 1 else '1'
        }
        
        # Add seat class if specified
        seat_class_map = {
            'economy': '1',
            'premium-economy': '2', 
            'business': '3',
            'first': '4'
        }
        if seat_class in seat_class_map:
            params['seat'] = seat_class_map[seat_class]
        
        # Try to build a search URL that will show results for the specific route and dates
        # This is the best we can do without flight numbers from the API
        base_search_url = f"{base_url}?{urlencode(params)}"
        
        # Add a comment in the URL to help identify the search
        search_comment = f"# Search: {from_airport} to {to_airport}, {dep_date} - {ret_date}"
        
        return base_search_url

    def search(self, config):
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
                booking_url = None
            
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

# Initialize search engine
search_engine = FlightSearchEngine()

# Global variable to store progress updates
progress_updates = []

def send_progress_update(current, total, current_dates, status, flights_found=0):
    """Send progress update to connected clients"""
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
    return render_template('index.html')

@app.route('/progress_status')
def progress_status():
    """Get current progress status"""
    global progress_updates
    if progress_updates:
        return jsonify(progress_updates[-1])  # Return latest update
    else:
        return jsonify({
            'current': 0,
            'total': 0,
            'current_dates': 'Preparing...',
            'status': 'preparing',
            'flights_found': 0,
            'percentage': 0
        })

@app.route('/search', methods=['POST'])
def search_flights():
    try:
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
        
        result = search_engine.search(config)
        result['config'] = config
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'flights': [],
            'price_level': 'unknown',
            'total_found': 0
        })

@app.route('/search_range', methods=['POST'])
def search_flights_range():
    try:
        # Clear previous progress updates
        global progress_updates
        progress_updates = []
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
        
        result = search_engine.search_date_range(config)
        result['config'] = config
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'flights': [],
            'total_found': 0,
            'search_type': 'date_range'
        })

def open_browser():
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5000')

if __name__ == '__main__':
    import os
    
    # Get port from environment variable (for deployment) or use 5000 for local
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if 'PORT' in os.environ else '127.0.0.1'
    
    # Only show local messages and open browser if running locally
    if host == '127.0.0.1':
        print("Starting Flight Search Web App...")
        print("Opening browser in 1.5 seconds...")
        print("Access the app at: http://127.0.0.1:5000")
        
        # Open browser automatically
        threading.Timer(1.5, open_browser).start()
    else:
        print(f"Starting Flight Search Web App on port {port}...")
        # Disable verbose logging in production
        import logging
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    try:
        # Run Flask app
        app.run(debug=False, host=host, port=port)
    except Exception as e:
        print(f"Error starting app: {e}")
        if host == '127.0.0.1':  # Only wait for input if running locally
            input("Press Enter to exit...")
