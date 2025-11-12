# MEDITEK 2FA Authentication Bypass Tool

This tool allows you to capture browser authentication state (including cookies and tokens) after manually completing 2FA login, then reuse that state to bypass 2FA in automated tests or future sessions.

## Prerequisites

Install required dependencies:

```bash
pip install playwright colorama
playwright install chromium
```

## Quick Start Guide

### Step 1: Capture Authentication State

Run this command to capture your authentication after manual login:

```bash
python auth_capture.py --capture
```

**What happens:**
1. A browser window will open
2. Manually log in with your credentials
3. Complete the Microsoft 2FA verification
4. Wait for the main application page to load
5. Return to the terminal and press ENTER
6. The authentication state will be saved to `auth_states/` folder

**Important:** The captured authentication is valid for 24 hours.

### Step 2: Use Saved Authentication

Run this command to open an authenticated browser session without login:

```bash
python used_script.py
```

**What happens:**
1. The script will prompt you for the path to your auth JSON file
   - Default location: `./auth_states/auth_state_test_chromium_latest.json`
2. Select your preferred browser (Chromium, Firefox, or Webkit)
3. Optionally provide a custom URL or use the default
4. Browser opens with you already logged in - no 2FA needed!

## Common Issues and Solutions

### Issue: "Authentication state has EXPIRED"

**Error message:**
```
WARNING - Saved auth state has expired (expired at 2025-11-10 10:46:48.597347)
No valid auth state found. Please run capture first.
```

**Solution:** Your authentication has expired (valid for 24 hours). Recapture it:
```bash
python auth_capture.py --capture
```

### Issue: "No saved auth state found"

**Solution:** You haven't captured authentication yet. Run:
```bash
python auth_capture.py --capture
```

## Advanced Usage

### Capture for Different Environments

```bash
# Test environment (default)
python auth_capture.py --capture --env test

# Pre-production environment
python auth_capture.py --capture --env preprod

# Production environment
python auth_capture.py --capture --env prod
```

### Capture with Different Browsers

```bash
# Chromium (default)
python auth_capture.py --capture --browser chromium

# Firefox
python auth_capture.py --capture --browser firefox

# Webkit (Safari)
python auth_capture.py --capture --browser webkit
```

### Capture for Custom URL

```bash
python auth_capture.py --capture --url https://your-custom-url.com
```

### Test Saved Authentication

Run a quick test to verify your saved auth works:

```bash
python auth_capture.py --test
```

## Project Structure

```
skipp_2FA_auth/
├── auth_capture.py         # Main script to capture authentication
├── used_script.py          # Script to use saved authentication
├── auth_states/            # Folder containing saved auth files
│   └── auth_state_test_chromium_latest.json
├── auth_capture.log        # Capture script logs
├── used_script.log         # Usage script logs
└── README.md              # This file
```

## How It Works

1. **Capture Phase:** Opens a browser where you manually log in and complete 2FA. The script captures all cookies, tokens, and session data.

2. **Storage:** Authentication data is saved as JSON files with:
   - Cookies (including session cookies)
   - Local storage data
   - Session storage data
   - Authentication tokens
   - Metadata (capture time, expiration time)

3. **Reuse Phase:** Loads the saved authentication state into a new browser session, bypassing the need for login and 2FA.

## Security Notes

- Authentication files contain sensitive session data
- Files are valid for 24 hours by default
- Keep auth files secure and do not commit them to version control
- Add `auth_states/` to your `.gitignore`

## Troubleshooting

**Browser doesn't open:**
- Make sure Playwright browsers are installed: `playwright install`

**Authentication doesn't work:**
- The session may have been invalidated on the server side
- Recapture authentication with `python auth_capture.py --capture`

**Script shows errors:**
- Check log files: `auth_capture.log` or `used_script.log`
- Ensure all dependencies are installed

## Support

For issues or questions, check the log files for detailed error messages.
