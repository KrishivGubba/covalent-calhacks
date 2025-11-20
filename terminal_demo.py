import curses
import subprocess
import shlex

# -------------------------------
# TRIE ENGINE
# -------------------------------

class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end = False
        self.score = 0

class CommandTrie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, command):
        node = self.root
        for ch in command:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.is_end = True

    def autocomplete(self, prefix):
        node = self.root
        for ch in prefix:
            if ch not in node.children:
                return []
            node = node.children[ch]

        results = []

        def dfs(cur, path):
            if cur.is_end:
                results.append((path, cur.score))
            for ch, nxt in cur.children.items():
                dfs(nxt, path + ch)

        dfs(node, prefix)
        results.sort(key=lambda x: -x[1])
        return [cmd for cmd, score in results]

    def learn(self, command):
        node = self.root
        for ch in command:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.is_end = True
        node.score += 1


# -------------------------------
# AUTOCOMPLETE SETUP
# -------------------------------

trie = CommandTrie()
commands = [
    "npm install",
    "npm run dev",
    "npm start",
    "git status",
    "git push",
    "python3 main.py",
    "git add *",
    "git commit -m \"created empty text file\""
]

for c in commands:
    trie.insert(c)


# -------------------------------
# RUN REAL COMMAND
# -------------------------------

def run_real(cmd, screen):
    try:
        proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        output = out.decode() + err.decode()
        if output:
            screen.addstr(output)
    except Exception as e:
        screen.addstr(f"Error: {e}\n")


# -------------------------------
# MAIN LOOP
# -------------------------------

def main(screen):
    curses.curs_set(1)
    buffer = ""
    
    while True:
        # Get current cursor position
        y, x = screen.getyx()
        
        # Draw the prompt and buffer
        screen.addstr(y, 0, "krishiv$ " + buffer)
        
        # Clear to end of line (in case buffer shrunk)
        screen.clrtoeol()

        # Compute suggestion
        matches = trie.autocomplete(buffer)
        suggestion = ""
        if matches:
            best = matches[0]
            if best.startswith(buffer) and best != buffer:
                suggestion = best[len(buffer):]

        # Draw ghost text
        if suggestion:
            screen.addstr(suggestion, curses.A_DIM)

        # Move cursor back to end of buffer
        screen.move(y, len("krishiv$ ") + len(buffer))
        screen.refresh()

        ch = screen.getch()

        # ENTER
        if ch == 10:
            screen.addstr("\n")
            if buffer.strip():
                run_real(buffer, screen)
                trie.learn(buffer)
            buffer = ""
            continue

        # BACKSPACE
        if ch in (curses.KEY_BACKSPACE, 127):
            if buffer:
                buffer = buffer[:-1]
            continue

        # ACCEPT suggestion (Right arrow or TAB)
        if ch in (curses.KEY_RIGHT, 9):
            if suggestion:
                buffer += suggestion
            continue

        # EXIT (Ctrl+C)
        if ch == 3:
            return

        # Normal characters
        if 32 <= ch <= 126:
            buffer += chr(ch)


curses.wrapper(main)