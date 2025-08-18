"""
Configuration module for the Pilot Salary Calculator
Contains all salary configurations, tax brackets, and constants
"""

class SalaryConfig:
    """Configuration class containing all salary-related constants and data"""
    
    # Position configurations: (base_salary, allowance, sector_value, diaria, ido_value)
    POSITIONS = {
        "SO": (1192.15, 2976.21, 20.85, 46.95, 300),
        "FO": (1520.161, 3795.108, 21.48, 46.95, 375),
        "SFO": (1856.64, 4635.13, 21.48, 46.95, 469),
        "NewCPT": (2858.48, 7136.21, 35.83, 53.33, 750),
        "CPT": (3176.09, 7929.12, 35.83, 53.33, 750)
    }
    
    # Extra position bonuses (percentage)
    EXTRA_POSITIONS = {
        "Nessuna": 0, "BSP": 5, "TFO": 5, "TFO + SIM": 9,
        "Line trainer": 12.5, "TRI": 15, "TRE/TRI": 17.5, "ABT": 20
    }
    
    # Contract types and their sector thresholds
    CONTRACTS = {
        "Standard": {'soglia_settori': 35},
        "5-4": {'soglia_settori': 35},
        "FRV": {'soglia_settori': 35},
        "50% (14-14)": {'soglia_settori': 18},
        "Sesonale PPY50": {'soglia_settori': 18},
        "7-21": {'soglia_settori': 27},
        "PPY 75 Summer": {'soglia_settori': 35},
        "PPY 75 Winter": {'soglia_settori': 18},
        "7-7": {'soglia_settori': 27}
    }
    
    # Sector value ranges: (min_distance, max_distance, value)
    SECTOR_VALUES = [
        (0, 400, 0.8),
        (400, 1000, 1.2),
        (1000, 1500, 1.5),
        (1500, float('inf'), 2.5)
    ]
    
    # Italian tax brackets: (threshold, rate)
    TAX_BRACKETS = [
        (2333.33, 0.23),
        (4166.67, 0.35),
        (float('inf'), 0.43)
    ]
    
    # Multipliers and rates
    SNC_SECTOR_MULTIPLIER = 3
    VACATION_PAY_MULTIPLIER = 3.5
    NIGHT_STOP_BONUS_MULTIPLIER = 2
    OVERTIME_SECTOR_MULTIPLIER = 2
    FRV_CONTRACT_INCREASE_RATE = 0.11
    
    # Social security and tax rates
    IVS_FONDO_VOLO = 0.0919
    ADDITIONAL_IVS = 0.0359
    FAP = 0.003
    FIS = 0.00267
    CTR_TO = 0.00167
    
    @classmethod
    def get_total_contribution_rate(cls) -> float:
        """Calculate total contribution rate"""
        return (cls.IVS_FONDO_VOLO + cls.ADDITIONAL_IVS + 
                cls.FAP + cls.FIS + cls.CTR_TO)