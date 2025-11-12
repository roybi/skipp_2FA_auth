"""
MEDITEK Authentication State Capture Tool

Captures browser authentication state (cookies, tokens, storage) after manual login
to bypass 2FA in automated tests. Run once per environment, then reuse the saved state.

Usage:
    python auth_capture.py --capture [--url URL] [--env ENV] [--browser BROWSER]
    python auth_capture.py --test
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

init(autoreset=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("auth_capture.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class AuthStateManager:
    """Manages authentication state capture and reuse for test automation."""

    def __init__(self, state_dir: str = "./auth_states"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        logger.info(f"State directory: {self.state_dir.absolute()}")

    async def capture_auth_state(
        self,
        url: str,
        environment: str = "test",
        browser_type: str = "chromium",
        headless: bool = False,
        timeout: int = 300000,
    ) -> Dict:
        """Launch browser for manual authentication and capture state."""
        print(f"\n{Fore.CYAN}{'=' * 70}")
        print(f"{Fore.CYAN}Starting Authentication Capture for MEDITEK")
        print(f"{Fore.CYAN}{'=' * 70}\n")

        async with async_playwright() as p:
            browser = await self._launch_browser(p, browser_type, headless)

            context = await browser.new_context(
                viewport={"width": 430, "height": 932},
                locale="he-IL",  # Hebrew locale for Israeli users
                timezone_id="Asia/Jerusalem",
                accept_downloads=True,
                ignore_https_errors=False,
            )

            context.on("request", lambda request: self._log_request(request))
            context.on("response", lambda response: self._log_response(response))

            page = await context.new_page()

            logger.info(f"Opening {url} for manual authentication...")
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Set browser zoom to 50% for better visibility
            await page.evaluate("document.body.style.zoom = '0.5'")

            # Display instructions
            self._display_instructions(url, environment)

            input(
                f"\n{Fore.GREEN}➜ Press ENTER after completing authentication and 2FA..."
            )

            print(f"\n{Fore.YELLOW}📸 Capturing authentication state...")
            state_data = await self._capture_complete_state(context, page)

            filename = self._save_state(state_data, environment, browser_type)

            self._display_success(filename, environment, browser_type)

            await context.close()
            await browser.close()

            return state_data

    def _display_instructions(self, url: str, environment: str):
        """Display authentication instructions."""
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
        print(f"{Fore.GREEN}5. → Return to this terminal and press ENTER")
        print(
            f"\n{Fore.YELLOW}⚠️  DO NOT close the browser! The script will do it automatically."
        )
        print(f"{Fore.YELLOW}{'=' * 70}")

    def _display_success(self, filename: str, environment: str, browser_type: str):
        """Display success message."""
        print(f"\n{Fore.GREEN}{'=' * 70}")
        print(f"{Fore.GREEN}✅ SUCCESS! Authentication State Captured")
        print(f"{Fore.GREEN}{'=' * 70}\n")
        print(f"{Fore.WHITE}📁 File saved to: {Fore.CYAN}{filename}")
        print(f"{Fore.WHITE}🔑 Environment: {Fore.CYAN}{environment}")
        print(f"{Fore.WHITE}🌐 Browser: {Fore.CYAN}{browser_type}")
        print(f"\n{Fore.YELLOW}HOW TO USE:")
        print(f"{Fore.CYAN}   auth_manager = AuthStateManager()")
        print(
            f"{Fore.CYAN}   state = await auth_manager.load_auth_state('{environment}', '{browser_type}')"
        )
        print(
            f"{Fore.CYAN}   context = await auth_manager.create_authenticated_context(...)"
        )
        print(f"\n{Fore.GREEN}Your tests can now skip login! 🚀")
        print(f"{Fore.GREEN}{'=' * 70}\n")

    def _log_request(self, request):
        """Log authentication-related requests."""
        url = request.url
        if any(
            p in url.lower() for p in ["login", "auth", "token", "microsoft", "oauth"]
        ):
            logger.debug(f"→ Auth Request: {request.method} {url}")

    def _log_response(self, response):
        """Log authentication responses."""
        url = response.url
        if any(
            p in url.lower() for p in ["login", "auth", "token", "microsoft", "oauth"]
        ):
            logger.debug(f"← Auth Response: {response.status} {url}")
            if response.status >= 400:
                logger.warning(f"Auth Error: {response.status} at {url}")

    async def _capture_complete_state(
        self, context: BrowserContext, page: Page
    ) -> Dict:
        """Capture all authentication data (cookies, storage, tokens)."""
        storage_state = await context.storage_state()

        logger.info(f"Captured {len(storage_state.get('cookies', []))} cookies")

        state_data = {
            "storage_state": storage_state,
            "metadata": {
                "captured_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(hours=48)).isoformat(),
                "url": page.url,
                "title": await page.title(),
                "environment": page.url,
            },
            "headers": {"user_agent": await page.evaluate("navigator.userAgent")},
        }

        tokens = await self._extract_tokens(page)
        if tokens:
            state_data["tokens"] = tokens
            logger.info(f"Captured {len(tokens)} authentication tokens")

        # Log key authentication cookies
        for cookie in storage_state.get("cookies", []):
            if any(
                p in cookie["name"].lower()
                for p in [".aspnet", "msal", "auth", "session"]
            ):
                logger.info(
                    f"Found auth cookie: {cookie['name']} (domain: {cookie['domain']})"
                )

        return state_data

    async def _extract_tokens(self, page: Page) -> Dict[str, str]:
        """Extract authentication tokens from browser storage."""
        tokens = {}

        # Extract localStorage
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

        # Extract sessionStorage
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

        # Token patterns to search for
        token_keys = [
            "access_token",
            "id_token",
            "refresh_token",
            "msal",
            "adal",
            "bearer",
            "jwt",
            "auth",
            "token",
            "session",
            ".authority",
            ".idtoken",
            ".accesstoken",
        ]

        # Extract matching tokens
        for storage_dict in [local_storage, session_storage]:
            for key, value in storage_dict.items():
                if any(token_key in key.lower() for token_key in token_keys):
                    tokens[key] = value
                    logger.info(
                        f"Found token: {key[:30]}... (length: {len(str(value))})"
                    )

        return tokens

    def _save_state(self, state_data: Dict, environment: str, browser_type: str) -> str:
        """Save authentication state to JSON file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"auth_state_{environment}_{browser_type}_{timestamp}.json"
        filepath = self.state_dir / filename

        # Save timestamped version
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)

        # Save as "latest" for easy access
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
        """Load saved authentication state from file."""
        filename = f"auth_state_{environment}_{browser_type}_latest.json"
        filepath = self.state_dir / filename

        if not filepath.exists():
            logger.warning(f"No saved auth state found at {filepath}")
            logger.info("Run capture_auth_state() first to create auth file")
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            state_data = json.load(f)

        # Check expiration
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
        """Create a browser context with pre-authenticated state."""
        browser = await self._launch_browser(
            playwright_instance, browser_type, headless
        )

        context = await browser.new_context(
            storage_state=state_data["storage_state"],  # Load all auth data
            viewport={"width": 430, "height": 932},
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
        """Launch browser with appropriate settings."""
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


async def capture_authentication(
    url: str = None, environment: str = "test", browser: str = "chromium"
):
    """Main function to capture authentication state."""
    if url is None:
        url = "https://meditik.test.medical.idf.il/"

    print(f"\n{Fore.CYAN}MEDITEK Authentication State Capture Tool")
    print(f"{Fore.CYAN}Version 1.0 - Microsoft 2FA Support")
    print(f"{Fore.WHITE}{'=' * 50}\n")

    auth_manager = AuthStateManager()

    try:
        state = await auth_manager.capture_auth_state(
            url=url,
            environment=environment,
            browser_type=browser,
            headless=False,
        )

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


async def example_test_with_saved_auth():
    """Example: How to use saved authentication state in tests."""
    print(f"\n{Fore.CYAN}Example Test Using Saved Authentication")
    print(f"{Fore.CYAN}{'=' * 50}\n")

    auth_manager = AuthStateManager()

    state_data = await auth_manager.load_auth_state(
        environment="test", browser_type="chromium"
    )

    if not state_data:
        print(f"{Fore.RED}❌ No valid auth state found. Please run capture first.")
        return

    async with async_playwright() as p:
        browser, context = await auth_manager.create_authenticated_context(
            p, state_data, "chromium", headless=True
        )

        page = await context.new_page()

        print(f"{Fore.GREEN}➜ Navigating directly to dashboard (skipping login)...")
        await page.goto("https://meditik.test.medical.idf.il/dashboard")

        page_title = await page.title()
        print(f"{Fore.GREEN}✅ Successfully accessed: {page_title}")
        print(f"{Fore.GREEN}✅ No login or 2FA required!")

        await context.close()
        await browser.close()


async def ci_cd_test_runner():
    """Example of CI/CD integration."""
    auth_manager = AuthStateManager()

    state = await auth_manager.load_auth_state("test", "chromium")
    if not state:
        raise Exception(
            "Auth state not found in CI/CD. Please update the stored auth file."
        )

    async with async_playwright() as p:
        browser, context = await auth_manager.create_authenticated_context(
            p, state, "chromium", headless=True
        )

        # Run tests here with authenticated context

        await context.close()
        await browser.close()


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
        asyncio.run(
            capture_authentication(
                url=args.url, environment=args.env, browser=args.browser
            )
        )
    elif args.test:
        asyncio.run(example_test_with_saved_auth())
    else:
        parser.print_help()
        print(f"\n{Fore.YELLOW}Examples:")
        print(f"{Fore.WHITE}  Capture auth:  python auth_capture.py --capture")
        print(f"{Fore.WHITE}  Test with auth: python auth_capture.py --test")
