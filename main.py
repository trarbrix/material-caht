import flet as ft
import asyncio
import random
import requests
from datetime import datetime

API_URL = "https://developers.cloudflare.com/cloudflare-one/connections/connect-apps"

def main(page: ft.Page):
    page.title = "Material Chat"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.bgcolor = "#e0e0e0"
    page.window_width = 400
    page.window_height = 800

    THEMES = {
        "light": {"bg": "#ffffff", "text": "#1a1a1a", "accent": "#E0E0E0", "card": "#ffffff", "nav": "rgba(255,255,255,0.9)", "msg_out": "#1E1E1E", "msg_in": "#E0E0E0"},
        "dark": {"bg": "#121212", "text": "#ffffff", "accent": "#333333", "card": "#1E1E1E", "nav": "rgba(30,30,30,0.9)", "msg_out": "#6750A4", "msg_in": "#2A2A2A"},
    }

    current_theme = "light"
    current_user = "user"
    last_msg_id = 0
    
    # Состояния авторизации
    auth_mode = "login"
    auth_step = 1
    auth_tg = ""
    auth_code = ""
    auth_email = ""
    auth_phone = ""

    # Состояние настроек (какой экран открыт)
    settings_page = "main" 

    def create_wallpaper():
        wallpaper = ft.Stack(expand=True, fit=ft.StackFit.EXPAND)
        wallpaper.controls.append(
            ft.Container(
                expand=True,
                gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT, colors=["#ffffff", "#d4d4d4"] if current_theme == "light" else ["#1a1a1a", "#000000"])
            )
        )
        icons = [ft.Icons.CHAT, ft.Icons.CAMERA_ALT, ft.Icons.PHONE, ft.Icons.STAR, ft.Icons.IMAGE, ft.Icons.MIC]
        icon_color = ft.Colors.with_opacity(0.08, "black") if current_theme == "light" else ft.Colors.with_opacity(0.1, "white")
        
        for _ in range(40):
            icon = ft.Icon(
                random.choice(icons), size=random.randint(30, 70), color=icon_color,
                rotate=ft.Rotate(angle=random.uniform(0, 6.28)),
                left=f"{random.randint(0, 100)}%", top=f"{random.randint(0, 100)}%"
            )
            wallpaper.controls.append(icon)
        return wallpaper

    # ================= АВТОРИЗАЦИЯ =================
    async def send_code_async(e):
        nonlocal auth_step
        try:
            res = await asyncio.to_thread(requests.post, f"{API_URL}/send_code", json={"tg_username": auth_tg}, timeout=10)
            if res.json().get("status") != "error":
                auth_step = 2
                render_auth()
            else:
                page.snack_bar = ft.SnackBar(ft.Text("Нажми /start в боте!"), bgcolor="orange")
                page.snack_bar.open = True
                page.update()
        except: pass

    async def verify_code_async(e, code):
        nonlocal auth_step, auth_code
        try:
            res = await asyncio.to_thread(requests.post, f"{API_URL}/verify_code", json={"tg_username": auth_tg, "code": code}, timeout=10)
            if res.status_code == 200:
                auth_code = code
                auth_step = 3
                render_auth()
            else:
                page.snack_bar = ft.SnackBar(ft.Text("Неверный код!"), bgcolor="red")
                page.snack_bar.open = True
                page.update()
        except: pass

    async def do_login_async(e, password):
        nonlocal current_user
        try:
            payload = {"username": auth_tg, "tg_username": auth_tg, "password": password}
            res = await asyncio.to_thread(requests.post, f"{API_URL}/auth", json=payload, timeout=10)
            if res.status_code == 200:
                current_user = auth_tg
                await start_app()
            else:
                page.snack_bar = ft.SnackBar(ft.Text("Неверный пароль!"), bgcolor="red")
                page.snack_bar.open = True
                page.update()
        except: pass

    async def do_register_async(e, nick, password, password2):
        nonlocal current_user
        if password != password2:
            page.snack_bar = ft.SnackBar(ft.Text("Пароли не совпадают!"), bgcolor="red")
            page.snack_bar.open = True
            page.update()
            return
        try:
            payload = {"username": nick, "email": auth_email, "phone": auth_phone, "tg_username": auth_tg, "password": password}
            res = await asyncio.to_thread(requests.post, f"{API_URL}/auth", json=payload, timeout=10)
            if res.status_code == 200:
                current_user = nick
                await start_app()
            else:
                page.snack_bar = ft.SnackBar(ft.Text("Ошибка: возможно, ник занят"), bgcolor="red")
                page.snack_bar.open = True
                page.update()
        except: pass

    auth_container = ft.Column(expand=True, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    
    def switch_mode(e):
        nonlocal auth_mode, auth_step
        auth_mode = "login" if auth_mode == "register" else "register"
        auth_step = 1
        render_auth()

    def change_step(step):
        nonlocal auth_step
        auth_step = step
        render_auth()

    def render_auth():
        auth_container.controls.clear()
        if auth_step == 1:
            f_tg = ft.TextField(label="Ник в Telegram (без @)", width=300, value=auth_tg, bgcolor="#ffffff")
            def next_step(e):
                nonlocal auth_tg
                auth_tg = f_tg.value.replace("@", "").strip()
                if not auth_tg: return
                if auth_mode == "login": change_step(2)
                else: page.run_task(send_code_async, e)
            btn_next = ft.Button("Далее" if auth_mode == "login" else "Получить код", width=300, bgcolor="#1E1E1E", color="white")
            btn_next.on_click = next_step
            btn_switch = ft.TextButton("Нет аккаунта? Зарегистрироваться" if auth_mode=="login" else "Есть аккаунт? Войти", on_click=switch_mode)
            
            title = "Вход" if auth_mode=="login" else "Регистрация"
            auth_container.controls = [ft.Text(title, size=32, weight=ft.FontWeight.BOLD, color="#1E1E1E"), f_tg, btn_next, btn_switch]
            
        elif auth_step == 2:
            if auth_mode == "login":
                f_pass = ft.TextField(label="Пароль", password=True, width=300, bgcolor="#ffffff")
                btn = ft.Button("Войти", width=300, bgcolor="#1E1E1E", color="white", on_click=lambda e: page.run_task(do_login_async, e, f_pass.value))
                auth_container.controls = [ft.Text("Введите пароль", size=32, color="#1E1E1E"), f_pass, btn, ft.TextButton("Назад", on_click=lambda e: change_step(1))]
            else:
                f_code = ft.TextField(label="Код из ТГ", width=300, bgcolor="#ffffff")
                btn = ft.Button("Подтвердить", width=300, bgcolor="#1E1E1E", color="white", on_click=lambda e: page.run_task(verify_code_async, e, f_code.value))
                auth_container.controls = [ft.Text("Введите код", size=32, color="#1E1E1E"), f_code, btn, ft.TextButton("Назад", on_click=lambda e: change_step(1))]
                
        elif auth_step == 3:
            f_nick = ft.TextField(label="Ник в чате", width=300, bgcolor="#ffffff")
            f_email = ft.TextField(label="Почта (Опц.)", width=300, bgcolor="#ffffff")
            f_phone = ft.TextField(label="Телефон (Опц.)", width=300, bgcolor="#ffffff")
            f_pass = ft.TextField(label="Пароль", password=True, width=300, bgcolor="#ffffff")
            f_pass2 = ft.TextField(label="Повторите пароль", password=True, width=300, bgcolor="#ffffff")
            def reg_handler(e):
                nonlocal auth_email, auth_phone
                auth_email, auth_phone = f_email.value, f_phone.value
                page.run_task(do_register_async, e, f_nick.value, f_pass.value, f_pass2.value)
            btn = ft.Button("Создать", width=300, bgcolor="#1E1E1E", color="white", on_click=reg_handler)
            auth_container.controls = [ft.Text("Создание аккаунта", size=32, color="#1E1E1E"), f_nick, f_email, f_phone, f_pass, f_pass2, btn]
        page.update()

    auth_view = ft.Stack([
        ft.Container(expand=True, gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT, colors=["#ffffff", "#d4d4d4"])),
        ft.Container(content=auth_container, alignment=ft.Alignment.CENTER, expand=True)
    ], expand=True)

    # ================= ОСНОВНОЕ ПРИЛОЖЕНИЕ =================
    main_app_view = ft.Column(visible=False, expand=True)
    
    top_bar = ft.Container(content=ft.Row([ft.Text("Material Chat", size=22, weight=ft.FontWeight.BOLD, color="#1E1E1E")]), padding=15, bgcolor=ft.Colors.TRANSPARENT)
    bottom_nav = ft.NavigationBar(selected_index=0, on_change=lambda e: switch_tab(e.control.selected_index), bgcolor=THEMES[current_theme]["nav"], destinations=[
        ft.NavigationBarDestination(icon=ft.Icons.CHAT_BUBBLE_OUTLINE, label="Чаты"),
        ft.NavigationBarDestination(icon=ft.Icons.PERSON_OUTLINE, label="Профиль"),
        ft.NavigationBarDestination(icon=ft.Icons.SETTINGS, label="Настройки"),             
    ])

    chat_list_view = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True, spacing=10)
    profile_view = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True, spacing=10, visible=False)
    settings_view = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True, spacing=10, visible=False)
    active_chat_view = ft.Column(expand=True, visible=False) 

    chat_messages = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True, spacing=10)
    msg_input = ft.TextField(hint_text="Сообщение...", expand=True, on_submit=lambda e: send_message(e), bgcolor="rgba(255,255,255,0.8)")

    content_stack = ft.Stack(expand=True)
    content_stack.controls = [create_wallpaper(), chat_list_view, profile_view, settings_view, active_chat_view]

    main_app_view.controls = [top_bar, content_stack, bottom_nav]

    # --- ВЫБОР ФАЙЛА ---
    def select_file_tkinter():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_path = filedialog.askopenfilename(title="Выберите картинку", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        root.destroy()
        return file_path

    def upload_job(file_path, file_name):
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f)}
            res = requests.post(f"{API_URL}/upload", files=files)
            return res.json()

    async def pick_file_async(e):
        try:
            file_path = await asyncio.to_thread(select_file_tkinter)
            if not file_path: return
            file_name = file_path.split("/")[-1]
            page.snack_bar = ft.SnackBar(ft.Text(f"Загрузка..."))
            page.snack_bar.open = True
            page.update()

            data = await asyncio.to_thread(upload_job, file_path, file_name)
            requests.post(f"{API_URL}/messages", json={"chat_id": "global", "sender": current_user, "media_url": data["url"], "msg_type": "image"})
            load_messages()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Ошибка: {ex}"), bgcolor="red")
            page.snack_bar.open = True
            page.update()

    # --- СООБЩЕНИЯ ---
    def render_messages(messages):
        chat_messages.controls.clear()
        theme = THEMES[current_theme]
        for msg in messages:
            is_out = msg['sender'] == current_user
            if msg.get('media_url'):
                content = ft.Column([ft.Image(src=msg['media_url'], width=200, border_radius=10), ft.Text(msg['text'] or "", color="white" if is_out else theme["text"])])
            else:
                content = ft.Text(msg['text'] or "", color="white" if is_out else theme["text"])
                
            chat_messages.controls.append(
                ft.Container(
                    content=ft.Row([ft.Container(content=content, padding=10, bgcolor=theme["msg_out"] if is_out else theme["msg_in"], border_radius=15)], alignment=ft.MainAxisAlignment.END if is_out else ft.MainAxisAlignment.START),
                    margin=ft.Margin.only(bottom=5)
                )
            )
        page.update()
        chat_messages.scroll_to(offset=-1, duration=300)

    def send_message(e):
        if msg_input.value:
            text = msg_input.value
            msg_input.value = ""
            page.update()
            requests.post(f"{API_URL}/messages", json={"chat_id": "global", "sender": current_user, "text": text, "msg_type": "text"})
            load_messages()

    def load_messages():
        try:
            res = requests.get(f"{API_URL}/messages/global")
            if res.status_code == 200: render_messages(res.json())
        except: pass

    async def update_loop():
        nonlocal last_msg_id
        while True:
            if main_app_view.visible and active_chat_view.visible:
                try:
                    res = await asyncio.to_thread(requests.get, f"{API_URL}/messages/global")
                    if res.status_code == 200:
                        msgs = res.json()
                        if msgs:
                            new_msg = msgs[-1]
                            if new_msg['id'] > last_msg_id:
                                last_msg_id = new_msg['id']
                            render_messages(msgs)
                except: pass
            await asyncio.sleep(2)

    # --- ЧАТ ---
    input_row = ft.Row([
        ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE, on_click=lambda e: page.run_task(pick_file_async, e)),
        msg_input, 
        ft.IconButton(icon=ft.Icons.SEND, on_click=send_message)
    ])
    active_chat_view.controls = [chat_messages, ft.Container(content=input_row, padding=10, bgcolor=THEMES[current_theme]["nav"])]

    def open_chat(e):
        chat_list_view.visible = False
        active_chat_view.visible = True
        top_bar.content = ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=close_chat, icon_color=THEMES[current_theme]["text"]), ft.Text("Global Chat", size=20, color=THEMES[current_theme]["text"])])
        bottom_nav.visible = False
        load_messages()
        page.update()

    def close_chat(e):
        active_chat_view.visible = False
        chat_list_view.visible = True
        top_bar.content = ft.Row([ft.Text("Material Chat", size=22, weight=ft.FontWeight.BOLD, color=THEMES[current_theme]["text"])])
        bottom_nav.visible = True
        apply_theme()

    # --- ПРОФИЛЬ ---
    def build_profile():
        theme = THEMES[current_theme]
        profile_view.controls = [ft.Container(content=ft.Column([
            ft.CircleAvatar(radius=50, bgcolor=theme["msg_out"], content=ft.Text(current_user[0].upper(), size=40, color="white")),
            ft.Text(f"@{current_user}", size=24, weight=ft.FontWeight.BOLD, color=theme["text"]),
            ft.Text("Люблю Python и Vibe Coding", size=14, color="gray"),
            ft.Divider(color=theme["accent"]), 
            ft.Text("Подарки (Скоро)", size=18, color=theme["text"]),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15), padding=20, bgcolor=theme["card"], border_radius=20, margin=20)]

    # --- НАСТРОЙКИ (С ПОДЭКРАНАМИ) ---
    def open_settings_subpage(page_name):
        nonlocal settings_page
        settings_page = page_name
        build_settings()
        # Меняем верхнюю панель на кнопку "Назад"
        top_bar.content = ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=close_settings_subpage, icon_color=THEMES[current_theme]["text"]), ft.Text("Настройки", size=20, color=THEMES[current_theme]["text"])])
        page.update()

    def close_settings_subpage(e):
        nonlocal settings_page
        settings_page = "main"
        build_settings()
        # Возвращаем обычную верхнюю панель
        top_bar.content = ft.Row([ft.Text("Material Chat", size=22, weight=ft.FontWeight.BOLD, color=THEMES[current_theme]["text"])])
        page.update()

    def build_settings():
        theme = THEMES[current_theme]
        settings_view.controls.clear()

        if settings_page == "main":
            settings_view.controls = [
                ft.Container(
                    content=ft.Column([
                        ft.ListTile(leading=ft.Icon(ft.Icons.NOTIFICATIONS, color=theme["text"]), title=ft.Text("Уведомления", color=theme["text"]), on_click=lambda e: open_settings_subpage("notifications")),
                        ft.ListTile(leading=ft.Icon(ft.Icons.LOCK, color=theme["text"]), title=ft.Text("Конфиденциальность", color=theme["text"]), on_click=lambda e: open_settings_subpage("privacy")),
                        ft.ListTile(leading=ft.Icon(ft.Icons.FOLDER, color=theme["text"]), title=ft.Text("Папки с чатами", color=theme["text"]), on_click=lambda e: open_settings_subpage("folders")),
                        ft.ListTile(leading=ft.Icon(ft.Icons.LANGUAGE, color=theme["text"]), title=ft.Text("Язык", color=theme["text"]), on_click=lambda e: open_settings_subpage("language")),
                        ft.Divider(color=theme["accent"]),
                        ft.Text("Оформление", size=16, color=theme["text"], weight=ft.FontWeight.BOLD),
                        ft.RadioGroup(content=ft.Column([ft.Radio(value="light", label="Светлая"), ft.Radio(value="dark", label="Темная")]), value=current_theme, on_change=change_theme),
                        ft.Divider(color=theme["accent"]),
                        ft.Button("Выйти из аккаунта", bgcolor="red", color="white", on_click=logout)
                    ]),
                    padding=20, bgcolor=theme["card"], border_radius=20, margin=20
                )
            ]
        elif settings_page == "notifications":
            settings_view.controls = [ft.Container(content=ft.Column([
                ft.ListTile(leading=ft.Icon(ft.Icons.NOTIFICATIONS, color=theme["text"]), title=ft.Text("Личные сообщения", color=theme["text"]), trailing=ft.Switch(value=True, active_color=theme["msg_out"])),
                ft.ListTile(leading=ft.Icon(ft.Icons.GROUPS, color=theme["text"]), title=ft.Text("Группы", color=theme["text"]), trailing=ft.Switch(value=True, active_color=theme["msg_out"])),
                ft.ListTile(leading=ft.Icon(ft.Icons.VIBRATION, color=theme["text"]), title=ft.Text("Вибрация", color=theme["text"]), trailing=ft.Switch(value=True, active_color=theme["msg_out"])),
            ]), padding=20, bgcolor=theme["card"], border_radius=20, margin=20)]
        elif settings_page == "privacy":
            settings_view.controls = [ft.Container(content=ft.Column([
                ft.ListTile(leading=ft.Icon(ft.Icons.PHONE, color=theme["text"]), title=ft.Text("Номер телефона", color=theme["text"]), subtitle=ft.Text("Никто", color="gray")),
                ft.ListTile(leading=ft.Icon(ft.Icons.VISIBILITY_OFF, color=theme["text"]), title=ft.Text("Блокировка", color=theme["text"]), subtitle=ft.Text("0 пользователей", color="gray")),
                ft.ListTile(leading=ft.Icon(ft.Icons.SECURITY, color=theme["text"]), title=ft.Text("Двухэтапная проверка", color=theme["text"]), subtitle=ft.Text("Включена", color="gray")),
            ]), padding=20, bgcolor=theme["card"], border_radius=20, margin=20)]
        elif settings_page == "folders":
            settings_view.controls = [ft.Container(content=ft.Column([
                ft.Text("У вас пока нет папок", color="gray"),
                ft.Button("Создать папку", icon=ft.Icons.ADD, bgcolor=theme["msg_out"], color="white")
            ]), padding=20, bgcolor=theme["card"], border_radius=20, margin=20)]
        elif settings_page == "language":
            settings_view.controls = [ft.Container(content=ft.Column([
                ft.RadioGroup(content=ft.Column([ft.Radio(value="ru", label="Русский"), ft.Radio(value="en", label="English")]), value="ru"),
            ]), padding=20, bgcolor=theme["card"], border_radius=20, margin=20)]
            
        page.update()

    def switch_tab(idx):
        nonlocal settings_page
        chat_list_view.visible = (idx == 0)
        profile_view.visible = (idx == 1)
        settings_view.visible = (idx == 2)
        
        if idx == 1: 
            build_profile()
            top_bar.content = ft.Row([ft.Text("Материал Чат", size=22, weight=ft.FontWeight.BOLD, color=THEMES[current_theme]["text"])])
        if idx == 2: 
            settings_page = "main" # Сбрасываем на главную при переходе
            build_settings()
            top_bar.content = ft.Row([ft.Text("Материал Чат", size=22, weight=ft.FontWeight.BOLD, color=THEMES[current_theme]["text"])])
        if idx == 0:
            top_bar.content = ft.Row([ft.Text("Материал Чат", size=22, weight=ft.FontWeight.BOLD, color=THEMES[current_theme]["text"])])
            
        page.update()

    def logout(e):
        main_app_view.visible = False
        auth_view.visible = True
        page.update()

    page.add(ft.Stack([auth_view, main_app_view], expand=True))

    def apply_theme():
        theme = THEMES[current_theme]
        top_bar.bgcolor = ft.Colors.TRANSPARENT
        bottom_nav.bgcolor = theme["nav"]
        
        if isinstance(top_bar.content, ft.Row):
            for ctrl in top_bar.content.controls:
                if isinstance(ctrl, ft.Text): ctrl.color = theme["text"]
                if isinstance(ctrl, ft.IconButton): ctrl.icon_color = theme["text"]

        content_stack.controls[0] = create_wallpaper() # Обновляем обои
        page.update()

    def change_theme(e):
        nonlocal current_theme
        current_theme = e.control.value
        page.theme_mode = ft.ThemeMode.DARK if current_theme == "dark" else ft.ThemeMode.LIGHT
        apply_theme()

    async def start_app():
        auth_view.visible = False
        main_app_view.visible = True
        
        content_stack.controls[0] = create_wallpaper()
        
        chat_list_view.controls = [ft.Container(content=ft.Row([ft.CircleAvatar(content=ft.Text("G")), ft.Text("Global Chat", size=16, color=THEMES[current_theme]["text"])]), padding=15, bgcolor=THEMES[current_theme]["card"], border_radius=15, margin=10, on_click=lambda e: open_chat(e))]
        apply_theme()
        page.update()
        page.run_task(update_loop)

    render_auth()

ft.run(main)
