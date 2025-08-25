"""
Streamlit Web App for Pilot Salary Calculator
"""
import streamlit as st
import pandas as pd
import io
import pickle
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

# Import our modules
from config import SalaryConfig
from models import PilotProfile, BonusInfo, MissingAirportError
from services import AirportService, SalaryCalculatorService, RosterParser
from utils import setup_logging
from export import ReportExporter

# Initialize services
@st.cache_resource
def init_services():
    """Initialize services with caching"""
    airport_service = AirportService()
    calculator_service = SalaryCalculatorService(airport_service)
    roster_parser = RosterParser()
    exporter = ReportExporter()
    return airport_service, calculator_service, roster_parser, exporter

def main():
    """Main Streamlit app"""
    st.set_page_config(
        page_title="Pilot Salary Calculator",
        page_icon="✈️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state early to prevent mobile upload issues
    if 'file_upload_key' not in st.session_state:
        st.session_state.file_upload_key = 0
    if 'upload_error_count' not in st.session_state:
        st.session_state.upload_error_count = 0
    if 'last_upload_method' not in st.session_state:
        st.session_state.last_upload_method = "File Upload"
    
    # Add JavaScript to handle mobile file upload issues
    st.markdown("""
    <script>
    // Enhanced mobile compatibility script
    window.addEventListener('load', function() {
        // Longer delay for slower mobile browsers
        setTimeout(function() {
            // Ensure SessionInfo is initialized
            if (window.parent && window.parent.streamlit) {
                console.log('Streamlit SessionInfo check completed');
                
                // Additional mobile-specific fixes
                const fileInputs = document.querySelectorAll('input[type="file"]');
                fileInputs.forEach(function(input) {
                    // Add mobile-specific event handlers
                    input.addEventListener('touchstart', function() {
                        console.log('Mobile file input touched');
                    });
                    
                    // Handle file selection changes more robustly
                    input.addEventListener('change', function(e) {
                        if (e.target.files && e.target.files.length > 0) {
                            console.log('File selected:', e.target.files[0].name);
                        }
                    });
                });
            }
        }, 1000); // Increased timeout for mobile
    });
    </script>
    """, unsafe_allow_html=True)
    
    st.title("✈️ Advanced Pilot Salary Calculator v2.0")
    st.markdown("---")
    
    # Initialize services
    airport_service, calculator_service, roster_parser, exporter = init_services()
    
    # Sidebar for inputs
    with st.sidebar:
        st.header("Configuration")
        
        # Position selection
        position = st.selectbox(
            "Position:",
            options=list(SalaryConfig.POSITIONS.keys()),
            index=1  # Default to FO
        )
        
        # Extra position
        extra_position = st.selectbox(
            "Extra Position:",
            options=list(SalaryConfig.EXTRA_POSITIONS.keys()),
            index=0  # Default to None
        )
        
        # Contract type
        contract_type = st.selectbox(
            "Contract:",
            options=list(SalaryConfig.CONTRACTS.keys()),
            index=0  # Default to Standard
        )
        
        # Home base
        home_base = st.selectbox(
            "Home Base:",
            options=["MXP"],
            index=0
        )
        
        # SNC units
        snc_units = st.number_input(
            "SNC Units:",
            min_value=0,
            max_value=100,
            value=0,
            step=1
        )
        
        # Debug mode with mobile diagnostics
        debug_mode = st.checkbox("Debug Mode", value=False)
        
        if debug_mode:
            st.markdown("**Debug Information:**")
            st.write(f"Upload errors encountered: {st.session_state.upload_error_count}")
            st.write(f"Current upload method: {st.session_state.last_upload_method}")
            st.write(f"File upload key: {st.session_state.file_upload_key}")
            
            # Add mobile detection info
            st.markdown("**Device Detection:**")
            st.markdown("""
            <div id="device-info"></div>
            <script>
            const userAgent = navigator.userAgent;
            const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(userAgent);
            const deviceInfo = {
                userAgent: userAgent,
                isMobile: isMobile,
                platform: navigator.platform,
                cookieEnabled: navigator.cookieEnabled,
                onLine: navigator.onLine,
                language: navigator.language
            };
            document.getElementById('device-info').innerHTML = 
                '<pre>' + JSON.stringify(deviceInfo, null, 2) + '</pre>';
            </script>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.header("File Upload")
        
        # Add mobile fallback option with smart suggestions
        upload_options = ["File Upload", "📱 Copy & Paste Text", "📧 Email Method", "📷 Photo of File"]
        
        # Auto-suggest text input if there have been upload errors
        if st.session_state.upload_error_count >= 2:
            default_index = 1  # Copy & Paste
            st.warning("⚠️ Multiple upload issues detected. Copy & Paste is recommended for mobile devices.")
        else:
            default_index = 0 if st.session_state.last_upload_method == "File Upload" else 1
            
        upload_method = st.radio(
            "Upload Method:",
            upload_options,
            index=default_index,
            help="Multiple ways to get your roster data into the app"
        )
        
        # Remember the chosen method
        st.session_state.last_upload_method = upload_method
        
        uploaded_file = None
        manual_text = None
        
        if upload_method == "File Upload":
            # Add a button to reset file uploader if needed
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("🔄 Reset", help="Reset file uploader if stuck"):
                    st.session_state.file_upload_key += 1
                    st.rerun()
            
            with col1:
                # Mobile-optimized file upload with better compatibility
                try:
                    # Add mobile-specific HTML to improve file picker
                    st.markdown("""
                    <style>
                    /* Mobile file input improvements */
                    .stFileUploader > div > div > div > div {
                        font-size: 16px !important; /* Prevents iOS zoom on focus */
                    }
                    .stFileUploader input[type="file"] {
                        -webkit-appearance: none;
                        appearance: none;
                    }
                    /* Better touch targets for mobile */
                    .stFileUploader > div > div {
                        min-height: 50px;
                        padding: 10px;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    uploaded_file = st.file_uploader(
                        "📁 Upload Roster File (.txt)",
                        type=['txt'],
                        help="Tap here to select your roster text file from your device",
                        accept_multiple_files=False,
                        key=f"roster_file_upload_{st.session_state.file_upload_key}",
                        disabled=False
                    )
                except Exception as e:
                    st.session_state.upload_error_count += 1
                    st.error("File uploader initialization failed. Please try the text input method.")
                    if debug_mode:
                        st.exception(e)
                    uploaded_file = None
                    
                # Add mobile-specific file input as fallback
                if uploaded_file is None:
                    st.markdown("**Alternative Mobile File Input:**")
                    st.markdown("""
                    <div id="mobile-file-input">
                        <input type="file" id="mobile-file" accept=".txt,text/plain" 
                               style="width: 100%; padding: 10px; font-size: 16px; 
                                      border: 2px dashed #ccc; border-radius: 5px;
                                      cursor: pointer;" 
                               onchange="handleMobileFile(this)">
                        <div id="file-content" style="display: none;"></div>
                    </div>
                    
                    <script>
                    function handleMobileFile(input) {
                        const file = input.files[0];
                        if (file && file.type === 'text/plain') {
                            const reader = new FileReader();
                            reader.onload = function(e) {
                                const content = e.target.result;
                                document.getElementById('file-content').innerText = content;
                                
                                // Try to trigger Streamlit update
                                const event = new CustomEvent('mobile-file-loaded', {
                                    detail: { content: content, fileName: file.name }
                                });
                                window.dispatchEvent(event);
                                
                                // Show success message
                                alert('File loaded! Please switch to "📱 Copy & Paste Text" and paste the content.');
                            };
                            reader.readAsText(file);
                        } else {
                            alert('Please select a .txt file');
                        }
                    }
                    </script>
                    """, unsafe_allow_html=True)
                    
                    st.info("💡 If file upload doesn't work, try the alternative input above or use Copy & Paste method.")
                    
                    # Add drag and drop zone for mobile
                    st.markdown("**📱 Mobile Drag & Drop Zone:**")
                    st.markdown("""
                    <div id="drop-zone" 
                         style="width: 100%; height: 80px; border: 2px dashed #007bff; 
                                border-radius: 10px; text-align: center; padding: 20px; 
                                margin: 10px 0; cursor: pointer; background: #f8f9fa;"
                         onclick="document.getElementById('mobile-file').click()"
                         ondrop="dropHandler(event);" 
                         ondragover="dragOverHandler(event);">
                        <p style="margin: 0; color: #007bff; font-weight: bold;">
                            📁 Tap here to select file or drag & drop
                        </p>
                        <p style="margin: 5px 0 0 0; color: #6c757d; font-size: 14px;">
                            Supports .txt files only
                        </p>
                    </div>
                    
                    <script>
                    function dragOverHandler(ev) {
                        ev.preventDefault();
                        ev.currentTarget.style.background = '#e7f3ff';
                    }
                    
                    function dropHandler(ev) {
                        ev.preventDefault();
                        ev.currentTarget.style.background = '#f8f9fa';
                        
                        const files = ev.dataTransfer.files;
                        if (files.length > 0) {
                            const file = files[0];
                            if (file.type === 'text/plain' || file.name.endsWith('.txt')) {
                                handleMobileFile({files: [file]});
                            } else {
                                alert('Please drop a .txt file');
                            }
                        }
                    }
                    </script>
                    """, unsafe_allow_html=True)
        elif upload_method == "📱 Copy & Paste Text":
            # Enhanced mobile copy/paste with detailed instructions
            st.markdown("### 📱 Mobile Copy & Paste Guide")
            
            # Create tabs for different platforms
            ios_tab, android_tab = st.tabs(["📱 iOS (iPhone/iPad)", "🤖 Android"])
            
            with ios_tab:
                st.markdown("""
                **Step-by-Step for iOS:**
                1. **Open your roster file** in Files app, Notes, Mail, or any text app
                2. **Select all text** using one of these methods:
                   - **Triple-tap** anywhere in the text to select all
                   - **Double-tap** a word, then drag the blue handles to select all
                   - **Long press** and select "Select All" from popup menu
                3. **Copy the text**:
                   - **3-finger pinch** gesture (iOS 13+) - pinch inward with thumb + 2 fingers
                   - OR tap "Copy" from the popup menu
                4. **Switch back** to this app in your browser
                5. **Paste below**:
                   - **3-finger pinch out** gesture to paste
                   - OR long press in text area and select "Paste"
                """)
            
            with android_tab:
                st.markdown("""
                **Step-by-Step for Android:**
                1. **Open your roster file** in any text app (Gmail, Drive, Notes, etc.)
                2. **Select all text**:
                   - **Long press** on the text until selection handles appear
                   - Drag handles to select all text, or tap "Select All"
                   - Use **Ctrl+A** if using external keyboard
                3. **Copy the text**:
                   - Tap the **Copy** icon or "Copy" from menu
                   - Text is saved to clipboard
                4. **Switch back** to this app in your browser
                5. **Paste below**:
                   - **Long press** in the text area below
                   - Tap "Paste" when it appears
                """)
            
            st.markdown("---")
            
            # Enhanced text area with better mobile support
            manual_text = st.text_area(
                "📝 Paste your roster text here:",
                height=300,
                help="Long press and select Paste, or use 3-finger pinch out on iOS",
                key="mobile_text_input",
                placeholder="Your roster text will appear here after pasting...\n\nTip: Make sure you copied ALL the text from your roster file."
            )
            
            # Add paste verification
            if manual_text and len(manual_text.strip()) > 0:
                word_count = len(manual_text.split())
                line_count = len(manual_text.splitlines())
                st.success(f"✅ Text pasted successfully! ({word_count} words, {line_count} lines)")
                
                # Quick validation
                if "flight" in manual_text.lower() or "roster" in manual_text.lower() or any(char.isdigit() for char in manual_text):
                    st.info("✈️ Looks like roster data - ready to process!")
                else:
                    st.warning("⚠️ This doesn't look like roster data. Make sure you copied the right text.")
                    
        elif upload_method == "📧 Email Method":
            st.markdown("### 📧 Email Method")
            st.info("📧 **Coming Soon**: Send your roster file to a special email address and get the text extracted automatically.")
            st.markdown("""
            **How it will work:**
            1. Email your roster file to: `roster@yourdomain.com`
            2. Get a reply with the extracted text
            3. Copy and paste the text here
            
            For now, please use the **Copy & Paste** method above.
            """)
            manual_text = None
            
        elif upload_method == "📷 Photo of File":
            st.markdown("### 📷 Photo Text Recognition")
            st.info("📷 **Coming Soon**: Take a photo of your roster file and extract the text automatically.")
            st.markdown("""
            **How it will work:**
            1. Take a clear photo of your roster text
            2. Upload the photo here
            3. AI will extract the text automatically
            
            For now, please use the **Copy & Paste** method above.
            """)
            manual_text = None
    
    # Debug info for mobile
    if debug_mode:
        st.write("Debug: File uploader state:", uploaded_file is not None)
        if uploaded_file is not None:
            st.write(f"Debug: File object type: {type(uploaded_file)}")
            st.write(f"Debug: File attributes: {dir(uploaded_file)}")
    
    # Main content area
    if uploaded_file is not None or (manual_text and len(manual_text.strip()) > 0):
        file_content = None
        
        if uploaded_file is not None:
            # Display file info for mobile debugging
            st.info(f"📁 File: {uploaded_file.name} ({uploaded_file.size} bytes)")
            
            # Additional mobile debugging
            st.write("✅ File successfully uploaded!")
            if debug_mode:
                st.write(f"Debug: File type: {uploaded_file.type}")
                st.write(f"Debug: File size: {uploaded_file.size}")
            
            try:
                # Enhanced mobile-compatible file reading with multiple fallback methods
                file_bytes = None
                file_content = None
                
                # Method 1: Try getvalue() first (best for mobile)
                try:
                    file_bytes = uploaded_file.getvalue()
                    if debug_mode:
                        st.info(f"Method 1 (getvalue): Got {len(file_bytes)} bytes")
                except Exception as e:
                    if debug_mode:
                        st.warning(f"Method 1 failed: {str(e)}")
                
                # Method 2: Try read() if getvalue() failed
                if file_bytes is None or len(file_bytes) == 0:
                    try:
                        uploaded_file.seek(0)  # Reset file pointer
                        file_bytes = uploaded_file.read()
                        if debug_mode:
                            st.info(f"Method 2 (read): Got {len(file_bytes)} bytes")
                    except Exception as e:
                        if debug_mode:
                            st.warning(f"Method 2 failed: {str(e)}")
                
                # Check if we got any data
                if file_bytes is None or len(file_bytes) == 0:
                    st.session_state.upload_error_count += 1
                    st.error("The uploaded file appears to be empty or couldn't be read. Please try:")
                    st.markdown("""
                    - Check that the file isn't corrupted
                    - Try uploading again 
                    - Use the 'Text Input (Mobile Fallback)' option instead
                    - Use the 🔄 Reset button if upload seems stuck
                    """)
                    return
                
                # Enhanced encoding detection with more options
                encoding_attempts = [
                    'utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 
                    'windows-1252', 'iso-8859-1', 'ascii'
                ]
                
                for encoding in encoding_attempts:
                    try:
                        file_content = file_bytes.decode(encoding)
                        # Validate that we got reasonable text content
                        if len(file_content.strip()) > 0:
                            if debug_mode:
                                st.success(f"File loaded successfully using {encoding} encoding")
                            break
                        else:
                            if debug_mode:
                                st.warning(f"Encoding {encoding} produced empty content")
                    except UnicodeDecodeError:
                        if debug_mode:
                            st.warning(f"Failed to decode with {encoding}")
                        continue
                    except Exception as e:
                        if debug_mode:
                            st.warning(f"Error with {encoding}: {str(e)}")
                        continue
                
                if file_content is None or len(file_content.strip()) == 0:
                    st.session_state.upload_error_count += 1
                    st.error("Could not decode the file content. Please try:")
                    st.markdown("""
                    - Save your file as UTF-8 encoding
                    - Use the 'Text Input (Mobile Fallback)' option
                    - Copy and paste the file content manually
                    """)
                    return
                    
            except Exception as e:
                st.session_state.upload_error_count += 1
                st.error(f"Error reading file: {str(e)}")
                st.info("💡 Try the 'Text Input (Mobile Fallback)' option as an alternative")
                if debug_mode:
                    st.exception(e)
                return
                
        else:
            # Handle manual text input
            file_content = manual_text.strip()
            st.info("📝 Text input received")
            st.write("✅ Content successfully loaded!")
        
        # Validate file content
        if len(file_content.strip()) == 0:
            st.error("The content appears to be empty. Please check your input.")
            return
        
        # Reset error count on successful file loading
        if st.session_state.upload_error_count > 0:
            st.session_state.upload_error_count = 0
        
        try:
            
            # Create pilot profile
            profile = PilotProfile(
                position=position,
                extra_position=extra_position,
                contract_type=contract_type,
                home_base=home_base,
                snc_units=int(snc_units),
                debug_mode=debug_mode
            )
            
            # Parse roster
            with st.spinner("Parsing roster data..."):
                roster_data = roster_parser.parse_roster_text(file_content)
            
            # Calculate salary
            with st.spinner("Calculating salary..."):
                (detailed_df, grouped_df, ido_bonuses, night_stop_bonus, 
                 extra_diaria_days, salary_calc) = calculator_service.calculate_salary(
                    roster_data, profile
                )
            
            if detailed_df.empty:
                st.warning("No valid flight data found in roster.")
                return
            
            # Display results
            display_results(detailed_df, grouped_df, ido_bonuses, extra_diaria_days, 
                          salary_calc, profile, night_stop_bonus)
            
            # Export options
            st.markdown("---")
            st.header("📥 Export Options")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📊 Export to CSV", use_container_width=True):
                    csv_data = export_to_csv(detailed_df, grouped_df, salary_calc)
                    st.download_button(
                        label="Download CSV",
                        data=csv_data,
                        file_name=f"salary_report_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
            
            with col2:
                if exporter.excel_available:
                    if st.button("📋 Export to Excel", use_container_width=True):
                        excel_data = export_to_excel(detailed_df, grouped_df, salary_calc, 
                                                   ido_bonuses, extra_diaria_days, profile)
                        if excel_data:
                            st.download_button(
                                label="Download Excel",
                                data=excel_data,
                                file_name=f"salary_report_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                else:
                    st.button("📋 Excel Not Available", disabled=True, use_container_width=True)
            
            with col3:
                if st.button("📄 Export to Text", use_container_width=True):
                    text_data = export_to_text(grouped_df, salary_calc, profile)
                    st.download_button(
                        label="Download Text",
                        data=text_data,
                        file_name=f"salary_report_{datetime.now().strftime('%Y%m%d')}.txt",
                        mime="text/plain"
                    )
            
        except MissingAirportError as e:
            st.error(f"Missing airport coordinates for: {e.iata_code}")
            
            # Show manual input form for missing airport
            st.warning("This airport is not in our database. Please add coordinates manually:")
            
            col1, col2 = st.columns(2)
            with col1:
                lat = st.number_input(f"Latitude for {e.iata_code}:", value=0.0, format="%.6f", step=0.000001, key=f"lat_{e.iata_code}")
            with col2:
                lon = st.number_input(f"Longitude for {e.iata_code}:", value=0.0, format="%.6f", step=0.000001, key=f"lon_{e.iata_code}")
            
            if st.button(f"Add {e.iata_code} coordinates and recalculate", type="primary"):
                if lat != 0.0 or lon != 0.0:
                    # Add airport to service temporarily
                    airport_service.add_airport(e.iata_code, lat, lon)
                    st.success(f"Added {e.iata_code}: ({lat}, {lon})")
                    st.rerun()  # Restart the app to recalculate
                else:
                    st.error("Please enter valid coordinates (not 0,0)")
            else:
                st.info("💡 **Tip**: You can find airport coordinates on websites like:")
                st.markdown("- [OpenFlights](https://openflights.org/data.html)")
                st.markdown("- [World Airport Codes](https://www.world-airport-codes.com/)")
                st.markdown("- [AirNav](https://www.airnav.com/airports/)")
        
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            if debug_mode:
                st.exception(e)
    
    else:
        # Welcome message with mobile-specific instructions
        st.info("👈 Please upload a roster file from the sidebar to begin calculation")
        
        # Add mobile-specific help with dynamic suggestions
        st.markdown("### 📱 Mobile Upload Tips")
        
        if st.session_state.upload_error_count > 0:
            st.markdown("**⚠️ You're experiencing upload issues. Try these solutions:**")
        
        st.markdown("""
        **📱 Copy & Paste Method (RECOMMENDED):**
        - Choose "📱 Copy & Paste Text" option above
        - Follow the iOS or Android specific instructions
        - No file upload needed - just copy and paste!
        
        **File Upload Method (Desktop/Laptop):**
        - **File Selection**: Tap the upload area and select "Choose Files" or "Browse Files"
        - **File Location**: Files may be in Downloads, Documents, Google Drive, or Files app
        - **File Format**: Ensure your file is a .txt file (not .doc, .docx, or .pdf)
        - **File Size**: Check that the file is not empty (should show file size after selection)
        - **Reset Button**: If upload gets stuck, use the 🔄 Reset button
        
        **Mobile Touch Gestures:**
        - **iOS**: Use 3-finger pinch to copy, 3-finger pinch out to paste
        - **Android**: Long press to select, tap Copy/Paste from menu
        - **Select All**: Triple-tap (iOS) or long press + "Select All" (Android)
        
        **Common Mobile Issues:**
        - Safari on iOS: Try Chrome or Firefox instead
        - Android: Ensure file permissions are granted
        - File uploads often fail on mobile - use Copy & Paste instead!
        """)
        
        # Add browser-specific tips if there have been errors
        if st.session_state.upload_error_count >= 2:
            st.markdown("""
            **🚨 Multiple Issues Detected - Try These Steps:**
            1. Switch to "Text Input (Mobile Fallback)" method ← **RECOMMENDED**
            2. Try a different browser (Chrome, Firefox, Safari)
            3. Check your internet connection stability
            4. Restart the browser and try again
            5. Contact support if issues persist
            """)
        
        # Display sample information
        st.markdown("## 📖 How to Use")
        st.markdown("""
        1. **Configure your profile** in the sidebar (position, contract, etc.)
        2. **Upload your roster file** (.txt format)
        3. **View results** in the main area with detailed breakdowns
        4. **Export** your results in various formats
        """)
        
        st.markdown("## ✨ Features")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            - **Multiple Positions**: SO, FO, SFO, NewCPT, CPT
            - **Contract Variations**: Standard, FRV, Part-time
            - **Bonus Calculations**: IDO, Night stops, SNC
            """)
        
        with col2:
            st.markdown("""
            - **Tax Calculations**: Italian IRPEF system
            - **Export Options**: CSV, Excel, Text formats
            - **Flight Analysis**: Distance-based sectors
            """)

def display_results(detailed_df: pd.DataFrame, grouped_df: pd.DataFrame, 
                   ido_bonuses: List[BonusInfo], extra_diaria_days: Set[str],
                   salary_calc, profile: PilotProfile, night_stop_bonus: float):
    """Display calculation results"""
    
    # Get month/year from data
    first_date = grouped_df['Data'].iloc[0]
    if isinstance(first_date, str):
        month_year = pd.to_datetime(first_date).strftime('%B %Y').upper()
    else:
        month_year = first_date.strftime('%B %Y').upper()
    
    # Calculate diaria for main display
    _, _, _, diaria, _ = SalaryConfig.POSITIONS[profile.position]
    working_days = len(grouped_df[grouped_df['Attività'].str.contains("Flight|Positioning|Training|Rest Day", na=False)])
    extra_diaria_count = len(extra_diaria_days)
    total_diaria_days = working_days + extra_diaria_count
    total_diaria = total_diaria_days * diaria
    total_in_payslip = salary_calc.net_estimated + total_diaria
    
    # Summary metrics
    st.header(f"💰 Salary Summary for {month_year}")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Gross Total", f"€{salary_calc.gross_total:,.2f}")
    
    with col2:
        st.metric("Total in Payslip", f"€{total_in_payslip:,.2f}", help="Net salary + tax-free diaria")
    
    with col3:
        operational_sectors = detailed_df['Settori Operativi'].sum()
        st.metric("Operational Sectors", f"{operational_sectors:.1f}")
    
    with col4:
        st.metric("Working Days", f"{working_days}")
    
    # Detailed breakdown
    st.markdown("---")
    
    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Daily Summary", "✈️ Flight Details", "💳 Salary Breakdown"])
    
    with tab1:
        st.subheader("Daily Activity Summary")
        
        # Prepare display dataframe
        display_df = grouped_df.copy()
        display_df['Data'] = pd.to_datetime(display_df['Data']).dt.strftime('%Y-%m-%d')
        display_df['Settori'] = display_df['Settori'].round(2)
        display_df['Guadagno (€)'] = display_df['Guadagno (€)'].round(2)
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )
    
    with tab2:
        st.subheader("Detailed Flight Information")
        
        # Filter to show only flights
        flight_df = detailed_df[detailed_df['Settori'] > 0].copy()
        flight_df['Data'] = pd.to_datetime(flight_df['Data']).dt.strftime('%Y-%m-%d')
        flight_df['Distanza'] = flight_df['Distanza'].round(0)
        flight_df['Settori'] = flight_df['Settori'].round(2)
        flight_df['Guadagno (€)'] = flight_df['Guadagno (€)'].round(2)
        
        # Add type column
        flight_df['Type'] = flight_df['IsPositioning'].apply(lambda x: 'Positioning' if x else 'Operational')
        
        st.dataframe(
            flight_df[['Data', 'Volo', 'Partenza', 'Arrivo', 'Distanza', 'Settori', 'Guadagno (€)', 'Type']],
            use_container_width=True,
            hide_index=True
        )
    
    with tab3:
        st.subheader("Complete Salary Breakdown")
        
        # Use already calculated diaria values
        
        # Create breakdown
        breakdown_data = []
        
        # Base components
        if salary_calc.gross_total > 0:
            base_salary = (salary_calc.gross_total - salary_calc.operational_sectors_earnings - 
                          salary_calc.positioning_earnings - salary_calc.frv_bonus - 
                          salary_calc.snc_compensation - salary_calc.vacation_compensation - 
                          night_stop_bonus - sum(b.amount for b in ido_bonuses))
            breakdown_data.append(["Base Salary + Allowances", f"€{base_salary:,.2f}"])
        
        if salary_calc.operational_sectors_earnings > 0:
            breakdown_data.append(["Operational Sectors", f"€{salary_calc.operational_sectors_earnings:,.2f}"])
        
        if salary_calc.positioning_earnings > 0:
            breakdown_data.append(["Positioning Flights", f"€{salary_calc.positioning_earnings:,.2f}"])
        
        if salary_calc.frv_bonus > 0:
            breakdown_data.append(["FRV Contract Bonus (11%)", f"€{salary_calc.frv_bonus:,.2f}"])
        
        if salary_calc.snc_compensation > 0:
            breakdown_data.append(["SNC Compensation", f"€{salary_calc.snc_compensation:,.2f}"])
        
        if salary_calc.vacation_compensation > 0:
            breakdown_data.append([f"Vacation Pay ({salary_calc.vacation_days} days)", f"€{salary_calc.vacation_compensation:,.2f}"])
        
        if night_stop_bonus > 0:
            breakdown_data.append(["Night Stop Bonus", f"€{night_stop_bonus:,.2f}"])
        
        if ido_bonuses:
            total_ido = sum(b.amount for b in ido_bonuses)
            breakdown_data.append(["IDO Violation Bonus", f"€{total_ido:,.2f}"])
        
        breakdown_data.extend([
            ["", ""],
            ["**GROSS TOTAL**", f"**€{salary_calc.gross_total:,.2f}**"],
            ["", ""],
            ["Social Contributions (INPS)", f"€{-salary_calc.social_contributions:,.2f}"],
            ["Estimated Tax (IRPEF)", f"€{-salary_calc.estimated_tax:,.2f}"],
            ["Diaria (Tax-free)", f"€{total_diaria:,.2f}"],
            ["", ""],
            ["**TOTAL IN PAYSLIP**", f"**€{total_in_payslip:,.2f}**"]
        ])
        
        # Display as DataFrame
        breakdown_df = pd.DataFrame(breakdown_data, columns=["Component", "Amount"])
        st.dataframe(breakdown_df, use_container_width=True, hide_index=True)

def export_to_csv(detailed_df: pd.DataFrame, grouped_df: pd.DataFrame, salary_calc) -> str:
    """Export results to CSV format"""
    output = io.StringIO()
    
    # Write summary
    output.write("=== SALARY SUMMARY ===\n")
    output.write(f"Gross Total,{salary_calc.gross_total:.2f}\n")
    output.write(f"Net Estimated,{salary_calc.net_estimated:.2f}\n")
    output.write("\n=== DAILY SUMMARY ===\n")
    
    # Write grouped data
    grouped_df.to_csv(output, index=False)
    
    return output.getvalue()

def export_to_excel(detailed_df: pd.DataFrame, grouped_df: pd.DataFrame, salary_calc,
                   ido_bonuses: List[BonusInfo], extra_diaria_days: Set[str], 
                   profile: PilotProfile) -> bytes:
    """Export results to Excel format"""
    output = io.BytesIO()
    
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = {
                'Component': ['Gross Total', 'Net Estimated', 'Operational Sectors', 'Positioning'],
                'Amount': [salary_calc.gross_total, salary_calc.net_estimated, 
                          salary_calc.operational_sectors_earnings, salary_calc.positioning_earnings]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            
            # Daily data
            grouped_df.to_excel(writer, sheet_name='Daily Summary', index=False)
            
            # Flight details
            detailed_df.to_excel(writer, sheet_name='Flight Details', index=False)
        
        return output.getvalue()
    
    except Exception:
        return None

def export_to_text(grouped_df: pd.DataFrame, salary_calc, profile: PilotProfile) -> str:
    """Export results to text format"""
    output = []
    
    first_date = grouped_df['Data'].iloc[0]
    if isinstance(first_date, str):
        month_year = pd.to_datetime(first_date).strftime('%B %Y').upper()
    else:
        month_year = first_date.strftime('%B %Y').upper()
    
    output.append(f"===== SALARY REPORT FOR {month_year} =====")
    output.append(f"Position: {profile.position}")
    output.append(f"Contract: {profile.contract_type}")
    output.append("")
    output.append(f"Gross Total: €{salary_calc.gross_total:,.2f}")
    output.append(f"Net Estimated: €{salary_calc.net_estimated:,.2f}")
    output.append("")
    output.append("=== DAILY BREAKDOWN ===")
    
    for _, row in grouped_df.iterrows():
        date_str = row['Data'].strftime('%Y-%m-%d')
        output.append(f"{date_str}: {row['Attività']} - €{row['Guadagno (€)']:.2f}")
    
    return "\n".join(output)

if __name__ == "__main__":
    main()