"""
================================================================================
MEDITEK Authentication State Capture Tool - Microsoft 2FA Bypass Solution
================================================================================

WHAT THIS SCRIPT DOES:
----------------------
1. Opens a real browser window where you manually log in (including 2FA)
2. Captures ALL authentication data after successful login:
   - Cookies (including session cookies)
   - Local Storage data
   - Session Storage data
   - Authentication tokens (Bearer, JWT, etc.)
   - Browser context (user agent, viewport, etc.)
3. Saves everything to a JSON file
4. This file can be loaded in ANY test (local or remote) to skip login

HOW IT CAPTURES:
----------------
The script uses Playwright's storage_state API which captures:
- All HTTP cookies from all domains
- All localStorage items
- All sessionStorage items
- Origin-specific data

After manual authentication, it extracts:
- Microsoft authentication cookies (like .AspNet.Cookies, MSAL tokens)
- OAuth/OIDC tokens (access_token, id_token, refresh_token)
- Any custom application tokens
- Session identifiers

HOW TO USE THE SAVED FILE:
---------------------------
1. Run this capture script once per environment (test/preprod)
2. Complete manual login with 2FA when browser opens
3. Script saves file: auth_states/auth_state_test_chromium_latest.json
4. In your test scripts, load this file to bypass login completely
5. Tests will start directly at authenticated pages

FILE STRUCTURE:
---------------
The JSON file contains:
{
    "storage_state": {
        "cookies": [...],        # All browser cookies
        "origins": [...]         # localStorage and sessionStorage per origin
    },
    "metadata": {
        "captured_at": "...",    # When captured
        "expires_at": "...",     # When it expires (24 hours default)
        "url": "...",           # URL after login
        "title": "..."          # Page title after login
    },
    "tokens": {                 # Extracted auth tokens
        "access_token": "...",
        "id_token": "...",
        "msal.idtoken": "..."
    }
}

================================================================================
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from colorama import Fore, init
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

# Initialize colorama for colored terminal output
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("auth_capture.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class AuthStateManager:
    """
    Manages authentication state capture and reuse for MEDITEK test automation.
    Handles Microsoft 2FA by capturing session after manual authentication.
    """

    def __init__(self, state_dir: str = "./auth_states"):
        """
        Initialize the authentication state manager.

        Args:
            state_dir: Directory to store authentication state files
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        logger.info(f"State directory: {self.state_dir.absolute()}")

    async def capture_auth_state(
        self,
        url: str,
        environment: str = "test",
        browser_type: str = "chromium",
        headless: bool = False,
        timeout: int = 300000,  # 5 minutes for manual auth
    ) -> Dict:
        """
        Launch browser for manual authentication and capture state.

        CAPTURE PROCESS:
        1. Opens browser at your application URL
        2. You manually log in with username/password
        3. Complete Microsoft 2FA verification
        4. Once fully logged in, press ENTER in terminal
        5. Script captures all auth data and saves to JSON

        Args:
            url: The MEDITEK application URL to authenticate to
            environment: Environment name (test/preprod/prod)
            browser_type: Browser to use (chromium/firefox/webkit)
            headless: Whether to run in headless mode (must be False for manual auth)
            timeout: Maximum time to wait for authentication (ms)

        Returns:
            Dictionary containing the captured authentication state
        """
        print(f"\n{Fore.CYAN}{'=' * 70}")
        print(f"{Fore.CYAN}Starting Authentication Capture for MEDITEK")
        print(f"{Fore.CYAN}{'=' * 70}\n")

        async with async_playwright() as p:
            # Launch browser
            browser = await self._launch_browser(p, browser_type, headless)

            # Create context with specific settings
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="he-IL",  # Hebrew locale for Israeli users
                timezone_id="Asia/Jerusalem",
                # Important: Accept all cookies for Microsoft auth
                accept_downloads=True,
                ignore_https_errors=False,  # Don't ignore for production
            )

            # Enable request/response logging for debugging
            context.on("request", lambda request: self._log_request(request))
            context.on("response", lambda response: self._log_response(response))

            page = await context.new_page()

            logger.info(f"Opening {url} for manual authentication...")
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Display instructions
            self._display_instructions(url, environment)

            # Wait for user to complete authentication
            input(
                f"\n{Fore.GREEN}➜ Press ENTER after completing authentication and 2FA..."
            )

            # Capture complete browser state
            print(f"\n{Fore.YELLOW}📸 Capturing authentication state...")
            state_data = await self._capture_complete_state(context, page)

            # Save state to file
            filename = self._save_state(state_data, environment, browser_type)

            # Display success message with usage instructions
            self._display_success(filename, environment, browser_type)

            await context.close()
            await browser.close()

            return state_data

    def _display_instructions(self, url: str, environment: str):
        """Display clear instructions for manual authentication."""
        print(f"\n{Fore.YELLOW}{'=' * 70}")
        print(
            f"{Fore.YELLOW}MANUAL AUTHENTICATION REQUIRED - {environment.upper()} Environment"
        )
        print(f"{Fore.YELLOW}{'=' * 70}")
        print(f"\n{Fore.WHITE}Follow these steps:")
        print(f"{Fore.GREEN}1. ✓ Browser opened at: {Fore.CYAN}{url}")
        print(f"{Fore.GREEN}2. → Enter your username and password")
        print(f"{Fore.GREEN}3. → Complete Microsoft 2FA verification")
        print(f"{Fore.GREEN}4. → Wait for the main application page to load")
        print(f"{Fore.GREEN}5. → Verify you are fully logged in")
        print(f"{Fore.GREEN}6. → Return to this terminal")
        print(
            f"\n{Fore.YELLOW}⚠️  DO NOT close the browser! The script will do it automatically."
        )
        print(f"{Fore.YELLOW}{'=' * 70}")

    def _display_success(self, filename: str, environment: str, browser_type: str):
        """Display success message with usage instructions."""
        print(f"\n{Fore.GREEN}{'=' * 70}")
        print(f"{Fore.GREEN}✅ SUCCESS! Authentication State Captured")
        print(f"{Fore.GREEN}{'=' * 70}\n")
        print(f"{Fore.WHITE}📁 File saved to: {Fore.CYAN}{filename}")
        print(f"{Fore.WHITE}🔑 Environment: {Fore.CYAN}{environment}")
        print(f"{Fore.WHITE}🌐 Browser: {Fore.CYAN}{browser_type}")
        print(f"\n{Fore.YELLOW}HOW TO USE THIS FILE IN YOUR TESTS:")
        print(f"{Fore.WHITE}1. Copy this file to your test machine (if different)")
        print(f"{Fore.WHITE}2. In your test script, use:")
        print(f"{Fore.CYAN}   auth_manager = AuthStateManager()")
        print(
            f"{Fore.CYAN}   state = await auth_manager.load_auth_state('{environment}', '{browser_type}')"
        )
        print(
            f"{Fore.CYAN}   context = await auth_manager.create_authenticated_context(...)"
        )
        print(f"\n{Fore.GREEN}Your tests can now skip login completely! 🚀")
        print(f"{Fore.GREEN}{'=' * 70}\n")

    def _log_request(self, request):
        """Log HTTP requests for debugging."""
        url = request.url
        # Log only authentication-related requests
        if any(
            pattern in url.lower()
            for pattern in ["login", "auth", "token", "microsoft", "oauth"]
        ):
            logger.debug(f"→ Auth Request: {request.method} {url}")

    def _log_response(self, response):
        """Log HTTP responses for debugging."""
        url = response.url
        # Log authentication responses
        if any(
            pattern in url.lower()
            for pattern in ["login", "auth", "token", "microsoft", "oauth"]
        ):
            logger.debug(f"← Auth Response: {response.status} {url}")
            if response.status >= 400:
                logger.warning(f"Auth Error: {response.status} at {url}")

    async def _capture_complete_state(
        self, context: BrowserContext, page: Page
    ) -> Dict:
        """
        Capture all authentication-related data from the browser.

        WHAT IS CAPTURED:
        - All cookies (including Microsoft auth cookies)
        - localStorage (including MSAL tokens)
        - sessionStorage (including temporary tokens)
        - Bearer tokens, JWT tokens
        - OAuth tokens (access_token, id_token, refresh_token)

        Args:
            context: Browser context
            page: Current page

        Returns:
            Complete authentication state
        """
        # Get storage state (cookies, localStorage, sessionStorage)
        storage_state = await context.storage_state()

        # Log captured data for debugging
        logger.info(f"Captured {len(storage_state.get('cookies', []))} cookies")

        # Get additional browser data
        state_data = {
            "storage_state": storage_state,
            "metadata": {
                "captured_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(hours=24)).isoformat(),
                "url": page.url,
                "title": await page.title(),
                "environment": page.url,  # Store the base URL for validation
            },
            "headers": {"user_agent": await page.evaluate("navigator.userAgent")},
        }

        # Capture any bearer tokens from localStorage/sessionStorage
        tokens = await self._extract_tokens(page)
        if tokens:
            state_data["tokens"] = tokens
            logger.info(f"Captured {len(tokens)} authentication tokens")

        # Log some key cookies for verification (without exposing values)
        for cookie in storage_state.get("cookies", []):
            if any(
                pattern in cookie["name"].lower()
                for pattern in [".aspnet", "msal", "auth", "session"]
            ):
                logger.info(
                    f"Found auth cookie: {cookie['name']} (domain: {cookie['domain']})"
                )

        return state_data

    async def _extract_tokens(self, page: Page) -> Dict[str, str]:
        """
        Extract authentication tokens from browser storage.

        TOKENS EXTRACTED:
        - Microsoft authentication tokens (MSAL)
        - OAuth/OIDC tokens
        - Custom application tokens
        - JWT tokens
        - Session tokens

        Args:
            page: Current page

        Returns:
            Dictionary of extracted tokens
        """
        tokens = {}

        # Extract from localStorage
        local_storage = await page.evaluate("""
            () => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }
        """)

        # Extract from sessionStorage
        session_storage = await page.evaluate("""
            () => {
                const items = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    items[key] = sessionStorage.getItem(key);
                }
                return items;
            }
        """)

        # Microsoft and common token patterns
        token_keys = [
            "access_token",
            "id_token",
            "refresh_token",  # OAuth standard
            "msal",
            "adal",  # Microsoft Auth Library
            "bearer",
            "jwt",
            "auth",  # Common patterns
            "token",
            "session",  # Generic
            ".authority",
            ".idtoken",
            ".accesstoken",  # MSAL specific
        ]

        # Extract matching tokens
        for storage_dict in [local_storage, session_storage]:
            for key, value in storage_dict.items():
                if any(token_key in key.lower() for token_key in token_keys):
                    tokens[key] = value
                    # Log token discovery without exposing value
                    logger.info(
                        f"Found token: {key[:30]}... (length: {len(str(value))})"
                    )

        return tokens

    def _save_state(self, state_data: Dict, environment: str, browser_type: str) -> str:
        """
        Save authentication state to JSON file.

        FILE NAMING:
        - Timestamped: auth_state_test_chromium_20240315_143022.json
        - Latest: auth_state_test_chromium_latest.json (for easy reference)

        Args:
            state_data: Authentication state data
            environment: Environment name
            browser_type: Browser type

        Returns:
            Path to saved file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"auth_state_{environment}_{browser_type}_{timestamp}.json"
        filepath = self.state_dir / filename

        # Save with timestamp
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)

        # Also save as "latest" for easy reference
        latest_filename = f"auth_state_{environment}_{browser_type}_latest.json"
        latest_filepath = self.state_dir / latest_filename
        with open(latest_filepath, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)

        logger.info(f"State saved to: {filepath}")
        logger.info(f"Latest link updated: {latest_filepath}")

        return str(filepath.absolute())

    async def load_auth_state(
        self, environment: str = "test", browser_type: str = "chromium"
    ) -> Optional[Dict]:
        """
        Load saved authentication state from file.

        HOW TO USE:
        1. This method loads the saved JSON file
        2. Checks if it's not expired (24 hour default)
        3. Returns the complete state for use in tests

        Args:
            environment: Environment name
            browser_type: Browser type

        Returns:
            Authentication state data or None if not found/expired
        """
        filename = f"auth_state_{environment}_{browser_type}_latest.json"
        filepath = self.state_dir / filename

        if not filepath.exists():
            logger.warning(f"No saved auth state found at {filepath}")
            logger.info("Run capture_auth_state() first to create auth file")
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            state_data = json.load(f)

        # Check if state is expired
        expires_at = datetime.fromisoformat(state_data["metadata"]["expires_at"])
        if datetime.now() > expires_at:
            logger.warning(f"Saved auth state has expired (expired at {expires_at})")
            logger.info("Run capture_auth_state() again to refresh")
            return None

        logger.info(f"Loaded valid auth state from {filepath}")
        logger.info(f"State expires at: {expires_at}")
        return state_data

    async def create_authenticated_context(
        self,
        playwright_instance,
        state_data: Dict,
        browser_type: str = "chromium",
        headless: bool = True,
    ) -> tuple[Browser, BrowserContext]:
        """
        Create a browser context with pre-authenticated state.

        WHAT THIS DOES:
        1. Creates new browser instance
        2. Loads all cookies from saved state
        3. Loads all localStorage/sessionStorage data
        4. Returns ready-to-use authenticated browser context
        5. Your test can navigate directly to protected pages!

        Args:
            playwright_instance: Playwright instance
            state_data: Authentication state data (from load_auth_state)
            browser_type: Browser type
            headless: Whether to run headless (can be True with saved state!)

        Returns:
            Tuple of (browser, context) - both authenticated and ready
        """
        browser = await self._launch_browser(
            playwright_instance,
            browser_type,
            headless=headless,  # Can run headless with saved state!
        )

        # Create context with saved storage state - this is the magic!
        context = await browser.new_context(
            storage_state=state_data["storage_state"],  # Load all auth data
            viewport={"width": 1920, "height": 1080},
            locale="he-IL",
            timezone_id="Asia/Jerusalem",
        )

        logger.info(
            f"Created authenticated context with {len(state_data['storage_state'].get('cookies', []))} cookies"
        )

        return browser, context

    async def _launch_browser(
        self, playwright, browser_type: str, headless: bool
    ) -> Browser:
        """
        Launch browser with appropriate settings.

        Args:
            playwright: Playwright instance
            browser_type: Type of browser to launch
            headless: Whether to run headless

        Returns:
            Browser instance
        """
        browser_launcher = {
            "chromium": playwright.chromium,
            "firefox": playwright.firefox,
            "webkit": playwright.webkit,
        }

        if browser_type not in browser_launcher:
            raise ValueError(f"Unsupported browser type: {browser_type}")

        browser = await browser_launcher[browser_type].launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
            if browser_type == "chromium"
            else [],
        )

        logger.info(f"Launched {browser_type} browser (headless={headless})")
        return browser


# ================================================================================
# MAIN CAPTURE SCRIPT
# ================================================================================


async def capture_authentication(url: str = None, environment: str = "test", browser: str = "chromium"):
    """
    Main function to capture authentication state.
    Run this once per environment to capture auth state.

    Args:
        url: Application URL (defaults to MEDITEK test URL if not provided)
        environment: Environment name (test/preprod/prod)
        browser: Browser type (chromium/firefox/webkit)
    """

    # Use provided URL or fall back to default MEDITEK URL
    if url is None:
        url = "https://meditik.test.medical.idf.il/"

    print(f"\n{Fore.CYAN}MEDITEK Authentication State Capture Tool")
    print(f"{Fore.CYAN}Version 1.0 - Microsoft 2FA Support")
    print(f"{Fore.WHITE}{'=' * 50}\n")

    # Initialize manager
    auth_manager = AuthStateManager()

    try:
        # Capture authentication state
        state = await auth_manager.capture_auth_state(
            url=url,
            environment=environment,
            browser_type=browser,
            headless=False,  # MUST be False for manual authentication
        )

        # Display summary
        print(f"\n{Fore.GREEN}✅ Authentication state captured successfully!")
        print(f"{Fore.WHITE}📊 Summary:")
        print(f"  • Cookies captured: {len(state['storage_state']['cookies'])}")
        if "tokens" in state:
            print(f"  • Tokens captured: {len(state['tokens'])}")
        print("  • Valid for: 24 hours")
        print(f"  • Environment: {environment}")

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️  Capture cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Fore.RED}❌ Error: {str(e)}")
        logger.error(f"Failed to capture authentication state: {e}", exc_info=True)
        sys.exit(1)


# ================================================================================
# EXAMPLE TEST SCRIPT - How to use the saved authentication
# ================================================================================


async def example_test_with_saved_auth():
    """
    EXAMPLE: How to use saved authentication state in your test scripts.
    This shows how your actual test would skip login completely.
    """
    print(f"\n{Fore.CYAN}Example Test Using Saved Authentication")
    print(f"{Fore.CYAN}{'=' * 50}\n")

    auth_manager = AuthStateManager()

    # Load saved authentication state
    state_data = await auth_manager.load_auth_state(
        environment="test", browser_type="chromium"
    )

    if not state_data:
        print(f"{Fore.RED}❌ No valid auth state found. Please run capture first.")
        return

    async with async_playwright() as p:
        # Create authenticated browser context
        browser, context = await auth_manager.create_authenticated_context(
            p,
            state_data,
            "chromium",
            headless=True,  # Can be headless!
        )

        page = await context.new_page()

        # Navigate directly to protected area - NO LOGIN NEEDED!
        print(f"{Fore.GREEN}➜ Navigating directly to dashboard (skipping login)...")
        await page.goto("https://meditik.test.medical.idf.il/dashboard")

        # Verify we're logged in
        page_title = await page.title()
        print(f"{Fore.GREEN}✅ Successfully accessed: {page_title}")
        print(f"{Fore.GREEN}✅ No login or 2FA required!")

        # Your test logic here...
        # await page.click("button#some-button")
        # await page.fill("input#some-input", "test data")
        # etc...

        await context.close()
        await browser.close()


# ================================================================================
# CI/CD INTEGRATION EXAMPLE
# ================================================================================


async def ci_cd_test_runner():
    """
    Example of how to integrate this in CI/CD pipeline.
    The auth file should be stored securely and copied to the CI/CD agent.
    """
    auth_manager = AuthStateManager()

    # In CI/CD, the auth file would be:
    # 1. Stored in secure storage (Azure Key Vault, etc.)
    # 2. Downloaded to the agent at runtime
    # 3. Used for all tests
    # 4. Refreshed periodically (daily)

    state = await auth_manager.load_auth_state("test", "chromium")
    if not state:
        raise Exception(
            "Auth state not found in CI/CD. Please update the stored auth file."
        )

    # Run your test suite with authenticated state...
    async with async_playwright() as p:
        browser, context = await auth_manager.create_authenticated_context(
            p, state, "chromium", headless=True
        )

        # Run all your tests here with authenticated context
        # No login needed for any test!

        await context.close()
        await browser.close()


# ================================================================================
# ENTRY POINT
# ================================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MEDITEK Authentication State Manager")
    parser.add_argument("--capture", action="store_true", help="Capture new auth state")
    parser.add_argument(
        "--test", action="store_true", help="Run example test with saved auth"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Application URL",
        default="https://meditik.test.medical.idf.il/",
    )
    parser.add_argument(
        "--env", type=str, choices=["test", "preprod", "prod"], default="test"
    )
    parser.add_argument(
        "--browser",
        type=str,
        choices=["chromium", "firefox", "webkit"],
        default="chromium",
    )

    args = parser.parse_args()

    if args.capture:
        # Run the capture tool with command-line arguments
        asyncio.run(capture_authentication(url=args.url, environment=args.env, browser=args.browser))
    elif args.test:
        # Run example test
        asyncio.run(example_test_with_saved_auth())
    else:
        # Default: show help
        parser.print_help()
        print(f"\n{Fore.YELLOW}Examples:")
        print(f"{Fore.WHITE}  Capture auth:  python auth_capture.py --capture")
        print(f"{Fore.WHITE}  Test with auth: python auth_capture.py --test")
