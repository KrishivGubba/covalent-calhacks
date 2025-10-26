from playwright.sync_api import Page, sync_playwright
import time

from PIL import Image, ImageDraw, ImageFont

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

def move_cursor_to(x: int, y: int, duration: float = 0.0):
    """
    Connect to an existing Chrome instance and move the mouse cursor
    to the specified (x, y) coordinates.

    Args:
        x (int): Target x-coordinate (pixels from left of viewport).
        y (int): Target y-coordinate (pixels from top of viewport).
        duration (float): Optional delay (seconds) for smooth movement.
    """
    try:
        with sync_playwright() as p:
            # Connect to Chrome with remote debugging enabled
            browser = p.chromium.connect_over_cdp("http://localhost:9222")

            if not browser.contexts:
                print("❌ No browser contexts found. Launch Chrome with --remote-debugging-port=9222")
                return

            context = browser.contexts[0]
            if not context.pages:
                print("❌ No open tabs found.")
                return

            page = context.pages[0]
            print(f"🖱️ Connected to: {page.title()} — {page.url}")

            print(f"🎯 Moving cursor to ({x}, {y})")
            if duration > 0:
                steps = max(1, int(duration * 60))
                # Playwright doesn't expose current cursor position,
                # so just simulate smooth movement anyway
                for i in range(steps):
                    page.mouse.move(x, y)
                    time.sleep(duration / steps)
            else:
                page.mouse.move(x, y)
            print("✅ Cursor move complete")

    except Exception as e:
        print(f"❌ Failed to move cursor: {e}")


def click_at(x: int, y: int, delay: float = 0.1):
    """
    Connect to an existing Chrome instance and perform a mouse click
    at the specified (x, y) coordinates within the current tab viewport.

    Args:
        x (int): X-coordinate in pixels (relative to the top-left of viewport).
        y (int): Y-coordinate in pixels.
        delay (float): Optional delay (seconds) between press and release.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")

            if not browser.contexts:
                print("❌ No browser contexts found. Launch Chrome with --remote-debugging-port=9222")
                return

            context = browser.contexts[0]
            if not context.pages:
                print("❌ No open tabs found.")
                return

            page = context.pages[0]
            print(f"🖱️ Connected to: {page.title()} — {page.url}")
            print(f"🎯 Clicking at ({x}, {y})")

            page.mouse.move(x, y)
            page.mouse.down()
            time.sleep(delay)
            page.mouse.up()

            print("✅ Click complete")

    except Exception as e:
        print(f"❌ Failed to click at ({x}, {y}): {e}")

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


#FUCKASS HELPER METHODS UH IDK

import base64, json


def capture_screenshot(path: str = "page.png", full_page: bool = False):
    """
    Connects to an existing Chrome instance (via CDP) and captures a screenshot
    of the current tab viewport.

    Args:
        path (str): File path where the screenshot will be saved.
        full_page (bool): If True, captures the full scrollable page.

    Returns:
        str: The absolute file path of the saved screenshot.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")

            if not browser.contexts:
                print("❌ No browser contexts found. Launch Chrome with --remote-debugging-port=9222")
                return None

            context = browser.contexts[0]
            if not context.pages:
                print("❌ No open tabs found.")
                return None

            page = context.pages[0]
            print(f"📸 Capturing screenshot of: {page.title()} — {page.url}")

            # Playwright handles base64 encoding internally
            page.screenshot(path=path, full_page=full_page)
            print(f"✅ Screenshot saved at {path}")
            return path

    except Exception as e:
        print(f"❌ Failed to capture screenshot: {e}")
        return path
    

def annotate_screenshot(img_path, 
                        bounds=(1730, 1000), 
                        grid_divs=10, 
                        coords_to_mark=None):
    """
    Draws a coordinate grid and labels on a screenshot aligned to a fixed (0,0)-(1730,1000) space.
    The grid auto-scales to the image size for consistent LLM orientation.
    """
    img = Image.open(img_path)
    draw = ImageDraw.Draw(img)
    w, h = img.size
    max_x, max_y = bounds

    # scale factors in case your screenshot resolution differs from 1730x1000
    x_scale = w / max_x
    y_scale = h / max_y

    # load a font
    try:
        font = ImageFont.truetype("arial.ttf", 50)
        print("we doing the big font")
    except Exception as e:
        print(e)
        font = ImageFont.load_default(size=40)

    # spacing between gridlines in logical coordinate space
    step_x = max_x // grid_divs
    step_y = max_y // grid_divs

    # vertical lines + X labels
    for i in range(0, max_x + 1, step_x):
        x = int(i * x_scale)
        draw.line([(x, 0), (x, h)], fill=(255, 0, 0), width=1)
        draw.text((x + 3, 5), f"x={i}", fill=(255, 0, 0), font=font)

    # horizontal lines + Y labels
    for j in range(0, max_y + 1, step_y):
        y = int(j * y_scale)
        draw.line([(0, y), (w, y)], fill=(0, 0, 255), width=1)
        draw.text((5, y + 3), f"y={j}", fill=(0, 0, 255), font=font)

    # mark a coordinate if given
    if coords_to_mark:
        cx, cy = coords_to_mark
        x, y = int(cx * x_scale), int(cy * y_scale)
        r = 10
        draw.ellipse(
            [(x - r, y - r), (x + r, y + r)],
            outline=(0, 255, 0),
            width=3,
        )
        draw.text((x + 12, y + 12), f"({cx},{cy})", fill=(0, 255, 0), font=font)

    annotated_path = img_path.replace(".png", "_annotated.png")
    img.save(annotated_path)
    return annotated_path

screenshot_path = capture_screenshot("page.png")
annotated_path = annotate_screenshot(
    screenshot_path,
    bounds=(1730, 1000),
    grid_divs=10,
    coords_to_mark=(1730, 1000)  # optional marker
)
