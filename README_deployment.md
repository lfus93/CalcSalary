# Pilot Salary Calculator - Web App Deployment

## Local Testing

To run the app locally:

```bash
# Activate virtual environment
venv\Scripts\activate

# Run the Streamlit app
streamlit run streamlit_app.py
```

The app will be available at: http://localhost:8501

## Online Deployment Options

### 1. Streamlit Cloud (Recommended - Free)

1. **Push to GitHub**:
   - Create a new GitHub repository
   - Upload these files:
     - `streamlit_app.py`
     - `config.py`
     - `models.py`
     - `services.py`
     - `utils.py`
     - `export.py`
     - `cord_airport.csv`
     - `requirements_web.txt`
     - `.streamlit/config.toml`

2. **Deploy on Streamlit Cloud**:
   - Go to https://share.streamlit.io/
   - Connect your GitHub account
   - Select your repository
   - Set main file: `streamlit_app.py`
   - Set requirements file: `requirements_web.txt`
   - Deploy!

### 2. Heroku (Free Tier Available)

1. Create `Procfile`:
   ```
   web: streamlit run streamlit_app.py --server.port=$PORT --server.address=0.0.0.0
   ```

2. Deploy to Heroku using Git or GitHub integration

### 3. Railway (Modern Alternative)

1. Connect GitHub repository
2. Railway auto-detects Streamlit apps
3. Automatic deployment from GitHub pushes

## Files Required for Deployment

**Essential files:**
- `streamlit_app.py` (main app)
- `config.py` (salary configuration)
- `models.py` (data models)
- `services.py` (business logic)
- `utils.py` (utility functions)
- `export.py` (export functionality)
- `cord_airport.csv` (airport database)
- `requirements_web.txt` (dependencies)

**Optional but recommended:**
- `.streamlit/config.toml` (app configuration)
- `README.md` (documentation)

## Environment Variables (if needed)

For production deployment, you might want to set:
- `STREAMLIT_SERVER_HEADLESS=true`
- `STREAMLIT_SERVER_PORT=8501`
- `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`

## Features of the Web App

- ✅ **File Upload**: Drag & drop roster files
- ✅ **Real-time Calculation**: Instant results
- ✅ **Export Options**: CSV, Excel, Text formats
- ✅ **Responsive Design**: Works on mobile and desktop
- ✅ **No Installation Required**: Runs in any web browser
- ✅ **Multi-user Support**: Each user gets their own session

## Performance Notes

- Airport service is cached for better performance
- Large roster files are processed efficiently
- Results are displayed in organized tabs
- Export functions generate files on-demand