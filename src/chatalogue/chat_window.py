# chat_window.py
"""
Main GUI application for the BU Guide Chatbot.
Handles the Tkinter interface, custom chat bubble rendering, 
and interaction with the scraping/querying backend.
"""
from . import chatalogue
from . import bu_scraper
from .db_interface import process_semantic_query
from . import run_query as connections


import os
import tkinter as tk
from tkinter import messagebox, filedialog, ttk, simpledialog
import tkinter.font as tkfont
from datetime import datetime
import threading
import time
import sys
import traceback

# Legacy imports (now handled in __init__.py)
#import chatalogue as chatalogue
#import bu_scraper as bu_scraper
#import run_query as connections

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

# ---------- Custom Widgets ----------

class ChatBubble(tk.Frame):
    def __init__(self, master, text, sender='bot', ts=None, max_width_pct=0.65, *args, **kwargs):
        super().__init__(master, bg=master["bg"], pady=4)
        self.master = master
        self.text = text
        self.sender = sender
        self.ts = ts or now_ts()
        self.max_width_pct = max_width_pct

        self.bot_c1, self.bot_c2 = "#F5F6F8", "#EEF0F2"
        self.user_c1, self.user_c2 = "#E8F4FF", "#DAEDFF"
        self.text_dark = "#111111"
        self.ts_color = "#666666"

        preferred = ["Poppins", "Inter", "Nunito Sans", "Segoe UI", "Helvetica"]
        avail = set(tkfont.families())
        fam = next((f for f in preferred if f in avail), "Segoe UI")
        self.body_font = tkfont.Font(family=fam, size=13)
        self.ts_font = tkfont.Font(family=fam, size=9)

        self.canvas = tk.Canvas(self, bg=self.master["bg"], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._rx1 = self._rx2 = self._ry1 = self._ry2 = 0
        self._rendered = False
        self._copy_tag = f"copy_{id(self)}"
        self._hovering = False
        self._hover_job = None
        self._skip_fade = False

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
        # Prevent redundant rendering if already drawn
        if self._rendered:
            return
        self._rendered = True

        try:
            root_w = self.winfo_toplevel().winfo_width() or 1000
        except Exception:
            root_w = 1000

        wrap_w = int(root_w * self.max_width_pct) - 36
        if wrap_w < 160:
            wrap_w = 160

        icon = "🧑" if self.sender == 'user' else "🤖"
        display = f"{icon}  {self.text}"
        
        # Create text element; keep reference for resize updates
        if getattr(self, 'text_id', None):
            try:
                self.canvas.delete(self.text_id)
            except:
                pass
        self.text_id = self.canvas.create_text(16, 12, text=display, font=self.body_font,
                                               fill=self.text_dark, width=wrap_w, anchor='nw', justify='left')
        self.canvas.update_idletasks()
        bbox = self.canvas.bbox(self.text_id) or (0,0,200,20)
        x1, y1, x2, y2 = bbox
        pad_x, pad_y = 14, 10
        ts_h = self.ts_font.metrics("linespace") + 6

        rx1 = x1 - pad_x
        ry1 = y1 - pad_y
        rx2 = x2 + pad_x
        ry2 = y2 + pad_y + ts_h

        canvas_w = rx2 + pad_x + 8
        canvas_h = ry2 + pad_y + 8
        try:
            total_w = self.winfo_toplevel().winfo_width() or root_w
        except:
            total_w = root_w
        desired_w = int(total_w * self.max_width_pct)
        if desired_w < canvas_w:
            canvas_w = desired_w
        self.canvas.config(width=canvas_w, height=canvas_h)

        self._rx1, self._rx2, self._ry1, self._ry2 = rx1, rx2, ry1, ry2

        if self.sender == 'user':
            c1, c2 = self.user_c1, self.user_c2
            text_color = self.text_dark
        else:
            c1, c2 = self.bot_c1, self.bot_c2
            text_color = self.text_dark

        # Draw background gradient (reduced steps for performance)
        draw_gradient_rect(self.canvas, rx1, ry1, rx2, ry2, c1, c2, steps=8, horizontal=False)
        self.canvas.create_rectangle(rx1+1, ry1+1, rx2-1, ry2-1, outline="#E0E0E0", width=1)
        self.canvas.tag_raise(self.text_id)

        ts_x = rx2 - pad_x - 4 if self.sender == 'user' else rx1 + pad_x + 4
        ts_anchor = 'se' if self.sender == 'user' else 'sw'
        self.canvas.create_text(ts_x, ry2 - 6, text=self.ts, font=self.ts_font, fill=self.ts_color, anchor=ts_anchor)

        # Event bindings
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-3>", lambda e: self.copy_to_clipboard())

        # Animate entry unless skipped (e.g., during resize)
        if not getattr(self, '_skip_fade', False):
            self._fade_in_text(self.text_id)
        self._skip_fade = False

    def refresh(self):
        """Force re-render of the bubble. Useful on window resize."""
        try:
            for it in self.canvas.find_all():
                try:
                    self.canvas.delete(it)
                except:
                    pass
            self._rendered = False
            # Skip animation for layout adjustments
            self._skip_fade = True
            self.after(10, self._render)
        except Exception:
            pass

    def _lighter(self, hexc, amount=0.10):
        r,g,b = hex_to_rgb(hexc)
        def clamp(v): return max(6, min(255, int(v)))
        nr = clamp(r + (255 - r) * amount)
        ng = clamp(g + (255 - g) * amount)
        nb = clamp(b + (255 - b) * amount)
        return rgb_to_hex((nr,ng,nb))

    def _on_enter(self, ev):
        self._hovering = True
        try:
            if not self.canvas.find_withtag(self._copy_tag):
                bx2 = int(self._rx2 - 10)
                bx1 = bx2 - 72
                by1 = int(self._ry1 + 8)
                by2 = by1 + 28
                base_fill = self.user_c2 if self.sender == 'user' else self.bot_c2
                fill = self._lighter(base_fill, 0.72)
                self.canvas.create_rectangle(bx1, by1, bx2, by2, outline="#2C2828", fill=fill, tags=(self._copy_tag,))
                self.canvas.create_text((bx1+bx2)//2, (by1+by2)//2, text="Copy", fill="#111111",
                                        font=(self.body_font.actual('family'), 9), tags=(self._copy_tag,))
                self.canvas.tag_bind(self._copy_tag, "<Button-1>", self.copy_to_clipboard)
        except Exception:
            pass
        self._start_hover_anim()

    def _on_leave(self, ev):
        self._hovering = False
        try:
            self.canvas.delete(self._copy_tag)
        except:
            pass
        if self._hover_job:
            self.after_cancel(self._hover_job); self._hover_job = None
        for it in self.canvas.find_all():
            if self.canvas.type(it) == "text":
                self.canvas.itemconfigure(it, fill=self.text_dark)

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
        steps = 6
        def tick(i):
            if i > steps:
                return
            start = 200
            end = 17
            val = int(start + (end - start) * (i / steps))
            hexc = rgb_to_hex((val, val, val))
            try:
                for it in self.canvas.find_all():
                    if self.canvas.type(it) == "text":
                        self.canvas.itemconfigure(it, fill=hexc)
            except:
                pass
            self.after(30, lambda: tick(i+1))
        tick(0)

# ---------- Main Application ----------

class ChatApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chatalogue — Your Smart Campus Assistant")
        
        # Maximize window by default
        try:
            self.state("zoomed")
        except Exception:
            pass

        # Set minimum size to prevent layout breakage
        self.minsize(900, 600)

        self.configure(bg="#2C2C2C")

        # Font selection
        self.pref_font = self._choose_font()

        # Header section
        self.header_h = 64
        self.header = tk.Canvas(self, height=self.header_h, highlightthickness=0, bg=self["bg"])
        self.header.pack(fill=tk.X, side=tk.TOP)
        draw_gradient_rect(self.header, 0, 0, 3000, self.header_h, "#C41E3A", "#F24C4C", steps=80, horizontal=True)

        # Initialize header UI elements
        self._build_header_buttons()

        # Track UI state for optimization
        self._last_inner_w = None
        self._chat_config_job = None
        self._jump_check_job = None

        # Main Scrollable Area
        main_wrap = tk.Frame(self, bg="#2C2C2C")
        main_wrap.pack(fill=tk.BOTH, expand=True)

        self.global_scrollbar = tk.Scrollbar(main_wrap, orient=tk.VERTICAL)
        self.global_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.center_container = tk.Frame(main_wrap, bg="#2C2C2C")
        self.center_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.chat_canvas = tk.Canvas(self.center_container, bg="#252626", highlightthickness=0,
                                     yscrollcommand=self.global_scrollbar.set)
        self.chat_frame = tk.Frame(self.chat_canvas, bg="#252626")
        self.chat_window_id = self.chat_canvas.create_window((0,0), window=self.chat_frame, anchor='nw')
        self.chat_canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=12, pady=12)
        self.chat_frame.bind("<Configure>", lambda e: self._on_chat_frame_configure())
        self.global_scrollbar.config(command=self.chat_canvas.yview)

        # Bindings
        self.bind("<Configure>", lambda e: self._on_resize())
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)

        # Input Area
        self.divider = tk.Frame(self, bg="#DDDDDD", height=1)
        self._build_input_area()

        # Chat History
        self.history = []
        self._welcome_text = " Welcome to Chatalogue, your campus companion! Ask me about courses, campus life, or support."
        self.add_bot(self._welcome_text)

        # Focus input on load
        self.jump_visible = False
        self.after(200, lambda: self.user_input.focus_set())

    def _on_chat_frame_configure(self):
        # Debounce configuration events to improve performance
        try:
            if self._chat_config_job:
                try:
                    self.after_cancel(self._chat_config_job)
                except Exception:
                    pass
            self._chat_config_job = self.after(60, self._handle_chat_frame_configure)
        except Exception:
            self._handle_chat_frame_configure()

    def _handle_chat_frame_configure(self):
        # Update scroll region and adjust bubble widths
        try:
            self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
            canvas_w = self.chat_canvas.winfo_width()
            inner_w = max(360, int(canvas_w * 0.90))
            self.chat_canvas.itemconfigure(self.chat_window_id, width=inner_w)
            
            # Avoid expensive redraws for minor pixel changes
            threshold = 8
            if self._last_inner_w is None or abs(inner_w - self._last_inner_w) >= threshold:
                for wrapper in self.chat_frame.winfo_children():
                    for child in wrapper.winfo_children():
                        if isinstance(child, ChatBubble):
                            child.refresh()
                self._last_inner_w = inner_w
        except Exception:
            pass
        finally:
            self._chat_config_job = None

    def _choose_font(self):
        pref = ["Poppins", "Inter", "Nunito Sans", "Segoe UI", "Helvetica"]
        avail = set(tkfont.families())
        return next((f for f in pref if f in avail), "Segoe UI")

    def _build_header_buttons(self):
        # Define titles
        self.full_title = "🤖 Chatalogue — Your Smart Campus Assistant"
        self.short_title = "🤖 Chatalogue"

        self._hdr_title = tk.Label(self.header, text=self.full_title,
                                   fg="#F2C94C", bg=self.header["bg"],
                                   font=(self.pref_font, 14, "bold"))

        # Right-side button buttons
        self.btn_frame = tk.Frame(self.header, bg=self.header["bg"], padx=6, pady=6)
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

        # Determine initial placement
        try:
            win_w = self.winfo_width() or self.winfo_screenwidth()
        except:
            win_w = self.winfo_screenwidth()

        left_padding = 18
        right_padding = 18

        # Clear existing windows if any
        try:
            if self._hdr_title_win:
                self.header.delete(self._hdr_title_win)
            if self._hdr_btn_win:
                self.header.delete(self._hdr_btn_win)
        except:
            pass

        # Place widgets on canvas
        self._hdr_title_win = self.header.create_window(left_padding, self.header_h // 2,
                                                         window=self._hdr_title, anchor='w', tags="hdr_title")

        self._hdr_btn_win = self.header.create_window(win_w - right_padding, self.header_h // 2,
                                                      window=self.btn_frame, anchor='e', tags="hdr_buttons")

        # Responsive adjustment: Shorten title if space is limited
        try:
            self.header.update_idletasks()
            btn_w = self.btn_frame.winfo_reqwidth() + right_padding
            title_req = self._hdr_title.winfo_reqwidth() + left_padding + 20  # safety buffer
            available = win_w - btn_w
            
            if available < title_req + 60:
                self._hdr_title.config(text=self.short_title)
                self._hdr_title.bind("<Enter>", lambda e: self._show_btn_tooltip(e, self.full_title))
                self._hdr_title.bind("<Leave>", lambda e: self._hide_btn_tooltip())
            else:
                self._hdr_title.config(text=self.full_title)
                try:
                    self._hdr_title.unbind("<Enter>")
                    self._hdr_title.unbind("<Leave>")
                except:
                    pass

            if win_w < 1000:
                fs = 12
            else:
                fs = 14
            self._hdr_title.config(font=(self.pref_font, fs, "bold"))
        except:
            pass

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
        self.input_bg = tk.Canvas(self.input_area, bg="#2C2C2C", height=80, highlightthickness=0)
        self.input_bg.pack(fill=tk.X, padx=18)
        self.input_bg.bind("<Configure>", lambda e: self._draw_input_bg())

        # Font for input to calculate line height
        self.input_font = tkfont.Font(family=self.pref_font, size=14)
        
        # Create the Text widget with proper styling
        self.user_input = tk.Text(self.input_area, height=2, wrap='word', font=self.input_font, 
                                  bg="#222222", fg="white", bd=0, padx=12, pady=10, 
                                  insertbackground='white')
        
        # Initial geometry - start with 2 lines to prevent text overlap
        line_h = self.input_font.metrics('linespace')
        init_h = max(60, 2 * line_h + 24)  # 2 lines + padding
        self.user_input.place(in_=self.input_bg, x=12, y=10, relwidth=0.76, height=init_h)

        # Bindings
        self.user_input.bind("<Return>", self._on_enter)
        self.user_input.bind("<Shift-Return>", self._insert_newline)
        self.user_input.bind("<Control-Return>", self._on_enter)
        self.user_input.bind("<KeyRelease>", lambda e: self._adjust_input_height())

        # Container for Scrape and Send buttons
        self.btn_holder = tk.Frame(self.input_bg, bg="#2C2C2C")
        self.btn_holder.place(in_=self.input_bg, relx=0.76, y=10, relwidth=0.24, height=init_h)

        # Scrape button
        self.scrape_btn = tk.Button(self.btn_holder, text="🔎 Scrape", bg="#F2C94C", fg="#111111", bd=0,
                                    activebackground="#E6B93A", cursor="hand2", command=self.on_scrape,
                                    font=(self.pref_font, 11, "bold"))
        self.scrape_btn.place(relx=0.0, rely=0.0, relwidth=0.5, relheight=1.0)
        self.scrape_btn.bind("<Enter>", lambda e: self.scrape_btn.config(relief='raised'))
        self.scrape_btn.bind("<Leave>", lambda e: self.scrape_btn.config(relief='flat'))
        self.scrape_btn.bind("<Enter>", lambda e: self._show_btn_tooltip(e, "Scrape the provided URL or default BU page"))
        self.scrape_btn.bind("<Leave>", lambda e: self._hide_btn_tooltip())

        # Send button
        self.send_btn = tk.Button(self.btn_holder, text="📤 Send", bg="#C41E3A", fg="white", bd=0,
                                  activebackground="#A3182E", cursor="hand2", command=self.on_send,
                                  font=(self.pref_font, 11, "bold"))
        self.send_btn.place(relx=0.5, rely=0.0, relwidth=0.5, relheight=1.0)
        self.send_btn.bind("<Enter>", lambda e: self.send_btn.config(relief='raised'))
        self.send_btn.bind("<Leave>", lambda e: self.send_btn.config(relief='flat'))
        self.send_btn.bind("<Enter>", lambda e: self._show_btn_tooltip(e, "Send message to Chatalogue"))
        self.send_btn.bind("<Leave>", lambda e: self._hide_btn_tooltip())

    def _draw_input_bg(self):
        c = self.input_bg; c.delete("all")
        w = c.winfo_width() or 900; h = c.winfo_height() or 64; pad = 6
        draw_gradient_rect(c, pad, pad, w-pad, h-pad, "#1F1F1F", "#2C2C2C", steps=18, horizontal=False)
        c.create_rectangle(pad+2, pad+2, w-pad-2, h-pad-2, outline="#333333")

    def _adjust_input_height(self, max_lines=6):
        """Dynamically adjust input box height based on content."""
        try:
            lines = int(self.user_input.index('end-1c').split('.')[0])
            lines = max(2, lines)  # Minimum 2 lines to prevent text overlap
            lines = min(max_lines, lines)
            line_h = self.input_font.metrics('linespace')
            new_h = lines * line_h + 24  # Increased padding for better visibility
            try:
                self.user_input.place_configure(height=new_h)
                self.btn_holder.place_configure(height=new_h)
            except Exception:
                pass
        except Exception:
            pass

    def _on_resize(self):
        win_w = self.winfo_width() or 1200
        cont_w = int(win_w * 0.70)
        if cont_w > 1400: cont_w = 1400
        height_avail = max(300, self.winfo_height() - self.header_h - 180)
        self.center_container.config(width=cont_w, height=height_avail)
        self.chat_canvas.config(width=cont_w, height=height_avail)

        # Reposition header elements
        try:
            left_padding = 18
            right_padding = 18
            
            if win_w < 900:
                fs = 12
            elif win_w < 1200:
                fs = 13
            else:
                fs = 14
            self._hdr_title.config(font=(self.pref_font, fs, "bold"))

            try:
                if getattr(self, '_hdr_title_win', None):
                    self.header.coords(self._hdr_title_win, left_padding, self.header_h // 2)
                else:
                    self._hdr_title_win = self.header.create_window(left_padding, self.header_h // 2,
                                                                     window=self._hdr_title, anchor='w', tags="hdr_title")
                if getattr(self, '_hdr_btn_win', None):
                    self.header.coords(self._hdr_btn_win, win_w - right_padding, self.header_h // 2)
                else:
                    self._hdr_btn_win = self.header.create_window(win_w - right_padding, self.header_h // 2,
                                                                   window=self.btn_frame, anchor='e', tags="hdr_buttons")
            except Exception:
                # Recreate if coordinate update fails
                try:
                    if getattr(self, '_hdr_title_win', None):
                        self.header.delete(self._hdr_title_win)
                    if getattr(self, '_hdr_btn_win', None):
                        self.header.delete(self._hdr_btn_win)
                    self._hdr_title_win = self.header.create_window(left_padding, self.header_h // 2,
                                                                     window=self._hdr_title, anchor='w', tags="hdr_title")
                    self._hdr_btn_win = self.header.create_window(win_w - right_padding, self.header_h // 2,
                                                                  window=self.btn_frame, anchor='e', tags="hdr_buttons")
                except Exception:
                    pass
        except Exception:
            # Fallback placement
            try:
                self.header.create_window(max(700, win_w//2 + 300), self.header_h // 2, window=self.btn_frame, anchor='w', tags="hdr_buttons")
            except:
                pass

        self._on_chat_frame_configure()
        # Ensure jump button position is updated on resize
        self._check_jump()


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
        
        # Check jump button visibility (throttled)
        try:
            if self._jump_check_job:
                try:
                    self.after_cancel(self._jump_check_job)
                except Exception:
                    pass
            self._jump_check_job = self.after(200, self._check_jump)
        except Exception:
            self._check_jump()

    def _check_jump(self):
        """
        Shows a 'jump to bottom' button if the user has scrolled up significantly.
        Hides it if they are near the bottom (within a ~150px threshold).
        Positions the button responsively centered over the chat area.
        """
        try:
            # Get current scroll position (fraction 0.0 to 1.0)
            y1, y2 = self.chat_canvas.yview()
            
            # Get total scrollable height in pixels
            bbox = self.chat_canvas.bbox("all")
            if not bbox:
                return
            scroll_h = bbox[3]
            
            # Calculate pixels hidden below the view
            # y2 is the bottom fraction visible; (1.0 - y2) is the hidden portion.
            hidden_pixels = scroll_h * (1.0 - y2)

            # Threshold: ~150 pixels (approx 3-4 lines/buffer)
            # If we are closer than this to the bottom, hide the button
            if hidden_pixels > 150:
                if not getattr(self, 'jump_visible', False):
                    # Define command to scroll to bottom AND re-check immediately (to hide button)
                    def jump_action():
                        self.chat_canvas.yview_moveto(1.0)
                        self._check_jump()

                    # Create button with a clean look (Square with arrow)
                    self.jump_btn = tk.Button(self, text="⬇", bg="#444444", fg="white", 
                                            bd=0, cursor="hand2", font=("Arial", 12, "bold"),
                                            command=jump_action)
                    self.jump_visible = True
                
                # Update placement (responsive)
                # We center the button relative to the chat canvas.
                # Calculate the X position of the canvas in the root window.
                cx = self.chat_canvas.winfo_rootx() - self.winfo_rootx()
                cw = self.chat_canvas.winfo_width()
                
                # Fallback if window isn't fully drawn yet
                if cw < 10: 
                    cw = self.winfo_width()
                    cx = 0 
                
                btn_w = 40
                btn_x = cx + (cw // 2) - (btn_w // 2)
                
                # Position above input area (approx 130px from bottom)
                btn_y = self.winfo_height() - 130
                
                self.jump_btn.place(x=btn_x, y=btn_y, width=btn_w, height=40)
                self.jump_btn.tkraise()
                
            else:
                # If near bottom, hide button
                if getattr(self, 'jump_visible', False):
                    try:
                        self.jump_btn.place_forget()
                    except:
                        pass
                    self.jump_visible = False
        except Exception:
            pass

    # ---- Messaging Logic ----

    def add_bot(self, text):
        ts = now_ts()
        self.history.append(f"Bot: {text}")
        wrapper = tk.Frame(self.chat_frame, bg="#252626")
        wrapper.pack(fill=tk.X, pady=4, anchor='w', padx=8)
        bubble = ChatBubble(wrapper, text=text, sender='bot', ts=ts, max_width_pct=0.65)
        bubble.pack(anchor='w', padx=(4, 40))
        # Auto-scroll to bottom
        self.after(50, lambda: self.chat_canvas.yview_moveto(1.0))

    def add_user(self, text):
        ts = now_ts()
        self.history.append(f"You: {text}")
        wrapper = tk.Frame(self.chat_frame, bg="#252626")
        wrapper.pack(fill=tk.X, pady=4, anchor='e', padx=8)
        bubble = ChatBubble(wrapper, text=text, sender='user', ts=ts, max_width_pct=0.65)
        bubble.pack(anchor='e', padx=(40, 4))
        self.after(50, lambda: self.chat_canvas.yview_moveto(1.0))

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

        # Show typing indicator
        typing_wrap = tk.Frame(self.chat_frame, bg="#252626")
        typing_wrap.pack(fill=tk.X, pady=4, anchor='w', padx=8)
        typing_bubble = ChatBubble(typing_wrap, text="🤖  Chatalogue is typing...", sender='bot', ts=now_ts(), max_width_pct=0.65)
        typing_bubble.pack(anchor='w', padx=(4, 40))

        stop_flag = {"stop": False}

        def call_backend(m):
            try:
                reply = chatalogue.chat_loop(m)
            except Exception:
                tb = traceback.format_exc()
                print("Backend exception:\n", tb)
                reply = "⚠️ Backend error: an exception occurred. Check logs for details."
            finally:
                stop_flag["stop"] = True
            
            self.after(200, lambda: self._replace_typing(typing_wrap, reply))
        t2 = threading.Thread(target=call_backend, args=(msg,), daemon=True)
        t2.start()

    def on_scrape(self):
        """Handle scraping URL via background thread."""
        try:
            default = "https://www.bu.edu/met/degrees-certificates/bs-computer-science/"
            url = simpledialog.askstring("Scrape URL", "Enter URL to scrape:", initialvalue=default)
            if not url:
                return

            try:
                msg = (
                    "Do you want to delete the existing scraper database before scraping?\n\n"
                    "Selecting 'Yes' will remove the file and start with a fresh database."
                )
                delete_db = messagebox.askyesno("Delete existing data?", msg)
            except Exception:
                delete_db = False

            def _run():
                try:
                    if delete_db:
                        try:
                            dbp = getattr(bu_scraper, 'DB_PATH', None)
                            if dbp and os.path.exists(dbp):
                                os.remove(dbp)
                                print(f"[INFO] Removed existing DB: {dbp}")
                        except Exception as e:
                            print("[WARN] Failed to remove DB file:", e)
                    bu_scraper.scrape(url)
                    self.after(100, lambda: messagebox.showinfo("Scrape complete", f"Scraped and saved data from:\n{url}"))
                except Exception as e:
                    tb = traceback.format_exc()
                    print("Scrape exception:\n", tb)
                    self.after(100, lambda: messagebox.showerror("Scrape error", str(e)))

            threading.Thread(target=_run, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _replace_typing(self, typing_wrapper, text):
        try:
            typing_wrapper.destroy()
        except:
            pass
        if not text:
            text = "Sorry — no response from backend."
        self.add_bot(text)

    # ---- Actions: Copy, Save, Clear ----

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


# ---------- Lifecycle Management ----------

def _on_app_close(app, conn):
    try:
        try:
            messagebox.showinfo("Shutting down", "Disconnecting local database and closing the app...")
        except Exception:
            pass

        if conn is not None:
            try:
                connections.disconnect_db(conn)
            except Exception:
                pass
    finally:
        try:
            app.destroy()
        except Exception:
            pass


def main():

    app = ChatApp()
    app.mainloop()


if __name__ == "__main__":
    main()