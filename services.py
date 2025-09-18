"""
Business logic services for the Pilot Salary Calculator
"""
import os
import sys
import re
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set, Any

import pandas as pd

from config import SalaryConfig
from models import FlightLeg, DutyDay, PilotProfile, SalaryCalculation, BonusInfo, MissingAirportError
from utils import resource_path, calculate_tax, validate_numeric_input


class AirportService:
    """Service for managing airport coordinates"""
    
    def __init__(self):
        # Use user's AppData directory for persistence in exe
        import os
        if getattr(sys, 'frozen', False):
            # Running as exe - use AppData
            app_data = os.path.expanduser("~\\AppData\\Local\\PilotSalaryCalc")
            os.makedirs(app_data, exist_ok=True)
            self.csv_path = os.path.join(app_data, "cord_airport.csv")
        else:
            # Running as script - use local file
            self.csv_path = resource_path("cord_airport.csv")
            
        self.coordinates: Dict[str, Tuple[float, float]] = {}
        self._load_coordinates()
        self.logger = logging.getLogger(__name__)
    
    def _load_coordinates(self) -> None:
        """Load airport coordinates from CSV file"""
        if not os.path.exists(self.csv_path):
            self._create_default_csv()
            return
        
        try:
            # Try different separators and encodings
            for sep in [';', ',', '\t']:
                for encoding in ['utf-8', 'latin1', 'cp1252']:
                    try:
                        df = pd.read_csv(self.csv_path, sep=sep, decimal=',', encoding=encoding)
                        # Check for new EU format (iata_code column)
                        if all(col in df.columns for col in ['iata_code', 'Lat', 'Long']):
                            self.coordinates = {
                                row['iata_code']: (row['Lat'], row['Long']) 
                                for _, row in df.iterrows()
                                if pd.notna(row['iata_code'])  # Skip empty IATA codes
                            }
                            return
                        # Check for old format (IATA column)
                        elif all(col in df.columns for col in ['IATA', 'Lat', 'Long']):
                            self.coordinates = {
                                row['IATA']: (row['Lat'], row['Long']) 
                                for _, row in df.iterrows()
                            }
                            return
                    except Exception:
                        continue
            
            raise IOError(f"Could not parse CSV '{self.csv_path}' with any known format.")
            
        except Exception as e:
            raise IOError(f"Failed to load {self.csv_path}: {e}")
    
    def _create_default_csv(self) -> None:
        """Create default airport CSV file"""
        default_airports = [
            "IATA;Lat;Long",
            "MXP;45,6306;8,7281",
            "FCO;41,8003;12,2389",
            "BGY;45,6739;9,7042",
            "LIN;45,4450;9,2808"
        ]
        
        try:
            with open(self.csv_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(default_airports))
        except Exception as e:
            raise IOError(f"Could not create default airport file '{self.csv_path}': {e}")
    
    def get_coordinates(self, iata_code: str) -> Tuple[float, float]:
        """Get coordinates for an airport"""
        if iata_code not in self.coordinates:
            raise MissingAirportError(iata_code)
        return self.coordinates[iata_code]
    
    def add_airport(self, iata_code: str, lat: float, lon: float) -> None:
        """Add new airport coordinates"""
        self.coordinates[iata_code] = (lat, lon)
        self._save_to_csv(iata_code, lat, lon)
        self.logger.info(f"Added new airport {iata_code}: ({lat}, {lon})")
    
    def _save_to_csv(self, iata: str, lat: float, lon: float) -> None:
        """Save new airport to CSV file"""
        try:
            with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                lat_str = str(lat).replace('.', ',')
                lon_str = str(lon).replace('.', ',')
                # Use proper CSV format: icao_code;iata_code;gps_code;Lat;Long
                f.write(f"\n;{iata};{iata};{lat_str};{lon_str}")
        except Exception as e:
            raise IOError(f"Could not save airport to CSV: {e}")


class DistanceCalculator:
    """Service for calculating flight distances"""
    
    def __init__(self, airport_service: AirportService):
        self.airport_service = airport_service
    
    def calculate_distance(self, departure: str, arrival: str) -> float:
        """
        Calculate great circle distance between airports in nautical miles
        
        Args:
            departure: IATA code of departure airport
            arrival: IATA code of arrival airport
        
        Returns:
            Distance in nautical miles
        """
        dep_coords = self.airport_service.get_coordinates(departure)
        arr_coords = self.airport_service.get_coordinates(arrival)
        
        lat_d_deg, lon_d_deg = dep_coords
        lat_a_deg, lon_a_deg = arr_coords
        
        # Convert string coordinates to float (handle comma decimal separator)
        lat_d_deg = float(str(lat_d_deg).replace(',', '.'))
        lon_d_deg = float(str(lon_d_deg).replace(',', '.'))
        lat_a_deg = float(str(lat_a_deg).replace(',', '.'))
        lon_a_deg = float(str(lon_a_deg).replace(',', '.'))
        
        # Convert to radians
        lon_d, lat_d, lon_a, lat_a = map(math.radians, [lon_d_deg, lat_d_deg, lon_a_deg, lat_a_deg])
        
        # Great circle distance calculation
        arg = (math.sin(lat_d) * math.sin(lat_a) + 
               math.cos(lat_d) * math.cos(lat_a) * math.cos(lon_a - lon_d))
        
        # Clamp to valid range to avoid floating point errors
        arg = max(-1.0, min(1.0, arg))
        
        # Return distance in nautical miles
        return max(0.0, 3440.0 * math.acos(arg))


class RosterParser:
    """Service for parsing pilot roster text files"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_roster_text(self, text_content: str) -> Dict[str, List[Any]]:
        """Parse roster text and extract daily schedule"""
        data = {"dailySchedule": []}
        
        if not text_content or not text_content.strip():
            raise ValueError("Empty roster content")
        
        lines = text_content.strip().split('\n')
        day_pattern = re.compile(r"^\d{2}/\d{2}/\d{4}")
        
        # Find start of schedule
        schedule_start = next(
            (i for i, line in enumerate(lines) if day_pattern.search(line)), 
            -1
        )
        
        if schedule_start == -1:
            raise ValueError("No valid date entries found in roster")
        
        current_day_lines = []
        
        for line in lines[schedule_start:]:
            if line.strip().startswith("Total Hours and Statistics"):
                break
            
            line = line.strip()
            if not line:
                continue
            
            if day_pattern.match(line) and current_day_lines:
                day_data = self._process_day_block(current_day_lines)
                if day_data:
                    data["dailySchedule"].append(day_data)
                current_day_lines = [line]
            else:
                current_day_lines.append(line)
        
        # Process last day
        if current_day_lines:
            day_data = self._process_day_block(current_day_lines)
            if day_data:
                data["dailySchedule"].append(day_data)
        
        if not data["dailySchedule"]:
            raise ValueError("No valid schedule data found")
        
        return data
    
    def _process_day_block(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Process a block of lines for a single day"""
        if not lines:
            return None
        
        day_text = "\n".join(lines)
        day_pattern = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(\w+)")
        day_match = day_pattern.match(lines[0])
        
        if not day_match:
            return None
        
        try:
            date_obj = datetime.strptime(day_match.group(1), '%d/%m/%Y')
        except ValueError:
            self.logger.warning(f"Invalid date format: {day_match.group(1)}")
            return None
        
        day_data = {
            "date": date_obj.strftime('%Y-%m-%d'),
            "dayOfWeek": day_match.group(2),
            "duty": {"legs": []},
            "raw_text": day_text
        }
        
        # Determine duty type - exclude TAXI from duty codes as they are flight legs
        duty_code_match = re.search(r'\s(PSBL|PSBE|ESBY|ADTY|CSBE|CSBL|GDO|D/O|LVE|SIM|M2D1|LSBY|REST|WD/O|SIMI|G/S|LTGI)(\s|$)', lines[0])
        is_flight_day = "EJU" in day_text or "FR" in day_text or re.search(r'\s\d{4}\s', day_text) or "TAXI" in day_text or "OWN" in day_text
        initial_duty_code = duty_code_match.group(1) if duty_code_match else None
        
        if is_flight_day:
            day_data["duty"]["type"] = "Flight"
            if initial_duty_code:
                standby_descriptions = {
                    "PSBE": "MXP Standby",
                    "ESBY": "Early Standby", 
                    "ADTY": "Airport Duty",
                    "LSBY": "Late Standby"
                }
                day_data["duty"]["initialDuty"] = standby_descriptions.get(
                    initial_duty_code, initial_duty_code
                )
        elif initial_duty_code:
            self._process_non_flight_duty(day_data, initial_duty_code)
        else:
            day_data["duty"]["type"] = "Unknown"
        
        # Extract flight legs
        self._extract_flight_legs(day_data, lines)
        
        # Check for additional training duties on flight days
        self._extract_training_duties(day_data, lines)
        
        return day_data
    
    def _process_non_flight_duty(self, day_data: Dict[str, Any], duty_code: str) -> None:
        """Process non-flight duty types"""
        standby_codes = {
            "PSBL": ("Standby", "Gapfill Standby Late"),
            "PSBE": ("Standby", "MXP Standby"),
            "ADTY": ("Airport Duty", "Airport Duty"),
            "CSBE": ("Standby", "Crewing Standby"),
            "CSBL": ("Standby", "Crewing Standby Late"),
            "ESBY": ("Standby", "Early Standby"),
            "LSBY": ("Standby", "Late Standby")
        }
        
        day_off_codes = {
            "GDO": ("Day Off", "Guaranteed Day Off"),
            "D/O": ("Day Off", "Day off"),
            "W/DO": ("Day Off", "Weekly Day Off"),  # Added W/DO support
            "WD/O": ("Day Off", "Wrap Around Day Off")  # Day off - no diaria
        }
        
        rest_day_codes = {
            "REST": ("Rest Day", "Rest Day")        # Should count as diaria
        }
        
        training_codes = {
            "LVE": ("Leave", "Annual leave"),
            "SIM": ("Training", "Simulator"),
            "M2D1": ("Training", "Module 2 Day 1"),
            "SIMI": ("Training", "Simulator instructor"),  # 4 sectors
            "G/S": ("Training", "Ground School"),  # Training FO duty - 8 hours, 2 nominal sectors
            "LTGI": ("Training", "Pre Line training ground Instructor")  # Training FO duty - 8 hours, 2 nominal sectors
        }
        
        taxi_codes = {
            # Pattern matches TAXI followed by optional numbers (e.g., TAXI71, TAXI72)
        }
        
        other_codes = training_codes
        
        if duty_code in standby_codes:
            duty_type, description = standby_codes[duty_code]
        elif duty_code in day_off_codes:
            duty_type, description = day_off_codes[duty_code]
        elif duty_code in rest_day_codes:
            duty_type, description = rest_day_codes[duty_code]
        elif duty_code in other_codes:
            duty_type, description = other_codes[duty_code]
        else:
            duty_type, description = "Unknown", duty_code
        
        day_data["duty"]["type"] = duty_type
        day_data["duty"]["description"] = description
        
        # Parse duty times for airport duty
        if duty_code == "ADTY":
            self._parse_airport_duty_times(day_data)
    
    def _parse_airport_duty_times(self, day_data: Dict[str, Any]) -> None:
        """Parse airport duty start and end times"""
        # Look for time patterns in the raw data
        day_text = day_data.get('raw_text', '')
        
        # Pattern to match time ranges like "06:00 - 12:00"
        time_range_pattern = re.compile(r'(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})')
        
        match = time_range_pattern.search(day_text)
        if match:
            start_time_str = match.group(1)
            end_time_str = match.group(2)
            
            try:
                start_parts = start_time_str.split(':')
                end_parts = end_time_str.split(':')
                start_hour, start_min = int(start_parts[0]), int(start_parts[1]) if len(start_parts) >= 2 else 0
                end_hour, end_min = int(end_parts[0]), int(end_parts[1]) if len(end_parts) >= 2 else 0
                
                # Calculate duration in hours
                start_minutes = start_hour * 60 + start_min
                end_minutes = end_hour * 60 + end_min
                
                # Handle overnight duties
                if end_minutes <= start_minutes:
                    end_minutes += 24 * 60
                
                duration_hours = (end_minutes - start_minutes) / 60
                day_data["duty"]["airport_duty_hours"] = duration_hours
                
                self.logger.debug(f"Parsed airport duty: {start_time_str} to {end_time_str} = {duration_hours:.1f} hours")
                
            except (ValueError, AttributeError) as e:
                self.logger.warning(f"Could not parse airport duty times: {e}")
                day_data["duty"]["airport_duty_hours"] = 6  # Default assumption
        else:
            day_data["duty"]["airport_duty_hours"] = 6  # Default assumption
            
        day_data["duty"]["was_called"] = False  # Will be set if pilot was called to fly
        
    def _extract_flight_legs(self, day_data: Dict[str, Any], lines: List[str]) -> None:
        """Extract flight legs from day lines"""
        leg_pattern = re.compile(r"([A-Z0-9]+)\s*(?:\[(\w+)\])?\s*(\*?)\s*([A-Z]{3})\s*-\s*([A-Z]{3})")
        time_pattern = re.compile(r"(A?)(\d{2}:\d{2}[^\s]*)\s*-\s*(A?)(\d{2}:\d{2}[^\s]*)")
        
        for line in lines:
            if line.strip().startswith(('CP ', 'FO ', 'FA ', 'PU ')):
                continue
            
            # Find ALL flight legs in the line, not just the first one
            leg_matches = leg_pattern.findall(line)
            time_matches = time_pattern.findall(line)
            
            for i, leg_match in enumerate(leg_matches):
                leg = {
                    "flightNumber": leg_match[0],
                    "aircraft": leg_match[1] if leg_match[1] else None,
                    "origin": leg_match[3],
                    "destination": leg_match[4],
                    "isPositioning": bool(leg_match[2]) or leg_match[0].startswith('TAXI'),
                    "hasActualTimes": False
                }
                
                # Match corresponding time if available
                if i < len(time_matches):
                    time_match = time_matches[i]
                    leg["hasActualTimes"] = bool(time_match[0]) or bool(time_match[2])
                    leg["takeOffTime"] = time_match[1]
                    leg["landingTime"] = time_match[3]
                
                day_data["duty"]["legs"].append(leg)
    
    def _extract_training_duties(self, day_data: Dict[str, Any], lines: List[str]) -> None:
        """Extract training duties that appear alongside flight legs"""
        day_data["duty"]["training_duties"] = day_data["duty"].get("training_duties", [])
        
        # Check for G/S and LTGI duties - only count once per day regardless of multiple sessions
        day_text = "\n".join(lines)
        has_gs = bool(re.search(r'\bG/S\b', day_text))
        has_ltgi = bool(re.search(r'\bLTGI\b', day_text))
        
        if has_gs:
            day_data["duty"]["training_duties"].append({
                "type": "G/S",
                "description": "Ground School",
                "sectors": 4.0
            })
            
        if has_ltgi:
            day_data["duty"]["training_duties"].append({
                "type": "LTGI", 
                "description": "Pre Line training ground Instructor",
                "sectors": 4.0
            })


class SalaryCalculatorService:
    """Main service for calculating pilot salaries"""
    
    def __init__(self, airport_service: AirportService):
        self.airport_service = airport_service
        self.distance_calculator = DistanceCalculator(airport_service)
        self.logger = logging.getLogger(__name__)
    
    def calculate_salary(self, roster_data: Dict[str, Any], profile: PilotProfile) -> Tuple[pd.DataFrame, pd.DataFrame, List[BonusInfo], float, Set[str], SalaryCalculation]:
        """
        Calculate complete salary breakdown
        
        Returns:
            Tuple of (detailed_df, grouped_df, ido_bonuses, night_stop_bonus, extra_diaria_days, salary_calculation)
        """
        # Get position configuration
        base_salary, allowance, sector_value, diaria, ido_value = SalaryConfig.POSITIONS[profile.position]
        sector_threshold = SalaryConfig.CONTRACTS[profile.contract_type]['soglia_settori']
        
        # Process roster
        detailed_df, grouped_df, ido_bonuses, night_stop_bonus, extra_diaria_days = self._process_roster_data(
            roster_data, profile, sector_value, sector_threshold, ido_value
        )
        
        if detailed_df.empty:
            raise ValueError("No valid flight data found in roster")
        
        # Calculate salary components
        salary_calc = self._calculate_salary_components(
            detailed_df, grouped_df, profile, base_salary, allowance, 
            sector_value, night_stop_bonus, sum(b.amount for b in ido_bonuses), roster_data
        )
        
        return detailed_df, grouped_df, ido_bonuses, night_stop_bonus, extra_diaria_days, salary_calc
    
    def _process_roster_data(self, data: Dict[str, Any], profile: PilotProfile, 
                           sector_value: float, sector_threshold: float, 
                           ido_value: float) -> Tuple[pd.DataFrame, pd.DataFrame, List[BonusInfo], float, Set[str]]:
        """Process roster data and calculate flight details"""
        schedule_list = []
        
        # Get target month for filtering (payment schedule: roster month - 1)
        payment_month = getattr(profile, 'payment_month', None)
        roster_month = None
        
        if payment_month:
            # Calculate roster month (payment month - 1)
            roster_month = payment_month - 1 if payment_month > 1 else 12
            self.logger.info(f"Filtering for payment month {payment_month} (roster month {roster_month})")
        else:
            self.logger.info("No month filtering - processing all dates")
        
        total_days = 0
        processed_days = 0
        
        for day in data.get('dailySchedule', []):
            total_days += 1
            
            # Filter by month if specified
            if roster_month:
                try:
                    day_date = datetime.strptime(day.get('date', ''), '%Y-%m-%d')
                    if day_date.month != roster_month:
                        self.logger.debug(f"Skipping day {day.get('date')} (month {day_date.month}) - not in target month {roster_month}")
                        continue
                    else:
                        self.logger.debug(f"Processing day {day.get('date')} - matches target month {roster_month}")
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid date format: {day.get('date')}")
                    continue
            
            processed_days += 1
            
            duty = day.get('duty', {})
            activity_type = duty.get('type', 'N/A')
            
            if activity_type == 'Flight':
                for leg in duty.get('legs', []):
                    try:
                        origin = leg.get('origin')
                        destination = leg.get('destination')
                        
                        # Skip legs involving training facilities (not real airports)
                        training_facilities = {'XWT', 'XDH'}
                        if origin in training_facilities or destination in training_facilities:
                            continue
                            
                        distance = self.distance_calculator.calculate_distance(origin, destination)
                        sectors = self._assign_sector_value(distance)
                        is_positioning = leg.get('isPositioning', False)
                        
                        # Check if this is a TAXI leg (unpaid positioning)
                        is_taxi = leg.get('flightNumber', '').startswith('TAXI')
                        
                        schedule_list.append({
                            'Data': day.get('date'),
                            'Attività': 'TAXI (unpaid)' if is_taxi else ('Positioning' if is_positioning else 'Flight'),
                            'Volo': leg.get('flightNumber', 'N/A'),
                            'Partenza': leg.get('origin'),
                            'Arrivo': leg.get('destination'),
                            'Distanza': distance,
                            'Settori': 0 if is_taxi else sectors,  # TAXI legs earn 0 sectors
                            'IsPositioning': is_positioning,
                            'IsTAXI': is_taxi
                        })
                    except MissingAirportError:
                        # Re-raise to be handled by GUI
                        raise
                
                # Process additional training duties on flight days
                for training_duty in duty.get('training_duties', []):
                    schedule_list.append({
                        'Data': day.get('date'),
                        'Attività': f"Training ({training_duty['description']})",
                        'Volo': training_duty['type'],
                        'Partenza': '---',
                        'Arrivo': '---',
                        'Distanza': 0,
                        'Settori': training_duty['sectors'],
                        'IsPositioning': False,
                        'IsTAXI': False,
                        'IsAirportDuty': False,
                        'IsTraining': True
                    })
            else:
                # Handle airport duty sector calculation
                sectors = 0
                if activity_type == "Airport Duty":
                    sectors = self._calculate_airport_duty_sectors(duty)
                elif activity_type == "Training":
                    if "SIM" in duty.get('description', '') or "Simulator" in duty.get('description', ''):
                        sectors = self._calculate_sim_sectors(duty, day.get('date', ''))
                    elif "Ground School" in duty.get('description', '') or "Pre Line training ground Instructor" in duty.get('description', ''):
                        sectors = 4.0  # Training FO duties: 4 nominal sectors for 8 hours
                    else:
                        sectors = 0
                elif activity_type == "TAXI":
                    sectors = 0  # TAXI duties are unpaid
                
                schedule_list.append({
                    'Data': day.get('date'),
                    'Attività': f"{activity_type} ({duty.get('description', '')})",
                    'Volo': '---',
                    'Partenza': '---',
                    'Arrivo': '---',
                    'Distanza': 0,
                    'Settori': sectors,
                    'IsPositioning': False,
                    'IsAirportDuty': activity_type == "Airport Duty",
                    'IsTraining': activity_type == "Training"
                })
        
        self.logger.info(f"Processed {processed_days}/{total_days} days, generated {len(schedule_list)} schedule entries")
        
        if not schedule_list:
            if roster_month:
                self.logger.warning(f"No schedule entries found for roster month {roster_month}. Check if the roster file contains data for the correct month.")
            else:
                self.logger.warning("No schedule entries found in roster file. Check roster file format.")
            return pd.DataFrame(), pd.DataFrame(), [], 0, set()
        
        # Create detailed DataFrame
        detailed_df = pd.DataFrame(schedule_list)
        detailed_df['Data'] = pd.to_datetime(detailed_df['Data'])
        
        # Calculate operational sectors and earnings
        detailed_df = self._calculate_earnings(detailed_df, sector_value, sector_threshold)
        
        # Calculate bonuses
        ido_bonuses = self._calculate_ido_bonuses(data, ido_value)
        night_stop_bonus = self._calculate_night_stop_bonus(data, profile.home_base, sector_value)
        extra_diaria_days = self._find_extra_diaria_days(data)
        
        # Create grouped DataFrame
        grouped_df = self._create_grouped_dataframe(detailed_df)
        
        return detailed_df, grouped_df, ido_bonuses, night_stop_bonus, extra_diaria_days
    
    def _assign_sector_value(self, distance: float) -> float:
        """Assign sector value based on flight distance"""
        if distance <= 0:
            return 0.0
        
        # Handle same-airport flights (distance < 0.1 NM due to floating point precision)
        if distance < 0.1:
            return 0.0
        
        for min_dist, max_dist, value in SalaryConfig.SECTOR_VALUES:
            if min_dist < distance <= max_dist:
                return value
        
        return 0.0
    
    def _calculate_earnings(self, df: pd.DataFrame, sector_value: float, threshold: float) -> pd.DataFrame:
        """Calculate earnings for each flight"""
        # Add missing columns with defaults
        if 'IsAirportDuty' not in df.columns:
            df['IsAirportDuty'] = False
        if 'IsTraining' not in df.columns:
            df['IsTraining'] = False
        if 'IsTAXI' not in df.columns:
            df['IsTAXI'] = False
            
        df['Settori Operativi'] = df.apply(
            lambda row: row['Settori'] if (row['Attività'] == 'Flight' and not row['IsPositioning']) else 0,
            axis=1
        )
        
        df['Settori Cumulativi Operativi'] = df['Settori Operativi'].cumsum()
        df['Guadagno (€)'] = 0.0
        
        operational_sectors_prev = 0.0
        
        for i, row in df.iterrows():
            earnings = 0
            sectors_this_row = row['Settori']
            is_operational = (row['Attività'] == 'Flight' and not row['IsPositioning'])
            is_positioning = row['IsPositioning']
            is_airport_duty = row.get('IsAirportDuty', False)
            is_training = row.get('IsTraining', False)
            is_taxi = row.get('IsTAXI', False)
            
            if sectors_this_row > 0:
                if is_operational:
                    cumulative_operational = row['Settori Cumulativi Operativi']
                    
                    if operational_sectors_prev < threshold and cumulative_operational > threshold:
                        # Crossing threshold
                        below_threshold = threshold - operational_sectors_prev
                        above_threshold = cumulative_operational - threshold
                        earnings = (below_threshold * sector_value + 
                                  above_threshold * sector_value * SalaryConfig.OVERTIME_SECTOR_MULTIPLIER)
                    elif operational_sectors_prev >= threshold:
                        # All overtime
                        earnings = sectors_this_row * sector_value * SalaryConfig.OVERTIME_SECTOR_MULTIPLIER
                    else:
                        # All regular
                        earnings = sectors_this_row * sector_value
                    
                    operational_sectors_prev = cumulative_operational
                    
                elif is_positioning:
                    # Positioning sectors don't count toward operational total
                    earnings = sectors_this_row * sector_value
                elif is_airport_duty:
                    # Airport duty sectors don't count toward operational total
                    earnings = sectors_this_row * sector_value
                elif is_training:
                    # Training sectors don't count toward operational total
                    earnings = sectors_this_row * sector_value
                elif is_taxi:
                    # TAXI legs are unpaid - explicitly set to 0
                    earnings = 0
            
            df.at[i, 'Guadagno (€)'] = earnings
        
        return df
    
    def _calculate_ido_bonuses(self, data: Dict[str, Any], ido_value: float) -> List[BonusInfo]:
        """Calculate IDO (rest period violation) bonuses"""
        bonuses = []
        schedule = data['dailySchedule']
        
        for i in range(len(schedule) - 1):
            day1, day2 = schedule[i], schedule[i + 1]
            
            if (day1['duty'].get('type') == 'Flight' and 
                day1['duty'].get('legs')):
                
                last_leg = day1['duty']['legs'][-1]
                landing_time = last_leg.get('landingTime')
                
                if landing_time:
                    try:
                        # Parse landing time - handle complex formats like "01:55?�/00:36"
                        main_time = landing_time.split('/')[0]  # Take part before /
                        time_str = re.sub(r'[^\d:]', '', main_time)
                        time_parts = time_str.split(':')
                        if len(time_parts) < 2:
                            continue
                        
                        try:
                            hours, minutes = int(time_parts[0]), int(time_parts[1])
                            # Validate time values
                            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                                continue
                        except ValueError:
                            continue
                        
                        day1_date = datetime.strptime(day1['date'], '%Y-%m-%d')
                        landing_datetime = day1_date.replace(hour=hours, minute=minutes)
                        
                        # Handle next day landings
                        if hours < 5:
                            landing_datetime += timedelta(days=1)
                        
                        day2_start = datetime.strptime(day2['date'], '%Y-%m-%d')
                        
                        if landing_datetime > day2_start - timedelta(minutes=29):
                            minutes_into_day_off = (landing_datetime - day2_start).total_seconds() / 60
                            day2_type = day2['duty'].get('type')
                            
                            if day2_type in ["Day Off", "Leave"]:
                                if minutes_into_day_off <= 90:
                                    bonuses.append(BonusInfo(day1['date'], "(++€)", ido_value / 2))
                                else:
                                    bonuses.append(BonusInfo(day1['date'], "(+++€)", ido_value))
                            elif day2_type == "Standby":
                                bonuses.append(BonusInfo(day1['date'], "(+€)", 0))
                    
                    except (ValueError, IndexError):
                        continue
        
        return bonuses
    
    def _calculate_night_stop_bonus(self, data: Dict[str, Any], home_base: str, sector_value: float) -> float:
        """Calculate night stop bonuses"""
        bonus = 0
        schedule = data['dailySchedule']
        
        for i in range(len(schedule) - 1):
            day1, day2 = schedule[i], schedule[i + 1]
            
            if (day1['duty'].get('type') == 'Flight' and 
                day2['duty'].get('type') == 'Flight'):
                
                legs1 = day1['duty'].get('legs', [])
                legs2 = day2['duty'].get('legs', [])
                
                if (legs1 and legs2 and 
                    legs1[-1]['destination'] != home_base and
                    legs1[-1]['destination'] == legs2[0]['origin']):
                    
                    bonus += SalaryConfig.NIGHT_STOP_BONUS_MULTIPLIER * sector_value
        
        return bonus
    
    def _find_extra_diaria_days(self, data: Dict[str, Any]) -> Set[str]:
        """Find days eligible for extra diaria"""
        extra_days = set()
        schedule = data['dailySchedule']
        
        for i in range(len(schedule) - 1):
            day1, day2 = schedule[i], schedule[i + 1]
            
            if (day1['duty'].get('type') == 'Flight' and 
                day1['duty'].get('legs')):
                
                last_leg = day1['duty']['legs'][-1]
                landing_time = last_leg.get('landingTime')
                
                if landing_time:
                    try:
                        # Check for the midnight crossing symbol before cleaning
                        # The symbol can be various special characters indicating next day
                        has_midnight_symbol = (chr(185) in landing_time or  # Character code 185
                                             '\ufffd' in landing_time or    # Unicode replacement
                                             '�' in landing_time or         # Direct symbol
                                             '¹' in landing_time)           # Superscript 1
                        
                        # Handle complex time formats like "01:55?�/00:36"
                        # First extract the main time (before any separator like /)
                        main_time = landing_time.split('/')[0]  # Take part before /
                        main_time = re.sub(r'[^\d:]', '', main_time)  # Clean non-digits/colons
                        
                        if ':' not in main_time:
                            continue
                            
                        time_parts = main_time.split(':')
                        if len(time_parts) < 2:
                            continue
                        
                        try:
                            hours, minutes = int(time_parts[0]), int(time_parts[1])
                            # Validate time values
                            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                                continue
                        except ValueError:
                            continue
                        
                        day1_date = datetime.strptime(day1['date'], '%Y-%m-%d')
                        landing_datetime = day1_date.replace(hour=hours, minute=minutes)
                        
                        # Handle midnight crossings (flights landing after midnight)
                        is_midnight_crossing = False
                        
                        # First check: explicit midnight symbol in roster
                        if has_midnight_symbol:
                            landing_datetime += timedelta(days=1)
                            is_midnight_crossing = True
                            self.logger.debug(f"Midnight crossing detected by symbol for {day1['date']}: {landing_time}")
                        
                        # Second check: time-based logic for cases without symbol
                        elif hours < 12:  # Expanded from 5 to 12 for better midnight detection
                            # Check if this is actually a next day landing
                            takeoff_time = last_leg.get('takeOffTime')
                            if takeoff_time:
                                takeoff_str = re.sub(r'[^\d:]', '', takeoff_time)
                                if ':' in takeoff_str:
                                    takeoff_hours = int(takeoff_str.split(':')[0])
                                    # If takeoff is in evening and landing in early morning, it's next day
                                    if takeoff_hours >= 18 and hours <= 6:
                                        landing_datetime += timedelta(days=1)
                                        is_midnight_crossing = True
                            else:
                                # Fallback: assume early morning times are next day
                                if hours <= 6:
                                    landing_datetime += timedelta(days=1)
                                    is_midnight_crossing = True
                        
                        day2_start = datetime.strptime(day2['date'], '%Y-%m-%d')
                        day2_type = day2['duty'].get('type', '')
                        
                        # Check for extra diaria eligibility
                        # Landing within 30 minutes of next day AND next day is standby
                        time_diff_minutes = (landing_datetime - day2_start).total_seconds() / 60
                        
                        self.logger.debug(f"Checking extra diaria for {day1['date']} -> {day2['date']}: "
                                        f"landing_time={landing_time}, parsed_datetime={landing_datetime}, "
                                        f"has_symbol={has_midnight_symbol}, next_day_type={day2_type}, "
                                        f"time_diff_minutes={time_diff_minutes:.1f}")
                        
                        if (-30 <= time_diff_minutes <= 480 and  # Landing 30min before to 8h after day start
                            day2_type == "Standby"):
                            extra_days.add(day2['date'])
                            self.logger.info(f"Extra diaria added for {day2['date']} - landing at {landing_datetime}, next day start {day2_start}")
                        elif is_midnight_crossing and day2_type == "Standby":
                            # Special case: if we detected midnight crossing but timing is off, still consider it
                            self.logger.debug(f"Midnight crossing detected but time criteria not met for {day2['date']}: {time_diff_minutes:.1f} minutes")
                    
                    except (ValueError, IndexError, TypeError) as e:
                        self.logger.warning(f"Error processing extra diaria for {day1.get('date')}: {e}")
                        continue
        
        return extra_days
    
    def _count_midnight_standby_days(self, data: Dict[str, Any], grouped_df: pd.DataFrame) -> tuple[int, Set[str]]:
        """Count standby/airport duty days that follow flights landing after midnight"""
        midnight_days = 0
        midnight_standby_dates = set()
        schedule = data['dailySchedule']
        
        for i in range(len(schedule) - 1):
            day1, day2 = schedule[i], schedule[i + 1]
            
            # Debug logging
            self.logger.debug(f"Checking {day1['date']} -> {day2['date']}: day1_type={day1['duty'].get('type')}, day2_type={day2['duty'].get('type')}")
            
            # Check if day1 has flights and day2 is standby/airport duty
            if (day1['duty'].get('type') == 'Flight' and 
                day1['duty'].get('legs') and
                day2['duty'].get('type') in ['Standby', 'Airport Duty']):
                
                last_leg = day1['duty']['legs'][-1]
                landing_time = last_leg.get('landingTime')
                
                self.logger.debug(f"Found flight->standby: {day1['date']} -> {day2['date']}, landing_time: {landing_time}")
                
                if landing_time:
                    try:
                        # Check for midnight crossing symbol or early morning landing
                        has_midnight_symbol = (chr(185) in landing_time or  
                                             '\ufffd' in landing_time or    
                                             '�' in landing_time or         
                                             '¹' in landing_time or
                                             '?' in landing_time)  # Also check for ? symbol
                        
                        # Extract main time
                        main_time = landing_time.split('/')[0]
                        main_time = re.sub(r'[^\d:]', '', main_time)
                        
                        self.logger.debug(f"Processed landing time: original='{landing_time}', main_time='{main_time}', has_symbol={has_midnight_symbol}")
                        
                        if ':' not in main_time:
                            continue
                            
                        time_parts = main_time.split(':')
                        if len(time_parts) < 2:
                            continue
                        
                        hours, minutes = int(time_parts[0]), int(time_parts[1])
                        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                            continue
                        
                        # Check if this is a midnight crossing (landing after midnight)
                        is_midnight_crossing = False
                        
                        if has_midnight_symbol:
                            is_midnight_crossing = True
                            self.logger.info(f"Midnight crossing detected by symbol for standby day {day2['date']}")
                        elif hours <= 6:  # Early morning landing likely means midnight crossing
                            takeoff_time = last_leg.get('takeOffTime')
                            if takeoff_time:
                                takeoff_str = re.sub(r'[^\d:]', '', takeoff_time)
                                if ':' in takeoff_str:
                                    takeoff_hours = int(takeoff_str.split(':')[0])
                                    if takeoff_hours >= 18:  # Evening takeoff, early morning landing
                                        is_midnight_crossing = True
                                        self.logger.info(f"Midnight crossing detected by time logic for standby day {day2['date']}")
                        
                        if is_midnight_crossing:
                            midnight_days += 1
                            midnight_standby_dates.add(day2['date'])
                            self.logger.info(f"Adding diaria for standby/airport duty day {day2['date']} due to midnight landing from {day1['date']}")
                    
                    except (ValueError, IndexError, TypeError) as e:
                        self.logger.warning(f"Error processing midnight standby for {day2.get('date')}: {e}")
                        continue
        
        self.logger.info(f"Total midnight standby days found: {midnight_days}")
        return midnight_days, midnight_standby_dates
    
    
    def _calculate_airport_duty_sectors(self, duty: Dict[str, Any]) -> float:
        """Calculate sectors for airport duty based on hours and if called"""
        # Default assumption: 4 hours if not specified
        duty_hours = duty.get('airport_duty_hours', 4)
        was_called = duty.get('was_called', False)
        
        # Base sectors: 1 for up to 4 hours, 2 for 4+ hours
        if duty_hours <= 4:
            base_sectors = 1
        else:
            base_sectors = 2
        
        # Add 1 sector if pilot was called to fly
        if was_called:
            base_sectors += 1
        
        return float(base_sectors)
    
    def _calculate_sim_sectors(self, duty: Dict[str, Any], date: str) -> float:
        """Calculate SIM sectors based on instructor/trainee role"""
        description = duty.get('description', '').lower()
        
        # Look for instructor keywords
        instructor_keywords = ['instructor', 'luca fusari', 'instr', 'teaching']
        trainee_keywords = ['trainee', 'support', 'student', 'training']
        
        # Check for instructor role
        for keyword in instructor_keywords:
            if keyword in description:
                return 4.0  # Instructor gets 4 sectors
        
        # Check for trainee role
        for keyword in trainee_keywords:
            if keyword in description:
                return 0.0  # Trainee gets only diaria (0 sectors)
        
        # Default: assume instructor if role unclear
        return 4.0
    
    def _create_grouped_dataframe(self, detailed_df: pd.DataFrame) -> pd.DataFrame:
        """Create grouped summary DataFrame"""
        # Create itinerary column
        itinerari = detailed_df.groupby(detailed_df['Data'].dt.date).apply(
            self._create_itinerary
        ).rename('Itinerario')
        
        # Aggregate functions
        agg_functions = {
            'Attività': lambda x: ' / '.join(x.unique()),
            'Volo': 'count',
            'Settori': 'sum',
            'Guadagno (€)': 'sum'
        }
        
        grouped_df = (detailed_df.groupby(detailed_df['Data'].dt.date)
                     .agg(agg_functions)
                     .reset_index()
                     .merge(itinerari, on='Data'))
        
        return grouped_df
    
    def _create_itinerary(self, group: pd.DataFrame) -> str:
        """Create itinerary string for a day"""
        flight_legs = group[group['Settori'] > 0]
        
        if flight_legs.empty:
            return '---'
        
        operational = flight_legs[~flight_legs['IsPositioning']]
        positioning = flight_legs[flight_legs['IsPositioning']]
        itinerary_parts = []
        
        if not operational.empty:
            departures = operational['Partenza'].tolist()
            arrivals = operational['Arrivo'].tolist()
            itinerary_parts.append(' - '.join([departures[0]] + arrivals))
        
        if not positioning.empty:
            pos_routes = [
                f"POS({row['Partenza']}-{row['Arrivo']})" 
                for _, row in positioning.iterrows()
            ]
            if itinerary_parts:
                itinerary_parts.append(' + ' + ' + '.join(pos_routes))
            else:
                itinerary_parts.append(' + '.join(pos_routes))
        
        return ''.join(itinerary_parts)
    
    def _calculate_salary_components(self, detailed_df: pd.DataFrame, grouped_df: pd.DataFrame,
                                   profile: PilotProfile, base_salary: float, allowance: float,
                                   sector_value: float, night_stop_bonus: float, 
                                   total_ido_bonus: float, data: Dict[str, Any]) -> SalaryCalculation:
        """Calculate all salary components"""
        
        # Note: Standby days are handled individually in the daily processing
        # They contribute €0 to earnings but may still get diaria if landing after midnight
        
        # Calculate extra position bonus
        extra_percentage = SalaryConfig.EXTRA_POSITIONS[profile.extra_position]
        extra_bonus = (base_salary + allowance) * (extra_percentage / 100)
        final_base = base_salary + (base_salary * extra_percentage / 100)
        final_allowance = allowance + (allowance * extra_percentage / 100)
        
        # Calculate earnings from sectors
        operational_earnings = detailed_df[
            ~detailed_df['IsPositioning'] & (detailed_df['Attività'] == 'Flight')
        ]['Guadagno (€)'].sum()
        
        positioning_earnings = detailed_df[detailed_df['IsPositioning']]['Guadagno (€)'].sum()
        total_sector_earnings = operational_earnings + positioning_earnings
        
        # FRV contract bonus
        frv_bonus = 0
        if profile.contract_type == "FRV":
            frv_bonus = (base_salary + allowance) * SalaryConfig.FRV_CONTRACT_INCREASE_RATE
        
        # SNC compensation
        snc_compensation = profile.snc_units * SalaryConfig.SNC_SECTOR_MULTIPLIER
        
        # Vacation compensation
        vacation_days = grouped_df[grouped_df['Attività'].str.contains("Leave", na=False)]['Data'].nunique()
        vacation_compensation = vacation_days * SalaryConfig.VACATION_PAY_MULTIPLIER * sector_value
        
        # Calculate gross total (matches original exactly)
        gross_total = (final_base + final_allowance + total_sector_earnings + 
                      frv_bonus + vacation_compensation + snc_compensation + 
                      night_stop_bonus + total_ido_bonus)
        
        # Calculate contribution base (matches original exactly)
        contribution_base = (final_base + (final_allowance / 2) + (total_sector_earnings / 2) + 
                           (frv_bonus / 2) + vacation_compensation + night_stop_bonus + 
                           total_ido_bonus + snc_compensation)
        
        # Calculate contributions and taxes
        total_contribution_rate = SalaryConfig.get_total_contribution_rate()
        social_contributions = contribution_base * total_contribution_rate
        taxable_income = contribution_base - social_contributions
        estimated_tax = calculate_tax(taxable_income, SalaryConfig.TAX_BRACKETS)
        
        # Calculate working days for diaria
        # Include Flight, Positioning, Training, and Rest Days (REST earns diaria)
        # Also include Standby/Airport Duty days that follow flights landing after midnight
        base_working_days = grouped_df[
            grouped_df['Attività'].str.contains("Flight|Positioning|Training|Rest Day", na=False)
        ]['Data'].nunique()
        
        # Add standby/airport duty days that have midnight landing from previous day
        midnight_standby_days, midnight_standby_dates = self._count_midnight_standby_days(data, grouped_df)
        working_days = base_working_days + midnight_standby_days
        
        # Get diaria value
        _, _, _, diaria, _ = SalaryConfig.POSITIONS[profile.position]
        diaria_compensation = working_days * diaria  # This will be adjusted for extra days in GUI
        
        # Calculate net salary (matches original formula exactly)
        net_estimated = (taxable_income - estimated_tax + (final_allowance / 2) + 
                        (total_sector_earnings / 2) + (frv_bonus / 2))
        
        return SalaryCalculation(
            gross_total=gross_total,
            net_estimated=net_estimated,
            operational_sectors_earnings=operational_earnings,
            positioning_earnings=positioning_earnings,
            frv_bonus=frv_bonus,
            snc_compensation=snc_compensation,
            vacation_compensation=vacation_compensation,
            vacation_days=vacation_days,
            taxable_income=taxable_income,
            contribution_base=contribution_base,
            estimated_tax=estimated_tax,
            social_contributions=social_contributions,
            working_days=working_days,
            base_working_days=base_working_days,
            midnight_standby_days=midnight_standby_days,
            midnight_standby_dates=midnight_standby_dates
        )