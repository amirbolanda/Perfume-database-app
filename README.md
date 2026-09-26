# Perfume Information Database

A desktop app for storing and searching perfume information, built with **Python, Tkinter and SQLite**.

The idea comes from my background: in 2010 I launched Liliume Perfume, the first online perfume store in Iran. This app is a small tool for keeping perfume data organized and easy to search.

![App screenshot](screenshot.png)

## Features

- **Save** perfumes with name, brand, gender, volume, type, year, accords and description
- **Search** by part of the name, brand or accord (leave the box empty to list everything)
- **Update / delete** a perfume by selecting it in the results table
- **Duplicate protection**: the same name + brand + volume + type can't be saved twice
- **Translate** the description from English to Persian (deep-translator)
- **More information**: looks up the perfume on Google with Selenium and shows the top results
- **Login**: on first run you create a username and password, which are stored as a salted hash (PBKDF2) in a local file that is not committed

## Tech stack

Python 3 · Tkinter · SQLite · Selenium · deep-translator

## Run it

```bash
git clone https://github.com/amirbolanda/perfume-database-app.git
cd perfume-database-app
pip install -r requirements.txt
python perfume_app.py
```

Notes:
- The "More information" button needs Google Chrome installed.
- The database (`perfumes.db`) and login file (`auth.json`) are created next to the script on first use.

## Possible next steps

- Filters by brand and gender
- Export the data to CSV
- Basic data analysis on the collection (brands, accords, years) with pandas and Matplotlib

## Author

Amir Masoud Bolanda · [LinkedIn](https://www.linkedin.com) · [amirbolanda.com](https://www.amirbolanda.com)
