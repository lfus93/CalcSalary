#!/usr/bin/env python3
"""
Test script to verify MXP payment blocking logic when standby codes are present
"""

import sys
import os
import logging

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import AirportService, SalaryCalculatorService, RosterParser
from models import PilotProfile

def test_mxp_blocking():
    """Test that MXP payments are blocked when standby codes are present"""
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    # Initialize services
    airport_service = AirportService()
    calculator_service = SalaryCalculatorService(airport_service)
    roster_parser = RosterParser()
    
    # Read the August roster file
    roster_file_path = r"C:\Users\fusar\OneDrive\Documents\EasyJet\schedule txt\Aug.txt"
    
    try:
        with open(roster_file_path, 'r', encoding='utf-8') as f:
            roster_content = f.read()
    except UnicodeDecodeError:
        # Try with different encoding if UTF-8 fails
        with open(roster_file_path, 'r', encoding='latin1') as f:
            roster_content = f.read()
    
    logger.info("Successfully loaded roster file")
    
    # Parse the roster
    roster_data = roster_parser.parse_roster_text(roster_content)
    logger.info(f"Parsed roster with {len(roster_data['dailySchedule'])} days")
    
    # Create pilot profile with MXP home base
    profile = PilotProfile(
        position="FO",
        extra_position="Nessuna", 
        contract_type="Standard",
        home_base="MXP",
        snc_units=0,
        debug_mode=True
    )
    
    # Calculate salary - this should be blocked due to standby codes
    try:
        detailed_df, grouped_df, ido_bonuses, night_stop_bonus, extra_diaria_days, salary_calc = calculator_service.calculate_salary(
            roster_data, profile
        )
        
        # Check if payment was blocked (all values should be zero)
        if (salary_calc.gross_total == 0.0 and 
            salary_calc.net_estimated == 0.0 and 
            salary_calc.operational_sectors_earnings == 0.0):
            
            logger.info("✅ SUCCESS: MXP payment correctly blocked due to standby codes!")
            logger.info(f"Gross Total: {salary_calc.gross_total}")
            logger.info(f"Net Estimated: {salary_calc.net_estimated}")
            logger.info(f"Operational Earnings: {salary_calc.operational_sectors_earnings}")
            return True
        else:
            logger.error("❌ FAILURE: MXP payment was not blocked!")
            logger.error(f"Gross Total: {salary_calc.gross_total}")
            logger.error(f"Net Estimated: {salary_calc.net_estimated}")
            logger.error(f"Operational Earnings: {salary_calc.operational_sectors_earnings}")
            return False
            
    except Exception as e:
        logger.error(f"Error during calculation: {e}")
        return False

def test_non_mxp_base():
    """Test that non-MXP bases are not affected by the blocking logic"""
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Initialize services
    airport_service = AirportService()
    calculator_service = SalaryCalculatorService(airport_service)
    roster_parser = RosterParser()
    
    # Read the August roster file
    roster_file_path = r"C:\Users\fusar\OneDrive\Documents\EasyJet\schedule txt\Aug.txt"
    
    try:
        with open(roster_file_path, 'r', encoding='utf-8') as f:
            roster_content = f.read()
    except UnicodeDecodeError:
        with open(roster_file_path, 'r', encoding='latin1') as f:
            roster_content = f.read()
    
    # Parse the roster
    roster_data = roster_parser.parse_roster_text(roster_content)
    
    # Create pilot profile with FCO home base (not MXP)
    profile = PilotProfile(
        position="FO",
        extra_position="Nessuna", 
        contract_type="Standard",
        home_base="FCO",  # Different base
        snc_units=0,
        debug_mode=True
    )
    
    # Calculate salary - this should NOT be blocked
    try:
        detailed_df, grouped_df, ido_bonuses, night_stop_bonus, extra_diaria_days, salary_calc = calculator_service.calculate_salary(
            roster_data, profile
        )
        
        # Check if payment was NOT blocked (values should be > 0)
        if (salary_calc.gross_total > 0.0 or 
            salary_calc.operational_sectors_earnings > 0.0):
            
            logger.info("✅ SUCCESS: Non-MXP base correctly allows payment!")
            logger.info(f"Gross Total: {salary_calc.gross_total}")
            logger.info(f"Operational Earnings: {salary_calc.operational_sectors_earnings}")
            return True
        else:
            logger.error("❌ FAILURE: Non-MXP base payment was incorrectly blocked!")
            return False
            
    except Exception as e:
        logger.error(f"Error during calculation: {e}")
        return False

if __name__ == "__main__":
    print("Testing MXP payment blocking logic...")
    print("="*50)
    
    # Test 1: MXP base should be blocked
    print("Test 1: MXP home base with standby codes (should block payment)")
    result1 = test_mxp_blocking()
    
    print("\n" + "="*50)
    
    # Test 2: Non-MXP base should not be blocked
    print("Test 2: Non-MXP home base with standby codes (should allow payment)")
    result2 = test_non_mxp_base()
    
    print("\n" + "="*50)
    print("SUMMARY:")
    print(f"MXP blocking test: {'PASSED' if result1 else 'FAILED'}")
    print(f"Non-MXP test: {'PASSED' if result2 else 'FAILED'}")
    
    if result1 and result2:
        print("\nAll tests PASSED! MXP blocking logic works correctly.")
        sys.exit(0)
    else:
        print("\nSome tests FAILED! Please check the implementation.")
        sys.exit(1)