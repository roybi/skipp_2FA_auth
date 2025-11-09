"""
MEDITEK Authentication State Loader

Loads saved authentication state and opens an authenticated browser session.
No login or 2FA required - uses pre-captured authentication data.

Usage:
    python used_script.py
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from colorama import Fore, Style, init
from playwright.async_api import Browser, BrowserContext, async_playwright

init(autoreset=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("used_script.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class AuthStateLoader:
    """Loads and uses saved authentication state."""

    def prompt_for_json_path(self) -> Path:
        """Prompt user for authentication JSON file path."""
        print(f"\n{Fore.CYAN}{'=' * 70}")
        print(f"{Fore.CYAN}MEDITEK Authentication State Loader")
        print(f"{Fore.CYAN}{'=' * 70}\n")

        while True:
            print(f"{Fore.YELLOW}Please provide the path to your authentication JSON file:")
            print(f"{Fore.WHITE}Example: ./auth_states/auth_state_test_chromium_latest.json\n")

            file_path = input(f"{Fore.GREEN}➜ File path: {Style.RESET_ALL}").strip().strip('"').strip("'")
            path = Path(file_path)

            if not path.exists():
                print(f"{Fore.RED}❌ File not found: {file_path}\n")
                continue

            if not path.is_file():
                print(f"{Fore.RED}❌ Path is not a file: {file_path}\n")
                continue

            if path.suffix != ".json":
                print(f"{Fore.RED}❌ File must be a JSON file (.json extension)\n")
                continue

            print(f"{Fore.GREEN}✅ File found: {path.absolute()}\n")
            return path

    def load_auth_state(self, json_path: Path) -> Optional[dict]:
        """Load and validate authentication state from JSON file."""
        print(f"{Fore.YELLOW}📂 Loading authentication state...")

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            if "storage_state" not in state_data:
                print(f"{Fore.RED}❌ Invalid JSON file: missing 'storage_state' field")
                return None

            if "metadata" not in state_data:
                print(f"{Fore.YELLOW}⚠️  Warning: No metadata found in file (may be old format)")
            else:
                # Check expiration
                if "expires_at" in state_data["metadata"]:
                    expires_at = datetime.fromisoformat(state_data["metadata"]["expires_at"])
                    if datetime.now() > expires_at:
                        print(f"{Fore.RED}❌ Authentication state has EXPIRED (expired at {expires_at})")
                        print(f"{Fore.YELLOW}Please run auth_capture.py again to create a new auth file.")
                        return None

                    print(f"{Fore.GREEN}✅ Auth state is valid until: {expires_at}")

                if "captured_at" in state_data["metadata"]:
                    captured_at = datetime.fromisoformat(state_data["metadata"]["captured_at"])
                    print(f"{Fore.WHITE}📅 Captured at: {captured_at}")

            cookies_count = len(state_data["storage_state"].get("cookies", []))
            print(f"{Fore.WHITE}🍪 Cookies loaded: {cookies_count}")

            if "tokens" in state_data:
                tokens_count = len(state_data["tokens"])
                print(f"{Fore.WHITE}🔑 Tokens loaded: {tokens_count}")

            logger.info(f"Successfully loaded auth state from {json_path}")
            return state_data

        except json.JSONDecodeError as e:
            print(f"{Fore.RED}❌ Invalid JSON file: {e}")
            return None
        except Exception as e:
            print(f"{Fore.RED}❌ Error loading file: {e}")
            logger.error(f"Error loading auth state: {e}", exc_info=True)
            return None

    async def navigate_to_application(self, context: BrowserContext, url: str = None):
        """Navigate to application using authenticated session."""
        page = await context.new_page()

        if url is None:
            url = "https://meditik.test.medical.idf.il/"

        print(f"\n{Fore.YELLOW}🚀 Navigating to: {url}")
        print(f"{Fore.GREEN}✨ Using saved authentication (NO LOGIN REQUIRED!)\n")

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            page_title = await page.title()
            current_url = page.url

            print(f"{Fore.GREEN}{'=' * 70}")
            print(f"{Fore.GREEN}✅ SUCCESS! You are now logged in!")
            print(f"{Fore.GREEN}{'=' * 70}")
            print(f"{Fore.WHITE}📄 Page Title: {Fore.CYAN}{page_title}")
            print(f"{Fore.WHITE}🔗 Current URL: {Fore.CYAN}{current_url}")
            print(f"\n{Fore.YELLOW}{'=' * 70}")
            print(f"{Fore.YELLOW}Browser is open and authenticated.")
            print(f"{Fore.YELLOW}Press Ctrl+C in this terminal to close.")
            print(f"{Fore.YELLOW}{'=' * 70}\n")

            # Keep browser open
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print(f"\n{Fore.CYAN}Closing browser...")

        except Exception as e:
            print(f"{Fore.RED}❌ Error navigating to application: {e}")
            logger.error(f"Navigation error: {e}", exc_info=True)


async def main():
    """Main function to load and use saved authentication state."""
    loader = AuthStateLoader()

    try:
        # Get JSON file path
        json_path = loader.prompt_for_json_path()

        # Load authentication state
        state_data = loader.load_auth_state(json_path)

        if not state_data:
            print(f"\n{Fore.RED}Failed to load authentication state. Exiting.")
            sys.exit(1)

        # Ask for browser preference
        print(f"\n{Fore.CYAN}Which browser would you like to use?")
        print(f"{Fore.WHITE}1. Chromium (recommended)")
        print(f"{Fore.WHITE}2. Firefox")
        print(f"{Fore.WHITE}3. Webkit (Safari)")

        browser_choice = input(f"\n{Fore.GREEN}➜ Enter choice [1-3] (default: 1): {Style.RESET_ALL}").strip()

        browser_map = {"1": "chromium", "2": "firefox", "3": "webkit", "": "chromium"}
        browser_type = browser_map.get(browser_choice, "chromium")

        print(f"{Fore.GREEN}✅ Selected browser: {browser_type}")

        # Ask for custom URL
        print(f"\n{Fore.CYAN}Application URL:")
        print(f"{Fore.WHITE}Press Enter to use default: https://meditik.test.medical.idf.il/")

        custom_url = input(f"{Fore.GREEN}➜ URL: {Style.RESET_ALL}").strip()
        app_url = custom_url if custom_url else None

        # Create authenticated browser and navigate
        async with async_playwright() as p:
            browser_launcher = {
                "chromium": p.chromium,
                "firefox": p.firefox,
                "webkit": p.webkit,
            }

            browser = await browser_launcher[browser_type].launch(
                headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"] if browser_type == "chromium" else [],
            )

            context = await browser.new_context(
                storage_state=state_data["storage_state"],
                viewport={"width": 1920, "height": 1080},
                locale="he-IL",
                timezone_id="Asia/Jerusalem",
            )

            print(f"{Fore.GREEN}✅ Browser launched with authenticated session")

            await loader.navigate_to_application(context, app_url)

            await context.close()
            await browser.close()

        print(f"\n{Fore.GREEN}✅ Session closed successfully. Goodbye!")

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️  Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Fore.RED}❌ Error: {str(e)}")
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
