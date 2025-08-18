"""
Configuration management system for easy updates and customization
"""
import json
import os
import logging
from typing import Dict, Any, Optional, List
from utils import resource_path


class ConfigManager:
    """Manages application configuration with file-based persistence"""
    
    def __init__(self, config_file: str = "app_config.json"):
        self.config_file = resource_path(config_file)
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file"""
        # Default configuration
        self.config = {
            "app": {
                "version": "2.0",
                "title": "Advanced Pilot Salary Calculator",
                "geometry": "1300x900",
                "min_size": [1200, 800],
                "debug_mode": False
            },
            "calculation": {
                "cache_enabled": True,
                "cache_size": 128,
                "performance_logging": True,
                "decimal_places": 2
            },
            "export": {
                "default_formats": ["csv", "excel", "text"],
                "excel_available": True,
                "include_timestamps": True,
                "auto_open_after_export": False
            },
            "ui": {
                "theme": "default",
                "font_family": "Helvetica",
                "font_size": 10,
                "show_tooltips": True,
                "auto_save_settings": True
            },
            "logging": {
                "level": "INFO",
                "file_enabled": True,
                "file_name": "salary_calculator.log",
                "max_file_size": 10485760,  # 10MB
                "backup_count": 3
            },
            "data": {
                "airport_csv": "cord_airport.csv",
                "backup_enabled": True,
                "validation_strict": True
            }
        }
        
        # Try to load from file
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    self._merge_config(file_config)
                self.logger.info(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                self.logger.warning(f"Could not load config file: {e}, using defaults")
    
    def _merge_config(self, file_config: Dict[str, Any]):
        """Merge file configuration with defaults"""
        for section, values in file_config.items():
            if section in self.config:
                if isinstance(values, dict):
                    self.config[section].update(values)
                else:
                    self.config[section] = values
            else:
                self.config[section] = values
    
    def save_config(self) -> bool:
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            self.logger.error(f"Could not save config file: {e}")
            return False
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(section, {}).get(key, default)
    
    def set(self, section: str, key: str, value: Any) -> None:
        """Set configuration value"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire configuration section"""
        return self.config.get(section, {}).copy()
    
    def update_section(self, section: str, values: Dict[str, Any]) -> None:
        """Update entire configuration section"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section].update(values)
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults"""
        self.__init__(os.path.basename(self.config_file))
        self.save_config()
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return list of issues"""
        issues = []
        
        # Validate app section
        app_config = self.get_section("app")
        if not isinstance(app_config.get("min_size"), list) or len(app_config.get("min_size", [])) != 2:
            issues.append("Invalid min_size format in app section")
        
        # Validate calculation section
        calc_config = self.get_section("calculation")
        cache_size = calc_config.get("cache_size", 0)
        if not isinstance(cache_size, int) or cache_size <= 0:
            issues.append("Invalid cache_size in calculation section")
        
        decimal_places = calc_config.get("decimal_places", 0)
        if not isinstance(decimal_places, int) or decimal_places < 0 or decimal_places > 10:
            issues.append("Invalid decimal_places in calculation section")
        
        # Validate logging section
        log_config = self.get_section("logging")
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_config.get("level") not in valid_levels:
            issues.append(f"Invalid logging level, must be one of: {valid_levels}")
        
        max_size = log_config.get("max_file_size", 0)
        if not isinstance(max_size, int) or max_size <= 0:
            issues.append("Invalid max_file_size in logging section")
        
        return issues
    
    def create_sample_config(self) -> None:
        """Create a sample configuration file for user customization"""
        sample_config = {
            "app": {
                "title": "My Custom Pilot Salary Calculator",
                "geometry": "1400x1000",
                "debug_mode": False
            },
            "calculation": {
                "cache_enabled": True,
                "decimal_places": 2
            },
            "ui": {
                "font_size": 11,
                "show_tooltips": True
            },
            "logging": {
                "level": "INFO",
                "file_enabled": True
            }
        }
        
        sample_file = resource_path("sample_config.json")
        try:
            with open(sample_file, 'w', encoding='utf-8') as f:
                json.dump(sample_config, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Sample configuration created at {sample_file}")
        except Exception as e:
            self.logger.error(f"Could not create sample config: {e}")


# Global configuration instance
_config_manager = None


def get_config_manager() -> ConfigManager:
    """Get or create the global configuration manager"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config(section: str, key: str, default: Any = None) -> Any:
    """Convenience function to get configuration value"""
    return get_config_manager().get(section, key, default)


def set_config(section: str, key: str, value: Any) -> None:
    """Convenience function to set configuration value"""
    get_config_manager().set(section, key, value)


def save_config() -> bool:
    """Convenience function to save configuration"""
    return get_config_manager().save_config()