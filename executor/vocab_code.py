from playwright.sync_api import Page
import time

# ======================
#  Core vocabulary actions
# ======================

def click_element(page: Page, selector: str = None, text_hint: str = None, timeout: int = 5000):
    """
    Click on a button, link, or any clickable element.

    Args:
        page: Active Playwright page.
        selector: CSS selector (preferred).
        text_hint: Text-based locator (fallback, e.g., "Submit").
        timeout: Max wait time (ms) for element to appear.
    """
    if not selector and not text_hint:
        raise ValueError("You must provide either a CSS selector or a text_hint.")

    try:
        if selector:
            print(f"🔍 Clicking element via selector: {selector}")
            page.wait_for_selector(selector, timeout=timeout)
            page.click(selector)
        else:
            print(f"🔍 Clicking element via text: {text_hint}")
            page.get_by_text(text_hint, exact=True).click(timeout=timeout)
        print("✅ Click successful")
    except Exception as e:
        print(f"❌ Failed to click element ({selector or text_hint}): {e}")


def set_value(page: Page, selector: str, value: str, timeout: int = 5000):
    """
    Type a given value into an input field.

    Args:
        page: Active Playwright page.
        selector: CSS selector for the input element.
        value: Text to type.
        timeout: Max wait time (ms) for field to appear.
    """
    try:
        print(f"⌨️ Setting value '{value}' in {selector}")
        page.wait_for_selector(selector, timeout=timeout)
        page.fill(selector, value)
        print("✅ Value set successfully")
    except Exception as e:
        print(f"❌ Failed to set value in {selector}: {e}")


def scroll_page(page: Page, direction: str = "down", amount: int = 500):
    """
    Scroll the page vertically or horizontally.

    Args:
        page: Active Playwright page.
        direction: 'up', 'down', 'left', 'right'.
        amount: Number of pixels to scroll.
    """
    dx, dy = 0, 0
    if direction == "down":
        dy = amount
    elif direction == "up":
        dy = -amount
    elif direction == "left":
        dx = -amount
    elif direction == "right":
        dx = amount
    else:
        raise ValueError(f"Invalid direction: {direction}")

    try:
        print(f"🧭 Scrolling {direction} by {amount}px")
        page.mouse.wheel(dx, dy)
        print("✅ Scroll complete")
    except Exception as e:
        print(f"❌ Failed to scroll: {e}")


def wait_seconds(duration: float):
    """
    Pause execution for a given number of seconds.

    Args:
        duration: Time in seconds.
    """
    print(f"⏳ Waiting {duration}s")
    time.sleep(duration)
    print("✅ Wait complete")


def hover_element(page: Page, selector: str, timeout: int = 5000):
    """
    Hover over an element to reveal tooltips or dropdowns.

    Args:
        page: Active Playwright page.
        selector: CSS selector for the element to hover.
        timeout: Max wait time (ms) for element to appear.
    """
    try:
        print(f"🖱️ Hovering over {selector}")
        page.wait_for_selector(selector, timeout=timeout)
        page.hover(selector)
        print("✅ Hover successful")
    except Exception as e:
        print(f"❌ Failed to hover on {selector}: {e}")


def navigate_to(page: Page, url: str, timeout: int = 10000):
    """
    Navigate to a specific URL.

    Args:
        page: Active Playwright page.
        url: Target URL.
        timeout: Max wait time (ms) for navigation to finish.
    """
    try:
        print(f"🌐 Navigating to {url}")
        page.goto(url, timeout=timeout)
        print("✅ Navigation successful")
    except Exception as e:
        print(f"❌ Failed to navigate to {url}: {e}")


def extract_text(page: Page, selector: str, timeout: int = 5000) -> str:
    """
    Extract and return text content from a given element.

    Args:
        page: Active Playwright page.
        selector: CSS selector for the element.
        timeout: Max wait time (ms) for element to appear.

    Returns:
        str: The extracted text, or an empty string on failure.
    """
    try:
        print(f"📋 Extracting text from {selector}")
        page.wait_for_selector(selector, timeout=timeout)
        text = page.inner_text(selector)
        print(f"✅ Extracted text: {text[:80]}{'...' if len(text) > 80 else ''}")
        return text
    except Exception as e:
        print(f"❌ Failed to extract text from {selector}: {e}")
        return ""


def run_script(page: Page, code: str):
    """
    Execute inline JavaScript within the current page context.

    Args:
        page: Active Playwright page.
        code: JavaScript code to execute.

    Returns:
        Any: The result of the executed script.
    """
    try:
        print(f"🧠 Running inline JS:\n{code}")
        result = page.evaluate(code)
        print(f"✅ Script executed successfully — result: {result}")
        return result
    except Exception as e:
        print(f"❌ Failed to run JS: {e}")
        return None


def confirm_action(message: str) -> bool:
    """
    Ask the user for confirmation before continuing.

    Args:
        message: Confirmation message.

    Returns:
        bool: True if user confirms, False otherwise.
    """
    print(f"⚠️  CONFIRMATION: {message}")
    resp = input("Proceed? (y/n): ").strip().lower()
    confirmed = resp in ["y", "yes"]
    print("✅ Continuing..." if confirmed else "🛑 Cancelled by user")
    return confirmed


def chain_actions(page: Page, actions: list):
    """
    Execute a sequence of actions in order.

    Args:
        page: Active Playwright page.
        actions: List of action dictionaries.
    """
    print("🔗 Executing chained actions...")
    for a in actions:
        action_type = a.get("type")
        if action_type == "click":
            click_element(page, a.get("selector"), a.get("text_hint"))
        elif action_type == "set_value":
            set_value(page, a.get("selector"), a.get("value"))
        elif action_type == "scroll":
            scroll_page(page, a.get("direction"), a.get("amount"))
        elif action_type == "wait":
            wait_seconds(a.get("duration", 1))
        elif action_type == "hover":
            hover_element(page, a.get("selector"))
        elif action_type == "navigate":
            navigate_to(page, a.get("url"))
        elif action_type == "extract":
            extract_text(page, a.get("selector"))
        elif action_type == "run_script":
            run_script(page, a.get("code"))
        else:
            print(f"⚠️ Unknown action type in chain: {action_type}")
    print("✅ Chain complete")