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
import os

logging.basicConfig(level=logging.WARNING)

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

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
                safe = lambda value: repr(value)
                print("DEBUG - Flight object attributes:")
                print(f"  name: {safe(flight_name)}")
                print(f"  duration: {safe(duration)}")
                print(f"  stops: {safe(stops)}")
                print(f"  departure: {safe(departure_time)}")
                print(f"  arrival: {safe(arrival_time)}")
                
                # Try to get all attributes
                all_attrs = [attr for attr in dir(flight) if not attr.startswith('_')]
                print(f"  All flight attributes: {safe(all_attrs)}")
            
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

    def search_multi_city(self, config):
        """Dispatch multi-city search based on the requested mode."""
        mode = config.get('multi_city_mode', 'multi-city-range')
        if mode == 'multi-city-open-jaw':
            return self._search_multi_city_open_jaw(config)
        if mode == 'multi-city-range' or (config.get('start_period') and config.get('end_period')):
            return self._search_multi_city_range(config)
        return self._search_multi_city_specific(config)

    def _search_multi_city_specific(self, config):
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
                'ILS': '₪',
                'USD': '$',
                'EUR': '€',
                'GBP': '£'
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
                    flights_found=0
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
                        flights_found=len(all_combinations)
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
                                flights_found=len(all_combinations)
                            )

                except Exception as e:
                    print(f"   Error processing leg 2 date {leg2_date_option}: {e}")
                    send_progress_update(
                        current=idx + 1,
                        total=total_combinations,
                        current_dates=f"{leg1_date} -> {leg2_date_option} -> {leg3_date}",
                        status="error",
                        flights_found=len(all_combinations)
                    )
                    continue

            all_combinations.sort(key=lambda x: x['total_price'])

            print(f"[OK] Found {len(all_combinations)} multi-city combinations (specific dates)")

            send_progress_update(
                current=total_combinations,
                total=total_combinations,
                current_dates="Search completed!",
                status="completed",
                flights_found=len(all_combinations)
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

    def _search_multi_city_range(self, config):
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
                'ILS': '₪',
                'USD': '$',
                'EUR': '€',
                'GBP': '£'
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
                    flights_found=0
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
                flights_found=0
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
                        flights_found=len(all_combinations)
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
                                flights_found=len(all_combinations)
                            )

                    except Exception as leg_error:
                        print(f"   Error computing combination: {leg_error}")
                        send_progress_update(
                            current=processed,
                            total=total_combinations,
                            current_dates=combination_label,
                            status="error",
                            flights_found=len(all_combinations)
                        )
                        continue
            
            all_combinations.sort(key=lambda x: x['total_price'])
            
            print(f"[OK] Found {len(all_combinations)} multi-city combinations (range mode)")
            
            send_progress_update(
                current=total_combinations,
                total=total_combinations,
                current_dates="Search completed!",
                status="completed",
                flights_found=len(all_combinations)
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

    def _search_multi_city_open_jaw(self, config):
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
                'ILS': '₪',
                'USD': '$',
                'EUR': '€',
                'GBP': '£'
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
                    flights_found=0
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
                flights_found=0
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
                    flights_found=len(all_combinations)
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
                            flights_found=len(all_combinations)
                        )

                except Exception as combo_error:
                    print(f"   Error computing open-jaw combination {combination_label}: {combo_error}")
                    send_progress_update(
                        current=idx,
                        total=total_combinations,
                        current_dates=combination_label,
                        status="error",
                        flights_found=len(all_combinations)
                    )
                    continue

            all_combinations.sort(key=lambda x: x['total_price'])

            print(f"[OK] Found {len(all_combinations)} open-jaw combinations")

            send_progress_update(
                current=total_combinations,
                total=total_combinations,
                current_dates="Search completed!",
                status="completed",
                flights_found=len(all_combinations)
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
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Template error: {e}")
        import traceback
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

@app.route('/search_multi_city', methods=['POST'])
def search_multi_city():
    try:
        global progress_updates
        progress_updates = []

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
        
        result = search_engine.search_multi_city(config)
        result['config'] = config
        
        return jsonify(result)
        
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
        print("Opening browser in 1.5 seconds...")
        print(f"Access the app at: http://127.0.0.1:{port}")
        
        # Open browser automatically
        threading.Timer(1.5, open_browser, args=(port,)).start()
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
