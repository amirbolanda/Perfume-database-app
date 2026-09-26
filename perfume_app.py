"""Perfume Information Database.

A desktop app built with Tkinter and SQLite. You can store perfume details,
search them by name / brand / accord, translate descriptions from English to
Persian, and look up extra information on Google.

Run:  python perfume_app.py
"""

import hashlib
import hmac
import json
import os
import queue
import sqlite3
import threading
import tkinter as tk
import webbrowser
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from urllib.parse import quote_plus

from deep_translator import GoogleTranslator
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "perfumes.db"
AUTH_PATH = BASE_DIR / "auth.json"  # created on first run, never commit it

CURRENT_YEAR = datetime.now().year
BG = "lightcyan"

BRANDS = ["Chanel", "Dior", "Hermes", "Creed", "Tom Ford", "Gucci",
          "Yves Saint Laurent", "Carolina Herrera"]
GENDERS = ["Female", "Male", "Unisex"]
VOLUMES = ["30ml", "50ml", "75ml", "90ml", "100ml", "120ml", "125ml", "200ml"]
ACCORDS = ["Aromatic", "Chypre", "Floral", "Citrus", "Woody", "Oriental", "Leather"]
TYPES = ["Eau de Cologne", "Eau de Toilette", "Eau de Parfum", "Perfume", "Pure Perfume"]

FIELDS = ("name", "brand", "gender", "volume", "accord",
          "perfume_type", "year", "description")


# --------------------------------------------------------------------------
# Login (credentials are stored as a salted hash, never in the source code)
# --------------------------------------------------------------------------
def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000).hex()


def create_account(username, password):
    salt = os.urandom(16)
    data = {
        "username": username,
        "salt": salt.hex(),
        "hash": _hash_password(password, salt),
    }
    AUTH_PATH.write_text(json.dumps(data), encoding="utf-8")


def verify_login(username, password):
    try:
        data = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        salt = bytes.fromhex(data["salt"])
        saved_user = data["username"].encode("utf-8")
        saved_hash = data["hash"].encode("utf-8")
    except (OSError, ValueError, KeyError):
        return False
    same_user = hmac.compare_digest(saved_user, username.encode("utf-8"))
    same_pass = hmac.compare_digest(saved_hash, _hash_password(password, salt).encode("utf-8"))
    return same_user and same_pass


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS perfume (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL COLLATE NOCASE,
    brand        TEXT NOT NULL COLLATE NOCASE,
    gender       TEXT NOT NULL,
    volume       TEXT NOT NULL,
    accord       TEXT NOT NULL,
    perfume_type TEXT NOT NULL,
    year         INTEGER NOT NULL,
    description  TEXT NOT NULL,
    UNIQUE (name, brand, volume, perfume_type)
)
"""


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


def add_perfume(record):
    """Insert a perfume and return its id. Raises sqlite3.IntegrityError on duplicates."""
    with closing(db_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO perfume (name, brand, gender, volume, accord, "
            "perfume_type, year, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(record[f] for f in FIELDS),
        )
        return cur.lastrowid


def update_perfume(perfume_id, record):
    with closing(db_connect()) as conn, conn:
        conn.execute(
            "UPDATE perfume SET name=?, brand=?, gender=?, volume=?, accord=?, "
            "perfume_type=?, year=?, description=? WHERE id=?",
            tuple(record[f] for f in FIELDS) + (perfume_id,),
        )


def delete_perfume(perfume_id):
    with closing(db_connect()) as conn, conn:
        conn.execute("DELETE FROM perfume WHERE id=?", (perfume_id,))


def search_perfumes(term=""):
    """Partial, case-insensitive search in name, brand and accord.
    An empty term returns every perfume."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{escaped}%"
    with closing(db_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM perfume "
            "WHERE name LIKE ? ESCAPE '\\' OR brand LIKE ? ESCAPE '\\' "
            "OR accord LIKE ? ESCAPE '\\' ORDER BY brand, name",
            (like, like, like),
        ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------
# Google lookup (Selenium)
# --------------------------------------------------------------------------
def google_lookup(query, max_results=6):
    """Return a list of (title, url) pairs from the first Google results page."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    browser = webdriver.Chrome(options=options)
    try:
        browser.get("https://www.google.com/search?q=" + quote_plus(query))
        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h3"))
        )
        results = []
        for heading in browser.find_elements(By.CSS_SELECTOR, "h3"):
            title = heading.text.strip()
            if not title:
                continue
            try:
                url = heading.find_element(By.XPATH, "./ancestor::a").get_attribute("href")
            except Exception:
                continue
            results.append((title, url))
            if len(results) >= max_results:
                break
        return results
    finally:
        browser.quit()


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
def login_window():
    """Show the login (or first-run 'create account') window.
    Returns True when the user logged in successfully."""
    first_run = not AUTH_PATH.exists()
    result = {"ok": False}

    win = tk.Tk()
    win.geometry("300x290" if first_run else "300x230")
    win.resizable(False, False)
    win.config(bg=BG)
    win.title("Create account" if first_run else "Login")

    tk.Label(win, text="Username:", bg=BG).pack(pady=(15, 3))
    entry_user = tk.Entry(win)
    entry_user.pack()

    tk.Label(win, text="Password:", bg=BG).pack(pady=(10, 3))
    entry_pass = tk.Entry(win, show="*")
    entry_pass.pack()

    entry_confirm = None
    if first_run:
        tk.Label(win, text="Confirm password:", bg=BG).pack(pady=(10, 3))
        entry_confirm = tk.Entry(win, show="*")
        entry_confirm.pack()

    lbl_error = tk.Label(win, text="", fg="red", bg=BG)

    def submit(event=None):
        username = entry_user.get().strip()
        password = entry_pass.get()
        if first_run:
            if not username or len(password) < 6:
                lbl_error.config(text="Enter a username and a 6+ character password")
                return
            if password != entry_confirm.get():
                lbl_error.config(text="Passwords do not match")
                return
            create_account(username, password)
        elif not verify_login(username, password):
            lbl_error.config(text="Invalid username or password")
            return
        result["ok"] = True
        win.destroy()

    tk.Button(win, text="Create account" if first_run else "Login",
              command=submit, fg="red").pack(pady=15)
    lbl_error.pack()
    tk.Label(win, text="© Design by Amir Bolanda", bg=BG).pack(side="bottom", pady=5)

    win.bind("<Return>", submit)
    entry_user.focus_set()
    win.mainloop()
    return result["ok"]


def main_window():
    root = tk.Tk()
    root.geometry("900x690")
    root.resizable(False, False)
    root.config(bg=BG)
    root.title("Perfume Information")

    label_font = ("Arial", 11, "bold")

    # Form variables
    name_var = tk.StringVar()
    brand_var = tk.StringVar()
    gender_var = tk.StringVar()
    vol_var = tk.StringVar()
    accord_var = tk.StringVar()
    type_var = tk.StringVar()
    year_var = tk.StringVar()
    search_var = tk.StringVar()
    status_var = tk.StringVar(value="Ready")

    state = {"id": None}   # id of the perfume currently loaded in the form
    rows_by_id = {}        # search results currently shown in the table

    def label(text, x, y, color="darkblue"):
        tk.Label(root, text=text, bg=BG, font=label_font, fg=color).place(x=x, y=y)

    # ---- helpers ---------------------------------------------------------
    def set_status(message):
        status_var.set(message)

    def run_in_background(work, on_done):
        """Run work() in a thread so the window doesn't freeze, then call
        on_done(result, error) back in the Tk thread."""
        q = queue.Queue()

        def worker():
            try:
                q.put((work(), None))
            except Exception as exc:  # noqa: BLE001 - reported to the user
                q.put((None, exc))

        def poll():
            try:
                result, error = q.get_nowait()
            except queue.Empty:
                root.after(150, poll)
                return
            on_done(result, error)

        threading.Thread(target=worker, daemon=True).start()
        poll()

    def read_form():
        record = {
            "name": name_var.get().strip(),
            "brand": brand_var.get().strip(),
            "gender": gender_var.get().strip(),
            "volume": vol_var.get().strip(),
            "accord": accord_var.get().strip(),
            "perfume_type": type_var.get().strip(),
            "year": year_var.get().strip(),
            "description": t_desc.get("1.0", tk.END).strip(),
        }
        if not all(record.values()):
            raise ValueError("All fields must be filled out.")
        try:
            record["year"] = int(record["year"])
        except ValueError:
            raise ValueError("Year must be a number.") from None
        if not 1900 <= record["year"] <= CURRENT_YEAR:
            raise ValueError(f"Year must be between 1900 and {CURRENT_YEAR}.")
        return record

    def fill_form(rec):
        name_var.set(rec["name"])
        brand_var.set(rec["brand"])
        gender_var.set(rec["gender"])
        vol_var.set(rec["volume"])
        accord_var.set(rec["accord"])
        type_var.set(rec["perfume_type"])
        year_var.set(str(rec["year"]))
        t_desc.delete("1.0", tk.END)
        t_desc.insert("1.0", rec["description"])

    def show_translation(text):
        t_out.config(state="normal")
        t_out.delete("1.0", tk.END)
        t_out.insert("1.0", text, "rtl")
        t_out.config(state="disabled")

    def clear_form():
        for var in (name_var, brand_var, gender_var, vol_var,
                    accord_var, type_var, year_var):
            var.set("")
        t_desc.delete("1.0", tk.END)
        show_translation("")
        state["id"] = None
        tree.selection_remove(tree.selection())
        set_status("Form cleared")

    # ---- actions ---------------------------------------------------------
    def do_search(event=None):
        rows = search_perfumes(search_var.get().strip())
        tree.delete(*tree.get_children())
        rows_by_id.clear()
        for row in rows:
            rows_by_id[row["id"]] = row
            tree.insert("", tk.END, iid=str(row["id"]), values=(
                row["name"], row["brand"], row["gender"],
                row["volume"], row["perfume_type"], row["year"]))
        set_status(f"{len(rows)} perfume(s) found" if rows else "No perfume found")

    def on_select(event=None):
        selected = tree.selection()
        if selected:
            rec = rows_by_id[int(selected[0])]
            state["id"] = rec["id"]
            fill_form(rec)
            set_status(f"Loaded: {rec['brand']} {rec['name']}")

    def save():
        try:
            record = read_form()
            state["id"] = add_perfume(record)
        except ValueError as err:
            messagebox.showwarning("Check the form", str(err))
            return
        except sqlite3.IntegrityError:
            messagebox.showwarning(
                "Already saved",
                "This perfume (same name, brand, volume and type) already exists.")
            return
        except sqlite3.Error as err:
            messagebox.showerror("Database error", str(err))
            return
        do_search()
        set_status(f"Saved: {record['brand']} {record['name']}")

    def update():
        if state["id"] is None:
            messagebox.showinfo("Update", "Select a perfume from the table first.")
            return
        try:
            update_perfume(state["id"], read_form())
        except ValueError as err:
            messagebox.showwarning("Check the form", str(err))
            return
        except sqlite3.IntegrityError:
            messagebox.showwarning(
                "Duplicate", "Another perfume with the same name, brand, volume and type exists.")
            return
        except sqlite3.Error as err:
            messagebox.showerror("Database error", str(err))
            return
        do_search()
        set_status("Perfume updated")

    def delete():
        if state["id"] is None:
            messagebox.showinfo("Delete", "Select a perfume from the table first.")
            return
        if not messagebox.askyesno("Delete", "Delete the selected perfume?"):
            return
        try:
            delete_perfume(state["id"])
        except sqlite3.Error as err:
            messagebox.showerror("Database error", str(err))
            return
        clear_form()
        do_search()
        set_status("Perfume deleted")

    def translate():
        text = t_desc.get("1.0", tk.END).strip()
        if not text:
            set_status("Write a description first")
            return
        set_status("Translating...")

        def done(result, error):
            if error:
                set_status(f"Translation failed: {error}")
            else:
                show_translation(result)
                set_status("Translated to Persian")

        run_in_background(
            lambda: GoogleTranslator(source="en", target="fa").translate(text), done)

    def more_info():
        name = name_var.get().strip()
        if not name:
            messagebox.showinfo("More information", "Enter a perfume name first.")
            return
        query = " ".join(part for part in (brand_var.get().strip(), name, "perfume") if part)
        set_status("Searching Google...")

        def done(results, error):
            if error or not results:
                set_status("Couldn't read Google results - opened your browser instead")
                webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
                return
            set_status(f"{len(results)} Google results for: {query}")
            window = tk.Toplevel(root)
            window.title(f"Google: {query}")
            window.geometry("640x360")
            box = scrolledtext.ScrolledText(window, wrap="word")
            box.pack(fill="both", expand=True)
            for i, (title, url) in enumerate(results, 1):
                box.insert(tk.END, f"{i}. {title}\n   {url}\n\n")
            box.config(state="disabled")

        run_in_background(lambda: google_lookup(query), done)

    # ---- form ------------------------------------------------------------
    label("Name:", 5, 5)
    tk.Entry(root, width=50, textvariable=name_var).place(x=80, y=9)
    label("Company:", 420, 5)
    ttk.Combobox(root, width=50, textvariable=brand_var, values=BRANDS).place(x=540, y=9)

    label("Gender:", 5, 70)
    ttk.Combobox(root, width=47, textvariable=gender_var, values=GENDERS).place(x=80, y=73)
    label("Vol:", 420, 70)
    ttk.Combobox(root, width=50, textvariable=vol_var, values=VOLUMES).place(x=540, y=73)

    label("Type:", 5, 135)
    for text, x in zip(TYPES, (80, 270, 420, 600, 750)):
        tk.Radiobutton(root, text=text, variable=type_var, value=text,
                       bg=BG, fg="hotpink").place(x=x, y=135)

    label("Year:", 5, 200)
    tk.Spinbox(root, from_=1900, to=CURRENT_YEAR, width=49,
               textvariable=year_var).place(x=80, y=204)
    label("Accords:", 420, 200)
    ttk.Combobox(root, width=50, textvariable=accord_var, values=ACCORDS).place(x=537, y=203)

    label("Description:", 5, 270, "darkorange")
    t_desc = tk.Text(root, width=48, height=8, wrap="word")
    t_desc.place(x=5, y=300)
    tk.Button(root, text="Translate", fg="red", command=translate).place(x=420, y=350)
    label("Persian translation:", 500, 270, "darkorange")
    t_out = tk.Text(root, width=48, height=8, wrap="word", state="disabled")
    t_out.tag_configure("rtl", justify="right")
    t_out.place(x=500, y=300)

    # ---- search ----------------------------------------------------------
    label("Search:", 5, 455)
    entry_search = tk.Entry(root, width=62, textvariable=search_var)
    entry_search.place(x=85, y=459)
    entry_search.bind("<Return>", do_search)
    tk.Button(root, text="Search (empty = show all)", fg="red", width=22,
              command=do_search).place(x=650, y=453)

    columns = ("name", "brand", "gender", "volume", "type", "year")
    tree = ttk.Treeview(root, columns=columns, show="headings", height=5)
    for col, title, width in zip(columns,
                                 ("Name", "Brand", "Gender", "Volume", "Type", "Year"),
                                 (250, 150, 90, 90, 180, 70)):
        tree.heading(col, text=title)
        tree.column(col, width=width)
    tree.place(x=5, y=490, width=860, height=125)
    scroll = ttk.Scrollbar(root, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.place(x=868, y=490, height=125)
    tree.bind("<<TreeviewSelect>>", on_select)

    # ---- buttons + status bar -------------------------------------------
    for text, color, command, x in (
            ("Save", "red", save, 5),
            ("Update", "red", update, 180),
            ("Delete", "red", delete, 355),
            ("Clear form", "darkblue", clear_form, 530),
            ("More Information", "darkblue", more_info, 705)):
        tk.Button(root, text=text, fg=color, width=18, command=command).place(x=x, y=627)

    tk.Label(root, textvariable=status_var, bg=BG, fg="darkgreen",
             anchor="w").place(x=5, y=662, width=890)

    do_search()
    root.mainloop()


if __name__ == "__main__":
    if login_window():
        main_window()
