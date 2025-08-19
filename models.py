"""
Data models for the Pilot Salary Calculator
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class FlightLeg:
    """Represents a single flight leg"""
    flight_number: str
    aircraft: Optional[str]
    origin: str
    destination: str
    is_positioning: bool = False
    has_actual_times: bool = False
    takeoff_time: Optional[str] = None
    landing_time: Optional[str] = None


@dataclass
class DutyDay:
    """Represents a single duty day"""
    date: str
    day_of_week: str
    duty_type: str
    description: Optional[str] = None
    initial_duty: Optional[str] = None
    legs: List[FlightLeg] = None
    
    def __post_init__(self):
        if self.legs is None:
            self.legs = []


@dataclass
class PilotProfile:
    """Pilot profile configuration"""
    position: str
    extra_position: str
    contract_type: str
    home_base: str
    snc_units: int
    debug_mode: bool = False


@dataclass
class SalaryCalculation:
    """Complete salary calculation result"""
    gross_total: float
    net_estimated: float
    operational_sectors_earnings: float
    positioning_earnings: float
    frv_bonus: float
    snc_compensation: float
    vacation_compensation: float
    vacation_days: int
    taxable_income: float
    contribution_base: float
    estimated_tax: float
    social_contributions: float
    working_days: int
    base_working_days: int
    midnight_standby_days: int
    midnight_standby_dates: set


@dataclass
class BonusInfo:
    """Bonus information (IDO, night stops)"""
    date: str
    symbol: str
    amount: float


class MissingAirportError(Exception):
    """Exception raised when airport coordinates are missing"""
    def __init__(self, iata_code: str):
        self.iata_code = iata_code
        super().__init__(f"Missing coordinates for airport: {iata_code}")