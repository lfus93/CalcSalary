"""
Utility functions for the Pilot Salary Calculator
"""
import os
import sys
import logging
from typing import List, Tuple


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)


def calculate_tax(total: float, brackets: List[Tuple[float, float]]) -> float:
    """
    Calculate progressive tax based on brackets
    
    Args:
        total: Total taxable amount
        brackets: List of (threshold, rate) tuples
    
    Returns:
        Total tax amount
    """
    if total <= 0:
        return 0
    
    remaining_taxable = total
    total_tax = 0
    previous_threshold = 0
    
    for threshold, rate in brackets:
        if remaining_taxable > 0:
            bracket_amount = min(remaining_taxable, threshold - previous_threshold)
            total_tax += bracket_amount * rate
            remaining_taxable -= bracket_amount
            previous_threshold = threshold
        else:
            break
    
    return total_tax


def setup_logging(debug: bool = False) -> logging.Logger:
    """Setup logging configuration"""
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('salary_calculator.log')
        ]
    )
    
    return logging.getLogger(__name__)


def validate_numeric_input(value: str, field_name: str) -> float:
    """
    Validate and convert numeric input
    
    Args:
        value: String value to validate
        field_name: Name of the field for error messages
    
    Returns:
        Converted float value
    
    Raises:
        ValueError: If value is not a valid number
    """
    try:
        # Handle comma as decimal separator
        cleaned_value = value.replace(',', '.')
        return float(cleaned_value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid numeric value for {field_name}: {value}")


def validate_integer_input(value: str, field_name: str) -> int:
    """
    Validate and convert integer input
    
    Args:
        value: String value to validate
        field_name: Name of the field for error messages
    
    Returns:
        Converted integer value
    
    Raises:
        ValueError: If value is not a valid integer
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid integer value for {field_name}: {value}")