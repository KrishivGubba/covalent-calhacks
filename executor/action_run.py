# file: run_actions.py
from playwright.sync_api import sync_playwright
from executor.vocab_code import click_element, set_value, scroll_page, wait_seconds, hover_element, navigate_to, extract_text
import json
import time


def parse_and_run(action):
    """
    action: dict describing ONE action to perform.
        e.g. {"type": "click", "selector": "#submitButton"}
    """

    with sync_playwright() as p:
        # Connect to Chrome already running with remote debugging
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print("❌ Could not connect to Chrome:", e)
            return

        if not browser.contexts:
            print("❌ No browser contexts found. Launch Chrome with --remote-debugging-port=9222")
            return
        
        context = browser.contexts[0]
        if not context.pages:
            print("❌ No open tabs found.")
            return
        print("brothe rin chirst")
        if "actions" in action:
            action = action["actions"][0]
        print("hello are we getting here.")
        page = context.pages[0]
        print(f"✅ Connected to: {page.title()} — {page.url}")
        print(action, "is the action")
        t = action.get("type")
        print(t, " is the t")
        print(f"➡️ Running action: {t}")

        try:
            if t == "click":
                click_element(page, selector=action.get("selector") or f"text={action.get('text_hint', '')}")

            elif t == "set_value":
                set_value(page, selector=action["selector"], value=action["value"])

            elif t == "scroll":
                scroll_page(page, direction=action.get("direction", "down"), amount=action.get("amount", 300))

            elif t == "wait":
                wait_seconds(action.get("duration", 1))

            elif t == "hover":
                hover_element(page, selector=action["selector"])

            elif t == "navigate":
                navigate_to(page, url=action["url"])

            elif t == "extract":
                text = extract_text(page, selector=action["selector"])
                print(f"🟡 Extracted text: {text}")

            else:
                print(f"⚠️ Unknown action type: {t}")

            print("✅ Action complete.")

        except Exception as e:
            print(f"❌ Error executing action {t}: {e}")

        finally:
            browser.close()



def get_simplified_dom(port=9222, buffer_px=200) -> dict:
    """
    Connects to an existing Chrome session (launched with --remote-debugging-port),
    captures visible + interactive elements near the viewport,
    including hidden combobox dropdowns (React-Select, etc.).
    Returns a compact JSON snapshot.
    """
    script = f"""
    () => {{
      const snapshot = {{}};
      const elements = document.querySelectorAll('*');
      const viewportHeight = window.innerHeight;

      for (const el of elements) {{
        const tag = el.tagName.toLowerCase();

        // skip structural junk
        if (["html","head","meta","script","style","link","svg","path"].includes(tag)) continue;

        const rect = el.getBoundingClientRect();
        if (rect.bottom < -{buffer_px} || rect.top > viewportHeight + {buffer_px}) continue;

        const role = el.getAttribute("role");
        const tabIndex = el.tabIndex;
        const clickable = !!el.onclick;
        const hasPopup = el.getAttribute("aria-haspopup") === "listbox";
        const isCombobox = role === "combobox";

        // treat comboboxes and popups as interactive, even if hidden
        const isInteractive =
          ["button","input","a","select","textarea"].includes(tag) ||
          ["button","link","combobox"].includes(role) ||
          tabIndex >= 0 || clickable || hasPopup;

        if (!isInteractive) continue;

        // detect visibility but allow hidden comboboxes
        const isVisible = !!(el.offsetParent || el.getClientRects().length);
        if (!isVisible && !isCombobox && !hasPopup) continue;

        // get best available label/description
        const txt = (el.innerText || "").trim();
        const aria = el.getAttribute("aria-label") || "";
        const placeholder = el.getAttribute("placeholder") || "";
        const alt = el.getAttribute("alt") || "";
        const title = el.getAttribute("title") || "";
        const name = el.getAttribute("name") || "";
        const value = el.value || "";

        const description = txt || aria || placeholder || alt || title || name || value;
        if (!description) continue;

        // build readable key
        let key = "";
        if (el.id) key = "#" + el.id;
        else if (aria) key = `[aria-label='${{aria.slice(0,30)}}']`;
        else if (txt) key = `[text*='${{txt.slice(0,30)}}']`;
        else if (placeholder) key = `[placeholder*='${{placeholder.slice(0,30)}}']`;
        else key = tag;

        snapshot[key] = {{
          tag: tag,
          description: description.slice(0, 120),
          visible: isVisible,
          value: value
        }};
      }}
      return snapshot;
    }}
    """

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
            if not browser.contexts:
                print("❌ No browser contexts found.")
                return {}

            context = browser.contexts[0]
            if not context.pages:
                print("❌ No open tabs found.")
                return {}

            page = context.pages[0]
            print(f"✅ Connected to: {page.title()} — {page.url}")

            dom_snapshot = page.evaluate(script)
            print(f"📸 Captured {len(dom_snapshot)} interactive elements (including dropdowns).")

            # Optional: print a small sample for inspection
            # print(json.dumps(dom_snapshot, indent=2)[:1000])

            browser.close()
            return dom_snapshot

        except Exception as e:
            print(f"❌ Failed to capture DOM snapshot: {e}")
            return {}
        




# # if __name__ == "__main__":
# #     # Example: test with a single action
# #     time.sleep(3)
# #     with open("tryme.json", "r") as file:
# #         data = json.load(file)
# #     print("Running:", data)
# #     parse_and_run(data)

# # assign_hashed_ids()
# res = get_simplified_dom()

# with open("something.json", "w") as file:
#     file.write(json.dumps(res, indent=4))