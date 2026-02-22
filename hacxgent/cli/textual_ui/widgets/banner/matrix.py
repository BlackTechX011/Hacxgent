from __future__ import annotations

import random
from typing import Any

from textual.widgets import Static

class MatrixRain(Static):
    """
    A fixed-size Matrix widget that breaks the 'box' illusion by using 
    randomized column delays and varying densities.
    """

    DEFAULT_CSS = """
    MatrixRain {
        background: transparent;
        overflow: hidden;
    }
    """

    def __init__(self, width: int = 45, height: int = 10, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._matrix_width = width
        self._matrix_height = height
        
        # 1. FIXED CONTAINER SIZE
        # We reserve the space so the layout is stable, but we won't fill it solid.
        self.styles.width = width
        self.styles.height = height
        
        # Hacker/Math Character Set
        self._chars = (
            [chr(i) for i in range(0xFF66, 0xFF9D)] + # Katakana
            list("0123456789") + 
            list("±≡≈≠≤≥")
        )
        
        # Initialize columns
        self._columns = []
        for _ in range(width):
            self._columns.append(self._generate_column(start_random=True))

    def _generate_column(self, start_random: bool = False) -> dict:
        """
        Creates a column state. 
        'delay' is the key to breaking the box shape.
        """
        # If start_random is True, we scatter them instantly.
        # If False (resetting), we add a random DELAY so the column stays empty for a while.
        delay = 0 if start_random else random.randint(0, 40)
        
        start_pos = random.randint(-self._matrix_height, 0)
        if start_random:
            start_pos = random.randint(-self._matrix_height, self._matrix_height)

        return {
            "pos": float(start_pos),
            "trail": random.randint(4, 12),      # Random trail lengths
            "speed": random.uniform(0.8, 2.2),   # Different speeds
            "delay": delay,                      # Time to wait before showing up
            "chars": [random.choice(self._chars) for _ in range(self._matrix_height + 15)]
        }

    def on_mount(self) -> None:
        self.set_interval(0.05, self._update_matrix)

    def _update_matrix(self) -> None:
        lines = []
        
        # Pixel Hacker Palette (Blue/Cyan/White)
        c_head = "[bold #FFFFFF]"       # Bright White
        c_glow = "[bold #00FFFF]"       # Cyan Neon
        c_mid  = "[#00BFFF]"            # Tech Blue
        c_fade = "[dim #000080]"        # Deep Navy (Faded)
        c_reset = "[/]"

        for y in range(self._matrix_height):
            line_parts = []
            
            for x in range(self._matrix_width):
                col = self._columns[x]
                
                # 2. THE "NO BOX" LOGIC
                # If the column is in delay mode, render a space and skip math.
                if col["delay"] > 0:
                    line_parts.append(" ")
                    continue

                pos = int(col["pos"])
                char_idx = y % len(col["chars"])
                
                # 1% Chance to glitch a character
                if random.random() < 0.01:
                    col["chars"][char_idx] = random.choice(self._chars)
                
                char = col["chars"][char_idx]

                if pos == y:
                    line_parts.append(f"{c_head}{char}{c_reset}")
                elif pos > y and pos - y < col["trail"]:
                    dist = pos - y
                    if dist == 1:
                        line_parts.append(f"{c_glow}{char}{c_reset}")
                    elif dist < 5:
                        line_parts.append(f"{c_mid}{char}{c_reset}")
                    else:
                        line_parts.append(f"{c_fade}{char}{c_reset}")
                else:
                    line_parts.append(" ")
            
            lines.append("".join(line_parts))
        
        # Physics Update
        for x in range(self._matrix_width):
            col = self._columns[x]
            
            # If delaying, count down
            if col["delay"] > 0:
                col["delay"] -= 1
                continue

            col["pos"] += col["speed"]
            
            # 3. RESET WITH DELAY
            # When a drop finishes, we don't restart immediately. 
            # We generate a new column which includes a random delay.
            if col["pos"] - col["trail"] > self._matrix_height:
                self._columns[x] = self._generate_column(start_random=False)

        self.update("\n".join(lines))