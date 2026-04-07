import os
import sys

# إصلاح خطأ AttributeError: 'NoneType' object has no attribute 'fileno' عند استخدام PyInstaller مع --noconsole
# حيث أن speedtest-cli يحاول الوصول إلى التدفقات القياسية التي تكون None في وضع noconsole
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r")

import customtkinter as ctk
import tkinter as tk
import math
import threading
import speedtest
import psutil
import time
import ctypes
from PIL import Image, ImageDraw
import pystray
from pynput import keyboard

def resource_path(relative_path):
    """ الحصول على المسار المطلق للموارد، يعمل في بيئة التطوير وPyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

class GhostSpeedTest(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- إعدادات النافذة الاحترافية ---
        self.overrideredirect(True)  # حذف شريط العنوان
        
        # تعيين أيقونة النافذة لتظهر في شريط المهام وفي قائمة التبديل (Alt+Tab)
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            
        # جعل النافذة تظهر في شريط المهام (Taskbar) رغم أنها بدون إطار (Windows Only)
        self.after(200, self.set_appwindow)
        
        # حساب الموقع في أسفل يمين الشاشة (فوق منطقة الإشعارات)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = 360
        window_height = 520
        # إزاحة قليلة من اليمين والأسفل (للمهمات)
        x = screen_width - window_width - 20
        y = screen_height - window_height - 60 
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.attributes("-alpha", 0.98) # شفافية عصرية
        self.attributes("-topmost", True) # دائما في المقدمة
        
        # جعل الخلفية شفافة للحصول على حواف مستديرة حقيقية
        self.attributes("-transparentcolor", "#010101")
        self.configure(fg_color="#010101")
        
        # الحاوية الرئيسية ذات الحواف المستديرة
        self.main_container = ctk.CTkFrame(self, fg_color="#050505", corner_radius=35, 
                                          border_width=1, border_color="#1a1a1a")
        self.main_container.pack(fill="both", expand=True, padx=5, pady=5)

        # الخروج بـ Esc
        self.bind('<Escape>', lambda e: self.withdraw()) # يختفي للمهات بدلاً من الخروج
        
        # لسحب النافذة
        self.main_container.bind("<ButtonPress-1>", self.start_move)
        self.main_container.bind("<B1-Motion>", self.do_move)

        # متغيرات الحالة
        self.stage = "READY"
        self.colors = {"READY": "#444444", "PING": "#FFCC00", "DOWNLOAD": "#00FFCC", "UPLOAD": "#8A2BE2"}
        self.current_val = 0.0
        self.target_val = 0.0
        
        # --- الواجهة الرسومية داخل الحاوية ---
        self.canvas = tk.Canvas(self.main_container, width=350, height=300, bg="#050505", highlightthickness=0)
        self.canvas.pack(pady=(20, 0))

        # رسم العداد (خلفية)
        self.bg_arc = self.canvas.create_arc(50, 40, 300, 290, start=-30, extent=240, 
                                            outline="#111111", width=15, style="arc")
        # العداد المضيء
        self.active_arc = self.canvas.create_arc(50, 40, 300, 290, start=210, extent=0, 
                                               outline=self.colors["READY"], width=18, style="arc")

        # الرقم المركزي
        self.lbl_main = tk.Label(self.main_container, text="0", font=("Consolas", 60, "bold"), 
                                fg="white", bg="#050505")
        self.lbl_main.place(relx=0.5, rely=0.32, anchor="center")

        # شبكة النتائج
        self.res_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.res_frame.pack(fill="x", padx=20, pady=5)

        self.stat_ping = self.create_stat_box(self.res_frame, "PING", self.colors["PING"])
        self.stat_dl = self.create_stat_box(self.res_frame, "DOWNLOAD", self.colors["DOWNLOAD"])
        self.stat_ul = self.create_stat_box(self.res_frame, "UPLOAD", self.colors["UPLOAD"])

        # زر التشغيل
        self.btn_run = ctk.CTkButton(self.main_container, text="START TEST", font=("Arial", 14, "bold"),
                                    fg_color="#111111", border_width=1, border_color="#333333",
                                    hover_color="#1a1a1a", corner_radius=22, height=45,
                                    command=self.start_engine)
        self.btn_run.pack(pady=20)
        
        self.btn_run.bind("<Enter>", self.on_btn_enter)
        self.btn_run.bind("<Leave>", self.on_btn_leave)

        # إعداد الاختصار العالمي F8 وأيقونة النظام
        self.setup_hotkey()
        self.setup_tray()
        
        self.update_loop()

    def create_stat_box(self, parent, label, color):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(side="left", expand=True)
        lbl = ctk.CTkLabel(box, text=label, font=("Arial", 9, "bold"), text_color="#555555")
        lbl.pack()
        val = ctk.CTkLabel(box, text="--", font=("Consolas", 16, "bold"), text_color=color)
        val.pack()
        return val

    def update_loop(self):
        # تنعيم الحركة
        self.current_val += (self.target_val - self.current_val) * 0.07
        extent = -(min(self.current_val, 100) / 100 * 240)
        self.canvas.itemconfig(self.active_arc, extent=extent, outline=self.colors.get(self.stage, "#FFFFFF"))
        self.lbl_main.config(text=f"{int(self.current_val)}", fg=self.colors.get(self.stage, "#FFFFFF"))
        self.after(16, self.update_loop)

    def on_btn_enter(self, e):
        self.btn_run.configure(font=("Arial", 16, "bold"), border_color="#00FFCC", border_width=2)

    def on_btn_leave(self, e):
        self.btn_run.configure(font=("Arial", 14, "bold"), border_color="#333333", border_width=1)

    def start_engine(self):
        self.btn_run.configure(state="disabled", text="RUNNING...")
        threading.Thread(target=self.run_speedtest, daemon=True).start()

    def run_speedtest(self):
        try:
            st = speedtest.Speedtest(secure=True)
            self.stage = "PING"
            server = st.get_best_server()
            self.target_val = server['latency']
            self.stat_ping.configure(text=f"{int(self.target_val)}")
            time.sleep(1)

            self.stage = "DOWNLOAD"
            self.target_val = 0
            monitor = threading.Thread(target=self.live_monitor, daemon=True)
            monitor.start()
            dl = st.download() / 1_000_000
            self.stat_dl.configure(text=f"{dl:.1f}")
            
            self.stage = "UPLOAD"
            ul = st.upload() / 1_000_000
            self.stat_ul.configure(text=f"{ul:.1f}")
        except Exception as e: print(f"Error: {e}")
        finally:
            self.stage = "READY"
            self.target_val = 0
            self.btn_run.configure(state="normal", text="START TEST")

    def live_monitor(self):
        last_recv = psutil.net_io_counters().bytes_recv
        history = []
        while self.stage in ["DOWNLOAD", "UPLOAD"]:
            time.sleep(0.2)
            curr_recv = psutil.net_io_counters().bytes_recv
            instant_val = ((curr_recv - last_recv) * 8) / (1024 * 1024 * 0.2)
            history.append(instant_val)
            if len(history) > 5: history.pop(0)
            self.target_val = sum(history) / len(history)
            last_recv = curr_recv

    # --- ميزات النظام الجديدة ---
    def setup_hotkey(self):
        def on_f8(): self.toggle_visibility()
        self.listener = keyboard.GlobalHotKeys({'<f8>': on_f8})
        self.listener.start()

    def setup_tray(self):
        def quit_app(icon, item):
            icon.stop()
            self.quit()
        
        def show_app(icon, item): self.toggle_visibility(force_show=True)

        # تحميل أيقونة خارجية من ملف icon.ico لضمان ظهورها في منطقة الإشعارات
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            image = Image.open(icon_path)
        else:
            # أيقونة احتياطية في حال عدم وجود الملف
            image = Image.new('RGB', (64, 64), (5, 5, 5))
            d = ImageDraw.Draw(image)
            d.ellipse((10, 10, 54, 54), fill="#00FFCC")
        
        menu = pystray.Menu(
            pystray.MenuItem("Show/Hide (F8)", show_app),
            pystray.MenuItem("Exit", quit_app)
        )
        self.icon = pystray.Icon("GhostSpeed", image, "Ghost Speed Test", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def toggle_visibility(self, force_show=False):
        if self.state() == "withdrawn" or force_show:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
        else:
            self.withdraw()

    def set_appwindow(self):
        # هذه الوظيفة تجبر نظام ويندوز على إظهار النافذة في شريط المهام رغم أنها بلا إطار (overrideredirect)
        try:
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = style & ~WS_EX_TOOLWINDOW
            style = style | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            
            # إعادة إظهار النافذة لتفعيل التغيير
            self.withdraw()
            self.after(10, self.deiconify)
        except Exception as e:
            print(f"Taskbar show error: {e}")

    def start_move(self, event): self.x, self.y = event.x, event.y
    def do_move(self, event):
        deltax, deltay = event.x - self.x, event.y - self.y
        self.geometry(f"+{self.winfo_x() + deltax}+{self.winfo_y() + deltay}")

if __name__ == "__main__":
    app = GhostSpeedTest()
    app.mainloop()