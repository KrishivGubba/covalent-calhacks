import requests
from playwright.sync_api import sync_playwright
from urllib.parse import quote_plus
from llm_client_obj import LLM_Client

class LearnObject:
    def __init__(self, ws_endpoint=None):
        self.browser = None
        self.context = None
        self.currTabs = []

        # auto-discover Chrome's websocket endpoint if not provided
        if ws_endpoint is None:
            try:
                info = requests.get("http://localhost:9222/json/version").json()
                ws_endpoint = info["webSocketDebuggerUrl"]
                print(f"🛰️  Found Chrome WebSocket endpoint:\n   {ws_endpoint}")
            except Exception as e:
                raise RuntimeError("❌ Could not fetch Chrome WebSocket URL. "
                                   "Make sure Chrome is running with --remote-debugging-port=9222") from e

        self.ws_endpoint = ws_endpoint


    def _ensure_browser(self):
        """Attach to existing Chrome instance over CDP."""
        if not self.browser:
            p = sync_playwright().start()
            # Connect to your running Chrome instead of launching new
            self.browser = p.chromium.connect_over_cdp(self.ws_endpoint)
            # Get the default context (Chrome window)
            self.context = self.browser.contexts[0]

    def googleSearchUp(self, query):
        """
        Opens a new tab in the attached Chrome window and performs
        a Google search for the given query string.
        """
        self._ensure_browser()
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        page = self.context.new_page()
        page.goto(search_url)
        self.currTabs.append({
            "query": query,
            "url": search_url,
            "page": page
        })
        print(f"🔍 Searched Google for: '{query}'")

    
    def youtubeSearchUp(self, topic):
        self._ensure_browser()
        search_url = f"https://www.youtube.com/results?search_query={topic}"
        page = self.context.new_page()
        page.goto(search_url)
        self.currTabs.append({
            "query" : topic,
            "url" : search_url,
            "page" : page
        })
        print(f"🔍 Searched YT for: '{topic}'")



    #NOTE: this is to be actually used
    def switchToTabByQuery(self, query):
        """Switch to a tab by its search query"""
        for tab in self.currTabs:
            if tab["query"] == query:
                tab["page"].bring_to_front()
                print(f"✅ Switched to tab: {query}")
                return
        print(f"❌ No tab found with query: {query}")

    def switchToTabByIndex(self, index): #TODO: this is kinda broken, don't use this, instead use the above 
        """Switch to tab by index (0-based)"""
        if 0 <= index < len(self.currTabs):
            self.currTabs[index]["page"].bring_to_front()
            print(f"✅ Switched to tab {index}: {self.currTabs[index]['query']}")
        else:
            print(f"❌ Invalid index: {index}")
            

    def closeAll(self):
        if self.browser:
            self.browser.close()
            self.browser = None
            self.context = None
            self.currTabs = []
            print("🧹 Closed all tabs (attached Chrome still running).")
    
    def clickFirstResult(self, tab_index=-1):
        """
        Click the first search result in a Google search tab.
        
        Args:
            tab_index: Index of tab in self.currTabs (default -1 for last tab)
        """
        if not self.currTabs:
            print("❌ No tabs available")
            return
        
        if tab_index >= len(self.currTabs) or tab_index < -len(self.currTabs):
            print(f"❌ Invalid tab index: {tab_index}")
            return
        
        tab = self.currTabs[tab_index]
        page = tab["page"]
        
        try:
            print(f"🔍 Looking for first result in: '{tab['query']}'")
            
            # Wait for search results to load
            page.wait_for_selector("div#search", timeout=2000)
            
            # Google search result selectors (they have multiple formats)
            selectors = [
                "div#search a[jsname='UWckNb']",  # Main result link
                "div#search h3",                   # Result title (click parent link)
                "div.g a[href]:not([class])",      # Generic result link
            ]
            
            for selector in selectors:
                try:
                    # Find first clickable result
                    first_link = page.locator(selector).first
                    if first_link.count() > 0:
                        # Get the URL before clicking (for logging)
                        href = first_link.get_attribute("href")
                        print(f"🎯 Clicking first result: {href}")
                        
                        first_link.click()
                        page.wait_for_load_state("networkidle", timeout=10000)
                        print(f"✅ Navigated to first result!")
                        return
                except Exception:
                    continue
            
            print("❌ Could not find any clickable results")
            
        except Exception as e:
            print(f"❌ Error clicking first result: {e}")


    def googleSearchAndClick(self, query):
        """
        Convenience method: search Google and immediately click first result.
        """
        self.googleSearchUp(query)
        self.clickFirstResult(-1)  # Click in the last (just created) tab


    @staticmethod
    def generateQueries(action, details):
        """
        Uses the LLM to generate 3 focused search queries
        based on the given user action and context details.
        Returns a Python list of strings.
        """
        queryGenerator = LLM_Client()

        PROMPT = f"""
You are a smart query generator.
Given a user's current goal or action and some background context,
generate exactly 3 short, relevant Google search queries the user would likely want to run next.

- Each query should be phrased naturally as if typed into Google.
- Avoid duplicates or overly similar queries.
- Keep them concise (max ~10 words each).
- Return ONLY a valid JSON array of strings.

Example:
["what is the chrome devtools protocol", "playwright connect_over_cdp example", "how to automate browser tabs with python"]

User action: {action}
Context details: {details}
        """

        SYS_PROMPT = "You are a precise query generator that outputs only a JSON array of 3 search queries."

        response = queryGenerator.generate(
            prompt=PROMPT.strip(),
            sys_prompt=SYS_PROMPT
        )

        # ensure we return a parsed Python list
        try:
            import json
            queries = json.loads(response)
            if isinstance(queries, list):
                return queries
            else:
                raise ValueError("Response was not a JSON array")
        except Exception:
            print("⚠️ Could not parse response from LLM, returning fallback.")
            return [f"{action} {details}".strip(), f"how to {action}", f"{action} tutorial"]

