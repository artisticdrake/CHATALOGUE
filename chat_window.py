# chat_window.py
"""
BU Guide Chat - Final Fixes (final)
- Python 3.11 compatible
- Left/right aligned bubbles (bot left, user right)
- Bubbles sized ~65% of chat width (responsive)
- Subtle matched colors (bot light gray, user soft blue)
- Auto-scroll to newest message
- Fade-in animation for messages (text color transition)
- All original function & variable names preserved
"""

import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import tkinter.font as tkfont
from datetime import datetime
import threading
import time
import sys
import traceback

# === CRITICAL: DO NOT MODIFY ===
def fetch_bot_reply(user_message):
    return "Bot reply: " + user_message
# ==============================

# ---------- Utilities ----------
def now_ts():
    return datetime.now().strftime("%I:%M %p")

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % rgb

def blend(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

def draw_gradient_rect(canvas, x1, y1, x2, y2, color1, color2, steps=24, horizontal=False):
    r1 = hex_to_rgb(color1); r2 = hex_to_rgb(color2)
    if horizontal:
        width = max(1, x2 - x1)
        for i in range(steps):
            t1 = i / steps
            t2 = (i + 1) / steps
            cstart = rgb_to_hex(blend(r1, r2, t1))
            xs = int(x1 + t1 * width)
            xe = int(x1 + t2 * width)
            canvas.create_rectangle(xs, y1, xe, y2, outline="", fill=cstart)
    else:
        height = max(1, y2 - y1)
        for i in range(steps):
            t1 = i / steps
            t2 = (i + 1) / steps
            cstart = rgb_to_hex(blend(r1, r2, t1))
            ys = int(y1 + t1 * height)
            ye = int(y1 + t2 * height)
            canvas.create_rectangle(x1, ys, x2, ye, outline="", fill=cstart)

# ---------- Chat Bubble ----------
class ChatBubble(tk.Frame):
    def __init__(self, master, text, sender='bot', ts=None, max_width_pct=0.65, *args, **kwargs):
        super().__init__(master, bg=master["bg"], pady=4)
        self.master = master
        self.text = text
        self.sender = sender
        self.ts = ts or now_ts()
        self.max_width_pct = max_width_pct

        # Colors: subtle matched tones (bot light gray; user soft blue)
        # We'll keep the red/gold variables for compatibility but not use them directly
        self.bot_c1, self.bot_c2 = "#F5F6F8", "#EEF0F2"   # soft gray gradient
        self.user_c1, self.user_c2 = "#E8F4FF", "#DAEDFF" # light blue gradient
        self.text_dark = "#111111"
        self.ts_color = "#666666"

        # Font
        preferred = ["Poppins", "Inter", "Nunito Sans", "Segoe UI", "Helvetica"]
        avail = set(tkfont.families())
        fam = next((f for f in preferred if f in avail), "Segoe UI")
        self.body_font = tkfont.Font(family=fam, size=13)
        self.ts_font = tkfont.Font(family=fam, size=9)

        # canvas for bubble drawing
        self.canvas = tk.Canvas(self, bg=self.master["bg"], highlightthickness=0)
        # pack direction is set by the caller via pack(anchor=...)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # preserved bounds for stable copy button placement
        self._rx1 = self._rx2 = self._ry1 = self._ry2 = 0

        self._rendered = False
        self._copy_tag = f"copy_{id(self)}"
        self._hovering = False
        self._hover_job = None

        # schedule render shortly after creation (so toplevel sizes are available)
        self.after(10, self._render)

    def copy_to_clipboard(self, event=None):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.text)
            top = self.winfo_toplevel()
            old = top.title()
            top.title("Copied to clipboard")
            self.after(600, lambda: top.title(old))
        except Exception:
            pass

    def _render(self):
        if self._rendered:
            return
        self._rendered = True

        # compute max width based on root or chat canvas width
        try:
            root_w = self.winfo_toplevel().winfo_width() or 1000
        except Exception:
            root_w = 1000
        # prefer to use parent canvas width if available (keeps bubbles proportional to chat area)
        parent_canvas_w = None
        try:
            # climb up until we find a canvas with yscrollcommand (chat_canvas)
            p = self.master
            while p:
                if isinstance(p, tk.Frame) and hasattr(p, "master"):
                    p = p.master
                else:
                    break
            # not reliable to find chat_canvas; fallback to root_w
        except:
            pass
        wrap_w = int(root_w * self.max_width_pct) - 36
        if wrap_w < 160:
            wrap_w = 160

        icon = "🧑" if self.sender == 'user' else "🤖"
        display = f"{icon}  {self.text}"

        # create text item
        text_id = self.canvas.create_text(16, 12, text=display, font=self.body_font,
                                          fill=self.text_dark, width=wrap_w, anchor='nw', justify='left')
        self.canvas.update_idletasks()
        bbox = self.canvas.bbox(text_id) or (0,0,200,20)
        x1, y1, x2, y2 = bbox
        pad_x, pad_y = 14, 10
        ts_h = self.ts_font.metrics("linespace") + 6

        rx1 = x1 - pad_x
        ry1 = y1 - pad_y
        rx2 = x2 + pad_x
        ry2 = y2 + pad_y + ts_h

        # ensure the canvas has enough size to show the bubble (and reflect proportional width)
        canvas_w = rx2 + pad_x + 8
        canvas_h = ry2 + pad_y + 8
        # set explicit width based on desired proportion of whole window (so bubbles don't stretch to full width)
        try:
            total_w = self.winfo_toplevel().winfo_width() or root_w
        except:
            total_w = root_w
        desired_w = int(total_w * self.max_width_pct)
        if desired_w < canvas_w:
            canvas_w = desired_w
        # final canvas size
        self.canvas.config(width=canvas_w, height=canvas_h)

        # store bounds for copy button
        self._rx1, self._rx2, self._ry1, self._ry2 = rx1, rx2, ry1, ry2

        # pick colors
        if self.sender == 'user':
            c1, c2 = self.user_c1, self.user_c2
            text_color = self.text_dark
        else:
            c1, c2 = self.bot_c1, self.bot_c2
            text_color = self.text_dark

        # draw rounded-like rectangle by using a gradient rect (keeps look consistent)
        draw_gradient_rect(self.canvas, rx1, ry1, rx2, ry2, c1, c2, steps=20, horizontal=False)
        # small inner border for subtle separation
        self.canvas.create_rectangle(rx1+1, ry1+1, rx2-1, ry2-1, outline="#E0E0E0", width=1)

        # raise text above background
        self.canvas.tag_raise(text_id)

        # timestamp
        ts_x = rx2 - pad_x - 4 if self.sender == 'user' else rx1 + pad_x + 4
        ts_anchor = 'se' if self.sender == 'user' else 'sw'
        self.canvas.create_text(ts_x, ry2 - 6, text=self.ts, font=self.ts_font, fill=self.ts_color, anchor=ts_anchor)

        # bind hover/click for copy
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-3>", lambda e: self.copy_to_clipboard())

        # animate in (fade-like)
        self._fade_in_text(text_id)

    def _lighter(self, hexc, amount=0.10):
        r,g,b = hex_to_rgb(hexc)
        def clamp(v): return max(0, min(255, int(v)))
        nr = clamp(r + (255 - r) * amount)
        ng = clamp(g + (255 - g) * amount)
        nb = clamp(b + (255 - b) * amount)
        return rgb_to_hex((nr,ng,nb))

    def _on_enter(self, ev):
        self._hovering = True
        # stable copy button placement inside bubble bounds
        try:
            if not self.canvas.find_withtag(self._copy_tag):
                bx2 = int(self._rx2 - 10)
                bx1 = bx2 - 72
                by1 = int(self._ry1 + 8)
                by2 = by1 + 28
                if self.sender == 'user':
                    base_fill = self.user_c2
                else:
                    base_fill = self.bot_c2
                fill = self._lighter(base_fill, 0.72)
                rect = self.canvas.create_rectangle(bx1, by1, bx2, by2, outline="#2C2828", fill=fill, tags=(self._copy_tag,))
                txt = self.canvas.create_text((bx1+bx2)//2, (by1+by2)//2, text="Copy", fill="#111111",
                                              font=(self.body_font.actual('family'), 9), tags=(self._copy_tag,))
                self.canvas.tag_bind(self._copy_tag, "<Button-1>", self.copy_to_clipboard)
                self.canvas.tag_bind(self._copy_tag, "<Enter>", lambda e: self._show_tooltip(e.x_root, e.y_root, "Copy"))
                self.canvas.tag_bind(self._copy_tag, "<Leave>", lambda e: self._hide_tooltip())
        except Exception:
            pass
        self._start_hover_anim()

    def _on_leave(self, ev):
        self._hovering = False
        try:
            self.canvas.delete(self._copy_tag)
        except:
            pass
        self._hide_tooltip()
        if self._hover_job:
            self.after_cancel(self._hover_job); self._hover_job = None
        # restore text color
        for it in self.canvas.find_all():
            if self.canvas.type(it) == "text":
                self.canvas.itemconfigure(it, fill=self.text_dark)

    def _show_tooltip(self, x, y, text="Copy"):
        self._hide_tooltip()
        self._tt = tk.Toplevel(self, bg='black')
        self._tt.wm_overrideredirect(True)
        lbl = tk.Label(self._tt, text=text, bg='black', fg='white', font=(self.body_font.actual('family'), 9))
        lbl.pack(padx=6, pady=3)
        self._tt.wm_geometry("+%d+%d" % (x + 12, y + 12))

    def _hide_tooltip(self):
        try:
            if hasattr(self, "_tt") and self._tt:
                self._tt.destroy()
                self._tt = None
        except:
            pass

    def _start_hover_anim(self):
        def step():
            if not self._hovering:
                return
            for it in self.canvas.find_all():
                if self.canvas.type(it) == "text":
                    cur = self.canvas.itemcget(it, "fill")
                    nxt = "#0F0F0F" if cur != "#0F0F0F" else "#111111"
                    self.canvas.itemconfigure(it, fill=nxt)
            self._hover_job = self.after(320, step)
        step()

    def _fade_in_text(self, text_id):
        # simulate fade-in by cycling text color from light gray to final dark color
        steps = 6
        def tick(i):
            if i > steps:
                return
            # interpolate grayscale value
            start = 200  # light
            end = 17     # dark
            val = int(start + (end - start) * (i / steps))
            hexc = rgb_to_hex((val, val, val))
            try:
                # update all text elements to this intermediate color for a consistent fade
                for it in self.canvas.find_all():
                    if self.canvas.type(it) == "text":
                        self.canvas.itemconfigure(it, fill=hexc)
            except:
                pass
            self.after(30, lambda: tick(i+1))
        tick(0)

# ---------- Main App ----------
class ChatApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("📚 BU Guide — Your Smart Campus Assistant")
        # try fullscreen (native frame retained)
        try:
            self.attributes("-fullscreen", True)
        except tk.TclError:
            self.state("zoomed")
        self.configure(bg="#2C2C2C")

        # keyboard shortcuts
        self.bind("<Escape>", self._on_escape)       # toggle fullscreen/windowed
        self.bind_all("<Control-m>", lambda e: self._minimize())  # minimize
        self.bind_all("<Control-q>", lambda e: self._close())     # close

        # choose font
        self.pref_font = self._choose_font()

        # header area (canvas gradient)
        self.header_h = 64
        self.header = tk.Canvas(self, height=self.header_h, highlightthickness=0, bg=self["bg"])
        self.header.pack(fill=tk.X, side=tk.TOP)
        draw_gradient_rect(self.header, 0, 0, 3000, self.header_h, "#C41E3A", "#F24C4C", steps=80, horizontal=True)
        self.header.create_text(18, self.header_h//2, text="📚 BU Guide — Your Smart Campus Assistant 🚀",
                                anchor='w', fill="#F2C94C", font=(self.pref_font, 14, "bold"))

        # header buttons frame (placed on canvas at right)
        self._build_header_buttons()

        # main + right scrollbar (scrollbar is always at the right of window)
        main_wrap = tk.Frame(self, bg="#2C2C2C")
        main_wrap.pack(fill=tk.BOTH, expand=True)

        # right-aligned global scrollbar (always visible)
        self.global_scrollbar = tk.Scrollbar(main_wrap, orient=tk.VERTICAL)
        self.global_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # center container (70% width by default)
        self.center_container = tk.Frame(main_wrap, bg="#2C2C2C")
        self.center_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # chat canvas inside center container
        self.chat_canvas = tk.Canvas(self.center_container, bg="#252626", highlightthickness=0,
                                     yscrollcommand=self.global_scrollbar.set)
        # chat_frame holds message wrappers; we'll keep it narrow-ish and centered within chat_canvas
        self.chat_frame = tk.Frame(self.chat_canvas, bg="#252626")
        self.chat_window_id = self.chat_canvas.create_window((0,0), window=self.chat_frame, anchor='nw')
        self.chat_canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=12, pady=12)
        self.chat_frame.bind("<Configure>", lambda e: self._on_chat_frame_configure())
        self.global_scrollbar.config(command=self.chat_canvas.yview)

        # bind resize and wheel
        self.bind("<Configure>", lambda e: self._on_resize())
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)

        # thin divider between chat and input
        self.divider = tk.Frame(self, bg="#DDDDDD", height=1)

        # input area
        self._build_input_area()

        # history
        self.history = []

        # welcome
        self._welcome_text = "👋 Welcome to BU Guide — your campus companion! Ask me about courses, campus life, or support."
        self.add_bot(self._welcome_text)

        # typing lock
        self._typing_lock = threading.Lock()
        self.jump_visible = False
        self.after(200, lambda: self.user_input.focus_set())

    def _on_chat_frame_configure(self):
        # ensure canvas scrollregion is updated and inner window width tracks container width
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
        # set inner window width to an appropriate value so wrappers (frames) can be sized
        canvas_w = self.chat_canvas.winfo_width()
        # keep some side padding inside the visible canvas (so bubbles don't touch edges)
        inner_w = max(360, int(canvas_w * 0.90))
        self.chat_canvas.itemconfigure(self.chat_window_id, width=inner_w)

    def _choose_font(self):
        pref = ["Poppins", "Inter", "Nunito Sans", "Segoe UI", "Helvetica"]
        avail = set(tkfont.families())
        return next((f for f in pref if f in avail), "Segoe UI")

    def _build_header_buttons(self):
        # frame to hold header buttons
        self.btn_frame = tk.Frame(self, bg='', padx=6, pady=6)
        # fixed width buttons to avoid expansion on hover
        copy_btn = tk.Button(self.btn_frame, text="📋 Copy", bg="#F2C94C", fg="#111", bd=0, padx=8, cursor="hand2", command=self.copy_all)
        copy_btn.pack(side=tk.LEFT, padx=6)
        copy_btn.configure(width=12, anchor="center")
        copy_btn.bind("<Enter>", lambda e: self._show_btn_tooltip(e, "Copy conversation to clipboard"))
        copy_btn.bind("<Leave>", lambda e: self._hide_btn_tooltip())

        save_btn = tk.Button(self.btn_frame, text="💾 Save", bg="#F2C94C", fg="#111", bd=0, padx=8, cursor="hand2", command=self.save_as)
        save_btn.pack(side=tk.LEFT, padx=6)
        save_btn.configure(width=10, anchor="center")
        save_btn.bind("<Enter>", lambda e: self._show_btn_tooltip(e, "Save conversation to file"))
        save_btn.bind("<Leave>", lambda e: self._hide_btn_tooltip())

        clear_btn = tk.Button(self.btn_frame, text="🧹 Clear Chat", bg="#F2C94C", fg="#111", bd=0, padx=8, cursor="hand2", command=self.clear_chat)
        clear_btn.pack(side=tk.LEFT, padx=6)
        clear_btn.configure(width=12, anchor="center")
        clear_btn.bind("<Enter>", lambda e: self._show_btn_tooltip(e, "Clear chat history"))
        clear_btn.bind("<Leave>", lambda e: self._hide_btn_tooltip())

        for btn in (copy_btn, save_btn, clear_btn):
            btn.bind("<Enter>", lambda e, b=btn: b.config(relief='raised'))
            btn.bind("<Leave>", lambda e, b=btn: b.config(relief='flat'))

        try:
            win_w = self.winfo_screenwidth()
            x = win_w - 320
            self.header.create_window(x, self.header_h//2, window=self.btn_frame, anchor='w', tags="hdr_btns")
        except Exception:
            self.header.create_window(1100, self.header_h//2, window=self.btn_frame, anchor='w', tags="hdr_btns")

    def _show_btn_tooltip(self, event, text):
        self._hide_btn_tooltip()
        x_root = event.widget.winfo_rootx()
        y_root = event.widget.winfo_rooty()
        self._btn_tt = tk.Toplevel(self, bg='black')
        self._btn_tt.wm_overrideredirect(True)
        lbl = tk.Label(self._btn_tt, text=text, bg='black', fg='white', font=(self.pref_font, 9))
        lbl.pack(padx=6, pady=3)
        self._btn_tt.wm_geometry("+%d+%d" % (x_root + 8, y_root + event.widget.winfo_height() + 6))

    def _hide_btn_tooltip(self):
        try:
            if hasattr(self, "_btn_tt") and self._btn_tt:
                self._btn_tt.destroy()
                self._btn_tt = None
        except:
            pass

    def _build_input_area(self):
        self.input_area = tk.Frame(self, bg="#2C2C2C", pady=10)
        self.input_area.pack(fill=tk.X, side=tk.BOTTOM)
        self.divider.pack(fill=tk.X, side=tk.BOTTOM)
        self.input_bg = tk.Canvas(self.input_area, bg="#2C2C2C", height=64, highlightthickness=0)
        self.input_bg.pack(fill=tk.X, padx=18)
        self.input_bg.bind("<Configure>", lambda e: self._draw_input_bg())
        self.user_input = tk.Text(self.input_area, height=1, wrap='word', font=(self.pref_font, 14), bg="#222222", fg="white", bd=0, padx=12, pady=10, insertbackground='white')
        self.user_input.place(in_=self.input_bg, x=12, y=8, relwidth=0.78, height=48)
        self.user_input.bind("<Return>", self._on_enter)
        self.user_input.bind("<Shift-Return>", self._insert_newline)
        self.send_btn = tk.Button(self.input_area, text="📤  Send", bg="#C41E3A", fg="white", bd=0, padx=12, cursor="hand2", command=self.on_send)
        self.send_btn.place(in_=self.input_bg, relx=0.82, x=0, y=8, width=140, height=48)
        self.send_btn.bind("<Enter>", lambda e: self.send_btn.config(relief='raised'))
        self.send_btn.bind("<Leave>", lambda e: self.send_btn.config(relief='flat'))

    def _draw_input_bg(self):
        c = self.input_bg; c.delete("all")
        w = c.winfo_width() or 900; h = c.winfo_height() or 64; pad = 6
        draw_gradient_rect(c, pad, pad, w-pad, h-pad, "#1F1F1F", "#2C2C2C", steps=18, horizontal=False)
        c.create_rectangle(pad+2, pad+2, w-pad-2, h-pad-2, outline="#333333")

    def _on_resize(self):
        # center container width = 70% window, max 1400
        win_w = self.winfo_width() or 1200
        cont_w = int(win_w * 0.70)
        if cont_w > 1400: cont_w = 1400
        height_avail = max(300, self.winfo_height() - self.header_h - 180)
        self.center_container.config(width=cont_w, height=height_avail)
        self.chat_canvas.config(width=cont_w, height=height_avail)
        # reposition header buttons to right edge
        try:
            self.header.delete("hdr_btns")
        except:
            pass
        try:
            x = self.winfo_width() - 320
            self.header.create_window(x, self.header_h//2, window=self.btn_frame, anchor='w', tags="hdr_btns")
        except:
            pass
        # ensure inner window width updates
        self._on_chat_frame_configure()

    def _on_mousewheel(self, ev):
        try:
            if sys.platform == 'darwin':
                delta = -1 * int(ev.delta)
            else:
                if hasattr(ev, 'delta'):
                    delta = -1 * int(ev.delta / 120)
                else:
                    if ev.num == 4:
                        delta = -1
                    else:
                        delta = 1
            self.chat_canvas.yview_scroll(delta, "units")
        except Exception:
            pass
        self._check_jump()

    def _check_jump(self):
        try:
            y1, y2 = self.chat_canvas.yview()
            if y2 < 0.999:
                if not getattr(self, 'jump_visible', False):
                    w = self.winfo_width(); h = self.winfo_height()
                    self.jump_btn = tk.Button(self, text="⬇", bg="#444444", fg="white", bd=0, cursor="hand2", command=lambda: self.chat_canvas.yview_moveto(1.0))
                    self.jump_btn.place(x=w//2 - 20, y=h - 120, width=40, height=40)
                    self.jump_visible = True
            else:
                if getattr(self, 'jump_visible', False):
                    try:
                        self.jump_btn.place_forget()
                    except:
                        pass
                    self.jump_visible = False
        except Exception:
            pass

    # ---- add messages ----
    def add_bot(self, text):
        ts = now_ts()
        self.history.append(text)
        # wrapper frame sized to inner width and aligned left
        wrapper = tk.Frame(self.chat_frame, bg="#252626")
        wrapper.pack(fill=tk.X, pady=4, anchor='w', padx=8)
        # we'll constrain bubble width via max_width_pct in ChatBubble (default 0.65)
        bubble = ChatBubble(wrapper, text=text, sender='bot', ts=ts, max_width_pct=0.65)
        # ensure bubble is anchored left
        bubble.pack(anchor='w', padx=(4, 40))
        # auto-scroll to bottom
        self.after(50, lambda: self.chat_canvas.yview_moveto(1.0))

    def add_user(self, text):
        ts = now_ts()
        self.history.append(text)
        wrapper = tk.Frame(self.chat_frame, bg="#252626")
        wrapper.pack(fill=tk.X, pady=4, anchor='e', padx=8)
        bubble = ChatBubble(wrapper, text=text, sender='user', ts=ts, max_width_pct=0.65)
        bubble.pack(anchor='e', padx=(40, 4))
        self.after(50, lambda: self.chat_canvas.yview_moveto(1.0))

    # ---- input handlers & backend ----
    def _on_enter(self, ev=None):
        if ev and (ev.state & 0x0001):
            return
        self.on_send()
        return "break"

    def _insert_newline(self, ev=None):
        self.user_input.insert("insert", "\n")
        return "break"

    def on_send(self):
        msg = self.user_input.get("1.0", "end").strip()
        if not msg:
            messagebox.showerror("Input Error", "Please enter a message before sending.")
            return
        self.add_user(msg)
        self.user_input.delete("1.0", "end")
        # typing indicator
        typing_wrap = tk.Frame(self.chat_frame, bg="#F8F9FA")
        typing_wrap.pack(fill=tk.X, pady=4, anchor='w', padx=8)
        typing_bubble = ChatBubble(typing_wrap, text="🤖 BU Guide is typing...", sender='bot', ts=now_ts(), max_width_pct=0.65)
        typing_bubble.pack(anchor='w', padx=(4, 40))

        stop_flag = {"stop": False}
        def dot_anim():
            while not stop_flag["stop"]:
                for n in range(1,4):
                    if stop_flag["stop"]:
                        break
                    try:
                        typing_bubble.canvas.delete("typing_text")
                        typing_bubble.canvas.create_text(16, 12, text=f"🤖  BU Guide is typing{'.'*n}",
                                                        font=typing_bubble.body_font, fill=typing_bubble.text_dark,
                                                        width=int(self.winfo_width()*0.65), anchor='nw', tags="typing_text")
                    except:
                        pass
                    time.sleep(0.5)
        t1 = threading.Thread(target=dot_anim, daemon=True)
        t1.start()

        def call_backend(m):
            try:
                reply = fetch_bot_reply(m)  # preserved
            except Exception as e:
                reply = None
                tb = traceback.format_exc()
                self.after(50, lambda: self._replace_typing(typing_wrap, "⚠️ Error contacting backend."))
                stop_flag["stop"] = True
                return
            stop_flag["stop"] = True
            self.after(200, lambda: self._replace_typing(typing_wrap, reply))
        t2 = threading.Thread(target=call_backend, args=(msg,), daemon=True)
        t2.start()

    def _replace_typing(self, typing_wrapper, text):
        try:
            typing_wrapper.destroy()
        except:
            pass
        if not text:
            text = "Sorry — no response from backend."
        self.add_bot(text)

    # ---- copy / save / clear ----
    def copy_all(self):
        try:
            plain = "\n".join(self.history)
            self.clipboard_clear()
            self.clipboard_append(plain)
            messagebox.showinfo("Copied", "Conversation copied to clipboard ✅")
        except Exception as e:
            messagebox.showerror("Copy Error", str(e))

    def save_as(self):
        try:
            default_name = f"chat_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
            fpath = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files","*.txt")],
                                                 initialfile=default_name, title="Save Conversation As")
            if not fpath:
                return
            with open(fpath, "w", encoding="utf-8") as f:
                for m in self.history:
                    f.write(m + "\n")
            messagebox.showinfo("Saved", f"Conversation saved to:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def clear_chat(self):
        if not messagebox.askyesno("Clear Chat", "Are you sure you want to clear the chat?"):
            return
        for w in self.chat_frame.winfo_children():
            w.destroy()
        self.history = []
        self.add_bot(self._welcome_text)

    # ---- window control helpers ----
    def _on_escape(self, ev=None):
        # Toggle fullscreen/windowed
        try:
            cur = bool(self.attributes("-fullscreen"))
            self.attributes("-fullscreen", not cur)
        except tk.TclError:
            # fallback: toggle zoomed state
            if str(self.state()) == "zoomed":
                self.state("normal")
            else:
                self.state("zoomed")

    def _minimize(self):
        try:
            self.attributes("-fullscreen", False)
        except:
            pass
        try:
            self.iconify()
        except:
            pass

    def _close(self):
        try:
            self.destroy()
        except:
            pass

# ---------------- Run ----------------
if __name__ == "__main__":
    app = ChatApp()
    app.mainloop()




