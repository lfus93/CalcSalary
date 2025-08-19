"""
Improved Pilot Salary Calculator - Main Application
"""
import os
import sys
import pickle
import logging
from typing import Dict, Any, Optional, List, Set
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import pandas as pd  # Keep for type annotations

# Lazy imports for better startup performance
def _lazy_import_pandas():
    return pd

def _lazy_import_calendar():
    try:
        from tkcalendar import DateEntry
        return DateEntry
    except ImportError:
        # Fallback if tkcalendar is not available
        return None

# Import our modules
from config import SalaryConfig
from models import PilotProfile, BonusInfo, MissingAirportError
from utils import setup_logging, validate_integer_input, resource_path
from config_manager import get_config_manager, get_config

# Lazy import services for faster startup
_services_initialized = False
_airport_service = None
_calculator_service = None
_roster_parser = None
_exporter = None
_df_optimizer = None

def _init_services():
    """Initialize services lazily"""
    global _services_initialized, _airport_service, _calculator_service, _roster_parser, _exporter, _df_optimizer
    if not _services_initialized:
        from services import AirportService, SalaryCalculatorService, RosterParser
        from export import ReportExporter
        from performance import DataFrameOptimizer
        
        _airport_service = AirportService()
        _calculator_service = SalaryCalculatorService(_airport_service)
        _roster_parser = RosterParser()
        _exporter = ReportExporter()
        _df_optimizer = DataFrameOptimizer()
        _services_initialized = True
    
    return _airport_service, _calculator_service, _roster_parser, _exporter, _df_optimizer


class NewAirportDialog(tk.Toplevel):
    """Dialog for adding missing airport coordinates"""
    
    def __init__(self, parent: tk.Tk, iata_code: str):
        super().__init__(parent)
        self.title("Missing Airport")
        self.geometry("350x180")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        self.iata_code = iata_code
        self.result: Optional[tuple[float, float]] = None
        
        self._create_widgets()
        self._center_window()
    
    def _create_widgets(self):
        """Create dialog widgets"""
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text=f"Missing coordinates for airport: {self.iata_code}",
            font=('Helvetica', 11, 'bold')
        )
        title_label.pack(pady=(0, 20))
        
        # Input fields
        fields_frame = ttk.Frame(main_frame)
        fields_frame.pack(fill="x", pady=(0, 20))
        
        ttk.Label(fields_frame, text="Latitude:", width=12).grid(row=0, column=0, sticky="w", pady=5)
        self.lat_entry = ttk.Entry(fields_frame, width=20)
        self.lat_entry.grid(row=0, column=1, padx=(10, 0), pady=5, sticky="ew")
        
        ttk.Label(fields_frame, text="Longitude:", width=12).grid(row=1, column=0, sticky="w", pady=5)
        self.lon_entry = ttk.Entry(fields_frame, width=20)
        self.lon_entry.grid(row=1, column=1, padx=(10, 0), pady=5, sticky="ew")
        
        fields_frame.columnconfigure(1, weight=1)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")
        
        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(side="right", padx=(10, 0))
        ttk.Button(button_frame, text="Save", command=self._on_save).pack(side="right")
        
        # Set focus and bindings
        self.lat_entry.focus_set()
        self.bind('<Return>', lambda e: self._on_save())
        self.bind('<Escape>', lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
    
    def _center_window(self):
        """Center the dialog on parent window"""
        self.update_idletasks()
        parent_x = self.master.winfo_rootx()
        parent_y = self.master.winfo_rooty()
        parent_width = self.master.winfo_width()
        parent_height = self.master.winfo_height()
        
        x = parent_x + (parent_width // 2) - (self.winfo_width() // 2)
        y = parent_y + (parent_height // 2) - (self.winfo_height() // 2)
        
        self.geometry(f"+{x}+{y}")
    
    def _on_save(self):
        """Handle save button click"""
        try:
            lat_str = self.lat_entry.get().strip().replace(',', '.')
            lon_str = self.lon_entry.get().strip().replace(',', '.')
            
            if not lat_str or not lon_str:
                messagebox.showerror("Invalid Input", "Please enter both latitude and longitude.", parent=self)
                return
            
            lat = float(lat_str)
            lon = float(lon_str)
            
            # Basic validation
            if not (-90 <= lat <= 90):
                messagebox.showerror("Invalid Input", "Latitude must be between -90 and 90.", parent=self)
                return
            
            if not (-180 <= lon <= 180):
                messagebox.showerror("Invalid Input", "Longitude must be between -180 and 180.", parent=self)
                return
            
            self.result = (lat, lon)
            self.destroy()
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric values.", parent=self)
    
    def _on_cancel(self):
        """Handle cancel button click"""
        self.result = None
        self.destroy()


class StatisticsViewer(tk.Toplevel):
    """Window for viewing aggregated statistics from multiple reports"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Statistics Viewer")
        self.geometry("800x600")
        self.transient(parent)
        
        self.report_dir = tk.StringVar()
        self._create_widgets()
    
    def _create_widgets(self):
        """Create statistics viewer widgets"""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Controls frame
        controls_frame = ttk.LabelFrame(main_frame, text="Report Selection", padding="10")
        controls_frame.pack(fill="x", pady=(0, 10))
        
        # Directory selection
        dir_frame = ttk.Frame(controls_frame)
        dir_frame.pack(fill="x", pady=5)
        
        ttk.Label(dir_frame, text="Report Directory:").pack(side="left")
        ttk.Entry(dir_frame, textvariable=self.report_dir, state="readonly").pack(side="left", fill="x", expand=True, padx=(10, 5))
        ttk.Button(dir_frame, text="Browse...", command=self._select_directory).pack(side="right")
        
        # Date range
        date_frame = ttk.Frame(controls_frame)
        date_frame.pack(fill="x", pady=5)
        
        ttk.Label(date_frame, text="Start Date:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.start_date_entry = DateEntry(date_frame, date_pattern='dd/mm/yyyy', width=12)
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(date_frame, text="End Date:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.end_date_entry = DateEntry(date_frame, date_pattern='dd/mm/yyyy', width=12)
        self.end_date_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        # Generate button
        ttk.Button(controls_frame, text="Generate Statistics", 
                  command=self._generate_statistics).pack(pady=10)
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Statistics Results", padding="10")
        results_frame.pack(fill="both", expand=True)
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(results_frame)
        text_frame.pack(fill="both", expand=True)
        
        self.stats_text = tk.Text(text_frame, font=("Courier New", 10), 
                                 wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.stats_text.yview)
        self.stats_text.configure(yscrollcommand=scrollbar.set)
        
        self.stats_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def _select_directory(self):
        """Select directory containing salary reports"""
        directory = filedialog.askdirectory(title="Select Directory Containing Salary Reports")
        if directory:
            self.report_dir.set(directory)
    
    def _generate_statistics(self):
        """Generate and display statistics"""
        directory = self.report_dir.get()
        if not directory:
            messagebox.showwarning("Warning", "Please select a report directory first.", parent=self)
            return
        
        try:
            start_date = self.start_date_entry.get_date()
            end_date = self.end_date_entry.get_date()
            
            valid_reports = []
            
            if not os.path.exists(directory):
                messagebox.showerror("Error", "Selected directory does not exist.", parent=self)
                return
            
            # Load reports in date range
            for filename in os.listdir(directory):
                if filename.endswith(".salrep"):
                    filepath = os.path.join(directory, filename)
                    try:
                        with open(filepath, 'rb') as f:
                            report_data = pickle.load(f)
                        
                        # Get report month from first date
                        if 'df_raggruppato' in report_data and not report_data['df_raggruppato'].empty:
                            report_month = pd.to_datetime(report_data['df_raggruppato']['Data'].iloc[0]).date()
                            if start_date <= report_month <= end_date:
                                valid_reports.append(report_data)
                    
                    except Exception as e:
                        logging.warning(f"Could not load report {filename}: {e}")
            
            if not valid_reports:
                self._display_text("No valid reports found in the selected date range.")
                return
            
            self._display_aggregated_stats(valid_reports, start_date, end_date)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error generating statistics: {e}", parent=self)
    
    def _display_aggregated_stats(self, reports: List[Dict[str, Any]], start_date, end_date):
        """Display aggregated statistics"""
        try:
            num_months = len(reports)
            
            # Calculate totals
            total_net = sum(r['salary_data']['net_estimated'] for r in reports if 'salary_data' in r)
            total_gross = sum(r['salary_data']['gross_total'] for r in reports if 'salary_data' in r)
            total_sectors = sum(r['df_dettagliato']['Settori Operativi'].sum() for r in reports if 'df_dettagliato' in r)
            total_positioning = sum(r['df_dettagliato']['IsPositioning'].sum() for r in reports if 'df_dettagliato' in r)
            
            # Generate summary
            summary_lines = [
                f"{'STATISTICS SUMMARY':-^60}",
                f"Period: {start_date} to {end_date}",
                f"Months Analyzed: {num_months}",
                f"{'':-^60}",
                "",
                f"{'Total Net Salary:':<35} {total_net:>20,.2f} €",
                f"{'Average Monthly Net:':<35} {(total_net / num_months if num_months > 0 else 0):>20,.2f} €",
                f"{'Total Gross Salary:':<35} {total_gross:>20,.2f} €",
                f"{'Average Monthly Gross:':<35} {(total_gross / num_months if num_months > 0 else 0):>20,.2f} €",
                "",
                f"{'Total Operational Sectors:':<35} {total_sectors:>20.2f}",
                f"{'Total Positioning Flights:':<35} {total_positioning:>20}",
                "",
                f"{'--- Monthly Breakdown ---':-^60}",
            ]
            
            # Add monthly details
            for i, report in enumerate(reports, 1):
                if 'df_raggruppato' in report and not report['df_raggruppato'].empty:
                    month_date = pd.to_datetime(report['df_raggruppato']['Data'].iloc[0])
                    month_str = month_date.strftime('%B %Y')
                    net_salary = report['salary_data'].get('net_estimated', 0)
                    summary_lines.append(f"Month {i} ({month_str}): {net_salary:,.2f} €")
            
            self._display_text("\n".join(summary_lines))
            
        except Exception as e:
            self._display_text(f"Error processing statistics: {e}")
    
    def _display_text(self, text: str):
        """Display text in the stats widget"""
        self.stats_text.config(state="normal")
        self.stats_text.delete(1.0, "end")
        self.stats_text.insert(1.0, text)
        self.stats_text.config(state="disabled")


class SalaryCalculatorApp(tk.Tk):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize configuration
        self.config_manager = get_config_manager()
        
        # Initialize basic services
        debug_mode = get_config("app", "debug_mode", False)
        self.logger = setup_logging(debug_mode)
        
        # Services will be initialized lazily when needed
        self.services_initialized = False
        
        # Initialize UI with configuration
        app_title = get_config("app", "title", "Advanced Pilot Salary Calculator v2.0")
        app_geometry = get_config("app", "geometry", "1300x900")
        min_size = get_config("app", "min_size", [1200, 800])
        
        self.title(app_title)
        self.geometry(app_geometry)
        self.minsize(min_size[0], min_size[1])
        
        # State variables
        self.file_path = tk.StringVar()
        self.raw_text_content: Optional[str] = None
        self.report_data: Optional[Dict[str, Any]] = None
        
        self._setup_ui()
        self._create_menu()
        
        self.logger.info("Application initialized successfully")
    
    def _get_services(self):
        """Get services, initializing them if needed"""
        if not self.services_initialized:
            self.airport_service, self.calculator_service, self.roster_parser, self.exporter, self.df_optimizer = _init_services()
            self.services_initialized = True
        return self.airport_service, self.calculator_service, self.roster_parser, self.exporter, self.df_optimizer
    
    def _setup_ui(self):
        """Setup the user interface"""
        # Configure modern styles
        style = ttk.Style()
        style.theme_use('clam')  # More modern theme
        
        # Custom styles
        style.configure('Title.TLabel', font=('Segoe UI', 14, 'bold'), foreground='#2c3e50')
        style.configure('Subtitle.TLabel', font=('Segoe UI', 10), foreground='#34495e')
        style.configure('Accent.TButton', font=('Segoe UI', 12, 'bold'), foreground='white')
        style.map('Accent.TButton', background=[('active', '#3498db'), ('!active', '#2980b9')])
        style.configure('Success.TButton', font=('Segoe UI', 10), foreground='white')
        style.map('Success.TButton', background=[('active', '#27ae60'), ('!active', '#2ecc71')])
        
        # Main container with better padding
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Header section
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = ttk.Label(header_frame, text="✈️ Pilot Salary Calculator", style='Title.TLabel')
        title_label.pack(side="left")
        
        subtitle_label = ttk.Label(header_frame, text="Advanced calculation for Italian airline pilots", style='Subtitle.TLabel')
        subtitle_label.pack(side="left", padx=(10, 0))
        
        # Progress bar (initially hidden)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, mode='determinate')
        
        # Input section
        self._create_input_section(main_frame)
        
        # Calculate button with icon
        calc_button = ttk.Button(
            main_frame, 
            text="🧮 Calculate Salary", 
            command=self._calculate_salary,
            style='Accent.TButton'
        )
        calc_button.pack(fill="x", pady=20, ipady=10)
        
        # Results section
        self._create_results_section(main_frame)
    
    def _create_input_section(self, parent):
        """Create input controls section"""
        # Create two sections: Configuration and File Upload
        
        # Configuration section
        config_frame = ttk.LabelFrame(parent, text="📋 Pilot Configuration", padding="15")
        config_frame.pack(fill="x", pady=(0, 10))
        
        # Configure grid
        for i in range(4):
            config_frame.columnconfigure(i, weight=1)
        
        # Position and extras with tooltips
        ttk.Label(config_frame, text="Position:", font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky="w", padx=5, pady=8)
        self.position_combo = ttk.Combobox(
            config_frame, values=list(SalaryConfig.POSITIONS.keys()), 
            state="readonly", width=15, font=('Segoe UI', 10)
        )
        self.position_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=8)
        self.position_combo.current(1)  # Default to FO
        
        ttk.Label(config_frame, text="Extra Position:", font=('Segoe UI', 10, 'bold')).grid(row=0, column=2, sticky="w", padx=5, pady=8)
        self.extra_combo = ttk.Combobox(
            config_frame, values=list(SalaryConfig.EXTRA_POSITIONS.keys()),
            state="readonly", width=15, font=('Segoe UI', 10)
        )
        self.extra_combo.grid(row=0, column=3, sticky="ew", padx=5, pady=8)
        self.extra_combo.current(0)  # Default to None
        
        # Contract and home base
        ttk.Label(config_frame, text="Contract:", font=('Segoe UI', 10, 'bold')).grid(row=1, column=0, sticky="w", padx=5, pady=8)
        self.contract_combo = ttk.Combobox(
            config_frame, values=list(SalaryConfig.CONTRACTS.keys()),
            state="readonly", width=15, font=('Segoe UI', 10)
        )
        self.contract_combo.grid(row=1, column=1, sticky="ew", padx=5, pady=8)
        self.contract_combo.current(0)  # Default to Standard
        
        ttk.Label(config_frame, text="Home Base:", font=('Segoe UI', 10, 'bold')).grid(row=1, column=2, sticky="w", padx=5, pady=8)
        self.home_base_combo = ttk.Combobox(
            config_frame, values=["MXP", "FCO", "BGY", "LIN"], state="readonly", width=15, font=('Segoe UI', 10)
        )
        self.home_base_combo.grid(row=1, column=3, sticky="ew", padx=5, pady=8)
        self.home_base_combo.current(0)
        
        # SNC and Month selection
        ttk.Label(config_frame, text="SNC Units:", font=('Segoe UI', 10, 'bold')).grid(row=2, column=0, sticky="w", padx=5, pady=8)
        self.snc_entry = ttk.Entry(config_frame, width=10, font=('Segoe UI', 10))
        self.snc_entry.grid(row=2, column=1, sticky="w", padx=5, pady=8)
        self.snc_entry.insert(0, "0")
        
        ttk.Label(config_frame, text="Filter by Month:", font=('Segoe UI', 10, 'bold')).grid(row=2, column=2, sticky="w", padx=5, pady=8)
        
        # Month filtering frame
        month_frame = ttk.Frame(config_frame)
        month_frame.grid(row=2, column=3, sticky="ew", padx=5, pady=8)
        
        self.filter_month_var = tk.BooleanVar(value=False)  # Default: no filtering
        month_check = ttk.Checkbutton(month_frame, text="Payment month:", variable=self.filter_month_var)
        month_check.pack(side="left")
        
        current_month = datetime.now().month
        self.payment_month_combo = ttk.Combobox(
            month_frame, values=[f"{i:02d}" for i in range(1, 13)],
            state="readonly", width=8, font=('Segoe UI', 9)
        )
        self.payment_month_combo.pack(side="left", padx=(5, 0))
        self.payment_month_combo.current(current_month - 1)  # Current month
        
        # File upload section
        file_frame = ttk.LabelFrame(parent, text="📁 Roster File Upload", padding="15")
        file_frame.pack(fill="x", pady=(0, 10))
        
        file_inner_frame = ttk.Frame(file_frame)
        file_inner_frame.pack(fill="x")
        
        ttk.Label(file_inner_frame, text="Roster File (.txt):", font=('Segoe UI', 10, 'bold')).pack(side="left", padx=(0, 10))
        
        # File path display
        self.file_display_frame = ttk.Frame(file_inner_frame)
        self.file_display_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.file_status_label = ttk.Label(self.file_display_frame, text="No file selected", foreground="gray", font=('Segoe UI', 9))
        self.file_status_label.pack(side="left")
        
        # Browse button
        browse_button = ttk.Button(file_inner_frame, text="📂 Browse", command=self._browse_file, style='Success.TButton')
        browse_button.pack(side="right")
        
        # Options section
        options_frame = ttk.LabelFrame(parent, text="⚙️ Advanced Options", padding="15")
        options_frame.pack(fill="x", pady=(0, 10))
        
        options_inner = ttk.Frame(options_frame)
        options_inner.pack(fill="x")
        
        self.debug_var = tk.BooleanVar()
        debug_check = ttk.Checkbutton(options_inner, text="🐛 Debug Mode", variable=self.debug_var, padding=5)
        debug_check.pack(side="left", padx=10)
        
        self.sim_increase_var = tk.BooleanVar()
        sim_check = ttk.Checkbutton(
            options_inner, text="📈 Simulate Salary Increase", 
            variable=self.sim_increase_var, command=self._toggle_simulation, padding=5
        )
        sim_check.pack(side="left", padx=10)
        
    
    def _create_results_section(self, parent):
        """Create results display section"""
        results_frame = ttk.LabelFrame(parent, text="Calculation Results", padding="10")
        results_frame.pack(fill="both", expand=True)
        
        # Create notebook for organized display
        notebook = ttk.Notebook(results_frame)
        notebook.pack(fill="both", expand=True)
        
        # Schedule tab
        schedule_frame = ttk.Frame(notebook)
        notebook.add(schedule_frame, text="Flight Schedule")
        self._create_schedule_tab(schedule_frame)
        
        # Summary tab
        summary_frame = ttk.Frame(notebook)
        notebook.add(summary_frame, text="Salary Summary")
        self._create_summary_tab(summary_frame)
    
    def _create_schedule_tab(self, parent):
        """Create flight schedule display tab"""
        # Treeview for flight details
        columns = ('Itinerary', 'Flights', 'Sectors', 'Diaria', 'Earnings')
        self.tree = ttk.Treeview(parent, columns=columns, show='headings tree')
        
        # Configure columns
        self.tree.heading('#0', text='Date')
        self.tree.column('#0', width=120, anchor='w')
        
        self.tree.heading('Itinerary', text='Itinerary / Activity')
        self.tree.column('Itinerary', width=400, anchor='w')
        
        self.tree.heading('Flights', text='Flights')
        self.tree.column('Flights', width=80, anchor='center')
        
        self.tree.heading('Sectors', text='Sectors')
        self.tree.column('Sectors', width=100, anchor='e')
        
        self.tree.heading('Diaria', text='Diaria')
        self.tree.column('Diaria', width=80, anchor='center')
        
        self.tree.heading('Earnings', text='Earnings (€)')
        self.tree.column('Earnings', width=120, anchor='e')
        
        # Configure tags for styling
        self.tree.tag_configure('work_day', background='#E8F5E9')
        self.tree.tag_configure('off_day', foreground='gray')
        self.tree.tag_configure('positioning', foreground='blue', font=('Helvetica', 9, 'italic'))
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(parent, orient="horizontal", command=self.tree.xview)
        
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack widgets
        self.tree.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")
    
    def _create_summary_tab(self, parent):
        """Create salary summary display tab"""
        self.summary_text = tk.Text(
            parent, font=("Courier New", 11), 
            state="disabled", wrap="none"
        )
        
        summary_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.summary_text.yview)
        self.summary_text.configure(yscrollcommand=summary_scrollbar.set)
        
        self.summary_text.pack(side="left", fill="both", expand=True)
        summary_scrollbar.pack(side="right", fill="y")
    
    def _create_menu(self):
        """Create application menu"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        
        file_menu.add_command(label="Load Report", command=self._load_report)
        file_menu.add_command(label="Save Report", command=self._save_report, state="disabled")
        file_menu.add_separator()
        
        # Export submenu
        export_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Export", menu=export_menu)
        export_menu.add_command(label="Export to CSV...", command=self._export_csv, state="disabled")
        export_menu.add_command(label="Export to Excel...", command=self._export_excel, state="disabled")
        export_menu.add_command(label="Export to Text...", command=self._export_text, state="disabled")
        
        file_menu.add_separator()
        file_menu.add_command(label="Open Statistics...", command=self._open_statistics)
        file_menu.add_separator()
        file_menu.add_command(label="Clear Cache", command=self._clear_cache)
        file_menu.add_command(label="Reset", command=self._reset_application)
        file_menu.add_separator()
        file_menu.add_command(label="Settings...", command=self._open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        
        # Store menu references for enabling/disabling items
        self.file_menu = file_menu
        self.export_menu = export_menu
    
    def _browse_file(self):
        """Browse and select roster file"""
        file_path = filedialog.askopenfilename(
            title="Select Roster File",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        self.file_path.set(file_path)
        
        # Show progress while loading
        self.progress_bar.pack(fill="x", pady=5)
        self.progress_var.set(10)
        self.update()
        
        # Try to read file with different encodings
        encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']
        
        for i, encoding in enumerate(encodings):
            self.progress_var.set(20 + (i * 20))
            self.update()
            
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    self.raw_text_content = f.read()
                
                # Update file status
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                self.file_status_label.config(
                    text=f"✅ {filename} ({file_size:,} bytes)",
                    foreground="green"
                )
                
                self.progress_var.set(100)
                self.update()
                self.logger.info(f"Successfully loaded roster file with {encoding} encoding")
                
                # Hide progress bar after short delay
                self.after(1000, lambda: self.progress_bar.pack_forget())
                return
                
            except UnicodeDecodeError:
                continue
            except Exception as e:
                self.progress_bar.pack_forget()
                messagebox.showerror("File Error", f"Could not read file: {e}")
                self.file_status_label.config(text="❌ Error loading file", foreground="red")
                self.raw_text_content = None
                return
        
        self.progress_bar.pack_forget()
        messagebox.showerror("Encoding Error", "Could not read file with any known encoding.")
        self.file_status_label.config(text="❌ Encoding error", foreground="red")
        self.raw_text_content = None
    
    def _get_user_profile(self) -> Optional[PilotProfile]:
        """Get user input as PilotProfile"""
        if not self.raw_text_content:
            messagebox.showwarning("Missing Data", "Please select a roster file first.")
            return None
        
        try:
            snc_units = validate_integer_input(self.snc_entry.get(), "SNC Units")
            
            if snc_units < 0:
                messagebox.showerror("Invalid Input", "SNC Units cannot be negative.")
                return None
            
            profile = PilotProfile(
                position=self.position_combo.get(),
                extra_position=self.extra_combo.get(),
                contract_type=self.contract_combo.get(),
                home_base=self.home_base_combo.get(),
                snc_units=snc_units,
                debug_mode=self.debug_var.get()
            )
            
            # Add payment month to profile only if filtering is enabled
            if self.filter_month_var.get():
                payment_month = int(self.payment_month_combo.get())
                profile.payment_month = payment_month
                self.logger.info(f"Month filtering enabled for payment month {payment_month}")
            else:
                self.logger.info("Month filtering disabled - processing all dates")
            
            return profile
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", str(e))
            return None
    
    def _calculate_salary(self):
        """Main salary calculation method"""
        try:
            # Initialize services if needed and show progress
            self.progress_bar.pack(fill="x", pady=5)
            self.progress_var.set(5)
            self.update()
            
            # Get services (lazy initialization)
            airport_service, calculator_service, roster_parser, exporter, df_optimizer = self._get_services()
            self.progress_var.set(15)
            self.update()
            
            # Reset simulation
            self.sim_increase_var.set(False)
            
            # Get user inputs
            profile = self._get_user_profile()
            if not profile:
                self.progress_bar.pack_forget()
                return
            
            self.progress_var.set(25)
            self.update()
            
            # Parse roster
            try:
                roster_data = roster_parser.parse_roster_text(self.raw_text_content)
                self.progress_var.set(40)
                self.update()
            except ValueError as e:
                self.progress_bar.pack_forget()
                messagebox.showerror("Roster Parse Error", f"Could not parse roster: {e}")
                return
            
            # Calculate salary with missing airport handling
            while True:
                try:
                    self.progress_var.set(60)
                    self.update()
                    
                    (detailed_df, grouped_df, ido_bonuses, night_stop_bonus, 
                     extra_diaria_days, salary_calc) = calculator_service.calculate_salary(
                        roster_data, profile
                    )
                    break
                    
                except MissingAirportError as e:
                    self.progress_bar.pack_forget()
                    
                    # Show dialog to get missing airport coordinates
                    dialog = NewAirportDialog(self, e.iata_code)
                    self.wait_window(dialog)
                    
                    if dialog.result:
                        lat, lon = dialog.result
                        airport_service.add_airport(e.iata_code, lat, lon)
                        self.logger.info(f"Added missing airport {e.iata_code}")
                        self.progress_bar.pack(fill="x", pady=5)
                    else:
                        messagebox.showwarning(
                            "Calculation Cancelled", 
                            f"Calculation cancelled - missing coordinates for {e.iata_code}"
                        )
                        return
            
            self.progress_var.set(80)
            self.update()
            
            if detailed_df.empty:
                self.progress_bar.pack_forget()
                messagebox.showinfo("No Data", "No valid flight data found in roster.")
                return
            
            # Optimize DataFrames for better performance
            detailed_df = df_optimizer.optimize_dtypes(detailed_df)
            grouped_df = df_optimizer.optimize_dtypes(grouped_df)
            
            self.progress_var.set(90)
            self.update()
            
            # Store calculation results
            self._store_calculation_results(
                profile, detailed_df, grouped_df, ido_bonuses, 
                night_stop_bonus, extra_diaria_days, salary_calc
            )
            
            # Display results
            self._display_results(detailed_df, grouped_df, ido_bonuses, extra_diaria_days, salary_calc)
            
            # Enable save and export menus
            self.file_menu.entryconfig("Save Report", state="normal")
            self._enable_export_menus(True)
            
            self.progress_var.set(100)
            self.update()
            self.logger.info("Salary calculation completed successfully")
            
            # Hide progress bar after short delay
            self.after(1000, lambda: self.progress_bar.pack_forget())
            
        except Exception as e:
            self.progress_bar.pack_forget()
            self.logger.exception("Calculation failed")
            messagebox.showerror("Calculation Error", f"An error occurred during calculation:\n\n{e}")
    
    
    def _store_calculation_results(self, profile: PilotProfile, detailed_df: pd.DataFrame,
                                 grouped_df: pd.DataFrame, ido_bonuses: List[BonusInfo],
                                 night_stop_bonus: float, extra_diaria_days: Set[str],
                                 salary_calc):
        """Store calculation results for later use"""
        # Get position data for diaria calculation
        _, _, _, diaria, _ = SalaryConfig.POSITIONS[profile.position]
        
        # Use correct working days from salary calculation (includes midnight standby days)
        working_days = salary_calc.working_days
        
        self.report_data = {
            'user_inputs': {
                'position': profile.position,
                'extra_position': profile.extra_position,
                'contract_type': profile.contract_type,
                'home_base': profile.home_base,
                'snc_units': profile.snc_units
            },
            'df_dettagliato': detailed_df,
            'df_raggruppato': grouped_df,
            'ido_bonuses': [{'date': b.date, 'symbol': b.symbol, 'amount': b.amount} for b in ido_bonuses],
            'night_stop_bonus': night_stop_bonus,
            'extra_diaria_days': extra_diaria_days,
            'midnight_standby_days': salary_calc.midnight_standby_days,
            'midnight_standby_dates': salary_calc.midnight_standby_dates,
            'salary_data': {
                'gross_total': salary_calc.gross_total,
                'net_estimated': salary_calc.net_estimated,
                'operational_sectors_earnings': salary_calc.operational_sectors_earnings,
                'positioning_earnings': salary_calc.positioning_earnings,
                'frv_bonus': salary_calc.frv_bonus,
                'snc_compensation': salary_calc.snc_compensation,
                'vacation_compensation': salary_calc.vacation_compensation,
                'vacation_days': salary_calc.vacation_days,
                'taxable_income': salary_calc.taxable_income,
                'contribution_base': salary_calc.contribution_base,
                'estimated_tax': salary_calc.estimated_tax,
                'social_contributions': salary_calc.social_contributions
            },
            'diaria': diaria,
            'working_days': working_days
        }
    
    def _display_results(self, detailed_df: pd.DataFrame, grouped_df: pd.DataFrame,
                        ido_bonuses: List[BonusInfo], extra_diaria_days: Set[str], salary_calc):
        """Display calculation results in UI"""
        # Get diaria value
        _, _, _, diaria, _ = SalaryConfig.POSITIONS[self.position_combo.get()]
        
        # Display schedule
        midnight_standby_dates = salary_calc.midnight_standby_dates
        self._display_schedule(detailed_df, grouped_df, ido_bonuses, extra_diaria_days, midnight_standby_dates, diaria)
        
        # Display summary
        self._display_salary_summary(grouped_df, salary_calc, extra_diaria_days, diaria)
    
    def _display_schedule(self, detailed_df: pd.DataFrame, grouped_df: pd.DataFrame,
                         ido_bonuses: List[BonusInfo], extra_diaria_days: Set[str], 
                         midnight_standby_dates: Set[str], diaria: float):
        """Display flight schedule in treeview"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add grouped data
        for _, day_row in grouped_df.iterrows():
            date_obj = day_row['Data']
            date_str = date_obj.strftime('%Y-%m-%d')
            
            is_work_day = (day_row['Settori'] > 0 or 
                          "Training" in day_row['Attività'] or 
                          "Airport Duty" in day_row['Attività'])
            tag = 'work_day' if is_work_day else 'off_day'
            
            # Prepare display values
            # Prepare display values with special handling for Airport Duty and Training
            if "Training" in day_row['Attività']:
                activity_display = day_row['Attività']
            elif "Airport Duty" in day_row['Attività']:
                # Show airport duty with hours
                sectors = day_row['Settori']
                if sectors == 1.0:
                    hours_info = "(≤4 hours)"
                elif sectors == 2.0:
                    hours_info = "(>4 hours)"
                else:
                    hours_info = f"({sectors} sectors)"
                activity_display = f"Airport Duty {hours_info}"  
            elif is_work_day:
                activity_display = day_row['Itinerario']
            else:
                activity_display = day_row['Attività']
            
            flights_display = str(day_row['Volo']) if is_work_day else '---'
            sectors_display = f"{day_row['Settori']:.2f}"
            
            # Determine if this day counts toward diaria
            activity_str = day_row['Attività']
            counts_diaria = (any(pattern in activity_str for pattern in ["Flight", "Positioning", "Training", "Rest Day"]) 
                           and "Airport Duty" not in activity_str) or date_str in midnight_standby_dates
            diaria_display = "✓" if counts_diaria else "—"
            
            # Calculate earnings display
            earnings_str = f"{day_row['Guadagno (€)']:.2f}"
            
            # Add extra diaria indicator
            if date_str in extra_diaria_days:
                earnings_str += f" (+{diaria:.2f}€)"
            
            # Add IDO bonus indicators
            for bonus in ido_bonuses:
                if bonus.date == date_str:
                    earnings_str += f" {bonus.symbol}"
            
            # Insert parent item
            parent_id = self.tree.insert(
                "", "end", iid=date_str,
                text=f" {date_str}",
                values=(activity_display, flights_display, sectors_display, diaria_display, earnings_str),
                tags=(tag,)
            )
            
            # Add flight details for work days (but not for Airport Duty or Training)
            if (is_work_day and 
                "Training" not in day_row['Attività'] and 
                "Airport Duty" not in day_row['Attività']):
                day_flights = detailed_df[detailed_df['Data'].dt.date == date_obj]
                
                for _, flight_row in day_flights.iterrows():
                    # Format sectors with cumulative info
                    if flight_row['Attività'] == 'Flight':
                        sectors_display = f"{flight_row['Settori']:.2f} (#{flight_row['Settori Cumulativi Operativi']:.1f})"
                        flight_tag = ()
                    else:
                        sectors_display = f"{flight_row['Settori']:.2f} (POS)"
                        flight_tag = ('positioning',)
                    
                    self.tree.insert(
                        parent_id, "end",
                        text=f"   ↳ {flight_row['Volo']}",
                        values=(
                            f"{flight_row['Partenza']} - {flight_row['Arrivo']}",
                            f"{flight_row['Distanza']:.0f} NM",
                            sectors_display,
                            "",  # Individual flights don't show diaria
                            f"{flight_row['Guadagno (€)']:.2f}"
                        ),
                        tags=flight_tag
                    )
    
    def _display_salary_summary(self, grouped_df: pd.DataFrame, salary_calc, 
                               extra_diaria_days: Set[str], diaria: float):
        """Display salary summary"""
        # Get month/year from data
        month_year = pd.to_datetime(grouped_df['Data'].iloc[0]).strftime('%B %Y').upper()
        
        # Calculate diaria using correct working days from salary calculation
        base_working_days = salary_calc.base_working_days
        midnight_standby_days = salary_calc.midnight_standby_days
        working_days = salary_calc.working_days
        extra_diaria_count = len(extra_diaria_days)
        total_diaria_days = working_days + extra_diaria_count
        total_diaria = total_diaria_days * diaria
        
        # Format diaria string showing breakdown
        if midnight_standby_days > 0 and extra_diaria_count > 0:
            diaria_str = f"Diaria Totale ({base_working_days}+{midnight_standby_days}+{extra_diaria_count} giorni):"
        elif midnight_standby_days > 0:
            diaria_str = f"Diaria Totale ({base_working_days}+{midnight_standby_days} giorni):"
        elif extra_diaria_count > 0:
            diaria_str = f"Diaria Totale ({base_working_days}+{extra_diaria_count} giorni):"
        else:
            diaria_str = f"Diaria Totale ({total_diaria_days} giorni):"
        
        # Get bonuses from stored report data
        night_stop_bonus = self.report_data.get('night_stop_bonus', 0) if self.report_data else 0
        total_ido_bonus = sum(b['amount'] for b in self.report_data.get('ido_bonuses', [])) if self.report_data else 0
        
        # Build summary (matching original format exactly)
        summary_lines = [
            f"===== STIMA STIPENDIO PER {month_year} =====",
            f"{'Stipendio Lordo Totale:':<48} {salary_calc.gross_total:>15,.2f} €",
        ]
        
        # Calculate base salary (always show)
        base_salary = (salary_calc.gross_total - salary_calc.operational_sectors_earnings - 
                      salary_calc.positioning_earnings - salary_calc.frv_bonus - 
                      salary_calc.snc_compensation - salary_calc.vacation_compensation - 
                      night_stop_bonus - total_ido_bonus)
        summary_lines.append(f"{'   - Stipendio Fisso Lordo (Base + Indennità):':<48} {base_salary:>15,.2f} €")
        
        # Only show non-zero components
        if salary_calc.operational_sectors_earnings > 0:
            summary_lines.append(f"{'   - Guadagno da Settori Operativi:':<48} {salary_calc.operational_sectors_earnings:>15,.2f} €")
        
        if salary_calc.positioning_earnings > 0:
            summary_lines.append(f"{'   - Guadagno da Voli di Posizionamento:':<48} {salary_calc.positioning_earnings:>15,.2f} €")
        
        if salary_calc.frv_bonus > 0:
            summary_lines.append(f"{'   - Aumento Contratto FRV (11%):':<48} {salary_calc.frv_bonus:>15,.2f} €")
        
        if salary_calc.snc_compensation > 0:
            summary_lines.append(f"{'   - Compenso SNC:':<48} {salary_calc.snc_compensation:>15,.2f} €")
        
        if salary_calc.vacation_compensation > 0:
            vacation_label = f"   - Compenso Ferie ({salary_calc.vacation_days} giorni):"
            summary_lines.append(f"{vacation_label:<48} {salary_calc.vacation_compensation:>15,.2f} €")
        
        if night_stop_bonus > 0:
            summary_lines.append(f"{'   - Bonus Night Stop (POS):':<48} {night_stop_bonus:>15,.2f} €")
        
        if total_ido_bonus > 0:
            summary_lines.append(f"{'   - Bonus Infrazione Riposo (IDO):':<48} {total_ido_bonus:>15,.2f} €")
        
        summary_lines.extend([
            f"{'':-^65}",
            f"{'Totale Settori Operativi nel Mese:':<48} {self._get_total_operational_sectors():>15.1f}",
        ])
        
        # Add positioning flights count if any
        if hasattr(salary_calc, 'positioning_earnings') and salary_calc.positioning_earnings > 0:
            detailed_df = self.report_data.get('df_dettagliato') if self.report_data else None
            if detailed_df is not None:
                num_positioning = detailed_df[detailed_df['IsPositioning'] == True].shape[0]
                if num_positioning > 0:
                    summary_lines.append(f"{'Voli di Posizionamento Effettuati:':<48} {num_positioning}")
        
        summary_lines.extend([
            f"{'':-^65}",
            f"{'Base per Contributi:':<48} {salary_calc.contribution_base:>15,.2f} €",
            f"{'Contributi Previdenziali (INPS):':<48} {-salary_calc.social_contributions:>15,.2f} €",
            f"{'Imponibile Fiscale (IRPEF):':<48} {salary_calc.taxable_income:>15,.2f} €",
            f"{'Tasse Stimate (IRPEF):':<48} {-salary_calc.estimated_tax:>15,.2f} €",
            f"{diaria_str:<48} {total_diaria:>15,.2f} €",
            f"{'':-^65}",
            f"{'STIPENDIO NETTO STIMATO IN BUSTA PAGA:':<48} {salary_calc.net_estimated + total_diaria:>15,.2f} €",
        ])
        
        # Display in text widget
        self.summary_text.config(state="normal")
        self.summary_text.delete(1.0, "end")
        self.summary_text.insert(1.0, "\n".join(summary_lines))
        self.summary_text.config(state="disabled")
    
    def _get_total_operational_sectors(self) -> float:
        """Get total operational sectors from report data"""
        if not self.report_data or 'df_dettagliato' not in self.report_data:
            return 0.0
        
        df = self.report_data['df_dettagliato']
        return df['Settori Operativi'].sum() if 'Settori Operativi' in df.columns else 0.0
    
    def _toggle_simulation(self):
        """Toggle salary increase simulation"""
        if self.sim_increase_var.get():
            self._run_salary_simulation()
        else:
            # Restore original display
            if self.report_data:
                self._display_salary_summary(
                    self.report_data['df_raggruppato'],
                    type('obj', (object,), self.report_data['salary_data'])(),
                    self.report_data['extra_diaria_days'],
                    self.report_data['diaria']
                )
    
    def _run_salary_simulation(self):
        """Run salary increase simulation"""
        if not self.report_data:
            messagebox.showwarning("Warning", "Please run a calculation first.", parent=self)
            self.sim_increase_var.set(False)
            return
        
        percentage_str = simpledialog.askstring(
            "Salary Increase Simulation", 
            "Enter percentage increase (e.g., '5' for 5%):",
            parent=self
        )
        
        if not percentage_str:
            self.sim_increase_var.set(False)
            return
        
        try:
            increase_perc = float(percentage_str)
            if increase_perc < 0:
                raise ValueError("Percentage cannot be negative")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid percentage.", parent=self)
            self.sim_increase_var.set(False)
            return
        
        # Properly recalculate salary with increase
        multiplier = 1 + (increase_perc / 100)
        original = self.report_data['salary_data']
        
        # Apply increase to sector values and base components
        new_gross = original['gross_total'] * multiplier
        new_operational = original['operational_sectors_earnings'] * multiplier
        new_positioning = original['positioning_earnings'] * multiplier
        new_frv = original['frv_bonus'] * multiplier
        new_snc = original['snc_compensation'] * multiplier
        new_vacation = original['vacation_compensation'] * multiplier
        
        # Recalculate taxes and contributions on new amounts
        new_contribution_base = original['contribution_base'] * multiplier
        new_social_contributions = new_contribution_base * SalaryConfig.get_total_contribution_rate()
        new_taxable_income = new_contribution_base - new_social_contributions
        
        # Calculate new tax
        from utils import calculate_tax
        new_estimated_tax = calculate_tax(new_taxable_income, SalaryConfig.TAX_BRACKETS)
        
        # Calculate new net salary
        new_net = new_taxable_income - new_estimated_tax + (original['gross_total'] - original['contribution_base']) * multiplier
        
        # Get diaria info
        working_days = self.report_data.get('working_days', 0)
        extra_diaria_count = len(self.report_data.get('extra_diaria_days', set()))
        total_diaria_days = working_days + extra_diaria_count
        total_diaria = total_diaria_days * self.report_data.get('diaria', 0)
        
        # Create detailed simulation summary
        summary_lines = [
            f"===== SALARY SIMULATION (+{increase_perc:.1f}%) =====",
            f"{'Component':<40}{'Original':>15}{'Simulated':>15}{'Increase':>15}",
            f"{'':-^85}",
            f"{'Gross Total:':<40}{original['gross_total']:>15,.2f}{new_gross:>15,.2f}{new_gross - original['gross_total']:>15,.2f}",
            f"{'Operational Sectors:':<40}{original['operational_sectors_earnings']:>15,.2f}{new_operational:>15,.2f}{new_operational - original['operational_sectors_earnings']:>15,.2f}",
            f"{'Positioning Earnings:':<40}{original['positioning_earnings']:>15,.2f}{new_positioning:>15,.2f}{new_positioning - original['positioning_earnings']:>15,.2f}",
            "",
            f"{'Social Contributions:':<40}{-original['social_contributions']:>15,.2f}{-new_social_contributions:>15,.2f}{-(new_social_contributions - original['social_contributions']):>15,.2f}",
            f"{'Estimated Tax:':<40}{-original['estimated_tax']:>15,.2f}{-new_estimated_tax:>15,.2f}{-(new_estimated_tax - original['estimated_tax']):>15,.2f}",
            f"{'Diaria (unchanged):':<40}{total_diaria:>15,.2f}{total_diaria:>15,.2f}{0:>15,.2f}",
            f"{'':-^85}",
            f"{'NET TOTAL:':<40}{original['net_estimated'] + total_diaria:>15,.2f}{new_net + total_diaria:>15,.2f}{(new_net + total_diaria) - (original['net_estimated'] + total_diaria):>15,.2f}",
            "",
            f"Monthly increase: +{(new_net + total_diaria) - (original['net_estimated'] + total_diaria):.2f} €",
            f"Annual increase: +{((new_net + total_diaria) - (original['net_estimated'] + total_diaria)) * 12:.2f} €"
        ]
        
        self.summary_text.config(state="normal")
        self.summary_text.delete(1.0, "end")
        self.summary_text.insert(1.0, "\n".join(summary_lines))
        self.summary_text.config(state="disabled")
    
    def _save_report(self):
        """Save current report"""
        if not self.report_data:
            messagebox.showwarning("Warning", "No report data to save.")
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Save Salary Report",
            defaultextension=".salrep",
            filetypes=[("Salary Reports", "*.salrep"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'wb') as f:
                pickle.dump(self.report_data, f)
            
            messagebox.showinfo("Success", "Report saved successfully.")
            self.logger.info(f"Report saved to {filepath}")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save report:\n{e}")
            self.logger.error(f"Failed to save report: {e}")
    
    def _load_report(self):
        """Load saved report"""
        filepath = filedialog.askopenfilename(
            title="Load Salary Report",
            filetypes=[("Salary Reports", "*.salrep"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'rb') as f:
                self.report_data = pickle.load(f)
            
            self._populate_from_report()
            self.file_menu.entryconfig("Save Report", state="normal")
            self._enable_export_menus(True)
            
            messagebox.showinfo("Success", "Report loaded successfully.")
            self.logger.info(f"Report loaded from {filepath}")
            
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load report:\n{e}")
            self.logger.error(f"Failed to load report: {e}")
    
    def _populate_from_report(self):
        """Populate UI from loaded report"""
        if not self.report_data:
            return
        
        inputs = self.report_data['user_inputs']
        
        # Set combobox values
        self.position_combo.set(inputs.get('position', ''))
        self.extra_combo.set(inputs.get('extra_position', ''))
        self.contract_combo.set(inputs.get('contract_type', ''))
        self.home_base_combo.set(inputs.get('home_base', ''))
        self.snc_entry.delete(0, "end")
        self.snc_entry.insert(0, str(inputs.get('snc_units', 0)))
        
        # Display results
        ido_bonuses = [BonusInfo(b['date'], b['symbol'], b['amount']) for b in self.report_data['ido_bonuses']]
        
        salary_calc = type('obj', (object,), self.report_data['salary_data'])()
        
        self._display_results(
            self.report_data['df_dettagliato'],
            self.report_data['df_raggruppato'],
            ido_bonuses,
            self.report_data['extra_diaria_days'],
            salary_calc
        )
    
    def _open_statistics(self):
        """Open statistics viewer"""
        StatisticsViewer(self)
    
    def _reset_application(self):
        """Reset application to initial state"""
        # Reset variables
        self.file_path.set("")
        self.raw_text_content = None
        self.report_data = None
        
        # Reset controls
        self.position_combo.current(1)
        self.extra_combo.current(0)
        self.contract_combo.current(0)
        self.home_base_combo.current(0)
        
        self.snc_entry.delete(0, "end")
        self.snc_entry.insert(0, "0")
        
        self.debug_var.set(False)
        self.sim_increase_var.set(False)
        
        # Clear displays
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.summary_text.config(state="normal")
        self.summary_text.delete(1.0, "end")
        self.summary_text.config(state="disabled")
        
        # Disable save and export menus
        self.file_menu.entryconfig("Save Report", state="disabled")
        self._enable_export_menus(False)
        
        self.logger.info("Application reset")
    
    def _enable_export_menus(self, enabled: bool):
        """Enable or disable export menu items"""
        state = "normal" if enabled else "disabled"
        self.export_menu.entryconfig("Export to CSV...", state=state)
        self.export_menu.entryconfig("Export to Excel...", state=state)
        self.export_menu.entryconfig("Export to Text...", state=state)
    
    def _export_csv(self):
        """Export report to CSV format"""
        if not self.report_data:
            messagebox.showwarning("Warning", "No report data to export.")
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Export to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            success = self.exporter.export_to_csv(
                filepath,
                self.report_data['df_dettagliato'],
                self.report_data['df_raggruppato'],
                self.report_data['salary_data']
            )
            
            if success:
                messagebox.showinfo("Success", "Report exported to CSV successfully.")
                self.logger.info(f"Report exported to CSV: {filepath}")
            else:
                messagebox.showerror("Export Error", "Failed to export report to CSV.")
                
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export report:\n{e}")
            self.logger.error(f"CSV export failed: {e}")
    
    def _export_excel(self):
        """Export report to Excel format"""
        if not self.report_data:
            messagebox.showwarning("Warning", "No report data to export.")
            return
        
        if not self.exporter.excel_available:
            messagebox.showerror(
                "Excel Export Unavailable", 
                "Excel export requires the 'openpyxl' package.\n"
                "Install it with: pip install openpyxl"
            )
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Export to Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            # Convert BonusInfo objects back to the format expected by exporter
            ido_bonuses = [
                BonusInfo(b['date'], b['symbol'], b['amount']) 
                for b in self.report_data['ido_bonuses']
            ]
            
            success = self.exporter.export_to_excel(
                filepath,
                self.report_data['df_dettagliato'],
                self.report_data['df_raggruppato'],
                self.report_data['salary_data'],
                ido_bonuses,
                self.report_data['extra_diaria_days'],
                self.report_data['user_inputs']
            )
            
            if success:
                messagebox.showinfo("Success", "Report exported to Excel successfully.")
                self.logger.info(f"Report exported to Excel: {filepath}")
            else:
                messagebox.showerror("Export Error", "Failed to export report to Excel.")
                
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export report:\n{e}")
            self.logger.error(f"Excel export failed: {e}")
    
    def _export_text(self):
        """Export report to formatted text"""
        if not self.report_data:
            messagebox.showwarning("Warning", "No report data to export.")
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Export to Text",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            success = self.exporter.export_to_text(
                filepath,
                self.report_data['df_raggruppato'],
                self.report_data['salary_data'],
                self.report_data['user_inputs']
            )
            
            if success:
                messagebox.showinfo("Success", "Report exported to text file successfully.")
                self.logger.info(f"Report exported to text: {filepath}")
            else:
                messagebox.showerror("Export Error", "Failed to export report to text.")
                
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export report:\n{e}")
            self.logger.error(f"Text export failed: {e}")
    
    def _clear_cache(self):
        """Clear performance cache"""
        clear_cache()
        messagebox.showinfo("Cache Cleared", "Performance cache has been cleared.")
        self.logger.info("Performance cache cleared")
    
    def _open_settings(self):
        """Open settings dialog"""
        SettingsDialog(self, self.config_manager)
    
    def quit(self):
        """Override quit to save configuration"""
        # Save current window state
        self.config_manager.set("app", "geometry", self.geometry())
        self.config_manager.save_config()
        super().quit()


class SettingsDialog(tk.Toplevel):
    """Settings configuration dialog"""
    
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager
        
        self.title("Application Settings")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._load_current_settings()
        self._center_window()
    
    def _create_widgets(self):
        """Create settings dialog widgets"""
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Create notebook for categories
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=(0, 20))
        
        # Application tab
        app_frame = ttk.Frame(notebook)
        notebook.add(app_frame, text="Application")
        self._create_app_settings(app_frame)
        
        # UI tab
        ui_frame = ttk.Frame(notebook)
        notebook.add(ui_frame, text="Interface")
        self._create_ui_settings(ui_frame)
        
        # Calculation tab
        calc_frame = ttk.Frame(notebook)
        notebook.add(calc_frame, text="Calculation")
        self._create_calc_settings(calc_frame)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")
        
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right", padx=(10, 0))
        ttk.Button(button_frame, text="Reset to Defaults", command=self._reset_defaults).pack(side="right", padx=(10, 0))
        ttk.Button(button_frame, text="Apply", command=self._apply_settings).pack(side="right")
    
    def _create_app_settings(self, parent):
        """Create application settings"""
        frame = ttk.LabelFrame(parent, text="Application Settings", padding="10")
        frame.pack(fill="x", pady=5)
        
        ttk.Label(frame, text="Window Title:").grid(row=0, column=0, sticky="w", pady=5)
        self.title_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.title_var, width=40).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        ttk.Label(frame, text="Default Window Size:").grid(row=1, column=0, sticky="w", pady=5)
        self.geometry_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.geometry_var, width=20).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=5)
        
        self.debug_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Enable debug mode", variable=self.debug_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
        
        frame.columnconfigure(1, weight=1)
    
    def _create_ui_settings(self, parent):
        """Create UI settings"""
        frame = ttk.LabelFrame(parent, text="User Interface", padding="10")
        frame.pack(fill="x", pady=5)
        
        ttk.Label(frame, text="Font Size:").grid(row=0, column=0, sticky="w", pady=5)
        self.font_size_var = tk.StringVar()
        font_combo = ttk.Combobox(frame, textvariable=self.font_size_var, values=["8", "9", "10", "11", "12", "14"], width=10)
        font_combo.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=5)
        
        self.tooltips_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Show tooltips", variable=self.tooltips_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        
        self.auto_save_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Auto-save settings", variable=self.auto_save_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
    
    def _create_calc_settings(self, parent):
        """Create calculation settings"""
        frame = ttk.LabelFrame(parent, text="Calculation Settings", padding="10")
        frame.pack(fill="x", pady=5)
        
        ttk.Label(frame, text="Decimal Places:").grid(row=0, column=0, sticky="w", pady=5)
        self.decimal_var = tk.StringVar()
        decimal_combo = ttk.Combobox(frame, textvariable=self.decimal_var, values=["0", "1", "2", "3", "4"], width=10)
        decimal_combo.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=5)
        
        ttk.Label(frame, text="Cache Size:").grid(row=1, column=0, sticky="w", pady=5)
        self.cache_size_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.cache_size_var, width=15).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=5)
        
        self.cache_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Enable performance cache", variable=self.cache_enabled_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
        
        self.perf_logging_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Performance logging", variable=self.perf_logging_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=5)
    
    def _load_current_settings(self):
        """Load current settings into dialog"""
        # App settings
        self.title_var.set(self.config_manager.get("app", "title", ""))
        self.geometry_var.set(self.config_manager.get("app", "geometry", "1300x900"))
        self.debug_var.set(self.config_manager.get("app", "debug_mode", False))
        
        # UI settings
        self.font_size_var.set(str(self.config_manager.get("ui", "font_size", 10)))
        self.tooltips_var.set(self.config_manager.get("ui", "show_tooltips", True))
        self.auto_save_var.set(self.config_manager.get("ui", "auto_save_settings", True))
        
        # Calculation settings
        self.decimal_var.set(str(self.config_manager.get("calculation", "decimal_places", 2)))
        self.cache_size_var.set(str(self.config_manager.get("calculation", "cache_size", 128)))
        self.cache_enabled_var.set(self.config_manager.get("calculation", "cache_enabled", True))
        self.perf_logging_var.set(self.config_manager.get("calculation", "performance_logging", True))
    
    def _apply_settings(self):
        """Apply settings and close dialog"""
        try:
            # Validate and apply app settings
            self.config_manager.set("app", "title", self.title_var.get())
            self.config_manager.set("app", "geometry", self.geometry_var.get())
            self.config_manager.set("app", "debug_mode", self.debug_var.get())
            
            # Validate and apply UI settings
            self.config_manager.set("ui", "font_size", int(self.font_size_var.get()))
            self.config_manager.set("ui", "show_tooltips", self.tooltips_var.get())
            self.config_manager.set("ui", "auto_save_settings", self.auto_save_var.get())
            
            # Validate and apply calculation settings
            self.config_manager.set("calculation", "decimal_places", int(self.decimal_var.get()))
            self.config_manager.set("calculation", "cache_size", int(self.cache_size_var.get()))
            self.config_manager.set("calculation", "cache_enabled", self.cache_enabled_var.get())
            self.config_manager.set("calculation", "performance_logging", self.perf_logging_var.get())
            
            # Save configuration
            if self.config_manager.save_config():
                messagebox.showinfo("Settings", "Settings saved successfully.\nRestart the application to apply all changes.", parent=self)
            else:
                messagebox.showerror("Settings", "Failed to save settings.", parent=self)
            
            self.destroy()
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Please check your input values:\n{e}", parent=self)
    
    def _reset_defaults(self):
        """Reset to default settings"""
        if messagebox.askyesno("Reset Settings", "Reset all settings to defaults?", parent=self):
            self.config_manager.reset_to_defaults()
            self._load_current_settings()
    
    def _center_window(self):
        """Center dialog on parent"""
        self.update_idletasks()
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        x = parent_x + (parent_width // 2) - (self.winfo_width() // 2)
        y = parent_y + (parent_height // 2) - (self.winfo_height() // 2)
        
        self.geometry(f"+{x}+{y}")


def main():
    """Main application entry point"""
    try:
        app = SalaryCalculatorApp()
        app.mainloop()
    except Exception as e:
        logging.exception("Application failed to start")
        messagebox.showerror("Startup Error", f"Failed to start application:\n{e}")


if __name__ == "__main__":
    main()